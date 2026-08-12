"""Thin web-facing wrapper over btsgen's class forge (single source of truth).

`forge_to_bundle()` mirrors `cli_forge_class.main` exactly — same generators (Anthropic hosted /
OpenAI-compatible BYOK / offline fake), same `forge_class` orchestration, same `encode_class` codec — but
returns the result in memory (for persistence + the HTTP response) and streams progress through `on_event`.

BYOK keys are used once, here, and never persisted or logged. The only disk writes are btsgen's scratch
card files (overwritten each run), pointed at the mod contract by `point_btsgen_at_mod_contract()`.
"""
from __future__ import annotations

import contextlib
import datetime
import json
import os
from pathlib import Path

# btsgen is installed non-editable on the droplet (`pip install ./generation`), so its own repo-root
# guess (`parents[2]`) lands inside the venv, not the repo — and the mod contract (mod/contract/) can't
# be found. We DO know the real repo root from this file's location (web/ -> repo), so hand it to btsgen
# via BTS_REPO_ROOT before importing it. setdefault: an explicit env (or editable install) still wins.
_REPO_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("BTS_REPO_ROOT", str(_REPO_ROOT))

# Wire the player-feedback loop CLOSED on the server (paths.py reads these at import, so set them
# before any btsgen import):
#   BTSGEN_FEEDBACK_FILE   the curated git-tracked log, read from the repo checkout (the non-editable
#                          site-packages install has no feedback/ dir, so btsgen's default is empty);
#   BTSGEN_FEEDBACK_EXTRA  the website's own live append-only rating log (see CARD_FEEDBACK_LOG below)
#                          — feedback_store unions + de-dupes both, so a rating filed on the site
#                          steers the NEXT forge with no manual pull-into-git step.
os.environ.setdefault("BTSGEN_FEEDBACK_FILE",
                      str(_REPO_ROOT / "generation" / "feedback" / "card_feedback.jsonl"))
os.environ.setdefault("BTSGEN_FEEDBACK_EXTRA",
                      os.environ.get("BTSWEB_CARD_FEEDBACK_LOG",
                                     str(Path(__file__).resolve().parent / "card_feedback.jsonl")))

# MUST run before any btsgen module reads paths at import time — repoints the card schema/vocab/statuses
# at the constrained vocab-v2 mod contract. (Same call cli_forge_class makes at the top of main().)
from btsgen.class_forge import (ClassBrief, _BlueprintContract, _CardFake, _RelicContract, forge_class,
                                point_btsgen_at_mod_contract)

point_btsgen_at_mod_contract()


class ForgeError(RuntimeError):
    """Generation could not start or did not produce a class (bad key, endpoint down, empty result)."""


def _guard_outbound_url(base_url: str) -> None:
    """SSRF guard for user-supplied BYOK endpoints: http(s) only, and the host must not resolve to a
    loopback/private/link-local address — blocks the cloud metadata service (169.254.169.254) and the
    droplet's own services. Checks every resolved address; resolution happens again at request time, so
    this is a strong filter, not an airtight DNS-rebinding defense. Set BTSWEB_ALLOW_PRIVATE_URLS=1 in
    local dev, where pointing BYOK at a localhost Ollama is legitimate."""
    import ipaddress
    import socket
    from urllib.parse import urlparse

    parsed = urlparse((base_url or "").strip())
    if parsed.scheme not in ("http", "https"):
        raise ForgeError("base URL must start with http:// or https://.")
    if not parsed.hostname:
        raise ForgeError("base URL needs a hostname.")
    if os.environ.get("BTSWEB_ALLOW_PRIVATE_URLS", "").strip() in ("1", "true", "yes"):
        return
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(parsed.hostname, port, proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise ForgeError(f"could not resolve {parsed.hostname}.") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ForgeError("base URL points at a private or internal address — "
                             "use a public provider endpoint.")


def _build_generators(key: dict | None, hosted: bool, fake: bool, model: str | None = None):
    """Return (blueprint_gen, card_gen_factory, relic_gen) for the requested path. Raises ForgeError on bad
    config. `relic_gen` forges the class's keystone relic (non-fatal — if it fails, the class still ships,
    just without a custom relic); it mirrors the CLI's wiring so the website forges relics too.

    `model` (hosted path only) lets the website user pick which Anthropic model to call; the generator is
    model-aware (drops params a model doesn't accept) so any choice produces working calls. None = default.
    """
    if fake:
        return None, (lambda: _CardFake()), None  # forge_class emits a _fake_relic offline (no relic_gen)

    if key and key.get("provider") == "anthropic":  # BYOK — the user's own Anthropic key
        api_key, model = key.get("api_key"), key.get("model")
        if not (api_key and model):
            raise ForgeError("Anthropic BYOK needs api_key and model together.")
        from btsgen.generator import AnthropicGenerator
        # 48000 leaves headroom for adaptive thinking + re-emitting the whole blueprint on repair, which share
        # one max_tokens budget; truncation there → unparseable JSON. Safe: Haiku 4.5 / Sonnet 4.6 cap output
        # at 64K, Opus 4.8 at 128K. (Streamed, so the SDK's large-max_tokens timeout guard is moot.)
        try:
            blueprint_gen = AnthropicGenerator(model=model, api_key=api_key,
                                               contract_mod=_BlueprintContract(), max_tokens=48000)
        except RuntimeError as e:
            raise ForgeError(f"Anthropic generation unavailable: {e}") from e
        relic_gen = AnthropicGenerator(model=model, api_key=api_key,
                                       contract_mod=_RelicContract(), max_tokens=6000)
        return blueprint_gen, (lambda: AnthropicGenerator(model=model, api_key=api_key)), relic_gen

    if key:  # BYOK — any OpenAI-compatible /chat/completions endpoint
        base_url, api_key, model = key.get("base_url"), key.get("api_key"), key.get("model")
        if not (base_url and api_key and model):
            raise ForgeError("BYOK needs base_url, api_key, and model together.")
        from btsgen import contract
        from btsgen.generator import OpenAICompatGenerator
        blueprint_gen = OpenAICompatGenerator(base_url, api_key, model,
                                              contract_mod=_BlueprintContract(), max_tokens=8000)
        relic_gen = OpenAICompatGenerator(base_url, api_key, model,
                                          contract_mod=_RelicContract(), max_tokens=4000)
        card_factory = lambda: OpenAICompatGenerator(base_url, api_key, model,  # noqa: E731
                                                     contract_mod=contract, max_tokens=4000)
        return blueprint_gen, card_factory, relic_gen

    if hosted:  # our Anthropic key (server-side secret, never sent to the browser)
        from btsgen.generator import AnthropicGenerator
        # 48000: headroom for adaptive thinking + full-blueprint repair (shared budget; truncation → unparseable
        # JSON). Safe under every hosted model's output cap (Haiku 4.5 / Sonnet 4.6 = 64K, Opus 4.8 = 128K).
        try:
            blueprint_gen = AnthropicGenerator(model=model, contract_mod=_BlueprintContract(), max_tokens=48000)
        except RuntimeError as e:
            raise ForgeError(f"hosted generation unavailable: {e}") from e
        relic_gen = AnthropicGenerator(model=model, contract_mod=_RelicContract(), max_tokens=6000)
        return blueprint_gen, (lambda: AnthropicGenerator(model=model)), relic_gen

    raise ForgeError("no generation path selected (need a BYOK key, the hosted option, or fake).")


# Server-side off-vocab gap capture. The staged front-end surfaces mechanics the theme wants but the engine
# can't express; we record them HERE (an append-only JSONL log), NOT in the git-tracked VOCABULARY_GAPS.md —
# a server write to that tracked file would dirty it and block deploy.sh's `git pull --ff-only`. This side log
# is untracked and survives deploys; review it periodically (`tail` / scp down) and fold the good gaps into
# VOCABULARY_GAPS.md in git. Path overridable via BTSWEB_GAP_LOG; defaults next to the app (web/captured_gaps.jsonl).
GAP_LOG = Path(os.environ.get("BTSWEB_GAP_LOG", str(Path(__file__).resolve().parent / "captured_gaps.jsonl")))


def _append_captured_gaps(entries: list[dict]) -> int:
    """Append surfaced off-vocab gaps to the server-side JSONL log. Returns the count written. Never raises —
    a gap-capture failure must never break a forge."""
    if not entries:
        return 0
    try:
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        GAP_LOG.parent.mkdir(parents=True, exist_ok=True)
        with GAP_LOG.open("a", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps({"ts": ts, "title": e.get("title", ""),
                                    "surfaced_by": e.get("surfaced_by", ""),
                                    "fantasy": e.get("fantasy", ""), "sketch": e.get("sketch", "")},
                                   ensure_ascii=False) + "\n")
        return len(entries)
    except OSError:
        return 0


# Per-card player feedback (the website's per-card feedback buttons append here). Written in the EXACT
# shape btsgen.contract.feedback_section() reads back as few-shot examples / anti-examples, so a periodic
# pull of this log into generation/btsgen/feedback/card_feedback.jsonl feeds the refinement loop with no
# generator changes. Untracked side log like GAP_LOG above; review/pull periodically. Path overridable via
# BTSWEB_CARD_FEEDBACK_LOG; defaults next to the app (web/card_feedback.jsonl).
CARD_FEEDBACK_LOG = Path(os.environ.get(
    "BTSWEB_CARD_FEEDBACK_LOG", str(Path(__file__).resolve().parent / "card_feedback.jsonl")))

# Canonical feedback categories — the single source of truth lives in the generator's prompt builder, so
# import it rather than re-typing the set (keeps web and generator from drifting). 'great' is the positive
# rating; the rest are flags (anti-examples). See btsgen.contract.feedback_section / _FEEDBACK_LABELS.
from btsgen.contract import _FEEDBACK_LABELS  # noqa: E402

VALID_FEEDBACK_CATEGORIES = frozenset(_FEEDBACK_LABELS) | {"great"}


def append_card_feedback(*, category: str, card: dict, character: str, note: str = "") -> bool:
    """Append one per-card rating to the server-side JSONL log. Returns True on write. Never raises — a
    feedback-logging failure must never break the request. Fields match feedback_section()'s reader."""
    try:
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        CARD_FEEDBACK_LOG.parent.mkdir(parents=True, exist_ok=True)
        with CARD_FEEDBACK_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": ts,
                "category": category,
                "card_id": card.get("id", ""),
                "name": card.get("name", ""),
                "character": character,
                "card": card,
                "note": note,
            }, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


# Player feedback on a class's NON-card forged elements — custom orbs, custom statuses, the summon, and the
# keystone relic. These are the mechanics the website now describes in a popout (they carry no card text), so
# players can rate them too. We write them to the SAME log in a card-shaped record (synthetic effects + a
# `card_id` like "orb:ember") so btsgen.contract.feedback_section() folds them into the prompt with zero
# generator changes; the extra `element_kind` field flags them for any kind-aware tooling later.
ELEMENT_KINDS = frozenset({"orb", "status", "summon", "relic"})


def _element_effects_summary(element_kind: str, element: dict) -> list[dict]:
    """Best-effort flattening of an element's mechanical effects into a card-style effects list, so the
    feedback fold-in has something concrete to show. Statuses/summons carry their meaning in `description`
    (no effect arrays), so they summarize to []; the name + category + player note still convey the signal."""
    if element_kind == "orb":
        return list(element.get("passive") or []) + list(element.get("evoke") or [])
    if element_kind == "relic":
        effs = [e for h in (element.get("hooks") or []) for e in (h.get("effects") or [])]
        effs += [{"op": "modifier", "stat": m.get("stat"), "amount": m.get("amount")}
                 for m in (element.get("modifiers") or [])]
        return effs
    return []


def append_element_feedback(*, category: str, element_kind: str, element: dict, character: str,
                            note: str = "") -> bool:
    """Append one rating on a forged orb/status/summon/relic to the same JSONL log. Returns True on write.
    Never raises — a feedback-logging failure must never break the request."""
    try:
        name = str(element.get("name") or element_kind).strip()
        slug = "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_") or element_kind
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        CARD_FEEDBACK_LOG.parent.mkdir(parents=True, exist_ok=True)
        with CARD_FEEDBACK_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": ts,
                "category": category,
                "card_id": f"{element_kind}:{slug}",
                "name": name,
                "character": character,
                "element_kind": element_kind,
                "card": {**element, "type": element_kind,
                         "effects": _element_effects_summary(element_kind, element)},
                "note": note,
            }, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def _make_gen_factory(key: dict | None, hosted: bool, fake: bool, model: str | None = None):
    """Return a `make_gen(contract_mod, *, max_tokens)` closure for the selected backend — the staged creative
    front-end uses it to spin up a generator for each stage (same backend, swapped contract). Mirrors
    `_build_generators`' backend selection so BYOK / hosted / fake all work for the front-end too."""
    if fake:
        from btsgen.frontend.fakes import _StageFake
        return lambda contract_mod, *, max_tokens: _StageFake(contract_mod)
    if key and key.get("provider") == "anthropic":
        api_key, m = key.get("api_key"), key.get("model")
        if not (api_key and m):
            raise ForgeError("Anthropic BYOK needs api_key and model together.")
        from btsgen.generator import AnthropicGenerator
        return lambda contract_mod, *, max_tokens: AnthropicGenerator(
            model=m, api_key=api_key, contract_mod=contract_mod, max_tokens=max_tokens)
    if key:
        base_url, api_key, m = key.get("base_url"), key.get("api_key"), key.get("model")
        if not (base_url and api_key and m):
            raise ForgeError("BYOK needs base_url, api_key, and model together.")
        _guard_outbound_url(base_url)
        from btsgen.generator import OpenAICompatGenerator
        # 300s (vs the 180s default), matching the Ollama path: the front-end's heavy stages (map/compose,
        # reframed blueprint) can sit a long time before the first streamed chunk when the provider is loaded.
        return lambda contract_mod, *, max_tokens: OpenAICompatGenerator(
            base_url, api_key, m, contract_mod=contract_mod, max_tokens=max_tokens, timeout=300)
    if hosted:
        from btsgen.generator import AnthropicGenerator
        return lambda contract_mod, *, max_tokens: AnthropicGenerator(
            model=model, contract_mod=contract_mod, max_tokens=max_tokens)
    raise ForgeError("no generation path selected (need a BYOK key, the hosted option, or fake).")


def list_models(base_url: str, api_key: str) -> list[str]:
    """List model ids from any OpenAI-compatible endpoint (`GET {base_url}/models`). Used by the website so a
    BYOK user who doesn't know the model name can pick one. The key is used once, here, and never persisted."""
    import urllib.error
    import urllib.request

    if not (base_url and api_key):
        raise ForgeError("base URL and API key are both required to list models.")
    _guard_outbound_url(base_url)
    url = base_url.rstrip("/") + "/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # Status code only — never reflect the response body (an SSRF read primitive).
        raise ForgeError(f"endpoint returned HTTP {e.code} — check the key, URL, and model access.") from e
    except urllib.error.URLError as e:
        raise ForgeError(f"could not reach the endpoint: {e.reason}") from e
    items = data.get("data") or data.get("models") or (data if isinstance(data, list) else [])
    ids = {m.get("id") or m.get("name") for m in items if isinstance(m, dict)}
    return sorted(i for i in ids if i)


def forge_to_bundle(concept: str, *, key: dict | None = None, hosted: bool = False,
                    fake: bool = False, model: str | None = None, pool_per_archetype: int = 4,
                    staged: bool = True, ollama_mix: bool = False, on_event=None,
                    archetype_checkpoint=None, user_id=None) -> dict:
    """Forge a whole class from `concept`. Returns
    {character, cards, blueprint, code, skipped, log}. Raises ForgeError on failure.

    `user_id` (optional) scopes the cross-forge recency ledger to THIS user: each signed-in user reads/writes
    their own recency window (via btsgen.ledger's per-forge scope), so one player's recent archetypes/ops never
    steer another's forge. None (CLI / anonymous) => the shared global ledger. The scope is thread-local, so
    concurrent forges on different users stay isolated.

    `model` (hosted path) selects which Anthropic model to call (None = default). `staged` (default True) runs
    the staged creative front-end (cloud->cluster->map->compose->relic-intent) instead of the one-shot
    blueprint call — same downstream safety, identical bundle shape. `ollama_mix` (the hosted "Use a token"
    path) ignores key/hosted/model and runs the server-side Ollama per-role mixture (ministral brainstorm +
    glm-5.2 cards, on OLLAMA_API_KEY). `on_event(str)` (optional) receives each progress line, for SSE.

    `archetype_checkpoint(options, dossier) -> list[archetype_id]` (optional; needs `staged`) switches the
    front-end to INTERACTIVE forge mode: it's called mid-forge with the theme-matched archetypes and blocks
    until the player picks (the app.py bridge waits on the SSE round-trip with a timeout). Empty return =
    the forge decides autonomously.
    """
    concept = (concept or "").strip()
    if not concept:
        raise ForgeError("concept is empty.")

    # Per-user recency ledger: scope every read_window()/record_forge() in this forge to the user's OWN ledger
    # file. ledger_scope uses a thread-local ContextVar (NOT os.environ), so concurrent forges on other users
    # never see this override. user_id None (CLI/anon) => nullcontext => the shared global ledger. Import here
    # to keep btsgen a soft dependency of the wrapper's import time.
    from btsgen import ledger
    _lscope = (ledger.ledger_scope(ledger.ledger_path_for_user(user_id))
               if user_id is not None else contextlib.nullcontext())
    with _lscope:
        brief = ClassBrief(concept=concept, pool_cards_per_archetype=max(2, int(pool_per_archetype)))

        # The token path forges on the server's Ollama mixture: one build_ollama_mix() supplies every generator
        # (blueprint/cards/relic) AND the front-end make_gen, so both legs share the same per-role models.
        front_end = None
        if ollama_mix:
            try:
                from btsgen.ollama_mix import build_ollama_mix
                blueprint_gen, card_factory, relic_gen, make_gen = build_ollama_mix()
            except RuntimeError as e:
                raise ForgeError(f"hosted Ollama generation unavailable: {e}") from e
            if staged:
                from btsgen.frontend import BlueprintBuilder, load_catalog
                front_end = BlueprintBuilder(make_gen, catalog=load_catalog(), on_event=on_event,
                                             auto=True, gap_log_append=_append_captured_gaps,
                                             archetype_checkpoint=archetype_checkpoint)
            res = forge_class(brief, blueprint_gen=blueprint_gen, card_gen_factory=card_factory,
                              relic_gen=relic_gen, fake=False, front_end=front_end, on_event=on_event)
            return _bundle_result(res)

        blueprint_gen, card_factory, relic_gen = _build_generators(key, hosted, fake, model)

        # Opt into the staged creative front-end (autonomous: picks the most distinctive BUILDABLE candidate). The
        # bp it produces is identical in shape, so the card set / safety nets / assembly below are untouched.
        if staged:
            from btsgen.frontend import BlueprintBuilder, load_catalog
            make_gen = _make_gen_factory(key, hosted, fake, model)
            # The website READS the git-managed VOCABULARY_GAPS.md (for buildability) but never WRITES it (a server
            # append would dirty the tracked file and block deploy.sh's `git pull --ff-only`). Live-surfaced gaps go
            # to the SEPARATE untracked side log (_append_captured_gaps) for later human triage into git.
            front_end = BlueprintBuilder(make_gen, catalog=load_catalog(), on_event=on_event,
                                         auto=True, gap_log_append=_append_captured_gaps,
                                         archetype_checkpoint=archetype_checkpoint)

        res = forge_class(brief, blueprint_gen=blueprint_gen, card_gen_factory=card_factory, relic_gen=relic_gen,
                          fake=(fake and front_end is None), front_end=front_end, on_event=on_event)
        return _bundle_result(res)


def _bundle_result(res) -> dict:
    """Turn a forge_class result into the web response dict (encode the BTSC code). Raises ForgeError if the
    class didn't generate. Shared by the Anthropic/BYOK path and the hosted Ollama-mix (token) path."""
    if not res.ok or res.bundle is None:
        tail = res.log[-1] if res.log else "no detail"
        raise ForgeError(f"class did not generate: {tail}")

    from btsgen.bts1 import encode_class
    from btsgen.class_forge import archetype_display
    code = encode_class(json.dumps(res.bundle, separators=(",", ":")))

    return {
        "character": res.bundle["character"],
        "cards": res.bundle["cards"],
        "relic": res.bundle.get("relic"),  # the forged keystone relic, or None if it wasn't generated
        "blueprint": res.blueprint,
        "archetypes": archetype_display(res.blueprint),  # report-only: what the class was built around
        "code": code,
        "skipped": res.skipped,
        "log": res.log,
    }
