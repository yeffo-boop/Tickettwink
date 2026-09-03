# Setup & Credentials

## Sandbox mode (default) — no credentials required

Just PostgreSQL. See the Quickstart in the root `README.md`.

## Going to LIVE mode

Set `APP_MODE=live` in `backend/.env`. The app will refuse to start unless
the following are all set — this is checked at startup
(`app/core/config.py::validate_live_mode_requirements`), not discovered at
the first real request:

### 1. `SECRET_KEY`
Any long random string, used to sign auth JWTs.
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 2. `TELEGRAM_BOT_TOKEN`
1. Message [@BotFather](https://t.me/BotFather) on Telegram.
2. `/newbot`, follow the prompts.
3. Copy the token it gives you into `TELEGRAM_BOT_TOKEN`.
4. Set `TELEGRAM_BOT_USERNAME` to the bot's `@username`.
5. Generate a random string for `TELEGRAM_WEBHOOK_SECRET`.
6. After deploying, register the webhook (replace values):
   ```bash
   curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
     -d "url=https://yourdomain.com/api/telegram/webhook" \
     -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>"
   ```
7. For the Telegram Login Widget (browser login on the Mini App), also set
   your bot's domain via @BotFather: `/setdomain`.

### 3. `TMDB_API_KEY`
1. Create an account at https://www.themoviedb.org/
2. Request an API key at https://www.themoviedb.org/settings/api
   (the "API Read Access Token" / v3 "API Key" — this app uses the v3 key
   as a query parameter; see `app/providers/tmdb/live.py`).
3. Set `TMDB_API_KEY`.

### Optional: `VENMO_HANDLE`
Your organizer @handle, shown to members as payment instructions. There is
no credential to "activate" real Venmo integration — see
`app/providers/payment/base.py` for why (no public P2P verification API
exists) and how reconciliation works instead.

### Optional: a real showtime provider
Not implemented — see `app/providers/showtime/base.py` for what's needed to
add one. Until then `SHOWTIME_PROVIDER=manual` is what runs even in live
mode: an admin types in the cinema/time via `PUT /api/movie-nights/{id}/showtime`.

## Deployment

See `deploy/systemd/tickettwink-api.service` and `deploy/nginx/tickettwink.conf`
for the target layout, and `scripts/deploy.sh` for the deploy procedure
(install deps → migrate → build frontend → restart service → health check,
stopping at the first failure so a broken deploy never touches the running
service).
