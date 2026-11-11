from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

_sqlite = settings.database_url.startswith("sqlite")
connect_args = {"check_same_thread": False} if _sqlite else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# PostgreSQL row-level-security context
#
# RLS policies (see alembic/versions/0002_*) read three transaction-local settings:
#   app.current_user_id, app.current_org_id, app.rls_bypass
# They are stored in session.info and re-applied at the start of every transaction,
# because set_config(..., is_local=true) is discarded on COMMIT.
# On SQLite (development/tests) this is a no-op; tenant isolation is then enforced
# by the application layer only.
# ---------------------------------------------------------------------------
_APPLY_SQL = text(
    "SELECT set_config('app.current_user_id', :u, true),"
    " set_config('app.current_org_id', :o, true),"
    " set_config('app.rls_bypass', :b, true)"
)


def _rls_params(info: dict) -> dict:
    return {
        "u": str(info.get("rls_user_id") or ""),
        "o": str(info.get("rls_org_id") or ""),
        "b": "on" if info.get("rls_bypass") else "off",
    }


@event.listens_for(Session, "after_begin")
def _apply_rls_context(session, transaction, connection):
    if connection.dialect.name == "postgresql":
        connection.execute(_APPLY_SQL, _rls_params(session.info))


def set_rls_context(db: Session, *, user_id: int | None = None, org_id: int | None = None, bypass: bool | None = None) -> None:
    if user_id is not None:
        db.info["rls_user_id"] = user_id
    if org_id is not None:
        db.info["rls_org_id"] = org_id
    if bypass is not None:
        db.info["rls_bypass"] = bypass
    if db.get_bind().dialect.name == "postgresql" and db.in_transaction():
        db.execute(_APPLY_SQL, _rls_params(db.info))


@contextmanager
def system_context(db: Session):
    """Narrow, explicit RLS bypass for pre-tenant lookups (e.g. resolving an invitation token).
    Never use for request handling that returns tenant data to a user."""
    previous = bool(db.info.get("rls_bypass"))
    set_rls_context(db, bypass=True)
    try:
        yield
    finally:
        set_rls_context(db, bypass=previous)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
