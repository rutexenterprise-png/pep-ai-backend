from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import permissions as perm
from .config import settings
from .database import get_db, set_rls_context
from .models import OrgMember, Organization, User
from .security import decode_access_claims
from .services import audit

bearer = HTTPBearer(auto_error=False)


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                 db: Session = Depends(get_db)) -> User:
    if not credentials:
        raise HTTPException(401, "Authentication required")
    claims = decode_access_claims(credentials.credentials)
    user = db.get(User, int(claims["sub"]))
    if not user or not user.is_active:
        raise HTTPException(401, "User account is unavailable")
    if int(claims.get("ver", 0)) != user.token_version:
        raise HTTPException(401, "Session is no longer valid. Please sign in again.")
    set_rls_context(db, user_id=user.id)
    return user


def verified_user(user: User = Depends(current_user)) -> User:
    if settings.require_email_verification and user.email_verified_at is None:
        raise HTTPException(403, "Please verify your e-mail address before continuing.")
    return user


@dataclass
class OrgContext:
    user: User
    member: OrgMember
    org: Organization
    permissions: frozenset
    request: Request

    @property
    def role(self) -> str:
        return self.member.role


def resolve_org_context(db: Session, org_id: int, user: User, request: Request,
                        not_found: str = "Organization not found") -> OrgContext:
    """Resolve the caller's active membership of org_id.

    Non-members receive 404 (the organisation's existence is not revealed).
    Suspended / deactivated members are refused immediately (checked on every request).
    """
    member = db.scalar(select(OrgMember).where(OrgMember.organization_id == org_id, OrgMember.user_id == user.id))
    if not member:
        raise HTTPException(404, not_found)
    if member.status != "active":
        raise HTTPException(403, f"Your access to this organization is {member.status}")
    org = db.get(Organization, org_id)
    if not org or org.status != "active":
        raise HTTPException(403, "This organization is not active")
    set_rls_context(db, org_id=org_id)
    return OrgContext(user=user, member=member, org=org, request=request,
                      permissions=perm.effective_permissions(member.role, member.granted_permissions, member.denied_permissions))


def org_context(org_id: int, request: Request, user: User = Depends(current_user),
                db: Session = Depends(get_db)) -> OrgContext:
    return resolve_org_context(db, org_id, user, request)


def ensure(ctx: OrgContext, db: Session, permission: str) -> None:
    """Raise 403 (and audit the denial) unless the caller holds `permission`."""
    if permission not in ctx.permissions:
        audit.record(db, "permission.denied", request=ctx.request, actor_user_id=ctx.user.id,
                     organization_id=ctx.org.id, detail={"permission": permission, "path": ctx.request.url.path})
        db.commit()
        raise HTTPException(403, "You do not have permission to perform this action")


def require(permission: str):
    """Dependency factory: caller must hold `permission` in the organisation in the URL."""

    def dependency(ctx: OrgContext = Depends(org_context), db: Session = Depends(get_db)) -> OrgContext:
        ensure(ctx, db, permission)
        return ctx

    return dependency
