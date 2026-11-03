"""Operator email alerts: "the hosted forge's account is out of credit", and (bottom of the file) the page
experiments' Monday digest + planned-end / winner mail.

btsgen.alerts fires an event when a HOSTED tier (our OpenRouter / Ollama keys) or the server-keyed image
endpoint answers 402 (or a 429 that talks about credit). This module turns that into ONE plain-text email
through Resend — the same key + From address the magic links use — to BTSWEB_ALERT_EMAILS, or to
BTSWEB_ADMIN_EMAILS when the alert list is unset.

Throttled per endpoint (BTSWEB_ALERT_COOLDOWN_S, default 6h): a credit wall makes EVERY call fail, so a
single forge would otherwise mail once per stage and a busy hour would mail dozens of times. The send runs
on a daemon thread so a slow Resend never lengthens a forge, and every failure is logged, never raised.
Process-local state — keep gunicorn at one worker (the limiters already assume that).

Why this exists: 2026-09-24 — OpenRouter sat at $1.03 of $20, every hosted forge failed, and nothing said so.
"""
from __future__ import annotations

import datetime
import logging
import os
import threading
import time

import requests

import ab_report
from auth import ADMIN_EMAILS, RESEND_ENDPOINT, mail_configured

_log = logging.getLogger("btsweb.alerts")

DEFAULT_COOLDOWN_S = 6 * 3600
_LOCK = threading.Lock()
_last_sent: dict[str, float] = {}  # throttle key -> time.monotonic() of the last send

_TOPUP_HINTS = {
    "openrouter.ai": "Top up at https://openrouter.ai/settings/credits",
    "ollama.com": "Check the Ollama Cloud plan / usage at https://ollama.com/settings",
}


def recipients() -> list[str]:
    """BTSWEB_ALERT_EMAILS (comma-separated) when set, else the operator list — read per call so a test or
    an env edit takes effect without a restart."""
    raw = os.environ.get("BTSWEB_ALERT_EMAILS", "")
    picked = [e.strip().lower() for e in raw.split(",") if e.strip()]
    return picked or sorted(ADMIN_EMAILS)


def cooldown_s() -> int:
    try:
        return max(0, int(os.environ.get("BTSWEB_ALERT_COOLDOWN_S", DEFAULT_COOLDOWN_S)))
    except ValueError:
        return DEFAULT_COOLDOWN_S


def reset() -> None:
    """Test hook: forget every throttle window."""
    with _LOCK:
        _last_sent.clear()


def _dispatch(fn) -> None:
    """Run the send off the forge thread. Module-level so tests can make it synchronous."""
    threading.Thread(target=fn, name="btsweb-alert", daemon=True).start()


def _send_mail(to: list[str], subject: str, body: str) -> None:
    """One plain-text email through Resend (mirrors auth._send_magic_link). Module-level for test stubs."""
    resp = requests.post(
        RESEND_ENDPOINT,
        headers={"Authorization": f"Bearer {os.environ.get('RESEND_API_KEY', '').strip()}"},
        json={"from": os.environ.get("BTSWEB_MAIL_FROM", "").strip(), "to": to,
              "subject": subject, "text": body},
        timeout=10)
    resp.raise_for_status()


def _host(endpoint: str) -> str:
    return (endpoint or "").replace("https://", "").replace("http://", "").split("/")[0] or "unknown host"


def compose(event: dict) -> tuple[str, str]:
    """(subject, body) for a credit_exhausted event — plain text, everything an operator needs to act."""
    host = _host(event.get("endpoint", ""))
    source = event.get("source") or "chat"
    code = event.get("code")
    when = datetime.datetime.fromtimestamp(event.get("ts") or time.time(), datetime.timezone.utc)
    subject = f"[BLANK the spire] hosted forge credits exhausted on {host}"
    what = ("text generation (the hosted forge's model tiers)" if source == "chat"
            else "image generation (splash / sprite / card art)")
    consequence = (
        "Every hosted forge now fails over to the next tier on a different endpoint, or fails outright "
        "once every tier is refusing. Token forges that fail are refunded automatically, but nobody can "
        "forge on our models until this is fixed."
        if source == "chat" else
        "Art is non-fatal: forges still complete, but classes ship WITHOUT generated art until this is fixed.")
    hint = next((h for k, h in _TOPUP_HINTS.items() if k in host), "Top up the provider account.")
    lines = [
        f"The server's account on {host} refused a request with HTTP {code} during {what}.",
        "",
        f"When:     {when.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"Endpoint: {event.get('endpoint') or host}",
        f"Model:    {event.get('model') or '?'}" + (f"  (tier: {event['tier']})" if event.get("tier") else ""),
        "",
        "Provider said:",
        "  " + ((event.get("detail") or "").strip().replace("\n", " ")[:500] or "(no body)"),
        "",
        consequence,
        "",
        f"What to do: {hint}. The forge recovers on its own once the balance is positive (the endpoint's "
        f"breaker re-tries it within an hour; a restart clears it immediately).",
        "",
        f"You will not get another email about {host} for {cooldown_s() // 3600}h "
        f"(BTSWEB_ALERT_COOLDOWN_S), even if every forge in between hits the same wall.",
    ]
    return subject, "\n".join(lines) + "\n"


def _on_credit_exhausted(event: dict) -> bool:
    """The btsgen.alerts listener. Returns True when an email was queued (False = throttled / unconfigured),
    which the tests read; the forge never looks at it."""
    to = recipients()
    if not to:
        _log.warning("credit exhausted on %s but no alert recipients (set BTSWEB_ALERT_EMAILS or "
                     "BTSWEB_ADMIN_EMAILS)", event.get("endpoint"))
        return False
    if not mail_configured():
        _log.warning("credit exhausted on %s but mail is not configured (RESEND_API_KEY + BTSWEB_MAIL_FROM)",
                     event.get("endpoint"))
        return False
    key = f"{event.get('source')}:{_host(event.get('endpoint', ''))}"
    now = time.monotonic()
    with _LOCK:
        if now - _last_sent.get(key, float("-inf")) < cooldown_s():
            return False
        _last_sent[key] = now
    subject, body = compose(event)

    def _go():
        try:
            _send_mail(to, subject, body)
            _log.warning("credit alert emailed to %s: %s", ", ".join(to), subject)
        except Exception:  # noqa: BLE001 — never let a failed alert take anything else down
            _log.exception("credit alert email failed")
            with _LOCK:  # let the next event retry instead of waiting out the cooldown
                _last_sent.pop(key, None)

    _dispatch(_go)
    return True


def install() -> None:
    """Register the listener with btsgen (idempotent). Called once at app import."""
    from btsgen import alerts as _bts_alerts
    _bts_alerts.register(_on_credit_exhausted)


# --- page experiments: Monday digest + planned-end / winner mail (docs/plans/AB_TESTING_PLAN.md 3.10) ----
# Pure composers over the same per-experiment list the admin Experiments card reads
# (ab_report.build_experiments_payload); tools/experiments_mail.py (btsweb-experiments.timer, daily) owns the
# I/O: reading traffic.json, the "already sent" state file, and calling send_experiments_mail.

EXP_SUBJECT_PREFIX = "[BLANK the spire]"


def public_base_url() -> str:
    """The site the preview links point at — the same env var app.py's PUBLIC_BASE_URL reads."""
    return os.environ.get("BTSWEB_PUBLIC_URL", "https://blankthespire.com").rstrip("/")


def _rate(n, of) -> str:
    return f"{n} ({100 * n / of:.1f}%)" if of else f"{n}"


def _experiment_block(e: dict) -> list[str]:
    """One experiment in words, then numbers: the plain-text twin of the admin card's block."""
    arms = e.get("arms") or []
    d = e.get("decision") or {}
    ps = d.get("p_beats_control") or {}
    label = e.get("primary_label") or e.get("primary")
    per_arm = e.get("per_arm") or {}
    base = public_base_url()
    lines = [
        f"{e.get('name')} on {e.get('page')} — day {e.get('day')} of {e.get('of')} "
        f"(started {e.get('started')}, decision due {e.get('planned_end')}, {d.get('days_left', '?')} days left)",
        f"Status: {d.get('status', '?')}",
        f"Hypothesis: {e.get('hypothesis')}",
        f"Primary metric: {label}",
        "",
    ]
    for i, a in enumerate(arms):
        tag = f"{a} (control)" if i == 0 else a
        lines.append(f"  {tag}: {(e.get('arms_text') or {}).get(a, '')}")
        row = per_arm.get(a) or {}
        n = int(row.get("exposures") or 0)
        bits = [f"exposures {n}", f"{label} {_rate(int(row.get('primary') or 0), n)}"]
        if i > 0:
            p = ps.get(a)
            bits.append(f"P({a} beats {arms[0]}) {'—' if p is None else f'{p:.2f}'}")
        dv = row.get("devices") or {}
        if dv:
            bits.append(f"desktop {dv.get('desktop', 0)} / phone {dv.get('phone', 0)} / "
                        f"webview {dv.get('phone_webview', 0)}")
        lines.append("     " + " · ".join(bits))
    lines += ["", e.get("readout") or ab_report.readout(e), "", "Preview (opens that arm for you only):"]
    for a, path in (e.get("preview") or {}).items():
        lines.append(f"  {a}: {base}{path}")
    return lines


def _mail_footer() -> list[str]:
    return ["", ab_report.rule_sentence(), "", f"The card: {public_base_url()}/app#account (Experiments)",
            "Record: docs/experiments/LOG.md"]


def experiments_digest(payload: list[dict], today: str) -> tuple[str, str] | None:
    """The Monday "what am I testing right now" mail: one block per LIVE experiment; None when none is."""
    live = [e for e in payload or [] if e.get("live")]
    if not live:
        return None
    heads = "; ".join(f"{e.get('name')} {ab_report.p_phrase(e)}".strip() for e in live)
    subject = f"{EXP_SUBJECT_PREFIX} experiments: {len(live)} live — {heads}"
    lines = [f"Live page experiments on {today} (UTC):", ""]
    for i, e in enumerate(live):
        if i:
            lines += ["", "-" * 60, ""]
        lines += _experiment_block(e)
    lines += _mail_footer()
    return subject, "\n".join(lines) + "\n"


def experiments_due(payload: list[dict], today: str, already_sent: dict | None = None) -> list[tuple[str, str, str]]:
    """(key, subject, body) per mail that is due and not in ``already_sent`` (key -> date sent):
    ``end:<name>`` once `today >= planned_end` on a not-ended experiment, ``winner:<name>`` once the
    decision rule names a winner before anyone ended it."""
    sent = already_sent or {}
    out: list[tuple[str, str, str]] = []
    for e in payload or []:
        if e.get("ended"):
            continue
        name = e.get("name")
        d = e.get("decision") or {}
        pp = ab_report.p_phrase(e, " = ")
        if today >= (e.get("planned_end") or "9999") and f"end:{name}" not in sent:
            head = f"{name} reached its planned end — {pp}."
            body = [head + " Decide: set winner or keep control.", "",
                    "To end it: set ended + winner in web/experiments.py (winner \"a\" keeps the control), "
                    "deploy, then remove the losing arm's markers and i18n keys and fill in the LOG row.", ""]
            out.append((f"end:{name}", f"{EXP_SUBJECT_PREFIX} {head}",
                        "\n".join(body + _experiment_block(e) + _mail_footer()) + "\n"))
        w = d.get("winner_by_rule")
        if w and f"winner:{name}" not in sent:
            head = f"{name} has a winner by the rule: {w}"
            body = [f"{head} ({pp}, {d.get('days_running')} days, every arm ≥ the minimum exposures).",
                    "Nothing changes for visitors until you end it: set ended + winner in web/experiments.py and "
                    "deploy.", ""]
            out.append((f"winner:{name}", f"{EXP_SUBJECT_PREFIX} {head}",
                        "\n".join(body + _experiment_block(e) + _mail_footer()) + "\n"))
    return out


def send_experiments_mail(subject: str, body: str) -> bool:
    """Send one experiments mail synchronously (the caller is a oneshot CLI). False = not sent."""
    to = recipients()
    if not to:
        _log.warning("experiments mail %r not sent: no recipients (BTSWEB_ALERT_EMAILS / BTSWEB_ADMIN_EMAILS)",
                     subject)
        return False
    if not mail_configured():
        _log.warning("experiments mail %r not sent: mail is not configured (RESEND_API_KEY + BTSWEB_MAIL_FROM)",
                     subject)
        return False
    try:
        _send_mail(to, subject, body)
    except Exception:  # noqa: BLE001 — logged; the CLI retries on its next run
        _log.exception("experiments mail %r failed", subject)
        return False
    _log.warning("experiments mail sent to %s: %s", ", ".join(to), subject)
    return True
