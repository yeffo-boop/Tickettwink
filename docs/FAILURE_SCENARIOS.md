# Failure Scenarios

How Ticket Twink handles each required failure scenario, where the
mechanism lives, and how it was actually verified (not just designed).

---

### TMDB unavailable
**Mechanism:** `movie_night_service.create_movie_night` calls the TMDB
provider through the shared circuit breaker
(`app/core/circuit_breaker.py`). If TMDB is down, `ProviderUnavailableError`
is caught, the Movie Night is still created (using the title as typed) with
`tmdb_cache_stale=True`. A scheduler job (`_job_refresh_stale_tmdb`, every
15 min) retries enrichment until it succeeds. The frontend shows a
"⚠ Movie info pending" badge on stale entries.
**Code:** `app/providers/tmdb/live.py`, `app/services/movie_night_service.py`
**Tested:** Verified in sandbox mode, where `TMDBSandboxProvider` is used
instead of live TMDB (no API key configured in this environment) —
confirms the create-without-TMDB path and stale-cache flag. The circuit
breaker's open/half-open/closed transitions are exercised by
`backend/tests/test_circuit_breaker.py` (unit test, no network). Live-TMDB
failure was **not** tested against the real API (no `TMDB_API_KEY`
available in this environment) — the retry/backoff wrapper (`tenacity`) and
breaker wiring were code-reviewed but not integration-tested live.

### Showtime API unavailable
**Mechanism:** No real showtime provider exists to integrate against (see
`app/providers/showtime/base.py` for why). The shipped `ManualShowtimeProvider`
never makes a network call, so this failure mode can't occur with the
current provider — `Showtime.is_stale` / `ShowtimeStatus.UNKNOWN` exist on
the model precisely so a future real provider can flag "last known value,
couldn't refresh" the same way TMDB does.
**Code:** `app/providers/showtime/base.py`, `app/models/showtime.py`
**Tested:** N/A until a real provider is implemented — documented, not
fabricated.

### Telegram temporary failure
**Mechanism:** All sends go through `notification_service.queue_notification`
(write a DB row) then `drain_pending` (scheduler, every 30s) actually
delivers. A `ProviderUnavailableError` (breaker open) or transient network
error schedules a retry with exponential backoff
(`NOTIFICATION_RETRY_BASE_SECONDS * 2^attempt`) instead of losing the
message or blocking the request.
**Code:** `app/services/notification_service.py`, `app/providers/telegram/live.py`
**Tested:** End-to-end in sandbox mode: created a Movie Night, changed its
showtime (queues a notification), confirmed the scheduler drained it and —
since the sandbox user has no linked Telegram chat — correctly dead-lettered
it with a clear reason, visible at `GET /api/admin/notifications/dead-letter`.
Did not test against a real flaky Telegram connection (no bot token
configured here).

### Malformed ticket upload
**Mechanism:** `ticket_service._validate_structure` checks content-type
allowlist, size limits, magic-byte headers, and (for images) that Pillow can
actually decode the file — all before anything touches storage or the DB.
**Code:** `app/services/ticket_service.py`
**Tested:** Live, via `curl` against a running server — uploaded a `.txt`
file mislabeled as `application/pdf`; got `400 Bad Request` with
`"File claims to be a PDF but doesn't start with a PDF header"`. Also
covered by `backend/tests/test_ticket_service.py` (wrong content-type,
empty file, fake PDF header, valid PNG accepted).

### Duplicate ticket
**Mechanism:** SHA-256 of the file content is checked against existing
tickets for the same Movie Night before insert; a DB unique constraint
(`uq_ticket_movienight_filehash`) is the race-condition backstop.
**Code:** `app/services/ticket_service.py::upload_ticket`,
`app/models/ticket.py`
**Tested:** Live — uploaded the same PNG twice; second attempt returned
`409 Conflict` naming the existing ticket ID. Also covered by
`backend/tests/test_ticket_service.py::test_duplicate_upload_rejected`.

### Ticket mismatch
**Mechanism:** No automated OCR is wired up (documented decision, see
`ARCHITECTURE.md`). An admin reviews the uploaded file via
`GET /api/tickets/{id}/file` and calls `POST /api/tickets/{id}/verify`
with `matches: false` and notes; the ticket becomes `MISMATCH` and is
surfaced at `GET /api/admin/tickets/mismatched-or-missing`.
**Code:** `app/services/ticket_service.py::verify_ticket_manual`
**Tested:** Code path exercised via the `verify` endpoint logic (same
function backs both matches=true and matches=false); not tested against a
real mismatched photo since that requires human judgment by design.

### Missing ticket
**Mechanism:** Scheduler job `_job_check_missing_tickets` (hourly) finds
Movie Nights within 48h whose paid attendees have no `UPLOADED`/`VERIFIED`
ticket and queues a reminder notification per person.
**Code:** `app/scheduler/jobs.py`, `app/services/ticket_service.py::find_missing_tickets`
**Tested:** Code-reviewed and exercised via `find_missing_tickets` logic
against seeded data; not run against a live 48-hour clock (would require
waiting or mocking time, out of scope for this pass).

### Partial payment
**Mechanism:** `Payment.amount_received_cents` is cumulative across
possibly-multiple manual confirmations; status is recomputed from the
running total every time (`PENDING → PARTIAL → PAID → OVERPAID`).
**Code:** `app/services/payment_service.py::confirm_payment`
**Tested:** Logic covered by `backend/tests/test_payment_service.py`
(unit tests for all four status transitions).

### Overpayment
**Mechanism:** Same function as above; `amount_received_cents > amount_expected_cents`
→ `OVERPAID`, logged, and flaggable for refund via
`payment_service.mark_refund_due`.
**Code:** `app/services/payment_service.py`
**Tested:** Live, via `curl` — created a $15.00 payment, confirmed $20.00
received; response showed `"status": "overpaid"`. Confirmed via
`/api/admin/payments/refunds-due` after a subsequent Movie Night
cancellation.

### Failed notification
**Mechanism:** After `NOTIFICATION_MAX_RETRIES` (default 5) failed attempts,
a notification becomes `DEAD_LETTER` — never silently dropped — and is
listed at `GET /api/admin/notifications/dead-letter` with a one-click
`POST /api/admin/notifications/{id}/requeue`.
**Code:** `app/services/notification_service.py::_schedule_retry_or_deadletter`
**Tested:** Live — sandbox users have no Telegram chat linked, so every
queued notification exercises the "can't deliver" path; confirmed it lands
in the dead-letter list with a clear `error_message`, and that requeue
resets it to `PENDING`.

### Changed showtime
**Mechanism:** `movie_night_service.update_showtime` is the single place a
showtime can change; it records `previous_starts_at`, flips
`MovieNight.status` to `SHOWTIME_CHANGED`, and notifies every distinct
ticket holder.
**Code:** `app/services/movie_night_service.py::update_showtime`
**Tested:** Live — set an initial showtime, then changed it; response
showed `"status": "showtime_changed"`, and a `showtime_changed` notification
was queued and (correctly) dead-lettered for the recipient-less sandbox
user.

### Cancelled Movie Night
**Mechanism:** `movie_night_service.cancel_movie_night` cancels every
ticket, flags every non-zero payment `REFUND_DUE` (or `CANCELLED` if
nothing was paid), records the reason, and notifies every ticket holder.
**Code:** `app/services/movie_night_service.py::cancel_movie_night`
**Tested:** Live — cancelled a Movie Night with an overpaid ($20 vs $15)
payment attached; confirmed the ticket flipped to `CANCELLED`, the payment
to `REFUND_DUE` (visible in the Admin Dashboard screenshot), and a
cancellation notification was queued.

### Failed deployment
**Mechanism:** `scripts/deploy.sh` runs dependency install → migrations →
frontend build → **only then** restarts the systemd service, then polls
`/health` and fails loudly (with a rollback pointer) if the service doesn't
come up healthy. A failure at any earlier step never touches the
already-running service.
**Code:** `scripts/deploy.sh`, `deploy/systemd/tickettwink-api.service`
(`Restart=on-failure` + `StartLimitBurst` so a crash-looping deploy doesn't
hammer the box forever)
**Tested:** Script logic reviewed; not run against a real systemd host in
this environment (no systemd/root deploy target here) — this is a process
control, not application code, and is documented rather than fabricated as
"tested."

### Failed migration
**Mechanism:** `scripts/migrate.sh` runs `alembic upgrade head`; Alembic
runs each migration in a transaction, so a failing migration doesn't
partially apply. On failure the script exits non-zero *before*
`deploy.sh` reaches the service-restart step, and prints the
`alembic downgrade -1` escape hatch.
**Code:** `scripts/migrate.sh`, `backend/alembic/env.py`
**Tested:** Live — ran `alembic upgrade head` against a real local
PostgreSQL 16 instance from a clean schema; all 9 tables created
successfully (`\dt` confirmed). Did not test an intentionally-broken
migration in this pass, but the transactional/exit-code behavior is
Alembic's own well-documented guarantee, not something this app
reimplements.
