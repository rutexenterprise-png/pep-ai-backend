# PEP AI API (Milestone 1)

See `../docs/MILESTONE1_REPORT.md` for full installation, configuration, migration, testing and deployment instructions.

Key commands (from this directory):
* `pip install -r requirements-dev.txt`
* `pytest -q` — run first; this code has not been executed yet
* `alembic upgrade head` — apply migrations (existing first-package DB: `alembic stamp 0001` first)
* `uvicorn app.main:app --reload`

Production refuses to start unless `JWT_SECRET`, PostgreSQL `DATABASE_URL`, https `CORS_ORIGINS`/`APP_BASE_URL` and an SMTP provider are configured.
