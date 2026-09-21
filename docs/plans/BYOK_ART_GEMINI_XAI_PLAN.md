# BYOK ART ON GEMINI + xAI (plan, 2026-09-19, revised same day)

**Status 2026-09-20: steps 1–3 BUILT (tests green: generation 20 new, web 171 total), NOT deployed.**
Step 0's live half and step 4 wait on Ryan's own Gemini + xAI keys — nothing here has touched a real
vendor. Order of play from here: (a) one `POST /images/generations` per vendor on a real key to confirm
the fields listed under "Step 0 findings" (top-level `aspect_ratio`, accepted ratio tags, media type,
`b64_json`); fix `RATIOS`/`_KIND_RATIOS` in `openai_images.py` if a vendor 400s; (b) deploy web only;
(c) one live forge per vendor, compare the vendor's bill to the ledger's `art:*` rows and the panel's
quote, fix the preset prices if off by >10%; (d) eyeball the chroma-keyed sprites (`art/keying.py`,
`key_file()` re-keys saved images without re-billing) and decide sprite policy; (e) update memory
`byok-art-policy`. Deviation while building: the $0.40 card-art spend cap now applies to server-paid
packs only (`BTSWEB_BYOK_CARD_ART_MAX_USD`, default 0 = uncapped) — at Gemini's flat $0.039 it cut every
pack to 11 of 34 cards, the opposite of goal 1.

Context: since 56586c6 a bring-your-own-key forge makes its art on the user's OpenRouter/OpenAI key or not
at all. Research the same day (memory `byok-art-policy`) found two more providers whose keys can pay for
art through an OpenAI-shaped `/images/generations`: **Google Gemini** (the same
`generativelanguage.googleapis.com/v1beta/openai` base URL the user already picks) and **xAI**
(`api.x.ai/v1`, not in the provider list yet). Groq, Anthropic, DeepSeek, Ollama Cloud stay no-art;
Together is one preset row away if ever wanted.

Goals (Ryan, 2026-09-19):

1. Art for Gemini and xAI keys — the **complete** pack (splash, sprite, one portrait per card), billed to
   the user's key. **No spend cap on BYOK.**
2. Keep that bill **as low as possible while still complete**: cheapest acceptable image model per vendor,
   cheap text defaults, no wasted calls (reasoning held down, JSON pinned so repairs are rare).
3. **Tell the user the cost before they push go.** Picking a key type (and a model) shows a per-forge
   estimate: text + art + total, on their key, from real numbers.

Not in scope: a per-forge spend cap (the earlier draft's `ForgeBudget`). If we ever want one for the
token path — where the money is ours and the measured $0.93/forge sits under a $1.00–1.50 token — it is a
separate, small change and does not touch anything here. No mod release; no codec/vocab bump.

---

## Step 0 findings (2026-09-20, docs only — no Gemini or xAI key exists locally or on the droplet)

Read off the vendors' docs/pricing pages; the live-call half of step 0 (fixtures, `aspect_ratio` honoured,
returned image format, `stream_options`) still needs one forge each on Ryan's own keys.

- **Gemini shim.** `POST /v1beta/openai/images/generations` with `{model, prompt, n, response_format:
  "b64_json", aspect_ratio}`; `aspect_ratio` is the shim's "extra_body" field = a top-level JSON key
  (`size` also accepted, maps to a ratio). The shim page still lists only `gemini-2.5-flash-image`
  ($0.039) and `gemini-3-pro-image-preview` ($0.134). Google's pricing page now also carries
  `gemini-3.1-flash-lite-image` at **$0.0336**/1K image and `gemini-3.1-flash-image` at $0.067 — cheaper
  than flash-image, but NOT confirmed routable through the shim. Default stays `gemini-2.5-flash-image`;
  the lite model is in the price table and one `BTSGEN_GEMINI_*_MODEL` flip away once a live call proves it
  (would take the pack from $1.40 to ~$1.21). `reasoning_effort` is a top-level chat field on the shim.
  Text prices ($/M in, out, cached): 2.5-flash-lite 0.10/0.40/0.01; 2.5-flash 0.30/2.50/0.03;
  2.5-pro 1.25/10/0.125; 3-flash-preview 0.50/3.00/0.05.
- **xAI.** `POST /v1/images/generations`, same shape. `grok-imagine-image` $0.02, `-2.0` $0.04,
  `-quality` $0.05 — as planned. Accepted `aspect_ratio` strings are not enumerated on the pages we
  could fetch; the backend ships a conservative whitelist (1:1, 3:2, 2:3, 4:3, 3:4, 16:9, 9:16) to
  confirm live. **`grok-4-fast` no longer exists** on the models page. The only explicitly
  non-reasoning text model is `grok-4.20-0309-non-reasoning` at 1.25/2.50/0.20 (same as `grok-4.3`);
  `grok-4.5`/`4.6` are 2.00/6.00. So the xAI text line is ~$1.00, not the ~$0.35 in the cost table
  above, and the xAI total is ~$1.75 — still the estimate's job to say so, not ours to hide.
- **OpenAI chat prices** could not be fetched (pricing page 403s to the fetcher); the table carries the
  known list values marked unverified.
- Neither vendor returns cost/usage on the image call (confirmed on the docs), so `cost_usd` is the
  preset table, as planned.

---

## Decisions + assumptions (confirm or overrule)

- **One generic backend, two presets.** Gemini and xAI both take a top-level `aspect_ratio` and
  `response_format: "b64_json"` on the OpenAI images shape, so this is ONE class
  (`OpenAIImagesBackend`) with a per-host preset table (base URL, per-kind default model, per-image
  price, accepted ratios). Adding Together later = one more row.
- **Cheapest complete defaults.**
  - xAI: `grok-imagine-image` at $0.02/image for all three kinds ($0.04 `-2.0` and $0.05 `-quality` are
    env-selectable). Full pack ≈ 36 × $0.02 = **$0.72**.
  - Gemini: the OpenAI shim only routes `gemini-2.5-flash-image` ($0.039) and `gemini-3-pro-image-preview`
    ($0.134). Flash-image everywhere. Full pack ≈ 36 × $0.039 = **$1.40**. There is no cheaper Gemini
    image call; the one lever is fewer calls, see the grid experiment below.
  - Reference: today's OpenRouter/OpenAI path is ~$0.14–0.20 for the same pack (mini @ low for cards).
- **Grid experiment for Gemini cards (optional, step 6).** Ask for a 2×2 sheet of four portraits in one
  1024×1024 call and split it: $0.039 → ~$0.01 per portrait, cards ≈ $0.35 instead of $1.33. Each tile is
  512×512 scaled to the mod's 1000×760 box, so it is a visible quality trade. Build it as a flag, A/B it,
  and decide with eyes — not the default until it wins.
- **Prices are a table.** Neither vendor meters cost in the response (Gemini's shim returns no usage;
  xAI is flat per image), so the backend carries `price_for(req)` and the ledger's `cost_usd` is that
  estimate (advisory, like the openai backend). Env-overridable like `BTSWEB_MODEL_PRICES`. Verified
  against the vendors' pricing pages at build time and re-checked against the vendor's bill after the
  first live forge (step 5).
- **The estimate the user sees is computed server-side** from one source of truth: `/api/forge-estimate`
  already returns the rolling per-forge token counts; it grows an `art` block (per host: images per forge,
  price per image, model) and a `text_prices` block (per suggested model: $/M in/out/cached). The browser
  multiplies; it never owns a price table. Today's `CLAUDE_PRICES` in app.js folds into that.
- **Sprites on Gemini/xAI are chroma-keyed.** Neither vendor does `background=transparent` (only the
  OpenAI GPT Image family does). Prompt a flat `#00FF00` backdrop, key it out with Pillow (already on the
  droplet), let the mod's alpha autocrop do the rest. If the A/B looks bad, fall back to the procedural
  placeholder sprite — never an opaque rectangle.
- **Text defaults per host** (the cost lever on the text side): Gemini `reasoning_effort: "low"`
  + `response_format: json_object` on structure/cards; xAI `json_object` on structure/cards and the
  dropdown suggests non-reasoning `grok-4-fast`-class models first (grok-4.x "reasoning cannot be
  disabled"). Unknown hosts keep today's bare request.

---

## Is the text harness universal? (asked alongside this plan)

Mostly yes. The BYOK path builds `OpenAICompatGenerator(base_url, key, model)` for every role and the
class already handles what differs across vendors: it probes `max_tokens` vs `max_completion_tokens` and
remembers per model, drops `stream_options` when an endpoint 400s on it, streams so the timeout bounds
silence rather than total time, and the contract/repair loop fixes schema drift. Gemini's shim and xAI
both speak streaming chat completions, so **no harness change is needed to get a class out of either
key**.

What differs is *cost and JSON discipline* — the hosted path's solved problems the BYOK path doesn't
apply yet:

- **Hidden reasoning burns tokens.** Gemini Pro and grok-4.x think before answering; that thinking is
  billed and counts against `max_tokens` before any content — the glm-5.2 failure mode `ollama_mix` fixed
  with `extra_body`. BYOK passes no `extra_body` today.
- **JSON grammar pinning.** Hosted structure/cards roles set `response_format: {"type": "json_object"}`;
  BYOK doesn't. Both vendors accept it; it cuts repair churn, which on a per-token key is money.
- **One model for all three roles.** Hosted splits brainstorm (gemma) from structure/cards (glm); BYOK
  uses the user's one pick everywhere. Fine; not worth a per-role picker.

Step 3 adds a small **host profile** (extra_body + response_format + suggested models) keyed by base-URL
host in `web/forge.py`'s two BYOK generator builders. Additive; that is the only text-side change.

---

## Cost model (what the estimate will show)

Per-forge at list prices; `/api/forge-estimate` rolling average is ~50 calls, ~1.4M input tokens (much
cacheable), ~0.1M output. Verify at build time; these are the numbers the UI will surface.

| Key + suggested text model | Text (est.) | Art, full pack (36 images) | Total on the user's key |
|---|---|---|---|
| xAI grok-4-fast (non-reasoning) + grok-imagine-image | ~$0.35 | $0.72 | **~$1.05** |
| Gemini 2.5 Flash-Lite + flash-image | ~$0.25 | $1.40 | **~$1.65** |
| Gemini 2.5 Flash + flash-image | ~$0.60 | $1.40 | ~$2.00 |
| Gemini 2.5 Pro + flash-image | ~$2.00+ | $1.40 | ~$3.40+ (the hint says "pricey") |
| Gemini + flash-image, 2×2 grid cards (experiment) | as above | ~$0.43 | Flash-Lite total ~$0.70 |
| Today: OpenRouter key, glm-5.3 + mini cards | ~$0.79 | ~$0.14–0.20 | ~$0.95 |

---

## Steps

### 0. Verify vendor details (½ day, no code)

One real call each on Ryan's own keys, saved as fixtures for the offline tests:

- Gemini shim `POST /v1beta/openai/images/generations` with `{model, prompt, n:1,
  response_format:"b64_json", aspect_ratio:"3:2"}` — confirm `aspect_ratio` is honored as a top-level
  field (the docs call it an `extra_body` field, the SDK's name for extra top-level JSON), the returned
  bytes' format (PNG or JPEG; we normalize either), and 2:3 for sprites.
- xAI `POST /v1/images/generations`, same shape; confirm the `aspect_ratio` values (`3:2`, `2:3`, `1:1`
  are listed), `b64_json`, and the format.
- Both chat endpoints: one structure-role call with `response_format: json_object` + Gemini
  `reasoning_effort: "low"` / an xAI `grok-4-fast` model, to see the usage chunk and whether
  `stream_options` 400s (the probe copes either way; this tells us what the ledger will see).
- Read the exact current prices off both pricing pages into the preset table.

### 1. Generic OpenAI-images backend (generation/btsgen/art/backends/openai_images.py)

- `OpenAIImagesBackend(preset, api_key, model=None, card_model=None, sprite_model=None)`;
  `name = preset.name` ("gemini" | "xai"). `available()` = has key. `generate(req)`: build
  `{model, prompt, n:1, response_format:"b64_json", aspect_ratio}` from the kind→ratio map (splash 3:2,
  card 3:2, sprite 2:3), POST with `Authorization: Bearer`, decode `data[0].b64_json`.
- **Normalize to PNG** with Pillow and measure width/height from the decoded image, so JPEG/WebP replies
  are fine (the openrouter backend rejects non-PNG; this one converts).
- **Sprite chroma-key** when `req.transparent`: append "on a perfectly flat, solid bright green (#00FF00)
  background, nothing else in the background" to the prompt; key out pixels within a tolerance of the
  backdrop, 1px erode + alpha feather against halos, write RGBA. Lives in `art/keying.py` so the A/B
  harness can run it on saved images.
- `price_for(req)` from the preset table by (model, kind); `cost_usd` on the result = that estimate.
- Presets (`PRESETS = {"gemini": …, "xai": …}`): base URL, per-kind default models, price table, ratio
  whitelist, `returns_usage: False`. Env overrides mirror the openrouter backend's names
  (`BTSGEN_GEMINI_MODEL`, `BTSGEN_XAI_CARD_MODEL`, …). Register both in `backends/__init__.py` (inert
  without a key).
- Tests `generation/tests/test_art_openai_images.py` (urlopen mocked with step-0 fixtures): request shape
  per kind, PNG normalization from a JPEG reply, chroma-key yields alpha, `price_for`, ctor-key-over-env,
  graceful no-key.

### 2. Wire the providers (web/app.py, web/forge.py, web/static/app.js)

- `_BYOK_ART_HOSTS` gains `"generativelanguage.googleapis.com": "gemini"` and `"api.x.ai": "xai"`;
  `_byok_art_backend` builds `OpenAIImagesBackend(PRESETS[vendor], api_key=…)`.
- **Host profiles for text** in `web/forge.py`: `BYOK_HOST_PROFILES = {host: {"extra_body": {...},
  "json_roles": True}}` — Gemini `{"reasoning_effort": "low"}`; xAI none. Both BYOK generator builders
  look the profile up by host and pass `extra_body` + `response_format={"type":"json_object"}` for the
  structure/cards contracts (brainstorm stays free text, as hosted). A key the endpoint 400s on is already
  dropped by the generator, so a wrong guess degrades to today's request.
- `PROVIDERS` in app.js: `google` gets `art: true`, models cheap-first (`gemini-2.5-flash-lite`,
  `gemini-2.5-flash`, then Pro); new `xai: { label: "xAI (Grok)", base_url: "https://api.x.ai/v1",
  prefix: "xai-", art: true, models: [non-reasoning fast first, …] }` (exact ids from step 0);
  `providerFromKey` auto-picks on `xai-`.
- Privacy page: "(OpenRouter, OpenAI, Google Gemini, xAI)".
- Tests: `test_byok_art.py` gains a Gemini and an xAI end-to-end forge (mocked urlopen) proving
  `2 + n_cards` image calls on the user's key, the sprite request carries the green-backdrop prompt, and
  the ledger's `art:*` rows carry the preset's estimated cost; a Gemini BYOK forge's structure call
  carries `reasoning_effort` + `json_object` (assert on the stubbed generator's kwargs).

### 3. The pre-go cost summary (web/app.py `/api/forge-estimate`, web/static/app.js)

What the user sees, in the BYOK panel, the moment a provider is picked and again as the model changes,
and repeated in the confirm dialog:

```
Estimated cost per forge on your Gemini key
  Text   gemini-2.5-flash-lite   ~50 calls · ~1.4M in (≈0.9M cached) · ~0.1M out   ≈ $0.25
  Art    gemini-2.5-flash-image  36 images (splash, sprite, 34 card portraits) × $0.039   ≈ $1.40
  Total                                                                           ≈ $1.65
  Art is generated on your key; there's no cheaper Gemini image model on this API. An OpenRouter
  key makes the same pack for about $0.20.
```

- `/api/forge-estimate` grows: `images_per_forge` (rolling average of `art:*` calls per forge, today's
  ledger already has it), `art: {host: {model, per_image_usd}}` from the presets + the OpenRouter/OpenAI
  measured averages (metered `art:*` cost per forge over the same window — real numbers, not list price),
  and `text_prices: {model: [in, out, cached]}` for every suggested model in `PROVIDERS` (from
  `MODEL_PRICES`, extended with the Gemini/xAI/OpenAI chat prices). One handler, cached a minute.
- `estimateText()` becomes a three-line table builder: text line when the model is priced (else the
  token counts + "multiply by your provider's price sheet"), art line whenever `PROVIDERS[id].art`, total
  when both are known. Providers without art keep today's one-liner plus "no generated art on this key".
- For OpenRouter/OpenAI keys the art line uses the ledger's measured average (≈$0.14–0.20), so the
  comparison sentence under the Gemini/xAI estimate is a real number.
- The result line after the forge already shows images + metered/estimated art dollars; label estimated
  ones "est." so nobody reads a table price as a bill.
- Test: `/api/forge-estimate` carries `art` for every art host and `text_prices` for every suggested model
  (a suggested model with no price is a test failure — that is how the table stays complete); the UI
  smoke (`web/tools/ui_smoke.mjs`) checks the three-line estimate renders for Gemini and the one-liner for
  Groq.

### 4. Rollout + verification

1. Land steps 1–2. Deploy (web only).
2. One live forge per new provider on Ryan's own keys; compare the vendor's billing page to the ledger's
   `art:*` estimates and the estimate the panel showed. Fix the tables if off by >10%.
3. Land step 3 once the numbers are confirmed real, so the first thing users see is right.
4. A/B the chroma-keyed sprites vs the procedural placeholder (the promo recorder's clip cutter is the
   quickest way to eyeball them in combat). Decide sprite policy per provider.
5. Update memory `byok-art-policy` (this reverses "Gemini/xAI get no art") and the hint copy.

### 5. Optional: 2×2 grid cards on Gemini (after step 4, only if the $1.40 is a complaint)

Flag `BTSGEN_GEMINI_CARD_GRID=2`: batch four card prompts into one "2×2 sheet, equal quadrants, no
borders, no text" request, split into tiles, run each through `fit_to_portrait`. ~$0.35 for the cards
instead of $1.33; per-tile 512 px. Ship only if the side-by-side is acceptable; the estimate line shows
whichever mode is active.

---

## Open questions

- **Gemini's $1.40 art bill.** Complete-and-cheapest on Gemini is still ~7× the OpenRouter pack. The
  estimate makes it the user's informed choice; is that enough, or do we want the grid experiment (step 5)
  in the first release?
- **Sprite quality bar.** If chroma-keying is ugly on either vendor, placeholder mage or no sprite?
- **Rolling vs list for the art line.** For Gemini/xAI we have no history until the first forges land;
  show the list-price table until the ledger has ≥3 forges on that host, then switch to measured?
