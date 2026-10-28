# Multi-language support (website, forge console, forged classes, Workshop page)

Status: PLAN, written 2026-10-27. Nothing built yet. Decisions already made by Ryan on 2026-10-27:

- The creative pipeline (prompts, stages, validators, vocab) stays English, so it stays readable and workable.
- The forge console is translated at the STAGE-HEADER level only, and only when a language other than
  English is selected. Detail lines stream through in English.
- The English copy gets rewritten first. `docs/copy/COPY.md` is the source of truth for every user-facing
  English string (website, emails, Stripe, Workshop page, in-game mod UI, console stage headers). Translations
  live next to it (`docs/copy/COPY.zh.md`), same keys.

First target language: Simplified Chinese (`zh`, the game's `zhs`). Everything below is written so a second
language is one more file, not more code.

## Why (evidence from 2026-10-27)

- 3 of the 48 accounts signed up with QQ Mail addresses (Oct 21, 22, 27). None forged. Site referrals from
  Chinese sites are tiny (cn.bing.com: 2 hits ever), so these people arrive via Steam or word of mouth.
- Slay the Spire's Chinese player base is large (Simplified Chinese was roughly a quarter to a third of
  STS1's Steam reviews), and STS2 ships `zhs` and `zht` locales with their own CJK font sets
  (`FontManager`, `ZhsFontPathSet` in the decomp).
- The Oct 21 QQ user hit a separate, language-independent bug: the magic link opened inside the QQ desktop
  client's embedded browser, so the session cookie never reached Edge. Three re-sends in five minutes.
  That fix (a code the original tab can accept, or the original tab polling for completion) is NOT part of
  this plan but should ship before any Chinese-facing push. See "Related but separate".

## Scope

Four surfaces, in the order a Chinese player meets them:

| Surface | What changes | Where the strings live |
|---|---|---|
| A. Website | Language toggle, all static copy, JS-built strings, sign-in pages, magic-link email, user-facing error messages, Stripe Checkout locale | `docs/copy/COPY*.md` -> `web/static/i18n/<lang>.json` |
| B. Forge console | ~15 stage-header templates localized client-side, rest untouched | same files, `console.*` keys |
| C. Forged classes | Rules text via mod-side locale tables; creative text via one translation call at the end of the forge; bundle carries a `loc` block | mod `ForgedText.<lang>` tables + bundle `loc` |
| D. Workshop page + in-game mod UI | Chinese Workshop description (manual, Steam UI), import panel strings | `workshop.*`, `mod.*` keys |

Non-goals: translating prompts, vocab, validator messages, the ~180 console detail templates, the admin
panel, terms.html, privacy.html (English only, with a one-line note in Chinese). Prices stay in USD.

## Source of truth and build

```
docs/copy/COPY.md        English. Ryan edits this. Keys are stable forever; text is free to change.
docs/copy/COPY.zh.md     Simplified Chinese. Same keys, same order. Missing key = English fallback + warning.
docs/copy/GLOSSARY.md    Term table (game terms from the game's own zhs tables + our product terms).
web/tools/build_i18n.py  COPY*.md -> web/static/i18n/en.json, zh.json. Fails on duplicate keys, unknown
                         placeholders, or a {placeholder} present in en but missing in zh. Prints the
                         list of keys zh is missing. Run by hand; a pytest asserts the json is up to date.
```

COPY.md format (the extraction on 2026-10-27 seeded it with every current string):

- `### key.name` heading, a `Where:` line (file:line, element), optional `Notes:`, then the text indented
  four spaces. Inline markup: `**bold**`, `*italic*`, `[text](url)`, `` `code` ``. Blank line = paragraph.
- `{name}` placeholders are runtime values and must survive translation verbatim.
- The Workshop description is one entry and keeps its BBCode verbatim.
- Never say "buy" (donation framing, see `docs/plans/PRICING_V3_COPY.md`).

The same json files are read by Flask (email subject/body, Stripe product names), so there is exactly one
place a string can come from.

## A. Website

**Language selection** (client-side, `web/static/i18n.js`, loaded by every page):

1. `?lang=zh` in the URL (for links we post in Chinese communities; also sets the preference),
2. else `localStorage["bts.lang"]`,
3. else the browser language (`navigator.language` starting with `zh` -> `zh`),
4. else `en`.

Sets `<html lang>`, stores the choice, and shows a small toggle in the header of every page
(`EN | 中文`). Step 3 is enabled only after a native speaker has reviewed the Chinese (see "Translation
workflow"); until then the toggle exists but nothing auto-selects.

**Static copy:** the HTML keeps its English text in place; elements get `data-i18n="key"`
(`data-i18n-attr="placeholder:key"` for attributes). `i18n.js` overwrites text only when the language is not
English. So the English site never depends on JS or on the json, and there is no flash of untranslated
English for English users. CSP stays as is (`script-src 'self'`; the json is fetched, not inlined).

**JS-built strings:** about 60 literals in `app.js` / `render.js` plus a handful in the other page scripts
become `t("key", {vars})`. Plural logic stays in the English branch; Chinese does not inflect.

**Server-side strings the user sees:**

- JSON errors gain a stable `code` next to the English `error`; the browser shows `t("errors."+code)` and
  falls back to the English message.
- `/api/auth/email/start` takes `lang`; `auth.py` picks the subject/body from the json. The three sign-in
  landing pages are static HTML and get `data-i18n` like everything else.
- Stripe: `locale` on the Checkout Session (`zh` is supported) and the line-item name from the json.

**Cache:** nginx caches static files for 1h. Every page's `?v=` bumps, and `i18n/*.json` is referenced with
`?v=` too.

**SEO (later):** `<link rel="alternate" hreflang>` and a `lang` attribute per page. Not needed for launch.

## B. Forge console (stage headers only)

Every console line already arrives in the browser as one SSE `progress` event and goes through
`appendLog` in `app.js`. When the language is not English, each line first passes through
`localizeConsoleLine(msg)`:

- `zh.json` holds `console.*` entries, each a regex with named groups plus a Chinese template, built from
  the exact Python templates listed in COPY.md under "Forge console stage headers" (harness stamp, the six
  numbered front-end stages, the card counter, starter relic, card art, splash, done, failed/aborted,
  "starting…").
- First match wins, unmatched lines pass through unchanged, and quoted creative content (card names, the
  concept) is carried over by the named groups.
- One extra line at the top of the console when the language is not English: "The design log below is in
  English; your class will be in Chinese."

No server or pipeline change. The templates are stable (they predate the vocab waves), and a drift only
means a line shows in English, never an error.

## C. Forged classes in Chinese (what the player sees in-game)

Finding from 2026-10-27: card RULES text is not in the bundle at all. The bundle carries effects, and three
renderers turn effects into sentences: the mod (`ForgedCards.Describe` / `DescribeTrigger`, about 180
sentence templates plus fragments, also relic/power/orb/potion/status text in `Powers/`), the website
(`render.js` `fmtEffect` / `effPhrase` fragment tables), and the generator (`cardgen.describe`, for the
model's own review). So the two kinds of text need two different mechanisms.

**C1. Rules text: mod-side locale tables, no model involved.**

- New `Engine/ForgedText.cs` with the English templates keyed, and `ForgedText.zhs.cs` with the same keys.
  `Describe` picks the table by `LocManager.Instance.Language` (`"zhs"`), falling back to English per key.
  This is the pattern BaseLib documents on `ILocalizationProvider`.
- Templates are whole sentences per op, never word substitution: "Deal {Damage} damage." becomes
  "造成{Damage}点伤害。" (no spaces, the game's own convention) and the word order differs. Dynamic vars
  (`{Damage}`, `{CalculatedDamage}`, `{Block}`) are the game's and locale-neutral.
- Terms come from the game's own `zhs` tables so our text matches the base game exactly (力量, 格挡, 易伤,
  虚弱, 中毒, 消耗, 保留, 虚无, ...). Extracted 2026-10-27 into `docs/copy/GLOSSARY.md`: the pack stores
  them as plain JSON at `localization/zhs/*.json` (46 files, flat key->text maps, no `res://` prefix in
  the pack index), loaded by `LocManager.LoadTablesFromPath`, and a mod's `localization/zhs/<same
  file>.json` is merged on top.
- Keyword highlighting is NOT language-neutral: the game wraps the translated word itself
  (`[gold]力量[/gold]`), tooltips come from the card's declared keywords/powers, and the Exhaust/Retain/
  Ethereal/Innate/Sly/Unplayable lines are added by the game. The mod's English templates emit bare
  `{Damage}` with no colour tags, so the Chinese templates mirror that and follow GLOSSARY.md's sentence
  patterns.
- The picker prompts in `DataCard.PickPrompts` and the in-game import panel (`ForgeConfig.cs`) use the
  same table.
- The mod already ships the game's standard per-locale JSON tables in `mod/BlankTheSpire/localization/eng/`
  (`cards.json`, `card_keywords.json`, `powers.json`, `relics.json`, `characters.json`, `settings_ui.json`,
  `static_hover_tips.json`, `ancients.json`). Everything baked (keyword names and hover tips, the codegen
  cards, the settings panel labels) is localized by adding a `localization/zhs/` sibling with the same
  files, which the game picks up on its own. Only the runtime-rendered text (the `Describe` templates and
  the per-forge creative strings) needs the in-code tables above. The `mod.settings.*` entries in COPY.md
  are the `settings_ui.json` ones.

**C2. Creative text: one translation call at the end of the forge.**

Class name and description, archetype names, card names, card flavor, relic/potion/orb/status names.
Generated in English as today. When the forge's `lang` is not `en`, after assembly and before
`encode_class`, one call translates all of them in a single strict-JSON round trip:

- Hosted route: the design-tier model (GLM via Ollama Cloud, strong in Chinese). BYOK: the user's design
  model and key. Cost is a few thousand tokens, about a cent.
- The prompt loads GLOSSARY.md and the class concept for context.
- Validation: every key present, no placeholder changed, card names bounded for the card frame, no Latin
  leaking where Chinese is expected. A field that fails falls back to English. The translation can never
  fail the forge.
- Result goes in the bundle as `loc: {"zhs": {"character": {...}, "cards": {id: {name, flavor}}, "relic":
  {...}, ...}}`. English stays the primary strings, so the class still works for English players and in the
  English UI, and an English player who imports a Chinese forge sees English.
- Mod: `DataCard.Localization` becomes a `LocManager.Instance.Language` switch that prefers `Spec.Loc`
  for the active language and falls back to the English spec. `CardSpec` gains an optional `Loc` and the
  bundle/character parsers must ignore it when absent. Confirm the mod's JSON parsing tolerates the new
  optional field in OLD bundles and that OLD mods ignore it in NEW bundles (else a VocabVersion bump).
- Concept typed in Chinese: when the concept contains CJK, translate it to English first (same model, one
  call), run the pipeline on the English, keep the original for display and for `classes.concept`. Without
  this the explicit-request check in `frontend/request.py` misses Chinese asks entirely.
- DB: `classes.lang` (default `en`) so the Archive, deck page, and featured strip know what they hold.
- Code size: import codes average 3.8 KB, max 5 KB (gzip + base64url). A `zhs` block adds an estimated
  15–25%. Check the in-game import box and any URL use of the code for limits.
- Website deck/archive view, phase 1: shows the Chinese creative strings and English rules text, with a
  note that the game shows the rules in Chinese. Phase 2 (optional): port the `zhs` rules templates to
  `render.js` so the preview matches the game. `fmtEffect` builds phrases by concatenation, so that port is
  a restructure, not a string swap, which is why it is deferred.
- Fonts: the game's label nodes use its CJK font sets, so mod-injected strings render. Confirm in the smoke.

**Per-forge language:** an option next to the concept box, defaulting from the site language, sent as
`lang` in the `/api/forge-class` body. English users never see a change.

**Bundle `loc` schema (the contract between generation, web, and mod).** Optional top-level key on the
class bundle; absent on English-only forges. Keyed by the GAME's locale code (`zhs`, later `zht`, `jpn`,
`kor`, ...), never by the site's `zh`. Every field is optional; a missing field falls back to the English
string in the main bundle. Mod parsing (Godot `Json` into dictionaries, known keys only) already ignores
unknown top-level keys, so old mods tolerate the block.

```
"loc": {
  "zhs": {
    "character": {"name": "...", "description": "..."},
    "archetypes": [{"name": "..."}, ...],                 # same order as bundle.archetypes
    "cards":    {"<card id>": {"name": "...", "flavor": "..."}},
    "relic":    {"name": "...", "description": "..."},
    "potions":  {"<english name>": {"name": "...", "description": "..."}},
    "statuses": {"<english name>": {"name": "...", "description": "..."}},
    "summons":  {"<english name>": {"name": "...", "description": "..."}},
    "orbs":     {"<english name>": {"name": "...", "description": "..."}}
  }
}
```

Relic, potion, status, summon, and orb descriptions are model-written prose in the bundle (not rendered
from hooks), so they are translated like names. Card rules text is never in `loc`; the mod renders it from
effects through its own locale tables. `{placeholders}` and keyword markup inside any translated string must
be byte-identical to the English.

## D. Workshop page and in-game mod UI

- Steam supports per-language Workshop descriptions, but the uploader's `workshop.json` has a single
  description. Set the Chinese description by hand in the Steam web UI (edit item, description, language
  selector). Keep the text in `COPY.zh.md` under `workshop.description` so it is never lost. Verify once
  that a later upload does not wipe the extra-language description (the uploader already re-applies
  visibility on every upload, and an empty previews dir deletes previews).
- Title stays Latin ("BLANK the spire"); the Chinese tagline goes in the description's first line.
- The import panel, restart prompt, and bad-code message in `ForgeConfig.cs` read from the same mod table
  as C1. They ship in the same mod release.

## Translation workflow

1. Machine draft: one model pass over `COPY.md` -> `COPY.zh.md`, with GLOSSARY.md in the prompt.
2. Native review before `zh` auto-selects from the browser language. Candidates: ask the three QQ-mail
   signups (they are the target users), a Chinese STS community, or a paid reviewer. STS players are
   picky about card wording, so the rules-text templates (C1) are the part to have reviewed most carefully.
3. GLOSSARY.md is the contract both the copy draft and the per-forge creative translation obey.

## Phases and order

Mod before web whenever the bundle shape changes (codec rejects newer codes; see the 2026-10-01 incident).

| Phase | What | Needs a mod release? | Rough effort |
|---|---|---|---|
| 0 | Ryan rewrites the English in `COPY.md`. In parallel: `build_i18n.py`, `i18n.js`, `data-i18n` keys applied to the CURRENT strings, `t()` in the JS. Keys are stable, so his text drops in when ready. | no | 1 day |
| 1 | Website: toggle, `en.json`/`zh.json` (machine draft), console stage headers, email `lang`, error codes, Stripe locale. ui_smoke scenario `lang`: toggle, persistence, no English leaks (scan DOM text for Latin runs outside code boxes and names). pytest: build is up to date, email picks the language. Deploy. | no | 2 days |
| 2 | Mod: `ForgedText` tables + `zhs`, `Spec.Loc`, picker prompts, import panel, glossary extracted from the pck. AutoSlay smoke with the game set to `zhs` (find the language setting in the test profile), grep godot.log for "Localization formatting error", 0 mod exceptions. Workshop release. | yes | 3–4 days |
| 3 | Web: per-forge `lang`, concept-in translation, creative-out translation, bundle `loc`, `classes.lang`, deck/archive display. Deploy after the Workshop item is public. | no (after 2) | 2 days |
| 4 | Chinese Workshop description, native review, enable browser auto-select, hreflang, decide where to announce (Chinese STS communities; r/slaythespire is out, see the Reddit notes). | no | 1 day + review time |

Phase 1 alone is useful on its own (a Chinese reader can understand what the site does and sign up).
Phase 2+3 is what makes the product actually Chinese.

## Decisions still open for Ryan

- Traditional Chinese (`zht`) too? The game ships it. Recommendation: `zhs` first; `zht` later is mostly a
  character conversion of the same tables plus a few term differences.
- Auto-select `zh` from the browser before the native review, or toggle-only until then? Plan says
  toggle-only.
- Card-name length budget for the card frame (set once we see a few Chinese forges).
- Payment: Alipay / WeChat Pay are a Stripe dashboard toggle and worth checking before any Chinese-facing
  push. Not i18n, but the same audience.

## Risks

- English leaking from strings built out of fragments at runtime (listed with Notes in COPY.md); the smoke's
  Latin-run scan catches these.
- Chinese word order in the site's fragment-based renderer (`render.js`): why phase 1 shows English rules
  text on the site.
- nginx 1h cache: bump every `?v=`.
- Translation quality without a native reviewer: why auto-select waits.
- Import-code growth from the `loc` block.
- Mod/web ordering on the bundle shape change.

## Related but separate

- Magic-link cross-browser hand-off for desktop mail clients (QQ, Outlook, Electron apps). Hit on 2026-10-21
  by a Chinese signup. Fix: a short code in the email the original tab accepts, or the original tab polls
  for completion. Ship before promoting the site in China.
- Google sign-in is unreachable from mainland China; GitHub and email are the working paths. Resend
  delivered to QQ Mail within 15 seconds on 2026-10-21.
