"""Application configuration.

Fail-safe rules (enforced at import time):
* No secret has a hardcoded default.
* In production, a strong JWT_SECRET, a PostgreSQL DATABASE_URL, HTTPS CORS origins,
  a real e-mail provider and migrations (not create_all) are mandatory; otherwise the
  process refuses to start.
* In development/test, a missing JWT_SECRET produces a random ephemeral secret
  (sessions are invalidated on every restart) rather than a known value.
"""
import logging
import secrets
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("pep_ai.config")

_PLACEHOLDER_MARKERS = ("replace", "change-me", "changeme", "example", "secret-key", "your-secret")


class ConfigurationError(RuntimeError):
    pass


class Settings(BaseSettings):
    app_name: str = "PEP AI API"
    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./pep_ai_dev.db"

    # --- auth / sessions ---
    jwt_secret: str = ""
    jwt_issuer: str = "pep-ai"
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    require_email_verification: bool | None = None  # default: True in production/test, False in development
    login_max_failures: int = 5
    login_lockout_minutes: int = 15

    # --- web ---
    cors_origins: str = "http://127.0.0.1:5500,http://localhost:5500,http://127.0.0.1:5173,http://localhost:5173"
    app_base_url: str = "http://127.0.0.1:5500"  # used to build links in e-mails
    enable_docs: bool | None = None  # default: on except production
    trusted_proxy_hops: int = 0  # number of reverse proxies in front of the API (for client IP)

    # --- database ---
    auto_create_tables: bool | None = None  # development/test convenience only; never in production

    # --- rate limiting ---
    rate_limit_enabled: bool = True
    rate_limit_backend: Literal["memory", "redis"] = "memory"
    redis_url: str = ""
    login_rate_limit_per_minute: int = 10
    register_rate_limit_per_hour: int = 10
    sensitive_rate_limit_per_hour: int = 10  # password reset, verification resend, invitation preview/accept

    # --- tokens ---
    invite_ttl_hours: int = 72
    reset_ttl_minutes: int = 60
    verify_ttl_hours: int = 24

    # --- e-mail (no provider => nothing is sent; see docs) ---
    email_provider: Literal["none", "smtp", "memory"] = "none"
    email_from: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True

    # --- WhatsApp (Meta WhatsApp Cloud API). none => nothing is sent. ---
    whatsapp_provider: Literal["none", "meta", "memory"] = "none"
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_api_version: str = "v20.0"

    # --- AI model providers (keys live ONLY in the server .env, never in the database or the browser) ---
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    openai_model: str = "gpt-4o-mini"          # change to the model you have access to
    anthropic_model: str = "claude-sonnet-5-5"  # change to the model you have access to
    guide_provider: Literal["auto", "openai", "anthropic", "memory", "none"] = "auto"
    llm_max_output_tokens: int = 800
    llm_timeout_seconds: int = 60
    agent_rate_limit_per_hour: int = 60   # per IP and per user

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        prod = self.environment == "production"

        # JWT secret
        if not self.jwt_secret:
            if prod:
                raise ConfigurationError("JWT_SECRET is required in production.")
            self.jwt_secret = secrets.token_urlsafe(48)
            log.warning("JWT_SECRET not set: using a random ephemeral secret (sessions reset on restart).")
        else:
            low = self.jwt_secret.lower()
            if len(self.jwt_secret) < 32 or any(m in low for m in _PLACEHOLDER_MARKERS):
                raise ConfigurationError("JWT_SECRET must be a random value of at least 32 characters (not a placeholder).")

        # database URL normalisation (psycopg 3 driver)
        if self.database_url.startswith("postgresql://"):
            self.database_url = "postgresql+psycopg://" + self.database_url[len("postgresql://"):]
        elif self.database_url.startswith("postgres://"):
            self.database_url = "postgresql+psycopg://" + self.database_url[len("postgres://"):]

        # defaults that depend on environment
        if self.require_email_verification is None:
            self.require_email_verification = self.environment != "development"
        if self.auto_create_tables is None:
            self.auto_create_tables = not prod
        if self.enable_docs is None:
            self.enable_docs = not prod

        if self.email_provider == "memory" and self.environment != "test":
            raise ConfigurationError("EMAIL_PROVIDER=memory is only permitted when ENVIRONMENT=test.")
        if self.guide_provider == "memory" and self.environment != "test":
            raise ConfigurationError("GUIDE_PROVIDER=memory is only permitted when ENVIRONMENT=test.")
        if self.whatsapp_provider == "memory" and self.environment != "test":
            raise ConfigurationError("WHATSAPP_PROVIDER=memory is only permitted when ENVIRONMENT=test.")
        if self.whatsapp_provider == "meta" and not (self.whatsapp_access_token and self.whatsapp_phone_number_id):
            raise ConfigurationError("WHATSAPP_PROVIDER=meta requires WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID.")
        if self.email_provider == "smtp" and not (self.smtp_host and self.email_from):
            raise ConfigurationError("EMAIL_PROVIDER=smtp requires SMTP_HOST and EMAIL_FROM.")
        if self.rate_limit_backend == "redis" and not self.redis_url:
            raise ConfigurationError("RATE_LIMIT_BACKEND=redis requires REDIS_URL.")

        if prod:
            problems = []
            if not self.database_url.startswith("postgresql"):
                problems.append("DATABASE_URL must be PostgreSQL")
            origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
            if not origins or any(o == "*" or not o.startswith("https://") for o in origins):
                problems.append("CORS_ORIGINS must list exact https:// origins (no wildcard)")
            if not self.app_base_url.startswith("https://"):
                problems.append("APP_BASE_URL must be https://")
            if self.email_provider == "none":
                problems.append("EMAIL_PROVIDER must be configured (smtp) - verification and reset e-mails are required")
            if not self.require_email_verification:
                problems.append("REQUIRE_EMAIL_VERIFICATION cannot be disabled")
            if self.auto_create_tables:
                problems.append("AUTO_CREATE_TABLES must be false (use Alembic migrations)")
            if self.rate_limit_backend == "memory":
                log.warning("RATE_LIMIT_BACKEND=memory is per-process; use redis when running more than one instance.")
            if problems:
                raise ConfigurationError("Unsafe production configuration: " + "; ".join(problems))
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
