# Architecture

## Module boundaries

```
Telegram (bot handlers) ─┐
Mini App (React) ────────┼──► FastAPI routes ──► services ──► models (SQLAlchemy)
Admin API ────────────────┘         │                │
                                     ▼                ▼
                              provider interfaces  PostgreSQL
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
                  TMDB           Telegram          Storage
                (sandbox/live)  (sandbox/live)    (local/S3)
                    ▼                                 ▼
                Showtime                           Payment
             (manual/future)                   (venmo_manual/future)
```

Rules this codebase follows (and why):

- **Telegram handlers are thin** (`app/telegram_bot/handlers.py`). They parse
  an update, call a service, format a reply. No business rules live there —
  the same rule that creates a Movie Night from the Mini App creates one from
  a Telegram command, because both call `movie_night_service`.
- **Core services never import a provider's SDK directly** — only the
  abstract interface (`app/providers/*/base.py`). `ticket_service` doesn't
  know what "local filesystem" means; `payment_service` doesn't know what
  Venmo is. Swapping TMDB for another movie database, or local storage for
  S3, only touches one `providers/*` package.
- **The scheduler doesn't know about Telegram.** It calls
  `notification_service.drain_pending()`, which calls the Telegram provider
  interface. If Ticket Twink ever adds email notifications, the scheduler
  code doesn't change.

## Sandbox vs. LIVE mode

`APP_MODE` (env var) is either `sandbox` (default) or `live`.

- In **sandbox**, every provider factory (`app/providers/*/factory.py`)
  returns a mock/manual implementation if the corresponding credential isn't
  set — TMDB returns canned movies, Telegram logs instead of sending,
  sandbox login bypasses Telegram auth entirely. The whole app — including
  the failure-handling paths — is exercisable with nothing but PostgreSQL.
- In **live**, `Settings.validate_live_mode_requirements` (in
  `app/core/config.py`) refuses to start unless `SECRET_KEY`,
  `TELEGRAM_BOT_TOKEN`, and `TMDB_API_KEY` are all set — so a
  half-configured production deployment fails fast at startup, not on the
  first real request.
- `/api/auth/sandbox-login` is disabled outright when `APP_MODE=live`, so it
  can never become an authentication bypass in production.

## First-run architecture {#first-run}

There's no separate setup wizard. The **first user to authenticate**
(via Telegram login, or sandbox login in dev) is automatically made an
`admin`; everyone after that is a `member`. See `app/api/routes/auth.py`
and `app/telegram_bot/handlers.py::_get_or_create_user`.

## Reliability primitives

- **Circuit breaker** (`app/core/circuit_breaker.py`): shared by the TMDB and
  Telegram live providers. After N consecutive failures it opens and calls
  fail fast (`ProviderUnavailableError`) instead of piling up slow timeouts;
  it half-opens after a cooldown to test recovery. In-process/per-worker by
  design — see the module docstring for the tradeoff and how to change it if
  Ticket Twink ever runs multiple API workers.
- **Notification retry queue** (`app/models/notification.py` +
  `app/services/notification_service.py`): every outbound message is a DB
  row before it's ever sent. Delivery happens out-of-band via the
  scheduler, with exponential backoff, capped at `NOTIFICATION_MAX_RETRIES`
  before landing in `DEAD_LETTER` — visible on `/api/admin/notifications/dead-letter`.
- **Audit log** (`app/models/audit_log.py`): every automatic failure-handling
  decision (ticket rejected, showtime changed, payment marked overpaid,
  Movie Night cancelled...) is recorded, queryable at `/api/admin/audit-log`.

## What's deliberately NOT built (and why)

- **No real showtime-provider integration.** There is no standard public API
  for third-party movie showtime lookup. `app/providers/showtime/base.py`
  documents this and ships a manual provider; adding a real one later is a
  new module + a factory branch, nothing else changes.
- **No automatic Venmo payment verification.** Venmo does not expose a
  public API for verifying incoming P2P payments. `app/providers/payment/base.py`
  documents this; reconciliation is a manual admin confirmation
  (`POST /api/payments/{id}/confirm`).
- **No OCR-based ticket verification.** Confirming a ticket photo shows the
  right movie/showtime would need real OCR, which isn't wired up. Ticket
  "mismatch" detection is a manual admin review step instead
  (`POST /api/tickets/{id}/verify`), documented in `ticket_service.py`.

Each of these follows the same pattern from the project rules: implement the
abstraction, implement the manual fallback, document what's needed to
activate real automation.
