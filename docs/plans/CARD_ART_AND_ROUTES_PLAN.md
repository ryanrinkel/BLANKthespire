# CARD ART + ROUTE UPDATE PLAN (2026-09-18)

What we learned from the 2026-09-17/18 A/B runs (memory notes `e2e-route-ab-2026-09-18`,
`card-art-ab-2026-09-18`, `openrouter-image-backend`) and what to change because of it:

1. **LLM route:** OpenRouter `z-ai/glm-5.3` produced the class Ryan liked best (The Sixgun Pyre: 36 cards,
   0 skipped briefs, vs 3 skipped on glm-5.2). Make it the hosted default; fall back from there.
2. **Card art:** `openai/gpt-5-image-mini` at quality `low`, 3:2, via OpenRouter, the whole-class run Ryan
   liked (32/32 ok, $0.0038/card, ~11 s each). Build the infrastructure to generate, deliver, and show it.
3. **Cost truth:** OpenRouter meters real cost per call; our rate table under-counts by 30-45% and the Ollama
   rows are priced at $0. Record metered cost, price art, stop guessing.

Status: PLAN. Nothing below is built. The working tree already holds UNCOMMITTED prerequisites (OpenRouter
image backend, literal-naming prompts, Anthropic hardening). Step 0 lands those first.

---

## Decisions + assumptions (confirm or overrule)

- **"gpt-img-5-low" = `openai/gpt-5-image-mini`, quality `low`, 1536x1024 (3:2), via OpenRouter.** That is
  the exact config of the Jack-in-Iron run. OpenRouter's "gpt-5-image-mini" is OpenAI's `gpt-image-1-mini`;
  the direct-OpenAI call is ~5% cheaper and is the second tier of the art fallback. If you meant the full
  (non-mini) `openai/gpt-5-image`, it is one env value, but it was not A/B'd and costs several times more.
- **Route chain:** OpenRouter glm-5.3 -> OpenRouter glm-5.2 -> Ollama Cloud (gemma4:31b + glm-5.2). The middle
  tier covers a glm-5.3-only outage on the same key; the Ollama tier covers OpenRouter credits/outage while
  Pro credits last. Brainstorm stays on Gemma 4 at every tier (`google/gemma-4-31b-it` on OpenRouter, which
  the E2E legs used; the current fallback map's `gemma-3-27b-it` is stale).
- **Splash + sprite move to OpenRouter too** (one image key, metered cost): splash `openai/gpt-5-image-mini`
  @ low (as in the E2E legs), sprite `openai/gpt-image-2.5-flare` (mini refuses transparent). Prod today runs
  the `openai` backend on the OpenAI key for these.
- **Card art is delivered as ONE zip per class** (`cards.zip`, ~34 x ~150 KB): one URL in the code, one
  download at import. Per-card URLs would mean ~34 synchronous HTTP calls on the game's UI thread at import.
- **No codec/vocab bump.** `card_art_url` is one more optional top-level bundle key, exactly like
  `splash_url`; older mods ignore it. So the usual "mod zip before web deploy" ordering is not forced here,
  but ship the mod first anyway so early importers get art.
- **Anthropic stays BYOK-only** (never a tier, primary or fallback). Unchanged.
- Expected hosted cost per forge after this: LLM ~$0.65 (glm-5.3, metered) + art ~$0.15 (splash $0.004,
  sprite $0.006, ~34 cards x $0.004) = about **$0.80**. glm-5.2 tier about $0.55 total; Ollama tier about
  $0.71 at list.

---

## Step 0: land what is already in the tree (prerequisite, ~30 min)

The uncommitted diff (13 files + 4 new) is the OpenRouter image backend, the literal-naming prompt changes,
and the server-side Anthropic hardening that is ALREADY live on the droplet's `.env`. Commit it as two
commits so steps 1-3 build on committed code:

- `generation/btsgen/art/backends/openrouter.py`, `tests/test_art_openrouter.py`, `styles.py`, `prompt.py`,
  `request.py`, `splash.py`, `enrich.py`, `backends/__init__.py`, `test_art.py`: "art: OpenRouter image backend
  + descriptive STS style + literal concept naming".
- `web/forge.py`, `web/app.py`, `web/tests/test_no_server_anthropic.py`, `class_forge.py`, `stage_map.py`,
  `test_literal_naming.py`, `.env.example`, `SPLASH_ART_PLAN.md`: "web: hosted forges never touch Anthropic;
  real-name naming rules".
- Run both suites first: `cd generation && uv run python -m pytest` (NOT bare `uv run pytest`), and
  `cd web && python -m pytest` (128 pass as of 2026-09-18).

---

## Step 1: LLM route, OpenRouter glm-5.3 primary with tiered fallback

### 1a. Generalize the failover to an ordered tier list (`generation/btsgen/ollama_mix.py`)

Today `_FailoverGenerator(primary, fallback, cooldown_s)` is a fixed pair with ONE process-wide breaker that
trips on 402/429 (1 h) or transport faults (5 min), and the fallback twin inherits the primary role's
`extra_body`. Three things must change:

1. **Tiers, not a pair.** `DEFAULT_ROLE_MAP` becomes:

   ```
   "defaults": {"base_url": "https://openrouter.ai/api/v1", "api_key": "${OPENROUTER_API_KEY}"},
   "roles": {
       "brainstorm": {"model": "google/gemma-4-31b-it", "temperature": 0.9, "response_format": json},
       "structure":  {"model": "z-ai/glm-5.3", "temperature": 0.4, "response_format": json,
                      "extra_body": {"reasoning": {"effort": "low"}, "usage": {"include": true}}},
       "cards":      {"model": "z-ai/glm-5.3", "temperature": 0.3, "response_format": json,
                      "extra_body": {"reasoning": {"effort": "low"}, "usage": {"include": true}}},
   },
   "fallbacks": [
       {"name": "openrouter-glm52", "base_url": openrouter, "api_key": "${OPENROUTER_API_KEY}",
        "models": {"brainstorm": "google/gemma-4-31b-it", "structure": "z-ai/glm-5.2", "cards": "z-ai/glm-5.2"},
        "extra_body": {"reasoning": {"enabled": false}, "usage": {"include": true}}, "cooldown_s": 900},
       {"name": "ollama", "base_url": "https://ollama.com/v1", "api_key": "${OLLAMA_API_KEY}",
        "models": {"brainstorm": "gemma4:31b", "structure": "glm-5.2", "cards": "glm-5.2"},
        "extra_body": {"reasoning_effort": "none"}, "cooldown_s": 3600},
   ]
   ```

   `_normalize_fallback` becomes `_normalize_fallbacks(list)`; a tier whose key expands empty is dropped.
   Keep accepting the singular `fallback` key from the three `generation/ollama_roles.*.json` files (wrap it
   into a one-item list) so `--ollama-config` users are untouched.
2. **Per-tier `extra_body`.** glm-5.3 on OpenRouter 400s on `reasoning:{enabled:false}` ("Reasoning is
   mandatory") and the generator's drop-rejected-key logic cannot catch it (the message names no key), while
   Ollama wants `reasoning_effort:"none"`. So each tier carries its own `extra_body` (tier-level, applied to
   structure+cards; brainstorm gets none) instead of inheriting the primary role's. `_gen()` builds one
   `OpenAICompatGenerator` per tier with the same contract/temperature/json pin/token budget/timeout and
   only endpoint+model+extra_body differing.
3. **Breaker per endpoint + per-call skip.** Keep the process-wide breaker semantics but key the breaker by
   `base_url` (402/429 = account-level, trips every tier on that endpoint for `cooldown_s`; transport
   faults = 5 min). ADD: a 404/408/5xx from a tier (model-level outage, "no endpoints found") skips to the
   next tier for THIS call only, no breaker. Any other HTTP error (401/403/400) stays loud as today.
   `.model` / `.last_meta` report the tier that actually answered.

`HARNESS_V2_TEMPERATURES` (structure 0.6 under `BTS_HARNESS_V2=1`) still applies to the primary roles.
`build_ollama_mix` / `ollama_mix=True` / provider `"hosted"` keep their names (historical; renaming is churn
across web/tests/CLI for no behavior). Update the module docstring and `cli_forge_class.py` / `cli_bench.py`
help text ("DEFAULT: Ollama-Cloud mixture" becomes "hosted mixture, OpenRouter primary").

### 1b. Reasoning budget

glm-5.3 at `effort: low` bills hidden reasoning as output tokens against `max_tokens`. The E2E leg ran clean
under the existing `max_tokens_cap: 24000`; keep it, and keep `generator.py`'s `last_meta.reasoning_chars`
so a truncated stage is diagnosable. Do not add a `max_tokens_floor` unless a stage truncates in the live
check (step 5).

### 1c. Key requirements + failure modes

- `OPENROUTER_API_KEY` is now REQUIRED for the token path. `_normalize` already raises "role has no API key";
  make the message name OPENROUTER_API_KEY. `web/forge.py` wraps it in `ForgeError("hosted Ollama generation
  unavailable: ...")`; reword to "hosted generation unavailable".
- `OLLAMA_API_KEY` unset: the Ollama tier is silently dropped (same as today's disarmed fallback).
- `.env.example`: flip the comments (OPENROUTER primary, OLLAMA = last-resort tier).

### 1d. Tests (`generation/tests/test_ollama_failover.py` + new cases)

Update the pinned expectations: fallback twin `z-ai/glm-5.2` becomes a tier list;
`test_extra_body_reaches_both_twins` becomes per-tier extra_body (primary carries `reasoning.effort=low`,
Ollama tier carries `reasoning_effort=none`); `test_default_roles_disable_glm_thinking` asserts the
OpenRouter tiers never send `reasoning_effort` and the Ollama tier never sends `reasoning`. New: 5xx skips
one tier for one call without tripping; 429 on OpenRouter trips BOTH OpenRouter tiers and lands on Ollama;
the singular `fallback` key still loads.

---

## Step 2: cost ledger, metered cost + art rows (`web/app.py`, `web/forge.py`, `web/models.py`, `web/db.py`)

- `usage:{include:true}` makes OpenRouter return `usage.cost` per call; the generator already hands the raw
  `usage` dict to `on_usage`. `UsageMeter` gains a `cost_usd` accumulator per (role, model);
  `_record_usage` writes it to a new `forge_usage.metered_cost_micros` column (add via the existing
  `_ensure_forge_usage_columns` forward-only pattern). `est_cost_micros` keeps the table estimate; the admin
  stats page prefers metered when present.
- Fix `MODEL_PRICES`: add `z-ai/glm-5.3` (live OpenRouter rate at deploy time), correct `glm-5.2` /
  `gemma4:31b` to Ollama's per-token list (glm-5.2 1.40/4.40/0.26, gemma4 0.14/0.40/0.05 per M) instead
  of 0, and `google/gemma-4-31b-it`.
- **Art rows:** `_generate_art` and the new card-art step return `ImageResult.cost_usd` (metered on
  OpenRouter, advisory on openai). Record one `forge_usage` row per art kind:
  `role="art:splash"|"art:sprite"|"art:cards"`, `model=<image model>`, `calls=n`, `metered_cost_micros`.
  `forge_estimate()` must skip `role LIKE 'art:%'` rows so the BYOK token estimate stays an LLM number.

---

## Step 3: card art generation (`generation/btsgen/art/` + `web/app.py`)

### 3a. Style + prompt (new `art/card.py`, edit `styles.py`, `request.py`)

- `CARD_STYLE = StyleProfile(name="card", size=(1536, 1024), out_format="png", prompt_suffix=<the same
  descriptive STS ink/cel sentence as DEFAULT_STYLE>, negative="text, lettering, watermark, ui, card frame,
  border, logo")`. 1536x1024 snaps to `3:2` in `nearest_ratio`; the OpenAI family rejects 4:3 on OpenRouter.
- `card_prompt(art: ClassArt, card: dict, style)`, the "mechanical prompt" shape from the A/B: lead with the
  card's `name` and `type` (attack / skill / power) as the literal subject, then the card's `description` /
  `flavor` / `pitch` line, then the class look (`_append_concept`, the player's verbatim concept, and
  `_append_theme` flavor/imagery motifs), then "single focal subject filling the frame, no character text",
  then the style suffix. Enrichment (`enrich.py`) stays OFF for cards (34 extra LLM calls for little gain).
- `ImageRequest` gains `kind: str = "splash"` so a backend can pick model/quality per asset kind.

### 3b. Per-kind model + quality knobs (`backends/openrouter.py`, `backends/openai.py`)

Today `BTSGEN_IMAGE_QUALITY` and the model env are shared across splash and sprite. Resolve per `req.kind`:

| kind   | OpenRouter model env (default)                                   | quality env (default)               |
|--------|------------------------------------------------------------------|-------------------------------------|
| splash | `BTSGEN_OPENROUTER_MODEL` (`openai/gpt-5-image-mini`)            | `BTSGEN_IMAGE_QUALITY` (`low`)      |
| sprite | `BTSGEN_OPENROUTER_SPRITE_MODEL` (`openai/gpt-image-2.5-flare`)  | `BTSGEN_IMAGE_SPRITE_QUALITY` (falls back to the splash quality) |
| card   | `BTSGEN_OPENROUTER_CARD_MODEL` (`openai/gpt-5-image-mini`)       | `BTSGEN_IMAGE_CARD_QUALITY` (`low`) |

Same three-way split in `openai.py` (`BTSGEN_IMAGE_CARD_MODEL` default `gpt-image-1-mini`) so direct OpenAI is
a working second route. Splash default changes from Qwen to mini@low, which is what the E2E legs Ryan judged
used; Qwen stays one env flip away.

### 3c. Image fallback chain (`art/splash.py::_forge_asset`)

`BTSGEN_IMAGE_BACKEND` accepts a comma list (`openrouter,openai`); `_forge_asset` tries each available backend
in order and returns the first `ok`. Inside the OpenRouter backend, `BTSGEN_OPENROUTER_CARD_MODELS` (comma
list, default `openai/gpt-5-image-mini@low,black-forest-labs/flux.2-klein-4b`) gives a per-image model
fallback (one transient OpenAI 502 in 105 images in the E2E; FLUX.2 Klein is 3 s, PNG, $0.015, accepts any
ratio). Order per card: mini@low, retry once, FLUX, direct OpenAI mini (if key), no art (the mod shows the
per-type doodle, as today). The PNG-only guard stays (Gemini/Seedream return JPEG).

### 3d. Post-process to the mod's portrait box (new dependency: Pillow)

The mod's portrait slots are 1000x760 big / 250x190 small (about 1.32:1); renders are 3:2. Center-crop to
1.32:1 and resize to 1000x760 with Pillow (add `pillow>=10` to `generation/pyproject.toml` core deps; it also
unlocks JPEG-to-PNG later). Only the big file ships; the game scales it for the small slot (verify in 4c).

### 3e. Orchestration in `web/app.py::_persist_class`

- New `_generate_card_art(class_id, out, bundle)` next to `_generate_art`: builds `ClassArt` once, runs
  `forge_card_art` for every card in `out["cards"]` on a 6-worker pool (IO-bound; the 1 vCPU droplet is
  fine), writes `static/forged/<id>/cards/<card_id>.png`, then zips the successes into
  `static/forged/<id>/cards.zip` (stored, not deflated; PNG is already compressed). Sets
  `bundle["card_art_url"] = _art_url(class_id, "cards", digest)` (extend `_art_url` to allow the `.zip`
  suffix) and returns the digest; `ForgedClass` gets a `card_art_hash` column (same `_ensure_class_columns`
  pattern as `splash_hash`).
- Runs INSIDE the existing persist pool alongside splash/sprite/relic so the returned code already carries
  every URL. Wall-clock: about 34 x 10 s / 6 = 60-90 s on top of the forge; emit SSE progress lines
  ("card art 12/34") through the existing `on_event` so the page does not look hung.
- Guardrails: `BTSWEB_CARD_ART_BUDGET_S` (default 150) and `BTSWEB_CARD_ART_MAX_USD` (default 0.40). When
  either is hit, remaining cards ship without art; partial zips are fine (the mod falls back per card).
  `BTSWEB_CARD_ART=0` disables the step outright. Never raises (same contract as `_generate_art`).
- Card-art rows go to `forge_usage` per Step 2. `detail()` gains `card_art_url` for the class page; the
  share/class page can show a card-art strip later (not in this plan).
- Cleanup: deleting a class already `rmtree`s `static/forged/<id>/`, which covers `cards/` and `cards.zip`.

### 3f. Tests

- `test_art.py` / new `test_card_art.py`: `card_prompt` leads with name+type and ends with the style suffix;
  `nearest_ratio((1536,1024)) == "3:2"`; per-kind model/quality resolution; backend list fallback order;
  crop math (3:2 to 1000x760); the procedural backend produces a valid zip end-to-end with no key.
- Web: `_persist_class` with `BTSGEN_IMAGE_BACKEND=procedural` yields `card_art_url` in the bundle, the
  re-encoded code decodes with `card_art_url`, budget/cost caps stop the loop, `BTSWEB_CARD_ART=0` skips it,
  `forge_estimate` ignores `art:` rows.

---

## Step 4: mod side, fetch, cache, show (`mod/BlankTheSpireCode/`)

### 4a. Fetch + cache (`Cards/Forged/ForgedSplash.cs`)

`TryCacheFromBundle` gains `CacheKey(d, "card_art_url", classSlot, "cards.zip")`, then unpacks with Godot's
`ZipReader` into `user://forged/characters/KK/cards/<card_id>.png` (clear the directory first so a re-import
drops stale art). Raise the HttpClient timeout for this one download (~5 MB) to 60 s. Best-effort like the
others; `DeleteClass` removes the folder.

### 4b. Show it (`Engine/DataCard.cs` + new `Cards/Forged/ForgedCardArt.cs`)

BaseLib's `CustomCardModel` exposes `CustomPortrait => Texture2D?`, checked BEFORE `CustomPortraitPath` by
its Harmony prefixes on `CardModel.Portrait` and `CardModel.PortraitPath`. So:

- `ForgedCardArt.TryGetTexture(classSlot, cardId)`: load `user://.../cards/<id>.png` via
  `Image.LoadPngFromBuffer`, then `ImageTexture.CreateFromImage`, cache per (slot, id) in a static dictionary
  with STRONG refs (the invisible-relic lesson from `ForgedRelicIcon`), and `TakeOverPath` a synthetic
  `res://BlankTheSpire/images/card_portraits/big/forged_KK_<id>_live.png` so the `PortraitPath` prefix's
  `CustomPortrait.ResourcePath` is non-empty.
- `DataCard`: `public override Texture2D? CustomPortrait => ForgedCardArt.TryGetTexture(ClassSlot, Spec.Id)`;
  the existing type-doodle `CustomPortraitPath` / `PortraitPath` overrides stay as the fallback. DataCard needs
  its class slot: card slots are global (`ForgedCards.SpecForSlot`), so add `ForgedCards.ClassSlotFor(cardSlot)`
  (or stamp `ClassSlot` on `CardSpec` at load); the slot-to-class map already exists for pool assignment.
- `Invalidate(classSlot)` on re-import, called from `TryCacheFromBundle` like `ForgedPortrait.Invalidate`.

### 4c. Verify

- Build with `~/.dotnet/dotnet.exe`; stage in tester slot 04; AutoSlay smoke (gate on godot.log tags + 0 mod
  exceptions; the map-nav FAIL verdict is expected). Add a `[ForgedCardArt]` log line per class ("N/M card
  portraits live").
- Eyeball one hand in-game: big portrait on the zoomed card, small portrait in hand/pile views (confirms the
  single-file decision in 3d), reward screen, and a class with a PARTIAL zip (doodle fallback per card).
- Bump the mod to v0.2.2; release zip + Workshop item 3803255976 update.

---

## Step 5: rollout (droplet)

1. Ship the mod first (4c). Not codec-forced, just so early importers get art.
2. `ssh blankdroplet`, edit `/opt/btsweb/web/.env` (back it up to `_backups/` first, like the Anthropic edit):
   - confirm `OPENROUTER_API_KEY` is present (it armed the old failover); confirm `OLLAMA_API_KEY` stays.
   - `BTSGEN_IMAGE_BACKEND=openrouter,openai`, `BTSGEN_IMAGE_QUALITY=low`,
     `BTSGEN_OPENROUTER_MODEL=openai/gpt-5-image-mini`, `BTSGEN_OPENROUTER_SPRITE_MODEL=openai/gpt-image-2.5-flare`,
     `BTSGEN_OPENROUTER_CARD_MODEL=openai/gpt-5-image-mini`, `BTSGEN_IMAGE_CARD_QUALITY=low`.
   - leave `BTS_HARNESS_V2=1` as is.
3. `sudo /opt/btsweb/deploy.sh` (pull, deps since Pillow is new, web tests, restart, /healthz).
4. One live hosted forge. Check: SSE shows card-art progress; the class page lists `card_art_url`;
   `static/forged/<id>/cards.zip` exists; `forge_usage` has `art:*` rows with metered cost and the LLM rows
   name `z-ai/glm-5.3`; total about $0.80. Import the code into the mod, confirm portraits.
5. Force the fallback once: temporarily set the primary model to a bogus slug in a local run (not prod) and
   confirm the 404 skips to glm-5.2 for that call; the 429 trip is covered by unit tests.
6. Update the memory notes (`hosted-forge-unit-cost`, `droplet-deploy-path`) with the new default route and
   measured numbers.

---

## Risks / open items

- **glm-5.3 costs ~60% more than 5.2** for the same pipeline (~$0.65 vs ~$0.40 LLM). Ryan chose quality;
  the glm-5.2 tier is one env/role-map flip away if margins bite.
- **Card-art consistency** was ~60-70% strong, rest grainy/posterized with brown palette drift on clockwork
  concepts. Not fixed here; a later pass can add a per-class palette hint from `skin.imagery` or a
  reference-image conditioning step (Mega Crit art must not leave the box; see the pricing/permission note).
- **Import-time download** grows from ~0.5 MB to ~5 MB per class, on the UI thread. Acceptable for now; move
  to a background task if the freeze is noticeable.
- **OpenRouter as primary** concentrates risk on one vendor; the Ollama tier is the hedge while credits last
  (Ollama moved to per-token billing 2026-08-31; the credits are finite).
- `forge_estimate()` samples the last 30 forges "any mode"; after the switch its numbers mix glm-5.2 and 5.3
  forges for a while. Cosmetic.
- The `web/static/forged/` disk: 34 PNGs + zip is about 10 MB per class on a small droplet; watch `df` after
  the first 50 classes and add a "drop `cards/` after zipping" switch if needed (only the zip is served).
