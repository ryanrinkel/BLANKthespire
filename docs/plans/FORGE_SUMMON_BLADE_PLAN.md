# Phase T — the True Blade: summon-on-Forge (base-game-exact Forge keyword)

**Status:** DONE (2026-07-10, vocab v25) — implemented by Opus 4.8. Mod builds clean (0 errors); generation
suite green (`tests/test_forge.py` 53/53 + full suite); `--fake` bundle verified (blade token/cost 2/damage 10 +
retain, NO innate, EXCLUDED from the 10-card starting deck; `summon_blade` + `on_blade_played` cards ship). Scope
notes vs the plan below: (a) token rarity SHIPPED (decision #8) with `CanBeGeneratedInCombat:false` closing the
combat-gen leak; the one residual Uniform-odds-reward path is accepted (fall back to `basic` if it ever surfaces).
(b) the decision-#9 manipulation rule is an ADVISORY warning (`forge_manipulation_warnings`), mirroring the
sibling `forge_pairing_warnings`, rather than a hard error — the blueprint prompt is the primary enforcement.
(c) stretch op `blade_empower` CUT (filed as a future gap). AutoSlay smoke: staged a v25 Gap-Tester (slot 04,
`turn_start forge` relic → turn-1 summon every combat) — see `generation/scratch/stage_phase_t_autoslay.py`.

Handoff plan for implementation. Follow-on to `PHASE_M_FORGE_PLAN.md`
(v19 Forge counter, DONE) and `SOVEREIGN_BLADE_SCOPE.md` (Tier 1 Innate Blade, SHIPPED v20). This phase
replaces Tier 1's *innate deck card* with the base game's actual behavior and closes the scope doc's
"Tier 2" — but with a **better seed hook than the scope doc proposed**: the summon rides the `forge`
executor itself, so no combat-start trigger is needed at all.

## Goal — what "correct" means (the user's spec, confirmed against the game dump)

Base-game Forge (The Regent):

1. **Playing a Forge card summons the Sovereign Blade to your hand.** The blade is NOT in your deck and
   NOT in your opening hand — it appears when you first stoke the Forge.
2. The blade is a **2-energy Token-rarity attack with Retain that deals base damage**
   (`generation/reference/sts2_cards.json:19733-19778`: cost 2, damage 10, `Retain`, rarity `Token`,
   damage = `baseDamage + CalculationExtra × Forge`; upgrade drops cost 2→1).
3. **Each subsequent Forge play permanently buffs the blade's damage for the rest of combat**
   (the Forge counter, which the blade's damage formula reads).

We do NOT need the name "Sovereign Blade" (each class names its own weapon — already true via
`name_hint`), and "colorless" is cosmetic (ours stays class-colored — out of scope).

**User-confirmed additions (2026-07-10):**
- The blade should carry real **`token` rarity** (not `basic`), not start in the deck, and be
  **created at the first Forge** — see decision #8.
- **Every forge-archetype class must ship blade-manipulation effects** — cards that interact with the
  blade itself, the way base-game Regent support does (Parry "whenever you play Sovereign Blade, gain
  8 Block" `sts2_cards.json:15235`; "Sovereign Blade deals double damage this turn" `:4346`; Summon
  Forth retrieval `:21002`). See decision #9 + slice T-2.
- The harness should carry **game-design notes for the mechanic** (how the base game builds a Forge
  class), so the mapping/compose stages design around the blade — see slice T-3.

## What's already right vs wrong

**Right (keep):**
- The Forge counter + additive `scale:"forged"` payoff (`ForgedForgePower`, `EffectRunner.cs:120`,
  v19) — this IS behavior #3. Blade damage = printed base + Forge, live-verified in the gunsmith run.
- Exactly-one synthesized signature blade per forge class, named/themed by the LLM, `token:true`,
  never drafted/rewarded, retained (`class_forge.py:1203 _synthesize_blade`, blade-safety net `:1567`).
- Retain on the blade; per-combat counter reset.

**Wrong (this phase fixes):**
- The blade is `innate` + seeded in the **starting deck** — it opens in hand every combat for free,
  before any Forge card is played. Base game summons it on the first Forge play.
- Blade cost is 1 with base 6→9; base game is **cost 2, damage 10** (upgrade 2→1 cost).
- The generator's prompt/validator/tests all describe and enforce the innate-deck-card shape.

## Prerequisite — commit the token-pool fix first

The working tree holds an UNCOMMITTED fix in `CardSpec.cs` + `DataCard.cs` (+ `ledger.py` repairs):
tokens must stay **pool-registered (`autoAdd:true`)** — an unpooled card faults `CardModel.get_Pool()`
(MockCardPool "You monster!") and hangs combat when drawn (found in-game on "Foundry Rot"). Tokens now
stay out of rewards via **Basic rarity** (CardFactory excludes Basic everywhere), not via autoAdd.
This phase's summoned blade is resolved/rendered the same way, so **that fix must land (commit + build)
before this work starts**. Verify `git status` is clean of those files first.

---

## Design decisions (recommendations inline; confirm before build)

1. **Summon once per combat, on the FIRST Forge income.** Trigger = the `forge` executor when the
   counter was 0 before applying. After the blade is played it goes to discard and cycles through the
   combat deck like any generated card (redrawable, reshuffled) — it does NOT re-summon on later Forge
   plays. Rationale: base game ships a dedicated rare, SUMMON_FORTH "Put Sovereign Blade into your Hand
   from anywhere" (`sts2_cards.json:21000-21037`) — if every Forge play already retrieved the blade,
   that card would be redundant; so retrieval-on-every-play is NOT the base mechanic.
   *Alternative (rejected): re-summon whenever the blade is absent from hand — makes Retain pointless
   and floods the hand on trigger-income classes.*
2. **The first Forge play also stokes.** "Forge 3" as your first play summons the blade AND sets the
   counter to 3 (blade hits for 13). This matches the dump's damage formula (`baseDamage + 1 × Forge`)
   — the counter has no "skip the first" carve-out. The user's "each *subsequent* play buffs" phrasing
   is satisfied: the buff *visible on the blade you now hold* comes from every play including the first.
3. **All THREE income paths summon** — card (`EffectRunner.cs:120`), trigger payload
   (`TriggerRunner.cs:84`), relic hook (`EffectRunner.cs:496`). "At the start of your turn, Forge 4"
   summoning the blade turn 1 is correct base-game behavior. Centralize so this is free (see T-1).
4. **Blade stats: cost 2, base damage 10, Retain, `scale:"forged"`.** Match the base card. Upgrade:
   base game drops cost 2→1, but our upgrade model is **positional effect deltas only**
   (`ForgedCards.cs:343-367` reads a single int/`"X"` cost; no upgrade-cost channel) — so keep a
   **damage upgrade (10→13)** and note cost-upgrade support as a separate future gap. Do NOT build
   upgrade-cost support inside this phase.
5. **Keep our explicit card text** (`Deal 10 damage, plus your Forge.` + `Retain.`) rather than the
   base game's hidden-calc "Deal 10 damage." — clearer for generated classes; no lockstep exception.
6. **Vocab bump v24 → v25** (`ForgedCards.cs VocabVersion`, `bts1.py VOCAB_VERSION`). The bundle
   *shape* barely changes (blade loses `innate`, leaves `starting_deck`), but the RUNTIME semantics of
   `token:true` change (summoned, not seeded) — a v25 code on a v24 mod would produce a class whose
   blade never appears. Same reasoning as the v20 bump.
7. **Legacy bundles (v20–v24) keep working on the v25 mod.** Their blades are `innate` + in
   `starting_deck`; the summon guard (T-1's "blade already in combat" check) sees the blade in a pile
   and skips — old classes behave exactly as before. No re-import/repair pass needed. Legacy `basic`
   rarity blades also stay valid (decision #8's token rarity is for NEW bundles).
8. **Blade rarity `token`, gated on a CardFactory check.** The importer's `RarityMap`
   (`ForgedCards.cs:200-203`) has NO `token` entry today. Add `["token"] = CardRarity.Token`
   (verify the enum member exists — base game stamps `"rarity_key": "Token"` on the blade) and allow
   it ONLY on the `token:true` card (reject `token` rarity on ordinary cards, mirroring the existing
   `allowBasic` gate at `:325`). **Before switching, verify CardRarity.Token is excluded from every
   merchant/reward/combat-generation CardFactory path** (expected — base-game tokens never drop) AND
   that the pool-resolution fix (`autoAdd:true`, see prerequisite) still resolves `get_Pool()` for a
   Token-rarity card. If either check fails in-game, fall back to `basic` rarity (the current
   uncommitted-fix behavior) and note it — the summon mechanic does not depend on the rarity label.
9. **A forge class MUST ship ≥1 blade-manipulation card** — an effect that interacts with the blade
   itself, beyond plain Forge income. In-vocab means (slice T-2): `summon_blade` retrieval, an
   `on_blade_played` trigger rider, or (stretch) `blade_empower`. Enforced class-level in
   `character_validator.py` beside the forge-pairing rule; the blueprint prompt demands it so the
   validator rarely has to bite.

---

## Build slices

### T-1 — mod: the summon hook (the core mechanic — ship this first, it stands alone)

Centralize Forge income in ONE place so the summon can't drift across the three paths:

- **`ForgedForgePower.Stoke(PlayerChoiceContext ctx, Player owner, int amount)`** (new static, in
  `Powers/ForgedForgePower.cs` or a small `Engine/ForgeRunner.cs`):
  1. `before = ForgeStacks(owner)` (helper already exists — see `EffectRunner.cs:124,499`).
  2. `await Apply(ctx, owner, amount)` (existing).
  3. If `before == 0`: summon the blade —
     - `k = ForgedCharacters.ClassIndexOfPlayer(owner)`; find the class's token card id (the CardSpec
       with `IsToken` — add a small `ForgedCharacters.BladeCardId(k)` lookup; specs are already indexed
       per class). No token card → log + skip (a forge class without a blade is the pre-v20 case).
     - **Guard: skip if the blade is already in combat** (scan hand/draw/discard/exhaust piles for the
       blade's model type). This is both the legacy-innate compat (decision #7) and a double-summon
       belt-and-suspenders. Precedent for pile scans: the discard executor walks the hand
       (`EffectRunner.cs` Phase R region); HandStateTracker reads piles too.
     - Resolve + add exactly like Phase Q: `ForgedCharacters.ResolveClassCardModel(k, bladeId, owner,
       null)` → `CardPileCmd.AddGeneratedCardToCombat(model, PileType.Hand, owner,
       CardPilePosition.Random)` (see `EffectRunner.AddCards`, `EffectRunner.cs:283-304`). The blade has
       no `add_card` effects, so depth-1 discipline can't refuse it.
     - Log `[T] blade summoned: '<id>' (first Forge of combat)`.
  4. **Factor the summon body into a reusable `SummonBlade(ctx, owner, fromAnywhere:)` helper** — T-2's
     `summon_blade` op is the same code with two differences: it also MOVES an existing blade from
     draw/discard back to hand ("from anywhere"), and it ignores the counter.
- **Swap the three call sites** (`EffectRunner.cs:120-125`, `:496-500`, `TriggerRunner.cs:84-88`) from
  `ForgedForgePower.Apply(...)` to `Stoke(...)`. Keep the existing per-site log lines.
- **Power tooltip** (`ForgedForgePower.Localization`, `ForgedForgePower.cs:35-38`): rewrite — e.g.
  "Your first Forge each combat summons your signature blade to your hand. Effects that add your Forge
  deal or block that much more; resets each combat."
- **`VocabVersion` 24 → 25** (`ForgedCards.cs:45` region).
- NO codegen/slot changes: the blade keeps its pool slot (of 40), it's just never deck-seeded.

### T-2 — mod: token rarity + the blade-manipulation vocabulary

The importer work for decisions #8/#9. All under the same v25 bump.

- **Token rarity** (`ForgedCards.cs`): `RarityMap` + `["token"] = CardRarity.Token` (`:200-203`);
  validation — `token` rarity legal ONLY when the card carries `token:true`, and a `token:true` card
  should BE token rarity (accept legacy `basic` for old bundles); update the error text at `:319`.
  Run decision #8's CardFactory/reward-exclusion + `get_Pool()` checks in-game before relying on it.
- **Op `summon_blade`** (Summon Forth analogue, "put your blade into your hand from anywhere"):
  executor calls T-1's `SummonBlade(..., fromAnywhere: true)` — if the blade is in draw/discard/exhaust,
  MOVE it to hand (find the pile-move command near `CardPileCmd` — `AddGeneratedCardToCombat`'s
  neighbors in the reflection dump; spike this call the same way Phase Q spiked its add); if absent
  entirely, generate it; if already in hand, no-op. Allowed on cards and in trigger payloads
  (`SupportedOps`/`TriggerOps`, `ForgedCards.cs:69-79,136-141`); no amount. `Describe`: `Put your
  <blade name> into your hand from anywhere.` — resolve the class's blade title at describe time.
- **Trigger kind `on_blade_played`** (Parry analogue, "Whenever you play your blade, <payload>"):
  clone the `on_card_played` reactive path (`ForgedTriggerPower.cs:142-147`, registered kinds
  `ForgedCharacters.cs:374`, `ForgedCards.cs:136`) with one added filter — the played card's spec
  `IsToken` (the played card is a `DataCard`; read its `Spec`). Sentence at `ForgedCards.cs:931`
  region: `Whenever you play your <blade name>`.
- **STRETCH — op `blade_empower`** ("your blade deals double damage this turn", `sts2_cards.json:4346`):
  a turn-scoped player power (`ForgedBladeEmpowerPower`, expires end of turn like the temp-stat powers);
  the blade's damage site consults it when the playing card's spec `IsToken` (the forged-scale read,
  `EffectRunner.cs` FromState region, already has the card in scope). Cut freely if T-1/T-2 run long —
  the validator rule (T-3) accepts any ONE manipulation form.
- **OUT (future gaps, do not build):** permanent blade mutations — "now hits ALL enemies"
  (`:18336`), "+1 hit / cost change" (`:21380`) — these need per-combat card-model mutation, a
  different machinery class. File in `VOCABULARY_GAPS.md`.

### T-3 — generation lockstep

- **`_synthesize_blade`** (`class_forge.py:1203-1221`): drop the `{"op":"innate"}` effect (keep
  damage-forged + retain, in that order); `cost: 1 → 2`; `rarity: "basic" → "token"`;
  `_BLADE_BASE_DAMAGE 6 → 10`, `_BLADE_UPGRADE_DAMAGE 9 → 13` (`class_forge.py:1193-1194`).
- **Starting deck**: the blade must NOT be in `starting_deck` and must NOT count toward the
  exactly-10 (`STARTING_DECK_SIZE`, `class_forge.py:92`). Today `n_sig` counts signatures + blade
  (`:1595-1599`) — exclude `_BLADE_ROLE` there and wherever deck refs are assembled, so the 10 fills
  from basics/signatures without it. KEEP the blade in the cap-guard protected set (`:1586`) and out of
  MIN_RARES/merchant-type pool counts (unchanged).
- **Prompt + the GAME-DESIGN notes** (`class_forge.py:276-290` FORGE block, `:390` role template,
  `:399` rules, + the archetype catalog's `forge_ramp` entry): rewrite the FORGE block as a compact
  design brief for HOW the base game builds this class, so the mapping/compose stages design around
  the blade rather than just sprinkling the op:
  1. *The blade is the win condition*: NOT in your deck — your FIRST Forge each combat CREATES it in
     your hand (2-energy token, retains, damage = printed base + your Forge).
  2. *Income is the curve*: numeric Forge riders spread across cheap commons ("Deal 5 damage.
     Forge 3.") + at least one engine source (turn_start trigger or relic hook, "At the start of your
     turn, Forge 2") + a rare big-stoke spike.
  3. *Manipulation is the texture* (REQUIRED, ≥1 card): support that touches the blade itself —
     retrieval (`summon_blade`, the Summon Forth pattern), on-play riders (trigger
     `on_blade_played` → block/draw/energy, the Parry pattern), or a this-turn empower
     (`blade_empower`, stretch). A forge class with income but no blade interaction is flat.
  4. *Payoffs stay concentrated*: the blade is the PRIMARY forged payoff; at most 1 extra
     `scale:"forged"` card (unchanged rule).
- **Validator**:
  - `validator.py` / blade-shape rule: the blade card = `token:true` + `retain` + one
    `damage scale:"forged"`, **no `innate`**, cost 2, rarity `token`. Reject an innate token at v25.
    Accept the new op/trigger (`summon_blade`, `on_blade_played`, stretch `blade_empower`) ONLY on
    forge classes (same gating style as orb/summon ops).
  - `character_validator.py:349-405`: `signature_blade` role no longer counts as a starting-deck
    card (update the role accounting + the `:383` comment); still at most 1; forge-pairing
    (`:147-164`) unchanged (blade still auto-satisfies the payoff half). **NEW class-level rule
    (decision #9): a forge class must ship ≥1 blade-manipulation card** (`summon_blade` /
    `on_blade_played` / `blade_empower` anywhere in base/upgrade/payload effects) — error, worded
    like the forge-pairing message.
  - `class_forge.py:758-761` blueprint check: unchanged (exactly-one rule stays).
- **`cardgen.py` lockstep**: byte-match the new sentences — `summon_blade` (`Put your <blade> into
  your hand from anywhere.`), `on_blade_played` trigger header (`Whenever you play your <blade>`),
  stretch `blade_empower`. Note: these sentences embed the class's blade NAME — the describe path
  needs the class context (the character bundle carries the blade card; both sides resolve the title
  the same way, byte-matched as always).
- **`bts1.py` `VOCAB_VERSION` → 25**; `contract.py` + system-prompt vocab text; schema
  (`mod/contract/card.schema.json`): rarity enum + `token`, op enum + `summon_blade` (+
  `blade_empower` if built), trigger enum + `on_blade_played`, `token` doc rewritten to the summon
  semantics; `mod/contract/VOCABULARY.md` rows for all of the above.
- **Fakes**: the `--fake` forge class + `_CardFake` forge branch (`class_forge.py:1758-1772`) — blade at
  cost 2/damage 10/rarity token, no innate, absent from the fake's starting_deck; give the fake ONE
  manipulation card (e.g. a Parry-style `on_blade_played` skill) so the new validator rule is
  exercised offline.
- **Tests** (`generation/tests/test_forge.py`): update blade-shape cases (no innate, cost 2, rarity
  token, 10/13); NEW cases — blade excluded from starting_deck, starting deck still exactly 10, v25
  stamp, innate token rejected, token rarity rejected on non-token cards, manipulation-rule
  fires/passes, `summon_blade`/`on_blade_played` emit + sentence byte-match. Full suite green.

### T-4 — verify

1. `git status` clean of the prerequisite fix; mod build 0 errors (csproj auto-deploys).
2. Generation suite green; forge a `--fake` class end-to-end; import a real staged forge class
   (e.g. the gunsmith) to confirm legacy v20-v24 bundles still load and keep innate behavior.
3. Stage a fresh v25 forge Gap-Tester (card + trigger + relic income, forged payoffs) and AutoSlay
   smoke (run without asking — the ask-first preference was superseded 2026-07-06). Success:
   - Turn 1: blade NOT in opening hand; first `[M] forge` log is immediately followed by
     `[T] blade summoned`; blade visible in hand.
   - Subsequent forge income: counter climbs, NO second summon log; blade damage grows
     (`forged payoff: damage base 10 + Forge N`).
   - Blade played → discard; later drawn again normally; retains when held.
   - Blade never offered in rewards/merchant; not in the compendium (specifically re-verify with
     TOKEN rarity — decision #8's exclusion check, in-game).
   - Trigger-income and relic-income classes also summon (cover at least one).
   - Manipulation ops fire: `summon_blade` retrieves the blade from discard to hand;
     `on_blade_played` payload fires when the blade is played and NOT for other cards.
   - 0 mod exceptions across a full run.
4. Stamp this doc DONE + update `SOVEREIGN_BLADE_SCOPE.md` (Tier 2 superseded by this phase) and
   `VOCABULARY_GAPS.md` if it tracks the blade item.

## Out of scope

- Upgrade-cost delta (base blade upgrades 2→1 energy) — needs an upgrade-cost channel in the importer
  + `CardSpec`; file as a new vocab gap.
- Permanent blade mutations ("now hits ALL enemies" `sts2_cards.json:18336`, "+1 hit / cost change"
  `:21380`) — per-combat card-model mutation, a different machinery class; file as vocab gaps.
  (`summon_blade` retrieval + `on_blade_played` riders ARE in scope — slice T-2.)
- Colorless/token card frame cosmetics; run-persistent Forge; base-game `AfterForge` machinery
  (ours stays parallel/closed-vocab).
