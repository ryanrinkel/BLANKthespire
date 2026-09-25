"""Offline tests for the Ollama subscription cost gate (btsgen/ollama_quota.py) and its hook in the hosted
failover chain — no network, no keys.

Run:  uv run python -m tests.test_ollama_quota     (from generation/)
Covers: parsing the usage endpoint, the session/weekly ceilings, per-token billing detection (cost delta ->
hold), poll caching, failed polls keeping the last snapshot / never gating blind, the env kill-switch, and
the chain actually skipping the Ollama tier for OpenRouter when saturated (and still trying it when not).
"""
from __future__ import annotations

import contextlib
import os
import sys

from btsgen import ollama_quota as Q
from btsgen.ollama_mix import _FailoverGenerator, _Tier, _reset_breaker

_PASS = 0
_FAIL = 0
KEY = "sk-ollama-test"
RAW_OK = {"activity": {"cost": "0.00000", "period": {"type": "last_4_weeks"}, "models": []},
          "limits": {"session": {"usage": 0.051, "models": []}, "weekly": {"usage": 0.009, "models": []}}}


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


@contextlib.contextmanager
def _env(**kv):
    prior = {k: os.environ.get(k) for k in kv}
    try:
        for k, v in kv.items():
            os.environ[k] = v
        yield
    finally:
        for k, v in prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _raw(session=0.05, weekly=0.01, cost="0.00000") -> dict:
    return {"activity": {"cost": cost}, "limits": {"session": {"usage": session}, "weekly": {"usage": weekly}}}


class _Fetch:
    """Scripted usage endpoint: returns its answers in order (an Exception instance is raised), counts calls."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = 0

    def __call__(self, api_key):
        self.calls += 1
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(a, Exception):
            raise a
        return a


class _Gen:
    """Duck-typed tier generator with an api_key, like OpenAICompatGenerator."""

    def __init__(self, tag: str, base_url: str, api_key: str = KEY):
        self.model, self.base_url, self.api_key = tag, base_url, api_key
        self.calls = 0
        self.last_meta: dict = {}

    def first_attempt(self, brief):
        self.calls += 1
        return f"{self.model}:{brief}", []

    def repair(self, messages, prev_text, errors):
        self.calls += 1
        return f"{self.model}:repaired", []


def test_parse_shape() -> None:
    print("parse the usage endpoint...")
    s = Q.parse(RAW_OK, now=100.0)
    check((s.session, s.weekly, s.cost, s.fetched_at) == (0.051, 0.009, 0.0, 100.0), f"got {s}")
    check(Q.parse({}, now=1.0).session == 0.0 and Q.parse({"limits": None, "activity": "x"}, now=1.0).cost == 0.0,
          "a partial or malformed answer reads as no usage (never as saturation)")
    check(Q.parse(_raw(cost="1.2345"), now=1.0).cost == 1.2345, "cost is a decimal string")
    check("session 5%" in s.line() and "weekly 1%" in s.line(), f"banner line: {s.line()}")


def test_ceilings() -> None:
    print("session / weekly ceilings...")
    Q._reset()
    check(Q.saturated(KEY, fetch=_Fetch(_raw(0.5, 0.5)), now=0.0) is None, "half-used plan has headroom")
    Q._reset()
    r = Q.saturated(KEY, fetch=_Fetch(_raw(0.96, 0.1)), now=0.0)
    check(r is not None and "session" in r and "96%" in r, f"session at 96% is saturated (got {r})")
    Q._reset()
    r = Q.saturated(KEY, fetch=_Fetch(_raw(0.1, 0.98)), now=0.0)
    check(r is not None and "weekly" in r and "98%" in r, f"week at 98% is saturated (got {r})")
    Q._reset()
    with _env(BTSGEN_OLLAMA_WEEKLY_CEILING="0.5"):
        check(Q.saturated(KEY, fetch=_Fetch(_raw(0.1, 0.6)), now=0.0) is not None, "the ceilings are env knobs")
    Q._reset()
    check(Q.saturated("", fetch=_Fetch(_raw(0.99, 0.99)), now=0.0) is None, "no key -> no gate")


def test_metered_billing_detection() -> None:
    print("per-token billing (cost delta) holds the tier...")
    Q._reset()
    f = _Fetch(_raw(0.2, 0.2, "0.0"), _raw(0.2, 0.2, "0.0"), _raw(0.2, 0.2, "0.37"), _raw(0.2, 0.2, "0.37"))
    check(Q.saturated(KEY, fetch=f, now=0.0) is None, "first poll: headroom, cost 0")
    check(Q.saturated(KEY, fetch=f, now=61.0) is None, "second poll: cost still 0 -> no hold")
    r = Q.saturated(KEY, fetch=f, now=122.0)
    check(r is not None and "per-token" in r, f"cost grew 0 -> 0.37: Ollama is billing, hold (got {r})")
    check(Q.saturated(KEY, fetch=f, now=1000.0) is not None, "still held inside the hold window")
    check(Q.saturated(KEY, fetch=f, now=122.0 + 3600.0 + 1) is None,
          "after the hold, an unchanged cost releases the tier")
    Q._reset()
    with _env(BTSGEN_OLLAMA_METERED_HOLD_S="10"):
        f = _Fetch(_raw(cost="1.0"), _raw(cost="1.5"), _raw(cost="1.5"))
        Q.saturated(KEY, fetch=f, now=0.0)
        check(Q.saturated(KEY, fetch=f, now=61.0) is not None, "hold set")
        check(Q.saturated(KEY, fetch=f, now=61.0 + 61.0) is None, "hold length is an env knob")
    Q._reset()
    f = _Fetch(_raw(cost="2.0"), _raw(cost="1.5"))
    Q.saturated(KEY, fetch=f, now=0.0)
    check(Q.saturated(KEY, fetch=f, now=61.0) is None, "a FALLING trailing-4-week cost is not billing")


def test_poll_cache_and_failures() -> None:
    print("poll caching + failed polls...")
    Q._reset()
    f = _Fetch(_raw(0.1, 0.1))
    for t in (0.0, 10.0, 59.0):
        Q.saturated(KEY, fetch=f, now=t)
    check(f.calls == 1, f"within the poll interval the endpoint is hit once (got {f.calls})")
    Q.saturated(KEY, fetch=f, now=60.5)
    check(f.calls == 2, "the interval elapsed -> re-polled")
    with _env(BTSGEN_OLLAMA_QUOTA_POLL_S="5"):
        Q.saturated(KEY, fetch=f, now=66.0)
        check(f.calls == 3, "poll interval is an env knob")

    Q._reset()
    f = _Fetch(OSError("boom"))
    check(Q.saturated(KEY, fetch=f, now=0.0) is None, "no snapshot ever + failed poll -> never gates")
    check(Q.status_line(KEY).startswith("unknown"), f"banner says unknown (got {Q.status_line(KEY)!r})")
    Q._reset()
    f = _Fetch(_raw(0.99, 0.1), ValueError("bad json"), ValueError("bad json"))
    check(Q.saturated(KEY, fetch=f, now=0.0) is not None, "saturated snapshot")
    check(Q.saturated(KEY, fetch=f, now=61.0) is not None, "a failed poll keeps the last (saturated) verdict")
    check(f.calls == 2, "the failed poll counted")
    Q.saturated(KEY, fetch=f, now=90.0)
    check(f.calls == 2, "a failed poll stretches the stale snapshot one interval instead of hammering")


def test_kill_switch() -> None:
    print("BTSGEN_OLLAMA_QUOTA=0 disables the gate...")
    Q._reset()
    f = _Fetch(_raw(0.99, 0.99))
    with _env(BTSGEN_OLLAMA_QUOTA="0"):
        check(Q.saturated(KEY, fetch=f, now=0.0) is None and f.calls == 0, "disabled: no gate, no poll")
        check("disabled" in Q.status_line(KEY), "banner names the switch")


def test_chain_routes_around_a_saturated_subscription() -> None:
    print("the failover chain skips Ollama for OpenRouter when saturated...")
    _reset_breaker()
    Q._reset()
    ollama = _Gen("glm-5.3", "https://ollama.com/v1")
    backup = _Gen("z-ai/glm-5.3", "https://openrouter.ai/api/v1", api_key="sk-or")
    last = _Gen("z-ai/glm-5.2", "https://openrouter.ai/api/v1", api_key="sk-or")
    gen = _FailoverGenerator([_Tier(ollama, name="primary"), _Tier(backup, name="openrouter-glm53"),
                              _Tier(last, name="openrouter-glm52")])
    real_fetch = Q.fetch_usage
    try:
        Q.fetch_usage = _Fetch(_raw(0.2, 0.2))
        out, _ = gen.first_attempt("a")
        check(out == "glm-5.3:a" and gen.model == "glm-5.3", "with headroom the Ollama tier answers")

        Q._reset()
        Q.fetch_usage = _Fetch(_raw(0.2, 0.99))
        out, _ = gen.first_attempt("b")
        check(out == "z-ai/glm-5.3:b" and ollama.calls == 1, "saturated week: Ollama untouched, OpenRouter answers")
        check(gen.model == "z-ai/glm-5.3", ".model names the tier that answered")
        out, _ = gen.repair([], "p", ["e"])
        check(out == "z-ai/glm-5.3:repaired", "repair() is gated the same way")

        # Gated tiers do not count as attempted: with every tier gated/breakered the LAST tier still runs.
        Q._reset()
        Q.fetch_usage = _Fetch(_raw(0.99, 0.2))
        from btsgen import ollama_mix
        ollama_mix._trip_breaker("https://openrouter.ai/api/v1", 60, "test")
        out, _ = gen.first_attempt("c")
        check(out == "z-ai/glm-5.2:c" and ollama.calls == 1, "everything gated -> the last tier is still tried")
        _reset_breaker()

        # A tier without an api_key (test doubles, odd configs) is never gated.
        Q._reset()
        Q.fetch_usage = _Fetch(_raw(0.99, 0.99))
        bare = _Gen("bare", "https://ollama.com/v1", api_key="")
        g2 = _FailoverGenerator([_Tier(bare, name="primary"), _Tier(backup, name="b")])
        out, _ = g2.first_attempt("d")
        check(out == "bare:d", "no key on the tier -> no gate")
    finally:
        Q.fetch_usage = real_fetch
        Q._reset()
        _reset_breaker()


def main() -> int:
    test_parse_shape()
    test_ceilings()
    test_metered_billing_detection()
    test_poll_cache_and_failures()
    test_kill_switch()
    test_chain_routes_around_a_saturated_subscription()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
