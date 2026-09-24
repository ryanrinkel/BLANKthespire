"""Operator email alerts — today, one kind: "the hosted forge's account is out of credit".

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
