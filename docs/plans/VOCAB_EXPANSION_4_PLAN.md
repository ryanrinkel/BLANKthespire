# Vocabulary Expansion — Wave 4 Plan

**Written 2026-07-14 from a 5-agent scout of every OPEN gap in `VOCABULARY_GAPS.md` (post-wave-3,
live vocab v31).** This plan is designed to be executed phase-by-phase by an implementing agent
(Opus). Every phase carries an **executable test spec**: a `tests/test_phase_*.py` assert list, a
Gap Tester class, the AutoSlay command, and the godot.log grep gate. A phase is DONE only when all
of its tests pass.

**Scout caveat:** all file:line references below came from an automated scout pass. **Re-grep the
symbol before trusting a line number** — treat names as authoritative, line numbers as hints.

---

## 0. Ground rules (read once, apply to every phase)

These mirror `VOCAB_EXPANSION_3_PLAN.md` §0; the load-bearing ones repeated:

- **0.1 Lockstep or nothing.** A vocab change ships across ALL of: `mod/BlankTheSpireCode/`
  (`ForgedCards.cs` SupportedOps/TriggerOps/AmountOps/Validate/ValidateTrigger/Describe/
  TriggerFragment/VocabVersion · `EffectRunner.cs` · `TriggerRunner.cs` · `DataCard.cs` ·
  `CardSpec.cs` · `Conditions.cs` if conditions) + `mod/contract/card.schema.json` +
  `mod/contract/VOCABULARY.md` + `generation/btsgen/` (`cardgen.py` describe byte-match ·
  `validator.py` · `census.py` · `bts1.py` VOCAB_VERSION · `class_forge.py` blueprint ·
  `featured.py` · `frontend/archetypes.json` catalog) + `character_validator.py`/
  `character_pipeline.py` when class-level rules change. Grep a recent phase (W or AA) for the
  concrete diff shape.
- **0.2 Describe text is a byte-match contract.** `cardgen.describe()` output must equal
  `ForgedCards.Describe()` byte-for-byte. Every phase test asserts this.
- **0.3 AutoSlay validation is by godot.log tags, NOT the tool verdict.** The random bot fails
  navigation on its own (map-nav watchdog, event timeouts, NEOW). Pass bar per run: **≥1 phase
  tag fired · 0 mod exceptions · no hang attributable to the mod** (a BlankTheSpire frame in the
  stall stack). Log every new mechanic with a `[<PHASE>] ...` tag so the grep gate exists.
- **0.4 Deck-deletion / choice mechanics need an all-aggression tester** (wave-3 lesson: a random
  bot that thins its own offense self-stalemates to turn-100). Any tester whose mechanic shrinks
  the deck or opens a picker: make every other card aggressive damage.
- **0.5 Choice UIs are AutoSlay-safe** via `AutoSlayCardSelector` auto-pick (proven in Phases
  X/Z/AA) — but always grep for the `Auto-selected` line to confirm the picker resolved.
- **0.6 STOP rules.** If a phase's verify-first step contradicts the spec (API absent/renamed),
  STOP that phase, write findings into the phase section, move to the next phase. If the C# build
  breaks and can't be fixed inside the phase, revert the phase, record why.
- **0.7 Commit convention.** One commit per phase:
  `mod+forge: Phase <LETTER> — <mechanic> (vocab v<N>)`. Gate/doc-only phases: `docs:` prefix.
- **0.8 Vocab versions.** Assigned in build order starting at **v32**. If you reorder phases,
  renumber — the version stamps below are tentative.

### Standard commands (from the test-convention harvest)

```powershell
# Generation-side phase test (each file is a standalone module, exit 0 = pass)
cd generation
uv run python -m tests.test_phase_ab

# Full generation suite (run every phase file; stop on first failure)
cd generation
Get-ChildItem tests/test_phase_*.py | ForEach-Object { uv run python -m ("tests." + $_.BaseName); if ($LASTEXITCODE -ne 0) { throw $_.BaseName } }

# C# build (also deploys to the game's mods folder via CopyToModsFolderOnBuild)
dotnet build mod/BlankTheSpire.csproj -c Debug

# AutoSlay smoke (driver resolves game/log paths via generation/btsgen/game_paths.py)
cd generation
uv run btsgen-autoslay-smoke --seeds GAPTEST<NN> GAPTEST<NN>B --character class4 --relic auto --build --timeout 900
```

### Gap Tester recipe (per phase)

Create `generation/scratch/gaptest-<phase>/` with `build_gaptest_<phase>.py` +
`restore_slot04.py`, cloned from `generation/scratch/gaptest-aa/` (the freshest template):
inline `CARDS` dict → validate each via `CardValidator` → back up slot 04 on first run → stage
into the game's `forged/characters/04/` → print the AutoSlay command. Restore slot 04 after the
smoke. Validation = grep godot.log for the phase tags (examples per phase below) + exception
count 0.

---

## 1. Gate H — gap-log hygiene + triage rulings (doc-only, no vocab)

Do this first; it is pure `VOCABULARY_GAPS.md` editing plus one queue update.

### H-1 · Clear the stale "PENDING env reboot" notes

Gaps **#1, #9, #21, #22, #24** still say "AutoSlay GAPTEST… PENDING (env reboot)".
`AUTOSLAY_VALIDATION_QUEUE.md` records P/R/S as runtime-PASSED 2026-07-09 and AutoSlay now runs
on Windows without reboot. Cross-check each gap against the queue's results table; where the
queue shows a pass, replace the PENDING clause with `runtime-PASSED <date> (see
AUTOSLAY_VALIDATION_QUEUE.md)`. Where the queue shows nothing, leave the note but change it to
`runtime re-check queued` and add a row to the queue.

### H-2 · Apply the scout triage rulings (2026-07-14)

Update these gap entries (keep the existing text; append a dated triage paragraph):

- **#11 Frostbite Signature → `rejected`** — the burst half is expressible (`apply_status`
  vulnerable/weak/poison + `ripen`), but the freeze half needs an enemy STUN primitive (prevent
  enemy action) that has no surface in the vocab or scouted API. Re-open only if a stun/disable
  power is ever scouted.
- **#34 Lightning Chain → `rejected`** — no positional/adjacency API surfaced in the reflection
  dump (`HittableEnemies` is an unordered-for-our-purposes list; no index/neighbor queries).
  AoE (`all_enemies`) + random-target payloads remain the expressible approximations.
- **#37 Weapon Autonomy → `rejected`** — force-play / card-locking would override the game's
  choice loop; no hook exists, and it breaks the closed-vocabulary safety model.
- **#12 Ice Shatter → `planned`** (cheap): the threshold-payoff shape is already expressible via
  `when hand_size_ge` / `cards_retained`; the missing HP-spent variant becomes Phase AD's
  `hp_lost_ge` condition. Point the entry at Phase AD.
- **#2 Ally-heal/shield → `planned`** (cheap): `SummonRunner` already has `heal_self` plumbing
  for summon moves; card-op exposure becomes Phase AC. Point the entry at Phase AC.
- **#20 Corruption → `planned` → Phase AB** (scouted BUILDABLE, no spike needed — see below).
- **#25, #39, #41 → `planned`** pointing at Phases AE / AG / AF.
- **#35 / #38 / #40 / #3 / #7** — append: "transform-family scout (2026-07-14): base game ships
  `CardCmd.Transform(original, replacement, style)` + `CardCmd.TransformTo` +
  `CardFactory.GetDefaultTransformationOptions` — see Phase AH + SPIKE_TRANSFORM.md."

### Gate H done =

One `docs:` commit. No vocab bump, no tests.

---

## 2. Phase AB — Corruption power (gap #20 · v32 · effort SMALL, scouted NO-RISK)

**The scout's best finding: this is a verbatim base-game recipe.** The decompile at
`_modref/decomp_full/MegaCrit.Sts2.Core.Models.Powers/CorruptionPower.cs` shows both hooks:

- `TryModifyEnergyCostInCombatLate(CardModel card, decimal originalCost, out decimal modifiedCost)`
  → returns cost 0 for `card.Type == CardType.Skill` owned by the power's owner.
- `ModifyCardPlayResultPileTypeAndPosition(...)` → returns `(PileType.Exhaust, position)` for
  Skills.

Both are public `AbstractModel` overrides — **no Harmony patch**. The mod already uses the cost
hook (`ForgedRelic.TryModifyEnergyCostInCombat`, `cost_reduction` modifier) and already
overrides result-pile logic (`DataCard.GetResultPileTypeForCardPlay` for purge). `CardType` enum:
`None, Attack, Skill, Power, Status, Curse, Quest` (dump.txt ~:1713).

### Spec

- New power `ForgedCorruptionPower` (`mod/BlankTheSpireCode/Powers/ForgedCorruptionPower.cs`),
  modeled on the ForgedForgePower file conventions (in-code loc, emoji icon ☠️ or 🃏, per-combat,
  `PowerStackType.Single` — binary, no stacking). Implements exactly the two base-game overrides
  above, scoped to owner + `CardType.Skill`.
- New card op **`corruption`** (flag-op, no amount/target, like `purge`): applying it grants
  ForgedCorruptionPower. Fixed semantics v1: **"Your Skills cost 0. Your Skills Exhaust when
  played."** (No card_type parameter — generalize later if demanded.)
- Legality: **power/skill cards only, card-only** (NOT in `add_trigger` payloads — re-granting a
  binary power every turn is noise; validator + `ValidateTrigger` reject). At most one
  `corruption` card per class (`character_validator` warning, like `purge_warnings`).
- Describe text (byte-match): `"Your Skills cost 0.\nYour Skills Exhaust when played."`
- Log tags: `[AB] corruption power applied` on grant; `[AB] corruption: '<card>' cost 0` from the
  cost hook (first application per card per combat is enough — don't spam); `[AB] corruption:
  '<card>' -> Exhaust` from the pile hook.
- Lockstep per §0.1. Catalog: extend an existing exhaust archetype (`exhaust_pyre`) with the
  `corruption` token + add blueprint guidance in `class_forge.py` (a corruption class needs
  Skill density + exhaust payoffs — pairs with `on_exhaust` triggers, gap #13).

### Executable tests

**`generation/tests/test_phase_ab.py`** (clone test_phase_w.py shape; every category from the
harvest):

1. `bts1.VOCAB_VERSION >= 32`.
2. Validator ACCEPTS: a power card `[{op:"corruption"}]`; a skill carrying corruption + a block
   effect.
3. Validator REJECTS: `corruption` on an attack card; `corruption` with an `amount`;
   `corruption` inside an `add_trigger` payload; two corruption effects on one card.
4. Describe byte-match: `cardgen.describe([{"op":"corruption"}], "self")` equals the C# string
   exactly (write the C# first, copy it).
5. C# emit: `cardgen.effect_literal({"op":"corruption"}) == 'new EffectSpec("corruption", 0)'`
   (match the flag-op emit shape `purge` uses).
6. Census: `"corruption" in census.walk_card(card).ops`, card classified non-plain.
7. Class warning: 2 corruption cards in one class → exactly 1 warning from
   `character_validator`.
8. Catalog: `exhaust_pyre` (or the archetype you extend) declares the `corruption` token and is
   BUILDABLE; token appears in `live_vocab_tokens()`.
9. Featured: detect fires on a corruption card (if you add a featured entry).

**Gap Tester `gaptest-ab`** (seeds `GAPTEST20`, `GAPTEST20B`): 10 cards — 1 corruption power
card, ~5 cheap Skills (block/draw — the fuel the power zeroes), 1 `on_exhaust` payoff engine
(proves the corruption→exhaust→on_exhaust chain), 3 plain attacks (aggression per §0.4).

godot.log grep gate:
```powershell
Select-String '\[AB\] corruption' godot.log | Measure-Object            # ≥ 1 grant + ≥ 5 cost-0 lines
Select-String "\[AB\] corruption: .* -> Exhaust" godot.log | Measure-Object   # ≥ 3 (skills exhausted)
Select-String "\[H4\] reactive trigger 'on_exhaust' fired" godot.log    # chain proof, ≥ 1
Select-String 'Exception' godot.log | Measure-Object                    # 0 mod exceptions
```
Also verify by absence: attacks in the log must NOT show cost-0 or exhaust redirect lines.

---

## 3. Phase AC — summon heal/shield ops (gap #2 · v33 · effort TRIVIAL)

**Verify-first:** `SummonRunner.cs` already executes `heal_self` for summon move-actions via
`CreatureCmd.Heal(pet, amount, true)` (scout: SummonRunner.cs ~:54). Confirm a block analog
exists for creatures (`CreatureCmd.Block` or the block path `EffectRunner` uses for the player);
if minions can't hold Block in this engine, ship **heal only** and record that in the gap entry.

### Spec

- New card ops **`heal_summon {amount 1..9}`** and (if block verifies) **`shield_summon
  {amount 1..12}`**: heal / grant Block to YOUR summon. No-op (logged, never throws) when no
  summon is out. Legal on cards AND in `add_trigger` self-payloads (a "medic engine" that heals
  the minion every turn is exactly the Phase-K fantasy this closes).
- Validator class-rule: classes emitting these ops must be summon classes (already have a
  `summon` op somewhere in the set) — mirror the existing `summon_attack` pairing rule in
  `character_validator`.
- Describe: `"Heal your summon {N} HP."` / `"Your summon gains {N} Block."`
- Log tags: `[AC] heal_summon N -> '<summon>'` · `[AC] shield_summon N -> '<summon>'` ·
  `[AC] heal_summon: no summon (no-op)`.

### Executable tests

**`tests/test_phase_ac.py`:** version ≥ 33 · ACCEPT heal_summon on skill + in a turn_start
payload · REJECT amount 0 / amount missing / on a non-summon class (class-level check) ·
describe byte-match both ops · effect_literal emit · census ops · catalog: summon archetype
gains the tokens · pairing warning fires for heal_summon-without-summon class.

**Gap Tester `gaptest-ac`** (seeds `GAPTEST2`, `GAPTEST2B`): summon class — 1 summon card,
2 heal_summon, 1 shield_summon, 1 turn_start→heal_summon engine, 2 summon_attack (offense per
the summon-needs-attack-cards rule), 3 plain attacks.
Grep gate: ≥5 `[AC]` fires incl. ≥1 no-op line (play a heal before summoning) + 0 exceptions.

---

## 4. Phase AD — `hp_lost_ge` condition (closes gap #12 · v34 · effort SMALL)

The threshold-payoff pattern (#12 Ice Shatter) is expressible except for the HP-spent read.

**Verify-first:** the `on_hp_lost` trigger machinery (gap #9, `ForgedTriggerPower.
AfterDamageReceived`) already observes unblocked HP loss. Check whether any per-turn accumulator
exists (HandStateTracker pattern from Phase F5); if not, add one.

### Spec

- New `when` condition **`hp_lost_ge N`** (1..15): true when the player has lost ≥ N HP **this
  turn** (any source — self-inflicted or enemy; simpler than Rupture scoping, document it).
  Tracker: `HpLossTracker` accumulating in the same hook family `on_hp_lost` uses, reset at turn
  start (copy HandStateTracker's reset wiring).
- Slots into `Conditions.cs` (Kinds/Validate/Eval/Phrase) + schema kind enum + `cardgen.
  cond_phrase` ("you have lost N or more HP this turn") + validator.
- Log tag: `[AD] hp_lost_ge gate open (lost X this turn)` when a gated effect passes the check.

### Executable tests

**`tests/test_phase_ad.py`:** version ≥ 34 · ACCEPT damage-with-when-hp_lost_ge · REJECT value 0
/ missing / >15 · cond_phrase byte-match · condition_literal emit · a composed "Ice Shatter"
card validates: `[{op:"lose_hp",amount:3},{op:"damage",amount:18,when:{kind:"hp_lost_ge",
value:3}}]` (the gap-#12 shape, self-fuel then payoff).

**Gap Tester `gaptest-ad`** (seeds `GAPTEST12`, `GAPTEST12B`): 2 lose_hp fuel cards, 2 hp_lost_ge
gated nukes, 1 on_hp_lost engine (existing vocab, chain proof), 5 plain attacks.
Grep gate: ≥5 `[AD]` gate-open fires + gated card also logged firing when gate closed→no bonus
(verify both branches) + 0 exceptions. Close gap #12 as `done` on pass.

---

## 5. Phase AE — card tags + `tag_cards_owned` scalar (gap #25 · v35 · effort MEDIUM-SMALL)

Base game: Perfected Strike carries `"tags":["Strike"]` in `sts2_cards.json` and CardModel
exposes `CanonicalTags: HashSet<string>` (dump.txt, MinionStrike entry). Our cards are
`ConstructedCardModel` subclasses — **verify-first whether CanonicalTags is settable/overridable
on DataCard; if not, keep tags purely in CardSpec** (we only need our own scan to see them).

### Spec

- New optional CardSpec/schema field **`tags`**: array of 1..2 lowercase slugs (pattern
  `^[a-z][a-z0-9_]{1,15}$`). Purely declarative metadata; no runtime behavior by itself.
- New scale value **`tag_cards_owned`** requiring a sibling effect field **`tag`** (string, must
  appear in ≥2 cards of the class — validator class-rule so the payoff is never dead): resolves
  to the count of cards carrying that tag across the player's combat piles (draw + discard +
  hand + exhaust; verify pile enumeration against the `draw_pile_empty` pattern in
  Conditions.cs ~:100). Resolution goes in the single `EffectRunner.ScaleValue` switch
  (~:553) + the `DataCard.BonusFor` calc-var for live display.
- Describe: damage example `"Deal {Damage} damage. (+{N} per '<tag>' card you own.)"` — pick
  final wording when writing the C#, byte-match it.
- Blueprint: `class_forge.py` gains a "TAGGED SYNERGY" note (tag 3-5 cards, 1-2 payoffs);
  catalog archetype `strike_synergy` (gap_refs #25).
- Log tag: `[AE] tag_cards_owned('<tag>') = N`.

### Executable tests

**`tests/test_phase_ae.py`:** version ≥ 35 · ACCEPT tagged card + payoff card with
scale/tag pair · REJECT: >2 tags, uppercase tag, `tag_cards_owned` without `tag` field, tag
referenced by payoff but present on <2 class cards (class-level) · describe byte-match ·
effect_literal carries the tag string · census + catalog + featured rows.

**Gap Tester `gaptest-ae`** (seeds `GAPTEST25`, `GAPTEST25B`): 4 cards tagged `strike` (plain
attacks), 2 payoff cards `scale:"tag_cards_owned", tag:"strike"`, 4 filler.
Grep gate: ≥5 `[AE] tag_cards_owned('strike') = N` lines with N varying as piles shift (proves a
live scan, not a constant) + 0 exceptions.

---

## 6. Phase AF — op `blade_empower` (gap #41 · v36 · effort SMALL)

Transient ×N multiplier on the forged blade for ONE turn. Rides three proven pieces: the
`scale:"forged"` resolution (`EffectRunner.ScaleValue` "forged" → `ForgeStacks`; calc-var
`DataCard.BonusFor` sums amount + upgrade + stacks), the Forge-class blade token (Phase T), and
the one-turn-power pattern (`ForgedTempStrengthPower : CustomTemporaryPowerModel`, auto-removed
at turn end).

**Design decision (take this, simpler than the scout's ModifyDamage idea):** do NOT hook damage
mutation. Add `ForgedBladeEmpowerPower` (one-turn, counter = multiplier N) and make the
**forged-damage calc read it**: in the one place blade damage resolves (`BonusFor` /
`ScaleValue("forged")` path), if the owner has the power, multiply the blade card's total by N.
Scope it to the blade token only (`Spec.IsToken`-gated), which keeps it "blade deals double",
not "everything forged deals double". **Verify-first** that the calc-var re-evaluates when a
power is applied mid-turn (Forge stacks already update the preview — same path).

### Spec

- Op **`blade_empower {amount 2..3}`** (×N this turn). **Forge-class only** (class must have
  forge income — reuse `forge_pairing` machinery); card-only (rejected in trigger payloads —
  repeating empower is degenerate); skill/power cards.
- Describe: `"Your blade deals {N}x damage this turn."`
- Expiry: power removes itself at turn end (CustomTemporaryPowerModel base — same as temp
  stats). Stacking: re-application REFRESHES (overwrite, don't multiply) — document.
- Log tags: `[AF] blade_empower xN` on apply · `[AF] blade hit: base B -> B*N` on an empowered
  blade resolution · power-expired line at turn end.

### Executable tests

**`tests/test_phase_af.py`:** version ≥ 36 · ACCEPT on a forge-class skill · REJECT amount 1 /
4+ / in payload / on a class with no forge income (class-level) · describe byte-match · emit ·
census/catalog (`forge_ramp` gains the token) · scoring: empower prices above plain forge
income.

**Gap Tester `gaptest-af`** (seeds `GAPTEST41`, `GAPTEST41B`): a forge class — forge income ×3,
1 blade_empower, summon_blade, 4 attacks. Grep gate: ≥2 `[AF] blade_empower` applies; at least
one blade damage line where the empowered value = 2× the un-empowered value **in the same
combat** (grep pairs of `[AF] blade hit` lines); next-turn blade hit back to base (expiry
proof); 0 exceptions.

---

## 7. Phase AG — upgrade-cost channel (gap #39 · v37 · effort MEDIUM-SMALL)

Today `CardSpec.Upgrade` is effects-only; cost is fixed in the DataCard constructor
(`base(spec.Cost, ...)`, DataCard.cs ~:80); `EffectRunner.UpgradeDelta` diffs amounts only.
The dump exposes cost-mutation surface: `CardModel.MockSetEnergyCost(CardEnergyCost)` +
`InvokeEnergyCostChanged()` (dump.txt ~:701-702) and star-cost setters (~:705-710 — likely a
different resource; ignore unless energy setters fail).

**Spike-inside-phase (do first, ~1h):** on a throwaway card, after `CardCmd.Upgrade`, call
`MockSetEnergyCost` + `InvokeEnergyCostChanged` and confirm (a) hand preview shows the new cost,
(b) play deducts the new cost, (c) rest-site (Deck pile) upgrade persists it for the run. If
MockSetEnergyCost is dead, find how the game's own cost-changing upgrades do it (search
`sts2_cards.json` for upgrades that lower cost, then trace that card's model in the decompile).
STOP per §0.6 if no path works.

### Spec

- Schema: `upgrade` object gains optional **`cost`** (int 0..3) = the card's cost AFTER upgrade
  (absolute, not delta). Validator: `upgrade.cost` ≤ base cost (upgrades never raise cost —
  house rule, document), reject on X-cost cards v1.
- `CardSpec` gains `UpgradedCost int?`; DataCard applies it wherever the spike proved
  (constructor branch on IsUpgraded for deck-load of an upgraded card + the OnUpgrade/in-combat
  path for live upgrades — cover BOTH: rest-site upgrade and in-combat `upgrade_card`).
- The forged blade token's default upgrade payload gains `cost: 1` (the gap-#39 motivating case)
  — update the blade emission in `class_forge.py`/importer.
- Describe: upgrade preview line gains `"Costs {N}."` when cost changes.
- Log tag: `[AG] upgrade cost: '<card>' 2 -> 1`.

### Executable tests

**`tests/test_phase_ag.py`:** version ≥ 37 · ACCEPT upgrade with cost 2→1 · REJECT cost raise
(1→2) / cost on X-cost / cost 4 · describe upgrade-preview byte-match · blade emission carries
`cost:1` · round-trip: importer parses upgrade.cost into the C# literal.

**Gap Tester `gaptest-ag`** (seeds `GAPTEST39`, `GAPTEST39B`): forge class with the cost-1-upgrade
blade + an `upgrade_card cards:"all"` card (upgrades the blade in combat → cost drop observable
same combat) + aggression filler. Grep gate: ≥1 `[AG] upgrade cost` line; blade plays after
upgrade log an energy spend of 1 not 2 (grep the energy lines around blade plays); 0 exceptions.
ALSO one manual check ride-along: rest-site upgrade persists cost across combats (grep two
combats' blade plays).

---

## 8. Spike AH-0 — transform surface (NO vocab; deliverable `SPIKE_TRANSFORM.md`)

**The scout found the missing primitive is not missing:** the game ships a full transform
command family (dump.txt ~:576-579, ~:1616-1622):

```
CardCmd.Transform(CardModel original, CardModel replacement, CardPreviewStyle) → Task<CardModel>
CardCmd.TransformTo(CardModel original, CardPreviewStyle) → Task<CardModel>
CardCmd.TransformToRandom(CardModel original, Rng, CardPreviewStyle) → Task<CardModel>
CardFactory.GetDefaultTransformationOptions(CardModel, bool isInCombat) → IEnumerable<CardModel>
```

Base-game cards using Transform: SummonForth, Refit, Metamorphosis, MinionDiveBomb (per
`sts2_cards.json`). Three unknowns block a spec; prove them with throwaway slot-04 code (spike-Y
style — no lockstep, code reverted, doc + gap-line updates committed):

1. **Deck permanence:** play a card that calls `CardCmd.Transform(thisCard.DeckVersion,
   replacement, None)` on its run-deck original (build `replacement` via the proven
   `owner.Creature.CombatState.CreateCard` / `ResolveClassCardModel` recipe from Phase Q,
   pointing at another same-class card). Is the new card in the deck NEXT combat? Does the
   in-combat clone keep working this combat?
2. **In-combat transform:** transform a card sitting in HAND (the clone, not the DeckVersion).
   Does the hand card visibly become the new card, playable this combat?
3. **Mid-run safety:** 0 exceptions across a multi-combat AutoSlay run with transforms firing
   every combat; upgraded originals, exhausted copies, and generated (`DeckVersion == null`)
   copies all guarded.

Also record (cheap while in there): does `CardCmd.Transform` animate/pause under AutoSlay, and
does anything hang (grep the `Auto-selected`/watchdog lines).

**Deliverable:** `SPIKE_TRANSFORM.md` — recipe or dead-end per question + go/no-go for Phase AH
+ effort re-estimate. Update gaps #35/#38/#40/#3/#7 to point at it. STOP Phase AH on no-go.

**DONE (2026-07-15) — `SPIKE_TRANSFORM.md`: GO.** All three unknowns answered with a working recipe,
AutoSlay-verified (2 valid multi-combat runs, 0 transform exceptions). Q1 deck permanence ✅
(`CardCmd.Transform(card.DeckVersion, ResolveClassCardModel(...), None)` under the `purge` guard —
run-permanent, persists next combat, old card never returns). Q2 hand transform ✅ (Compact/Begone shape;
lands in hand `playable=True` this combat). Q3 guards ✅ (reuse the `purge` null-`DeckVersion` guard;
generated copies + upgraded originals + curses all clean). No hang (hand VFX runs since AutoSlay leaves
`TestMode` off, but does not stall; the only run failures were the unrelated boss-reward known-bug).
**Effort re-estimate: MEDIUM** (down from MEDIUM-HIGH — runtime is ~15 lines of proven pieces; the rest is
generation lockstep). Validator note: add `transform_card` to the `card_id`-only-on-add_card allow-list
(`ForgedCards.cs:809`).

---

## 9. Phase AH — op `transform_card` (gaps #35/#38 + #3 track + unblocks #7 · v38 · effort MEDIUM-HIGH, gated on AH-0)

The wave-4 anchor: **run-permanent self-transform**, the primitive five gap entries converge on
(demand ×5 — #35 self-rewrite, #38 reconfigure, #40 blade mutations, #3 rank-up, #7 graft).

### Spec (adjust to AH-0 findings)

- Op **`transform_card {card_id: "<same-class card>"}`**, self-referential v1: when the carrying
  card is PLAYED, it permanently BECOMES `card_id` for the rest of the run (deck original
  transformed via the spike recipe; this combat's clone transformed in hand if the spike proved
  it, else the swap takes effect next combat — document whichever).
- Composes with existing vocab for the fantasies:
  - **Rank-up (#3):** `when {kind:"..."} ` gates on the transform effect — e.g. a card that
    transforms only once you've played it enough (`grow`-style play-count read exists:
    `EffectRunner.PlaysThisCombat`) or once `forged_ge`/`light_ge` thresholds hit. v1: allow the
    existing `when` conditions on the transform effect; a dedicated multi-rank track stays open
    on #3.
  - **Mode-swap (#38):** two cards each carrying `transform_card` into the other.
- Guards (all validator + C# `Validate`): target must be same-class + must exist; **no transform
  chains** (the referenced card may not itself contain `transform_card` — depth-1, the Phase-Q
  `add_card` precedent); not on BASIC cards; card-only (never in trigger payloads); ⊥ `purge`
  (transform and delete are contradictory); class-level cap ≤3 transform cards
  (`transform_warnings`).
- Describe: `"Transforms into <Title> for the rest of the run."` (resolve the target's title at
  import — verify cardgen can see sibling cards; if not, use the id).
- Log tags: `[AH] transform_card: '<from>' -> '<to>' (run deck)` · `... (combat clone)` ·
  `[AH] transform_card: '<from>' not in run deck (generated copy) — combat only` (the Phase-W
  null-DeckVersion guard shape).

### Executable tests

**`tests/test_phase_ah.py`:** version ≥ 38 · ACCEPT a two-card mode-swap pair + a
conditional rank-up transform · REJECT: chain (target contains transform_card), unknown card_id,
basic card, in-payload, transform+purge on one card, 4 transform cards per class (warning) ·
describe byte-match · emit carries CardId · census/catalog: new `metamorph` archetype
(gap_refs #35/#38, BUILDABLE flip) · featured detect.

**Gap Tester `gaptest-ah`** (seeds `GAPTEST35`, `GAPTEST35B`, `GAPTEST35C` — 3 seeds, this is the
risky one; **all-aggression filler per §0.4**): 1 caterpillar→butterfly pair (weak attack
transforms into big attack), 1 conditional transform (`when turn_at_least 3`), 1 add_card
generator whose token copies the transformer (exercises the null-DeckVersion guard), 6 plain
attacks.
Grep gate:
```powershell
Select-String '\[AH\] transform_card' godot.log | Measure-Object     # ≥ 3 across runs
# permanence: the '-> to' card id must appear as a PLAYED card in a LATER combat,
# and the 'from' id must not re-appear in the deck after its transform combat
Select-String 'Exception|NullReference' godot.log | Measure-Object   # 0
```
Full-run completion on ≥1 seed (transform survives boss/reward flows).

**Graft note (#7):** after AH ships, graft = `CardSelectCmd.FromHand` pick (spike Y) + transform
the PICKED card. File it as the first wave-5 candidate; do not build it in this wave. **SHIPPED
2026-07-15 as Phase AI (vocab v39, first wave-5 phase): op `graft_card {card_id}` — the choose form
of `transform_card` (as `purge_card` is the choose form of `purge`). AutoSlay GAPTEST7/7B verified:
66 `[AI] graft` lines (18 run-deck perm grafts + combat-clone + generated-copy guard-skip + self-
refusal + no-selection), 0 mod exceptions, permanence proven (molten_edge 0→17, persisted 30+
combats). Gap #7 → done/SHIPPED. The fantasy delivered is transform-the-picked-card; a true
"consume X to buff/merge INTO Y" resource-transfer variant remains a possible richer follow-up.**

---

## 10. Wave order, versions, and the scoreboard

| Order | Phase | Gap(s) | Vocab | Effort (scouted) | Risk |
|---|---|---|---|---|---|
| 1 | Gate H | hygiene + reject #11/#34/#37 | — | 1-2h docs | none |
| 2 | AB corruption | #20 | v32 | ~half day | none (decompile-proven) |
| 3 | AC summon heal/shield | #2 | v33 | ~half day | low (block-on-minion verify) |
| 4 | AD hp_lost_ge | #12 | v34 | ~half day | low |
| 5 | AE tags + tag_cards_owned | #25 | v35 | ~1 day | low |
| 6 | AF blade_empower | #41 | v36 | ~1 day | low-med (calc-var refresh verify) |
| 7 | AG upgrade-cost | #39 | v37 | ~1 day | med (cost-mutation spike inside) |
| 8 | AH-0 transform spike | — | — | ✅ DONE 2026-07-15 — GO (`SPIKE_TRANSFORM.md`) | — |
| 9 | AH transform_card | #35/#38 (+#3 partial, unblocks #7) | v38 | ✅ DONE 2026-07-15 (vocab v38) — op `transform_card`, mode-swap/chain rule resolved (target may carry transform_card iff it swaps BACK; A↔B ok, A→B→C rejected); tests/test_phase_ah.py 21 asserts + full suite green; C# build clean | low-med (AH-0 cleared it) |

Rejected this wave (Gate H): #11 frostbite (needs enemy stun), #34 lightning chain (no adjacency
API), #37 weapon autonomy (breaks the choice loop). **Wave 4 COMPLETE (2026-07-15): AB→AH all
SHIPPED, vocab v32→v38.** Still open after wave 4: **#3 multi-rank track** (the single-tier rank-up
half shipped with AH's `when`-gated transform; a 3+-stage arc stays open, priority downgraded),
~~**#7 graft**~~ (SHIPPED 2026-07-15 as **Phase AI, vocab v39** — op `graft_card`, the choose form of
`transform_card`; the first wave-5 phase, executed off this plan's §9 graft note; AutoSlay-verified,
gap #7 → done/SHIPPED), **#40 blade mutations** (re-triaged:
the discrete-variants half is buildable via transform-into-a-variant; literal in-place structural
mutation stays low-priority open).

**After every phase:** run the full generation suite, `dotnet build`, the phase's AutoSlay gate;
flip the gap's status line in `VOCABULARY_GAPS.md` (with tag counts + seed names, wave-3 style);
update the catalog BUILDABLE flags; one commit per §0.7. **Nothing in this wave is pushed or
deployed** — that remains a separate release step (prod is still emitting v25 codes; a new mod
zip must accompany any deploy).
