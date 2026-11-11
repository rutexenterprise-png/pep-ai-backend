"""AI model providers (OpenAI and Anthropic) over plain HTTPS - no extra dependency.

Keys come only from the server settings. Errors never include the key or the provider's raw response.
Provider 'memory' exists for automated tests only (ENVIRONMENT=test).
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from ..config import settings

log = logging.getLogger("pep_ai.llm")

PROVIDERS = ("openai", "anthropic")
last_call: dict = {}  # test introspection (memory provider only)


class LLMError(Exception):
    pass


class LLMNotConfigured(LLMError):
    pass


def available_providers() -> list[str]:
    out = []
    if settings.anthropic_api_key:
        out.append("anthropic")
    if settings.openai_api_key:
        out.append("openai")
    return out


def resolve_guide_provider() -> str | None:
    choice = settings.guide_provider
    if choice == "none":
        return None
    if choice == "memory":
        return "memory"
    if choice in PROVIDERS:
        return choice if choice in available_providers() else None
    avail = available_providers()
    return avail[0] if avail else None


def default_model(provider: str) -> str:
    return settings.openai_model if provider == "openai" else settings.anthropic_model


def _post(url: str, headers: dict, payload: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=settings.llm_timeout_seconds) as resp:  # noqa: S310 - fixed https hosts
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        log.error("LLM HTTP error %s from %s", exc.code, url.split("/")[2])
        raise LLMError(f"The AI provider returned HTTP {exc.code}.") from exc
    except Exception as exc:  # noqa: BLE001
        log.error("LLM call failed: %s", type(exc).__name__)
        raise LLMError("Could not reach the AI provider.") from exc


def complete(provider: str, model: str | None, system: str, messages: list[dict], max_tokens: int | None = None) -> str:
    """messages: [{"role": "user"|"assistant", "content": str}, ...] ending with the user turn."""
    max_tokens = min(max_tokens or settings.llm_max_output_tokens, 4000)
    if provider == "memory" and settings.environment == "test":
        last_call.clear(); last_call.update(system=system, messages=list(messages), model=model)
        return "MEMORY-REPLY: " + messages[-1]["content"][:200]
    if provider == "openai":
        if not settings.openai_api_key:
            raise LLMNotConfigured("OPENAI_API_KEY is not set on the server.")
        data = _post("https://api.openai.com/v1/chat/completions",
                     {"Authorization": f"Bearer {settings.openai_api_key}"},
                     {"model": model or settings.openai_model, "max_completion_tokens": max_tokens,
                      "messages": [{"role": "system", "content": system}, *messages]})
        try:
            return (data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("Unexpected response from the AI provider.") from exc
    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise LLMNotConfigured("ANTHROPIC_API_KEY is not set on the server.")
        data = _post("https://api.anthropic.com/v1/messages",
                     {"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01"},
                     {"model": model or settings.anthropic_model, "max_tokens": max_tokens, "system": system,
                      "messages": messages})
        try:
            return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text").strip()
        except (KeyError, TypeError) as exc:
            raise LLMError("Unexpected response from the AI provider.") from exc
    raise LLMNotConfigured(f"Provider '{provider}' is not supported. Use openai or anthropic.")
