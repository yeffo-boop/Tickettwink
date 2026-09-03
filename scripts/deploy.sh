#!/usr/bin/env bash
# Ticket Twink deployment script.
#
# "failed deployment" handling: every step that can fail runs before the
# live service is touched. The systemd service is only restarted after
# dependencies install, migrations apply, and the frontend builds
# successfully — so a failure at any earlier step leaves the currently
# running service untouched and serving traffic. `set -e` means the script
# stops at the first failure instead of leaving things half-updated.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Installing backend dependencies"
cd backend
source .venv/bin/activate
pip install -q -r requirements.txt
cd ..

echo "==> Running database migrations"
./scripts/migrate.sh

echo "==> Building frontend"
cd frontend
npm ci --silent
npm run build
cd ..

echo "==> Restarting API service"
sudo systemctl restart tickettwink-api

echo "==> Health check"
for i in $(seq 1 10); do
    if curl -sf http://127.0.0.1:8000/health > /dev/null; then
        echo "Deployment succeeded — service is healthy."
        exit 0
    fi
    sleep 2
done

echo "DEPLOYMENT FAILED HEALTH CHECK. Service did not become healthy within 20s." >&2
echo "Check: sudo journalctl -u tickettwink-api -n 100 --no-pager" >&2
echo "Rollback: git checkout <previous-good-commit>, then re-run this script." >&2
exit 1
