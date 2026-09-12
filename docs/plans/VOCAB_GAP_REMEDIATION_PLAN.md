# Vocabulary Gap Remediation Plan

**Written 2026-09-09 from a three-agent audit of the live vocabulary (v39, Phase AI) against the C# engine,
the planning docs' deferred items, and the generation-side contracts/coverage.** Every issue the audit
surfaced has a fix or a mitigation below. The plan is ordered so that the cheapest, highest-leverage work
(prompt and doc text that is actively suppressing supported features) ships first, and the deepest engine
work ships last, each as its own lockstep phase.

**Scout caveat:** file:line references came from an automated audit on 2026-09-09. **Re-grep the symbol
before trusting a line number** — names are authoritative, line numbers are hints.

**STATUS (2026-09-09): Wave 0 EXECUTED** — all eleven items W0.1–W0.11 landed (uncommitted at time of writing).
Tests: `tests/test_wave0_docs.py`, `tests/test_wave0_prompts.py`, `tests/test_archetypes.py`,
`tests/test_exemplars.py`; full suite 365 passed. Notes from execution: metallicize is STS2 Plating and DECAYS
one stack per turn (verified against the decompiled `PlatingPower.cs`; the vocabulary row now says so); the
exemplar pool grew 46 → 82; `battle_smith` deliberately carries no `mechanic_kind:"forge"` (its ops are base
vocab); gap #48 is `planned (verify-then-close)`, not done — it still needs the AutoSlay run its entry specifies.
Run tests with `uv run python -m pytest` from `generation/` — bare `uv run pytest` can resolve a different
checkout's `btsgen`.

**STATUS (2026-09-09): Phase AJ EXECUTED (vocab v40)** — all six items landed in lockstep (`ForgedCards.cs`
Validate/ValidateTrigger/Describe + `OrbNameError`, `ForgedCharacters.cs` import passes the class's custom orb names,
`EffectRunner`/`OrbRunner` warn + skip an unknown orb, `card.schema.json`, `VOCABULARY.md`, `cardgen.py`,
`validator.py`, `bts1.py`). Verify-first finding: `random_enemy` needs NO runtime change — BaseLib's `CardAttack`
already rolls a random enemy per hit (`TargetingRandomOpponents`) and `Apply<T>`/`GetTargets` one random enemy per
status effect — so the contract rule is "no `when:target_has_status` / `scale:target_debuff_count` on a random_enemy
card" (each effect rolls independently). Tests: `tests/test_phase_aj.py` (22 checks); suite 367 passed. C# build
0 errors (`~/.dotnet/dotnet.exe build mod/BlankTheSpire.csproj -c Debug` — the Program Files dotnet is runtime-only).
AutoSlay GAPTESTAJ2 (tester `generation/scratch/gaptest-aj/build_tester.py`, staged into slot 04, Act 2 floor 27):
**206 `[AJ]` tags** (random_enemy damage x1/x3/x5, random_enemy weak/vulnerable, trigger channel_orb 'ember' x27,
unknown-orb warn+skip x22) · **0 mod exceptions** · tool verdict = the documented base-game map-nav watchdog at a
shop ("There is no item to purchase"), not mod-attributable. **Incidental fix (pre-existing, also in the 2026-08-19
log):** every custom-orb channel threw `Expected a GodotObject but was Nil` from `NOrb.UpdateVisuals` because the
game now wraps the sprite's `SpineSkeleton` child in a MegaSprite and the procedural circle had none —
`ForgedOrb.CreateCustomSprite` now instantiates the Lightning orb's real spine scene tinted to the orb's hue, and
borrows Lightning's channel/passive/evoke sound events (64 "No loader found" errors per run gone). GAPTESTAJ1 (before
that fix): 138 tags, 32 of those exceptions; GAPTESTAJ2 (after): 0.

**STATUS (2026-09-09): Phase AJ-b EXECUTED (no vocab bump)** — `btsgen.paths` now DEFAULTS to the mod contract
(card + new `mod/contract/relic.schema.json` + both vocabularies + statuses + `mod/content/cards`); every contract
attr has a `BTSGEN_*` override, `paths.prototype_overrides()` / `use_prototype_contract()` reach the archived
prototype, and `point_btsgen_at_mod_contract()` is a no-op safety net. `_STATUS_WEIGHT` is keyed to all 18 mod
statuses (Intangible 8, Ritual/Strength/Barricade 4, Dexterity/Metallicize/Buffer/Focus 3, Vulnerable/Thorns/Regen/
Artifact/Blur/temp_strength 2, Weak/Frail/temp_dexterity 1.5, Poison 1.2). The prototype composites are out of
`_BUILD_AROUND_OPS` and live only in `_LEGACY_PROTOTYPE_OPS`, consulted when `_mod_contract` is False; the legacy
relic/character modules + CLIs carry a LEGACY banner and the two generate CLIs warn. **Deviations from the plan
text, deliberately:** (a) the prototype ops are GATED, not deleted — deleting them retires the prototype-era
validator suite (test_validator / test_relic_validator / test_character_pipeline / test_pipeline_balance_repair),
which is a separate decision; those four tests now pin the prototype contract themselves for standalone runs;
(b) the legacy CLIs are deprecated, not rewired onto `class_forge` (they generate a single relic/character, which
the mod has no concept of). Tests: `tests/test_phase_ajb.py`; `test_contract_binding` updated (env-clean default =
mod); suite 372 passed; every test file also runs standalone.

**STATUS (2026-09-09): Wave 2 EXECUTED (no vocab bump)** — all four items landed. **W2.1** `census.py` now counts
multi-hit (`hits` ≥ 2 on damage / summon_attack — and a multi-hit card is no longer "plain"), the four keywords
(exhaust / retain / innate / ethereal, with `multi_hit` joining them as a keyword KIND), `apply_status_custom`
statuses, `buff_summon` statuses (default strength), the poison / frail / focus SPECIALTY bucket (neither generic nor
exotic), `tags`, `upgrade.cost`, `once_per_turn`, `ripen` amounts and targeted trigger payloads; `format_report` prints
every counter (fixed baseline columns first, then the full tally). **W2.2** `coverage.py`: `WHEN_MENU_V2` +
retained_last_turn / draw_pile_empty / hp_lost_ge / target_has_status; `WHEN_MENU_KIND` (forged_ge → forge, dark_ge /
light_ge / centered → balance, orbs_match / orb_count_ge → orb) gated by the class's kind set
(`harness_v2.pool_kind`, the blueprint kind ∪ the selected archetypes' `mechanic_kind`); `SCALE_MENU` (5 sources) +
`SCALE_MENU_KIND` (tag_cards_owned → tags, forged → forge) replace the one fixed scale directive; `EXOTIC_NOMINATE_ONLY`
(ritual / barricade / intangible — never dealt off the shuffle, reachable by nomination); `KEYWORD_MENU` (retain /
innate / ethereal / hits) with `MIN_KEYWORD_KINDS = 2`; `NOMINATION_CATEGORIES` += scale / keyword; a `CENSUS_DETECTOR`
per menu key; the blueprint's nomination ask names every category and the class-kind keys. **Deviation, deliberate:**
the widened menus and the keyword quota ride the creative-harness-v2 path only — the v1 menus / quotas stay
byte-for-byte because `BTS_HARNESS_V2` is the live A/B and the control arm must not move. **W2.3** `featured.py`:
`FEATURED_CLASS_KIND` (orb / status / summon / forge / balance / discard / transform — 12 entries), `roll_class_kind`
(one pick per class, seeded on the concept with its own salt, kind-order-proof), `Featured.carried_by` (`min_cards` = 3
for the custom-status spread, `detect_pool` for the scry + on_discard loop). The pick is dealt AFTER the blueprint (the
kind is only known then) and enforced by the coverage round like any featured miss. It is dealt on the triad path too:
the 2026-08-15 triad exclusion was about the wild slot landing off-theme subsystems, and these entries only exist for
the class's own kind (`test_triad` updated: no base-menu ids under triad, exactly one class-kind id on an orb fake).
**W2.4** `class_forge.py`: blueprint `max_energy` (2..4; assembly default 3) and `color` (a hue 0-359, a palette name
crimson/amber/gold/emerald/teal/azure/violet/magenta, `{hue}` or `{h,s,v}` — emitted as the importer's `{h,s,v}`;
omitted → the engine's per-slot hue), `max_hp` 55..100, `orb_slots` ≤ 5, summon `max_hp` ≤ 100 (the C# ranges stay the
hard ceiling); the prompt grew two format fields + one rule line; the legacy `character_validator` bands follow.
Tests: W2 checks appended to `tests/test_census.py` (68), `test_coverage.py` (215), `test_featured.py` (153),
`test_forge.py` (88); suite **380 passed**; four v2 fake forges verified end-to-end (forge → blade_recall, summon →
summon_drill, orb → orb_focus_power, normal → none; colors + energy in the bundle). NOT in this wave: the cross-cutting
"vocab drift" / "prompt-vs-vocab" tests.

**STATUS (2026-09-09): Phase AK EXECUTED (vocab v41)** — both items landed in lockstep. **(1) `target:"attacker"`** on an
`attacked` payload: `ForgedTriggerPower.AfterDamageReceived` hands the dealer into `FireReactive(kind, ctx, attacker)` →
`TriggerRunner.Run(t, player, ctx, attacker)` → `ResolveEnemies` resolves `"attacker"` to it when alive (the RelicRunner L-3
pattern; a dead attacker = empty target list = no-op). Validate/ValidateTrigger accept it on `attacked` only (any other
trigger, card level, a self-buff status or a scale are rejected); Describe/`cardgen` read "… to the attacker" byte-identically;
the C# emit carries the named `Target: "attacker"`. **(2) `once_per_combat`** on `add_trigger`: a new `EffectSpec.OncePerCombat`
(parsed from `once_per_combat`), a `_firedThisCombat` set on the per-combat power instance (checked + consumed in `FireReactive`
and the `on_hp_lost` inline path), allowed on `OncePerCombatTriggers` = every multi-fire kind EXCEPT the card-latent `on_discard`
(no power instance to carry the flag; DataCard tracks it by round) — turn_start/turn_end/ripen, payload-level, card-level and
the `once_per_turn` + `once_per_combat` pair are all rejected; wording "… (once per combat)."; emit `OncePerCombat: true`.
Lockstep: `CardSpec.cs`, `ForgedCards.cs` (VocabVersion 41), `ForgedTriggerPower.cs`, `TriggerRunner.cs`, `card.schema.json`
(payload target enum + `once_per_combat`), `VOCABULARY.md` (add_trigger row, a `once_per_combat` bullet, the attacker paragraph),
`cardgen.py`, `validator.py` (`_ONCE_PER_COMBAT_TRIGGERS`), `census.py` (`once_per_combat` counter), `coverage.py` /
`featured.py` (the attacked directive/injection name the attacker target), `bts1.py` VOCAB_VERSION 41, `exemplar_pool.json`
(Spiked Guard → attacker; + Return Stroke, Second Wind), `archetypes.json` (counter_riposte ops += attacker /
once_per_combat). Tests: `tests/test_phase_ak.py` (48 checks); suite **382 passed**; C# build 0 errors. AutoSlay (tester
`generation/scratch/gaptest-ak/build_tester.py`, slot 04, three seeds): **GAPTESTAK1** 6 `[AK]` tags (a single-wurm fight —
riposte damage ×2, Weak-to-attacker ×2, once_per_combat `attacked` ×1 and `on_card_played` ×1, each consumed exactly once);
**GAPTESTAK2** a long run, **237 `[AK]` tags** — 176 riposte damage + 57 Weak "to the attacker (resolved)", **2 "no living
attacker — skipped"** (the attacker died to the damage riposte before the Weak rider — where `target:enemy` would have hit
another enemy), both once_per_combat kinds consumed; a LEAF_SLIME_S + LEAF_SLIME_M fight fired the riposte on each slime's
own attack and NOT on the M's non-damaging Sticky Shot; **0 mod-attributable exceptions** in both (the only exception frames
are BaseLib's own two startup Harmony patches — its networking `AdjustCustomMessageKeys` and the `RelicCollection.LoadRelics`
patch already noted in the Phase L plan — plus the documented merchant map-nav watchdog, which is the tool's FAIL verdict);
**GAPTESTAK3** was a harness launch miss (the game reached the main menu with the mod loaded but the AutoSlay hook never
fired — not mod-attributable). Caveat: the game log does not print the struck creature's name, so attribution is evidenced by
the dealer plumbing + the dead-attacker no-ops, not by a per-target damage line. Closed: the gap #4 nuance (`VOCABULARY_GAPS.md`)
and the Phase J "J-3 true Thorns" item (both stamped). Tag evidence: `generation/scratch/gaptest-ak/godot_AK_tags_GAPTESTAK{1,2}.txt`.

**STATUS (2026-09-09): Phase AL EXECUTED (vocab v42)** — all three items landed in lockstep. **(1) Class engines as payloads:**
`TriggerOps` += `apply_status_custom` (status class — untargeted = GAIN the buff on the player; with a payload `target` = APPLY
the debuff to the resolved enemies, buff/debuff split read off the resolved `StatusSpec.IsBuff` exactly like the card path),
`summon_attack` (summon class — the pet is the dealer, `target` optional → enemy/all_enemies/attacker, default the first
living enemy; no summon = logged no-op) and `buff_summon` (summon class; `SummonRunner.ApplyBuff`). `TriggerTargetedOps` +=
`summon_attack` / `apply_status_custom`. The class is read off the player at fire time (`ClassIndexOfPlayer`, the heal_summon
pattern). **(2) `hits` on a payload `damage`/`summon_attack`** — `TriggerRunner` loops the intrinsic hit; rejected on every
other payload op and together with a scale. **(3) Payload `scale`** — `TriggerScale` (const) became `TriggerScales` =
cards_retained / cards_in_hand / unspent_energy_last_turn / forged + `TriggerScalableOps` (block/draw/gain_energy/heal/
lose_hp/gain_orb_slot/self apply_status + a TARGETED damage — the H4 "a targeted effect can't be scaled" rule is lifted for
damage ONLY); `forged` keeps its ADDITIVE damage/block-only, amount ≥ 1 shape ("gain 2 Block, plus your Forge");
`TriggerRunner.ResolveAmount` resolves them at fire time. Wording: `TriggerScalePhrase` ("equal to cards retained" unchanged /
"the cards in your hand" / "your unspent energy last turn"), "deal N damage H times{to}", "deal N damage [H times] with your
summon{to}", "your summon gains N Strength", "gain N Razor Focus" / "apply N Brittle to ALL enemies" — byte-lockstep with
`cardgen._trigger_fragment`. **Deviation, deliberate:** scale on a payload is now RESTRICTED to the ops whose fragment can
word it (before, `discard`/`add_card`/… silently accepted `scale:cards_retained` and ran the scaled amount while the text
showed the literal). Lockstep: `ForgedCards.cs` (VocabVersion 42), `TriggerRunner.cs`, `CardSpec.cs` docs, `card.schema.json`
(triggerEffect: op enum, `hits`, `status_name`, `scale` enum, target/op coupling, allOf rules), `VOCABULARY.md` (three table
rows, Structural mechanics, Triggers bullets), `cardgen.py`, `validator.py` (`_TRIGGER_SCALES` / `_TRIGGER_SCALABLE_OPS` +
class-context checks), `census.py` (`payload_ops` / `scaled_payloads` / `multi_hit_payloads` + report line), `bts1.py`
VOCAB_VERSION 42, `featured.py` (class-kind entries `custom_status_engine` + `summon_engine`, detected via `payload_ops`),
`class_forge.py` (a one-line pointer in the TRIGGERS paragraph, paid for by trimming its second brief example — rule 0.9),
`archetypes.json` (summon_swarm + status_signature ops += add_trigger), `exemplar_pool.json` (+7: Honing Ritual, Thrall's
Hour, Drill Cadence, Flurry Ward, Ember Tithe, Thrift Bulwark, Crowded Mind; pool 84 → 91), `PHASE_K…` K-3 stamped. Tests:
`tests/test_phase_al.py` (87 checks); `test_phase_ak` / `test_h4_triggers` / `test_forge` re-pinned (a targeted DEBUFF is
the scaled-targeted rejection now; `scale:forged` on a block payload is LEGAL); suite **384 passed**; every `test_phase_*.py`
runs standalone; C# build 0 errors. **AutoSlay finding → fix:** `AfterSideTurnEnd` fires AFTER the end-of-turn discard, so
a `turn_end` payload `scale:cards_in_hand` read **0 on all 59 fires** in GAPTESTAL1 — both validators now REJECT
`cards_in_hand` on a `turn_end` trigger (use turn_start / a reactive trigger, or `cards_retained`); the exemplar and tester
moved to turn_start; VOCABULARY.md + schema say so. AutoSlay (tester `generation/scratch/gaptest-al/build_tester.py` — a
status+summon class, staged into slot 04): **GAPTESTAL1** PASS RunCompleted, **506 `[AL]` tags** — summon_attack x2 through
'Bone Thrall' ×91 (90 with a living target, 1 empty), buff_summon ×75, custom BUFF (Razor Focus) ×69, custom DEBUFF (Brittle
to all_enemies) ×45, x3 riposte to the attacker ×39 (all resolved), `unspent_energy_last_turn` ×56 (read 3–8),
`forged` ×65 (2 + Forge 0..20 → 2–22), plus 7 no-summon no-ops · **0 mod exceptions** (the only exception frames are BaseLib's
two startup Harmony patches and AutoSlay's own end-of-run Options-button timeout). **GAPTESTAL2** (after the fix, the
tester's Crowded Mind moved to turn_start) — a short run (the documented merchant map-nav watchdog ended it, tool verdict
FAIL, not mod-attributable): 8 `[AL]` tags, `cards_in_hand` at turn START read **5** on both fires (vs 0 on turn_end in
run 1) · 0 mod exceptions. **GAPTESTAL3** — likewise short (map-nav watchdog): 10 `[AL]` tags, `cards_in_hand` at turn
start read 5 ×2, buff_summon / summon_attack / Brittle / unspent / forged all fired again · 0 mod exceptions (the only
non-Harmony errors are the base game's own "Dev console used before being created"). The AL tester stays staged in
slot 04 (the smoke tool restores only its relic injection). Tag evidence:
`generation/scratch/gaptest-al/godot_AL_tags_GAPTESTAL{1,2,3}.txt`.

**STATUS (2026-09-09): Phase AM EXECUTED (vocab v43)** — both items landed in lockstep. **(1) Five card-level scales:**
`SupportedScales` += `block` (Body Slam; on a `block` effect = Entrench), `hp_lost_this_turn` (the AD `HpLossTracker`
snapshot read as a number), `draw_pile_count`, `energy`, `plays_this_combat` — one `EffectRunner.ScaleValue` case each
(`Creature.Block` / `HpLossTracker.HpLostThisTurn` / `DrawPile.Cards.Count` / `PlayerCombatState.Energy` / a new
`CardsPlayedThisCombat(player)`), so the `DataCard.BonusFor` calc-var preview and the resolved number share one read.
Rules: `block` / `hp_lost_this_turn` / `draw_pile_count` / `plays_this_combat` are damage/block-ONLY (`DamageBlockOnlyScales`
/ `_DAMAGE_BLOCK_ONLY_SCALES` — a draw equal to your Block or draw pile is absurd); `energy` is damage/block/draw but
**cost-0 cards ONLY** (checked after the cost is parsed, beside the X-cost coupling): the game spends the cost BEFORE
OnPlay (`PlayCardAction.SpendResources` → `OnPlayWrapper`, verified in the decompiled source), so on a paid card the
in-hand preview (pre-pay) and the dealt amount (post-pay) would differ by the cost. **Deviation, deliberate:** the plan's
`plays_this_combat` pointed at `EffectRunner.PlaysThisCombat` (the per-card-INSTANCE count that feeds `grow`); with
replace semantics that reads 0 on the first play, so the scale is the PLAYER-level count of cards you have finished playing
this combat (`CombatHistory.CardPlaysFinished` filtered by owner, the base-game Finisher pattern; the in-flight card is not
yet counted). Wording (byte-lockstep `ScalePhrase` / `cardgen._scale_phrase`): "your Block" / "the HP you have lost this
turn" / "the cards in your draw pile" / "your energy" / "the cards you have played this combat". **(2) Four conditions:**
`Conditions.Kinds` += `target_hp_below_half`, `target_has_block` (chosen-target reads off `play.Target` — a new
`Conditions.TargetKinds` / `_TARGET_CONDITIONS` set: **single-enemy cards only** (`target:"enemy"`; AoE has a null play
target, self/random_enemy none) and never on an `add_trigger` `when`, both validators), `energy_ge` {1..6} (on a card:
the energy left AFTER this card's cost is paid — same SpendResources ordering; on a trigger: energy at fire time) and
`cards_played_this_turn_ge` {1..10} (`CardsPlayedThisTurn(player)` = finished plays with `HappenedThisTurn` + owner filter;
on a card it counts the OTHER cards; on a `turn_end` trigger the whole turn). Caps are `Conditions.EnergyGeMax` /
`CardsPlayedGeMax` + schema `allOf` clauses. Phrases: "the enemy is below half HP" / "the enemy has Block" / "you have
N+ energy" / "you have played N+ cards this turn". Log tag `[AM]`: the five scales log their live read at resolution
(damage/block/draw sites), the four gates log BOTH branches with the value they compared against (card level in
`EffectRunner.Execute`; trigger level in `TriggerRunner.Run` + `ForgedTriggerPower.FireReactive`). Lockstep: `Conditions.cs`,
`EffectRunner.cs`, `ForgedCards.cs` (VocabVersion 43, SupportedScales, Validate, ValidateTrigger, ScalePhrase, the cost-0
rule), `TriggerRunner.cs`, `ForgedTriggerPower.cs`, `card.schema.json` (scale + kind enums, two value-cap clauses),
`VOCABULARY.md` (five scale bullets, four condition rows — ONE LINE each), `cardgen.py`, `validator.py`, `bts1.py`
VOCAB_VERSION 43, `coverage.py` (WHEN_MENU_V2 += 4, SCALE_MENU += 5), `featured.py` (+ `body_slam`, `executioner`,
`combo_finisher`), `class_forge.py` (one-line pointers in the CONDITIONS and SCALED AMOUNTS paragraphs), `archetypes.json`
(threshold_duelist / big_energy / block_bulwark / self_sacrifice ops), `exemplar_pool.json` (+9: Iron Tackle, Blood Toll,
Deep Reserves, Surge Strike, Crescendo, Culling Blow, Shatter Guard, Overcharge, Flurry Finish; pool 91 → 100). **Rule 0.9
budget:** the blueprint prompt embeds VOCABULARY.md verbatim, so the first draft (multi-line bullets) grew it by 2.8k chars;
compressed to one-line pointers + two duplicate phrases trimmed, the net is **+1.5k chars (84,764 → 86,283, seed 1)** — all
of it one-line menu pointers per the rule's second clause. Tests: `tests/test_phase_am.py` (105 checks); `test_phase_al`
re-pinned to `>= 42`; `test_coverage` / `test_featured` samples extended; suite **386 passed**; every `test_phase_*.py` runs
standalone; C# build 0 errors. AutoSlay (tester `generation/scratch/gaptest-am/build_tester.py` — a plain class, staged into slot 04 over the AL tester,
unstaged afterwards; two seeds): **GAPTESTAM1** **407 `[AM]` tags** — scale block ×66 (18 distinct reads, 2 → 157), energy ×62
(3–6, damage AND draw, cost-0 cards), hp_lost_this_turn ×31 (4/8/12/20 — the Blood Toll self-cost plus damage taken),
draw_pile_count ×20 (1 → 47, shrinking as the fight draws), plays_this_combat ×18 (0 → 41, climbing within a combat and
resetting per combat); gates: cards_played_this_turn_ge OPEN ×69 / closed ×21, energy_ge OPEN ×36 (the bot always held
2+ after paying), target_hp_below_half OPEN ×12 / closed ×9 ("target HP 5/47" vs "30/58"), target_has_block OPEN ×1 /
closed ×12 ("target Block N"); trigger-level gates on turn_end: energy_ge ×34, cards_played_this_turn_ge ×16 ("played 7
this turn; need 3") · **0 mod-attributable exception frames** (the only exception blocks are BaseLib's two startup Harmony
patches). **GAPTESTAM2** 146 `[AM]` tags — every scale and gate fired again (energy ×31, block ×18, plays_this_combat ×11,
hp_lost ×10, draw_pile ×7; both branches of target_hp_below_half and cards_played_this_turn_ge; target_has_block closed
×17 — the second seed never met a blocking enemy on that card) · 0 mod exceptions. Harness caveat: BOTH smoke runs had
their Python harness killed by the OS for low memory mid-run (no tool verdict), while the game kept playing under AutoSlay —
the tags above were harvested from the live godot.log and the game stopped by hand (`Stop-Process`); neither run reached
RunCompleted or the map-nav watchdog, and no hang was mod-attributable. Tag evidence:
`generation/scratch/gaptest-am/godot_AM_tags_GAPTESTAM{1,2}.txt`. Follow-ups (not in scope): the five AM scales are
card-level only — `block` / `energy` inside a trigger payload ("at turn end, deal damage equal to your Block") would need
`TriggerScales` + `ResolveAmount` + the trigger wording; `plays_this_combat` reads 41 in a long fight, so the vocabulary
pins it to uncommon/rare on a nominal base.

**STATUS (2026-09-09): Phase AN EXECUTED (vocab v44)** — all three items landed in lockstep. **(1) `gain_max_hp`** (card-only,
`amount` 1..5): `CreatureCmd.GainMaxHp(player, amt)` — verified in the decompiled `CreatureCmd`: it SETS the new max, then
`Heal(num)` for the gained amount, so the op is exactly the base-game Feed payoff (max HP up AND healed). The card carries a
real `MaxHpVar` (the game's own `{MaxHp}` var, upgrade-aware; VarKey `MaxHp` → "each value once"), text "Gain {MaxHp} Max
HP."; not in `TriggerOps` / the `triggerEffect` op enum (a per-turn max-HP engine is degenerate). Cap `GainMaxHpMaxAmount` /
`_GAIN_MAX_HP_MAX` = 5 + a schema clause; the vocabulary pins it to uncommon/rare on an exhausting attack; the validator
prices it at 4/pt (a permanent buff) so a common can't carry it cheaply. **(2) `unblockable:true` on `damage`:** the flag
rides the damage var's ValueProp — `DataCard` declares `new DamageVar(amount, Move | Unblockable)` (BaseLib's `WithDamage`
pins Move-only, so the var is built directly and passed via `WithVar`) or `WithCalculatedDamage(…, props)` for the scale /
`grow` shapes — and BaseLib's `CommonActions.CardAttack` reads `DamageVar/CalculatedDamageVar.Props` into the AttackCommand
while `Hook.ModifyDamage` previews with the same Props, so the in-hand number and every dealt hit both bypass Block (Block is
neither reduced nor consumed; Move without Unpowered stays a powered attack: Strength/Vulnerable/Weak apply, Thorns answers
it). Damage-only (both validators), CARD-LEVEL ONLY (a payload damage is an intrinsic `CreatureCmd` hit with no var to flag;
`ValidateTrigger` + validator + the `triggerEffect` schema all reject it). Wording: the clause ", ignoring Block" closes the
damage sentence in every shape ("Deal {Damage} damage {Hits} times to ALL enemies, ignoring Block." / "Deal damage equal to
your Block, ignoring Block." / "Deal {Damage} damage, ignoring Block. Grows by 3 …"); byte-lockstep `Describe` /
`cardgen.describe`, emit `Unblockable: true` named arg. Scoring premium +50% of the number. **(3) `temp_thorns` /
`temp_focus`:** `ForgedTempThornsPower` / `ForgedTempFocusPower` — `CustomTemporaryPowerModel` shells exactly like the temp
stats (internal `ThornsPower` / `FocusPower`; the base removes the stacks in `AfterSideTurnEnd`). Verified ordering for
temp_focus: orb passives fire in `OrbQueue.BeforeTurnEnd` (decompiled), BEFORE the AfterSideTurnEnd removal — so a one-turn
Focus boosts this turn's evokes AND the end-of-turn passives, then expires (worth shipping; orb-class-only like `focus`:
`class_forge._card_uses_orbs` + `_ORB_TOKENS` treat it as an orb mechanic). Worded like the temp stats ("Gain Thorns." /
"gain 3 Thorns" in a payload; `SelfBuffStatuses` so they always land on the player); legal as a SELF trigger payload, never
targeted. Wired through every status switch: `EffectRunner` (card + relic), `DataCard` (`WithPower<T>`), `TriggerRunner`,
`OrbRunner`, `SummonRunner`, both `StatusName` maps, the relic schema/vocabulary, `statuses/temp_*.json` (ref-integrity),
census (temp_thorns exotic, temp_focus specialty), `_STATUS_WEIGHT` (1.0 / 1.5). Log tag `[AN]`: gain_max_hp logs
before → after Max HP + current HP; unblockable logs the hit count, the target's Block at resolution and the var's Props;
temp_* log the apply (card path) and the power itself logs its expiry at the end of the owner's turn (`ExpiryLogTag` on the
abstract `ForgedTempStatPower`, after the base removal). Lockstep: `CardSpec.cs` (`Unblockable`), `ForgedCards.cs`
(VocabVersion 44, SupportedOps/AmountOps/SupportedStatuses, `GainMaxHpMaxAmount`, parse, Validate, ValidateTrigger, VarKey,
Describe, StatusName), `EffectRunner.cs`, `DataCard.cs`, `TriggerRunner.cs`, `OrbRunner.cs`, `SummonRunner.cs`,
`ForgedTempStatPowers.cs`, `card.schema.json` (op enum + description, `unblockable` property, two status enums, two allOf
clauses), `relic.schema.json`, `VOCABULARY.md` (damage-row clause, `gain_max_hp` row, two status rows, the payload self-buff
list, the orb paragraph — ONE LINE each), `RELIC_VOCABULARY.md`, `DESIGN_HEURISTICS.md` (one sentence on the burst note),
`statuses/temp_thorns.json` + `temp_focus.json`, `cardgen.py`, `validator.py`, `census.py` (+ `unblockable` counter),
`bridges.py` (`unblockable` witness token), `bts1.py` VOCAB_VERSION 44, `coverage.py` (EXOTIC_MENU_V2 += temp_thorns),
`featured.py` (+ `devourer`, `piercing_strike`; burst_window detects temp_thorns; orb menu + `orb_flash_focus`),
`class_forge.py` (self-buff sets, orb tokens, three fantasy→mechanic pointers), `archetypes.json` (iron_regrowth +=
gain_max_hp, strike_tempo += unblockable, burst_window += temp_thorns, orb_channel += temp_focus), `exemplar_pool.json`
(+4: Devouring Bite, Piercing Lunge, Bristle Up, Flash Focus [needs orb]; pool 100 → 104), `web/static/app.js` (status
names + the two phrases). **Rule 0.9 budget:** blueprint prompt **+1,340 chars (86,283 → 87,623, seed 1)** — all one-line
pointers. Tests: `tests/test_phase_an.py` (71 checks); `test_featured` / `test_exemplars` samples extended; suite
**388 passed**; every `test_phase_*.py` runs standalone; C# build 0 errors. AutoSlay (tester
`generation/scratch/gaptest-an/build_tester.py` — an ORB class so temp_focus is live, staged into slot 04, unstaged
afterwards): **GAPTESTAN1** **387 `[AN]` tags** — gain_max_hp ×47 (Devouring Bite +3/+4 ×23, Greedy Gulp +1/+2 ×24; Max HP climbed **80 → 206** across the run, every line showing the matching heal — "80 -> 83 (HP now 67)"), unblockable ×118 (Piercing Lunge ×37 + Body Pierce ×39 single-target with the target's Block read at resolution — including a hit into "target Block 6" — and Rending Volley ×42 AoE multi-hit; every line shows the var's props as "Unblockable, Move", the CalculatedDamageVar path via Body Pierce), temp_thorns +4/+6 ×75 with 60 end-of-turn expiries (stacked to "had 16" on a big turn), temp_focus +2/+3 ×30 with 57 expiries (the 27 extra expiries with no card-level apply are the Surge Stance trigger path — TriggerRunner.ApplySelfBuff → the same power; stacked to "had 5") · **0 mod-attributable exception frames** (the 7 Exception lines are BaseLib's two startup Harmony patch failures + their inner-exception echoes). Harness caveat, same as AM: the Python harness was killed by the OS for low memory (~1.9 GB free at launch; no tool verdict) while the game kept playing under AutoSlay — tags harvested from the live godot.log, game stopped by hand (`Stop-Process`); no hang was mod-attributable. One seed only (memory). Tag evidence: `generation/scratch/gaptest-an/godot_AN_tags_GAPTESTAN*.txt`.

**STATUS (2026-09-09): Phase AO EXECUTED (vocab v45)** — the op landed in lockstep, plus the relic form the plan promised.
**`cost_shift {card_type: attack|skill|power|all, amount: 1..2, scope: this_turn|combat, count?: 1..3}`** — "Your Attacks cost 1
less this turn." / "Your next Skill costs 2 less this turn." / "Your next 2 cards cost 1 less this turn." / "Your Skills cost 1 less
this combat." **Deviation, deliberate:** the plan wrote `amount: -1..-2`; the contract's `amount` is `minimum: 1` everywhere and
every op reads it as a magnitude, so `amount` is the DISCOUNT (1..2) and the sentence says "cost N less". The plan's "count:1 gives
'next Skill costs 0'" is the count-1 form with amount 2 (every Skill in the 0..3 band but a 3-cost goes free); a set-to-0 would
have been a second semantic on the same op, so it was not added. **Engine:** `Powers/ForgedCostShiftPower.cs` — ONE power per
player holding a LIST of live discounts (the game keys powers by type per creature, so a class-per-card_type would still collide
on scope/count; the list lets "Attacks -1 this turn" and "Skills -1 this combat" coexist). Native Amount mirrors the live entry
count (the Phase-J/S live-stack mutation; RemovePowerInternal when the list empties). Hooks, all verified against the decompiled
source before building: `TryModifyEnergyCostInCombat` (the EARLY pass — `Hook.ModifyEnergyCostInCombat` runs every early listener
before the Late pass, so the discount composes additively with a relic `cost_reduction` and Corruption's Late set-to-0 still wins;
`CardEnergyCost.GetWithModifiers` skips the global hook for X-cost and floors at 0, so nothing goes negative or touches X);
`AfterCardPlayed` consumes a use of each matching budgeted entry (`PlayCardAction.SpendResources` runs before `OnPlayWrapper`
fires the card-played hooks, so a use is never spent before the discounted card is paid for — the base game's `FreeAttackPower`
decrements on the same edge); an `Armed` flag keeps the GRANTING card from spending its own use (the power is added in that card's
OnPlay and its AfterCardPlayed fires right after — "your next Skill costs 1 less" on a Skill would otherwise eat itself);
`AfterSideTurnEnd` (owner's side) drops the this_turn entries, the temp-stat lifetime. Only cards in hand / in play are
discounted (the FreeAttackPower pile check). **Found by the smoke, fixed before commit:** `card_type:"all"` matched Statuses and
Curses — GAPTESTAO1 logged Ascender's Bane (cost -1, unplayable) rewritten to 0 (the engine's own hook skips negative costs, but
`CardCostHelper.TryModifyEnergyCostWithHooks` hands listeners the raw preview cost); `all` now means Attacks/Skills/Powers and the
hook passes any `originalCost <= 0` through untouched. Rules (both validators + schema): `card_type` ∈ attack/skill/power/all,
`scope` ∈ this_turn/combat, `amount` 1..2, `count` 1..3 optional; `scope:combat` is amount 1 (a whole-combat -2 is Corruption
without the tax), **rare-only** (generation side) and **≤1 such card per class** (`character_validator.cost_shift_warnings` — the
plan's loop-discipline rule; they stack); the three fields belong to cost_shift alone; at most one per effect list; never on a
BASIC; card-only (not in `TriggerOps` / the `triggerEffect` op enum — a turn_start "your next Attack costs 1 less" engine is a
follow-up if demanded). **Relic form** (closes the Phase-L "first card costs 0" deferral, `PHASE_L…:367-369`): `cost_shift` is a
relic hook op (`RelicEffectOps`, `TryParseRelicEffect` via the shared `ForgedCards.ValidateCostShift(relic:true)`,
`RunRelicEffects`, `relic.schema.json`, `RELIC_VOCABULARY.md`, `class_forge._RELIC_EFFECT_OPS` + `_validate_relic`) — `scope`
must be `this_turn` on a hook (a per-turn hook adding combat-scoped entries would accumulate; the whole-combat relic discount
stays the `cost_reduction` modifier); `turn_start` + `card_type:"all"` + `count:1` = "your first card each turn costs 1 less".
Describe, byte-lockstep (`ForgedCards.CostShiftSentence` / `cardgen._cost_shift_sentence`): literal numbers, no DynamicVar (like
forge / balance_step). Pricing (`validator._score_effect`): energy in disguise — a this-turn typed discount at 4/pt (`all` 5.5, just
under gain_energy's 6), the count form ×0.6 per covered play, the combat scope ×3 (a rare build-around; in `_BUILD_AROUND_OPS`).
Log tag `[AO]`: every add (entry text + live count), every discounted card's cost once per combat (`a -> b (-r)`, with the
card type), every consumed use (uses left), every end-of-turn expiry, the power removal. Lockstep: `CardSpec.cs` (`CardKind` /
`Scope` / `Count` — named CardKind so it doesn't shadow the game's `CardType` enum), `ForgedCards.cs` (VocabVersion 45,
SupportedOps / AmountOps, `CostShiftKinds` / `CostShiftScopes` / caps, `ValidateCostShift`, parse, Validate, the ≤1 rule,
Describe + `CostShiftSentence`), `EffectRunner.cs` (card + relic cases), `DataCard.cs`, `ForgedCharacters.cs`, `MainFile.cs`
(🏷️ icon kick), `ForgedCostShiftPower.cs` (new), `card.schema.json` (op enum + description, `card_type` / `scope` / `count`
properties, two allOf clauses), `relic.schema.json` (op + the three properties with `scope` const this_turn, two clauses),
`VOCABULARY.md` (one row), `RELIC_VOCABULARY.md` (one row), `DESIGN_HEURISTICS.md` (one sentence on the tempo_draw note),
`bts1.py` VOCAB_VERSION 45, `cardgen.py` (emit named `CardKind:` / `Scope:` / `Count:` args; describe), `validator.py`
(constants, per-effect + per-card rules, build-around, pricing), `character_validator.py` (`cost_shift_warnings`) +
`character_pipeline.py`, `featured.py` (+ `cost_trick`), `class_forge.py` (a fantasy pointer, a one-clause pointer in the
CORRUPTION section, the relic op gate), `archetypes.json` (tempo_draw + big_energy += cost_shift), `exemplar_pool.json` (+3:
Open Throttle, Quiet Step, War Economy; pool 104 → 107), `web/static/app.js` (the phrase). **Rule 0.9 budget:** blueprint prompt
**+1,233 chars (87,623 → 88,856, seed 1)** — pointers only, no new section. Tests: `tests/test_phase_ao.py` (75 checks: shape /
every reject / describe in 12 shapes / emit / census + detector / pricing order / relic through both gates / the set warning /
contract presence); `test_featured` sample extended; suite **390 passed**; every `test_phase_*.py` (25) runs standalone; C# build
0 errors. AutoSlay (tester `generation/scratch/gaptest-ao/build_tester.py` — a normal class with all six shapes + the
Apprentice's Patience relic, staged into slot 04, unstaged afterwards): **GAPTESTAO1** (pre-fix build) **2,938 `[AO]` tags** —
cost hook ×1,696 (Skill 895 / Attack 742 / Power 59; costs `2 -> 1`, `1 -> 0`, stacked `2 -> 0` when two entries overlapped),
adds ×663 across every shape (relic "next 1 cards -1" every turn start, `quiet_step` next-1-skill, `twin_edge` next-2-attacks,
`momentum` next-3-cards, `open_throttle` / `cheap_powers` flat, `war_economy` ×19 combat-scoped — each "N live" climbing as the
list grew), uses consumed ×377 (the count forms ran down to "0 left"; Quiet Step never spent itself), 138 end-of-turn expiries,
the list emptying to "power removed" · **0 mod-attributable exception frames** (the 7 Exception lines are BaseLib's two startup
Harmony patch failures + echoes) · verdict "HANG — wall-clock timeout" is the harness's 10-minute wall clock (the AutoSlay log
shows "Turn 5: playing cards" at the cut; no mod frame) · the 63 Curse/Status lines are the bug described above.
**GAPTESTAO2** (the fixed build) **2,289 `[AO]` tags** — cost hook ×1,239 (Attack 654 / Skill 482 / Power 103), adds ×500+ across the same six shapes, uses consumed ×384, 56 expiries · **0 Curse/Status lines** (the filter holds) · 0 mod-attributable exception frames · the same wall-clock verdict with the AutoSlay log mid-turn at the cut. Tag evidence: `generation/scratch/gaptest-ao/godot_AO_tags_GAPTESTAO{1,2}.txt`.

**STATUS (2026-09-10): Phase AP EXECUTED (vocab v46)** — all three items landed in lockstep. **(1) `discard` gains `cards:
random|choose`** — `choose` opens the base-game hand picker (`EffectRunner.DiscardChoose` → `CardSelectCmd.FromHandForDiscard`
with a fixed-count `DiscardSelectionPrompt`; the discard-styled `FromHand`, so it auto-returns the whole hand at ≤ N cards and no-ops
the empty hand), then discards through the SAME effect-discard path as the random form (`CardCmd.Discard` → the on_discard payoffs; since
Phase AU that is the game's own `Hook.AfterCardDiscarded`), so a
chosen discard fuels Reflex cards exactly like a random one. Card-only: a payload `discard` must be `random`/absent (both
`ValidateTrigger` and `validator.py` reject `choose` in a payload — the repeating-pick-UI footgun; `TriggerRunner` still calls
`DiscardRandom`). Describe: "Discard {Discard} card(s) of your choice." (the Phase-R random text is byte-unchanged; `VOCABULARY.md:37`
reworded as W0.2 promised). **(2) `retrieve_card {pile: discard|exhaust, cards: random|choose, amount?: 1..2}`** — the Headbutt /
Exhume shape: `EffectRunner.RetrieveCards` filters the pile to retrievable cards (never a Status/Curse — a random recursion pulling a
Wound back is anti-fun), picks via `CardSelectCmd.FromCombatPile(ctx, pile, owner, prefs, filter)` (choose; the `DiscardSelectionPrompt`
loc key is reused — the game has no "return to hand" prompt and inventing a key is the gap-#26 crash rule) or the run's
`CombatCardSelection` RNG (random), then moves each card with `CardPileCmd.Add(card, Hand, Random)` — the exact call Phase T's blade
retrieval already makes from any pile, exhaust included. **Deviation, deliberate:** the plan wrote `{pile, cards}`; an optional
`amount` 1..2 was added (default 1, not in AmountOps — add_card's copies precedent) so "Return 2 random cards" is one op, not two.
Card-only, at most one per card. Priced as a build-around: random 3/card (under a draw's 5), choose 5/card (a tutor), exhaust +1
(Exhume). **(3) `add_status_card {card: dazed|wound|burn, pile: hand|discard|draw, amount?: 1..3}`** — `EffectRunner.AddStatusCards`
builds each card owner-bound via `CombatState.CreateCard<Dazed|Wound|Burn>(owner)` and adds it with
`CardPileCmd.AddGeneratedCardToCombat(card, pile, owner, Random)` — byte-for-byte the base-game recipe (`FightThrough` / `BoostAway` /
`Overclock`, verified in the decompile) and the same generate-into-combat path add_card uses, so the cards are combat-transient. Field
is `card` (the plan's spelling) → `EffectSpec.StatusCard`; `pile` reuses the add_card piles. Priced NEGATIVE (burn −2.5 / wound −2.0 /
dazed −1.5 per card, ×1.25 into hand) so an over-statted carrier balances; never on a BASIC, at most one per card (generation side),
≤2 such cards per class (`character_validator.status_card_warnings` + pipeline). Closes VOCAB_EXPANSION_PLAN F4 (marked LANDED there).
**Field-legality rework:** `pile` is now legal on add_card / add_status_card (hand/discard/draw) and retrieve_card (discard/exhaust —
schema: the `exhaust` value implies retrieve_card); `cards` on upgrade_card / discard / retrieve_card; `card` on add_status_card only
(both validators + five new schema allOf clauses). Both new ops are card-only by omission from `TriggerOps` / the `triggerEffect` op enum.
Lockstep: `CardSpec.cs` (`StatusCard`), `ForgedCards.cs` (VocabVersion 46, SupportedOps, `RetrievePiles` / `PickModes` / `StatusCards` /
caps, parse, Validate, ValidateTrigger, Describe + `RetrieveSentence` / `StatusCardSentence` / `StatusCardName`, `PilePhrase` exhaust),
`EffectRunner.cs` (three cases + `DiscardChoose` / `RetrieveCards` / `AddStatusCards`), `DataCard.cs` (no-var cases),
`card.schema.json`, `VOCABULARY.md` (discard row reworded, two rows; the duplicated `gain_max_hp` row Phase AN left behind is
removed; payload-discard note), `DESIGN_HEURISTICS.md` (the madness_discard note), `bts1.py` VOCAB_VERSION 46, `cardgen.py` (emit
`Cards:` / `Pile:` / `StatusCard:` named args; describe; `_pile_phrase` exhaust), `validator.py` (constants, shape rules, trigger rule,
per-card rules, pricing, build-around), `character_validator.py` + `character_pipeline.py` (`status_card_warnings`), `featured.py`
(+ `grave_recall`, `tainted_power`), `class_forge.py` (two fantasy pointers, a one-clause pointer in the DISCARD section, the section
token set), `archetypes.json` (madness_discard + exhaust_pyre += retrieve_card; strike_tempo + big_energy += add_status_card),
`exemplar_pool.json` (+3: Cull the Hand, Ash Recall, Reckless Haymaker; pool 107 → 110), `web/static/app.js` (three phrases),
`VOCAB_EXPANSION_PLAN.md` (F4 LANDED). **Rule 0.9 budget:** blueprint prompt **+1,691 chars (88,856 → 90,547, seed 1)** — pointers
only; the three vocabulary rows were tightened by 432 chars after a first measure of +2,123. Tests: `tests/test_phase_ap.py` (133
checks: every legal shape / every reject incl. payload forms / describe in 15 shapes / emit / pricing order and sign / stray fields /
the set warning / census + both detectors / contract presence + the dup-row removal); `test_featured` samples extended; suite **392
passed**; every `test_phase_*.py` (26) runs standalone; C# build 0 errors. AutoSlay (tester `generation/scratch/gaptest-ap/build_tester.py`
— 12 shapes on a 16-card all-aggression deck, staged into slot 04, unstaged afterwards): **GAPTESTAP1** **348 `[AP]` tags** —
add_status_card ×182 (Wound ×2 → Hand 82, Dazed ×2 → Draw 41, Burn → Hand 32, Wound → Discard 27), retrieve_card ×97 (random ×2
from Discard 53, random from Exhaust 32, choose from Exhaust 9, random ×1 from Discard 3 — the min(n, pool) clamp), discard choose ×65
(picks logged by title — incl. a Dazed the bot pitched), **5 `[R] on_discard fired`** from chosen discards (the Reflex chain through the
new path), 4 empty-exhaust no-ops + 2 empty-hand no-ops, **69 `Auto-selected` selector lines** (rule 0.5: every pick UI driven by
AutoSlay, no hang) · 0 mod-attributable exception frames (the 7 Exception lines are BaseLib's startup pair + echoes) · verdict "HANG —
wall-clock timeout" with the AutoSlay log at Turn 28 mid-turn at the cut. The one un-fired shape, `retrieve_card choose` from the
DISCARD pile (`grave_hand`), got **0 plays** because the bot's Neow pick ("Precarious Shears") removed that card from the deck at run
start — the code path is the same `FromCombatPile` call the exhaust form fired 9 times, so not re-run. Tag evidence:
`generation/scratch/gaptest-ap/godot_AP_tags_GAPTESTAP1.txt`.

**STATUS (2026-09-10): Phase AQ EXECUTED (vocab v47)** — all three items landed in lockstep; the verify-first item PASSED, so
nothing was stopped. **(1) `damage_over_time` hook** — a `status_pool` DEBUFF: at the start of the afflicted enemy's turn it loses HP
equal to its stacks, unblockable + unpowered (PoisonPower's exact recipe — `ForgedStatusPower.AfterSideTurnStart` +
`CreatureCmd.Damage(new ThrowingPlayerChoiceContext(), Owner, stacks, Unblockable | Unpowered)`), then the EXISTING end-of-turn
decay burns it down (`lose_one_eot` = Poison's N + N−1 + …; `lose_all_eot` = a one-shot delayed hit). The spec MUST decay (both
validators reject `none` — a permanent burn is strictly better than Poison). **Deviation, deliberate:** the plan wrote
"BeforeTurnStart"; the first build used `BeforeSideTurnStart` (it hands over a choice context) and GAPTESTAQ1 hung at "Combat turn 2"
— that hook runs BEFORE the game's per-creature turn start (`Creature.AfterTurnStart → ClearBlock → Hook.ShouldClearBlock`), so a
LETHAL tick pulled Nibbit out from under the next `IterateCombatHookListeners` (NRE, turn-end task faulted, watchdog). Poison ticks
in `AfterSideTurnStart`; mirroring it byte-for-byte fixed it (GAPTESTAQ2 full run). **(2) `mode: multiplicative`** on `damage_dealt`
/ `damage_taken` ONLY (both validators + C# reject it elsewhere): `ModifyDamageMultiplicative` returns a FACTOR the game multiplies
into the running damage (Vulnerable/Weak convention, verified in `Hook.ModifyDamageInternal` — product of returns) = ×(1 + 0.1·stacks)
capped ×2 (`ForgedStatusPower.MultiplicativeFactor`; stacks past 10 add nothing), gated on `IsPoweredAttack()` like Vulnerable /
Weak / Strength so DoT ticks, Poison and thorns are never scaled; the additive hook returns 0 for a multiplicative spec (no
double-dip). **(3) `hit_count` hook — verify-first PASSED:** `AttackCommand.Attacker { get; private set; }` is PUBLIC in both the
decompile and the runtime reflect dump (`prop Creature Attacker`) — the J-1 "no clean dealer accessor" note was stale (the
PetDamageAttributionPatch point wasn't needed). `ModifyAttackHitCount(AttackCommand attack, int hitCount)` returns
`hitCount + stacks` when `attack.Attacker == Owner && attack.ModelSource is CardModel` (your CARD attacks; never enemy / pet /
relic attacks); the game runs its hit loop `attackCount` times, so a Strike becomes 2 hits, a 2-hit card 3. A BUFF that MUST decay
(a permanent extra hit is degenerate). Status-pool side/decay/mode rules are mirrored in `ForgedCharacters.TryParseStatus` and
`class_forge._validate_status_pool` (`_MULTIPLICATIVE_HOOKS`, `_MUST_DECAY_HOOKS`). No card-level change (cards still
`apply_status_custom` by name), so the card schema / cardgen / validator.py are untouched. Lockstep: `StatusSpec.cs` (docs),
`ForgedCharacters.cs` (StatusHooks / StatusModes / MultiplicativeHooks / MustDecayHooks + rules), `ForgedStatusPower.cs` (three
hooks, `[AQ]` logs, Describe incl. the buff/debuff-aware decay sentence), `ForgedCards.cs` VocabVersion 47, `bts1.py` 47,
`class_forge.py` (validator + the status-pool prompt paragraph + the fantasy table: "burn / bleed / venom on the enemy" now routes
to a `damage_over_time` status FIRST, Poison dropped from the burn line; "flurry / frenzy" → `hit_count`), `VOCABULARY.md` (two
hook rows, the decay bullet now says whose turn, a `mode` bullet), `DESIGN_HEURISTICS.md` (status_signature pricing for all three),
`web/static/app.js` (labels + the multiplicative suffix), `harness_v2.EXEMPLAR_CONTEXT` (+ Scorch, Flurry), `exemplar_pool.json`
(+2: Scorching Brand, Flurry Stance; pool 110 → 112), `archetypes.json` (status_signature metaphors "the lingering burn" / "the
extra cut" — the first picks collided with strike_tempo / countdown_ripen under `test_no_shared_strings`), `PHASE_J…PLAN.md` (cuts
lifted), `VOCAB_EXPANSION_2_PLAN.md` §6 LANDED, `VOCABULARY_GAPS.md` #11 (the DoT half). **Rule 0.9 budget:** blueprint prompt
**+1,402 chars (90,547 → 91,949, seed 1)** — under AP's +1,691. Tests: `tests/test_phase_aq.py` (63 checks: every legal / illegal
pool shape with the C# wording family, the C# mirror greps incl. the AfterSideTurnStart assertion, card-level describe, both
exemplars under `exemplar_validator`, contract / heuristics / web / archetype / prompt tokens); suite **394 passed**; C# build 0 errors.
AutoSlay (tester `generation/scratch/gaptest-aq/build_tester.py` — pool Scorch 🔥 DoT lose_one_eot / Flurry hit_count lose_all_eot /
Kindle damage_dealt ×mult none / Ashen damage_taken ×mult lose_one_eot, 13 cards, 15-card aggression deck, staged into slot 04,
unstaged afterwards): **GAPTESTAQ1** (first build) 57 `[AQ]` tags then the lethal-tick NRE above (mod-attributable — fixed).
**GAPTESTAQ2** (fixed build) **PASS: RunCompleted — a FULL run, 48 rooms, 2,033 `[AQ]` tags**: damage_over_time ×87 (ticks of 3–15
on 15 distinct enemy kinds, lethal ticks included, no NRE), hit_count ×25 (24× `1 -> 2`, 1× `2 -> 3` on Twin Cut), damage_dealt
multiplicative ×1,517 (Kindle ×1.3 … ×2.0 — 210 fires AT the cap, so the cap holds), damage_taken multiplicative ×404 (Ashen ×1.1 …
×2.0, 79 at the cap, and the factor stepping down 1 per enemy turn = the debuff decay) · 0 mod-attributable exception frames (the
ERROR lines are BaseLib's startup pair + AutoSlay's post-run "Options NButton not found" abandon step after RunCompleted). The
multiplicative tag fires ~3× per attack because the game runs `Hook.ModifyDamage` for card-text previews too — idempotent, expected.
Tag evidence: `generation/scratch/gaptest-aq/godot_AQ_tags_GAPTESTAQ{1,2}.txt`.

**STATUS (2026-09-10): Phase AS EXECUTED (vocab v48 — AR is not yet built, so AS took the next number per rule 0.8)** — every item
landed in lockstep; the verify-first item PASSED and the combat_start spike was RESOLVED without a new spelling. **(1) `card_type`
on `on_card_played`** — verify-first PASSED: `CardModel.Type` is a public accessor (the `PHASE_L…:366` "no clean accessor" note
was stale — `ForgedCostShiftPower` has keyed on it since v45, base and forged cards alike). `ForgedRelic.AfterCardPlayed` maps
`cardPlay.Card.Type` → `"attack"/"skill"/"power"` into `RelicRunner.Fire(cardType:)`; a hook with `card_type` fires only on a
match (any other trigger rejects it, both importers + the schema). **(2) `every_n`** (2..9, not on `combat_end`) — a per-combat
counter on the relic instance (`ForgedRelic._counters`, hook-index keyed, reset in `BeforeCombatStart`): an occurrence that passes
the trigger + card-type filter advances it, the hook fires on the Nth/2Nth… — counted BEFORE `when` (the count is "things that
happened"; the condition is "is now a good time"). The relic icon shows the running count (`ShowCounter` / `DisplayAmount` = count
mod N, `InvokeDisplayAmountChanged` after every fire — the BookOfFiveRings convention). **(3) `attack_base`** (1..3 generator-side,
1..5 import-side) — rides `ModifyDamageAdditive` next to `first_attack` (a bonus delta, never consumed); priced 7.0/pt in
`_MODIFIER_VALUE` (Vajra: 1 fits, 2 is the edge, 3 rejects). **(4) The reprice** — `max_energy` (18) and `cost_reduction` (24) stay
above the 13×1.15 budget ALONE, but `_relic_balance_errors` now splits value into boons and DRAWBACKS: `lose_hp` (−0.75/HP),
the new relic op `discard` (−1.5/card, 1..2, random only), a debuff on a SELF-target hook (weak/frail/vulnerable land on the
owner — now legal in both importers; poison never), and the new SIGNED `max_hp` modifier (0.4/pt, −30..30; applied ONCE in
`ForgedRelic.AfterObtained` via `CreatureCmd.GainMaxHp` / `LoseMaxHp(new ThrowingPlayerChoiceContext(), …)` — the
DistinguishedCape recipe; `RunManager.FinalizeStartingRelics` calls `AfterObtained` on starter relics, verified in the decompile
and live). Drawback credit is capped at 10, so `max_energy 1` needs `max_hp −8` (or `discard 1` / `lose_hp 2` / self `weak 1`
per turn) and `cost_reduction 1` needs the full price (`max_hp −15` + a per-turn cost); `max_energy 1 + cost_reduction 1` can
never fit. The reject message names the fix. A `card_type` filter narrows `on_card_played`'s 9 payouts (attack ×0.5, skill ×0.4,
power ×0.1) and `every_n` divides the rate. **(5) combat_start spike — RESOLVED, not shipped:** `RelicModel.Owner` IS the Player
inside `BeforeCombatStart()` (base-game Anchor uses `base.Owner.Creature` there) and the ctx-needing effects could use a
`ThrowingPlayerChoiceContext` as the base game does in `AfterObtained` — so it is buildable, but `turn_start + once_per_combat`
already has identical observable semantics and is documented as the ONLY spelling; a second spelling would only cost prompt budget.
Left as is. **(6)** `DESIGN_HEURISTICS.md` relic forms gained **Counter relic** and **Boon with a price** (and the passive-modifier
form lost the energy stats, which now exist only as a Boon with a price); `RELIC_VOCABULARY.md` gained the `card_type` / `every_n`
sections, the `discard` row, the self-debuff sentence, the `attack_base` / `max_hp` rows and the drawback rule. Lockstep:
`RelicSpec.cs` (CardType / EveryN), `ForgedCharacters.cs` (RelicEffectOps + discard, RelicCardTypes, Min/MaxEveryN,
RelicModifierStats + attack_base / max_hp, bounds, self-debuff + discard rules), `RelicRunner.cs` (filter + counter, `[AS]` logs),
`ForgedRelic.cs` (counters, AfterObtained max_hp, AfterCardPlayed type, ShowCounter/DisplayAmount, attack_base), `EffectRunner.cs`
(relic `discard` → `DiscardRandom`; `ApplyRelicStatus(hookTarget)` self-debuff), `ForgedCards.cs` VocabVersion 48, `bts1.py` 48,
`relic.schema.json`, `class_forge.py` (`_validate_relic` + `_RELIC_MODIFIER_RANGE` + `_relic_effect_value` / `_relic_hook_freq` +
the capped drawback credit + one relic-prompt sentence + `_fake_relic`), `smoke_relic.py` (+ every v48 shape), `relic_validator.py`,
`web/static/app.js` (labels, signed modifiers, "On Attack played (every 3rd)", the missing `on_hp_lost` label), PHASE_L plan
(deferrals marked LANDED); `tests/test_phase_as.py` (130 checks), `test_phase_ajb` probe repointed (max_hp is legal now); suite 396.
Prompt budget: the BLUEPRINT prompt is unchanged (91,949 — the relic vocab is not embedded there); the RELIC prompt grew ~3.3k
(vocab +2,016, forms +952, one sentence) to 17,480 chars. **AutoSlay GAPTESTAS1** (`generation/scratch/gaptest-as/` — a
"Counter Dripper" kitchen-sink relic: `max_energy +1 / max_hp −6 / attack_base +1`, every 3rd Attack → Block 3, turn_start →
discard 1, every other turn → self Weak 1, on a Power → draw 1; the keystone gate prices it over budget on purpose, printed not
enforced): 43 rooms, **6,799 `[AS]` tags** — `max_hp` ×1 (`Max HP 80 -> 74` at run start), typed counter ×113 fires / ×246 waits
(3-6-9…, reset to 1 each combat, Skills never advance it), turn-start every_n 2 ×69 fires / ×80 waits, Power-only filter ×60,
discard ×149, self-Weak ×69, attack_base ×6,012 (previews included) · 0 mod-attributable exception frames (the 3 ERROR lines are
BaseLib's startup pair + the dependency-version notice). Verdict "HANG — wall-clock timeout" = the Phase-AO harness limit (the
log was still mid-combat at 600 s, two 5 s watchdog blips over the run), not a mod hang. Tag evidence:
`generation/scratch/gaptest-as/godot_AS_tags_GAPTESTAS1.txt`.

**STATUS (2026-09-10): Phase AR EXECUTED (vocab v49 — built after AS, so it took the next number per rule 0.8)** — every item
landed in lockstep, plus one finding the plan did not anticipate. **(1) `when` inside custom-orb effects** — an orb-effect's gate
rides on its inner `EffectSpec.When` (the same JSON shape as a card effect's `when`; `OrbEffect.When` exposes it), parsed in
`ForgedCharacters.TryParseOrbEffects` through the shared `Conditions.Validate` plus the orb rule
(`OrbForbiddenConditionKinds` = `target_has_status` / `retained_last_turn` / `..Conditions.TargetKinds` — an orb fires with no
card and no chosen target, the trigger rule; everything else is legal, `orbs_match` / `orb_count_ge` included). `OrbRunner.RunEffect`
evaluates it at fire time with the player-state overload and logs `[AR] … gate <kind> OPEN|closed`; the HUD tooltip prints
"… if/unless …" via `Conditions.Phrase`. **(2) Plasma / Glass as RECIPES, not base orbs** — both in `VOCABULARY.md` Orbs as
backticked JSON (the phase test parses + validates them). **(3) The verify-first item FAILED in a useful way:** `gain_energy` IS
legal in an orb passive, but a forged passive ticked only on `BeforeTurnEndOrbTrigger` (the Lightning/Frost/Glass hook), so energy
gained there evaporated and a `draw` passive fed the end-of-turn discard — both ops were DEAD in a passive. The game's own
`PlasmaOrb` ticks on `AfterTurnStartOrbTrigger` (decompile; `OrbQueue` calls both hooks for every queued orb). Fix: a custom orb
gains **`passive_timing`** (`turn_end` default / `turn_start`), `ForgedOrb` overrides `AfterTurnStartOrbTrigger` and each orb ticks
on exactly one hook, and a passive carrying `gain_energy` / `draw` MUST declare `turn_start` (`OrbTurnStartOnlyOps`, both
importers). **(4) Lockstep:** `OrbSpec.cs` (When / PassiveTiming / PassiveAtTurnStart), `ForgedCharacters.cs`
(OrbPassiveTimings / OrbTurnStartOnlyOps / OrbForbiddenConditionKinds + both parsers), `OrbRunner.cs` (gate, `[AR]` tags,
"Passive (turn start):", the if/unless fragment), `ForgedOrb.cs`, `ForgedCards.cs` VocabVersion 49, `bts1.py` 49, `class_forge.py`
(`_ORB_CONDITION_KINDS` / `_ORB_FORBIDDEN_CONDITION_KINDS` / value caps / `_validate_orb_when` / `_ORB_PASSIVE_TIMINGS` /
`_ORB_TURN_START_ONLY_OPS`, the ORB POOL prompt sentence + recipes, the fake orb blueprint gains a Plasma orb with a gated
evoke), `VOCABULARY.md` (Orbs: `when` + `passive_timing` bullets + both recipes; Conditions cross-reference),
`DESIGN_HEURISTICS.md` (orb_channel note: gated orbs pay off orb count; a Plasma passive is a full energy — cap 1, never with
`max_energy`), `web/static/app.js` (turn_start passive label; `condCore` gained the nine post-Phase-M kinds that were falling
through to titleCase), PHASE_I plan deferrals (`:95`, `:118`) marked LANDED; `tests/test_phase_ar.py` (122 checks, incl. a
three-way kind lockstep: card.schema.json enum == C# `Conditions.Kinds` == Python orb kinds + forbidden); suite 397, all 35
standalone modules green. Prompt budget: blueprint 91,949 → 93,674 (+1,725: the two recipe lines + the ORB POOL sentence;
within rule 0.9's ±5%). **AutoSlay GAPTESTAR1** (`generation/scratch/gaptest-ar/` — a "Glass Cannon" orb class: Plasma
(turn_start energy; evoke energy + draw if 2+ orbs), Glass (evoke-only: 9 to all if 2+ orbs, Vulnerable if 2+ enemies), Cinder
(passive 2 dmg if turn 2+ / Block 2 if no Block; evoke 6 unless Block / Weak if 1+ energy); three channel skills + a 2-random pull +
evoke + Focus): **316 `[AR]` tags** — Plasma turn-start tick ×20, Plasma evoke draw gate ×25 open / ×1 closed, Glass shatter gate
×30 open / ×3 closed, Glass crowd-Vulnerable ×4 open / ×29 closed, Cinder turn gate ×39 open / ×10 closed, Cinder energy gate
×53 open, Cinder `no_block` ×49 closed and negated `has_block` ×53 closed (the AutoSlay bot carries ~1,000 Block, so the Block reads
never flip — harness, not mod; both kinds are card-proven since Phase H/L-4) · 0 mod-attributable exception frames. Verdict
"FAIL — Watchdog timeout … Navigating map" = the documented random-bot map stall, not a mod hang. Tag evidence:
`generation/scratch/gaptest-ar/godot_AR_tags_GAPTESTAR1.txt`.

**STATUS (2026-09-10): Phase AT EXECUTED (vocab v50)** — the item landed in lockstep, by a different mechanism than the plan
named. **(1) Pet damage fires `on_damage_dealt`** — both the card trigger (`ForgedTriggerPower.AfterDamageGiven`) and the relic
twin (`ForgedRelic.AfterDamageGiven`) now accept a dealer whose `PetOwner` is the hook's owner. **The plan said "use
`PetDamageAttributionPatch`"; that is NOT what shipped** — the decompile shows the base game's own idiom for exactly this
(`ReaperFormPower`: `dealer == Owner || dealer.PetOwner?.Creature == Owner`; `HandDrill`: `dealer?.PetOwner == Owner`), and
`Hook.AfterDamageGiven` is dispatched to EVERY listener regardless of dealer, so no Harmony patch is needed; the patch stays
scoped to `PersonalHivePower` (its doc comment says why). The card path is unchanged (`dealer == Owner && cardSource != null`);
the pet path needs no cardSource (a pet only ever hits via summon_attack — card- or payload-driven — never thorns/orb/payload
damage of its own), and a payload `summon_attack` re-raising the hook is stopped by the existing `_firing` / `FireGuarded`
re-entrancy sets. The relic's `first_attack` (Akabeko) one-shot is consumed on the CARD path only; `ModifyDamageAdditive`
(`first_attack` / `attack_base`) stays card-gated — a pet hit is not a card attack. **(2) No new token, no describe change:**
"Whenever you deal damage" was already the sentence, so the byte-match contract is untouched; the contract wording drops
"card" (`VOCABULARY.md` Triggers, `card.schema.json` trigger description, `RELIC_VOCABULARY.md` row), `DESIGN_HEURISTICS.md`'s
summon_swarm archetype-note names the pack-tactics engine (`on_damage_dealt` + summon_attack, once_per_turn), and the exemplar
pool gains `ex_blood_scent` (summon_swarm, needs summon: on_damage_dealt → buff_summon 1, once per turn; pool 112 → 113).
Lockstep: `ForgedTriggerPower.cs` / `ForgedRelic.cs` (`[AT]` tags), `ForgedCards.cs` VocabVersion 50, `ForgedCharacters.cs`
hook doc, `PetDamageAttributionPatch.cs` note, `bts1.py` 50, the three contract files, `DESIGN_HEURISTICS.md`,
`exemplar_pool.json`, PHASE_L plan (`:387` deferral marked WIDENED); `tests/test_phase_at.py` (39 checks: both stamps, the C#
mirror incl. the card-only first_attack consume and the un-widened patch, describe unchanged, summon-context validation, the
contract wording, the exemplar under `exemplar_validator`); `test_phase_ar.test_version` relaxed from `== 49` to `>= 49`;
suite **398 passed**; C# build 0 errors. Prompt budget: blueprint 93,674 → 93,750 (+76: the one Triggers clause; the heuristics
note is archetype-scoped). **AutoSlay GAPTESTAT1** (`generation/scratch/gaptest-at/` — a summon class whose only player
attack is Strike: Sic 'Em (summon_attack 5 ×2), Thrall's Hour (turn_end summon_attack 3 ×2), Blood Scent (on_damage_dealt →
draw 1, once/turn), Pack Hunger (on_damage_dealt → buff_summon 1, once/turn), Hound Ward (ungated on_damage_dealt → Block 1),
plus a starter relic "Hunter's Bell" (on_damage_dealt → Block 1)): 39 rooms into Act 3, **1,408 `[AT]` tags** — card-trigger
attribution ×1,017 (pet hits of 3–10+ on 32 distinct enemy kinds), relic attribution ×391, `[H4]` on_damage_dealt payload
fires ×615 (fewer than the tags because two of the three powers are once_per_turn — the gate holds), feeders: card
summon_attack ×2 ×101, payload summon_attack ×104, buff_summon ×91 · **0 mod-attributable exception frames** (the 3 ERROR lines
are BaseLib's startup pair + the dependency-version notice). Verdict "HANG — wall-clock timeout" = the Phase-AO harness limit
(the AutoSlay log was mid-combat on Act 3 Floor 6 at 600 s), not a mod hang. Tag evidence:
`generation/scratch/gaptest-at/godot_AT_tags_GAPTESTAT1.txt`.

**STATUS (2026-09-10): Phase AU EXECUTED (vocab v51)** — W0.2 Issue B closed at the ENGINE, not in the prose. **(1) The
mechanism is the game's own hook, not a Harmony patch:** `DataCard` (a `ConstructedCardModel`, i.e. a `CardModel`) now
overrides `AbstractModel.AfterCardDiscarded(PlayerChoiceContext, CardModel)` — `if (card != this) return;` then the existing
`FireOnDiscard`. Decompile facts that make this exact: `CardCmd.DiscardAndDraw` (`CardCmd.cs:172`, what `CardCmd.Discard`
wraps) does, per card, `CardPileCmd.Add(card, discardPile)` → `History.CardDiscarded` → `await
Hook.AfterCardDiscarded(...)`; `Hook.cs:330` dispatches to every `IterateCombatHookListeners` model, and
`CombatState.IterateHookListeners` yields creature Powers, player Relics, OrbQueue orbs AND every card in
`player.PlayerCombatState.AllPiles` — so the just-discarded card (already in the discard pile when the hook fires) gets
its own callback. Base-game idiom confirmed by `Relics/Tingsha.cs` + `Relics/ToughBandages.cs` (we deliberately do NOT
copy their `CurrentSide` gate: we stay side-agnostic, so an enemy-side forced discard would fire too — no base-game
source does that today). **(2) End-of-turn cleanup still never fires it:** `CombatManager.cs:1343` flushes the hand with
`CardPileCmd.Add(cardsToFlush, PileType.Discard)` + `Hook.AfterFlush`, never through `CardCmd.Discard`, so the contract
rule holds structurally rather than by convention. **(3) The base-game sources that now fuel Reflex cards:** cards
Acrobatics, CalculatedGamble, DaggerThrow, HiddenDaggers, Prepared, Scrape, ShadowStep, StormOfSteel, Survivor; potion
Gambler's Brew; power ToolsOfTheTrade; relic Gambling Chip. (No monster calls `CardCmd.Discard` in this build — the docs
say "relics, potions, other-class cards", never "enemy".) STS2's native `Sly` keyword (`CardModel.IsSlyThisTurn`,
auto-played from `DiscardAndDraw`) is a separate thing and out of scope. **(4) Our own ops stopped firing it by hand:**
`EffectRunner.FireOnDiscardFor` is DELETED and `DiscardRandom` / `DiscardChoose` / `Scry` no longer call it (their
`CardCmd.Discard` already reaches the hook — keeping both would double-fire). The no-cascade guard moved with the fire
point: `DataCard._firingOnDiscard` now wraps the `TriggerRunner.Run` payload, so a `discard` INSIDE an on_discard payload
still discards but fires no further payoffs, while siblings in one batch each fire (the game calls the hook per card,
after the previous payload finished) — Phase-R semantics, unchanged. `EffectRunner.ModDiscardDepth` (int, try/finally
around each `CardCmd.Discard`) exists ONLY for tag attribution. **(5) No new token, no describe change:** "Whenever this
card is discarded" was already the byte-match sentence on both sides (`cardgen.py:436` / `ForgedCards.Describe`).
New log line `[AU] on_discard via Hook.AfterCardDiscarded ('<title>', source=mod-op|base-game)`, emitted before the
retained `[R] on_discard fired` line. Lockstep: `DataCard.cs` (hook override + guard + `[AU]` tag), `EffectRunner.cs`
(FireOnDiscardFor deleted, three call sites, `ModDiscardDepth`, four doc comments), `ForgedCards.cs` VocabVersion 51 +
the on_discard comments, `bts1.py` 51, `mod/contract/VOCABULARY.md` (caveat removed), `mod/contract/card.schema.json`
(trigger description), `tests/test_wave0_docs.py` (caveat assertion FLIPPED to "must be gone"), this plan (W0.2-B marked
resolved). `class_forge.py`'s DISCARD/HAND-CHURN block and `archetypes.json` needed no change (neither said "only this
class"); `web/static/app.js` renders relic hook labels only, so it has no on_discard text. `tests/test_phase_au.py`
(55 checks: both stamps, the C# mirror — the override, `card != this`, the guard in DataCard wrapping the payload,
`FireOnDiscardFor` gone from EffectRunner, `ModDiscardDepth` bracketing all three ops, the `[AU]` tag and the retained
`[R]` line — describe byte-match, validator accept/reject, and the contract wording). Suite **399 passed (the 398 AT baseline + this module's pytest-collected `test_version`); every standalone `tests/test_phase_*.py` module green, and no older phase test asserted the deleted `FireOnDiscardFor` mechanism (`test_phase_as` only pins the unchanged `DiscardRandom(amt, player, ctx)` relic call). `test_phase_at`'s stamp asserts were already `>= 50`, so nothing needed relaxing**; C# build 0
errors. Prompt budget: VOCABULARY.md 50,323 -> 50,196 chars (-127), blueprint prompt 93,750 -> 93,623 chars (-127) (rule 0.9 satisfied — AU removes text).
**AutoSlay GAPTESTAU1** (`generation/scratch/gaptest-au/` — a discard class: four on_discard FUEL cards (Ember Reflex
Block 5 ungated · Cinder Lash targeted damage 6 · Second Wind draw 1 `once_per_turn` · Last Gasp Block 7 gated
`when turn_at_least 2`), three enablers (Cull the Hand `discard cards:"choose"` · Purge the Weak `discard 2` random ·
Sift `scry 3`), a `turn_start → discard 1` churn power (Ash Wind) and a starter relic that also discards each turn):
17 rooms through the Act 1 boss, **247 `[AU]` tags** — Second Wind ×93, Last Gasp ×72, Ember Reflex ×45, Cinder Lash
×37 — all `source=mod-op` and **247 `[R] on_discard fired`**, i.e. exactly 1:1 with the `[AU]` tags, which is the
double-fire regression proof (pre-AU the mod op fired the payload AND, post-AU, the hook would have fired it again).
Feeders: `[R] discard xN` ×336, `[AP] discard choose` ×49, `[AA] scry` ×77, `[H4]` turn_start churn ×37,
`Auto-selected` ×117 (rule 0.5 — the pick UIs never blocked the bot). `source=base-game` is 0 by construction: the
character format carries only a FORGED relic dict (`ForgedCharacters` parses no base-game relic id), so the run
exercises the hook through the mod ops — the identical single code path, since after AU nothing but
`Hook.AfterCardDiscarded` can fire an on_discard payload. **0 mod-attributable exception frames** (the 3 ERROR lines
are BaseLib's two startup HarmonyExceptions + the dependency-version notice; no `BlankTheSpire.` frame appears within
20 lines of any Exception). Verdict "FAIL — HANG, wall-clock timeout" is the Phase-AO harness limit: the AutoSlay log's
last line is the bot still playing cards on turn 14 of the Act 1 boss fight at 600 s. Tag evidence:
`generation/scratch/gaptest-au/godot_AU_tags_GAPTESTAU1.txt` (956 lines). Slot 04 unstaged afterwards.

**STATUS (2026-09-10): Phase AV EXECUTED (vocab v52)** — the K-3 autonomous minion engine, dormant since the
v15 true-Osty refit, is LIVE again and the generator emits it under gates. **(1) Two C# fixes made the dormant engine
reachable.** `EffectRunner.SummonForged` now RUNS `spec.OnSummon` (parsed since K-3, never fired) — after
`LayoutPets`, so the pet acts from a real board position, and ONLY on the fresh-summon path (the grow path returns
first, so re-summoning to pump Max HP never re-triggers the battle cry). `FindLivingSummon(player, summonClass,
string? name = null)` is name-keyed: the `summon` op passes the minion's name, so a second, differently-named pool
entry now JOINS the board instead of silently growing the first (`MaxSummons = 2` is finally reachable, matching
`slotgen.SUMMONS_PER_CLASS`). **Decision: `name == null` stays the default and every other caller keeps it** — for
`summon_attack` / `buff_summon` / `heal_summon` / `shield_summon` / `sacrifice_summon` and their trigger-payload
twins, "your summon" means the FRONT-most living minion of the class, exactly as `ForgedSummonShieldPower` picks
the front-most attackable one to meat-shield; that rule is written into the `FindLivingSummon` doc comment,
`VOCABULARY.md` and the blueprint prompt. **(2) New spec field `on_nth_attack`** `{"n": 2-5, "actions": [...]}`:
every Nth instance of damage the minion DEALS (per HIT — its own `attack` move actions and any `summon_attack`
routed through it) runs the payload, then the counter resets. **Hook chosen: `ForgedSummonPower.AfterDamageGiven`**
(`dealer == Owner && result.TotalDamage > 0`) — the same idiom `ForgedTriggerPower` uses, and it reaches the pet
because `CombatState.IterateHookListeners` walks every ally creature's Powers (verified in the decompile); the
payoff's own attacks are excluded by a `_firingNth` try/finally guard, so an `n:2` payoff that attacks twice cannot
re-arm itself. `SummonRunner.Describe` appends " Every {n}th hit: {actions}." after the On summon / On death
clauses. **(3) New CARD op `sacrifice_summon`** (flag-op, no amount/target): kills the front-most living minion
through the base game's own death path, **`CreatureCmd.Kill(pet, force: true)`** — the decompile
(`CreatureCmd.KillWithoutCheckingWinCondition`) shows it runs `Hook.BeforeDeath` -> `InvokeDiedEvent` ->
`Hook.AfterDeath` BEFORE `RemoveAllPowersAfterDeath`, so `ForgedSummonPower.AfterDeath` still sees its spec and
fires the `on_death` rattle; `force: true` so a death-prevention effect cannot refuse the sacrifice. Guards
(C# `ForgedCards.Validate` + `validator.py`, mirrored): class-only, card-only (not in `TriggerOps`, and the schema's
`triggerEffect` op enum excludes it), never on a BASIC, at most one per effect list (base/upgrade counted
independently), and **never a card's ONLY effect** — the sacrifice is the price, the rest of the card is the
payoff. No summon out = a logged no-op and the rest of the card still resolves. Describe (byte-match both sides):
**"Sacrifice your summon."** The scorer prices it at **-4.0** (a cost, like `lose_hp`) so the payoff half can be
generous without tripping the power ceiling. **(4) Generation gating (the part the engine does NOT enforce):**
`_MAX_SUMMONS` 1 -> 2; `_REMOVED_SUMMON_FIELDS` and its rejection are DELETED; `_validate_summon_pool` re-validates
`moves`/`actions` (via the re-armed `_validate_summon_actions`), `attackable`, `on_summon`, `on_death`
(enemy-facing) and `on_nth_attack`, and adds two rules: **at most ONE pool entry may be AUTONOMOUS** (declare
`moves`/`actions`) and **`attackable: false` (ETHEREAL) only on that autonomous one** (a passive ethereal minion
neither attacks nor shields — it would be a blank). **Caps (numbers chosen here):** per-ACTION `attack` ≤ 8,
`block` ≤ 6, `heal_self` ≤ 4, `apply_status` ≤ 2, `hits` ≤ 2; a new per-LIST total (one move, or one
on_summon / on_death / on_nth_attack payload) of the same numbers, with `attack` counted as amount × hits; an
autonomous minion's `max_hp` ≤ 20 (a passive bodyguard keeps the 100 cap). **These are GENERATION-SIDE ONLY** —
the C# parser only bounds-checks loosely (`amount >= 1`, `hits >= 1`, `max_hp` 1..999) so hand-authored / legacy
characters still import; the only number mirrored in C# is the `on_nth_attack` band (`SummonNthMin/Max` = 2/5).
That is the `attack_base` split Phase AS established. **(5) Lockstep:** `SummonSpec.cs` (`OnNthAttack` + the
`SummonNthAttack` record), `ForgedCharacters.cs` (the `on_nth_attack` parser + band, the v15 dormancy comment
rewritten), `SummonRunner.cs` (Describe), `ForgedSummonPower.cs` (the hit counter + guard + the `[AV] on_death
rattle` tag), `EffectRunner.cs` (`SummonForged` battle cry + name-keyed lookup, `SacrificeSummon`, the op case),
`ForgedCards.cs` (SupportedOps / Validate / Describe / `VocabVersion` 52), `DataCard.cs` (the flag-op declares no
card var), `bts1.py` 52, `card.schema.json` (op enum + description), `VOCABULARY.md` (an Effect-ops row + the
rewritten "Forged summons" section: one-or-two minions, the six-op table, the AUTONOMOUS subsection with a compact
ethereal-striker JSON example, the "disabled for now" paragraph deleted), `class_forge.py` (`_MAX_SUMMONS`,
`_validate_summon_pool` + `_summon_is_autonomous`, the caps, `_card_uses_summons`, the rewritten SUMMON POOL
prompt section, the summon class-kind sentence, the prunable-section registry + its ALSO-AVAILABLE one-liner),
`validator.py` (class-only / flag-op / basic / alone / twice / payload rules + the -4.0 score),
`harness_v2.py` (`_CLASS_ONLY_TOKENS`), `census.py` (a summon-op-mix report line), `featured.py`
(`summon_sacrifice`), `DESIGN_HEURISTICS.md` (pricing: an autonomous minion is a power that costs a card — 4-6
damage/Block a turn, 10-20 HP, ethereal takes the low HP / high damage end; a sacrifice payoff is >= 10 Block /
12 damage / 2 draws + energy and wants an `on_death` rattle), `archetypes.json` (summon_swarm ops + description),
`exemplar_pool.json` (`ex_bone_offering`: sacrifice + draw 2 + energy; pool 113 -> 114, byte-spliced CRLF),
`web/static/app.js` (the `sacrifice_summon` card label + a `summonLines` that renders Ethereal / the move cycle /
On summon / On death / Every Nth hit), PHASE_K3 plan status (SHELVED -> REVIVED; the per-summon `kind` token did
NOT ship — the three archetypes are prompt/heuristics guidance, not a declared field) and PHASE_K's K-3 list
(on_summon/on_death + Sacrifice/consume marked LANDED). **No character/class schema needed a change** —
`mod/contract/` has no character schema; `summon_pool` shape lives in `VOCABULARY.md` + `_validate_summon_pool`.
`coverage.py` needed none either: its repair menus are class-kind-agnostic base mechanics and `SECTION_KEYS`
already carried `summon`. **Tests:** `tests/test_phase_av.py` (**117 checks**: both stamps, the C# mirror — the
battle cry after LayoutPets and off the grow path, the name-keyed lookup with its null default plus every
name-less caller, the `on_nth_attack` parser/counter/guard/describe order, sacrifice in
SupportedOps/AmountOps-absent/TriggerOps-absent/Validate/Execute/Kill and all five `[AV]` tags — the describe
byte-match, ten validator accept/reject cases, twelve `_validate_summon_pool` gate/cap cases, the contract wording,
the exemplar under `exemplar_validator`, the app.js labels and the rule-0.9 budget). Repointed, not deleted:
`test_phase_au`'s absolute prompt-size assert became "AU's caveat removal is still absent" (an absolute pin breaks
on every later phase) and its `== 51` C# pin relaxed to `>= 51`; `test_exemplars.CLASS_ONLY_TOKENS` and
`harness_v2._CLASS_ONLY_TOKENS` gained `sacrifice_summon` (so the new exemplar's `needs: summon` tag is justified);
`test_featured` gained a `summon_sacrifice` sample. Suite **400 passed** (the 399 AU baseline + this module's
pytest-collected `test_version`); all 32 standalone `tests/test_phase_*.py` modules green; C# build **0 errors**.
Prompt budget: blueprint 93,623 -> **95,153** (+1,530, rule 0.9's "~+1,500"); VOCABULARY.md 50,196 -> 51,576
(+1,380) — the new autonomous paragraph was paid for by tightening the repetitive SUMMON POOL prose (that
section grew only 3,836 -> 3,995 source chars (+159) while gaining the opt-in model, the sixth op and the three
archetype one-liners) and by dropping VOCABULARY's duplicate card-example block (the prompt carries the same
examples one section above). **AutoSlay GAPTESTAV2** (`generation/scratch/gaptest-av/` — a summon class whose
pool is a PASSIVE 14 HP "Bone Thrall" (with an `on_death` attack 4) beside an AUTONOMOUS ETHEREAL 6 HP "Carrion
Hawk" (`moves` rotation attack 4 / attack 3×2, `on_summon` Weak 1, `on_death` attack 6 to all enemies,
`on_nth_attack` n=3 -> attack 5), with cards to summon each, two `summon_attack` shapes, `buff_summon`, and the two
sacrifice payoffs (Block 12; draw 2 + 1 energy)): **33 rooms through Act 2 to the Act 2 boss**, **172 `[AV]` tags**
 — `on_death rattle` ×34 (Thrall ×15 + Hawk ×19), `on_summon` ×32, `second summon '<b>' joins '<a>'` ×31,
`on_nth_attack ... (hit #3)` ×30, `sacrifice_summon` ×34 (Thrall ×15 + Hawk ×19; HP 6 up to HP 70, the grow
path working) and `sacrifice_summon: no summon (no-op)` ×11. **The 34:34 sacrifice-to-rattle match is the proof
that `CreatureCmd.Kill` reaches `Hook.AfterDeath` with the pet's powers still attached** (every rattle in the run
came from a sacrifice; the ethereal Hawk can die no other way). Feeders: `[AJ] summon_attack x2` ×47 and
`[AT] relic on_damage_dealt: pet ...` ×207 (Hawk ×153, Thrall ×54) — the Hawk's share is the move cycle +
on_nth_attack acting on its own, since card `summon_attack`s route through the FRONT-most minion (the Thrall).
**0 mod-attributable exception frames** (no `BlankTheSpire.` frame within 20 lines of any Exception; the ERROR
lines are BaseLib's two startup HarmonyExceptions, the dependency-version notice, and two base-game
"selection screen with 0 options" softlock guards from a POWER_POTION with no power cards in the deck). Verdict
"FAIL — Rewards screen did not appear after combat" is the harness: the bot LOST to THE_INSATIABLE on Act 2
Floor 16, so the game showed game-over and `WaitForRewardsScreenAsync` timed out — **no in-combat stall**: the
log runs continuously through 33 rooms with pets on the board, and the earlier GAPTESTAV1 run (72 `[AV]` tags, 18
rooms) stalled in an EVENT room on a BaseLib `DustyTome.SetupForPlayer_Patch1` NRE inside the base game's Darv
event — also not mod-attributable, and not combat. Benign observation: the run-history stat line credits
`MONSTER.BLANKTHESPIRE-FORGED_CLASS04_SUMMON1/2` with the player's death (our pets are `MonsterModel`s, so the
base game's per-monster loss counter includes them) — cosmetic bookkeeping, pre-dating AV. Tag evidence:
`generation/scratch/gaptest-av/godot_AV_tags_GAPTESTAV2.txt` (172 lines) and `..._GAPTESTAV1.txt` (72 lines).
Slot 04 unstaged afterwards (no `04.json.smokebak` left behind).

**STATUS (2026-09-11): Phase AW EXECUTED (vocab stays v52 — NO engine change)** — hybrid class kinds are LIVE in
generation. **(1) The AutoSlay gate ran FIRST and PASSED.** `generation/scratch/gaptest-aw/build_tester.py` hand-builds
an orb+status hybrid ("AW Gap Tester": 3 orb slots, the AR Plasma/Cinder gated orbs beside the AQ Scorch/Kindle/Ashen
statuses, 12 cards incl. 'Ember Surge' — damage + channel + Scorch on ONE card) and stages it to slot 04; seed
`GAPTESTAW1` imported (`class 04 <- 'AW Gap Tester' (HP 78, deck 12 entries)`), embarked and ran **37 rooms into Act 3**
with **377 `[AR]` tags** (all six orb shapes: Plasma turn_start passive ×44, orb_count_ge OPEN ×48 / closed ×5,
turn_at_least OPEN ×50 / closed ×24, no_block closed ×74, has_block-negated closed ×66, energy_ge OPEN ×66) and
**1,246 `[AQ]` tags** (Kindle damage_dealt ×956, Ashen damage_taken ×239, Scorch DoT ×51) in the SAME run — the orb HUD
and the custom status icons coexist and both engines fire, which is exactly what Phase N's O-2a could not prove.
**0 mod-attributable exception frames** (the 27 Exception lines are BaseLib's two startup HarmonyExceptions, a
base-game "There is no item to purchase" under AutoSlay, and the watchdog); verdict "FAIL — Watchdog timeout ...
Navigating map" is the usual map-nav harness stall. Evidence: `generation/scratch/gaptest-aw/godot_AW_tags_GAPTESTAW1.txt`
(1,623 lines). Slot 04 unstaged. PHASE_N's O-2a / O-2b tracker rows now record this. **(2) Generation: the class kind
is a SET, primary first.** `frontend/catalog.candidate_kinds()` keeps every distinct special kind among the fused
archetypes (priority orb > summon > status; `MAX_CLASS_KINDS = 2` — a triad fusing all three keeps the two boldest and
the third archetype's class-only cards fall to the drop nets exactly as before); `Candidate.class_kinds` rides beside
the UNCHANGED `class_kind` (the primary — every pre-AW consumer and test keeps working), with `__post_init__` keeping
the two consistent, plus `is_hybrid` / `kind_label()` ('orb+status'). The dossier brief keeps the primary's guidance and
appends a HYBRID sentence naming the splash budget (an orb splash beside a status/summon primary drops that guidance's
'"orb_slots": 0' clause). `_prune_archetype_sections` / `_BlueprintContract(class_kind=...)` accept the list (BOTH pool
sections stay in the pruned prompt); `harness_v2.kind_set` / `pool_kind` / `pick_exemplars` accept it (a hybrid is
dealt both kinds' `needs`-tagged exemplars and both class-kind coverage/featured menus); `forge_class` reads
`_declared_kinds(bp)` and notes "hybrid class: orb engine + status splash". **(3) The splash budget is the
GENERATION-side gate** (the engine accepts any mix): `_validate_hybrid`, wired into `_validate_blueprint` — at most TWO
pool kinds, and with two, at least one must be SPLASH-sized: splash orb = ≤3 `orb_slots` + ≤1 custom orb; splash
status = ≤2 custom statuses; splash summon = ONE passive minion (never the autonomous model). Primary vs splash is read
off the blueprint's SIZES (`_declared_kinds`: full-sized first, ties orb > summon > status), so ONE rule serves the
concept path (the model chose the kinds) and the dossier path (the candidate declared them); a both-splash-sized tie
only affects labels. **(4) Also:** `builder._HYBRID_WEIGHT = 3.5` (a hybrid out-scores a plain orb class in
`_distinctiveness`), narration "orb+status hybrid class", `ledger._class_kind` → 'orb+status', the dossier FAKE path
grafts a splash pool + two splash briefs (`_fake_splash`) so a hybrid candidate's `fake_output` validates, the
blueprint prompt's one-line HYBRID bullet (and the pre-AV "declare EXACTLY ONE custom summon" bullet corrected to ONE
or TWO), VOCABULARY.md "## Hybrid classes (two pool kinds)". Nothing downstream needed a change — `identity_block`,
the three drop nets, character emission, `coverage.py`, `featured.py`, `app.js`'s pool badges and
`character_validator.py` were already per-pool. The O-2b sketch's `splash_kind` compose field was NOT built: the kind
set falls out of the archetypes' own class_kinds. **Tests:** `tests/test_phase_aw.py` (**96 checks**: both v52 stamps
unchanged + the three independent C# `ContainsKey` pool branches, `candidate_kinds` / hydrate / Candidate consistency,
the brief's hybrid sentences, pruning keeps both sections under v2, kind-list dealing, `_declared_kinds` /
`_splash_sized` / `_validate_hybrid` accept-reject cases, the fake path for orb+status / status+orb / orb+summon,
builder weight + narration, ledger label, drop nets, the contract wording, the rule-0.9 budget, and an OFFLINE
END-TO-END staged forge — the archetype checkpoint picks orb_channel + status_signature, the fake compose composes a
hybrid, and the shipped character carries `orb_slots` 3 + `orb_pool` + a one-status `status_pool`).
`test_phase_av`'s absolute prompt pin repointed to "AV's paragraph still present" (the AU→AV precedent). Suite
**401 passed**; all 33 standalone `tests/test_phase_*.py` modules green; `--fake --staged` forge end to end (v2 on).
C# untouched (rebuilt only to deploy for the smoke; 0 errors). Prompt budget: blueprint 95,153 → **95,949** (+796:
the HYBRID bullet +312, VOCABULARY's four-line section +484 — the rule-0.9 "one-line pointer" form, stretched; the
only offset was the summon-bullet fix); VOCABULARY.md 51,576 → 52,060.

---

## 0. Ground rules

These are the `VOCAB_EXPANSION_4_PLAN.md` §0 rules; the load-bearing ones repeated so this file stands alone.

- **0.1 Lockstep or nothing.** Any vocab change ships across ALL of: `mod/BlankTheSpireCode/` (`ForgedCards.cs`
  SupportedOps / TriggerOps / AmountOps / Validate / ValidateTrigger / Describe / TriggerFragment / VocabVersion ·
  `EffectRunner.cs` · `TriggerRunner.cs` · `DataCard.cs` · `CardSpec.cs` · `Conditions.cs`) +
  `mod/contract/card.schema.json` + `mod/contract/VOCABULARY.md` + `generation/btsgen/` (`cardgen.py` describe
  byte-match · `validator.py` · `census.py` · `bts1.py` VOCAB_VERSION · `class_forge.py` blueprint · `featured.py`
  · `coverage.py` · `data/archetypes.json` · `data/exemplar_pool.json`) + `character_validator.py` when class-level
  rules change.
- **0.2 Describe text is a byte-match contract.** `cardgen.describe()` == `ForgedCards.Describe()` byte-for-byte.
- **0.3 AutoSlay validation is by godot.log tags.** Pass bar per run: ≥1 phase tag fired · 0 mod exceptions · no
  mod-attributable hang. Tag every new mechanic `[<PHASE>] ...`.
- **0.4 Deck-deletion / choice mechanics need an all-aggression tester.**
- **0.5 Choice UIs are AutoSlay-safe** via `AutoSlayCardSelector`; grep for `Auto-selected`.
- **0.6 STOP rules.** Verify-first step contradicts the spec → STOP that phase, write findings, move on.
- **0.7 Commit convention.** One commit per phase: `mod+forge: Phase <LETTER> — <mechanic> (vocab v<N>)`.
  Doc/prompt-only phases: `docs:` or `forge:` prefix, no vocab bump.
- **0.8 Vocab versions.** Assigned in build order starting at **v40**. Phase letters continue from **AJ**.
- **0.9 Prompt budget.** The blueprint prompt is tuned for 7B-class local models. Every prompt addition in this
  plan must be paid for by a removal of equal size or land as a one-line "menu" pointer, not a paragraph.
  Measure with the existing prompt-size assert in `tests/test_harness_v2.py` before and after.

### Standard commands

```powershell
# Generation-side phase test (each file is a standalone module, exit 0 = pass)
cd generation
uv run python -m tests.test_phase_aj

# Full generation suite
cd generation
Get-ChildItem tests/test_phase_*.py | ForEach-Object { uv run python -m ("tests." + $_.BaseName); if ($LASTEXITCODE -ne 0) { throw $_.BaseName } }
uv run pytest -q

# C# build (deploys to the game's mods folder via CopyToModsFolderOnBuild)
dotnet build mod/BlankTheSpire.csproj -c Debug
```

---

## Wave 0 — Text that suppresses supported features (no vocab bump; 1–2 days)

Everything in this wave is prose or data. It ships with `docs:` / `forge:` commits and needs no C# build.
It is first because it is the cheapest creative-range gain in the whole plan: the model is currently being
told that features it can use do not exist.

### W0.1 `DESIGN_HEURISTICS.md` — remove false negatives
- **Issue:** `relic_forms` note says there is no "whenever you lose HP" trigger (`:112-114`); `on_hp_lost` has
  existed since gap #9 (`RELIC_VOCABULARY.md:48`, `ForgedRelic.cs:134-143`). The RELIC FORMS menu (`:95-110`)
  omits `on_hp_lost`, `forge`, `channel_orb`, `summon`. The rarity ladder (`:41`) and reprint rule (`:51`) name
  prototype ops `multi / conditional / from_state / fuse`.
- **Fix:** delete the stale note; add a seventh form **"Bleed payoff"** (`on_hp_lost` → small buff/block) and a
  **"Class-kind boon"** line naming `forge` / `channel_orb` / `summon` hooks. Rewrite the rarity-ladder
  parenthetical to the mod's actual compositional tools: `when` gates, `scale`, `hits`, `add_trigger`, `add_card`,
  X-cost, `grow`, `transform_card`. Same substitution in `reprint_section`.
- **Test:** extend `tests/test_contract_binding.py`: assert no heuristic block contains `from_state`, `multi`,
  `fuse`, or the phrase "no \"whenever you lose HP\"".

### W0.2 `VOCABULARY.md` — stale and misleading lines
- **Issue A:** `:332` "Deeper build-around rares need ops not yet supported; for now make rares hit hard and wide"
  is prompt-injected and false.
  **Fix:** replace with two lines pointing rares at `add_trigger`, `when`-gated payoffs, `scale`, `transform_card`,
  and class-kind engines.
- **Issue B:** `on_discard` (`:232-235`) says it fires when "discarded by an effect"; the engine only fires it from
  the mod's own `discard`/`scry` ops (`EffectRunner.cs:439-441, 462-476`).
  **Fix:** add the caveat "(only THIS class's `discard`/`scry` — base-game relic/enemy discards do not fire it)"
  until Phase AU below lands, then remove.
  **RESOLVED (2026-09-10) by Phase AU (v51):** the caveat is REMOVED — `DataCard` now overrides the game's own
  `AfterCardDiscarded` hook, so every effect discard (base-game relics/potions/other-class cards included) fires the
  Reflex payload; `VOCABULARY.md` and `card.schema.json` say so, and `tests/test_wave0_docs.py` asserts the caveat is
  gone. Turn-end hand cleanup still does not fire it (it flushes via `CardPileCmd.Add` + `Hook.AfterFlush`).
- **Issue C:** `metallicize` (`:72`) is implemented as `PlatingPower` (`EffectRunner.cs:832`). Verify STS2 Plating
  semantics (does it decay when hit?). If it decays, reword the row; if not, add a comment in EffectRunner so the
  next reader doesn't re-audit it.
- **Issue D:** the `discard` row (`:35`) says "no card-selection UI" — the picker exists since Phase X/Z.
  **Fix:** leave until Phase AP (chosen discard) lands; then reword.
- **Test:** `tests/test_contract_binding.py` asserts the `:332` sentence is gone.

### W0.3 `RELIC_VOCABULARY.md` — defects
- **Issue:** truncated sentence "There is no" at `:51-52`; `summon` row (`:69`) says "Summon `amount` of your
  class's minion" (the old multi-pet wording; `amount` is HP now).
- **Fix:** finish the sentence ("There is no `combat_end` for losses; see `combat_end` for wins.") or delete it;
  reword `summon` to match `VOCABULARY.md:29`.
- **Test:** `tests/test_relic_validator.py` asserts the relic vocab text has no line ending in "There is no".

### W0.4 `class_forge.py` blueprint prompt — contradictions with the vocabulary
- **Issue A:** `:257-258` "no conditionals, no state-scaling, no card generation" — `when`, `scale`, `add_card`
  exist.
  **Fix:** replace with "no ops outside the list; but the list INCLUDES `when` gates, `scale` amounts,
  `add_trigger` engines, and `add_card` tokens — use them."
- **Issue B:** `:316` trigger payloads "NO targeted damage or enemy debuffs" — contradicts `VOCABULARY.md:238-242`.
  **Fix:** "payload may carry `target: enemy/all_enemies` on `damage` or an enemy debuff (Noxious Fumes /
  Combust)".
- **Issue C:** `:259-261` fantasy-translation table maps freeze → Weak/Frail, burn/venom → Poison, berserk →
  Strength + lose_hp; `:270` and `contract.py:341-343` then penalize exactly those statuses.
  **Fix:** rewrite the table to route fantasies to **distinct shapes first**: freeze → a `status_pool` debuff
  (`damage_taken` hook, "Brittle") or Frail + `blur`; burn → a `status_pool` DoT once Phase AQ lands, until then
  `poison` OR `on_hp_lost`/`turn_start` targeted damage engine; berserk → `forge` + `scale:"forged"` or
  `temp_strength` + `hp_lost_ge`; venom → `poison` + `target_debuff_count` payoff. Keep Vulnerable/Weak as the
  explicit last resort, but stop banning them outright in `contract.py:341` — replace "reach for them LAST" with
  "at most N cards per class lean on them" (N = the existing `MAX_GENERIC_DEBUFF_SHARE` quota, so the rule and
  the coverage gate agree).
- **Issue D:** `:14` docstring "Starter relics are NOT generated (the mod uses a placeholder)" is stale (Phase L).
  **Fix:** delete.
- **Test:** `tests/test_harness_v2.py` — assert the assembled blueprint prompt does not contain "no conditionals"
  or "NO targeted damage"; assert prompt length is within ±5% of the pre-change size (rule 0.9).

### W0.5 `class_forge.py` section pruning hides the vocabulary from the blueprint stage
- **Issue:** `_PRUNABLE_SECTIONS` (`:912-930`) drops TAGGED SYNERGY, TOKEN GENERATION, RAMPAGE, IN-RUN UPGRADE,
  DECK-THINNING, DISCARD/HAND-CHURN, CORRUPTION, METAMORPH, FORGE, BALANCE, STATUS POOL, SUMMON POOL unless an
  archetype already selected them. The blueprint model therefore never learns those exist, so it can never
  nominate them.
- **Fix:** keep the pruning (prompt budget), but append ONE compact line after the vocab block:
  `ALSO AVAILABLE (ask for the section by name in coverage_nominations): tags, tokens (add_card), rampage (grow),
  in-run upgrade, purge, discard/scry, corruption, transform/graft, forge+blade, balance gauge, custom statuses,
  a summon.` Extend `coverage.sanitize_nominations` to accept a fourth category `"sections"` whose values unprune
  the named section on the compose pass. This costs ~40 tokens.
- **Test:** `tests/test_harness_v2.py` — a blueprint nominating `sections: ["rampage"]` gets the RAMPAGE section
  in its compose prompt; one that doesn't, doesn't.

### W0.6 `contract.py` v1 card prompt — prototype residue
- **Issue A:** `_FEW_SHOT_IDS` (`:75-78`) lists `body_slam`, `twin_strike`, `disarm`, `battle_trance`, `anger`,
  `bloodletting`, `inflame`. None exist in `mod/content/cards/` (only `bash cleave clothesline defend expose
  hold_the_line iron_wave last_stand measured_riposte pommel_strike quick_jab rampart reckoning strike`). Under
  the repointed contract those few-shots are silently missing; under the default paths they are prototype cards
  using `from_state`/`set_flag`/`multi`.
  **Fix:** `_FEW_SHOT_IDS = ["strike", "defend", "bash", "cleave", "iron_wave", "expose", "hold_the_line",
  "rampart", "reckoning", "last_stand"]` and assert at import that every id resolves in `CARDS_DIR`.
- **Issue B:** `:276-279` names `multi, from_state, conditional`; only `harness_v2.compositional_clause` fixes it
  under `BTS_HARNESS_V2=1`.
  **Fix:** make the v2 clause the only clause (v2 has been live since 2026-09-08 for A/B; if the A/B is still
  running, gate the wording on the flag but make BOTH branches name mod ops).
- **Test:** `tests/test_contract_binding.py` — every few-shot id resolves; the rendered card prompt contains none
  of `from_state`, `set_flag`, `multi`, `fuse`.

### W0.7 `archetypes.json` — stale flags and metadata
- **Issue:** `buildable:false` on `reaper_lifesteal` (`:550`), `countdown_ripen` (`:613`), `balance_gauge`
  (`:643`), `token_conjurer` (`:708`) though their gaps are `done`; runtime recomputes (`catalog.py:167-180`) so
  the file lies. Duplicate metaphors: "the blade reforged" (`:46`, `:787`), "the rising storm" (`:82`, `:250`),
  "momentum" (`:244`, `:276`), "the curse" (`:406`, `:493`), "the crimson tithe" (`:468`, `:533`). `ops` lists mix
  statuses/conditions/scales/triggers (`:98`, `:196`, `:867-868`, `:898-901`, `:931`).
- **Fix:** flip the four flags; give each duplicated metaphor a distinct phrase; rename the field `ops` →
  `vocab` (it is what `catalog.live_vocab_tokens()` treats it as) or leave the name and add a schema comment.
  Add a `tests/test_archetypes.py`: no two archetypes share a metaphor string; every `buildable:false` names an
  open gap id that is not `done` in `VOCABULARY_GAPS.md`.

### W0.8 `exemplar_pool.json` — coverage imbalance and mis-tagging
- **Issue:** 46 exemplars, 14 archetypes with exactly one, and two of those (`token_conjurer` via `ex_ash_dividend`
  `:34`, `metamorph` via `ex_surge_capacitor` `:38`) don't use their archetype's mechanic. No exemplar uses
  `summon`, `buff_summon`, `heal_summon`, `add_card`, `transform_card`, `graft_card`, `blade_empower`,
  `summon_blade`, `gain_orb_slot`, `evoke`, `focus`, `draw_pile_empty`, `light_ge`, `centered`, a custom orb, or
  `upgrade.cost`.
- **Fix:** author ~20 exemplars so every archetype has ≥2 and every op/condition/scale in `VOCABULARY.md` appears
  in ≥1 exemplar. Retag `ex_ash_dividend` → `exhaust_pyre` only, `ex_surge_capacitor` → `big_energy` only. Add
  `needs:"balance"` support (see W0.9).
- **Test:** `tests/test_exemplars.py` — (a) every archetype id has ≥2 exemplars; (b) every exemplar uses ≥1 token
  from each tagged archetype's `ops`; (c) every backtick op/status/when-kind/scale token in `VOCABULARY.md`
  appears in some exemplar; (d) every exemplar passes `validator.validate_card`.

### W0.9 Exemplar dealing by archetype, not substring
- **Issue:** `harness_v2._pool_kind` (`:160-167`) satisfies `needs:"forge"` only when an archetype id contains
  the substring "forge"; `balance_gauge` and `forge_ramp` are `class_kind:"normal"` (`archetypes.json:641`, `:68`)
  so no `needs:"balance"` can exist and no class-kind guidance attaches.
- **Fix:** add an optional `mechanic_kind` field on archetypes (`forge` / `balance` / `discard` / …), and make
  `_pool_kind` return the union of the blueprint's `class_kind` plus every selected archetype's `mechanic_kind`.
  Leave `class_kind` alone (it drives pool declarations).
- **Test:** `tests/test_harness_v2.py` — a triad containing `balance_gauge` is dealt the balance exemplars.

### W0.10 Balance notes for every archetype
- **Issue:** only 4 of 34 archetypes have an `archetype-note` (`DESIGN_HEURISTICS.md:120-130`), so the MAP stage
  prints no `balance:` line for the other 30.
- **Fix:** write a one-sentence note for each of the remaining 30 (numbers cap, what counts as the payoff, what
  must not be stacked). Prioritize class-kind archetypes (orb_channel, slot_machine, summon_swarm,
  status_signature, forge_ramp, balance_gauge, madness_discard, token_conjurer, metamorph, exhaust_pyre).
- **Test:** `tests/test_contract_binding.py` — every archetype id has a non-empty note.

### W0.11 `VOCABULARY_GAPS.md` triage of #42–#48
- **#48 Penance Counter:** likely expressible today (`on_hp_lost` trigger + targeted `damage` payload). Build the
  Gap Tester, run AutoSlay, mark `done` with the verify-then-close pattern from gap #4.
- **#44 Coin & Ledger:** re-sketch as Forge-with-spend (a `spend_forge` op that consumes N counter for a payoff).
  Mark `planned` → Phase AX below.
- **#45/#46/#47 Contagion:** re-sketch as ONE op `spread_debuffs` (copy the target's debuffs to all other
  enemies). Mark `planned` → Phase AX. Adjacency stays rejected (#34).
- **#42/#43 Graveyard:** mark `rejected` for now (needs a fourth pile; `ForgedCards.cs:289` piles are
  hand/draw/discard). Note the nearest expressible shape: `ripen` + `add_card` from a "buried" token.

---

## Wave 1 — Lockstep hygiene: expose what the engine already runs (Phase AJ, vocab v40; ~2 days)

One phase, one vocab bump, because all four items change only validation and schema.

### Phase AJ — "Hidden capacity" (v40)
1. **`random_enemy` card target.** Engine maps it (`ForgedCards.cs:351`), Describe already says "to a random
   enemy" (`:1137`, `cardgen.py:344`). Add to `card.schema.json:13` enum, `VOCABULARY.md` Targeting table,
   `validator.py` target set, `census.py` target counts.
2. **Multi-hit `summon_attack`.** Engine executes `hits` (`EffectRunner.cs:320-322`); `validator.py:416-417`
   rejects `hits` off `damage`. Change the guard to `op not in ("damage", "summon_attack")`.
3. **Custom orb names in trigger payloads.** `TriggerRunner.cs:107-109` resolves them; `ForgedCards.cs:1012-1013`
   and `card.schema.json:147` restrict to base orbs. Relax both to "base orb, `random`, or a name in the class's
   `orb_pool`" (mirror the card-side check). `VOCABULARY.md` Triggers list: "`channel_orb` (any pool orb)".
4. **`once_per_turn` on `on_blade_played`.** Add to `validator.py:68` `_MULTI_FIRE_TRIGGERS`.
5. **Unknown custom orb silently channels Lightning.** `EffectRunner.cs:906-908` and `OrbRunner.cs:89-90`
   `?? OrbTypeFor("lightning")`. Replace with `Logger.Warn("[Forged] unknown orb '{orb}' — skipped")` + `continue`.
   Make `ForgedCards.Validate` reject an unknown pool name at import so it never reaches runtime.
6. **`VocabVersion = 40`, `bts1.VOCAB_VERSION = 40`.**
- **Test spec:** `tests/test_phase_aj.py` — random_enemy card validates and describes byte-identically; a
  `summon_attack` with `hits:3` validates; a trigger `channel_orb orb:"ember"` validates for a class whose pool
  has Ember and fails for one that doesn't; `on_blade_played` + `once_per_turn` validates. Gap Tester
  `generation/scratch/gaptest-aj/` (random-enemy attack, multi-hit summon attack, Ember auto-channeler) →
  AutoSlay, grep `[AJ]`.

### Phase AJ-b — Prototype path leakage (no vocab bump; `forge:` commit)
- **Issue:** `paths.py:36-61` defaults point card schema/vocab/statuses/cards at `prototype/`; `RELIC_*` and
  `CHARACTER_*` have no `BTSGEN_*` override at all and `point_btsgen_at_mod_contract()` (`class_forge.py:131-160`)
  never repoints them. `relic_contract.py` and `character_contract.py` therefore read prototype schemas
  (`combat_start`, `victory`, `attack_base`, tiers common/boss, `raw:true`, `max_energy 1..6`). `validator.py:159`
  reads prototype statuses so 12 of 18 mod statuses are "unknown" unless repointed. `validator.py:39`, `:244-250`,
  `:722-733` still walk `multi/conditional/from_state/fuse`. `_STATUS_WEIGHT` (`:26-32`) keys are prototype names.
- **Fix:**
  1. Flip `paths.py` defaults to the mod contract (`CARD_SCHEMA`, `VOCABULARY`, `STATUSES_DIR`, `CARDS_DIR`,
     `RELIC_VOCABULARY`, and a NEW `mod/contract/relic.schema.json` extracted from `class_forge._RelicContract`).
     Keep the `BTSGEN_*` env overrides for the prototype; make `point_btsgen_at_mod_contract()` a no-op that
     stays for callers.
  2. Delete the prototype ops from `validator.py` (`:39`, `:244-250`, `:722-733`).
  3. Re-key `_STATUS_WEIGHT` to the 18 mod statuses (proposed: vulnerable 2, weak 1.5, frail 1.5, poison 1.2,
     strength 4, dexterity 3, temp_strength 2, temp_dexterity 1.5, thorns 2, regen 2, metallicize 3, artifact 2,
     buffer 3, blur 2, intangible 8, ritual 5, barricade 5, focus 3). Keep `power_ceiling` warning-only.
  4. `relic_contract.py` / `character_contract.py` / `character_pipeline.py`: either retire (the production path is
     `class_forge`) or repoint. Recommendation: mark deprecated in the docstring, delete the prototype schema
     embed, and make `cli_relic_generate` / `cli_character_generate` call the `class_forge` contracts.
- **Test:** `tests/test_contract_binding.py` — with NO env set, `paths.CARD_SCHEMA` is the mod schema; every
  mod status is known to `validator`; no `from_state` anywhere in `btsgen/` except a comment.

---

## Wave 2 — Coverage pressure: make the generator reach for the whole vocabulary (no vocab bump; ~2 days)

The vocabulary is wide, but `coverage.py`/`featured.py`/`census.py` only measure a slice, so nothing pushes
the model toward the rest.

### W2.1 `census.py` — count what exists
- Count multi-hit (`hits ≥ 2`) as non-plain (`:123-131`); count the four keywords (exhaust/retain/innate/ethereal);
  count `apply_status_custom` statuses and `buff_summon` statuses (`:92-95`); move `poison`, `frail`, `focus` into
  their own bucket (`:44-47`); count `tags`, `upgrade.cost`, `once_per_turn`, `ripen` amounts, targeted payloads.
- `format_report` (`:256-264`) prints every counter, not a fixed subset.
- **Test:** `tests/test_census.py` extended per counter.

### W2.2 `coverage.py` — widen the menus, gate by class kind
- `WHEN_MENU_V2`: add `retained_last_turn`, `draw_pile_empty`, `hp_lost_ge value:3`, `target_has_status
  status:vulnerable`; class-kind-gated entries `forged_ge` (forge), `dark_ge`/`light_ge`/`centered` (balance),
  `orbs_match`/`orb_count_ge` (orb).
- `SCALE_DIRECTIVE` → a `SCALE_MENU`: `cards_in_hand`, `cards_retained`, `unspent_energy_last_turn`,
  `target_debuff_count`, `damage_dealt_unblocked` (heal), `tag_cards_owned` (needs a tag), `forged` (forge only).
- `EXOTIC_MENU_V2`: add `ritual`, `barricade`, `intangible` as **nominate-only, rare-tier** (repair never injects
  them; the blueprint may nominate one).
- New `KEYWORD_MENU`: `retain`, `innate`, `ethereal`, `hits` (multi-hit) with a `MIN_KEYWORD_KINDS = 2` quota.
- `NOMINATION_CATEGORIES` += `"scale"`, `"keyword"`, `"sections"` (W0.5).
- **Test:** `tests/test_coverage.py` — each new menu key has a directive, a census detector, and appears in
  `DIRECTIVE_BY_KEY`; repair walks the new menus.

### W2.3 `featured.py` — class-kind-aware roulette
- Keep the base menu as is. Add a second menu `FEATURED_CLASS_KIND` dealt only when the blueprint's class kind or
  a selected archetype's `mechanic_kind` (W0.9) matches: orb (`evoke` burst card, `gain_orb_slot`, `focus`
  power), status (`apply_status_custom` on ≥3 cards), summon (`heal_summon`/`shield_summon` medic,
  `buff_summon`), forge (`blade_empower`, `summon_blade`, `on_blade_played`), balance (a `centered` payoff),
  discard (`scry` + `on_discard`), transform (`graft_card`).
- **Test:** `tests/test_featured.py` — a summon-kind class rolls at least one summon featured entry; a normal
  class never does.

### W2.4 Character-level knobs the generator never touches
- **`max_energy` is never prompted** (assembly default 3, `class_forge.py:2730`; C# allows 1..10).
  **Fix:** blueprint field `max_energy` ∈ {2,3,4} with a one-line rule ("4 only with a smaller HP pool or a
  drawback relic; 2 only for a big-energy/X-cost class with cost 0–1 cards"). Validator range 2..4.
- **Pool `color {h,s,v}`** parsed by C# (`ForgedCharacters.cs:280-286`) but never emitted (`class_forge.py:2725`).
  **Fix:** blueprint field `color` (hue 0–359, or a named palette entry); emit it. Default stays slot-index hue.
- **Caps:** summon `max_hp` 60 → 100 (`class_forge.py:1838`); `orb_slots` 4 → 5 (`:1440`); `max_hp` 60..95 →
  55..100 (`:1432`). Keep the engine caps as the hard ceiling.
- **Test:** `tests/test_forge.py` — assembled blueprint carries `max_energy` and `color`; ranges enforced.

---

## Wave 3 — Cheap engine additions (one phase each, vocab bumps v41+; ~1 day each)

Each phase uses an API already called nearby, so the verify-first step is a grep, not a spike.

### Phase AK — Attacker target + once_per_combat on card triggers (v41)
- **`target:"attacker"`** on `attacked` payloads. `ForgedTriggerPower.cs:98-129` already holds `dealer`; thread it
  into `TriggerRunner.Run(t, player, ctx, attacker: dealer)` and resolve `"attacker"` in `ResolveEnemies`
  (`TriggerRunner.cs:158-165`), mirroring `RelicRunner.cs:50`. Closes the riposte polish (gap #4 note) and the
  J-3 "true Thorns" item.
- **`once_per_combat`** on `add_trigger` (relic pattern `RelicRunner.cs:30-33`). Trigger powers are per-combat
  instances already (`ForgedTriggerPower.cs:33-37`), so it's a bool + a fired flag.
- Lockstep: schema `triggerEffect.target` enum += `attacker` (attacked only); `add_trigger` += `once_per_combat`
  (reactive only); Describe: "…to the attacker" / "Once per combat, …".
- **Test:** `tests/test_phase_ak.py`; Gap Tester: two-enemy fight, riposte hits the one that struck.

### Phase AL — Richer trigger payloads (v42)
- Allow in `TriggerOps` (`ForgedCards.cs:267-277`) + schema `triggerEffect.op`: `apply_status_custom` (status
  class only), `summon_attack` / `buff_summon` (summon class only; the dormant move-cycle re-expressed as a card
  engine), `hits` on payload `damage`/`summon_attack` (`ForgedCards.cs:1094` currently rejects; `SummonRunner.cs:47`
  already loops hits).
- Payload `scale` (`ForgedCards.cs:315`) += `forged`, `unspent_energy_last_turn`, `cards_in_hand` (all player-level
  reads: `EffectRunner.ForgeStacks`, `HandStateTracker.cs:27`).
- **Test:** `tests/test_phase_al.py`; Gap Tester: "At turn start, gain 1 Razor Focus"; "At turn end, your summon
  attacks for 4 twice".

### Phase AM — New scales and conditions (v43)
- `scale` += `block` (Body Slam), `hp_lost_this_turn` (`HpLossTracker.cs:29`), `draw_pile_count`
  (`Conditions.cs:107`), `energy` (`HandStateTracker.cs:52`), `plays_this_combat` (`EffectRunner.cs:786-791`).
  One `ScaleValue` case each (`EffectRunner.cs:730-738`).
- `when` += `target_hp_below_half`, `target_has_block` (target creature already flows into `Conditions.Eval`
  `:78-91`), `energy_ge`, `cards_played_this_turn_ge` (`CombatManager.History`, `:788-790`).
- **Test:** `tests/test_phase_am.py`; describe byte-match for each new phrase.

### Phase AN — Small ops (v44)
- `gain_max_hp` (`CreatureCmd.GainMaxHp` in use `EffectRunner.cs:931`) — Feed; cap 1..5, rare-tier note.
- `damage` flag `unblockable:true` (`ValueProp.Unblockable` in use `:149`).
- `temp_thorns`, `temp_focus` statuses via `CustomTemporaryPowerModel` shells (`ForgedTempStatPowers.cs:24-37`).
- **Test:** `tests/test_phase_an.py`.

### Phase AO — Card-type-scoped cost modifiers (v45)
- New op `cost_shift {card_type: attack|skill|power|all, amount: -1..-2, scope: this_turn|combat, count?: 1}`.
  Generalizes `ForgedCorruptionPower.TryModifyEnergyCostInCombatLate` (`:43-54`); `count:1` gives "next Skill
  costs 0". Closes the Corruption `card_type` deferral (`VOCAB_EXPANSION_4_PLAN.md:142`) and the relic
  "first card costs 0" deferral (`PHASE_L…:367-369`) via the same power.
- Loop-discipline rule: `cost_shift` with `scope:combat` is rare-only and at most one per class.
- **Test:** `tests/test_phase_ao.py`; Gap Tester: "Your Attacks cost 1 less this turn".

### Phase AP — Pile manipulation and status cards (v46)
- `discard` gets `cards: random|choose` (`CardSelectCmd.FromHand` `EffectRunner.cs:562,649` + `CardCmd.Discard`
  `:457`). Then reword `VOCABULARY.md:35`.
- `retrieve_card {pile: discard|exhaust, cards: random|choose}` — the blade path minus the token filter
  (`CardPileCmd.Add` `ForgedForgePower.cs:74`; `CardSelectCmd.FromCombatPile` per `SPIKE_CARD_SELECT.md`).
- `add_status_card {card: dazed|wound|burn, pile, amount}` — `AddGeneratedCardToCombat` (`EffectRunner.cs:425`)
  with `ModelDb.Get(typeof(Dazed))` (pattern at `:248`; `Dazed` referenced at `PetDamageAttributionPatch.cs:12`).
  Closes F4 (`VOCAB_EXPANSION_PLAN.md:89-93`).
- Rule 0.4/0.5 apply (choice UI + deck-thinning tester).
- **Test:** `tests/test_phase_ap.py`; grep `Auto-selected`.

### Phase AQ — Status-pool hooks (v47)
- `damage_over_time` hook (debuff; stacks lose HP at the afflicted enemy's turn start, then decay per `decay`)
  — the burn/freeze fantasy (`VOCAB_EXPANSION_2_PLAN.md:363-364`). Implement as a `ForgedStatusPower` branch on
  `BeforeTurnStart` of the owner creature.
- `mode: multiplicative` — parsed already (`StatusSpec.cs:27`); implement for `damage_dealt`/`damage_taken`
  (`×(1 + 0.1·stacks)`, capped) and open the validator.
- `hit_count` hook — **verify first**: the J-1 blocker was no dealer accessor on `AttackCommand`.
  `PetDamageAttributionPatch.cs` now attributes pet damage, so check whether the same patch point exposes the
  dealer. If yes, implement; if no, STOP and record.
- **Test:** `tests/test_phase_aq.py`; Gap Tester: a "Scorch" DoT class.

### Phase AR — Conditions inside custom orb effects (v48)
- `OrbSpec.OrbEffect` (`OrbSpec.cs:11`) gains `When`; `OrbRunner` evaluates `Conditions.Eval` before each orb
  effect. Closes `PHASE_I_FORGED_ORBS_PLAN.md:95,118`.
- **Plasma / Glass:** do NOT add base orbs. Instead add two **custom-orb recipes** to `VOCABULARY.md` (Plasma =
  passive `gain_energy 1`; Glass = passive nothing, evoke `damage` ×3) so the model builds them from the existing
  pool machinery. Verify `gain_energy` is legal in orb passives; if not, add it.
- **Test:** `tests/test_phase_ar.py`.

### Phase AS — Relic vocabulary (v49)
- `on_card_played` hook gains `card_type` filter — **verify first**: `PHASE_L…:366` said `CardModel` had no clean
  type accessor; `DataCard.cs:283-284` frames by type, so the accessor exists on our own cards — check base cards.
- `every_n` on a hook (per-relic counter): `{trigger, every_n: 3}` fires on the 3rd, 6th… occurrence.
- `attack_base` modifier (always-on +N attack damage) — cheap (`PHASE_L…:271`); price it in `_MODIFIER_VALUE`.
- **Reprice `max_energy` / `cost_reduction`** (`class_forge.py:1092-1098`): keep them above budget ALONE, but let a
  second `drawback` hook (new: `turn_start` → `lose_hp` / `discard 1` / `apply_status weak self`) subtract from
  the price so "Coffee Dripper with a cost" is reachable. Add a `max_hp` modifier (±) to the modifier table as the
  standard drawback.
- True `combat_start`: **spike** (`PHASE_L…:149` unknown #2: reach player+ctx in `BeforeCombatStart`). If
  `ForgedRelic.cs:88-98` still can't get a ctx, keep the `turn_start + once_per_combat` idiom and document it as
  the ONLY spelling (already done). Do not block AS on it.
- Update `DESIGN_HEURISTICS.md` relic forms with "Counter relic" and "Boon with a price".
- **Test:** `tests/test_phase_as.py`, `tests/test_relic_validator.py`, `tests/test_keystone_balance.py`.

### Phase AT — Summon damage counts as "you deal damage" (v50)
- `ForgedTriggerPower.cs:164-169` requires `dealer == Owner && cardSource != null`; `summon_attack` deals via the pet
  with no card. Use `PetDamageAttributionPatch` to attribute pet damage to the owner for `on_damage_dealt` (and the
  relic twin). Summon classes can then build "whenever you deal damage" engines.
- **Test:** `tests/test_phase_at.py`; Gap Tester: summon attack + on_damage_dealt draw.

### Phase AU — `on_discard` for base-game discards (v51)
- **Verify first:** find the base-game discard hook (grep the decompiled API for the equivalent of
  `AfterCardDiscarded` / `CardCmd.Discard` completion). If present, call `DataCard.FireOnDiscard`
  (`DataCard.cs:263`) from it with the existing `_firingOnDiscard` guard. If absent, STOP; the W0.2 caveat stays.

---

## Wave 4 — Dormant subsystems, structural caps, and new content types (~1 week+)

### Phase AV — Re-enable the autonomous minion model (v52)
- Engine is present and mostly live: `SummonSpec.cs:19-28` (`Moves`, `Attackable`, `OnSummon`, `OnDeath`), parser
  `ForgedCharacters.cs:622-680`, move cycle `ForgedSummonPower.cs:43-52`, death rattle `:57-64`, ethereal
  `ForgedSummonShieldPower.cs:47-49`.
- Two C# fixes: fire `SummonRunner.RunActions(spec.OnSummon, pet, ctx)` inside `SummonForged`
  (`EffectRunner.cs:920-946` — parsed but never called); key `FindLivingSummon` on summon NAME so `MaxSummons = 2`
  (`ForgedCharacters.cs:593`) is reachable.
- Generation lockstep: drop `_REMOVED_SUMMON_FIELDS` (`class_forge.py:1901`), `_MAX_SUMMONS` 1 → 2 (`:1837`),
  re-add the K-3 prompt section (gated: a summon class may opt into ONE autonomous minion; the passive Osty model
  stays the default), restore `VOCABULARY.md:318-319`.
- Add the K-3 deferred payoffs while here: `on_nth_attack` counter on the summon spec; `sacrifice_summon` op
  (consume the living minion for a payoff, `PHASE_K…:111`).
- Rule 0.3: the K-3 AutoSlay history shows random bots stall on pets; reuse the K-3 Gap Testers.
- **Test:** `tests/test_phase_av.py`.

### Phase AW — Hybrid class kinds in generation (v52, no engine change)
- Blocked on an AutoSlay smoke that drives a hybrid (orb + status, say) into combat
  (`PHASE_N_CREATIVE_BREADTH_PLAN.md:40`). Run that smoke FIRST with a hand-built BTS1 code (the importer already
  accepts hybrids, O-2a). If it passes: `class_forge.py:795-800` `class_kind` becomes a set; pools are emitted for
  each kind; exemplar dealing (W0.9) already handles unions.
- **Test:** `tests/test_phase_aw.py`.

### Phase AX — Structural caps and the gap #44/#45 ops (v53)
- **Cost 0..3 → 0..4** (`card.schema.json:12,24`; engine has no cap). Rule: cost 4 only at rare with a headline
  effect.
- **Upgrade may add a keyword** (`ForgedCards.cs:963-964`, `validator.py:620-622` require equal effect counts).
  Relax: the upgrade may append exactly one of `exhaust`/`retain`/`innate`/`ethereal` or remove `exhaust`.
- **Two-of-a-kind values.** Keep "one damage / one block per card" (the Damage/Block vars are canonical,
  `DataCard.cs:142,149`). Allow a second `apply_status` of the SAME status when the second is `when`-gated, by
  suffixing the var name (`Weak2`). Leave Loss/Discard/Scry/Heal/Energy singletons.
- **`tags` maxItems 2 → 3** (`card.schema.json:16`).
- **`spend_forge {amount}`** — consumes Forge for a payoff (gap #44 re-sketch); pairs with `forged_ge`.
- **`spread_debuffs`** — copy every debuff on the target to all other enemies (gap #45–47 re-sketch; reads the
  target's powers the way `target_debuff_count` does).
- **Test:** `tests/test_phase_ax.py`.

**STATUS (2026-09-11): Phase AX EXECUTED (vocab v53)** — the four structural caps and both gap #44/#45 ops are LIVE,
engine + generation in lockstep. **(1) Structural caps.** Card `cost` ceiling 3 → 4, with the heavyweight slot
**RARE-only** on both sides (`ForgedCards.MaxCardCost` / `validator._MAX_COST`; the upgrade `cost` band widens with it,
upgrades still only cheapen); `tags` maxItems 2 → 3. **(2) An upgrade may change ONE keyword.** The old flat rule
("upgrade effect count must match base effect count") becomes `ValidateUpgradeShape` / `_upgrade_shape_errors`, mirrored
line for line: an upgrade may **append exactly one** of `exhaust`/`retain`/`innate`/`ethereal` the base lacks, or **drop
a trailing `exhaust`**; equal-length upgrades must now carry the SAME keyword set (verified safe — 0 of the 92 existing
cards with upgrades had a mismatch). Runtime rides BaseLib's designed `UpgradeKeywords` path: `DataCard` declares
`WithKeyword(kw, UpgradeType.Add/Remove)` from the base-vs-upgrade diff, so `ConstructedUpgrade` does the add/remove and
indices 0..n-1 still overlay positionally. **(3) Two of a kind.** A card may declare the SAME `apply_status` twice when
the SECOND is `when`-gated: `VarKey` is occurrence-numbered (`status:weak:2`), `DataCard` gives it a suffixed PowerVar
(`Weak2`) via BaseLib's named `WithPower<T>(name, …)`, and `EffectRunner` applies that one with its literal
upgrade-aware amount (the apply_status_custom card path) — so the DynamicVarSet ctor never sees a duplicate key. An
ungated pair and a third copy both reject. **(4) `spend_forge`** (gap #44 re-sketch, amount 1..10): consumes the
per-combat Forge counter as the card's PRICE, the cash-out half of the ramp `forge` builds.
`ForgedForgePower.Spend` mutates the live stack and removes the power at 0 (the Balance-gauge pattern — `PowerCmd.Apply`
only adds); over-asking just empties the counter, so an ungated card is weak, never broken. Card-only, never on a BASIC,
never a card's only effect, one per card. **A new ORDERING rule** (both sides) keeps it honest: a `when:forged_ge`
effect may not come AFTER the `spend_forge` in the same list — effects resolve top-to-bottom, so the gate would read the
counter this card just emptied. **(5) `spread_debuffs`** (gaps #45–#47 re-sketch): a flag-op that copies the struck
target's Vulnerable/Weak/Frail/Poison — at their live stack counts — onto every OTHER living hittable enemy. Needs a
chosen target, so single-enemy cards only; card-only, never on a BASIC, one per card.

**(6) The AutoSlay gate PASSED — a full RunCompleted, not the usual map-nav stall.**
`generation/scratch/gaptest-ax/build_tester.py` stages a FORGE class into slot 04 ("AX Gap Tester": full ramp — Strike
with `forge` income, a turn_start income power, a cost-4 rare `scale:"forged"` AoE carrying three tags — plus the
cash-out, the contagion card, the two-of-a-kind Weak card, an upgrade that appends `retain` and one that drops
`exhaust`, and an in-combat `upgrade_card cards:"all"` so BaseLib's `ConstructedUpgrade` fires every fight instead of
waiting on a random campfire). Seed `GAPTESTAX2`, **181 rooms, verdict PASS (RunCompleted), 0 mod-attributable
exception frames**, and every one of the seven new paths fired: `spend_forge` ×56 (including the clamp — "had 0, spent
0" — and partial spends), `spread_debuffs` ×29 real copies (+61 honest no-ops when the target was clean or alone),
`upgrade keyword ADD 'retain'` ×89 across two cards, `upgrade keyword REMOVE 'exhaust'` ×50, and the gated second Weak
(`Weak2`) ×4. Evidence: `generation/scratch/gaptest-ax/godot_AX_tags_GAPTESTAX2.txt`. Slot 04 unstaged.

**(7) The first smoke run found a real bug — in the harness, not the contract.** Seed `GAPTESTAX1` rejected slot-04
card 05 with "the base card already has 'ethereal'": `smoke_relic` injects `ethereal` into a starting-deck card by
APPENDING it to both the base and upgrade lists, which under the new rule puts `ethereal` last in the upgrade and so
claims to be the appended keyword. `smoke_relic._inject_ethereal` now inserts in front of a trailing `exhaust` (base)
and in front of an upgrade's appended keyword, keeping all four shapes importable; `tests/test_phase_ax.py` pins that.

**Lockstep:** `ForgedCards` (VocabVersion 53, SupportedOps, AmountOps, the caps, `ValidateUpgradeShape`,
`StatusOccurrence`/`StatusVarName`/`StatusDisplay`, the occurrence-aware `VarKey`, the cost band + rare gate, two
Describe sentences), `EffectRunner` (both op cases, `SpreadDebuffs`, the gated-status branch), `DataCard` (named
PowerVars, `KeywordUpgrade`/`DeclareUpgradeKeywords`, the `[AX]` upgrade tag), `ForgedForgePower.Spend`;
`card.schema.json` (cost 0..4 ×2, tags maxItems 3, the op enum + two clauses), `VOCABULARY.md` (two op rows, the card
shape, the two-of-a-kind paragraph), `validator.py`, `cardgen.py`, `bts1.py` (VOCAB_VERSION 53), `census.py` (a `cost4`
counter + an AX line), `featured.py` (contagion + forge_cashout), `harness_v2.py`, `class_forge.py` (the cash-out beat +
the pool-card cost band), `archetypes.json` + 3 exemplars (pool 117), `smoke_relic.py`, `web/static/app.js`;
`tests/test_phase_ax.py` (118 checks), suite 402 passed, C# build 0 errors.

### Phase AY — Run-persistent Forge (spike, then v54 if green)
- `PHASE_M_FORGE_PLAN.md:45-46`, `SOVEREIGN_BLADE_SCOPE.md:167`: needs run-persistent state. Spike: does the mod
  already persist anything per run (`user://forged/...` is per-install, not per-run)? If STS2 exposes a run-save
  hook, store `forge_persist` on the character and rehydrate `ForgedForgePower` at combat start. Otherwise STOP and
  keep per-combat.
- **Test:** `tests/test_phase_ay.py`.

**STATUS (2026-09-11): the AY-0 spike came back GREEN, and Phase AY EXECUTED on it (vocab v54)** — run-persistent
Forge is LIVE as an opt-in CLASS flag, engine + generation in lockstep.

**(0) The spike.** Two questions, both answered off the decompile + the pinned BaseLib 3.2.1 source in
`_modref/`. *Does the mod persist anything per run?* **No** — nothing in `BlankTheSpireCode/` used a
`[SavedProperty]` or a BaseLib spire field; `user://forged/...` is the per-install class library, not run state.
*Does STS2 expose a run-save hook?* **Yes, two of them.** The base game carries a reflective
`[SavedProperty]` system (`Saves.Runs/SavedProperties.cs`) whose values ride `SerializableCard.Props` /
`SerializableRelic.Props`, with `SavedPropertiesTypeCache.InjectTypeIntoCache(Type)` as the public door for mod
model types — but the PLAYER has no props bag, so a character-level counter has no home there. BaseLib 3.2.1
fills exactly that gap: `SavedSpireField<TKey,TVal>` plus `ExtendedSaveTypes`/`ExtendedSaveHandlers`, which patch
`SerializablePlayer`'s JSON *and* its packet round-trip (`ExtendedSavePatches.AddContext<Player,
SerializablePlayer>`), so `SavedSpireField<Player,int>` is a run-scoped, save-backed int. Registration is
automatic: BaseLib's post-mod-init scan force-initializes STATIC spire fields on mod types and sorts them into the
save handlers. (Worth recording: base-game Forge is per-combat too — `ForgeCmd` creates the Sovereign Blade token
inside the fight — so "the blade remembers across a run" is OUR design, not a base-game inference.)

**(1) The flag.** Character-level `forge_persist` (bool, default false, **FORGE-CLASS ONLY**). Absent on every
pre-v54 class, and the bundle only grows the key when it is set — so old codes are byte-identical.

**(2) The rule.** At combat end the class banks `min(Forge, ForgedForgePower.PersistCap = 5)`; at the start of its
first turn of the next combat the carry is paid back through `Stoke` — the same path a first Forge income takes, so
**the signature blade is summoned too** — and the bank empties (re-banked from whatever the counter holds when
THAT fight ends). The cap is the whole balance argument: a turn_start income engine banks ten-plus a fight across
~50 fights, so an uncapped carry would print free damage by Act 2; five is one good income card and the threshold
the contract's own example gate reads (`when forged_ge value:5`), so a ramping persist class opens the next fight
already at its first payoff. Head start, not snowball — income and payoffs stay priced per combat.

**(3) Where each half lives.** The BANK is on the power itself (`ForgedForgePower.AfterCombatEnd`): the hook still
sees the live counter, because the game clears powers later, in `Player.AfterCombatEnd`. The RESTORE cannot be —
the power does not exist yet — and no combat-start hook hands out a `(ctx, player)` (the same L-0 finding the
relic's `start_combat_block` lives with), so it rides `AfterPlayerTurnStart`, guarded to once per combat. That
needs a listener every forge class has, and not every class ships a relic: hence `Engine/ForgePersist.cs`, the
mod's first BaseLib `CustomSingletonModel`, on **`HookType.Combat`** — `Hook.AfterPlayerTurnStart` iterates
`combatState.IterateHookListeners()`, which run-state subscribers never reach.

**(4) The AutoSlay gate PASSED.** `generation/scratch/gaptest-ay/build_tester.py` stages a persist FORGE class into
slot 04 ("AY Gap Tester": Strike-with-`forge` income, a turn_start income power, a `scale:"forged"` payoff in the
STARTING deck so the carry is visibly cashed on turn 1, a `summon_blade` retrieval, and the blade token — kept out
of the starting deck, because a blade sitting in the deck makes the first-Forge summon a no-op and hides the very
thing under test). Seed `GAPTESTAY2`: **5 banks / 4 restores, every bank CLAMPED (8→5, 9→5, 13→5, 17→5), 4×
`[T] blade summoned … (first Forge of combat)`, 4 `[M] forged payoff` reads at exactly `Forge 5`, 0
mod-attributable exception frames.** Seed `GAPTESTAY1` covers the other branch — a short first fight banks **2 and
gets exactly 2 back**. Verdict on both is the usual map-nav watchdog stall, not mod-attributable (rule 0.3 gates on
tags + exceptions). Evidence: `generation/scratch/gaptest-ay/godot_AY_tags_GAPTESTAY{1,2}.txt`. Slot 04 unstaged.

**(5) Rule 0.9 paid in full.** The prompt additions are two one-liners (a `"forge_persist": false` row in the
blueprint format block, one RULES line) plus one clause in the FORGE archetype paragraph — no new paragraph — and
they are paid for by de-duplicating what the contract already said twice: the `forge` op row's restatement of the
`forged` scale bullet (payoff shape + the pairing rule), `spend_forge`'s doubled ordering rule, and the forge
beat-1 blade shape. Blueprint prompt **99,147 → 99,938** (ceiling 100,000).

**Lockstep:** `ForgedCards` (VocabVersion 54), `CharacterSpec.ForgePersist`, `ForgedCharacters` (`forge_persist`
parse + `IsForgePersistClass` / `IsForgePersistPlayer`), `ForgedForgePower` (`PersistCap`, `Bank`,
`AfterCombatEnd`, a tooltip true in both regimes — loc is baked once at `ModelDb.Init`, so it cannot read the
running class), new `Engine/ForgePersist.cs`; `VOCABULARY.md` (the Run-persistent Forge section + the `forge` op
row), `bts1.py` (VOCAB_VERSION 54), `class_forge.py` (`_FORGE_PERSIST_CAP`, `_validate_forge_persist`, the
assembly carry + the no-income self-heal, the offline forge fake), `census.py` (a class-level `forge_persist`
counter + the AY line), `web/static/app.js` + `style.css` (the class-mechanics chip — no card text says it);
`tests/test_phase_ay.py` (50 checks), suite 403 passed, C# build 0 errors. No card op, no schema change, no
`describe` change. **Pre-existing red left as found:** `test_phase_at` / `test_phase_aw` pin stale prompt-size
ceilings (98,357 and 96,153) that Phase AX already passed; both were failing at AX's commit and still are.

### Phase AZ — New content types (scoping only; each is its own plan)
- **Forged potions** — a `potion_pool` on the character (1–2 potions), spec `{name, emoji, effects[]}` reusing the
  card effect vocab (self/enemy target), runtime `ForgedPotion : BlankTheSpirePotion`
  (`Potions/BlankTheSpirePotion.cs`), pool wiring in `Character/BlankTheSpirePotionPool.cs`. Write
  `PHASE_BA_FORGED_POTIONS_PLAN.md`.
- **Curses / status cards as generated content** — extend card `type` with `curse` (unplayable, ethereal-ish
  drawback) only after Phase AP proves base status cards work. Write a scope note; do not build until a class
  concept demands it (no demand signal in `VOCABULARY_GAPS.md` yet).
- **Events** — no engine surface, no demand signal. Record as "not planned" in `VOCABULARY_GAPS.md` so it stops
  being re-audited.

---

## Cross-cutting mitigations (apply from Wave 0 onward)

- **A "vocab drift" test.** `tests/test_vocab_lockstep.py`: parse `ForgedCards.cs` (`SupportedOps`, `TriggerOps`,
  `SupportedTriggers`, `SupportedOrbs`, `Conditions.Kinds`), `card.schema.json` enums, `VOCABULARY.md` backtick
  tokens, `validator.py` sets, and `exemplar_pool.json` usage; assert set equality (engine ⊆ schema ⊆ vocab, every
  vocab token has an exemplar). This would have caught `random_enemy`, the `hits` guard, the orb enum, and
  `on_blade_played` once_per_turn.
- **A "prompt-vs-vocab" test.** Assert the rendered blueprint/card/relic prompts never contain the phrases
  "not yet", "no conditionals", "does not exist", or a prototype op name.
- **Stale-doc sweep.** `PHASE_L…:7` "STILL OPEN" (relic on_hp_lost), `SPLASH_ART_PLAN.md:15` "PLAN ONLY",
  `class_forge.py:14`: mark LANDED in place so future audits don't re-surface them.
- **Importer version gate** (`BTS1Codec.cs:65-67`) is one-directional. Add a min-version check in the OTHER
  direction only if an older mod build is still in the wild; otherwise document.

---

## Scoreboard

| Wave | Phases | Vocab | Effort | Creative-range gain |
|------|--------|-------|--------|---------------------|
| 0 | W0.1–W0.11 | — | 1–2 days | Highest per hour: the model stops being told features don't exist; exemplars cover every op |
| 1 | AJ, AJ-b | v40 | 2 days | Random-enemy, multi-hit summons, custom-orb engines, correct balance weights |
| 2 | W2.1–W2.4 | — | 2 days | Coverage pushes the model across the whole vocabulary; classes can vary energy and color |
| 3 | AK–AU | v41–v51 | ~1 day each | Attacker riposte, richer engines, five new scales, four new conditions, cost tricks, pile ops, status cards, DoT statuses, orb conditions, relic counters |
| 4 | AV–AZ | v52+ | 1 week+ | Autonomous minions, hybrid classes, cost 4, upgrade-adds-keyword, Forge spend, contagion, run-persistent Forge, potions |

**Recommended order:** Wave 0 in one sitting → AJ + AJ-b → Wave 2 → AK, AL, AM (the three that most widen card
design) → AQ (the most-requested fantasy, burn/DoT) → AS (relics) → the rest of Wave 3 by demand → Wave 4.
