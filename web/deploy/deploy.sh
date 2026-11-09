#!/usr/bin/env bash
# The ONLY deploy path for blankthespire.com. Run on the droplet, as root (systemctl) — git/pip steps drop to
# the btsweb user that owns the checkout:
#
#     sudo /opt/btsweb/web/deploy/deploy.sh            # deploy origin/main
#     sudo /opt/btsweb/web/deploy/deploy.sh --no-test  # skip the web tests (emergency only)
#     sudo /opt/btsweb/web/deploy/deploy.sh --now      # restart without waiting for running forges
#     (flags combine in any order: --no-test --now)
#
# Steps: fast-forward pull; reinstall deps only when requirements/pyproject changed; run the web tests
# against a throwaway SQLite DB (never prod MySQL); drain: wait (up to BTSWEB_DEPLOY_DRAIN_MAX_S, default
# 5400 s) for forges still running in the live DB to finish; restart the service; curl /healthz until 200.
# Any failure aborts BEFORE the restart, so a broken commit never takes the live site down.
set -euo pipefail

REPO="${BTSWEB_REPO:-/opt/btsweb}"
VENV="${BTSWEB_VENV:-$REPO/.venv}"
SERVICE="${BTSWEB_SERVICE:-btsweb}"
APP_USER="${BTSWEB_USER:-btsweb}"
HEALTH_URL="${BTSWEB_HEALTH_URL:-http://127.0.0.1:8000/healthz}"
DRAIN_MAX_S="${BTSWEB_DEPLOY_DRAIN_MAX_S:-5400}"
DRAIN_POLL_S=30
RUN_TESTS=1
DRAIN=1
for arg in "$@"; do
  case "$arg" in
    --no-test) RUN_TESTS=0 ;;
    --now) DRAIN=0 ;;
    *) echo "usage: $0 [--no-test] [--now]" >&2; exit 2 ;;
  esac
done

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
# What is being A/B tested right now (web/experiments.py; plan AB_TESTING_PLAN.md 3.10) — every deploy restates it.
echo "== $(as_app "$VENV/bin/python" -c 'import sys; sys.path.insert(0, "web"); import experiments; print(experiments.summary_line())' 2>/dev/null || echo 'live experiments: (could not read registry)')"

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

# 4. Drain (WALK_AWAY_FORGE_PLAN.md 5.1): a restart kills every running forge (boot reconciliation marks it
# failed and refunds it), and a slow BYOK forge can run an hour. Wait for the live DB's running forge_jobs to
# reach 0. running_forges.py is read-only, never imports app.py, and reads web/.env itself (it runs as the app
# user, who owns that file); it prints the count on line 1 and one "age_min<TAB>mode<TAB>concept" line per job,
# and prints 0 (warning on stderr) if the DB can't be read, so the drain can never block a deploy.
running_forges() {
  as_app "$VENV/bin/python" web/deploy/running_forges.py --env-file "$REPO/web/.env" || echo 0
}
if [[ "$DRAIN" == "1" ]]; then
  report="$(running_forges)"
  count="$(head -n1 <<<"$report")"
  [[ "$count" =~ ^[0-9]+$ ]] || count=0
  if (( count > 0 )); then
    echo "== drain: $count forge(s) running — waiting up to ${DRAIN_MAX_S}s (deploy.sh --now skips this)"
    tail -n +2 <<<"$report" | while IFS=$'	' read -r age mode concept; do
      echo "   - ${age} min  ${mode}  ${concept}"
    done
    drain_start=$SECONDS
    while (( count > 0 )); do
      waited=$(( SECONDS - drain_start ))
      if (( waited >= DRAIN_MAX_S )); then
        echo "!! DRAIN TIMEOUT: $count forge(s) still running after ${waited}s — restarting anyway;"              "boot reconciliation marks them failed and refunds them" >&2
        break
      fi
      sleep "$DRAIN_POLL_S"
      report="$(running_forges)"
      count="$(head -n1 <<<"$report")"
      [[ "$count" =~ ^[0-9]+$ ]] || count=0
      echo "== drain: $count running after $(( SECONDS - drain_start ))s"
    done
    if (( count == 0 )); then echo "== drain: no forges running"; fi
  else
    echo "== drain: no forges running"
  fi
else
  echo "== drain skipped (--now)"
fi

# 5. Restart + health check.
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
