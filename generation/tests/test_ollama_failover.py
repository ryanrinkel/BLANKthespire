"""Offline tests for the ollama_mix metered failover — no API key, no network.

Run:  uv run python -m tests.test_ollama_failover     (from generation/)
Exits nonzero on any failure. Covers: fallback disarmed without the env key (plain generators come back),
armed builds _FailoverGenerator twins with the right endpoints/models, a quota 429 fails the call over and
trips the process-wide breaker (subsequent calls skip the primary), transport faults trip the short breaker,
non-quota HTTP errors stay loud, breaker expiry returns to the primary, and repair() routes like
first_attempt().
"""
from __future__ import annotations

import os
import sys

from btsgen import ollama_mix
from btsgen.generator import EndpointHTTPError
from btsgen.ollama_mix import _FailoverGenerator, _reset_breaker

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


class _Stub:
    """Duck-typed generator stand-in: raises `exc` (once per call) or returns its tag."""

    def __init__(self, tag: str, exc: Exception | None = None):
        self.model = tag
        self.base_url = f"https://{tag}.example"
        self.exc = exc
        self.calls = 0

    def first_attempt(self, brief):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return f"{self.model}:{brief}", []

    def repair(self, messages, prev_text, errors):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return f"{self.model}:repaired", []


def test_disarmed_without_key():
    os.environ.pop("OLLAMA_TEST_FB_KEY", None)
    fb = ollama_mix._normalize_fallback({"api_key": "${OLLAMA_TEST_FB_KEY}"})
    check(fb is None, "fallback should be disarmed when its api_key env var is unset")
    check(ollama_mix._normalize_fallback(None) is None, '"fallback": null should disable failover')


def test_armed_normalization():
    os.environ["OLLAMA_TEST_FB_KEY"] = "sk-test"
    fb = ollama_mix._normalize_fallback({"api_key": "${OLLAMA_TEST_FB_KEY}", "models": {"cards": "x/y"}})
    check(fb is not None and fb["api_key"] == "sk-test", "armed fallback should expand its key")
    check(fb["models"]["structure"] == "x/y" and fb["models"]["brainstorm"] == "x/y",
          "missing role models should backfill from cards")
    check(fb["base_url"] == "https://openrouter.ai/api/v1", "base_url should default to OpenRouter")
    check(fb["cooldown_s"] == 3600, "cooldown should default to 3600s")
    os.environ.pop("OLLAMA_TEST_FB_KEY", None)


def test_build_returns_wrapper_only_when_armed():
    role_map = {"roles": {"cards": {"model": "m", "api_key": "k", "base_url": "https://o.example"}},
                "fallback": {"api_key": "${OLLAMA_TEST_FB_KEY}"}}
    os.environ.pop("OLLAMA_TEST_FB_KEY", None)
    _, card_factory, _, _ = ollama_mix.build_ollama_mix(role_map)
    check(type(card_factory()).__name__ == "OpenAICompatGenerator",
          "without the key, build should hand back plain generators")
    os.environ["OLLAMA_TEST_FB_KEY"] = "sk-test"
    _, card_factory, _, _ = ollama_mix.build_ollama_mix(role_map)
    gen = card_factory()
    check(isinstance(gen, _FailoverGenerator), "with the key, build should wrap in _FailoverGenerator")
    check(gen._fallback.model == "z-ai/glm-5.2" and "openrouter" in gen._fallback.base_url,
          "fallback twin should point at the metered endpoint/model")
    check(gen._fallback.max_tokens == gen._primary.max_tokens, "twins should share the token budget")
    os.environ.pop("OLLAMA_TEST_FB_KEY", None)


def test_quota_trips_breaker():
    _reset_breaker()
    primary = _Stub("primary", EndpointHTTPError(429, "usage limit reached"))
    fallback = _Stub("fallback")
    gen = _FailoverGenerator(primary, fallback, cooldown_s=3600)
    out, _ = gen.first_attempt("b")
    check(out == "fallback:b", "quota 429 should fail the call over to the fallback")
    check(gen.model == "fallback", ".model should name the active side while tripped")
    second = _FailoverGenerator(_Stub("primary2"), _Stub("fallback2"), cooldown_s=3600)
    out2, _ = second.first_attempt("c")
    check(out2 == "fallback2:c", "the breaker is process-wide: fresh generators skip the primary")
    check(second._primary.calls == 0, "a tripped breaker should not touch the primary at all")
    _reset_breaker()


def test_transport_fails_over():
    _reset_breaker()
    primary = _Stub("primary", RuntimeError("could not reach endpoint https://ollama.com/v1: refused"))
    gen = _FailoverGenerator(primary, _Stub("fallback"), cooldown_s=3600)
    out, _ = gen.first_attempt("b")
    check(out == "fallback:b", "an unreachable primary should fail over for the call")
    check(ollama_mix._breaker_active(), "transport faults should trip the short breaker")
    _reset_breaker()


def test_non_quota_errors_stay_loud():
    _reset_breaker()
    for exc in (EndpointHTTPError(401, "bad key"), RuntimeError("unexpected response from endpoint: {}")):
        gen = _FailoverGenerator(_Stub("primary", exc), _Stub("fallback"), cooldown_s=3600)
        try:
            gen.first_attempt("b")
            check(False, f"{exc} should have raised, not failed over")
        except (EndpointHTTPError, RuntimeError):
            check(not ollama_mix._breaker_active(), "misconfig errors must not trip the breaker")
    _reset_breaker()


def test_breaker_expiry_returns_to_primary():
    _reset_breaker()
    ollama_mix._trip_breaker(0.0, "test")  # deadline == now → already expired
    gen = _FailoverGenerator(_Stub("primary"), _Stub("fallback"), cooldown_s=3600)
    out, _ = gen.first_attempt("b")
    check(out == "primary:b", "an expired breaker should route back to the primary")
    _reset_breaker()


def test_repair_routes_like_first_attempt():
    _reset_breaker()
    gen = _FailoverGenerator(_Stub("primary", EndpointHTTPError(402, "payment required")),
                             _Stub("fallback"), cooldown_s=3600)
    out, _ = gen.repair([], "prev", ["err"])
    check(out == "fallback:repaired", "repair() should fail over exactly like first_attempt()")
    _reset_breaker()


def test_extra_body_reaches_both_twins():
    os.environ["OLLAMA_TEST_FB_KEY"] = "sk-test"
    role_map = {"roles": {"cards": {"model": "m", "api_key": "k", "base_url": "https://o.example",
                                    "extra_body": {"reasoning_effort": "none"}}},
                "fallback": {"api_key": "${OLLAMA_TEST_FB_KEY}"}}
    _, card_factory, _, _ = ollama_mix.build_ollama_mix(role_map)
    gen = card_factory()
    check(gen._primary._extra_body == {"reasoning_effort": "none"},
          "role extra_body must reach the primary generator")
    check(gen._fallback._extra_body == {"reasoning_effort": "none"},
          "the fallback twin must carry the same extra_body (it degrades itself on a 400)")
    os.environ.pop("OLLAMA_TEST_FB_KEY", None)


def test_default_roles_disable_glm_thinking():
    for role in ("structure", "cards"):
        spec = ollama_mix.DEFAULT_ROLE_MAP["roles"][role]
        check(spec.get("extra_body", {}).get("reasoning_effort") == "none",
              f"default {role} role must pin reasoning_effort=none (glm-5.2 hidden thinking truncated "
              "the triad blueprint — 2026-08-16)")
    check("extra_body" not in ollama_mix.DEFAULT_ROLE_MAP["roles"]["brainstorm"],
          "brainstorm (non-reasoning gemma) must not carry the knob")


def test_last_meta_delegates_to_active_twin():
    _reset_breaker()
    primary, fallback = _Stub("primary"), _Stub("fallback")
    primary.last_meta = {"finish_reason": "stop"}
    fallback.last_meta = {"finish_reason": "length"}
    gen = _FailoverGenerator(primary, fallback, cooldown_s=3600)
    check(gen.last_meta == {"finish_reason": "stop"}, "last_meta should read from the primary when closed")
    ollama_mix._trip_breaker(60, "test")
    check(gen.last_meta == {"finish_reason": "length"}, "last_meta should read from the fallback when tripped")
    _reset_breaker()


def test_build_defaults_stage_attempts():
    prior = os.environ.pop("BTS_STAGE_ATTEMPTS", None)
    try:
        role_map = {"roles": {"cards": {"model": "m", "api_key": "k", "base_url": "https://o.example"}},
                    "fallback": None}
        ollama_mix.build_ollama_mix(role_map)
        check(os.environ.get("BTS_STAGE_ATTEMPTS") == "2",
              "the ollama path should default the staged front-end to 2 attempts")
        os.environ["BTS_STAGE_ATTEMPTS"] = "5"
        ollama_mix.build_ollama_mix(role_map)
        check(os.environ.get("BTS_STAGE_ATTEMPTS") == "5", "an explicit BTS_STAGE_ATTEMPTS must win")
    finally:
        if prior is None:
            os.environ.pop("BTS_STAGE_ATTEMPTS", None)
        else:
            os.environ["BTS_STAGE_ATTEMPTS"] = prior


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(name)
            fn()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
