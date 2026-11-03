"""Page-experiment mail for the operator (docs/plans/AB_TESTING_PLAN.md 3.10 items 3-4).

Run once a day by deploy/btsweb-experiments.timer (09:05 UTC), in the app VENV with the app's env (Resend
key, From address, BTSWEB_ADMIN_EMAILS / BTSWEB_ALERT_EMAILS):

* Mondays: the digest — one block per live experiment (hypothesis, exposures and the primary metric per arm,
  P(beats control), days left). Nothing at all when nothing is live.
* Any day: "<name> reached its planned end" once `planned_end` passes on an experiment nobody ended, and
  "<name> has a winner by the rule" once the decision rule names one — each at most once, ever.

The numbers come from traffic.json (tools/traffic_report.py, every 15 min) through the same
ab_report.build_experiments_payload the admin card uses; a missing traffic.json still lists the registry's
experiments, with no exposures. What was sent is kept in a small JSON state file next to traffic.json
({"sent": {key: date}, "last_digest": date}), so a re-run (Persistent=true after downtime, a manual start)
never mails twice. A failed send is not recorded and is retried on the next run.

    .venv/bin/python tools/experiments_mail.py --dry-run --digest       # print what would go out
    .venv/bin/python tools/experiments_mail.py --today 2026-12-15 --dry-run

Exit status is 0 except for unusable arguments: a mail problem must never make the unit "failed" forever.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parents[1]
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

DEFAULT_TRAFFIC_DIR = "/opt/btsweb/traffic"


def _load_env() -> None:
    """web/.env, the way app.py loads it — before alerts/auth read their env at import."""
    if os.environ.get("BTSWEB_NO_DOTENV"):
        return
    try:
        from dotenv import load_dotenv
    except ImportError:   # outside the venv: the systemd EnvironmentFile still provides the env
        return
    load_dotenv(WEB_DIR / ".env")


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_state(path: Path, state: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--traffic-dir", default=os.environ.get("BTSWEB_TRAFFIC_DIR", DEFAULT_TRAFFIC_DIR),
                    help="where traffic.json lives (default %(default)s)")
    ap.add_argument("--state", default=None, help="sent-mail state file (default <traffic-dir>/experiments_mail.json)")
    ap.add_argument("--today", default=None, help="YYYY-MM-DD override (UTC)")
    ap.add_argument("--digest", action="store_true", help="send the digest even if today is not Monday")
    ap.add_argument("--dry-run", action="store_true", help="print the mails instead of sending; state untouched")
    args = ap.parse_args(argv)

    if args.today is not None:
        try:
            today_d = datetime.date.fromisoformat(args.today)
        except ValueError:
            ap.error(f"--today {args.today!r} is not YYYY-MM-DD")
    else:
        today_d = datetime.datetime.now(datetime.timezone.utc).date()
    today = today_d.isoformat()

    _load_env()
    import ab_report  # noqa: E402 — after the env is loaded
    import alerts

    traffic_dir = Path(args.traffic_dir)
    state_path = Path(args.state) if args.state else traffic_dir / "experiments_mail.json"
    traffic = _read_json(traffic_dir / "traffic.json")
    payload = ab_report.build_experiments_payload(traffic if isinstance(traffic, dict) else None, today)

    state = _read_json(state_path)
    state = state if isinstance(state, dict) else {}
    sent = state.get("sent") if isinstance(state.get("sent"), dict) else {}
    state["sent"] = sent

    outgoing: list[tuple[str | None, str, str]] = []
    digest_due = args.digest or (today_d.weekday() == 0 and state.get("last_digest") != today)
    if digest_due:
        digest = alerts.experiments_digest(payload, today)
        if digest is not None:
            outgoing.append((None, *digest))
        else:
            print(f"{today}: digest due but no experiment is live — nothing to send")
    outgoing.extend(alerts.experiments_due(payload, today, sent))

    changed = False
    for key, subject, body in outgoing:
        if args.dry_run:
            print(f"=== {key or 'digest'}\nSubject: {subject}\n\n{body}")
            continue
        if alerts.send_experiments_mail(subject, body):
            print(f"{today}: sent {key or 'digest'}: {subject}")
            if key is None:
                state["last_digest"] = today
            else:
                sent[key] = today
            changed = True
        else:
            print(f"{today}: NOT sent ({key or 'digest'}) — see the log; retried next run", file=sys.stderr)
    if not outgoing:
        print(f"{today}: nothing to send ({len(payload)} experiment(s) on the card)")
    if changed:
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            _write_state(state_path, state)
        except OSError as e:
            print(f"could not write {state_path}: {e} — the same mail may go out again", file=sys.stderr)
    return 0


if __name__ == "__main__":
    import logging
    for _s in (sys.stdout, sys.stderr):   # a cp1252 console must not crash a dry run on "≥" / "—"
        try:
            _s.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(main())
