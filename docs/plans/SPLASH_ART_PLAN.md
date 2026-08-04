# SPLASH ART + ID-AS-KEY DELIVERY PLAN

Two intertwined goals:
1. **Generated class splashes** on the character-select screen, with a **pluggable image backend**
   (try OpenAI today, FLUX or a local LoRA tomorrow — swap with one config line).
2. **Re-architect sharing from payload-codes to id-as-key:** the shared code becomes a short
   **key/URL** (`blankthespire.com/deck/<id>`) that resolves to a server-stored **package** of cards
   + relic + character **+ assets**. This is what makes art delivery trivial — the splash (and
   eventually per-card art) lives in the package instead of being crammed into a paste-code.

The art generator is built so the **existing creative harness is not modified** — splash generation
is a separate, optional step that runs *after* a class is forged.

Status: PLAN ONLY. Nothing below is built yet. Started 2026-06-29; rewritten around id-as-key.

---

## Why id-as-key (the pivot that solves art)

**Today:** the code IS the payload. Forge → `encode_class()` returns a self-contained `BTSC.…` blob
(gzipped+base64 JSON, ~2–4 KB). In-game (`ForgeConfig.ImportClass` → `BTS1Codec.TryDecode` →
`ForgedCharacters.TryImportClassBundle`) the mod decodes it locally. **Zero network, fully offline,
codes are immortal.** But binary assets can't ride a text paste without bloating it ~20–40×, and that
doesn't scale at all to "every card has art."

**New:** the code becomes a short **key**. Forge → server stores the package (JSON + asset blobs)
under a content-hash id → returns the id + URL. Sharing a class = sharing `…/deck/<id>`. Import =
paste the id → mod fetches the package → validates → installs. **Assets become free** (any size,
in the package), codes get tiny and human, and the URL doubles as a shareable preview page.

**The tradeoff we accept (decided 2026-06-29):** the mod gains its *first network dependency at
import time*, and the **server becomes load-bearing** — a shared id only works while we keep its data
hosted (today's codes are immortal; these are only as durable as the droplet). Mitigation below:
keep the self-contained code path as a fallback so nothing hard-breaks offline.

---

## Investigation findings (2026-06-29) — the integration points, traced

**Track 1 (remove Ironclad) — single, clean override surface.**
`PlaceholderCharacterModel.PlaceholderID => "ironclad"`
(`_modref/BaseLib-StS2/Abstracts/PlaceholderCharacterModel.cs:10`) is THE source: ~20 asset paths
(`CustomVisualPath`, `CustomCharacterSelectBg`, `CustomCharacterSelectIconPath`,
`CustomCharacterSelectLockedIconPath`, `CustomMapMarkerPath`, rest-site, merchant, energy counter,
SFX, multiplayer RPS hands…) are all string-built from it → all resolve to Ironclad assets. The 4
`ForgedCharacterSlotKK` shells (`ForgedClasses.g.cs:445,957,1469,1981`) extend it and override
gameplay (HP/deck/pool/relic/Localization) but **none of the asset hooks** — hence the Ironclad. Fix
= override the visible select-screen hooks (`CustomVisualPath` scene, `CustomCharacterSelectBg` scene,
`CustomCharacterSelectIconPath` + `…LockedIconPath` textures) to point at our own neutral assets. The
shells are GENERATED — the edit goes in `slotgen.py`'s `CHARACTER_TMPL` (`generation/btsgen/slotgen.py:154`),
regenerated into `ForgedClasses.g.cs`; adding overrides matches the template's existing pattern.
*Caveat:* `CustomVisualPath` is the animated in-combat creature; a static "?" scene means no
idle/attack animation (fine for a placeholder). Non-select Ironclad-derived assets (rest site,
merchant, RPS hands, SFX) can stay as-is for the first pass.

**Track 2 (art) — no art field exists yet; the file-store is the drop point.**
`CharacterSpec` (`CharacterSpec.cs`) and the class JSON have **no splash/icon field**. Runtime
consumption needs: extend the class JSON with a `splash` reference, parse it in
`ForgedCharacters.TryValidateCharacterDict`, add a field to `CharacterSpec`, and have the slot shell
load it (`Image.load` → `ImageTexture`) into `CustomCharacterSelectBg`/icon, else the Track 1
placeholder. The splash bytes land in the existing per-class store `user://forged/characters/KK/`
(next to `KK.json`); `ForgedCharacters.WriteClassFiles` is the writer to extend.

**Track 3 (id-as-key) — the server already stores the bundle; only assets are new.**
`web/models.py`: `ForgedClass` already persists the full `bundle_json` (`{kind, character, cards[],
relic?}`) + `code` per user, with an autoincrement int `id` and ready `summary()` / `detail()` shapes.
**So the JSON half of id-as-key is essentially already built** — a public `GET /api/deck/<id>` +
`GET /deck/<id>` preview can read this existing table. What's missing is **asset storage** (a column /
blob / served file for the splash) and the public (non-user-scoped) read path. Mod side: import is
**fully offline today** — `ForgeConfig.ImportClass` only calls `BTS1Codec.TryDecode` →
`ForgedCharacters.TryImportClassBundle`. Adding fetch-by-id = detect a short id / `…/deck/<id>` URL →
Godot `HTTPRequest` (confirmed the mod's **first network call**) → feed the SAME
`TryImportClassBundle` (which re-validates every card against the live vocab — the safety net is
source-agnostic) + write `splash.png` via `WriteClassFiles`. The `BTS1Codec` decode stays as the
offline fallback branch.

**Net:** all three tracks have concrete, low-surprise seams. The biggest positive surprise — the web
DB already holds every class bundle, so id-as-key is more "add a public resolver + asset storage"
than "build a store from scratch."

## Hard constraints (read first)

1. **Do not change the creative flow.** `character_pipeline.generate_character` and
   `class_forge.forge_class` / `web.forge.forge_to_bundle` stay as they are. Splash art is generated
   by a **separate call** that consumes their output. The only new generation-side piece is an
   **optional prompt-builder call** (blueprint → image prompt).
2. **Pluggable image backend.** All image generation goes through one `ImageBackend` interface;
   backends self-register; the active one is chosen by config/env. Default is a no-op so the feature
   is opt-in and a missing key never breaks a forge.
3. **Keep the self-contained code as a fallback.** The id-as-key resolver is *added in front of* the
   existing `BTS1Codec` path, not a replacement. A full `BTSC.…` payload code must still import
   offline. (The decoder already exists — near-zero cost to retain.)
4. **Graceful degradation everywhere.** No splash, server down, bad/expired id, offline user → never
   abort; fall back to the neutral placeholder (Track 1) and/or the self-contained code path.

Three tracks. **Track 1 ships alone** and is the safety net the others lean on. Track 2 (art) and
Track 3 (delivery) are complementary: Track 3 is what makes Track 2's assets painless, but each is
useful independently.

---

## Track 1 — Remove the Ironclad (no AI, no network, ships independently) — DONE + VERIFIED 2026-06-29

**Done:** added to `slotgen.py`'s `CHARACTER_TMPL` (regenerated into `ForgedClasses.g.cs`, all 4 slots)
overrides on each `ForgedCharacterSlotKK`: `CustomCharacterSelectIconPath` / `…LockedIconPath` /
`CustomMapMarkerPath` → the existing shared neutral "?" placeholder PNGs (`charui/char_select_char_name*.png`,
already in the shipped `.pck`), and `CreateCustomVisuals()` builds the in-combat/select MODEL from that
flat texture via `NodeFactory<NCreatureVisuals>.CreateFromResource(Texture2D)` (no `.tscn`). Build
clean (0 errors); DLL deployed. **VERIFIED in-game 2026-06-29:** (a) user confirmed the select screen
shows the gradient "?" placeholder, not the Ironclad, no menu crash; (b) AutoSlay smoke (pinned
`ForgedCharacterSlot01`, seed BTSVERIFY1) logged `Creating NCreatureVisuals from Texture2D` then ran
a FULL 3-act run (49 rooms, 28 combats incl. the Act 3 boss, 633 cards) with ZERO exceptions touching
the model / `CreateCustomVisuals` / `NodeFactory` — the static-model combat-crash risk did not
materialize. (The run's `RunFailed` was the known benign "main menu did not appear after game over"
end-of-run quirk, not a crash.)

**First cloud backend BUILT 2026-06-30:** `backends/openai.py` — OpenAI `gpt-image-1` via a stdlib-urllib
JSON POST (no new deps), key from `BTSGEN_IMAGE_API_KEY`/`OPENAI_API_KEY`, `BTSGEN_IMAGE_QUALITY` (default
medium), snaps size to gpt-image-1's 1536×1024 landscape, outputs PNG (mod reads it). Registered; inert
(`available()` False) with no key. Tests added (10 pass incl. a mocked full generate). "Splash on EVERY
run" now also covered on the CLI: `cli_character_generate` calls `forge_splash` orthogonally (respects
`BTSGEN_IMAGE_BACKEND`, no-op when unset). To enable in prod: deploy, then set `BTSGEN_IMAGE_BACKEND=openai`
+ `OPENAI_API_KEY` in the droplet `.env`. ⚠️ UX: cloud gen adds ~15–30 s to each web forge (it's synchronous
in `_persist_class`, before the result event) — candidate to make async later. The big select-screen
background (`CustomCharacterSelectBg`, a scene) is intentionally left for Track 2's generated splash.
Original design below.



The 4 `ForgedCharacterSlotKK` (and `BlankTheSpire`) extend `PlaceholderCharacterModel`, which falls
back to Ironclad art for three things on the select screen:

| What you see | BaseLib hook to override |
|---|---|
| animated character **model** | `CustomVisualPath` → a static `Sprite2D` scene (auto-converted to `NCreatureVisuals`) |
| select **card / icon** | `CustomCharacterSelectIconPath` |
| big **splash / background** | `CustomCharacterSelectBg` |

Steps:
1. Author a shared neutral asset set (one covers all 4 slots): a "?" / silhouette select icon, a
   matching big splash, and a one-node static model scene. Real `res://` assets under the mod's
   `images/` / `scenes/`.
2. Locate where the forged slots set asset hooks (base class / generation in
   `mod/BlankTheSpireCode/Cards/Forged/ForgedClasses.g.cs`, mirroring `Character/BlankTheSpire.cs`).
   *(investigation step)*
3. Override the three hooks on that base; optionally tint per-class by pool HSV so the 4 slots differ.
4. Build + in-game verify the select screen shows the placeholder, not the Ironclad.

Outcome: the Ironclad is gone for good, and `CustomCharacterSelectBg` is the seam the real splash
(Track 2, delivered via Track 3) swaps into — falling back to this placeholder whenever art is absent.

---

## Track 2 — Generated splash (pluggable backend, harness untouched) — SKELETON BUILT 2026-06-29

**Done (offline, end-to-end, harness untouched):** new package `generation/btsgen/art/` — `request.py`
(ClassArt / ImageRequest / ImageResult / StyleProfile), `registry.py` (`register` / `get_backend`,
selected by `BTSGEN_IMAGE_BACKEND` or arg), `backends/` (`base.py` Protocol + `null` default + `procedural`
zero-dep PNG via stdlib `png.py`), `extract.py` (`class_art_from_bundle` / `class_art_from_disk` — the
only touch-point to forge output, read-only), `prompt.py` (`splash_prompt`, template-only), `styles.py`
(DEFAULT_STYLE), `splash.py` (`forge_splash`, best-effort/never-raises), CLI `cli_forge_splash.py`
(`btsgen-forge-splash`). Tests: `tests/test_art.py` (6 pass). Verified: `btsgen-forge-splash cryomancer
--backend procedural` wrote a 1024×576 PNG + `.splash.meta.json` (carries the assembled prompt a cloud
backend will consume). NOTE: procedural hue is hashed from the class id (no upstream pool-colour field) —
so the tint is distinct-per-class but not theme-matched (a frost class can render magenta); a real backend
reads the full prompt and won't have this. Next: first cloud backend + wire into the web response + Track 3
delivery. Original design below.



### New, isolated package: `generation/btsgen/art/`

Nothing here is imported by the existing pipeline modules — the dependency arrow points one way
(`art/` reads bundle dicts; the harness never imports `art/`).

```
btsgen/art/
  __init__.py            forge_splash(...) — the public entry
  request.py             ImageRequest / ImageResult / StyleProfile dataclasses
  registry.py            register() + get_backend(name|env) ; default = "null"
  prompt.py              splash_prompt(bundle, style) -> ImageRequest   (the one new harness-side call)
  splash.py              forge_splash(bundle, *, backend, style, out_dir, on_event) orchestration
  styles/                swappable StyleProfiles (prompt suffix + reference images) — A/B styles here
  backends/
    base.py              ImageBackend Protocol
    null.py              no-op (default) — returns ok=False, "disabled"
    procedural.py        tinted abstract splash from pool HSV + archetype (no API, free)
    openai.py            gpt-image-1
    gemini.py            Imagen 4
    flux.py              FLUX.1 via fal.ai / Replicate
    # local_comfy.py     (future) ComfyUI/SDXL/FLUX + LoRA on your GPU box
```

### The pluggable interface

```python
# backends/base.py
class ImageBackend(Protocol):
    name: str
    def available(self) -> bool: ...               # keys/config present?
    def generate(self, req: ImageRequest) -> ImageResult: ...

# request.py
@dataclass
class ImageRequest:
    prompt: str
    out_path: Path
    negative: str | None = None
    ref_images: list[Path] = field(default_factory=list)   # style references
    size: tuple[int, int] = (1536, 1024)
    seed: int | None = None

@dataclass
class ImageResult:
    ok: bool
    backend: str
    path: Path | None = None
    cost_usd: float | None = None
    error: str | None = None
```

Selecting a backend is one line / one env var; adding one = drop a file in `backends/` and
`register("foo", FooBackend)`. Swapping styles = pick a different `StyleProfile` (the consistency
lever: fixed prompt suffix + reference image, or later a LoRA name). Backends report `cost_usd` for
the token economy. With id-as-key delivery the splash size is **no longer constrained** — it just
goes in the package — so we can use a generous resolution.

### The one new harness-side call (allowed by the constraint)

`prompt.py::splash_prompt(bundle, style)` turns a class into an image prompt. It reads the richer
in-memory `blueprint` when present (name, description, both archetype descriptions, relic theme, pool
HSV) and falls back to `character.json` + `meta.json` for post-hoc CLI runs. It may make **one small
Claude call** to write a vivid prompt — the "new small call" you OK'd; it does not touch the
blueprint/card/relic calls, and a template-only (no-LLM) path must also work.

### Where it hangs off (both surfaces — neither is modified)

- **Web** (`web/forge.py::forge_to_bundle`): after it returns its dict (already contains `blueprint`
  + `character`), an **orthogonal** `forge_splash(result)` runs at the call site / response assembly
  — not inside `forge_to_bundle`. Its output PNG is then handed to Track 3's package writer.
- **CLI** (`generate_character`): a separate `python -m btsgen.cli_forge_splash <class_id>` reads the
  quarantined bundle from `GENERATED_CHARACTERS_DIR` and writes the splash beside it.

Output: `<id>.splash.png` + a `<id>.splash.meta.json` sidecar (backend, cost, prompt, style, seed).
The existing `<id>.meta.json` writer is **not** touched.

---

## Track 3 — id-as-key delivery (the backbone)

Turns the shared code into a key that resolves to a server-stored package. This is what carries the
splash (and future card art) into the mod.

### Storage decision (settled 2026-06-29): static files on disk, nginx-served

Stack is Flask/gunicorn/nginx on a 1 GB DigitalOcean droplet, **SQLite** in prod, nginx serving
`/static/` directly from `/opt/btsweb/web/static/`. Decision: **the bundle JSON stays in the DB
(`ForgedClass.bundle_json`, the source of truth); the image is a FILE on disk** at
`web/static/forged/<id>/splash.webp`, served directly by nginx, **gitignored** (`/web/static/forged/`)
exactly like the existing `static/releases/*.zip` precedent so it survives `git pull` deploys. The
`ForgedClass` row gains one small column (`splash_hash`) for existence + cache-busting.
- *Why not DB blobs:* prod is SQLite — many ~50–200 KB blobs bloat the single db file and complicate
  backup; serving them puts Python/SQLite in the hot path on a 1 GB-RAM box. *Why not object store
  (Spaces/S3) yet:* the right answer once "every card has art" arrives, but premature infra + cost for
  splash-only/friends-scale. The static-file approach migrates to Spaces later behind the SAME
  URL-by-id contract.
- *Mod fetch* = a plain public static GET `https://blankthespire.com/static/forged/<id>/splash.webp`
  (simplest Godot `HTTPRequest`, no API auth for public-by-id sharing).
- *Ops note:* this dir is on the droplet disk → a separate backup concern from the DB and must be
  preserved on reprovision (document next to the `static/releases/` note in DEPLOY-DIGITALOCEAN.md).

### Server side (web) — BUILT + VERIFIED 2026-06-29 (mod-side fetch still TODO)

Done & verified end-to-end (offline fake forge + procedural backend, Flask test client):
- `ForgedClass.splash_hash` column + `db._ensure_class_columns` migration (mirrors the token_balance one).
- `_persist_class` (app.py): after `s.flush()` gives the row id, `_generate_splash()` renders to
  `static/forged/<id>/splash.png` (backend from `BTSGEN_IMAGE_BACKEND`; unset='null'=no splash),
  stamps `splash_hash`, embeds `splash_url` into the bundle, and **re-encodes the import code** so the
  code itself now delivers the splash URL to the mod. Best-effort — image failure never blocks the forge.
  The harness/`forge_to_bundle` is untouched (this lives entirely in the web layer; `art/` gained one
  optional `out_path` arg).
- `GET /api/deck/<id>` — PUBLIC id-as-key resolver (bundle + `splash_url`). `_splash_url()` builds the
  absolute URL from `BTSWEB_PUBLIC_URL` with a `?v=<hash>` cache-bust.
- `/web/static/forged/` gitignored (survives git-pull, like `static/releases/`).
- ⚠️ ids are the enumerable per-user autoincrement → `/api/deck/<id>` is walkable. Fine for a public
  gallery; revisit before launch if privacy is wanted (id-scheme open decision).

### Mod side — BUILT 2026-06-30, in-game visual verify pending

The select-background-from-runtime-PNG question is SOLVED: reflect showed
`NCharacterSelectScreen.SelectCharacter(NCharacterSelectButton, CharacterModel)` + a `Control _bgContainer`
(the same container BaseLib injects custom-entry scenes into). New `Cards/Forged/ForgedSplash.cs`:
- `IForgedCharacterSlot { int ClassSlot }` — implemented by every `ForgedCharacterSlotKK` (added to the
  slotgen template) so the patch maps a model → its slot.
- `ForgedSplash.TryCacheFromBundle(json, slot)` — called from `ForgeConfig.ImportClass` after a successful
  import: parses `splash_url` from the decoded bundle, fetches via `System.Net.Http.HttpClient` (sync,
  15 s timeout — the mod's first network call), writes `user://forged/characters/KK/splash.png`. Best-effort.
- `ForgedSplashBgPatch` — Harmony postfix on `SelectCharacter`: when the highlighted character is an
  `IForgedCharacterSlot` with a cached splash, overlays a `TextureRect` (FullRect, KeepAspectCovered) into
  `_bgContainer`. Manages only its own named overlay node (removed on any other select) — never touches
  vanilla nodes. No splash → no-op → the Track 1 "?" placeholder stands.

Build clean (0 err), DLL deployed. VERIFY: (a) DISPLAY — staged procedural splashes into the 3 imported
classes' user dirs (Gap Tester/Nimbus/Boneweaver); highlighting each on character select should show its
tinted splash as the background. (b) FETCH — build-clean only; a real round-trip needs the live site with
`BTSGEN_IMAGE_BACKEND` set, then re-forge + re-import (the 3 imported classes predate splash_url, hence the
manual stage). The model stays the Track 1 "?" (splash is the BACKGROUND, not the model).

Original design notes:

1. **Package store.** On forge, write the splash to `web/static/forged/<id>/splash.png` and stamp
   `ForgedClass.splash_hash`. The bundle JSON is already persisted (`bundle_json`). The public key is
   the row id (see id-scheme open decision — content-hash vs the existing autoincrement int).
2. **Resolve API.** `GET /api/deck/<id>` → returns a manifest: the class bundle JSON + asset URLs (or
   the bytes). Public-by-id (so non-logged-in friends can import a shared code). Validate id format;
   404 cleanly on unknown/expired.
3. **Preview page.** `GET /deck/<id>` → human page: class name, card list, the splash, and an
   "import code: `<id>`" box + install instructions. This is the shareable URL and a virality lever
   (a public gallery later falls out of this).
4. **Forge response.** `forge_to_bundle`'s caller stores the package and returns `{id, url, …}`
   alongside (or instead of) the legacy `code`. The forge UI shows the short id + URL to copy.

### Mod side

1. **HTTP resolver.** `ForgeConfig.ImportClass`: if the pasted value is a short id / `…/deck/<id>`
   URL, the mod calls `/api/deck/<id>` (Godot `HTTPRequest` — the mod's **first network call**),
   downloads the package, caches to `user://forged/<id>/` (bundle JSON + `splash.png`).
2. **Fallback path retained.** If the pasted value is a full `BTSC.…` payload code, decode locally
   exactly as today (`BTS1Codec.TryDecode`). Resolver tries id first, falls back to payload decode —
   one field, both formats.
3. **Install + validate.** Same `ForgedCharacters.TryImportClassBundle` (re-validates against the
   live EffectRunner vocabulary — keep this safety net), then load the cached `splash.png` at runtime
   (`Image.load` → `ImageTexture`) into `CustomCharacterSelectBg` / icon, else Track 1 placeholder.
4. **Error UX.** Friendly dialogs for offline / server-down / unknown id, pointing at the
   self-contained-code fallback.

### Durability note (the load-bearing decision)
Shared ids only work while we host their data. Keep the self-contained `BTSC` code available (forge
can still emit it on request) as the portability/offline insurance. Revisit retention/backup policy
before any wider launch.

---

## Cost (cloud image backend, per class)

≈ **$0.04–0.08 all-in**: one image ($0.03–0.07 — gpt-image-1 med ≈ $0.06, Imagen 4 ≈ $0.04, FLUX.1
dev ≈ $0.025) + a tiny prompt call (~$0.003–0.01). Negligible vs. a class's text generation. Cost
isn't the reason to pick local over cloud; **style consistency** is. Backends report `cost_usd` to
meter against the token economy.

---

## Open decisions
- **First real image backend**: cloud (OpenAI / Imagen / FLUX) vs. local SDXL/FLUX+LoRA. Recommend a
  cloud backend first; pluggable design makes it reversible.
- **Gating**: splash on every forge, or only paid / "Use-a-token" forges? (Token plumbing exists.)
- **id scheme**: content-hash (dedupe + integrity, recommended) vs. sequential (guessable, enables an
  enumerable public gallery — a feature choice).
- ~~**Package storage**~~: SETTLED 2026-06-29 → static files on disk under `web/static/forged/`,
  nginx-served, gitignored like `static/releases/` (see "Storage decision" in Track 3). Migrates to
  DO Spaces later behind the same URL-by-id contract if volume demands.
- **Legacy code emission**: keep emitting self-contained `BTSC` always, or only on request.

## Investigation steps — RESOLVED 2026-06-29 (see "Investigation findings" above)
- ✅ Asset hooks live in `slotgen.py` `CHARACTER_TMPL` (`:154`) → `ForgedClasses.g.cs`; source is
  `PlaceholderCharacterModel.PlaceholderID => "ironclad"`.
- ✅ `web/models.py` `ForgedClass` already stores `bundle_json` + `code` per user — JSON store exists;
  only asset storage + a public resolver are new.
- ✅ Import seam is `ForgeConfig.ImportClass` → `ForgedCharacters.TryImportClassBundle` /
  `WriteClassFiles`; vocab re-validation is source-agnostic, so fetch-by-id reuses it. Mod has no
  HTTP yet → `HTTPRequest` is the first network call.

Remaining unknown: exact asset-storage choice on the web side (DB column vs blob/object store vs
served static file) — an Open decision, not a blocker.
