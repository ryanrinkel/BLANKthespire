"""Ollama Cloud subscription headroom — the cost gate in front of the Ollama tier.

The hosted chain runs Ollama Cloud FIRST because Ryan's subscription already pays for a monthly allowance of
usage (Pro: $60/month for $20; Max: $300/month for $100), so a call there is free at the margin until the
allowance is spent — after which Ollama bills per token at LIST rates ($1.40/$4.40 per M for glm-5.3), which
is dearer than OpenRouter ($0.91/$2.86). "Most cost-effective route" therefore means: Ollama while the plan
has room, OpenRouter the moment it does not, OpenRouter for anything that fails either way.

Ollama exposes the headroom on an authenticated endpoint (probe 2026-09-24, same API key as /v1):

    GET https://ollama.com/api/usage
    {"activity": {"cost": "0.00000", "period": {"type": "last_4_weeks", ...}, "models": [...]},
     "limits": {"session": {"usage": 0.051, "models": [{"name": "glm-5.3", "request_count": 46}, ...]},
                "weekly":  {"usage": 0.009, "models": [...]}}}

  limits.session.usage   fraction (0..1) of the plan's included usage consumed in the current session window
  limits.weekly.usage    fraction (0..1) consumed in the current week (one forge ~ 0.01 on 2026-09-24)
  activity.cost          USD billed PER TOKEN (purchased credits / overage) in the last 4 weeks — "0.00000"
                         while the subscription absorbs everything

The gate (`saturated`) says to skip Ollama when
  1. the session window is >= BTSGEN_OLLAMA_SESSION_CEILING (default 0.95) full, or
  2. the week is >= BTSGEN_OLLAMA_WEEKLY_CEILING (default 0.97) full, or
  3. `activity.cost` GREW between two polls — per-token billing has started, whatever the fractions say —
     in which case Ollama is held off for BTSGEN_OLLAMA_METERED_HOLD_S (default 1h) before being re-tried.
The snapshot is cached process-wide per API key for BTSGEN_OLLAMA_QUOTA_POLL_S (default 60s), so a forge's
~40 calls cost one GET a minute. A poll that fails leaves the last snapshot in force (or, with none, no gate
at all): the endpoint being down must never route a forge away from the free tier by itself — the breaker
in ollama_mix still catches a real 402/429. BTSGEN_OLLAMA_QUOTA=0 disables the gate entirely.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

_log = logging.getLogger("btsgen.ollama_quota")

USAGE_URL = "https://ollama.com/api/usage"
OLLAMA_HOST = "ollama.com"
_LOCK = threading.Lock()


@dataclass(frozen=True)
class Snapshot:
    session: float  # fraction of the session window used (0..1)
    weekly: float   # fraction of the weekly allowance used (0..1)
    cost: float     # USD billed per token over the trailing 4 weeks
    fetched_at: float  # time.monotonic()

    def line(self) -> str:
        return f"session {self.session:.0%}, weekly {self.weekly:.0%}, metered ${self.cost:.2f} (4 wk)"


@dataclass
class _State:
    snap: Snapshot | None = None
    metered_until: float = 0.0
    last_reason: str | None = None
    fetch_failed_logged: bool = False


_state: dict[str, _State] = {}  # api_key -> state


def enabled() -> bool:
    return os.environ.get("BTSGEN_OLLAMA_QUOTA", "1") != "0"


def _knob(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def fetch_usage(api_key: str, timeout: float = 10.0) -> dict:
    """One GET of the usage endpoint; raises on transport/HTTP/JSON trouble (the caller decides what a
    failed poll means)."""
    req = urllib.request.Request(USAGE_URL, headers={"Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse(raw: dict, now: float | None = None) -> Snapshot:
    """The three numbers we route on, from the endpoint's shape; a missing field reads as 0 (no headroom
    claim is ever invented from a partial answer — 0 means "plenty of room")."""
    limits = raw.get("limits") if isinstance(raw.get("limits"), dict) else {}
    activity = raw.get("activity") if isinstance(raw.get("activity"), dict) else {}

    def frac(key: str) -> float:
        block = limits.get(key)
        try:
            return max(0.0, float((block or {}).get("usage") or 0.0))
        except (TypeError, ValueError):
            return 0.0

    try:
        cost = max(0.0, float(activity.get("cost") or 0.0))
    except (TypeError, ValueError):
        cost = 0.0
    return Snapshot(session=frac("session"), weekly=frac("weekly"), cost=cost,
                    fetched_at=time.monotonic() if now is None else now)


def snapshot(api_key: str, *, fetch=None, now: float | None = None) -> Snapshot | None:
    """The cached headroom for `api_key`, re-polled once the poll interval has passed. A failed poll keeps
    the previous snapshot (logged once per key) and yields None when there has never been one."""
    if not api_key:
        return None
    fetch = fetch or fetch_usage
    t = time.monotonic() if now is None else now
    poll_s = _knob("BTSGEN_OLLAMA_QUOTA_POLL_S", 60)
    with _LOCK:
        st = _state.setdefault(api_key, _State())
        if st.snap is not None and t - st.snap.fetched_at < poll_s:
            return st.snap
    try:
        fresh = parse(fetch(api_key), now=t)
    except (OSError, ValueError, TypeError, urllib.error.URLError) as e:
        with _LOCK:
            st = _state.setdefault(api_key, _State())
            if not st.fetch_failed_logged:
                _log.warning("ollama usage poll failed (%s) — routing on the last snapshot, if any", str(e)[:120])
                st.fetch_failed_logged = True
            if st.snap is not None:  # stretch the stale snapshot one more interval rather than hammering
                st.snap = Snapshot(st.snap.session, st.snap.weekly, st.snap.cost, t)
            return st.snap
    with _LOCK:
        st = _state.setdefault(api_key, _State())
        st.fetch_failed_logged = False
        prev = st.snap
        # Per-token billing detected: the trailing-4-week metered cost only ever grows when Ollama charged
        # for something — the subscription's included usage never shows up here.
        if prev is not None and fresh.cost > prev.cost + 1e-6:
            hold = _knob("BTSGEN_OLLAMA_METERED_HOLD_S", 3600)
            st.metered_until = t + hold
            _log.warning("ollama billed $%.4f per token since the last poll — holding the Ollama tier for %ds",
                         fresh.cost - prev.cost, int(hold))
        st.snap = fresh
        return fresh


def saturated(api_key: str, *, fetch=None, now: float | None = None) -> str | None:
    """Why the Ollama tier should be skipped right now, or None when it has headroom (or the gate is off /
    blind). State changes are logged once, so the forge journal shows each hand-over and hand-back."""
    if not enabled() or not api_key:
        return None
    snap = snapshot(api_key, fetch=fetch, now=now)
    t = time.monotonic() if now is None else now
    reason: str | None = None
    with _LOCK:
        st = _state.setdefault(api_key, _State())
        if st.metered_until > t:
            reason = "per-token billing detected"
    if reason is None and snap is not None:
        if snap.session >= _knob("BTSGEN_OLLAMA_SESSION_CEILING", 0.95):
            reason = f"session window {snap.session:.0%} used"
        elif snap.weekly >= _knob("BTSGEN_OLLAMA_WEEKLY_CEILING", 0.97):
            reason = f"weekly allowance {snap.weekly:.0%} used"
    with _LOCK:
        st = _state.setdefault(api_key, _State())
        if reason != st.last_reason:
            if reason:
                _log.warning("ollama subscription saturated (%s) — routing hosted calls to the backup tiers", reason)
            elif st.last_reason:
                _log.info("ollama subscription has headroom again — resuming the Ollama tier")
            st.last_reason = reason
    return reason


def status_line(api_key: str) -> str:
    """One line for the CLI banner: the cached snapshot plus the verdict (never raises)."""
    try:
        reason = saturated(api_key)
        snap = _state.get(api_key).snap if api_key in _state else None
    except Exception as e:  # noqa: BLE001 — a banner must never block a forge
        return f"unavailable ({str(e)[:60]})"
    if snap is None:
        return "unknown (usage endpoint unreachable)" if enabled() else "gate disabled (BTSGEN_OLLAMA_QUOTA=0)"
    verdict = f"SATURATED: {reason} -> backup tiers" if reason else "in use"
    return f"{snap.line()} - {verdict}"


def _reset() -> None:
    """Test hook: forget every snapshot and hold."""
    with _LOCK:
        _state.clear()
