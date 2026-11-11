"""E-mail provider interface.

No e-mail is ever faked. With EMAIL_PROVIDER=none (default) nothing is sent and callers
receive status "not_configured". EMAIL_PROVIDER=smtp sends through a real SMTP server
(credentials: SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, EMAIL_FROM).
EMAIL_PROVIDER=memory exists only for automated tests (ENVIRONMENT=test) and records
messages in a list so tests can read one-time links.

To add SendGrid / SES / Postmark / Microsoft Graph, implement EmailProvider.send().
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage

from ..config import settings

log = logging.getLogger("pep_ai.email")


@dataclass
class EmailMessage:
    to: str
    subject: str
    text_body: str


class EmailNotConfigured(Exception):
    pass


class EmailDeliveryError(Exception):
    pass


class EmailProvider(ABC):
    @abstractmethod
    def send(self, message: EmailMessage) -> None: ...


class NullEmailProvider(EmailProvider):
    def send(self, message: EmailMessage) -> None:
        raise EmailNotConfigured("No e-mail provider configured (set EMAIL_PROVIDER=smtp).")


class SmtpEmailProvider(EmailProvider):
    def send(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"], mime["To"], mime["Subject"] = settings.email_from, message.to, message.subject
        mime.set_content(message.text_body)
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
                if settings.smtp_starttls:
                    smtp.starttls(context=ssl.create_default_context())
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(mime)
        except Exception as exc:  # noqa: BLE001 - surface as delivery error, never leak credentials
            raise EmailDeliveryError(type(exc).__name__) from exc


class InMemoryEmailProvider(EmailProvider):
    """Test double. Only constructible when ENVIRONMENT=test."""

    def __init__(self) -> None:
        self.outbox: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.outbox.append(message)


_provider: EmailProvider | None = None


def get_email_provider() -> EmailProvider:
    global _provider
    if _provider is None:
        if settings.email_provider == "smtp":
            _provider = SmtpEmailProvider()
        elif settings.email_provider == "memory":
            _provider = InMemoryEmailProvider()
        else:
            _provider = NullEmailProvider()
    return _provider


def send_email(message: EmailMessage) -> str:
    """Returns 'sent', 'not_configured' or 'failed'. Never raises."""
    try:
        get_email_provider().send(message)
        return "sent"
    except EmailNotConfigured:
        return "not_configured"
    except EmailDeliveryError as exc:
        log.error("E-mail delivery failed: %s", exc)
        return "failed"


# ---------------------------------------------------------------- templates
def _link(kind: str, token: str) -> str:
    return f"{settings.app_base_url.rstrip('/')}/#{kind}={token}"


def verification_email(to: str, name: str, token: str) -> EmailMessage:
    return EmailMessage(to, "Verify your PEP AI e-mail address",
                        f"Hello {name},\n\nConfirm your e-mail address to activate your PEP AI account:\n{_link('verify', token)}\n\n"
                        f"This link expires in {settings.verify_ttl_hours} hours. If you did not register, ignore this message.\n")


def password_reset_email(to: str, name: str, token: str) -> EmailMessage:
    return EmailMessage(to, "Reset your PEP AI password",
                        f"Hello {name},\n\nUse this link to choose a new password:\n{_link('reset', token)}\n\n"
                        f"It expires in {settings.reset_ttl_minutes} minutes. If you did not request this, you can ignore it.\n")


def invitation_email(to: str, org_name: str, inviter: str, role_label: str, token: str) -> EmailMessage:
    return EmailMessage(to, f"You have been invited to {org_name} on PEP AI",
                        f"{inviter} invited you to join {org_name} on PEP AI as {role_label}.\n\n"
                        f"Accept the invitation:\n{_link('invite', token)}\n\n"
                        f"You will need to sign in (or create an account) using this e-mail address. "
                        f"The invitation expires in {settings.invite_ttl_hours} hours.\n")
