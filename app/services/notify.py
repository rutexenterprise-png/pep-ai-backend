"""Task notifications by e-mail and WhatsApp. Functions take plain values (no ORM objects) so they can run
as background tasks after the response is sent. Delivery problems are logged, never raised."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from . import email as email_service
from .whatsapp import send_whatsapp

log = logging.getLogger("pep_ai.notify")


@dataclass
class Recipient:
    name: str
    email: str | None
    phone: str | None


def _when(dt: datetime | None) -> str:
    return dt.strftime("%d %b %Y %H:%M UTC") if dt else "no deadline"


def _deliver(r: Recipient, subject: str, body: str) -> None:
    if r.email:
        status = email_service.send_email(email_service.EmailMessage(r.email, subject, body))
        if status != "sent":
            log.info("task e-mail to user not delivered: %s", status)
    status = send_whatsapp(r.phone, f"{subject}\n\n{body}")
    if status not in ("sent", "not_configured", "no_phone"):
        log.info("task WhatsApp not delivered: %s", status)


def task_assigned(r: Recipient, *, org_name: str, assigner: str, title: str, description: str | None,
                  due_at: datetime | None, priority: str) -> None:
    body = (f"Hello {r.name},\n\n{assigner} assigned you a new task in {org_name}:\n\n{title}\n"
            f"{description + chr(10) if description else ''}\nPriority: {priority}\nDeadline: {_when(due_at)}\n\n"
            f"Open PEP AI to start it and report when it is done.")
    _deliver(r, f"New task: {title}", body)


def task_completed(recipients: list[Recipient], *, org_name: str, staff_name: str, title: str,
                   note: str | None, on_time: bool) -> None:
    for r in recipients:
        body = (f"Hello {r.name},\n\n{staff_name} has completed a task in {org_name}:\n\n{title}\n"
                f"{'Completion note: ' + note + chr(10) if note else ''}"
                f"Finished {'on time' if on_time else 'after the deadline'}.")
        _deliver(r, f"Task completed: {title}", body)
