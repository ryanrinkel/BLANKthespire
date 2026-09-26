"""Hosted *mixture* backend (Ollama Cloud primary, OpenRouter tiered fallback) — a parallel path to the Anthropic flow.

The forge makes two kinds of LLM call: a handful of CREATIVE front-end calls (cloud/cluster, map/compose,
relic-intent, reframed-blueprint) and ~23 strict closed-vocabulary CARD calls. The existing CLI/web paths
force both onto ONE backend+model. This module lets each *role* pick its own model (and even its own
endpoint), so we can brainstorm on a small/permissive model and CODE THE CARDS on a strong model (GLM-class).

It produces the same `(blueprint_gen, card_gen_factory, relic_gen, make_gen)` tuple `cli_forge_class` /
`web.forge` already consume, built entirely from the existing `OpenAICompatGenerator` — so `class_forge.py`
and the staged `BlueprintBuilder` stay untouched and every downstream safety net is intact.

Role mapping (by the contract a call carries):
  brainstorm -> _CloudClusterContract, _RelicIntentContract, _OrbIntentContract  (divergent ideation — small, hot model)
  structure  -> _MapComposeContract, _BlueprintContract         (convergent + schema-strict — strong model)
  cards      -> the card `contract` module, _RelicContract, anything else           (strict JSON coding)

Why map/compose is on `structure` not `brainstorm`: it must map clusters to EXACT catalog ids and emit a
complex nested candidate schema. A small hot model produces unparseable JSON for it ~half the time (even in
JSON mode); the strong schema-faithful model handles it reliably and fuses archetypes better. The truly
divergent stage (the cloud) stays on the small permissive model.

A role spec is {model, base_url?, api_key?, response_format?, temperature?, max_tokens_cap?, extra_body?}.
`extra_body` is merged verbatim into the request payload (e.g. {"reasoning": {"effort": "low"}} to hold a
hybrid-reasoning model's hidden thinking to a floor — see DEFAULT_ROLE_MAP's structure role). `base_url` and
`api_key` default to the top-level `defaults` block (Ollama Cloud), but a role may override them — e.g. point
`brainstorm` at a LOCAL `http://localhost:11434/v1` uncensored model while `cards` stay on hosted GLM.
`${VAR}` values are expanded from the environment (so the key never sits in a committed file).

TIERED FAILOVER — the top-level `fallbacks` list is an ORDERED chain of whole backends the same harness
re-issues a failed call against. The shipped default is:

    primary            Ollama Cloud glm-5.3 / gemma4:31b   (Ryan's account, 2026-09-24: "Ollama primary for
                                                         any compatible call, OpenRouter as the backup")
      -> openrouter-glm53   OpenRouter  z-ai/glm-5.3   (the 2026-09-18 A/B pick; different vendor + key)
      -> openrouter-glm52   OpenRouter  z-ai/glm-5.2   (covers a glm-5.3-only outage on the same key)

A tier whose api_key expands empty is DROPPED at build time, so `OPENROUTER_API_KEY` unset simply means the
OpenRouter tiers do not exist. The PRIMARY degrades the same way: a role that inherits the defaults' key and
finds it empty (no `OLLAMA_API_KEY`) is re-pointed at the first ARMED tier, which is then removed from the
chain — so a box with only an OpenRouter key forges on OpenRouter exactly as before. The singular legacy `fallback` key
(the three `generation/ollama_roles.*.json` files) is still accepted and wrapped into a one-item list;
`"fallback": null` still opts out entirely.

Each tier carries its OWN `extra_body`, applied to the structure+cards roles only (brainstorm is a
non-reasoning gemma and gets none). This matters: glm-5.3 on OpenRouter 400s on `reasoning:{enabled:false}`
("Reasoning is mandatory") and the generator's drop-rejected-key logic cannot catch it (the message names no
key), glm-5.2 on OpenRouter accepts it, and Ollama Cloud wants the `reasoning_effort` spelling — "none" for
glm-5.2, but "low" for glm-5.3, which under "none" THINKS IN THE VISIBLE CONTENT ("The user wants a JSON
object…" until max_tokens; probe 2026-09-24) and with the knob unset burns the budget on hidden reasoning.
A tier that omits `extra_body` inherits the role's (the pre-tier behavior).

A stage that fails VALIDATION (not HTTP) on the primary is re-rolled on the next tier: the staged front-end
calls `rotate_tier()` before its whole-stage retry, so "OpenRouter as the backup" covers a model whiff as
well as an outage.

COST GATE — the Ollama tier is only the cheapest route while the subscription's included usage has room
(see ollama_quota.py). Before every call, a tier on ollama.com is skipped — exactly like a tripped breaker —
when `ollama_quota.saturated(api_key)` says the session window or the week is at its ceiling, or that Ollama
has started billing per token; the call then lands on OpenRouter. The verdict comes from GET /api/usage,
polled at most once a minute per key. BTSGEN_OLLAMA_QUOTA=0 turns the gate off.

Failure semantics, per error class:
  402 / 429          account-level quota/credit — trips a process-wide breaker KEYED BY `base_url` for that
                     tier's `cooldown_s`, so EVERY tier on that endpoint is skipped (a 429 on OpenRouter
                     skips both OpenRouter tiers and lands on Ollama) instead of burning ~30 failed calls.
  transport fault    endpoint unreachable / sent no data / dropped mid-response — same breaker, 5 minutes.
  404 / 408 / 5xx    model-level outage ("no endpoints found", gateway hiccup) — skips to the next tier for
                     THIS CALL ONLY. No breaker: the next call tries the tier again.
  anything else      401 / 403 / 400 are misconfiguration or a real contract error and stay LOUD.

`.model` / `.last_meta` report the tier that actually answered (quarantine reports and the cost ledger name
the real model).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path

from . import alerts
from . import contract as _card_contract
from . import ollama_quota
from .class_forge import _BlueprintContract, _RelicContract
from .generator import EndpointHTTPError, OpenAICompatGenerator, load_env

_log = logging.getLogger("btsgen.ollama_mix")

CLOUD_BASE_URL = "https://ollama.com/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Sane built-in mix. Primary is Ollama Cloud (Ryan's account) on the same model families the 2026-09-18 A/B
# picked on OpenRouter (glm-5.3: 36 cards, 0 skipped briefs, vs 3 skipped on glm-5.2); OpenRouter is the
# metered backup. Override any of this via --ollama-config <path.json>.
DEFAULT_ROLE_MAP: dict = {
    "defaults": {"base_url": CLOUD_BASE_URL, "api_key": "${OLLAMA_API_KEY}"},
    # Cap any per-stage max_tokens request (the blueprint asks for 48000, sized for Claude's output caps —
    # too high for most open models). min(requested, cap) keeps requests valid without truncating real work.
    # glm-5.3 at effort "low" bills hidden reasoning as output tokens against this; the E2E leg ran clean.
    "max_tokens_cap": 24000,
    "roles": {
        # creative + non-reasoning for divergent brainstorming; warm temperature. (Was ministral-3:8b until
        # Mistral's small line was retired from Ollama Cloud 2026-07-15 — the only Mistral left is the 675b
        # large, too heavy/slow for a hot divergent stage. gemma-4-31b is the replacement: reliably creative,
        # cheapish, and crucially NON-reasoning — the reasoning models on offer (deepseek-v4-flash,
        # minimax-m2.5) dump everything into a hidden `reasoning` field and return EMPTY content, which is
        # unparseable.) response_format=json_object pins output to valid JSON GRAMMAR at the API level — a hot
        # model otherwise emits malformed JSON (missing commas, keys inside arrays) for the complex map/compose
        # schema, which is UNPARSEABLE so the one repair attempt can't even act on it. JSON mode guarantees
        # parseable output, so any remaining SCHEMA mistake becomes a fixable validation error.
        "brainstorm": {"model": "gemma4:31b", "temperature": 0.9,
                       "response_format": {"type": "json_object"}},
        # strong, schema-faithful model turns the dossier into card briefs; pin to JSON.
        # reasoning_effort "low" (Ollama's spelling of the knob): left unbounded a hybrid-reasoning model burns
        # 10-20k tokens of hidden thinking against max_tokens on big calls (glm-5.2's triad blueprint REPAIR
        # re-emit hit ~20k of the 24k cap, truncating the visible answer mid-JSON — "unparseable blueprint",
        # 2 of 3 forges on 2026-08-16), and "none" makes glm-5.3 narrate its reasoning INSIDE the visible
        # content until the budget runs out (probe 2026-09-24). "low" answered in 209 tokens, clean JSON.
        "structure": {"model": "glm-5.3", "response_format": {"type": "json_object"}, "temperature": 0.4,
                      "extra_body": {"reasoning_effort": "low"}},
        # GLM codes the cards: strict closed-vocab JSON, low temperature, pinned to a JSON body
        "cards": {"model": "glm-5.3", "response_format": {"type": "json_object"}, "temperature": 0.3,
                  "extra_body": {"reasoning_effort": "low"}},
    },
    # Ordered failover chain (see module docstring). Each tier is a whole backend: endpoint + per-role model
    # slugs + its own extra_body + its own breaker cooldown. A tier whose api_key expands empty is dropped.
    "fallbacks": [
        # Different vendor, different key: the metered backup for an Ollama quota/outage wall, on the same
        # model generation. reasoning.effort "low": glm-5.3 REQUIRES reasoning on OpenRouter (400s on
        # `reasoning:{enabled:false}` with "Reasoning is mandatory") and "low" is the floor it accepts.
        # usage.include makes OpenRouter return the METERED `usage.cost` per call, which the web ledger
        # records instead of guessing from a rate table. 1h cooldown: an OpenRouter credit wall is not
        # self-healing.
        {"name": "openrouter-glm53", "base_url": OPENROUTER_BASE_URL, "api_key": "${OPENROUTER_API_KEY}",
         "models": {"brainstorm": "google/gemma-4-31b-it", "structure": "z-ai/glm-5.3", "cards": "z-ai/glm-5.3"},
         "extra_body": {"reasoning": {"effort": "low"}, "usage": {"include": True}}, "cooldown_s": 3600},
        # Same key, same endpoint, one model generation back: covers a glm-5.3-only outage. glm-5.2 ACCEPTS
        # `reasoning:{enabled:false}` (and is cheaper with thinking off), so this tier says so explicitly.
        # Short cooldown: an endpoint-level breaker trip here is almost always the 5.3 tier's doing.
        {"name": "openrouter-glm52", "base_url": OPENROUTER_BASE_URL, "api_key": "${OPENROUTER_API_KEY}",
         "models": {"brainstorm": "google/gemma-4-31b-it", "structure": "z-ai/glm-5.2", "cards": "z-ai/glm-5.2"},
         "extra_body": {"reasoning": {"enabled": False}, "usage": {"include": True}}, "cooldown_s": 900},
    ],
}

# The primary tier's own breaker cooldown when IT is the one that 402/429s (1h — Ollama session limits reset
# on 5h windows, so a quota trip there is worth remembering for a while).
PRIMARY_COOLDOWN_S = 3600

# Process-wide failover breaker, KEYED BY ENDPOINT (`base_url`). One quota trip diverts every role of every
# in-flight forge away from that endpoint — quota is an account-level condition, so probing it per-call would
# just burn ~30 failed requests per forge — while leaving tiers on OTHER endpoints untouched.
_BREAKER_LOCK = threading.Lock()
_breaker_until: dict[str, float] = {}  # base_url -> time.monotonic() deadline; absent/past = closed
_TRANSPORT_COOLDOWN_S = 300

# Model-level outages (the tier is up, this model is not) and gateway hiccups: skip the tier for ONE call.
_SKIP_CODES = frozenset({404, 408})
# Account-level quota/credit exhaustion: trip the endpoint's breaker.
_QUOTA_CODES = frozenset({402, 429})
# Transport-fault fingerprints OpenAICompatGenerator raises as plain RuntimeError after its own one retry.
_TRANSPORT_MARKERS = ("could not reach", "sent no data", "dropped mid-response")


def _breaker_key(base_url: str) -> str:
    return (base_url or "").rstrip("/")


def _quota_gate(tier: "_Tier") -> str | None:
    """Why this tier should be skipped for cost (Ollama Cloud tiers only): the subscription's headroom verdict
    from ollama_quota, or None. Tiers whose generator carries no key (test doubles) are never gated."""
    if ollama_quota.OLLAMA_HOST not in (tier.base_url or ""):
        return None
    return ollama_quota.saturated(getattr(tier.gen, "api_key", "") or "")


def _breaker_active(base_url: str | None = None) -> bool:
    """True when `base_url`'s breaker is open. With no argument: true when ANY endpoint is tripped."""
    with _BREAKER_LOCK:
        now = time.monotonic()
        if base_url is None:
            return any(d > now for d in _breaker_until.values())
        return _breaker_until.get(_breaker_key(base_url), 0.0) > now


def _trip_breaker(base_url: str, seconds: float, reason: str) -> None:
    key = _breaker_key(base_url)
    with _BREAKER_LOCK:
        deadline = time.monotonic() + seconds
        if deadline > _breaker_until.get(key, 0.0):
            _breaker_until[key] = deadline
            _log.warning("hosted endpoint %s tripped (%s) — skipping its tiers for %ds", key, reason, seconds)


def _reset_breaker(base_url: str | None = None) -> None:
    """Test hook / manual override: close the breaker(s) so the next call tries the endpoint again."""
    with _BREAKER_LOCK:
        if base_url is None:
            _breaker_until.clear()
        else:
            _breaker_until.pop(_breaker_key(base_url), None)


class _Tier:
    """One rung of the failover chain: a built generator plus how long ITS quota trip should be remembered."""

    __slots__ = ("name", "gen", "cooldown_s")

    def __init__(self, gen, cooldown_s: int = PRIMARY_COOLDOWN_S, name: str | None = None) -> None:
        self.gen = gen
        self.cooldown_s = int(cooldown_s)
        self.name = name or getattr(gen, "model", "tier")

    @property
    def base_url(self) -> str:
        return getattr(self.gen, "base_url", "")


class _FailoverGenerator:
    """Same duck-typed surface the pipelines consume (`.model`, `first_attempt`, `repair`), wrapping an
    ORDERED list of tiers built from the SAME contract/params — so a failed-over call is byte-identical
    except for endpoint, model slug and the tier's own `extra_body`. `repair` carries plain chat messages, so
    a conversation started on one tier repairs fine on the next.

    A call walks the list: tiers whose endpoint breaker is open are skipped outright; a tier that raises a
    skip-class error (404/408/5xx) or trips its breaker (402/429/transport) hands the call to the next tier.
    If every tier's breaker is open the LAST tier is still attempted — a cooling-down route is better than no
    route, and it keeps the pre-tier behavior where the final fallback was never itself gated."""

    def __init__(self, tiers: list[_Tier]) -> None:
        if not tiers:
            raise RuntimeError("_FailoverGenerator needs at least one tier.")
        self._tiers = list(tiers)
        self._last: _Tier | None = None  # the tier that actually answered most recently

    # ---- diagnostics -------------------------------------------------------
    def _active(self) -> _Tier:
        """The tier that answered last, or — before any call — the first one not currently breakered."""
        if self._last is not None:
            return self._last
        for t in self._tiers:
            if not _breaker_active(t.base_url):
                return t
        return self._tiers[-1]

    @property
    def model(self) -> str:  # quarantine reports / cost ledger name the model that actually answered
        return self._active().gen.model

    @property
    def last_meta(self) -> dict:  # diagnostics from whichever tier answered (see OpenAICompatGenerator)
        return self._active().gen.last_meta

    @property
    def last_gate(self) -> dict | None:  # the vocab-gate decision of the tier that answered (see gate.py)
        return getattr(self._active().gen, "last_gate", None)

    @property
    def tiers(self) -> list[_Tier]:
        return list(self._tiers)

    # ---- routing -----------------------------------------------------------
    def _call(self, method: str, *args):
        last_exc: Exception | None = None
        attempted = False
        # The breaker is re-read per tier, INSIDE the walk: a 402/429 from the primary trips the whole
        # endpoint, so the sibling tier sharing that base_url is skipped on this very call.
        for tier in self._tiers:
            if _breaker_active(tier.base_url) or _quota_gate(tier):
                continue
            attempted = True
            try:
                out = getattr(tier.gen, method)(*args)
            except EndpointHTTPError as e:
                if e.code in _QUOTA_CODES:
                    # Account-level: remember it for the whole endpoint, then try the next tier.
                    _trip_breaker(tier.base_url, tier.cooldown_s, f"HTTP {e.code} from {tier.name}")
                    # Tell the operator (the website mails it): these are OUR keys, and a credit wall is
                    # not self-healing — without a nudge every forge quietly fails over or dies.
                    if alerts.looks_like_credit_error(e.code, e.detail):
                        alerts.credit_exhausted(source="chat", endpoint=tier.base_url, code=e.code,
                                                detail=e.detail, model=getattr(tier.gen, "model", None),
                                                tier=tier.name)
                elif e.code in _SKIP_CODES or e.code >= 500:
                    # Model-level outage / gateway hiccup: THIS call only, no breaker.
                    _log.warning("tier %s returned HTTP %d — skipping it for this call", tier.name, e.code)
                else:
                    raise  # 400/401/403 — misconfig or a real contract error; stay loud
                last_exc = e
                continue
            except RuntimeError as e:
                # transport-shaped failures already got one in-place retry inside the tier; anything else
                # (unexpected response shape, …) is not the endpoint's availability and must surface.
                msg = str(e)
                if not any(s in msg for s in _TRANSPORT_MARKERS):
                    raise
                _trip_breaker(tier.base_url, _TRANSPORT_COOLDOWN_S, f"transport: {msg[:120]}")
                last_exc = e
                continue
            self._last = tier
            return out
        if not attempted:
            # Every endpoint is cooling down. A cooling route beats no route (and it keeps the pre-tier
            # behavior, where the final fallback was never itself gated by the breaker).
            tier = self._tiers[-1]
            out = getattr(tier.gen, method)(*args)
            self._last = tier
            return out
        raise last_exc  # every tier refused; the last failure is the honest one to surface

    def rotate_tier(self) -> str | None:
        """Send this generator's NEXT calls to the tier after the one that answered last (that tier moves to
        the back of this generator's chain). The staged front-end calls it before a whole-stage re-roll, so
        a sample that failed validation on the primary is retried on the backup — a different vendor and
        model build — instead of the same one. Returns the name of the tier now at the front, or None when
        there is nothing to rotate to (single tier, or no call has answered yet)."""
        if len(self._tiers) < 2 or self._last is None or self._last not in self._tiers:
            return None
        self._tiers.remove(self._last)
        self._tiers.append(self._last)
        return self._tiers[0].name

    def avoid_provider(self, name: str | None) -> None:
        """Forward a stage re-roll's "not that upstream again" to every tier (only OpenRouter tiers act)."""
        for t in self._tiers:
            fn = getattr(t.gen, "avoid_provider", None)
            if fn is not None:
                fn(name)

    def first_attempt(self, brief):
        return self._call("first_attempt", brief)

    def repair(self, messages, prev_text, errors):
        return self._call("repair", messages, prev_text, errors)

# Which role each call's contract belongs to (resolved by class name so we never import-couple to instances).
_BRAINSTORM_CONTRACTS = frozenset({"_CloudClusterContract", "_RelicIntentContract", "_OrbIntentContract"})
# map/compose joins the blueprint on the strong schema-faithful model — see module docstring. The
# interactive forge's split halves (_MapOnlyContract/_ComposeOnlyContract) are the same convergent work.
_STRUCTURE_CONTRACTS = frozenset({"_MapComposeContract", "_MapOnlyContract", "_ComposeOnlyContract",
                                  "_BlueprintContract"})


def _resolve_role(contract_mod) -> str:
    name = type(contract_mod).__name__
    if name in _BRAINSTORM_CONTRACTS:
        return "brainstorm"
    if name in _STRUCTURE_CONTRACTS:
        return "structure"
    return "cards"  # the card `contract` module, _RelicContract, or any future contract


def _expand(value):
    """Expand a bare ${VAR} placeholder from the environment; pass anything else through unchanged."""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return os.environ.get(value[2:-1], "")
    return value


def _normalize(role_map: dict) -> dict:
    """Fill each role's base_url/api_key from `defaults`, expand ${VAR}s, and guarantee all three roles exist
    (a missing role falls back to `cards`, then `structure`, then any present role)."""
    load_env()  # so ${OPENROUTER_API_KEY} (in generation/.env) is visible
    defaults = role_map.get("defaults", {})
    base_default = _expand(defaults.get("base_url", OPENROUTER_BASE_URL))
    key_default = _expand(defaults.get("api_key", "${OPENROUTER_API_KEY}"))
    cap = role_map.get("max_tokens_cap")
    # Calls stream, so the read timeout bounds silence-between-chunks, not total generation — but big cloud
    # models under load can stall long before the first chunk. Keep the hosted path's default generous
    # (vs the generator's 180s); let a role override per model.
    timeout_default = int(role_map.get("timeout", 300))
    # `fallbacks` (the tier list) wins; the singular legacy `fallback` key is still honored; neither present
    # means inherit the built-in chain (still inert per-tier without the env vars).
    if "fallbacks" in role_map:
        raw_fbs = role_map["fallbacks"]
    elif "fallback" in role_map:
        raw_fbs = role_map["fallback"]
    else:
        raw_fbs = DEFAULT_ROLE_MAP["fallbacks"]
    fallbacks = _normalize_fallbacks(raw_fbs)

    roles: dict = {}
    promoted: dict | None = None  # the armed tier standing in for an unarmed primary (see module docstring)
    for name, spec in (role_map.get("roles") or {}).items():
        if name.startswith("_"):  # "_brainstorm_comment"-style annotation keys (see the example JSONs)
            continue
        s = dict(spec)
        s["base_url"] = _expand(s.get("base_url", base_default))
        s["api_key"] = _expand(s.get("api_key", key_default))
        if not s.get("model"):
            raise RuntimeError(f"hosted role '{name}' is missing a 'model'.")
        if not s["api_key"] and "api_key" not in spec and fallbacks:
            # The role rides the defaults' endpoint and that key is unset: stand the first armed tier in as
            # the primary for this role (its endpoint, key, model slug and extra_body — a slug is endpoint-
            # specific, so the role's own model cannot be kept). Only a role WITHOUT its own api_key
            # qualifies; an explicit-but-empty key is a misconfiguration and stays loud below.
            promoted = fallbacks[0]
            s["base_url"], s["api_key"] = promoted["base_url"], promoted["api_key"]
            s["model"] = promoted["models"][name] if name in promoted["models"] else s["model"]
            s["extra_body"] = _tier_extra_body(promoted, name, s)
            _log.warning("hosted role '%s': no key for %s — using tier '%s' (%s) as the primary",
                         name, s.get("base_url"), promoted["name"], s["model"])
        if not s["api_key"]:
            raise RuntimeError(
                f"hosted role '{name}' has no API key. Set OLLAMA_API_KEY (the primary) and/or "
                "OPENROUTER_API_KEY (the backup) in generation/.env (see .env.example), or give the role an "
                "explicit api_key."
            )
        s["timeout"] = int(s.get("timeout", timeout_default))
        roles[name] = s
    if promoted is not None:
        fallbacks = [fb for fb in fallbacks if fb is not promoted]

    if not roles:
        raise RuntimeError("hosted role map has no roles.")
    # Backfill the three roles the forge needs from whatever is present.
    for need in ("cards", "structure", "brainstorm"):
        if need not in roles:
            donor = roles.get("cards") or roles.get("structure") or next(iter(roles.values()))
            roles[need] = dict(donor)
    return {"roles": roles, "max_tokens_cap": cap, "fallbacks": fallbacks}


# Sentinel: a tier that does not mention `extra_body` at all inherits the ROLE's (pre-tier behavior, which
# the three shipped ollama_roles.*.json files rely on). An explicit `"extra_body": null` means "send none".
_INHERIT_EXTRA_BODY = object()


def _normalize_fallbacks(fbs) -> list[dict]:
    """Expand + validate the ORDERED failover chain. Accepts a list of tiers, a single tier dict (the legacy
    singular `fallback` key), or None/empty (failover disabled). A tier whose api_key expands empty is
    dropped — that is how `OPENROUTER_API_KEY` unset silently removes the backup tiers."""
    if not fbs:
        return []
    if isinstance(fbs, dict):  # legacy singular `fallback` block -> a one-item chain
        fbs = [fbs]
    out: list[dict] = []
    for i, fb in enumerate(fbs):
        if not fb:
            continue
        api_key = _expand(fb.get("api_key", "${OPENROUTER_API_KEY}"))
        name = fb.get("name") or f"fallback{i + 1}"
        if not api_key:
            _log.debug("failover tier '%s' dropped: its api_key expands empty", name)
            continue
        models = dict(fb.get("models") or DEFAULT_ROLE_MAP["fallbacks"][0]["models"])
        for need in ("cards", "structure", "brainstorm"):
            if not models.get(need):
                models[need] = models.get("cards") or models.get("structure") or next(iter(models.values()))
        out.append({
            "name": name,
            "base_url": _expand(fb.get("base_url", OPENROUTER_BASE_URL)),
            "api_key": api_key,
            "models": models,
            "extra_body": fb["extra_body"] if "extra_body" in fb else _INHERIT_EXTRA_BODY,
            "cooldown_s": int(fb.get("cooldown_s", 3600)),
        })
    return out


def _tier_extra_body(tier: dict, role: str, role_spec: dict):
    """A tier's extra_body applies to the structure+cards roles ONLY — brainstorm rides a non-reasoning
    model on every tier and must not be handed a reasoning knob it will 400 on."""
    if role == "brainstorm":
        return None
    eb = tier.get("extra_body", _INHERIT_EXTRA_BODY)
    return role_spec.get("extra_body") if eb is _INHERIT_EXTRA_BODY else eb


# Creative harness v2 (BTS_HARNESS_V2=1, the temperature half of Fix E): warm the STRUCTURE role (map/compose +
# blueprint) from 0.4 to 0.6 on the token path. Cards stay at 0.3 (the encode step must be convergent). Applied
# to the built-in map only — an explicit --ollama-config keeps whatever it says.
HARNESS_V2_TEMPERATURES = {"structure": 0.6}


def effective_role_map(role_map: dict | None = None) -> dict:
    """The role map build_ollama_mix / describe should use: the caller's map verbatim, or DEFAULT_ROLE_MAP with
    the harness-v2 temperature bump applied when the flag is on (read at call time, so the flag governs)."""
    if role_map is not None:
        return role_map
    from . import harness_v2
    if not harness_v2.enabled():
        return DEFAULT_ROLE_MAP
    import copy
    out = copy.deepcopy(DEFAULT_ROLE_MAP)
    for role, temp in HARNESS_V2_TEMPERATURES.items():
        if role in out.get("roles", {}):
            out["roles"][role]["temperature"] = temp
    return out


def build_ollama_mix(role_map: dict | None = None, *, on_usage=None):
    """role_map -> (blueprint_gen, card_gen_factory, relic_gen, make_gen). Mirrors the tuple the existing
    forge paths consume; each role gets its own model/endpoint via OpenAICompatGenerator. `on_usage` (optional)
    is a callback(usage_dict) attached to every generator for cost/telemetry (used by the A/B harness)."""
    # Open models whiff a staged stage (unparseable/invalid after its one repair) far more often than
    # Claude, and a whole-stage re-roll usually lands — default the staged front-end to 2 attempts on this
    # path. setdefault: an explicit BTS_STAGE_ATTEMPTS (env or caller) always wins.
    os.environ.setdefault("BTS_STAGE_ATTEMPTS", "2")
    cfg = _normalize(effective_role_map(role_map))
    cap = cfg["max_tokens_cap"]
    fbs = cfg["fallbacks"]

    def _tagged(role: str, model: str):
        """Wrap on_usage so each usage dict also says which role/model produced it (the web's per-forge cost
        ledger groups by these). The original keys are untouched, so callers reading prompt_tokens etc. work."""
        if on_usage is None:
            return None
        # A dict that already names its role/model keeps them: the card generator's vocab gate reports its
        # Jev calls as role "gate" through this same callback, and they must not be booked as "cards".
        return lambda u, _r=role, _m=model: on_usage(
            {"_role": _r, "_model": _m, **u} if isinstance(u, dict) else u)

    def _gen(role: str, contract_mod, max_tokens: int):
        spec = cfg["roles"][role]
        eff = min(max_tokens, int(spec.get("max_tokens_cap", cap))) if (spec.get("max_tokens_cap") or cap) else max_tokens
        # Reasoning models (glm-5.3, kimi-k3, …) bill hidden thinking against max_tokens BEFORE any visible
        # content, so a small stage budget (relic-intent asks for 2000) truncates the answer to nothing. A
        # role serving such a model can set a floor; applied after the cap so the floor wins when both are set.
        if spec.get("max_tokens_floor"):
            eff = max(eff, int(spec["max_tokens_floor"]))

        def _build(base_url: str, api_key: str, model: str, extra_body):
            # Every tier differs ONLY in endpoint, model slug and extra_body — same contract, JSON pin,
            # temperature, token budget and timeout — so a failed-over call exercises the identical harness.
            return OpenAICompatGenerator(
                base_url, api_key, model,
                contract_mod=contract_mod, max_tokens=eff, timeout=spec["timeout"],
                response_format=spec.get("response_format"),
                temperature=spec.get("temperature"),
                on_usage=_tagged(role, model),
                extra_body=extra_body,
            )

        primary = _build(spec["base_url"], spec["api_key"], spec["model"], spec.get("extra_body"))
        if not fbs:
            return primary
        tiers = [_Tier(primary, PRIMARY_COOLDOWN_S, name="primary")]
        for fb in fbs:
            tiers.append(_Tier(
                _build(fb["base_url"], fb["api_key"], fb["models"][role],
                       _tier_extra_body(fb, role, spec)),
                fb["cooldown_s"], name=fb["name"]))
        return _FailoverGenerator(tiers)

    # One-shot blueprint generator (only used when the staged front-end is OFF) + relic generator. The
    # one-shot path is the classic 2-archetype flow — triad lives in the staged front-end — so pin the
    # contract off the (now default-on) triad env.
    blueprint_gen = _gen("structure", _BlueprintContract(triad=False), 24000)
    relic_gen = _gen("cards", _RelicContract(), 4000)
    card_gen_factory = lambda: _gen("cards", _card_contract, 4000)  # noqa: E731
    make_gen = lambda contract_mod, *, max_tokens: _gen(  # noqa: E731
        _resolve_role(contract_mod), contract_mod, max_tokens)
    return blueprint_gen, card_gen_factory, relic_gen, make_gen


def load_role_map(path: str | os.PathLike) -> dict:
    """Read a role map from a JSON file (see ollama_roles.example.json)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _no_think(extra_body) -> bool:
    """Whether a tier's extra_body asks the model NOT to think (either provider's spelling)."""
    if not isinstance(extra_body, dict):
        return False
    reasoning = extra_body.get("reasoning")
    return (extra_body.get("reasoning_effort") == "none"
            or (isinstance(reasoning, dict) and reasoning.get("enabled") is False))


def describe(role_map: dict | None = None, *, quota: bool = False) -> str:
    """One-line-per-role/tier summary for the CLI banner (no secrets — just role -> model @ host). `quota=True`
    appends the Ollama cost gate's verdict, which polls the usage endpoint (so offline callers leave it off)."""
    cfg = _normalize(effective_role_map(role_map))
    lines = []
    for role in ("brainstorm", "structure", "cards"):
        s = cfg["roles"][role]
        host = s["base_url"].replace("https://", "").replace("http://", "").split("/")[0]
        extras = []
        if s.get("temperature") is not None:
            extras.append(f"t={s['temperature']}")
        if s.get("response_format"):
            extras.append("json")
        if _no_think(s.get("extra_body")):
            extras.append("no-think")
        eb = s.get("extra_body") or {}
        effort = eb.get("reasoning", {})
        if isinstance(effort, dict) and effort.get("effort"):
            extras.append(f"think={effort['effort']}")
        elif eb.get("reasoning_effort") and eb["reasoning_effort"] != "none":  # Ollama's spelling of the knob
            extras.append(f"think={eb['reasoning_effort']}")
        tail = f" ({', '.join(extras)})" if extras else ""
        lines.append(f"  {role:10s} -> {s['model']} @ {host}{tail}")
    fbs = cfg["fallbacks"]
    if fbs:
        for i, fb in enumerate(fbs, 1):
            host = fb["base_url"].replace("https://", "").replace("http://", "").split("/")[0]
            lines.append(f"  fallback {i} -> {fb['name']}: {fb['models']['cards']} @ {host} (armed)")
    else:
        lines.append("  fallback   -> none armed (set OPENROUTER_API_KEY / OLLAMA_API_KEY for failover tiers)")
    # The cost gate's verdict for whichever Ollama key the roles/tiers use (one line; polls the usage endpoint).
    keys = {s["api_key"] for s in cfg["roles"].values() if ollama_quota.OLLAMA_HOST in s["base_url"]}
    keys |= {fb["api_key"] for fb in fbs if ollama_quota.OLLAMA_HOST in fb["base_url"]}
    for key in sorted(k for k in keys if k) if quota else []:
        lines.append(f"  ollama quota -> {ollama_quota.status_line(key)}")
    return "\n".join(lines)
