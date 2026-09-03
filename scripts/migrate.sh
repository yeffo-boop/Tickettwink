#!/usr/bin/env bash
# Applies pending Alembic migrations. Exits non-zero on failure so callers
# (deploy.sh, CI) can stop before restarting the service on a broken schema —
# this is the "failed migration" handling: a migration failure never makes
# it as far as a service restart.
set -euo pipefail
cd "$(dirname "$0")/../backend"
source .venv/bin/activate

echo "Current revision:"
alembic current

echo "Applying migrations..."
if ! alembic upgrade head; then
    echo "MIGRATION FAILED. Database left at last successful revision (Alembic runs each" >&2
    echo "migration in a transaction, so a failed one does not partially apply)." >&2
    echo "To roll back a migration that DID apply cleanly but you want reverted:" >&2
    echo "    alembic downgrade -1" >&2
    exit 1
fi

echo "Migrations applied successfully."
alembic current
