"""WhatsApp provider interface (Meta WhatsApp Cloud API).

WHATSAPP_PROVIDER=none (default): nothing is sent, callers get "not_configured".
WHATSAPP_PROVIDER=meta: sends via https://graph.facebook.com (needs WHATSAPP_ACCESS_TOKEN and
WHATSAPP_PHONE_NUMBER_ID). Untested against the live API. Meta only allows free-text messages inside the
24-hour customer-service window; business-initiated alerts outside it need an approved message template.
WHATSAPP_PROVIDER=memory is for automated tests only (ENVIRONMENT=test).
"""
from __future__ import annotations

import json
import logging
import re
import urllib.request
from abc import ABC, abstractmethod

from ..config import settings

log = logging.getLogger("pep_ai.whatsapp")


def normalise_phone(raw: str | None) -> str | None:
    """Return international digits only (E.164 without '+'), or None. Raises ValueError if invalid."""
    if raw is None or not raw.strip():
        return None
    digits = re.sub(r"[\s\-().]", "", raw.strip())
    if digits.startswith("+"):
        digits = digits[1:]
    if not re.fullmatch(r"[1-9]\d{7,14}", digits):
        raise ValueError("Enter the number in international format, e.g. +2348012345678")
    return digits


class WhatsAppProvider(ABC):
    @abstractmethod
    def send_text(self, to_phone: str, body: str) -> None: ...


class MetaWhatsAppProvider(WhatsAppProvider):
    def send_text(self, to_phone: str, body: str) -> None:
        url = f"https://graph.facebook.com/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/messages"
        payload = json.dumps({"messaging_product": "whatsapp", "to": to_phone, "type": "text",
                              "text": {"preview_url": False, "body": body[:1500]}}).encode()
        req = urllib.request.Request(url, data=payload, method="POST", headers={
            "Authorization": f"Bearer {settings.whatsapp_access_token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - fixed https host
            if resp.status >= 300:
                raise RuntimeError(f"WhatsApp API returned {resp.status}")


class InMemoryWhatsAppProvider(WhatsAppProvider):
    def __init__(self) -> None:
        self.outbox: list[tuple[str, str]] = []

    def send_text(self, to_phone: str, body: str) -> None:
        self.outbox.append((to_phone, body))


_provider: WhatsAppProvider | None | bool = False


def get_whatsapp_provider() -> WhatsAppProvider | None:
    global _provider
    if _provider is False:
        _provider = (MetaWhatsAppProvider() if settings.whatsapp_provider == "meta"
                     else InMemoryWhatsAppProvider() if settings.whatsapp_provider == "memory" else None)
    return _provider  # type: ignore[return-value]


def send_whatsapp(to_phone: str | None, body: str) -> str:
    """Returns 'sent', 'not_configured', 'no_phone' or 'failed'. Never raises."""
    provider = get_whatsapp_provider()
    if provider is None:
        return "not_configured"
    if not to_phone:
        return "no_phone"
    try:
        provider.send_text(to_phone, body)
        return "sent"
    except Exception as exc:  # noqa: BLE001 - never leak the token or break the request
        log.error("WhatsApp delivery failed: %s", type(exc).__name__)
        return "failed"
