#!/usr/bin/env bash
# Deploy NeuroWeave on a single server via Docker Compose.
#
# Run this ON the target server (or have CI SSH in and run it there - see
# .github/workflows/deploy.yml). Expects to be run from the repo root,
# with .env.prod already present (see docs/DEPLOYMENT.md for how to
# create it) - secrets live only on the server, never in CI or git.
#
# Usage:
#   ./scripts/deploy.sh [git-ref]     # defaults to origin/main
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

REF="${1:-origin/main}"
ENV_FILE="${ENV_FILE:-.env.prod}"
COMPOSE="docker compose -f docker-compose.prod.yml --env-file $ENV_FILE"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found. See docs/DEPLOYMENT.md - it must exist on the server before the first deploy." >&2
  exit 1
fi

echo "==> Fetching latest code"
git fetch origin
PREVIOUS_SHA="$(git rev-parse HEAD)"
git checkout --detach "$REF"
NEW_SHA="$(git rev-parse HEAD)"
echo "    $PREVIOUS_SHA -> $NEW_SHA"

echo "==> Building images"
IMAGE_TAG="$NEW_SHA" $COMPOSE build

echo "==> Running database migrations (alembic upgrade head)"
IMAGE_TAG="$NEW_SHA" $COMPOSE run --rm neuroweave \
  alembic -c migrations/alembic.ini upgrade head

echo "==> Restarting services"
IMAGE_TAG="$NEW_SHA" $COMPOSE up -d

echo "==> Waiting for the API to become healthy"
ATTEMPTS=0
until $COMPOSE exec -T neuroweave python -c "
import httpx, sys
try:
    r = httpx.get('http://localhost:8000/runtime/health', timeout=3)
    sys.exit(0 if r.status_code == 200 else 1)
except Exception:
    sys.exit(1)
" 2>/dev/null; do
  ATTEMPTS=$((ATTEMPTS + 1))
  if [ "$ATTEMPTS" -ge 20 ]; then
    echo "ERROR: /runtime/health did not become healthy after 20 attempts." >&2
    echo "       Logs: docker compose -f docker-compose.prod.yml logs --tail=100 neuroweave" >&2
    echo "       To roll back: git checkout $PREVIOUS_SHA && ./scripts/deploy.sh $PREVIOUS_SHA" >&2
    echo "       (Only safe if this deploy's migration, if any, is itself reversible - check" >&2
    echo "       migrations/versions/ for a new revision before rolling back the schema.)" >&2
    exit 1
  fi
  sleep 3
done

echo "==> Deploy succeeded: $NEW_SHA is live"
$COMPOSE ps
