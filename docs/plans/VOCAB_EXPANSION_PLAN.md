# BLANK the spire — Vocabulary Expansion Plan (Phase F: breadth → Phase G: orbs)

Status: **✅ F1–F5 SHIPPED — reconciled 2026-06-27.** Everything here shipped except **F4** (choice / card-ref),
which remains deferred. Vocab has advanced well past this plan (now **v17**). Original status preserved below. —
Author path stays the same (forge → validate → codegen → build →
deploy → restart). Everything here ships as **compiled vocabulary** in the C# `EffectRunner`/`DataCard`, with
the JSON contract + validator kept in lockstep. Each addition bumps `ForgedCards.VocabVersion` (was **2** when this
plan was written; now **v17**).

Grounded in live reflection of `sts2.dll` (`_modref/reflect/dump.txt`) — every type/method named below was
verified present. Note: `CommonActions` is a **BaseLib** helper (not in `sts2.dll`); the raw STS2 paths
(`DamageCmd`, `OrbCmd`, `CardCmd`, `CardPileCmd`) are what it wraps and what we drop to when no wrapper exists.

---

## The per-addition checklist (the "unit cost")
Every new op or status touches the same 7 places. Keeping them in lockstep is the whole discipline:

1. `mod/.../Engine/EffectRunner.cs` — execution (a switch arm).
2. `mod/.../Engine/DataCard.cs` — declaration (a `With*` builder so tooltip/preview/upgrade work).
3. `mod/.../Engine/ForgedCards.cs` — `SupportedOps`/`SupportedStatuses`(+`AmountOps`) + `Describe()` text + bump `VocabVersion`.
4. `generation/btsgen/cardgen.py` — mirror `describe()`.
5. `mod/contract/VOCABULARY.md` — the table the LLM reads.
6. `mod/contract/card.schema.json` — op/status enum + any new field.
7. `mod/contract/statuses/<name>.json` (statuses only) + a test card staged to `%APPDATA%\SlayTheSpire2\forged\cards\NN.json`.

**Design fix applied once, up front:** today "is this status a self-buff or a target-debuff?" is decided in
two places independently (`EffectRunner.ApplyStatus` picks `ApplySelf` vs `Apply`; `Describe` picks "Gain" vs
"Apply"). Before adding 11 statuses, introduce **one** source of truth — a `SelfBuffStatuses` set — that both
read. Prevents drift.

---

## Phase F1 — Status roster breadth  (effort: LOW, risk: LOW)
`apply_status` already maps a string → `WithPower<T>` + `Apply<T>`/`ApplySelf<T>`. Adding a status is pure
mapping. All 11 below are confirmed `PowerModel` subclasses in `MegaCrit.Sts2.Core.Models.Powers`.

| status | PowerModel | side | notes |
|---|---|---|---|
| `thorns` | `ThornsPower` | self | retaliate when hit |
| `regen` | `RegenPower` | self | heal each turn |
| `metallicize` | `PlatingPower` | self | Block each turn (no STS2 "PlatedArmor" — this is it) |
| `artifact` | `ArtifactPower` | self | negate next N debuffs |
| `buffer` | `BufferPower` | self | prevent next N HP-loss instances |
| `intangible` | `IntangiblePower` | self | all damage → 1 for N turns. **Gate to rare; cap small.** |
| `ritual` | `RitualPower` | self | +Strength each turn. **Strong — rare-leaning.** |
| `blur` | `BlurPower` | self | Block persists N extra turns (Defect's Blur) |
| `temp_strength` | `TemporaryStrengthPower` | self | Strength that expires (drawback-free burst) |
| `temp_dexterity` | `TemporaryDexterityPower` | self | Dexterity that expires |
| `barricade` | `BarricadePower` | self | Block never expires. **Flag-like** — apply `amount:1` by convention |

- Debuffs (`vulnerable/weak/frail/poison`) already cover the generic enemy-side menu; no new debuffs in F1.
- **Text wart preserved:** status lines render as "Gain Thorns." / "Apply Vulnerable." without the stack
  number (current behavior — the power's own tooltip shows the count). Optional polish later: inject the
  `{StatusVar}` placeholder. Not in scope for F1.
- **Test card:** one card per status staged to slots, verified via dev console `card BLANKTHESPIRE-FORGED_CARD_SLOTNN`.
- **VocabVersion → 3.**

## Phase F2 — Card-keyword ops  (effort: TRIVIAL, risk: LOW)
`exhaust` already proves the pattern: a flag op declared as `WithKeyword(CardKeyword.X)`, no execution. The
enum (`MegaCrit.Sts2.Core.Entities.Cards.CardKeyword`) has exactly: `None, Innate, Retain, Ethereal, Exhaust,
Eternal, Sly, Unplayable`. Add the three that make sense on forged cards:

| op | maps to | meaning |
|---|---|---|
| `innate` | `CardKeyword.Innate` | starts in opening hand |
| `retain` | `CardKeyword.Retain` | not discarded at end of turn |
| `ethereal` | `CardKeyword.Ethereal` | Exhausts if still in hand at end of turn |

- Each is one `case` in `DataCard.DeclareEffects`, one no-op `case` in `EffectRunner.Execute`, plus
  contract/schema/`SupportedOps`. No `AmountOps` entry (flags). **VocabVersion → 4** (or fold into F1's bump).

## Phase F3 — Structural-lite: multi-hit + X-cost  (effort: MEDIUM, risk: MEDIUM)
These are the first two ops that **break the flat-scalar model**, so they cost more — but both have native STS2
support and unlock a lot of card identity. Do them together since both touch damage/cost wiring.

- **Multi-hit.** Add an optional `hits` field to a `damage` effect. Execution leaves the canonical
  `CommonActions.CardAttack` path and uses the raw builder confirmed in the dump:
  `DamageCmd.Attack(perHit).WithHitCount(n).Targeting(...).FromCard(card).Execute(ctx)`, feeding the card's
  `Damage` var as `perHit`. Schema: `hits` (int ≥2, optional). Describe: "Deal {Damage} damage N times."
- **X-cost.** Allow `cost: "X"`. Native on `CardModel`: `HasEnergyCostX` + `int ResolveEnergyXValue()`
  (resolves to current energy at play). `CardSpec.Cost` becomes `int?`/sentinel for X; affected effect amounts
  read the resolved X at play time instead of a fixed amount. Schema: `cost` accepts `"X"`; an effect may set
  `"amount": "X"` to scale. Describe: "Deal {Damage}×X..." / "Draw X cards."
- **Why MEDIUM:** changes `CardSpec` (cost type + per-effect amount source), the damage execution path, and
  preview/upgrade text. Validator + both `describe()`s must learn the new fields. Worth it; just not "free."
- **VocabVersion → 5.**

## Phase F4 — Choice/card-ref manipulation  (effort: MEDIUM, **STRETCH / likely defer**)
`CardCmd`/`CardPileCmd` expose scry-style filtering, discard, exhaust-chosen, and add-card-to-pile — but most
need either a **player choice UI flow** or a **card-id reference** (e.g. "add a Wound"), which is more than a
data op. Recommend deferring until after orbs unless a specific card wants one. Candidates if pursued:
`discard` (random, no UI), `add_status_card` (Wound/Dazed/Burn by model id via `CardPileCmd.AddGeneratedCardToCombat`).

---

## Phase G — Orbs vertical (the flagship "hack")  (effort: MEDIUM–HIGH, risk: MEDIUM)
The orb API is **complete and generic** (not a stub): base `OrbModel`; concrete
`Lightning/Frost/Dark/Plasma/GlassOrb` (`...Models.Orbs`); `FocusPower`; and the command surface
`OrbCmd.Channel(ctx, orb, player)` / `Evoke` / `EvokeNext` / `AddSlots(player, n)` / `Replace`. The work is
**not** the API — it's that orbs only mean something as a **class identity**. So Phase G is a vertical that
plugs into the existing class-bundle system (Phase B), not a loose set of card ops.

New ops (cards):
| op | maps to | params |
|---|---|---|
| `channel_orb` | `OrbCmd.Channel` | `orb`: lightning/frost/dark/plasma/glass |
| `evoke` | `OrbCmd.EvokeNext` / `Evoke` | (count) |
| `gain_orb_slot` | `OrbCmd.AddSlots` | `amount` |
| `apply_status: focus` | `FocusPower` (self) | `amount` (scales orb output) |

Class plumbing (the real lift):
- **Starting orb slots** belong to the character, not a card — set on the forged `PlaceholderCharacterModel`
  (extend `CharacterSpec`/`ForgedCharacters` with an `orb_slots` field, applied at combat start).
- A forged class can then **be an orb class**: starter deck channels/evokes; Focus scales it.
- Verify the **orb HUD renders** for a non-Defect modded character (the one real unknown — needs an in-game
  check, since orbs may be wired to the Defect character's scene). Spike this first.
- Contract gets an `orbs` section; the blueprint generator (`class_forge.py`) learns the orb archetype so the
  website can forge a coherent orb class end-to-end.

**Sequencing:** F1 → F2 → F3, then a small **orb HUD spike** before committing to full Phase G.

---

## Phase F5 — Retain-payoff archetype: state scalars + retain conditions  (effort: MEDIUM, risk: MEDIUM)
<!-- STATUS: DONE 2026-06-19 (vocab v14). Built ALL THREE tiers (scalars cards_in_hand/cards_retained/
     unspent_energy_last_turn on damage/block/draw; when conditions hand_size_ge + retained_last_turn;
     add_trigger payloads may scale:cards_retained). Engine built clean + deployed; generation lockstep done;
     311 generation tests pass; test cards staged to forged slots 31-37. In-game verify pending. Infra:
     `EffectSpec.ScaleX` (bool) → `Scale` (string?), shared `EffectRunner.ScaleValue`, `HandStateTracker` +
     two Harmony patches (`Hook.BeforeHandDraw` pre-draw snapshot, `CombatManager.DoTurnEnd` energy). -->

<!-- Renumbered from "Phase L" 2026-06-19 to free that letter for the forge-axis PHASE_L_FORGED_RELICS_PLAN.md;
     this is a structural-op addition, so it belongs in the F (breadth/structural) family alongside F3. -->

Surfaced by the **creative-harness run** on the chosen build "Blade Adept" (Agility + Retain) 2026-06-19:
the class's keystone fantasy — "reward for cards you HELD / Retained, scale off how much you coiled" — is
currently inexpressible (see `VOCABULARY_GAPS.md` #5). The engine already has the right shape: a state-scalar
mechanism (`from_state`, e.g. Body Slam's "damage = your Block") plus `scale:"x"`. This phase extends that
family with hand/retain state, plus retain-aware `when` conditions.

| addition | maps to / mechanism | meaning |
|---|---|---|
| `scale`/`from_state` value `cards_retained` | count of cards held into this turn (hand pile minus this turn's draws) | "Deal/Block/Draw N per card retained" |
| `scale`/`from_state` value `cards_in_hand` | current hand-pile size | hand-size payoff |
| (optional) `unspent_energy_last_turn` | energy tracked at end of last turn | reward deliberate under-spend |
| `when` condition `retained_last_turn` | per-card-instance flag: was this card in hand at end of last turn | on-hold card bonus ("if retained, costs 0 / +dmg") |
| `when` condition `hand_size_ge` (`value`) | hand-pile count | "if hand ≥ N" |
| `add_trigger` payload reads `cards_retained` | per-turn amount source | flat ramp → true "hold more, hit harder" engine |

- **Why MEDIUM:** extends `CardSpec` (new scalar source + condition kinds), the `from_state` execution path, and
  both `describe()`s + validator + schema. `retained_last_turn` is the priciest bit — it needs a per-card-instance
  "was held" flag tracked across the end-of-turn boundary.
- **Payoff:** unlocks the *entire* Retain archetype (a recurring STS identity), not a single card. Touches the
  standard 7-place checklist; bump `VocabVersion`.
- **Sequencing:** independent of orbs/statuses/summons; can slot in whenever a Retain-flavored class is wanted.

## Test & verify (every phase)
- Build: `$env:DOTNET_ROOT="%USERPROFILE%\.dotnet"; %USERPROFILE%\.dotnet\dotnet.exe build <proj>` (DLL is
  locked while the game runs — restart required to reload).
- Stage hand-written test cards to `%APPDATA%\SlayTheSpire2\forged\cards\NN.json`, quit+relaunch, add via dev
  console (` ` toggles it): `card BLANKTHESPIRE-FORGED_CARD_SLOTNN`. Watch `%APPDATA%\SlayTheSpire2\logs\godot.log`.
- Then a real LLM forge against the grown contract to confirm the model uses the new vocab coherently.

## Open decisions for you
- **F1 scope:** all 11 statuses, or trim the strong ones (intangible/ritual/barricade) for a first pass?
- **F3 now or later:** fold multi-hit/X-cost into the breadth pass, or ship F1+F2 first and treat F3 as its own step?
- **Orb HUD spike:** want me to do the in-game orb-rendering spike before fully planning Phase G?
