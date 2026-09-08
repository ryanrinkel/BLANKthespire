#!/usr/bin/env bash
# The ONLY deploy path for blankthespire.com. Run on the droplet, as root (systemctl) — git/pip steps drop to
# the btsweb user that owns the checkout:
#
#     sudo /opt/btsweb/web/deploy/deploy.sh            # deploy origin/main
#     sudo /opt/btsweb/web/deploy/deploy.sh --no-test  # skip the web tests (emergency only)
#
# Steps: fast-forward pull; reinstall deps only when requirements/pyproject changed; run the web tests
# against a throwaway SQLite DB (never prod MySQL); restart the service; curl /healthz until it answers 200.
# Any failure aborts BEFORE the restart, so a broken commit never takes the live site down.
set -euo pipefail

REPO="${BTSWEB_REPO:-/opt/btsweb}"
VENV="${BTSWEB_VENV:-$REPO/.venv}"
SERVICE="${BTSWEB_SERVICE:-btsweb}"
APP_USER="${BTSWEB_USER:-btsweb}"
HEALTH_URL="${BTSWEB_HEALTH_URL:-http://127.0.0.1:8000/healthz}"
RUN_TESTS=1
[[ "${1:-}" == "--no-test" ]] && RUN_TESTS=0

# Run a command as the app user (the checkout's owner) when we are root; as ourselves otherwise.
as_app() {
  if [[ "$(id -u)" == "0" ]]; then sudo -u "$APP_USER" env HOME="$REPO" "$@"; else "$@"; fi
}
restart_service() {
  if [[ "$(id -u)" == "0" ]]; then systemctl restart "$SERVICE"; else sudo systemctl restart "$SERVICE"; fi
}

cd "$REPO"
echo "== $(date -u +%FT%TZ) deploy start (HEAD $(as_app git rev-parse --short HEAD))"

# 1. Pull. --ff-only: the checkout must be clean — server-side edits belong in env/logs, never in git.
before="$(as_app git rev-parse HEAD)"
as_app git fetch --quiet origin
as_app git pull --ff-only --quiet origin main
after="$(as_app git rev-parse HEAD)"
echo "== pulled $before -> $after"

# 2. Dependencies, only if the dependency files changed (or the venv / pytest is missing).
if [[ ! -x "$VENV/bin/python" ]] || ! as_app git diff --quiet "$before" "$after" -- web/requirements.txt generation/pyproject.toml; then
  echo "== dependency files changed: reinstalling"
  as_app "$VENV/bin/pip" install --quiet -r web/requirements.txt
  as_app "$VENV/bin/pip" install --quiet -e ./generation   # editable: btsgen finds mod/contract/ via its tree
fi
if [[ "$RUN_TESTS" == "1" ]] && ! "$VENV/bin/python" -c "import pytest" 2>/dev/null; then
  as_app "$VENV/bin/pip" install --quiet pytest
fi

# 3. Web tests on a throwaway SQLite DB. conftest.py pins its own BTSWEB_* env, so prod secrets are ignored.
if [[ "$RUN_TESTS" == "1" ]]; then
  echo "== web tests"
  as_app env -u BTSWEB_DATABASE_URL -u STRIPE_SECRET_KEY -u GOOGLE_CLIENT_ID -u GOOGLE_CLIENT_SECRET \
      PYTHONPATH="$REPO/generation" "$VENV/bin/python" -m pytest web/tests -q -p no:cacheprovider
fi

# 4. Restart + health check.
echo "== restarting $SERVICE"
restart_service
for i in $(seq 1 30); do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    echo "== healthy: $(curl -fsS "$HEALTH_URL")"
    echo "== deploy done ($after)"
    exit 0
  fi
  sleep 1
done
echo "!! $HEALTH_URL did not answer 200 within 30s — check: journalctl -u $SERVICE -n 100" >&2
exit 1
