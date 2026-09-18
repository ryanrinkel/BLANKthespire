"""Offline tests for the ollama_mix tiered failover — no API key, no network.

Run:  uv run python -m pytest -q tests/test_ollama_failover.py     (from generation/)
  or: uv run python -m tests.test_ollama_failover                  (standalone runner, exits nonzero)

Covers the whole error-class contract of the OpenRouter-primary chain (glm-5.3 -> glm-5.2 -> Ollama):
tiers whose api_key expands empty are dropped, the armed chain builds _FailoverGenerator with the right
endpoints/models/extra_body, a quota 402/429 fails the call over AND trips a breaker keyed by `base_url`
(so BOTH OpenRouter tiers are skipped and the call lands on Ollama), transport faults trip the short
breaker, a 404/408/5xx skips ONE tier for ONE call without tripping anything, misconfig errors (400/401/403)
stay loud, breaker expiry returns to the primary, `.model`/`.last_meta` name the tier that answered, and the
legacy singular `fallback` key still loads.
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path

from btsgen import ollama_mix
from btsgen.generator import EndpointHTTPError
from btsgen.ollama_mix import _FailoverGenerator, _Tier, _reset_breaker

_PASS = 0
_FAIL = 0

OPENROUTER = "https://openrouter.ai/api/v1"
OLLAMA = "https://ollama.com/v1"


def check(cond: bool, msg: str) -> None:
    """Record + assert. The assert is what makes these real pytest failures; `main()` below catches it so
    the standalone runner still reports every test instead of stopping at the first miss."""
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        return
    _FAIL += 1
    print(f"  FAIL: {msg}")
    raise AssertionError(msg)


class _Stub:
    """Duck-typed generator stand-in: raises `exc` (for its first `fail_times` calls) or returns its tag."""

    def __init__(self, tag: str, exc: Exception | None = None, base_url: str | None = None,
                 fail_times: int | None = None):
        self.model = tag
        self.base_url = base_url or f"https://{tag}.example"
        self.exc = exc
        self.fail_times = fail_times  # None = fail forever
        self.calls = 0
        self.last_meta: dict = {}

    def _maybe_raise(self):
        self.calls += 1
        if self.exc is None:
            return
        if self.fail_times is None or self.calls <= self.fail_times:
            raise self.exc

    def first_attempt(self, brief):
        self._maybe_raise()
        return f"{self.model}:{brief}", []

    def repair(self, messages, prev_text, errors):
        self._maybe_raise()
        return f"{self.model}:repaired", []


def _chain(*stubs, cooldown_s: int = 3600) -> _FailoverGenerator:
    """Wrap stubs into an ordered tier chain (every tier gets the same cooldown unless a test says otherwise)."""
    return _FailoverGenerator([_Tier(s, cooldown_s, name=s.model) for s in stubs])


@contextlib.contextmanager
def _env(**kv):
    """Set env vars for the block, restore exactly afterwards. Pass "" to mean UNSET: `_normalize` calls
    `load_env()`, which `setdefault`s generation/.env into the environment — a POPPED key would come back
    from a developer's real .env and make these tests machine-dependent, while an empty one survives."""
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


# ------------------------------------------------------------------ normalization / build

def test_tier_dropped_without_key():
    with _env(OLLAMA_TEST_FB_KEY=""):
        fbs = ollama_mix._normalize_fallbacks([{"api_key": "${OLLAMA_TEST_FB_KEY}"}])
        check(fbs == [], "a tier whose api_key env var is unset should be dropped")
    check(ollama_mix._normalize_fallbacks(None) == [], '"fallback": null should disable failover')
    check(ollama_mix._normalize_fallbacks([]) == [], "an empty tier list is failover-disabled")


def test_armed_normalization():
    with _env(OLLAMA_TEST_FB_KEY="sk-test"):
        fbs = ollama_mix._normalize_fallbacks([{"api_key": "${OLLAMA_TEST_FB_KEY}",
                                                "models": {"cards": "x/y"}}])
        check(len(fbs) == 1 and fbs[0]["api_key"] == "sk-test", "an armed tier should expand its key")
        fb = fbs[0]
        check(fb["models"]["structure"] == "x/y" and fb["models"]["brainstorm"] == "x/y",
              "missing role models should backfill from cards")
        check(fb["base_url"] == OPENROUTER, "base_url should default to OpenRouter")
        check(fb["cooldown_s"] == 3600, "cooldown should default to 3600s")
        check(fb["name"] == "fallback1", "an unnamed tier gets a positional name")


def test_singular_fallback_key_still_loads():
    """The three shipped generation/ollama_roles.*.json files use the singular `fallback` block."""
    with _env(OPENROUTER_API_KEY="sk-or-test", OLLAMA_API_KEY="sk-ol-test"):
        fbs = ollama_mix._normalize_fallbacks({"api_key": "${OPENROUTER_API_KEY}",
                                               "models": {"cards": "z-ai/glm-5.2"}, "cooldown_s": 1200})
        check(len(fbs) == 1 and fbs[0]["cooldown_s"] == 1200,
              "a singular `fallback` dict should wrap into a one-item tier list")
        root = Path(__file__).resolve().parents[1]
        for name in ("ollama_roles.example.json", "ollama_roles.hybrid.json", "ollama_roles.kimi3.json"):
            rm = json.loads((root / name).read_text(encoding="utf-8"))
            cfg = ollama_mix._normalize(rm)
            check(isinstance(cfg["fallbacks"], list), f"{name} should normalize to a tier list")
            if rm.get("fallback"):
                check(len(cfg["fallbacks"]) == 1 and cfg["fallbacks"][0]["models"]["cards"],
                      f"{name}'s singular fallback block should arm exactly one tier")
            else:  # hybrid.json names no fallback at all -> it inherits the built-in chain
                check(len(cfg["fallbacks"]) == 2,
                      f"{name} should inherit the built-in tier chain")
            check(ollama_mix.describe(rm), f"{name} should render a CLI banner")


def test_missing_key_error_names_openrouter():
    with _env(OPENROUTER_API_KEY=""):
        try:
            ollama_mix._normalize({"roles": {"cards": {"model": "m"}}, "fallback": None})
            check(False, "a role with no API key should raise")
        except RuntimeError as e:
            check("OPENROUTER_API_KEY" in str(e), f"the no-key error must name OPENROUTER_API_KEY, got: {e}")


def test_build_returns_wrapper_only_when_armed():
    role_map = {"roles": {"cards": {"model": "m", "api_key": "k", "base_url": "https://o.example"}},
                "fallbacks": [{"api_key": "${OLLAMA_TEST_FB_KEY}"}]}
    with _env(OLLAMA_TEST_FB_KEY=""):
        _, card_factory, _, _ = ollama_mix.build_ollama_mix(role_map)
        check(type(card_factory()).__name__ == "OpenAICompatGenerator",
              "with no armed tier, build should hand back plain generators")
    with _env(OLLAMA_TEST_FB_KEY="sk-test"):
        _, card_factory, _, _ = ollama_mix.build_ollama_mix(role_map)
        gen = card_factory()
        check(isinstance(gen, _FailoverGenerator), "with the key, build should wrap in _FailoverGenerator")
        tiers = gen.tiers
        check(len(tiers) == 2 and tiers[0].name == "primary", "the chain is primary + one armed tier")
        check(tiers[1].gen.model == "z-ai/glm-5.2" and "openrouter" in tiers[1].gen.base_url,
              "an unspecified tier defaults to the metered OpenRouter endpoint/model")
        check(tiers[1].gen.max_tokens == tiers[0].gen.max_tokens, "tiers should share the token budget")


def test_default_chain_shape():
    with _env(OPENROUTER_API_KEY="sk-or-test", OLLAMA_API_KEY="sk-ol-test"):
        _, card_factory, _, _ = ollama_mix.build_ollama_mix()
        tiers = card_factory().tiers
        check([t.name for t in tiers] == ["primary", "openrouter-glm52", "ollama"],
              f"the default chain is glm-5.3 -> glm-5.2 -> ollama, got {[t.name for t in tiers]}")
        check(tiers[0].gen.model == "z-ai/glm-5.3" and tiers[0].gen.base_url == OPENROUTER,
              "the primary tier is OpenRouter glm-5.3")
        check(tiers[1].gen.model == "z-ai/glm-5.2" and tiers[1].gen.base_url == OPENROUTER,
              "the second tier is OpenRouter glm-5.2 (same endpoint, one generation back)")
        check(tiers[2].gen.model == "glm-5.2" and tiers[2].gen.base_url == OLLAMA,
              "the last tier is Ollama Cloud")
        check(tiers[0].cooldown_s == 3600 and tiers[1].cooldown_s == 900 and tiers[2].cooldown_s == 3600,
              "per-tier cooldowns: 1h primary, 15m glm-5.2, 1h ollama")
    # OLLAMA_API_KEY unset and the last tier simply stops existing.
    with _env(OPENROUTER_API_KEY="sk-or-test", OLLAMA_API_KEY=""):
        _, card_factory, _, _ = ollama_mix.build_ollama_mix()
        check([t.name for t in card_factory().tiers] == ["primary", "openrouter-glm52"],
              "OLLAMA_API_KEY unset should silently drop the Ollama tier")


# ------------------------------------------------------------------ error classes

def test_quota_trips_breaker():
    _reset_breaker()
    primary = _Stub("primary", EndpointHTTPError(429, "usage limit reached"))
    fallback = _Stub("fallback")
    gen = _chain(primary, fallback)
    out, _ = gen.first_attempt("b")
    check(out == "fallback:b", "quota 429 should fail the call over to the next tier")
    check(gen.model == "fallback", ".model should name the tier that answered")
    check(ollama_mix._breaker_active(primary.base_url), "429 should trip the primary endpoint's breaker")
    second = _chain(_Stub("primary2", base_url=primary.base_url), _Stub("fallback2"))
    out2, _ = second.first_attempt("c")
    check(out2 == "fallback2:c", "the breaker is process-wide: fresh generators skip that endpoint")
    check(second.tiers[0].gen.calls == 0, "a tripped breaker should not touch that endpoint at all")
    _reset_breaker()


def test_breaker_is_keyed_by_base_url():
    _reset_breaker()
    ollama_mix._trip_breaker(OPENROUTER, 60, "test")
    check(ollama_mix._breaker_active(OPENROUTER), "the tripped endpoint is breakered")
    check(not ollama_mix._breaker_active(OLLAMA), "a DIFFERENT endpoint must stay open")
    check(ollama_mix._breaker_active(OPENROUTER + "/"), "the key ignores a trailing slash")
    _reset_breaker()


def test_429_on_openrouter_trips_both_openrouter_tiers_and_lands_on_ollama():
    _reset_breaker()
    t1 = _Stub("or-glm53", EndpointHTTPError(429, "credits exhausted"), base_url=OPENROUTER)
    t2 = _Stub("or-glm52", base_url=OPENROUTER)
    t3 = _Stub("ollama", base_url=OLLAMA)
    gen = _chain(t1, t2, t3)
    out, _ = gen.first_attempt("b")
    check(out == "ollama:b", "a 429 on OpenRouter should land the call on the Ollama tier")
    check(t2.calls == 0, "the sibling tier sharing the OpenRouter base_url must be skipped on THIS call")
    check(ollama_mix._breaker_active(OPENROUTER) and not ollama_mix._breaker_active(OLLAMA),
          "only the OpenRouter endpoint is breakered")
    check(gen.model == "ollama", ".model should report the tier that answered")
    _reset_breaker()


def test_5xx_skips_one_tier_for_one_call_without_tripping():
    _reset_breaker()
    t1 = _Stub("or-glm53", EndpointHTTPError(503, "upstream unavailable"), base_url=OPENROUTER, fail_times=1)
    t2 = _Stub("or-glm52", base_url=OPENROUTER)
    gen = _chain(t1, t2)
    out, _ = gen.first_attempt("b")
    check(out == "or-glm52:b", "a 5xx should skip to the next tier for this call")
    check(not ollama_mix._breaker_active(), "a 5xx must NOT trip any breaker")
    out2, _ = gen.first_attempt("c")
    check(out2 == "or-glm53:c", "the next call must try the skipped tier again (no breaker was set)")
    _reset_breaker()


def test_404_and_408_skip_the_tier():
    for code in (404, 408):
        _reset_breaker()
        t1 = _Stub("bogus-slug", EndpointHTTPError(code, "no endpoints found"), base_url=OPENROUTER)
        t2 = _Stub("next", base_url=OPENROUTER)
        out, _ = _chain(t1, t2).first_attempt("b")
        check(out == "next:b", f"HTTP {code} should skip to the next tier")
        check(not ollama_mix._breaker_active(), f"HTTP {code} must not trip a breaker")
    _reset_breaker()


def test_transport_fails_over():
    _reset_breaker()
    primary = _Stub("primary", RuntimeError("could not reach endpoint https://ollama.com/v1: refused"))
    gen = _chain(primary, _Stub("fallback"))
    out, _ = gen.first_attempt("b")
    check(out == "fallback:b", "an unreachable tier should fail over for the call")
    check(ollama_mix._breaker_active(primary.base_url), "transport faults should trip the short breaker")
    _reset_breaker()


def test_non_quota_errors_stay_loud():
    _reset_breaker()
    loud = (EndpointHTTPError(401, "bad key"), EndpointHTTPError(403, "forbidden"),
            EndpointHTTPError(400, "Reasoning is mandatory"),
            RuntimeError("unexpected response from endpoint: {}"))
    for exc in loud:
        gen = _chain(_Stub("primary", exc), _Stub("fallback"))
        try:
            gen.first_attempt("b")
            check(False, f"{exc} should have raised, not failed over")
        except (EndpointHTTPError, RuntimeError):
            check(not ollama_mix._breaker_active(), "misconfig errors must not trip the breaker")
        check(gen.tiers[1].gen.calls == 0, f"{exc} must not reach the next tier")
    _reset_breaker()


def test_every_tier_refuses_raises_the_last_failure():
    _reset_breaker()
    gen = _chain(_Stub("a", EndpointHTTPError(503, "down"), base_url=OPENROUTER),
                 _Stub("b", EndpointHTTPError(404, "no endpoints found"), base_url=OLLAMA))
    try:
        gen.first_attempt("x")
        check(False, "a chain where every tier refuses must raise")
    except EndpointHTTPError as e:
        check(e.code == 404, f"the LAST tier's failure is the honest one to surface, got {e.code}")
    _reset_breaker()


def test_all_endpoints_cooling_still_tries_the_last_tier():
    _reset_breaker()
    ollama_mix._trip_breaker(OPENROUTER, 60, "test")
    ollama_mix._trip_breaker(OLLAMA, 60, "test")
    gen = _chain(_Stub("or", base_url=OPENROUTER), _Stub("ollama", base_url=OLLAMA))
    out, _ = gen.first_attempt("b")
    check(out == "ollama:b", "with every endpoint cooling down, the last tier is still attempted")
    _reset_breaker()


def test_breaker_expiry_returns_to_primary():
    _reset_breaker()
    ollama_mix._trip_breaker("https://primary.example", 0.0, "test")  # deadline == now → already expired
    gen = _chain(_Stub("primary"), _Stub("fallback"))
    out, _ = gen.first_attempt("b")
    check(out == "primary:b", "an expired breaker should route back to the primary")
    _reset_breaker()


def test_repair_routes_like_first_attempt():
    _reset_breaker()
    gen = _chain(_Stub("primary", EndpointHTTPError(402, "payment required")), _Stub("fallback"))
    out, _ = gen.repair([], "prev", ["err"])
    check(out == "fallback:repaired", "repair() should fail over exactly like first_attempt()")
    _reset_breaker()


# ------------------------------------------------------------------ per-tier extra_body

def test_extra_body_is_per_tier():
    from btsgen.frontend.stage_cloud import _CloudClusterContract
    with _env(OPENROUTER_API_KEY="sk-or-test", OLLAMA_API_KEY="sk-ol-test"):
        _, card_factory, _, make_gen = ollama_mix.build_ollama_mix()
        tiers = card_factory().tiers
        check(tiers[0].gen._extra_body == {"reasoning": {"effort": "low"}, "usage": {"include": True}},
              "the glm-5.3 primary must send reasoning.effort=low (it 400s on reasoning.enabled=false)")
        check(tiers[1].gen._extra_body == {"reasoning": {"enabled": False}, "usage": {"include": True}},
              "the glm-5.2 OpenRouter tier carries its OWN extra_body, not the primary's")
        check(tiers[2].gen._extra_body == {"reasoning_effort": "none"},
              "the Ollama tier wants reasoning_effort=none (the OpenRouter spelling is ignored there)")
        # brainstorm rides a non-reasoning gemma on every tier and must carry no knob at all.
        bs = make_gen(_CloudClusterContract(), max_tokens=4000)
        check(all(not t.gen._extra_body for t in bs.tiers),
              "brainstorm must not receive a tier-level extra_body on ANY tier")


def test_tier_without_extra_body_inherits_the_role():
    """Backward compatibility for the shipped ollama_roles.*.json tiers, which name no extra_body."""
    role_map = {"roles": {"cards": {"model": "m", "api_key": "k", "base_url": "https://o.example",
                                    "extra_body": {"reasoning_effort": "none"}}},
                "fallbacks": [{"api_key": "${OLLAMA_TEST_FB_KEY}"},
                              {"api_key": "${OLLAMA_TEST_FB_KEY}", "extra_body": None}]}
    with _env(OLLAMA_TEST_FB_KEY="sk-test"):
        _, card_factory, _, _ = ollama_mix.build_ollama_mix(role_map)
        tiers = card_factory().tiers
        check(tiers[0].gen._extra_body == {"reasoning_effort": "none"},
              "role extra_body must reach the primary generator")
        check(tiers[1].gen._extra_body == {"reasoning_effort": "none"},
              "a tier that names no extra_body inherits the role's (pre-tier behavior)")
        check(tiers[2].gen._extra_body == {}, 'an explicit "extra_body": null sends none')


def test_default_roles_pin_reasoning_per_provider():
    for role in ("structure", "cards"):
        eb = ollama_mix.DEFAULT_ROLE_MAP["roles"][role].get("extra_body", {})
        check(eb.get("reasoning") == {"effort": "low"},
              f"default {role} role must pin reasoning.effort=low (glm-5.3 400s on reasoning.enabled=false: "
              "'Reasoning is mandatory'; unbounded thinking truncated the triad blueprint — 2026-08-16)")
        check(eb.get("usage") == {"include": True},
              f"default {role} role must ask OpenRouter for metered usage.cost")
        check("reasoning_effort" not in eb,
              f"the OpenRouter {role} role must not send Ollama's reasoning_effort spelling")
    check("extra_body" not in ollama_mix.DEFAULT_ROLE_MAP["roles"]["brainstorm"],
          "brainstorm (non-reasoning gemma) must not carry the knob")
    by_name = {t["name"]: t for t in ollama_mix.DEFAULT_ROLE_MAP["fallbacks"]}
    or_tier = by_name["openrouter-glm52"]["extra_body"]
    check("reasoning_effort" not in or_tier and or_tier["reasoning"] == {"enabled": False},
          "the OpenRouter glm-5.2 tier disables reasoning the OpenRouter way, never reasoning_effort")
    ol_tier = by_name["ollama"]["extra_body"]
    check("reasoning" not in ol_tier and ol_tier["reasoning_effort"] == "none",
          "the Ollama tier uses reasoning_effort=none and never the OpenRouter `reasoning` object")


# ------------------------------------------------------------------ diagnostics + build side effects

def test_last_meta_delegates_to_the_answering_tier():
    _reset_breaker()
    primary, fallback = _Stub("primary", base_url=OPENROUTER), _Stub("fallback", base_url=OLLAMA)
    primary.last_meta = {"finish_reason": "stop"}
    fallback.last_meta = {"finish_reason": "length"}
    gen = _chain(primary, fallback)
    check(gen.last_meta == {"finish_reason": "stop"}, "last_meta should read from the primary when closed")
    ollama_mix._trip_breaker(OPENROUTER, 60, "test")
    check(gen.last_meta == {"finish_reason": "length"},
          "before any call, last_meta reads the first tier whose endpoint is open")
    _reset_breaker()
    gen.first_attempt("b")  # answered by the primary
    check(gen.model == "primary" and gen.last_meta == {"finish_reason": "stop"},
          "after a call, .model/.last_meta name the tier that actually answered")
    _reset_breaker()


def test_build_defaults_stage_attempts():
    prior = os.environ.pop("BTS_STAGE_ATTEMPTS", None)
    try:
        role_map = {"roles": {"cards": {"model": "m", "api_key": "k", "base_url": "https://o.example"}},
                    "fallback": None}
        ollama_mix.build_ollama_mix(role_map)
        check(os.environ.get("BTS_STAGE_ATTEMPTS") == "2",
              "the hosted path should default the staged front-end to 2 attempts")
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
            try:
                fn()
            except AssertionError:
                pass  # already counted + printed by check()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
