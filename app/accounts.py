from datetime import timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from ..config import settings
from ..models import RefreshToken, User, UserToken
from ..security import new_opaque_token
from ..utils import utcnow


def issue_password_reset(db: Session, user: User) -> str:
    """Invalidate earlier unused reset tokens and create a new one. Caller commits and e-mails it."""
    db.execute(update(UserToken).where(UserToken.user_id == user.id, UserToken.purpose == "password_reset",
                                       UserToken.used_at.is_(None)).values(used_at=utcnow()))
    raw, hashed = new_opaque_token()
    db.add(UserToken(user_id=user.id, purpose="password_reset", token_hash=hashed,
                     expires_at=utcnow() + timedelta(minutes=settings.reset_ttl_minutes)))
    db.flush()
    return raw


def revoke_all_sessions(db: Session, user_id: int) -> None:
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
               .values(revoked_at=utcnow()))
