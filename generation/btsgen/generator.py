"""The live Anthropic backend: prompt -> a JSON card (as text).

Keeps a running message list so the one repair attempt has full context. Knows nothing
about validation or quarantine — that's the pipeline's job. The engine never touches this.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

import anthropic

from . import contract, paths
from .contract import Brief

DEFAULT_MODEL = "claude-opus-4-8"


def _model_features(model_id: str) -> dict:
    """Which OPTIONAL request params a given model accepts — so one code path 'just works' on any model
    the user picks, instead of 400-ing. Two knobs differ across the lineup:

      - adaptive thinking (`thinking={"type":"adaptive"}`): Fable 5, Opus 4.5+, Sonnet 4.6. NOT Haiku 4.5.
      - effort (`output_config.effort`): Fable 5, Opus 4.5+, Sonnet 4.6. NOT Haiku 4.5 / Sonnet 4.5.

    Unknown or older model ids fall back to the SAFEST request (send neither), which every Claude model
    accepts — so a model we haven't catalogued still produces a working call (just without those niceties).
    """
    m = (model_id or "").lower()
    if "haiku" in m:
        return {"thinking": False, "effort": False}  # Haiku 4.5 rejects both
    if "fable" in m or "sonnet-4-6" in m or any(
            o in m for o in ("opus-4-5", "opus-4-6", "opus-4-7", "opus-4-8")):
        return {"thinking": True, "effort": True}
    return {"thinking": False, "effort": False}  # safe default — request is always valid


def load_env() -> None:
    """Load generation/.env into os.environ (does not overwrite existing vars)."""
    env = paths.PACKAGE_DIR / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def extract_card_json(text: str) -> dict:
    """Pull a single JSON object out of a model response, tolerating fences/prose.

    Raises ValueError if no JSON object can be parsed (the caller treats this as a
    validation-style failure and may repair once).
    """
    text = text.strip()
    # 1) fenced ```json ... ``` block
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fence.group(1) if fence else None
    # 2) whole response is JSON
    if candidate is None and text.startswith("{"):
        candidate = text
    # 3) first balanced {...} span
    if candidate is None:
        start = text.find("{")
        if start != -1:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start : i + 1]
                        break
    if candidate is None:
        raise ValueError("no JSON object found in model response")
    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ValueError(f"model returned malformed JSON: {e}") from e
    if not isinstance(obj, dict):
        raise ValueError("model returned JSON that is not an object")
    return obj


def _make_gate(contract_mod, system_text: str):
    """The card-prompt gate for this contract, or None (flag off, or a contract that is never gated). A gate
    that fails to build is logged and ignored: the ungated prompt is always a safe answer."""
    fn = getattr(contract_mod, "card_prompt_gate", None)
    if fn is None:
        return None
    try:
        return fn(system_text)
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("vocab gate unavailable: %s", e)
        return None


def _gated_system(gen, brief) -> str | None:
    """The per-brief system prompt when the generator carries a gate (else None = use gen._system), and the
    decision summary on gen.last_gate for the pipeline log. Repairs never come through here: they keep the
    FULL cache-safe layout (gen._system)."""
    gp = getattr(gen, "_gate", None)
    if gp is None:
        gen.last_gate = None
        return None
    from . import gate as _gate_mod
    text = brief.describe() if hasattr(brief, "describe") else str(brief)
    system, decision = gp.for_brief(text, on_usage=getattr(gen, "_on_usage", None))
    gen.last_gate = _gate_mod.summary(decision, gp, system)
    return system


class AnthropicGenerator:
    """Prompt -> a JSON content object (as text). Content-agnostic: the `contract_mod` supplies the
    system prompt + the per-brief user/repair messages, so the SAME backend serves cards (the default
    `contract` module) and relics (`relic_contract`). Both expose system_prompt(), user_brief(brief),
    and repair_message(text, errors)."""

    def __init__(self, model: str | None = None, contract_mod=None, max_tokens: int = 8000,
                 effort: str = "high", on_usage=None, api_key: str | None = None) -> None:
        load_env()
        # Explicit api_key (website BYOK-Anthropic, used once and never persisted) wins over the server
        # env secret (the hosted path). Without either, live generation can't run.
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Put it in generation/.env "
                "(see .env.example) or export it. The validator/tests run without a key; "
                "only live generation needs one."
            )
        self.model = model or os.environ.get("BTSGEN_MODEL", DEFAULT_MODEL)
        self.max_tokens = max_tokens  # blueprint responses (whole-class plans) need far more than a card
        self.effort = effort          # only sent to models that support it (see _model_features)
        self._on_usage = on_usage     # optional callback(resp.usage) for cost/telemetry; library ignores usage otherwise
        self._contract = contract_mod or contract
        self._system = self._contract.system_prompt()
        # Card-stage vocab gate (off by default): the full prompt becomes the cache-safe layout (core + every
        # add-on); first attempts get a per-brief gated prompt sharing the same core prefix.
        self._gate = _make_gate(self._contract, self._system)
        if self._gate is not None:
            self._system = self._gate.full
        self.last_gate: dict | None = None
        self._client = anthropic.Anthropic(api_key=api_key)

    def _system_blocks(self, system: str) -> list[dict]:
        """One cached block, or — under the gate — two breakpoints: after the shared core and at the end of
        the per-card tail (the plan's rule 5), so a gated card and a repair both reuse the core cache."""
        core = self._gate.core if self._gate is not None else ""
        if core and system.startswith(core) and len(system) > len(core):
            return [{"type": "text", "text": core, "cache_control": {"type": "ephemeral"}},
                    {"type": "text", "text": system[len(core):], "cache_control": {"type": "ephemeral"}}]
        return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

    def _complete(self, messages: list[dict], system: str | None = None) -> str:
        feats = _model_features(self.model)
        kwargs: dict = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self._system_blocks(system or self._system),
            messages=messages,
        )
        # Only attach the optional params the chosen model actually accepts (Haiku 4.5 400s on both).
        if feats["thinking"]:
            kwargs["thinking"] = {"type": "adaptive"}
        if feats["effort"]:
            kwargs["output_config"] = {"effort": self.effort}
        # Stream so a thinking-heavy model can't exhaust max_tokens before finishing the JSON (Sonnet did
        # exactly that on the big blueprint), and so large max_tokens doesn't trip the SDK's non-streaming
        # timeout guard. Streaming works uniformly across every model.
        with self._client.messages.stream(**kwargs) as stream:
            msg = stream.get_final_message()
        if self._on_usage is not None and getattr(msg, "usage", None) is not None:
            try:
                self._on_usage(msg.usage)
            except Exception:  # noqa: BLE001 — a telemetry sink must never break generation
                pass
        return "".join(b.text for b in msg.content if b.type == "text")

    def first_attempt(self, brief) -> tuple[str, list[dict]]:
        messages = [{"role": "user", "content": self._contract.user_brief(brief)}]
        text = self._complete(messages, system=_gated_system(self, brief))
        messages.append(_assistant_msg(text))
        return text, messages

    def repair(self, messages: list[dict], prev_text: str, errors: list[str]) -> tuple[str, list[dict]]:
        messages = messages + [{"role": "user", "content": self._contract.repair_message(prev_text, errors)}]
        text = self._complete(messages)
        messages.append(_assistant_msg(text))
        return text, messages


# ---- OpenRouter provider hygiene ------------------------------------------------------------------------
# OpenRouter fans one model slug out over several upstream providers. Some of them answer a JSON-mode request
# with a PLACEHOLDER instead of an answer — `{}` or `{"name":-1,"fantasy":-1,...}` with finish_reason "stop" —
# and, because OpenRouter routes a cached prompt back to the provider holding the cache, the repair and the
# whole-stage re-roll land on the same provider, so one bad upstream kills the whole forge ("blueprint failed:
# missing 'name'; missing 'description'; …", 5 of 8 live forges on 2026-09-24). Provider ModelRun (gemma-4
# fp4) does this on EVERY prompt, vanilla or not (probe 2026-09-24); the glm-5.3 culprit is unidentified.
# Two defenses, both OpenRouter-only (the request field is OpenRouter's `provider.ignore`, which accepts the
# provider name exactly as the response's `provider` field spells it — verified):
#   1. a static block list for upstreams known to do this;
#   2. a stub detector on every reply — the answering provider joins a process-wide, time-limited block list
#      and the call is retried at once, so the retry cannot be routed back to it.
OPENROUTER_HOST = "openrouter.ai"
STATIC_IGNORED_PROVIDERS: tuple[str, ...] = ("ModelRun",)
PROVIDER_IGNORE_TTL_S = 3600  # a stubbing provider is skipped for an hour, then gets another chance
STUB_RETRIES = 2  # per call: how many placeholder answers to re-request before handing the stub back
_IGNORED_LOCK = threading.Lock()
_ignored_providers: dict[str, float] = {}  # provider name -> time.monotonic() deadline
_PLACEHOLDER_SCALARS = (-1, "-1", "", None)


def ignore_provider(name: str, seconds: float = PROVIDER_IGNORE_TTL_S) -> None:
    """Skip OpenRouter upstream `name` on every call from this process for `seconds` (extends, never shortens)."""
    if not name:
        return
    with _IGNORED_LOCK:
        deadline = time.monotonic() + seconds
        if deadline > _ignored_providers.get(name, 0.0):
            _ignored_providers[name] = deadline


def ignored_providers() -> list[str]:
    """The static block list plus every dynamically blocked provider whose deadline has not passed."""
    now = time.monotonic()
    with _IGNORED_LOCK:
        live = [n for n, d in _ignored_providers.items() if d > now]
    return sorted(set(STATIC_IGNORED_PROVIDERS) | set(live))


def _reset_ignored_providers() -> None:
    """Test hook: forget every dynamically blocked provider (the static list stays)."""
    with _IGNORED_LOCK:
        _ignored_providers.clear()


def _is_placeholder(value) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (list, dict)):
        return not value
    return any(value is p or value == p for p in _PLACEHOLDER_SCALARS)


def looks_like_stub(text: str) -> bool:
    """True when a JSON-mode reply is a provider placeholder rather than an answer: `{}`, `[]`, or an object
    whose every value is -1 / "-1" / "" / null / empty. Empty CONTENT is deliberately not a stub — that is the
    reasoning-budget failure `last_meta` already diagnoses, and it is not provider-specific."""
    s = (text or "").strip()
    if not s:
        return False
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        return False
    if isinstance(obj, dict):
        return not obj or all(_is_placeholder(v) for v in obj.values())
    return isinstance(obj, list) and not obj


class EndpointHTTPError(RuntimeError):
    """A non-adaptable HTTP status from an OpenAI-compatible endpoint. Subclasses RuntimeError with the
    same message the forge log always showed, but keeps `.code` so callers can react to the status —
    the ollama_mix failover uses it to tell quota exhaustion (429/402) from a misconfiguration (401)."""

    def __init__(self, code: int, detail: str) -> None:
        super().__init__(f"endpoint returned HTTP {code}: {detail[:400]}")
        self.code = code
        self.detail = detail


def _assistant_msg(text: str) -> dict:
    """A reasoning model that burns its whole token budget thinking returns "" content; some providers
    (Moonshot, Anthropic) then reject the WHOLE repair conversation over the empty assistant turn — keep
    history valid with a placeholder (the validator still sees the real empty `prev_text` separately)."""
    return {"role": "assistant", "content": text if text.strip() else "(empty response)"}


class OpenAICompatGenerator:
    """BYOK backend for ANY OpenAI-compatible Chat Completions endpoint — the website's default path, where
    the user brings their own `base_url` + `api_key` + `model` (OpenAI, OpenRouter, Together, Groq, a local
    llama.cpp/Ollama server, …). Same duck-typed surface as `AnthropicGenerator` (`.model`, `first_attempt`,
    `repair`), so the pipelines don't care which backend they got. Pure stdlib HTTP (no extra deps), so it
    drops cleanly into a serverless function. The contract still carries the schema/vocabulary; the system
    prompt is sent as the leading `system` message."""

    # Newer OpenAI models (o-series, gpt-4.1/gpt-5-era) reject `max_tokens` and require
    # `max_completion_tokens`; older models + most other OpenAI-compatible endpoints only know `max_tokens`.
    # We probe `max_tokens` first and, on that specific 400, switch — remembered per-model across instances
    # (the card pipeline builds a fresh generator per card) so the swap costs at most one rejected call.
    _completion_token_models: set[str] = set()
    # Endpoints that reject the OpenAI-only `stream_options` usage opt-in — same probe-and-remember pattern.
    _no_stream_options_models: set[str] = set()
    # (model, extra_body key) pairs an endpoint has 400'd on — the key is silently omitted from then on.
    _rejected_extra_keys: set[tuple[str, str]] = set()

    def __init__(self, base_url: str, api_key: str, model: str, contract_mod=None,
                 max_tokens: int = 4000, timeout: int = 180,
                 response_format: dict | None = None, temperature: float | None = None,
                 on_usage=None, extra_body: dict | None = None) -> None:
        if not (base_url and api_key and model):
            raise RuntimeError("OpenAI-compatible backend needs base_url, api_key, and model.")
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout
        # Optional, default-off so the BYOK path is byte-for-byte unchanged. Open models (Ollama, etc.) are
        # weaker than Claude at emitting strict closed-vocab JSON; `response_format={"type":"json_object"}`
        # pins them to a JSON body (cuts validator/repair churn). `temperature` lets a role tune divergence
        # (higher for brainstorm, low for cards). Both are forwarded only when set — endpoints that don't
        # know them never see them.
        self._response_format = response_format
        self._temperature = temperature
        self._on_usage = on_usage  # optional callback(usage_dict) for cost/telemetry; ignored otherwise
        # Verbatim extra request fields (e.g. {"reasoning_effort": "none"} — hybrid-reasoning models like
        # glm-5.2 otherwise burn 10-20k tokens of HIDDEN thinking against max_tokens before any content,
        # truncating big responses mid-JSON). Keys an endpoint 400s on are dropped per-model (see
        # `_adapt_params`), so a stricter fallback endpoint degrades gracefully instead of failing the call.
        self._extra_body = dict(extra_body) if extra_body else {}
        # Providers THIS generator must not use, on top of the process-wide list (see `ignore_provider`):
        # a stage re-roll adds the upstream whose answer just failed validation so the fresh sample escapes
        # OpenRouter's prompt-cache affinity instead of being routed straight back to it.
        self.avoid_providers: set[str] = set()
        self._contract = contract_mod or contract
        self._system = self._contract.system_prompt()
        self._gate = _make_gate(self._contract, self._system)  # card-stage vocab gate; None = off (see gate.py)
        if self._gate is not None:
            self._system = self._gate.full
        self.last_gate: dict | None = None
        self._token_param = ("max_completion_tokens"
                             if model in OpenAICompatGenerator._completion_token_models else "max_tokens")
        # Diagnostics from the LAST completed call: {"finish_reason", "content_chars", "reasoning_chars"}.
        # Callers use this to explain an unparseable response (truncated by max_tokens vs reasoning-only).
        self.last_meta: dict = {}

    def _is_openrouter(self) -> bool:
        return OPENROUTER_HOST in self.base_url

    @property
    def api_key(self) -> str:
        """The key this generator authenticates with (the hosted router's quota gate polls Ollama with it)."""
        return self._api_key

    def avoid_provider(self, name: str | None) -> None:
        """Keep `name` out of this generator's remaining calls (no-op off OpenRouter, or when unknown)."""
        if name and self._is_openrouter():
            self.avoid_providers.add(name)

    def _provider_field(self, payload: dict) -> None:
        """Merge the block lists into OpenRouter's `provider` request field (any static `provider` config from
        extra_body — routing order, quantization, … — is kept and only its `ignore` list is extended)."""
        if not self._is_openrouter():
            return
        block = set(ignored_providers()) | self.avoid_providers
        base = payload.get("provider") if isinstance(payload.get("provider"), dict) else {}
        block |= {str(n) for n in (base.get("ignore") or [])}
        if block:
            payload["provider"] = {**base, "ignore": sorted(block)}

    def _wants_usage_chunk(self) -> bool:
        """Whether to request the streamed usage chunk. `stream_options` is an OpenAI-only opt-in; once an
        endpoint 400s on it we remember per-model and stop sending it (usage just goes unreported there)."""
        return self._on_usage is not None and self.model not in OpenAICompatGenerator._no_stream_options_models

    def _post(self, payload: dict) -> dict:
        """POST /chat/completions STREAMED, reassembled into the non-streamed response shape.

        Streaming is what makes the read timeout sane: non-streamed, the server sends NOTHING until the
        whole completion is generated, so `timeout` bounds TOTAL generation time and a slow model dies
        with 'The read operation timed out' (this killed live forges at the map stage). Streamed, chunks
        arrive as they are generated and `timeout` only bounds the silence between chunks — a genuine
        stall. An endpoint that ignores `stream` (or a proxy that buffers it into one JSON body) is
        detected by Content-Type and parsed as-is."""
        payload = {**payload, "stream": True}
        if self._wants_usage_chunk():
            payload["stream_options"] = {"include_usage": True}
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body, method="POST",
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json",
                     "Accept": "text/event-stream"},
        )
        parts: list[str] = []
        usage: dict | None = None
        reasoning_chars = 0
        finish_reason: str | None = None
        provider: str | None = None  # OpenRouter names the upstream that served the call (per chunk)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            if "text/event-stream" not in (resp.headers.get("Content-Type") or ""):
                data = json.loads(resp.read().decode("utf-8"))
                try:
                    msg = data["choices"][0]
                    self.last_meta = {"finish_reason": msg.get("finish_reason"),
                                      "content_chars": len(msg["message"].get("content") or ""),
                                      "reasoning_chars": 0, "provider": data.get("provider")}
                except (KeyError, IndexError, TypeError):
                    self.last_meta = {}
                return data
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue  # SSE comments / event: lines / keep-alive blanks
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue  # a torn or vendor-specific line must never kill the call
                if not isinstance(chunk, dict):
                    continue
                if isinstance(chunk.get("usage"), dict):
                    usage = chunk["usage"]
                if isinstance(chunk.get("provider"), str):
                    provider = chunk["provider"]
                for choice in chunk.get("choices") or []:
                    delta = (choice or {}).get("delta") or {}
                    piece = delta.get("content")
                    if isinstance(piece, str):
                        parts.append(piece)
                    # Hidden thinking from hybrid-reasoning models (glm-5.2, kimi-k3, deepseek…). We never
                    # parse it, but its VOLUME is the diagnostic: it bills against max_tokens before any
                    # content, so heavy thinking + finish_reason "length" = the answer was truncated.
                    for k in ("reasoning", "reasoning_content", "thinking"):
                        if isinstance(delta.get(k), str):
                            reasoning_chars += len(delta[k])
                    if (choice or {}).get("finish_reason"):
                        finish_reason = choice["finish_reason"]
        self.last_meta = {"finish_reason": finish_reason, "content_chars": len("".join(parts)),
                          "reasoning_chars": reasoning_chars, "provider": provider}
        return {"choices": [{"message": {"content": "".join(parts)}}], "usage": usage}

    def _post_with_retry(self, payload: dict) -> dict:
        """One retry on a transient transport failure (read timeout, dropped connection, unreachable). A
        single provider blip on one of a forge's ~30 calls used to abort the whole class; a second attempt
        usually just works. HTTP status errors pass through untouched — `_complete` adapts request params
        on a 400, and anything else is not transient."""
        try:
            return self._post(payload)
        except urllib.error.HTTPError:
            raise
        except (TimeoutError, ConnectionError, urllib.error.URLError):
            return self._post(payload)

    def _post_translated(self, payload: dict) -> dict:
        """`_post_with_retry` with transport failures translated to actionable RuntimeErrors (these surface
        verbatim in the forge log). HTTPError passes through raw so `_complete` can read the 400 detail."""
        try:
            return self._post_with_retry(payload)
        except urllib.error.HTTPError:
            raise
        except TimeoutError as e:
            raise RuntimeError(
                f"endpoint sent no data for {self.timeout}s (tried twice) — "
                "the model or provider is likely overloaded; try again") from e
        except ConnectionError as e:
            raise RuntimeError(f"connection to {self.base_url} dropped mid-response: {e}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"could not reach endpoint {self.base_url}: {e.reason}") from e

    def _adapt_params(self, code: int, detail: str, payload: dict) -> bool:
        """Adapt the request (in place) to a 400 from a stricter endpoint; True means retry once. Two knobs
        vary across OpenAI-compatible endpoints — the max-tokens parameter name and `stream_options` — and
        both are remembered per-model across instances so each swap costs at most one rejected call."""
        if code != 400:
            return False
        adapted = False
        if self._token_param == "max_tokens" and "max_completion_tokens" in detail:
            # adapt to the newer parameter name (o-series / gpt-5-era OpenAI models)
            self._token_param = "max_completion_tokens"
            OpenAICompatGenerator._completion_token_models.add(self.model)
            payload.pop("max_tokens", None)
            payload["max_completion_tokens"] = self.max_tokens
            adapted = True
        if "stream_options" in detail and self._wants_usage_chunk():
            OpenAICompatGenerator._no_stream_options_models.add(self.model)
            adapted = True
        # An endpoint that rejects one of our extra_body fields by name (e.g. a fallback provider that
        # doesn't know `reasoning_effort`): drop that field, remember per-model, retry without it.
        for key in list(self._extra_body):
            if key in detail and key in payload:
                OpenAICompatGenerator._rejected_extra_keys.add((self.model, key))
                payload.pop(key, None)
                adapted = True
        return adapted

    def _complete(self, messages: list[dict], system: str | None = None) -> str:
        payload = {
            "model": self.model,
            self._token_param: self.max_tokens,
            "messages": [{"role": "system", "content": system or self._system}, *messages],
        }
        if self._response_format is not None:
            payload["response_format"] = self._response_format
        if self._temperature is not None:
            payload["temperature"] = self._temperature
        for key, value in self._extra_body.items():
            if (self.model, key) not in OpenAICompatGenerator._rejected_extra_keys:
                payload[key] = value
        stubs: list[str] = []  # providers that answered THIS call with a placeholder (see looks_like_stub)
        while True:
            self._provider_field(payload)
            text = self._complete_once(payload)
            if not (self._is_openrouter() and looks_like_stub(text)):
                break
            bad = self.last_meta.get("provider")
            stubs.append(bad or "?")
            if bad:
                ignore_provider(bad)
            if len(stubs) > STUB_RETRIES:
                break  # hand the stub back; the pipeline's repair/re-roll machinery takes it from here
        if stubs:
            self.last_meta = {**self.last_meta, "stubs": stubs}
        return text

    def _complete_once(self, payload: dict) -> str:
        """One request (plus the single param-adaptation retry on a 400); `payload` is adapted in place."""
        try:
            data = self._post_translated(payload)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            if not self._adapt_params(e.code, detail, payload):
                raise EndpointHTTPError(e.code, detail) from e
            try:
                data = self._post_translated(payload)
            except urllib.error.HTTPError as e2:
                raise EndpointHTTPError(e2.code, e2.read().decode("utf-8", "replace")) from e2
        if self._on_usage is not None and isinstance(data.get("usage"), dict):
            try:
                self._on_usage(data["usage"])
            except Exception:  # noqa: BLE001 — a telemetry sink must never break generation
                pass
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"unexpected response from endpoint: {str(data)[:400]}") from e

    def first_attempt(self, brief) -> tuple[str, list[dict]]:
        messages = [{"role": "user", "content": self._contract.user_brief(brief)}]
        text = self._complete(messages, system=_gated_system(self, brief))
        messages.append(_assistant_msg(text))
        return text, messages

    def repair(self, messages: list[dict], prev_text: str, errors: list[str]) -> tuple[str, list[dict]]:
        messages = messages + [{"role": "user", "content": self._contract.repair_message(prev_text, errors)}]
        text = self._complete(messages)
        messages.append(_assistant_msg(text))
        return text, messages
