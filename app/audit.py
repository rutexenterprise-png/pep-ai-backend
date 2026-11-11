from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from ..models import AuditLog
from ..utils import client_ip

_SENSITIVE = ("password", "token", "secret", "authorization", "hash")


def _scrub(value):
    if isinstance(value, dict):
        return {k: ("[redacted]" if any(s in k.lower() for s in _SENSITIVE) else _scrub(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(v) for v in value]
    return value


def record(db: Session, action: str, *, request: Request | None = None, actor_user_id: int | None = None,
           organization_id: int | None = None, target_type: str | None = None, target_id=None,
           detail: dict | None = None) -> AuditLog:
    """Add an audit row to the caller's transaction (commit together with the change itself)."""
    entry = AuditLog(
        organization_id=organization_id, actor_user_id=actor_user_id, action=action,
        target_type=target_type, target_id=None if target_id is None else str(target_id),
        detail=_scrub(detail) if detail else None,
        ip=client_ip(request) or None,
        user_agent=(request.headers.get("user-agent", "")[:255] or None) if request is not None else None,
    )
    db.add(entry)
    return entry
