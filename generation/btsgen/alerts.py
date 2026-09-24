"""Operator alerts: a tiny listener registry the hosted generation paths fire when a provider says the
SERVER'S account is out of credit (the 2026-09-24 outage: OpenRouter at $1.03 of $20, every hosted forge
failing over or dying while nobody was told).

btsgen has no mailer and must not grow one — the website registers a listener (web/alerts.py sends a
throttled email through Resend); the CLI registers nothing and just sees the log line. Call sites:

- ollama_mix._FailoverGenerator: a 402 (or a 429 whose body talks about credit/quota) from a HOSTED tier —
  the operator's OpenRouter / Ollama keys. A BYOK user's own key never goes through the failover chain, so
  their credit wall is never mistaken for ours.
- art.backends.openrouter: the same status from the image endpoint on the SERVER key only (an instance
  built with a BYOK `api_key=` stays silent).

Listeners must never break generation: every callback runs inside a try/except and failures are logged.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Callable

_log = logging.getLogger("btsgen.alerts")

_LOCK = threading.Lock()
_listeners: list[Callable[[dict], None]] = []

# A 402 is a credit wall by definition. A 429 is usually a rate limit — only treat it as "out of credit" when
# the provider's body says so (Ollama Cloud phrases its session quota that way).
_CREDIT_WORDS = re.compile(r"credit|quota|billing|insufficient|balance|payment", re.IGNORECASE)


def looks_like_credit_error(code: int, detail: str = "") -> bool:
    """True when an HTTP status + provider body mean the ACCOUNT is out of money, not just busy."""
    if code == 402:
        return True
    return code == 429 and bool(_CREDIT_WORDS.search(detail or ""))


def register(fn: Callable[[dict], None]) -> None:
    """Add a listener (idempotent). It receives one dict per event — see `credit_exhausted`."""
    with _LOCK:
        if fn not in _listeners:
            _listeners.append(fn)


def unregister(fn: Callable[[dict], None]) -> None:
    with _LOCK:
        if fn in _listeners:
            _listeners.remove(fn)


def credit_exhausted(*, source: str, endpoint: str, code: int, detail: str = "",
                     model: str | None = None, tier: str | None = None) -> dict:
    """Fire one 'the server account is out of credit' event to every listener. Returns the event dict.

    `source` is 'chat' (the text tiers) or 'art' (the image endpoint); `endpoint` is the base URL that
    refused; `detail` is the provider's error body (truncated by the listener). Never raises."""
    event = {
        "kind": "credit_exhausted",
        "source": source,
        "endpoint": (endpoint or "").rstrip("/"),
        "code": int(code),
        "detail": (detail or "")[:600],
        "model": model,
        "tier": tier,
        "ts": time.time(),
    }
    _log.warning("credit exhausted on %s (%s, HTTP %d%s)", event["endpoint"], source, event["code"],
                 f", {model}" if model else "")
    with _LOCK:
        listeners = list(_listeners)
    for fn in listeners:
        try:
            fn(event)
        except Exception:  # noqa: BLE001 — an alert sink must never break a forge
            _log.exception("credit-exhausted listener %r failed", fn)
    return event
