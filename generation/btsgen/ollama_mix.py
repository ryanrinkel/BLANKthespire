"""Ollama-Cloud *mixture* backend — a parallel path to the Anthropic flow.

The forge makes two kinds of LLM call: a handful of CREATIVE front-end calls (cloud/cluster, map/compose,
relic-intent, reframed-blueprint) and ~23 strict closed-vocabulary CARD calls. The existing CLI/web paths
force both onto ONE backend+model. This module lets each *role* pick its own Ollama model (and even its own
endpoint), so we can brainstorm on a small/permissive model and CODE THE CARDS on a strong model (GLM-class).

It produces the same `(blueprint_gen, card_gen_factory, relic_gen, make_gen)` tuple `cli_forge_class` /
`web.forge` already consume, built entirely from the existing `OpenAICompatGenerator` — so `class_forge.py`
and the staged `BlueprintBuilder` stay untouched and every downstream safety net is intact.

Role mapping (by the contract a call carries):
  brainstorm -> _CloudClusterContract, _RelicIntentContract     (divergent ideation — small, hot model)
  structure  -> _MapComposeContract, _BlueprintContract         (convergent + schema-strict — strong model)
  cards      -> the card `contract` module, _RelicContract, anything else           (strict JSON coding)

Why map/compose is on `structure` not `brainstorm`: it must map clusters to EXACT catalog ids and emit a
complex nested candidate schema. A small hot model produces unparseable JSON for it ~half the time (even in
JSON mode); the strong schema-faithful model handles it reliably and fuses archetypes better. The truly
divergent stage (the cloud) stays on the small permissive model.

A role spec is {model, base_url?, api_key?, response_format?, temperature?, max_tokens_cap?}. `base_url` and
`api_key` default to the top-level `defaults` block (Ollama Cloud), but a role may override them — e.g. point
`brainstorm` at a LOCAL `http://localhost:11434/v1` uncensored model while `cards` stay on cloud GLM.
`${VAR}` values are expanded from the environment (so the key never sits in a committed file).

METERED FALLBACK — the top-level `fallback` block arms an automatic escape hatch for when the flat Ollama
Cloud plan runs out of GPU-time quota: the SAME harness re-issues the failed call against a per-token
OpenAI-compatible provider (default: OpenRouter, serving the same glm/ministral model families). It is a
no-op until its api_key expands non-empty — set OPENROUTER_API_KEY on the server and it is live, unset it
and the forge behaves exactly as before. Quota errors (HTTP 429/402) trip a process-wide breaker that routes
ALL calls to the fallback for `cooldown_s` (default 1h — Ollama session limits reset on 5h windows), so a
mid-forge quota wall costs one failed call, not thirty. Transient transport faults (endpoint unreachable /
stalled / dropped) trip a short 5-minute breaker instead. Set `"fallback": null` to disable it outright.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path

from . import contract as _card_contract
from .class_forge import _BlueprintContract, _RelicContract
from .generator import EndpointHTTPError, OpenAICompatGenerator, load_env

_log = logging.getLogger("btsgen.ollama_mix")

CLOUD_BASE_URL = "https://ollama.com/v1"

# Sane built-in mix, all on Ollama Cloud. Models verified live in the cloud catalog (GET /v1/models).
# Override any of this via --ollama-config <path.json>.
DEFAULT_ROLE_MAP: dict = {
    "defaults": {"base_url": CLOUD_BASE_URL, "api_key": "${OLLAMA_API_KEY}"},
    # Cap any per-stage max_tokens request (the blueprint asks for 48000, sized for Claude's output caps —
    # too high for most open models). min(requested, cap) keeps requests valid without truncating real work.
    "max_tokens_cap": 24000,
    "roles": {
        # creative + non-reasoning for divergent brainstorming; warm temperature. (Was ministral-3:8b until
        # Mistral's small line was retired from Ollama Cloud 2026-07-15 — the only Mistral left is the 675b
        # large, too heavy/slow for a hot divergent stage. gemma4:31b is the replacement: reliably creative,
        # cheapish, and crucially NON-reasoning — the reasoning models on offer (deepseek-v4-flash,
        # minimax-m2.5) dump everything into a hidden `reasoning` field and return EMPTY content, which is
        # unparseable.) response_format=json_object pins output to valid JSON GRAMMAR at the API level — a hot
        # model otherwise emits malformed JSON (missing commas, keys inside arrays) for the complex map/compose
        # schema, which is UNPARSEABLE so the one repair attempt can't even act on it. JSON mode guarantees
        # parseable output, so any remaining SCHEMA mistake becomes a fixable validation error.
        "brainstorm": {"model": "gemma4:31b", "temperature": 0.9,
                       "response_format": {"type": "json_object"}},
        # strong, schema-faithful model turns the dossier into card briefs; pin to JSON
        "structure": {"model": "glm-5.2", "response_format": {"type": "json_object"}, "temperature": 0.4},
        # GLM codes the cards: strict closed-vocab JSON, low temperature, pinned to a JSON body
        "cards": {"model": "glm-5.2", "response_format": {"type": "json_object"}, "temperature": 0.3},
    },
    # Metered failover (see module docstring). Same model families via OpenRouter, per-token billed;
    # armed only when OPENROUTER_API_KEY is set. Slugs verified live 2026-07-10.
    "fallback": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key": "${OPENROUTER_API_KEY}",
        "models": {
            # matches the primary brainstorm swap (ministral → gemma) so divergent behavior is the same
            # whether or not the quota breaker is tripped. Slug verified live on OpenRouter 2026-07-15.
            "brainstorm": "google/gemma-3-27b-it",
            "structure": "z-ai/glm-5.2",
            "cards": "z-ai/glm-5.2",
        },
        "cooldown_s": 3600,
    },
}

# Process-wide failover breaker. One quota trip diverts every role of every in-flight forge — quota is an
# account-level condition, so probing it per-call would just burn ~30 failed requests per forge.
_BREAKER_LOCK = threading.Lock()
_breaker_until = 0.0  # time.monotonic() deadline; 0 = closed (primary active)
_TRANSPORT_COOLDOWN_S = 300

def _breaker_active() -> bool:
    with _BREAKER_LOCK:
        return time.monotonic() < _breaker_until

def _trip_breaker(seconds: float, reason: str) -> None:
    global _breaker_until
    with _BREAKER_LOCK:
        deadline = time.monotonic() + seconds
        if deadline > _breaker_until:
            _breaker_until = deadline
            _log.warning("ollama primary tripped (%s) — routing to metered fallback for %ds", reason, seconds)

def _reset_breaker() -> None:
    """Test hook / manual override: close the breaker so the next call tries the primary again."""
    global _breaker_until
    with _BREAKER_LOCK:
        _breaker_until = 0.0


class _FailoverGenerator:
    """Same duck-typed surface the pipelines consume (`.model`, `first_attempt`, `repair`), wrapping a
    primary (plan-based Ollama Cloud) and a fallback (metered) OpenAICompatGenerator built from the SAME
    contract/params — so a failed-over call is byte-identical except for endpoint + model slug. `repair`
    carries plain chat messages, so a conversation started on the primary repairs fine on the fallback."""

    def __init__(self, primary: OpenAICompatGenerator, fallback: OpenAICompatGenerator,
                 cooldown_s: int) -> None:
        self._primary = primary
        self._fallback = fallback
        self._cooldown_s = cooldown_s

    @property
    def model(self) -> str:  # quarantine reports name the model that actually answered
        return self._fallback.model if _breaker_active() else self._primary.model

    def _call(self, method: str, *args):
        if _breaker_active():
            return getattr(self._fallback, method)(*args)
        try:
            return getattr(self._primary, method)(*args)
        except EndpointHTTPError as e:
            if e.code not in (402, 429):  # a 401/403/5xx-with-body is misconfig or a real fault — stay loud
                raise
            _trip_breaker(self._cooldown_s, f"HTTP {e.code} from {self._primary.base_url}")
        except RuntimeError as e:
            # transport-shaped failures already got one in-place retry inside the primary; anything else
            # (unexpected response shape, …) is not the endpoint's availability and must surface.
            msg = str(e)
            if not any(s in msg for s in ("could not reach", "sent no data", "dropped mid-response")):
                raise
            _trip_breaker(_TRANSPORT_COOLDOWN_S, f"transport: {msg[:120]}")
        return getattr(self._fallback, method)(*args)

    def first_attempt(self, brief):
        return self._call("first_attempt", brief)

    def repair(self, messages, prev_text, errors):
        return self._call("repair", messages, prev_text, errors)

# Which role each call's contract belongs to (resolved by class name so we never import-couple to instances).
_BRAINSTORM_CONTRACTS = frozenset({"_CloudClusterContract", "_RelicIntentContract"})
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
    load_env()  # so ${OLLAMA_API_KEY} (in generation/.env) is visible
    defaults = role_map.get("defaults", {})
    base_default = _expand(defaults.get("base_url", CLOUD_BASE_URL))
    key_default = _expand(defaults.get("api_key", "${OLLAMA_API_KEY}"))
    cap = role_map.get("max_tokens_cap")
    # Calls stream, so the read timeout bounds silence-between-chunks, not total generation — but big cloud
    # models under load can stall long before the first chunk. Keep the Ollama path's default generous
    # (vs the generator's 180s); let a role override per model.
    timeout_default = int(role_map.get("timeout", 300))

    roles: dict = {}
    for name, spec in (role_map.get("roles") or {}).items():
        if name.startswith("_"):  # "_brainstorm_comment"-style annotation keys (see the example JSONs)
            continue
        s = dict(spec)
        s["base_url"] = _expand(s.get("base_url", base_default))
        s["api_key"] = _expand(s.get("api_key", key_default))
        if not s.get("model"):
            raise RuntimeError(f"ollama role '{name}' is missing a 'model'.")
        if not s["api_key"]:
            raise RuntimeError(
                f"ollama role '{name}' has no API key. Set OLLAMA_API_KEY in generation/.env "
                "(or give the role an explicit api_key)."
            )
        s["timeout"] = int(s.get("timeout", timeout_default))
        roles[name] = s

    if not roles:
        raise RuntimeError("ollama role map has no roles.")
    # Backfill the three roles the forge needs from whatever is present.
    for need in ("cards", "structure", "brainstorm"):
        if need not in roles:
            donor = roles.get("cards") or roles.get("structure") or next(iter(roles.values()))
            roles[need] = dict(donor)
    return {"roles": roles, "max_tokens_cap": cap,
            "fallback": _normalize_fallback(role_map.get("fallback", DEFAULT_ROLE_MAP["fallback"]))}


def _normalize_fallback(fb: dict | None) -> dict | None:
    """Expand + validate the metered-failover block; None (disarmed) unless its api_key resolves. A custom
    role map without a `fallback` key inherits the built-in OpenRouter one — still inert without the env
    var — while an explicit `"fallback": null` opts out entirely."""
    if not fb:
        return None
    api_key = _expand(fb.get("api_key", "${OPENROUTER_API_KEY}"))
    if not api_key:
        return None
    models = dict(fb.get("models") or DEFAULT_ROLE_MAP["fallback"]["models"])
    for need in ("cards", "structure", "brainstorm"):
        if not models.get(need):
            models[need] = models.get("cards") or models.get("structure") or next(iter(models.values()))
    return {"base_url": _expand(fb.get("base_url", "https://openrouter.ai/api/v1")),
            "api_key": api_key, "models": models, "cooldown_s": int(fb.get("cooldown_s", 3600))}


def build_ollama_mix(role_map: dict | None = None, *, on_usage=None):
    """role_map -> (blueprint_gen, card_gen_factory, relic_gen, make_gen). Mirrors the tuple the existing
    forge paths consume; each role gets its own model/endpoint via OpenAICompatGenerator. `on_usage` (optional)
    is a callback(usage_dict) attached to every generator for cost/telemetry (used by the A/B harness)."""
    cfg = _normalize(role_map or DEFAULT_ROLE_MAP)
    cap = cfg["max_tokens_cap"]
    fb = cfg["fallback"]

    def _gen(role: str, contract_mod, max_tokens: int):
        spec = cfg["roles"][role]
        eff = min(max_tokens, int(spec.get("max_tokens_cap", cap))) if (spec.get("max_tokens_cap") or cap) else max_tokens
        # Reasoning models (kimi-k3, …) bill hidden thinking against max_tokens BEFORE any visible content,
        # so a small stage budget (relic-intent asks for 2000) truncates the answer to nothing. A role
        # serving such a model can set a floor; applied after the cap so the floor wins when both are set.
        if spec.get("max_tokens_floor"):
            eff = max(eff, int(spec["max_tokens_floor"]))
        primary = OpenAICompatGenerator(
            spec["base_url"], spec["api_key"], spec["model"],
            contract_mod=contract_mod, max_tokens=eff, timeout=spec["timeout"],
            response_format=spec.get("response_format"),
            temperature=spec.get("temperature"),
            on_usage=on_usage,
        )
        if not fb:
            return primary
        # The fallback twin differs ONLY in endpoint + model slug — same contract, JSON pin, temperature,
        # token budget and timeout — so a failed-over call exercises the identical harness.
        fallback = OpenAICompatGenerator(
            fb["base_url"], fb["api_key"], fb["models"][role],
            contract_mod=contract_mod, max_tokens=eff, timeout=spec["timeout"],
            response_format=spec.get("response_format"),
            temperature=spec.get("temperature"),
            on_usage=on_usage,
        )
        return _FailoverGenerator(primary, fallback, fb["cooldown_s"])

    # One-shot blueprint generator (only used when the staged front-end is OFF) + relic generator.
    blueprint_gen = _gen("structure", _BlueprintContract(), 24000)
    relic_gen = _gen("cards", _RelicContract(), 4000)
    card_gen_factory = lambda: _gen("cards", _card_contract, 4000)  # noqa: E731
    make_gen = lambda contract_mod, *, max_tokens: _gen(  # noqa: E731
        _resolve_role(contract_mod), contract_mod, max_tokens)
    return blueprint_gen, card_gen_factory, relic_gen, make_gen


def load_role_map(path: str | os.PathLike) -> dict:
    """Read a role map from a JSON file (see ollama_roles.example.json)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def describe(role_map: dict | None = None) -> str:
    """One-line-per-role summary for the CLI banner (no secrets — just role -> model @ host)."""
    cfg = _normalize(role_map or DEFAULT_ROLE_MAP)
    lines = []
    for role in ("brainstorm", "structure", "cards"):
        s = cfg["roles"][role]
        host = s["base_url"].replace("https://", "").replace("http://", "").split("/")[0]
        extras = []
        if s.get("temperature") is not None:
            extras.append(f"t={s['temperature']}")
        if s.get("response_format"):
            extras.append("json")
        tail = f" ({', '.join(extras)})" if extras else ""
        lines.append(f"  {role:10s} -> {s['model']} @ {host}{tail}")
    fb = cfg["fallback"]
    if fb:
        host = fb["base_url"].replace("https://", "").replace("http://", "").split("/")[0]
        lines.append(f"  fallback   -> {fb['models']['cards']} @ {host} (metered, armed)")
    else:
        lines.append("  fallback   -> not armed (set OPENROUTER_API_KEY for metered failover)")
    return "\n".join(lines)
