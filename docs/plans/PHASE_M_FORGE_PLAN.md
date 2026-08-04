# Phase M — Forge (VOCABULARY_GAPS #36): the repeat-empower keyword

**Status:** **DONE (2026-07-06, AutoSlay-VERIFIED)** · **Vocab bump:** v18 → **v19** (shipped) ·
All slices landed same-day, M-3 stretch (`forged_ge`) included; relic-side income decided IN.
Smoke (seed GAPTEST36, "Forge Gap Tester" staged in slot 04, then restored): full-run **VICTORY**
through Act 3 — forge income ×543 across all three paths (card 198 / relic 194 / trigger 151),
forged payoffs ×170 with visibly growing amounts (peak Forge 98; per-combat reset observed at
combat boundaries), 0 mod exceptions. Generation suite 474 green incl. the new 33-case
`tests/test_forge.py`. The `forge_ramp` catalog entry flips BUILDABLE off gap #36's done status.
(Historical note: the "ask before smoke" preference below was superseded 2026-07-06 — run AutoSlay
without asking.)

## The fantasy, and why gap #18 doesn't cover it

Base StS2 **"Forge" is a numeric keyword, not a card upgrade**: "Forge N" repeatedly pumps value
into the Sovereign Blade attack over a combat ("Deal 5 damage. Forge X." / "At the start of your
turn, Forge 4." — see `generation/reference/sts2_cards.json:1553,2869,4346,9285`; runtime event
`AfterForge(amount, forger, source)` at `_modref/reflect/dump.txt:1273`). The fantasy is
**"my signature attack grows every time I stoke it"** — ramp you can feel hit-by-hit.

Gap #18 (`upgrade_card`) is the *Armaments* fantasy — apply a card's one-shot upgrade payload
mid-run — and stays a separate item. It cannot express Forge: the mod's upgrade model is a single
`IsUpgraded` boolean + one positional `Upgrade[]` list (`ForgedCards.cs:506`, `EffectRunner.cs:35-38`),
so "upgrade over and over" is structurally impossible down that path. Forge instead composes two
cheap primitives we already know how to build:

1. **op `forge` (amount N)** — increments a per-combat, player-level **Forge counter**, displayed
   as a stacking power (new `ForgedForgePower`, modeled on `Powers/ForgedTempStatPowers.cs`).
   Allowed on cards AND inside `add_trigger` self-payloads ("At the start of your turn, Forge 2")
   — trigger income is what makes it an engine.
2. **scale value `"forged"`** on `damage`/`block` — the payoff read, one new case in the F5 scalar
   switch (`EffectRunner.cs:263-271`).

No per-card-instance state (that's gap #23 Rampage — stays separate), no card-ref/choice flow
(that's #18/F4). Everything rides existing frameworks; this is F5-sized, smaller than H4.

## Design decisions

- **`forged` is ADDITIVE — the exception in the scale family.** F5 scales replace the amount
  (nominal amount ignored); `forged` instead resolves as `amount + ForgeTotal`. Base-game Forge is
  additive ("Forges an *additional* 5"), and replace-semantics would make every payoff a dead card
  until forge income comes online. Document the exception in the schema `scale` description
  (`card.schema.json:35`). Side benefit: the static `upgrade` delta keeps working on the printed
  base (with replace-scales the upgrade delta lands on an ignored amount).
- **Per-combat scope.** The counter is a power, powers die at combat end. Per-run persistence
  (base-game blade flavor) needs run-persistent state — out of scope, note for later.
- **Payload rules:** `forge` joins the self-payload op set (fixed amounts only); `scale:"forged"`
  is NOT allowed inside payloads (`TriggerScale` stays `cards_retained` — payoff reads belong on
  played cards). Relic-side forge income (via `RunRelicEffects`) is a cheap optional extra — decide
  during build, default IN (a "smoldering heirloom" keystone relic is on-theme).
- **Card text lockstep:** `Describe` renders `forge` as `Forge N.` and a forged-scaled effect as
  e.g. `Deal 6 damage, plus your Forge.` — byte-matched in `cardgen.py` as always.
- **Power presentation:** stacks = current Forge; in-code loc (the gap-#26 lesson: never depend on
  base-game loc keys); icon via the existing power-icon path (EmojiIconRenderer ⚒ works).
- **Name:** keep the keyword name "Forge" on card text (it IS the base-game fantasy), but never
  touch the base game's `AfterForge`/Sovereign-Blade machinery — ours is a parallel, closed-vocab
  implementation.

## Build slices

**M-1 — engine + contract (the vocab bump).**
- `ForgedForgePower` (new, `mod/…/Powers/`): stacking counter power, in-code loc.
- `EffectRunner.cs`: `case "forge"` in the `Execute` switch (`:69-226`); `"forged"` case in
  `FromState` (`:263-271`) reading the player's ForgedForgePower stacks (0 if absent) and ADDING to
  the printed amount at the damage/block sites.
- `TriggerRunner.cs`: accept op `forge` in self payloads.
- `ForgedCards.cs`: `SupportedOps` (`:69-79`) + `AmountOps` (`:111-121`) + `SupportedScales`
  (`:105-106`) + `TriggerOps`; `Validate` rules (`:405-509`): `forged` only on damage/block, keeps
  the "at most one scaled damage/block per card" rule, forbidden in payloads; `Describe`
  (`:606-713`) sentences; `VocabVersion` (`:45`) → 19.
- `DataCard.cs`: `DeclareEffects` — `forge` joins the executed-in-OnPlay/no-card-var group
  (`:101-110`); forged-scaled damage/block follow the existing scaled-effect declaration path.
- `CardSpec.cs`: no new fields (op + amount + existing `scale` suffice). Zero shell regen.
- `mod/contract/card.schema.json`: op enum (`:30`), scale enum (`:35`), payload op list (`:74-78`).
- `mod/contract/VOCABULARY.md`: op row + scale row.

**M-2 — generation lockstep.**
- `cardgen.py`: `effect_literal` (`:75-126`) + `describe()` byte-match.
- `validator.py`: `_SUPPORTED_SCALES` (`:42`) + `forge` into the build-around op set (`:34-52`);
  structural checks (forged only on damage/block, not in payloads); `_score_effect` (`:331-381`)
  weights — forge income priced like a ramp op, forged payoffs priced above their printed base.
- `character_validator.py`: **class-level pairing rule** — a class with `forge` ops must contain
  ≥1 `scale:"forged"` payoff and vice versa (the cross-card analogue of the X-cost coupling;
  prevents dud smiths and dead blades).
- `bts1.py` `VOCAB_VERSION` (`:28`) → 19; `contract.py` + `class_forge.py` system-prompt vocab.
- **Archetype catalog entry** (`class_forge.py`, mirroring the F5 retain archetype): a
  "Forgemaster / signature blade" archetype — 1-2 forged-scaled payoff attacks, forge-income
  commons, a turn_start-forge engine power, optional forge relic. **This is the actual point of the
  phase: the mapping stage can only use mechanics the catalog names.** Today nothing in the harness
  can express Forge, which is why it never appears.
- Tests: `generation/tests/test_forge.py` (mirror `test_h4_triggers.py`): schema accept/reject,
  validator pairing rule, C#-emit round-trip, sentence byte-match.

**M-3 (stretch, cheap) — `when` condition `forged_ge N`** for gated payoffs ("If your Forge is
10+ …"), slotting into the existing condition framework beside `turn_at_least`/`enemy_count_ge`.
Cut freely if M-1/M-2 run long.

**M-4 — verify.** Build + deploy (csproj auto-deploys). Gap-Tester class with staged forge cards
(card income, trigger income, scaled payoff, upgrade-of-payoff). AutoSlay smoke — **ask first** —
success = forge fired N× / forged-scaled hits resolved with growing amounts in the log, 0 mod
exceptions. Then flip gap #36 to done and stamp this doc like H4's header.

## Open questions (decide during build)

- Forge amount cap / validator ceiling (suggest: forge N ≤ 5 per instance, same spirit as other
  ramp caps in `_score_effect`).
- Relic-side forge income in or out of v19 (default IN, it's one op-set entry in the relic path).
- Whether the Forge power shows a tooltip sentence explaining the payoff ("Your Forge-scaling
  cards deal/block this much more") — in-code loc makes this free, do it.

## Out of scope (kept as separate gaps)

- **#18 `upgrade_card`** (Armaments): research note — `CardCmd.Upgrade(CardModel, CardPreviewStyle)`
  is a ready-made synchronous call (`dump.txt:580`), and a **no-choice variant (random/ALL cards in
  hand) is buildable today without the F4 card-pick UI**; player-choice needs the un-dumped
  `CardSelectCmd` surface reflected first. One-shot only (`IsUpgraded` bool).
- **#23 Rampage** (per-card grow-on-play counter) — needs per-card-instance state; Forge
  deliberately avoids it via the player-level counter.
- **#3 rank-up track** — needs condition-watched multi-tier transforms; revisit after Forge + #18.
