# Vocabulary Expansion — Wave 5 Plan (gaps #52–#61)

**Written 2026-09-30 from a four-scout verify-first pass over `VOCABULARY_GAPS.md` #52–#61 (live vocab v55,
Phase BA; last engine phase 075fb25 summon HP cap).** The ten gaps were captured in the 2026-09-29 archetype
copy review, all at Ryan's request, and every one of them now has a named engine surface — none needs a spike.
Each phase below carries the lockstep file list, the describe strings both sides must byte-match, the
harness wiring that makes the mechanic reachable from the class forge, the test file, and the AutoSlay gate.

**Scout caveat:** every `file:line` below came from an automated scout pass on 2026-09-30. **Re-grep the symbol
before trusting a line number** — names are authoritative, numbers are hints.

**Where the game sources are:** the decompiled game and BaseLib are NOT in this repo. They live in the sibling
checkout `C:\Users\ryanr\Desktop\NOVOGODOT\BLANKthespire\_modref\` (`decomp_full\`, `BaseLib-StS2\`). Below,
`DECOMP\` means `_modref\decomp_full\`.

**Status legend:** `VOCABULARY_GAPS.md` entries #52–#61 are all `captured`. Flipping an entry to `planned` is the
go signal for its phase; flipping it to `done` at ship is what `frontend/catalog.py:gap_status` reads to mark an
archetype BUILDABLE (`test_archetypes.py:80` pins the flag).

---

## 0. Ground rules (carry over from `VOCAB_EXPANSION_4_PLAN.md` §0; load-bearing ones repeated)

- **0.1 Lockstep or nothing.** A vocab change ships across ALL of: `mod/BlankTheSpireCode/Engine/`
  (`ForgedCards.cs` SupportedOps/TriggerOps/AmountOps/KeywordOps/Validate/ValidateTrigger/Describe/VocabVersion ·
  `EffectRunner.cs` · `TriggerRunner.cs` · `DataCard.cs` · `CardSpec.cs` · `Conditions.cs`) + `mod/contract/
  card.schema.json` + `mod/contract/VOCABULARY.md` + `generation/btsgen/` (`cardgen.py` · `validator.py` ·
  `census.py` · `bts1.py` VOCAB_VERSION · `coverage.py` · `featured.py` · `harness_v2.py` · `gate.py` ·
  `class_forge.py` · `data/archetypes.json` · `data/exemplar_pool.json`) + `web/static/app.js` / `render.js`
  renderers. The full per-item checklist is §1.
- **0.2 Describe text is a byte-match contract.** `cardgen.describe()` == `ForgedCards.Describe()`. Every phase
  test asserts both strings.
- **0.3 AutoSlay validation is by godot.log tags, not the tool verdict.** Pass bar per run: ≥1 phase tag fired ·
  0 mod exceptions · no BlankTheSpire frame in a stall stack. The merchant map-nav watchdog FAIL is expected.
- **0.4 / 0.5 Choice + deck-thinning testers** are all-aggression decks; grep `Auto-selected` to confirm the
  picker resolved (`AutoSlayCardSelector`). Only reuse base-game `CardSelectorPrefs.*Prompt` loc keys — an
  invented key is the gap-#26 crash.
- **0.6 STOP rules.** Verify-first contradicts the spec → STOP that phase, write findings into its section, move
  on. C# build breaks unrecoverably → revert the phase, record why.
- **0.7 Commit convention.** One commit per phase: `mod+forge: Phase <XX> — <mechanic> (vocab v<N>)`; mod-only
  UX phases `mod: Phase <XX> — …` (no vocab bump).
- **0.8 Vocab versions** are assigned in build order from **v56**. Reorder → renumber.
- **0.9 Prompt budget — READ §2 FIRST.** `test_rule_0_9_v2_is_the_worst_case` has **13 characters** of
  headroom today; the first VOCABULARY.md row of this wave trips it. The scaffold budget has 426.
- **0.10 Phase tests run under pytest.** Expose `def test_phase_<xx>_all(): assert main() == 0` (the AK/BA idiom).
  AX/AY only exposed `test_version`, so their real checks never run under `uv run python -m pytest` — don't repeat
  that. Run from `generation/` with `uv run python -m pytest` (bare `uv run pytest` can import the other checkout).
- **0.11 Release ordering.** The codec (`BTS1Codec.cs:65-67`) rejects codes newer than the installed mod, so the
  mod zip + Workshop item ship BEFORE the web deploy. Recommended: build BB→BF on one branch, one mod release
  at the end (see §4), per-phase commits.

### Standard commands

```powershell
# generation-side
cd generation
uv run python -m tests.test_phase_bb          # standalone
uv run python -m pytest                        # full suite

# C# (Program Files dotnet is runtime-only)
~/.dotnet/dotnet.exe build mod/BlankTheSpire.csproj -c Debug      # close the game first

# AutoSlay smoke (tester staged into slot 04; verdict FAIL on map-nav is expected)
cd generation
uv run btsgen-autoslay-smoke --seeds GAPTESTBB1 GAPTESTBB2 --character class4 --relic auto --build --timeout 900
# gate: grep godot.log for "[BB]" tags, "Auto-selected", and 0 mod exceptions
```

---

## 1. Harness wiring — the checklist every phase walks

This is the "add them to the creative harness" half. A token is only *reachable* by the class forge when all of
these see it; the engine alone makes it *legal*.

**Contract (everything else reads these)**
1. `mod/contract/card.schema.json` — op enum `$defs.effect.properties.op.enum` (:35); `triggerEffect.op.enum`
   (:199) ONLY if legal as a payload; per-op `if/then` rules in `allOf`; condition kinds `$defs.condition.kind`
   (:283); trigger kinds `effect.trigger.enum`. The effect object is `additionalProperties:false` (:32) — every new
   effect FIELD must be declared here.
2. `mod/contract/VOCABULARY.md` — op row `| \`op\` | args | **Name** (vNN) — … |` (Effect ops :7), condition row
   (:200-221), trigger kinds named in the `add_trigger` row (:30) + Triggers prose (:233). Pasted WHOLE into the
   blueprint prompt (`class_forge.py:257/265`) and card prompt (`contract.py:311/327`).
3. `generation/btsgen/bts1.py:28` — bump `VOCAB_VERSION`, add a `"NN: Phase XX — …"` comment line (the phase
   `test_version` greps for it). No table: codes are `MAGIC.<ver>.b64(gzip(json)).crc32`; new keys ride through.

**Card text + C# emit**
4. `cardgen.py` — `describe()` (:464) branch; `cond_phrase` (:278) for a `when` kind; `trigger_sentence` (:414)
   + `_trigger_fragment` (:336) for a trigger; `effect_literal` (:152) named arg for any field that must reach
   C# (`Grow:`, `OncePerCombat:` style, :236-252).

**Validator / pricing**
5. `validator.py` — `_BUILD_AROUND_OPS` (:59-75) so the op isn't scored as a plain stat line; caps constants
   (:171 style); `_MULTI_FIRE_TRIGGERS` (:106) / `_ONCE_PER_COMBAT_TRIGGERS` (:113); `_engine_structural_errors`
   (:405) per-op shape rules + the "not on a BASIC" idiom (:815-822) + the card-only rejection for payloads
   (:1022); `_score_effect` (:1112) pricing.

**Census / coverage / featured / harness**
6. `census.py` — `cc.ops` counts ops automatically (:139); a new FIELD or flag needs a counter + `_walk_effects`
   branch (:128-189), the `Census` aggregate (:222-251, :279, :311-325) and a `format_report` line (:432 style).
   Keyword-style nullary ops go in `KEYWORD_OPS` (:62) — `test_census.py:165/214` pins the exact set.
7. `bridges.py:40-52 card_tokens` — a non-op FIELD an archetype lists in `vocabulary.ops` must be surfaced here
   (as `unblockable` is) or the bridge witness check can't see it.
8. `coverage.py` — `WHEN_MENU_V2` (:79) / `REACTIVE_MENU_V2` (:75) / `SCALE_MENU` (:115) / `KEYWORD_MENU` (:150);
   kind-gated `WHEN_MENU_KIND` (:103) / `SCALE_MENU_KIND` (:137). `DIRECTIVE_BY_KEY` + `CENSUS_DETECTOR` derive
   from the menus (a detector only works if the census counts the token). **There is no op menu** — ops reach the
   repair round only through featured entries. `test_coverage.py:222/218/265` pin exact key sets + need a `samples`
   entry per key.
9. `featured.py` — `Featured(id, injection, directive, detect, exclusion, min_cards, detect_pool)` (:36-53);
   base ops → `FEATURED_MENU` (`contagion` :186-190 is the template); class-kind ops →
   `FEATURED_CLASS_KIND[kind]` (:202-299; kinds pinned to orb/status/summon/forge/balance/discard/transform by
   `test_featured.py:237`). `test_featured.py:164/290` need a sample per entry.
10. `harness_v2.py` — `_PREFERRED_OPS` (:62) / `_PREFERRED_CONDITIONS` (:67) / `_PREFERRED_TRIGGERS` (:70);
    `compositional_clause` (:119) only names tokens also present in VOCABULARY.md and lands in the CARD prompt.
11. `gate.py` — give the op a home: `CORE_OPS` (:104), `GATED_OP_ORDER` (:108) or a `FAMILY_OPS` family (:93);
    a new field needs a `FIELD_UNITS` entry (:116). `test_vocab_gate.py:104` fails on a schema op with no
    VOCABULARY row.
12. `class_forge.py` — blueprint prose that names ops (translation paragraph :270-281, archetype pitch sections
    :338-598), `_PRUNABLE_SECTIONS` keep-sets + ALSO-AVAILABLE pitch (:1007-1033), `_ORB_CONDITION_KINDS` (:2096)
    for any new condition (`test_phase_ar.py:184-198` asserts schema == C# `Conditions.Kinds` == this set), the
    condition uptime heuristic (:1383-1384). **All of this counts against `BP_SCAFFOLD_BUDGET`.**

**Catalog + exemplars + heuristics**
13. `data/archetypes.json` — the archetype's `vocabulary.ops` (NOT a top-level `ops`) += the new token; reword
    `build_notes` to point at it; every token must appear backticked somewhere in VOCABULARY.md
    (`test_archetypes.py:122`). Archetype ids for this wave: `ascetic_purge` (:532), `exhaust_pyre` (:2624),
    `strike_tempo` (:1054), `forge_ramp` (:147), `burst_window` (:3724), `madness_discard` (:2371),
    `poison_attrition` (:687), `retain_hold` (:5), `ambush_alpha` (:3390), `countdown_ripen` (:2178),
    `balance_gauge` (:2288).
14. `data/exemplar_pool.json` — ≥1 exemplar per new op / condition / trigger (`test_exemplars.py:143`);
    class-only tokens carry a `needs` tag; every exemplar validates under `harness_v2.exemplar_validator()`.
15. `DESIGN_HEURISTICS.md` — a balance note per mechanic (`archetype_balance_note` feeds `prompt_block`).
16. `VOCABULARY_GAPS.md` — the gap's Status → `done`, with the phase + version stamped.
17. `web/static/app.js` (`case "op":` renderer) + `web/static/render.js` (condition phrase :505 style) — the
    site's card preview is a third, looser copy of describe.

---

## 2. Rule 0.9 — the budget, settled up front (do this in Phase BB, not later)

Readings taken 2026-09-30 (`tests/test_harness_v2.py:330-410`, `_BlueprintContract(mode="dossier", triad=True,
seed=1).system_prompt()`, characters):

| Assert | Ceiling | Now | Headroom |
|---|---|---|---|
| `test_rule_0_9_blueprint_scaffolding_stays_within_budget` (:384) — prompt minus VOCABULARY.md, v2 | `BP_SCAFFOLD_BUDGET = 46_000` (:352) | 45,574 | **426** |
| `test_rule_0_9_total_prompt_stays_under_the_tripwire` (:395) | `BP_TOTAL_TRIPWIRE = 120_000` (:355) | 104,165 | ~15.8k |
| `test_rule_0_9_v2_is_the_worst_case` (:405) — flag-off prompt vs `BP_READING` | `BP_READING = 104_075` (:372) | 104,062 | **13** |

- **`BP_READING` / `BP_READING_V1` / `BP_READING_SCAFFOLD` (:372-374) are snapshots, not budgets.** VOCABULARY.md
  rows are exempt from the scaffold rule by design (AZ decision: "a phase that adds an op MUST document it") but
  they grow the flag-off reading too, so BB must re-take the three readings and update them in ONE commit with
  the numbers in the message. Do not pin a private ceiling in `test_phase_bb.py`.
- **The scaffold rule has teeth: 426 chars for the whole wave.** Every prose addition in `class_forge.py` (item
  12) is paid for by a cut. Budget per phase: **≤ +60 net scaffold chars**, and prefer the ALSO-AVAILABLE
  one-liner + `_PRUNABLE_SECTIONS` keep-set over new pitch paragraphs. Candidate cuts: the `blade_empower` clause
  in the Forge section (:500) once `vigor` exists; the "not yet" style residue the prompt-vs-vocab sweep flags.
- VOCABULARY.md is 58,591 chars. Six new op rows + two condition/trigger rows ≈ +1,200 → total ~105.4k, well
  under the 120k tripwire. The shrink lever (kind-gating the vocab paste) stays scoped, not built.

---

## 3. Phases

Ordered by cost-to-first-green, so the lockstep + budget mechanics are proven on the trivial phase first.

### Phase BB — Tempo keywords: `turn_at_most` + `sly` (v56; ~½ day)
Gaps **#59**, **#55**. Both are mirrors of things the engine already runs.

**#59 `turn_at_most {value}`** — `Conditions.cs:25` `Kinds` += ; `:54` value≥1 check += ; `:120-121` add
`case "turn_at_most": return player.Creature.CombatState.RoundNumber <= c.Value;`; `:175` phrase. Schema `:283`
enum + copy the `:301-304` required-value block. Python: `cardgen.cond_phrase`, `coverage.WHEN_MENU_V2`,
`class_forge._ORB_CONDITION_KINDS` (:2096) + the uptime heuristic (:1383: mirror `(value)/6`), `harness_v2.
_PREFERRED_CONDITIONS`, `render.js:505`. Relic condition lists stay untouched (relics don't need it).
- Describe (both sides): condition phrase **`it is turn {N} or earlier`** (turn_at_least renders `it is turn {N}+`).
- Note for the vocabulary row: `{"kind":"turn_at_least","value":N+1,"negate":true}` already means the same thing;
  the new kind buys legible card text, which is the point for Ambusher.

**#55 `sly` keyword** — the base game implements it: `CardKeyword.Sly` (`DECOMP\…\CardKeyword.cs:26`), the free
play lives inside `CardCmd.DiscardAndDraw` (`CardCmd.cs:172-205` → `AutoPlay(..., AutoPlayType.SlyDiscard)`, free,
random enemy target). Every mod discard already uses the batch overload (`EffectRunner.cs:564, 585, 681`), so
Sly fires with zero mod plumbing. Add: `DataCard.cs:174-177` `case "sly": WithKeyword(CardKeyword.Sly,
KeywordUpgrade("sly"))`; the upgrade-adds-keyword switch (:267-282); a no-op case at `EffectRunner.cs:251-257`;
`ForgedCards.KeywordOps` (:523) + `UpgradeAddableKeywords` (:519) + `SupportedOps` (:381) + sentence (:1823-1826).
Schema op enum. **Do NOT route Sly through `DataCard.AfterCardDiscarded`** — it would double-fire beside the native
path. Turn-end flush uses `CardPileCmd.Add`, not `Discard`, so end-of-turn never triggers Sly (matches the base game).
- Describe: **`Sly.`** (the keyword idiom, like `Retain.`).
- **Decision to make (default: accept):** `Scry` discards from the draw pile through the same batch call
  (`EffectRunner.cs:681`), so a scried Sly card auto-plays. The base game's Sly text says "from your Hand";
  default is to accept the quirk and note it in the row; the alternative is filtering Sly cards out of scry's
  discard list.
- Validator: `sly` requires at least one discard outlet on the class is a CLASS-level check → `character_validator`
  warning, not a card error. Card-level: not on a Power (Powers are never in hand to be discarded meaningfully) and
  not with `retain` (contradictory identity).
- Harness: `sly` is NOT a `KEYWORD_MENU` entry (that menu's quota would push Sly onto classes with no discard
  outlet). Instead `FEATURED_CLASS_KIND["discard"]` += a `sly_pitch` entry whose `detect` needs ≥1 `sly` card AND
  ≥1 `discard`/`scry` op; `census.KEYWORD_OPS` += `sly` (update the pinned set in `test_census.py`);
  `madness_discard.vocabulary.ops` += `sly`, build_notes already name Sly. `turn_at_most` → `ambush_alpha`.
- **Budget:** VOCABULARY rows (2) + re-take `BP_READING*`. Scaffold delta target 0: the ambush pitch already says
  "strongest early"; add the token to a `_PRUNABLE_SECTIONS` keep-set only.
- **Test:** `tests/test_phase_bb.py` (+ pytest wrapper). Gap Tester: Ambusher-flavoured deck with a Sly attack and
  a `turn_at_most 2` bonus, random `discard 1` outlets everywhere; grep `[BB]` tags (log a `[BB] sly autoplay` line
  from an `AfterCardPlayed` check on `AutoPlayType`, or just grep the game's own AutoPlay log) and the turn-gated
  condition read.

### Phase BC — Hand ops: `exhaust_card` + `draw_until` (v57; ~1 day)
Gaps **#52**, **#53**. Both copy a base-game card recipe verbatim and share one contract change: widening
`card_type`, which today is hard-wired to `cost_shift` (`ForgedCards.cs:989-990`, schema :45).

**Shared:** `card_type` enum += `non_attack` (Second Wind / Pillage both want it); the rule "`card_type` only on
cost_shift" becomes "on cost_shift | exhaust_card | draw_until". Pull the string→`CardType` mapping in
`ForgedCostShiftPower.cs:121-124` into a shared helper.

**#52 `exhaust_card {cards: choose|random|up_to|all, amount?, card_type?}`** — modelled on `discard`
(`EffectRunner.cs:343-353`, `DiscardRandom :549`, `DiscardChoose :576`). Picker `CardSelectCmd.FromHand` +
`CardSelectorPrefs.ExhaustSelectionPrompt` (`DECOMP\…\CardSelectorPrefs.cs:13`; ctor `(prompt, n)` :62 for
`choose`, `(prompt, 0, N)` :68 for `up_to`), random via `owner.RunState.Rng.CombatCardSelection`, then
`CardCmd.Exhaust(ctx, card)` **once per card** (`CardCmd.cs:237` — the doc says never bulk it). Base recipes:
Burning Pact (choose 1), True Grit (random), Second Wind (all non-Attacks), Purity (up to N). `on_exhaust` fires
for free via `ForgedTriggerPower.AfterCardExhausted` (:141-146). Rules: `cards` legal on upgrade_card/discard/
retrieve_card/exhaust_card (`:1230-1231`); `PickModes` (:497) += `up_to`, `all`; NOT a trigger payload (choice
UI, rule 0.5); `amount` required for choose/random/up_to, forbidden for `all`; `all` requires `card_type`.
- Describe: `Exhaust a card in your hand.` (choose 1) / `Exhaust {N} cards in your hand.` (choose N) /
  `Exhaust a random card in your hand.` / `Exhaust {N} random cards in your hand.` / `Exhaust up to {N} cards in
  your hand.` / `Exhaust all non-Attack cards in your hand.` / `Exhaust all Skills in your hand.`
- Pricing (`_score_effect`): exhausting your own cards is a COST when the card has no `on_exhaust` engine and a
  PAYOFF enabler when it does; price `choose 1` ≈ −1.0, `random N` ≈ −1.5·N, `all non_attack` ≈ −3 (Second Wind
  gives 5 Block per card exhausted — the payoff is elsewhere on the card).
- Harness: `FEATURED_MENU` += `exhaust_fuel` (detect: ≥1 `exhaust_card` AND ≥1 `on_exhaust` trigger or
  `retrieve_card pile:exhaust`); `exhaust_pyre.vocabulary.ops` += `exhaust_card`, `ascetic_purge` += `exhaust_card`
  (build_notes: "Exhaust, ethereal and purge effects let the player manipulate their deck size" → name the op);
  `harness_v2._PREFERRED_OPS`; `gate.py` FAMILY_OPS exhaust family (verify the family exists; else `GATED_OP_ORDER`).
- Rule 0.4 tester: every non-tester card is aggressive damage.

**#53 `draw_until {card_type}`** — `CardPileCmd.Draw(ctx, player)` single-card overload (`DECOMP\…\CardPileCmd.cs:
787`, returns null when nothing drawn; handles reshuffle, `Hook.ShouldDraw`, `AfterCardDrawn`). Loop per Pillage
(`Pillage.cs:28-33`): stop when the drawn card matches `card_type`, when `Draw` returns null, or when the hand is at
`CardPile.MaxCardsInHand` (= 10, `CardPile.cs:21`). Semantics: **draw until you draw a card of `card_type`**;
Pillage = `card_type: non_attack`. `DataCard` fall-through list (:178-206), no card variable. Card-only (not a
payload) in v57 — a payload form is a later add if wanted.
- Describe: `Draw cards until you draw a non-Attack.` / `Draw cards until you draw a Skill.` / `… an Attack.` /
  `… a Power.`
- Pricing: expected draws depend on deck density; price as `draw 2` (≈ the base Pillage rate) and let the class
  validator warn when the class has < 30% cards of the target type (a Striker asking for `non_attack` on an
  all-Attack deck draws its whole pile — cap the loop at 10 draws as a safety net and log `[BC] draw_until cap`).
- Harness: `strike_tempo.vocabulary.ops` += `draw_until`, `ascetic_purge` += `draw_until`; `_PREFERRED_OPS`;
  no featured entry (it's a tool, not an identity).
- **Test:** `tests/test_phase_bc.py`. Gap Tester: Pyre deck — Burning Pact clone, Second Wind clone, a Pillage
  clone, one `on_exhaust: gain 2 Block` power; grep `[BC]` + `Auto-selected` + the `on_exhaust` fire lines.

### Phase BD — Held-card fields: `grow_held` + `held_discount` (v58; ~1 day)
Gaps **#57**, **#58**. Key finding: **the game has a retain hook the mod never used** —
`AbstractModel.AfterFlush(ctx, player, flushedCards, retainedCards)` (`DECOMP\…\AbstractModel.cs:732`), dispatched
to every card in the player's piles exactly like `AfterCardDiscarded` (`DataCard.cs:342-356` documents that reach).
Base-game precedent: relic Bookmark iterates `retainedCards` and calls `EnergyCost.AddUntilPlayed(-1)`. Note
`CombatManager.FlushPlayerHand` (`CombatManager.cs:1315-1349`) runs `EndOfTurnCleanup()` AFTER `AfterFlush`, so
"this turn" cost modifiers made there are wiped — use `AddThisCombat`.

**Engine (shared):** `DataCard` overrides `AfterFlush`; if `retainedCards.Contains(this)` → `_turnsHeld++` (a
per-instance field beside `_onDiscardLastRound`, `DataCard.cs:331-333`), then apply the discount. **Verify first:**
`_turnsHeld` must start at 0 per combat — confirm combat cards are fresh clones (the `AfterCloned` note at :290-292)
or reset it by combat round like `_onDiscardLastRound`. Only ever mutate it on the in-combat instance (AfterFlush
only reaches those, so this holds by construction).

**#57 `grow_held: N`** — an effect FIELD on `damage` or `block`, the mirror of `grow` (`CardSpec.cs:84`, parse
`ForgedCards.cs:924-926`, rules :1039-1049, joins the **one-calc-var budget** at :1288-1292 and
`validator.py:686-690`, rejected in payloads :1509-1512). Display: `DataCard.cs:150` gains a branch
`WithCalculatedDamage(0, HeldBonusFor(e, up))` where the bonus is `e.Amount + up + e.GrowHeld * _turnsHeld`; block
gets the same via `WithCalculatedBlock` (:158 — today only scaled block has a calc-var path, so this is a new
branch and its text token is `{CalculatedBlock}`). Requires `retain` on the same card (validator + C# Validate).
Schema: `grow_held` in the effect object (:44 style) + an `if/then` → op ∈ {damage, block} ∧ card has `retain`.
`cardgen.effect_literal` emits `GrowHeld: N`.
- Describe: `Deal {CalculatedDamage} damage. Grows by {N} each turn it is retained.` /
  `Gain {CalculatedBlock} Block. Grows by {N} each turn it is retained.` (the `grow` sentence shape, :1799-1800).
- Pricing: like `grow` (≤ amount, 1..9) but discount the expected uptime — a held card costs tempo; price
  `grow_held N` at ~0.6× the `grow` value.

**#58 `held_discount` (flag-op, amount default 1)** — Sands of Time / Establishment. In `AfterFlush`:
`EnergyCost.AddThisCombat(-amount)` (`DECOMP\…\CardEnergyCost.cs:319`; `GetWithModifiers :94` floors at 0 and
skips X-cost). Keyword-style nullary-with-amount op like `retain`; requires `retain`; not on 0-cost or X-cost
cards; not a payload. Log `[BD] held_discount <card> now costs <n>`.
- Describe: `Costs {N} less for each turn it is retained.` (N=1 → `Costs 1 less for each turn it is retained.`).
- Pricing: `−0.8 × amount` on a cost ≥2 card; validator: at most one `held_discount` card per class rare/uncommon.

- Harness: `retain_hold.vocabulary.ops` += `grow_held`, `held_discount`; `bridges.card_tokens` += `grow_held`
  (it's a field, item 7); `census` counters for both + `KEYWORD_OPS` += `held_discount`; `FEATURED_CLASS_KIND`
  has no `retain` kind (pinned set) → `FEATURED_MENU` += `patience_payoff` (detect: ≥1 card with `grow_held` or
  `held_discount`, exclusion: no `retain` on the class); `_PREFERRED_OPS`; `gate.FIELD_UNITS` += `grow_held`;
  `build_notes` for `retain_hold` already cite Windmill Strike / Sands of Time — name the two tokens.
- **Test:** `tests/test_phase_bd.py`. Gap Tester: Retain deck — Windmill Strike clone (retain + damage 7 grow_held
  4), Sands of Time clone (cost 3, retain, held_discount 1), rest aggression; the bot won't deliberately hold, so
  make the two testers cost 3 and give the class 3 energy so they're often unplayable and get retained; grep
  `[BD]` lines for `_turnsHeld` increments and cost reads; 0 exceptions.

### Phase BE — Trigger `on_poison_damage` (v59; ~1 day)
Gap **#56**. The base Poison tick (`DECOMP\…\PoisonPower.cs:55-74`, `AfterSideTurnStart`) calls
`CreatureCmd.Damage(new ThrowingPlayerChoiceContext(), Owner, Amount, ValueProp.Unblockable | ValueProp.Unpowered,
null, null)` — no dealer, no card — and **`Hook.AfterDamageReceived` is skipped when the tick kills**
(`CreatureCmd.cs:388-398`), while **`Hook.AfterDamageGiven` fires even then**. Stacks are still on the target when
the hooks run (`PowerCmd.Decrement` comes after).

- **Hook:** `ForgedTriggerPower.AfterDamageGiven` (:175-187) — add a branch: `dealer == null && cardSource == null
  && props == (Unblockable|Unpowered) && target.Player == null && target.HasPower<PoisonPower>()` →
  `FireReactive("on_poison_damage", ctx)`. **Do not** store this ctx into `_combatCtx` (:177) — it's a
  `ThrowingPlayerChoiceContext`, and `AfterBlockGained` reuses `_combatCtx`.
- **Collision:** the mod's own DoT tick (`ForgedStatusPower.cs:165-174`) uses byte-identical props + null dealer.
  Wrap that `CreatureCmd.Damage` in a static `ForgedStatusPower.CustomTickInProgress` flag (our code, no Harmony)
  and skip the branch while it's set. Accelerant-style double ticks fire twice; `once_per_turn` (default ON in the
  validator for this kind, like #56's sketch) absorbs that.
- Lists: `SupportedTriggers` (:412-416), `MultiFireTriggers` (:419-422), `OncePerCombatTriggers` (:426-428), the
  title switch (`ForgedTriggerPower.cs:240-248`), `TriggerSentence` (:1938-1952). Schema trigger enum; VOCABULARY
  `add_trigger` row. Python: `cardgen.trigger_sentence`, `validator._MULTI_FIRE_TRIGGERS` / `_ONCE_PER_COMBAT_
  TRIGGERS`, `harness_v2._PREFERRED_TRIGGERS`.
- Describe: `Whenever an enemy takes Poison damage, {payload}.` with the once-per-turn suffix the other kinds use.
- Timing note for the row: ticks land at the ENEMY's turn start, so Block gained from the payload is live through
  their attacks — that's the Venom fantasy, and it's why the default payoff should be Block/draw, not damage.
- Harness: `poison_attrition.vocabulary.ops` += `on_poison_damage`; NOT in `REACTIVE_MENU_V2` (that menu isn't
  kind-gated and would push Poison onto every class) → `FEATURED_MENU` += `venom_engine` (detect: ≥1
  `on_poison_damage` trigger AND ≥2 cards with a `poison` op; exclusion: class has no `poison`);
  `class_forge._PRUNABLE_SECTIONS` keep-set for the poison section only.
- **Test:** `tests/test_phase_be.py`. Gap Tester: Venom deck with a power "Whenever an enemy takes Poison damage,
  gain 2 Block (once per turn)" + many cheap `poison 3` appliers; grep `[BE]` per tick, confirm a lethal tick also
  fires (log the target HP), confirm the custom-DoT collision guard (add one `damage_over_time` status to the
  tester and assert NO `[BE]` line on its tick); 0 exceptions.

### Phase BF — Next-attack amplifier: `vigor` status + `double_next_attack` (v60; ~1 day)
Gap **#54**. `blade_empower` can't be generalised: its multiplier is applied inside the blade card's own damage
lambda (`DataCard.cs:63`, `EffectRunner.BladeMultiplier :1054-1055`), never through a `Modify*` hook. But the base
game ships both flavours as **sealed, concrete** powers (unlike the abstract `TemporaryStrengthPower` that crashed
`temp_strength`, gap #26):
- `DECOMP\…\Powers\VigorPower.cs` — "+N to your next Attack, then consumed" (`BeforeAttack` latch :147-173,
  `ModifyDamageAdditive` :175-195, `AfterAttack` removes :197-204).
- `DECOMP\…\Powers\DoubleDamagePower.cs` — ×2 for the owner's card attacks, **whole turn**, one stack off at end
  of turn (:94-117). Pen Nib (`Relics\PenNib.cs:132-166`) is the true one-attack ×2 via `AfterCardPlayed`.

**BF-1 `apply_status vigor N` (self buff)** — pure status-list addition, no new power, base-game tooltip + name:
`EffectRunner.SelfBuffStatuses` (:884-890), `ApplyStatus` map (:1106-1133) + relic path (~:1391-1402),
`TriggerRunner.ApplySelfBuff` (:302-321), `OrbRunner.cs:160-171`, `SummonRunner.cs:106-117`, card variables
`DataCard.cs:215-238`, `ForgedCards.SupportedStatuses` (:453-457), display names (:1736-1740, :2128-2132,
`OrbRunner.cs:238-242`, `SummonRunner.cs:191-195`), `mod/contract/statuses/vigor.json`
(`{"id":"vigor","name":"Vigor","kind":"buff","decay":"consumed"}` — verify `decay` accepts a new value or reuse
`turn`), `validator._STATUS_WEIGHT` (vigor ≈ 0.5 per point). Legal as a trigger payload (an `on_block_gained → vigor 3`
engine is the Glass tempest dream).
- Describe: `Gain {N} Vigor.` (status idiom).

**BF-2 `double_next_attack` op** — new `Powers/ForgedNextAttackMultPower.cs`: `ModifyDamageMultiplicative` ×2 gated
on `props.IsPoweredAttack()` + the Vigor `BeforeAttack` latch / `AfterAttack` use-up, attached via the
`ForgedBladeEmpowerPower.ApplyOrRefresh` pattern (Single stack, re-apply refreshes). `ModifyDamage*` runs for
tooltip previews (`ForgedRelic.cs:297-301`) — keep it read-only; consume in `AfterAttack`. Rare-tier only, at most
one per class, priced ≈ 4.0 (it is Phantasmal Killer). Card-only in v60.
- Describe: `Your next Attack deals double damage.`
- **Decision to make (default: ship BF-1 only if BF-2's latch misbehaves under multi-hit):** verify-first that
  `BeforeAttack`/`AfterAttack` fire once per CARD, not per hit, on a `hits: 3` forged attack. If per hit, BF-2
  either doubles only the first hit (document it) or STOPs and `double_damage` maps to the whole-turn
  `DoubleDamagePower` instead (`Your Attacks deal double damage this turn.`).

- Harness: `forge_ramp.vocabulary.ops` += `vigor` (build_notes already say "prefer tools that boost ANY attack
  … `blade_empower` exists but is optional" → name `vigor` first, and CUT the `blade_empower` clause from the Forge
  pitch in `class_forge.py:~500` — that's the rule-0.9 offset for this wave); `burst_window` += `vigor`,
  `double_next_attack`; `harness_v2._PREFERRED_OPS`; `coverage.EXOTIC_*` unchanged (vigor is a plain buff);
  `FEATURED_MENU` += `setup_spike` (detect: ≥1 `vigor` or `double_next_attack` AND ≥1 draw/energy op).
- **Test:** `tests/test_phase_bf.py`. Gap Tester: Glass tempest deck — "Gain 4 Vigor", "Your next Attack deals
  double damage", a 3-hit attack, aggression elsewhere; grep `[BF]` on apply/consume, assert the multi-hit finding
  in the phase section; 0 exceptions.

### Phase BG — Mod-only UX: ripen countdown + balance gauge text (no vocab bump; ~½ day)
Gaps **#60**, **#61**. No contract change, so no `VocabVersion` bump — but it still ships in the mod zip.

**#60 ripen countdown** — `ForgedTriggerPower.cs:36-37` (`_ripenLeft`, `_ripenFired`), tick :88-97. Nothing shows
because the power is applied at Amount 1 with `Single` stack type (:55-61) and `NPower.cs:234` only draws a number
for `Counter` powers. Fix: `StackType = Counter` when `Trigger?.Trigger == "ripen"`; override
`DisplayAmount => _ripenLeft < 0 ? Math.Max(1, Trigger.Amount) : _ripenLeft` (`PowerModel.cs:218`; `OutbreakPower.cs:
26` is the base precedent); call `InvokeDisplayAmountChanged()` (:455) right after the decrement at :91; remove the
power after it fires (:93-95) so a spent countdown doesn't linger. Tooltip: `ForgedCards.cs:1941` is baked once
(BaseLib `ModelLocPatch` reads `.Localization` at `ModelDb.Init`) — put `{Amount}` in the smartDescription so the
live number renders ("Ripens in {Amount} turns: …"). Also satisfies `countdown_ripen.build_notes` ("shown as a buff
on the player that counts down"), which today promises something the engine doesn't do.

**#61 balance gauge** — `ForgedBalancePower.cs`: signed `_value` (:296), `SetValue` REMOVES the power at 0 (:346),
`Amount = |value|`, `ExtremeThreshold = 8` (:289) penalties at owner turn start (:362-379: Dark −3 HP, Light +1
Weak), and **the title flip at :388-398 is dead code** (loc is read once from the template where `_value == 0`,
so the title is always "Balance"; only the icon flips, :401-404). Fix: (a) keep the power at 0 with Amount 0
instead of removing it (delete the :346 branch; `BalanceStep` :328-329 then never needs to re-attach) so the gauge
is always visible; (b) override `PowerModel.Title` (:49) to select `titleDark` / `titleLight` / `title` from
`PowerLoc(..., ExtraLoc: …)` live, replacing the dead `Localization` flip; (c) rewrite the smartDescription
(:393-395) so it states the sign and the PENALTY: "Balance {Amount} toward the {pole}. At 8 or more the extreme
bites at the start of your turn: the Dark drains 3 HP, the Light inflicts 1 Weak." — use `DynamicVars` for the
pole word (`PowerModel.cs:363-392` formats live). The :339-342 same-magnitude sign-flip lag goes away with (b).
Verify-first: does a Counter power with Amount 0 render "0" or hide the number? If it hides, show 0 via
`DisplayAmount` override and keep the icon.

- No generation-side change except: `VOCABULARY.md` Balance paragraph + the `countdown_ripen` / `balance_gauge`
  build_notes already describe the fixed behaviour (2026-09-29 copy) — verify they still read true after the fix.
- **Test:** no `test_phase_bg.py` vocab checks; a C# build + AutoSlay Balance and Ripen testers (reuse the Phase
  G/H ripen tester and the balance gauge tester from `generation/scratch/`), grep `[S]` (balance) + a new `[BG]
  ripen display N` line; screenshot the power tray once by hand — the whole point is what the player sees.
- Commit: `mod: Phase BG — ripen countdown + balance gauge text`. Bump `mod/BlankTheSpire.json` version with the
  wave's release.

---

## 4. Release (one mod release for the wave)

Per `vocab-gaps-branch-unshipped` / `droplet-deploy-path`: merge to main → bump `mod/BlankTheSpire.json` (v0.2.2 →
**v0.3.0**, vocab v60) → `mod/tools/package_release.ps1 -Version 0.3.0` → scp the zip to
`/opt/btsweb/web/static/releases/` (chown btsweb) → Workshop update (`workshop/build_workspace.ps1`, move
`previews/.gitkeep` aside, `~/tools/ModUploader/ModUploader.exe upload -w workshop/workspace`, restore) →
`sudo /opt/btsweb/deploy.sh`. Players on v0.2.x get "this code needs a newer BLANK the spire" on new codes until
they update — the welcome banner already points at the Workshop item.

If Ryan wants an earlier drop: BB+BG together make a cheap v0.2.3 (two tiny vocab tokens + the two UX fixes).

---

## 5. Scoreboard

| Phase | Gaps | Vocab | Effort | What the forge can newly say |
|---|---|---|---|---|
| BB | #59, #55 | v56 | ½ day | "if it's turn 2 or earlier"; Sly cards for discard classes; the budget readings settled |
| BC | #52, #53 | v57 | 1 day | Burning Pact / True Grit / Second Wind / Purity; Pillage |
| BD | #57, #58 | v58 | 1 day | Windmill Strike; Sands of Time / Establishment — Retain finally has payoffs |
| BE | #56 | v59 | 1 day | "Whenever an enemy takes Poison damage…" engines |
| BF | #54 | v60 | 1 day | Vigor (+N next Attack, any class); Phantasmal ×2 (rare) |
| BG | #60, #61 | — | ½ day | The ripen buff counts down; the gauge shows its pole and warns about the penalty |

**Recommended order:** BB (proves the lockstep + settles rule 0.9 in one commit) → BC (most-requested, two
archetypes) → BD (Retain is the archetype with the biggest gap between its copy and what it can build) → BE → BF →
BG anywhere (it shares the mod zip). ~5 days end to end plus one release.

## 6. Open decisions for Ryan

1. **Sly + scry** (BB): accept that a scried Sly card auto-plays, or filter it? Default: accept.
2. **`double_next_attack` vs whole-turn `double_damage`** (BF-2): decided by the multi-hit verify-first; if you'd
   rather skip the new power entirely, BF ships `vigor` alone and #54 closes as "+N" only.
3. **Release cadence:** one v0.3.0 at the end (default) or an early v0.2.3 with BB+BG.
4. **Which of #52–#59 actually get built** — flip each to `planned` in `VOCABULARY_GAPS.md` as the go signal; the
   phases are independent except BC's shared `card_type` widening.
