# Ticket Twink 🎟️💅

A private movie-group platform: plan a Movie Night, share it with your group via
Telegram, collect ticket proof and payment, and let the app handle the boring
(and failure-prone) parts — showtime changes, cancellations, flaky
integrations — gracefully instead of falling over.

Ticket Twink is **not** a generic Telegram bot. Telegram is one integration
among several (TMDB for movie info, a showtime provider, Venmo for payment,
local/S3 for storage); the core business logic doesn't depend on any of them
directly. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Stack

- **Backend**: FastAPI + SQLAlchemy (async) + Alembic + PostgreSQL
- **Frontend**: React + TypeScript + Vite (the Mini App / web UI)
- **Bot**: python-telegram-bot, webhook-driven, thin handlers only
- **Scheduler**: APScheduler, in-process
- **Deployment**: systemd + nginx (see `deploy/`)

## Quickstart (sandbox mode — no credentials needed)

Sandbox mode is the default. Every external provider (TMDB, Telegram,
Showtime, Payment) runs against a local mock/manual implementation, so you
can run the whole app with nothing but PostgreSQL installed.

```bash
# 1. Database
sudo -u postgres createuser tickettwink -P   # set a password
sudo -u postgres createdb tickettwink_dev -O tickettwink

# 2. Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # edit DATABASE_URL if needed; APP_MODE=sandbox by default
alembic upgrade head
uvicorn app.main:app --reload

# 3. Frontend (separate terminal)
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open http://localhost:5173, click **Sandbox Sign-In** (the first person to
sign in becomes an admin — see `docs/ARCHITECTURE.md#first-run`), and create
a Movie Night.

## Running the checks

```bash
cd backend && pytest -q && ruff check .   # Python 3.12; uses in-memory SQLite
cd frontend && npm run lint && npm run build
```

CI (`.github/workflows/ci.yml`) runs these on every pull request, plus the
Alembic migrations against PostgreSQL 16 (upgrade, `alembic check`, and a
downgrade/upgrade round trip).

## Going live

Sandbox mode swaps in real integrations once you provide credentials and set
`APP_MODE=live`. See [`docs/SETUP.md`](docs/SETUP.md) for exactly what's
needed for each provider (Telegram, TMDB) and what is **not** available
(a real showtime API, automatic Venmo verification) and why.

## Failure handling

Every integration in this app is expected to fail sometimes. How each
scenario is handled — TMDB down, Telegram down, malformed/duplicate/missing
tickets, partial/overpayment, a cancelled Movie Night, a failed deploy or
migration — is documented in
[`docs/FAILURE_SCENARIOS.md`](docs/FAILURE_SCENARIOS.md), with pointers to
the code and how each was actually tested.

## Repository layout

```
backend/          FastAPI app, SQLAlchemy models, Alembic migrations
  app/core/        config, DB session, security, circuit breaker
  app/models/       SQLAlchemy models
  app/providers/    provider interfaces + sandbox/live implementations
  app/services/     business logic (provider-agnostic)
  app/scheduler/     background jobs
  app/telegram_bot/  thin Telegram handlers
  app/api/routes/     FastAPI routers
frontend/         React + Vite app
deploy/           systemd units, nginx config
scripts/          deploy.sh, migrate.sh
docs/             architecture, setup, failure-scenario docs
```
