# Spike AH-0 — the card-transform surface · GO

**Verdict: GO for Phase AH.** All three unknowns that blocked a `transform_card` spec are answered with a
working recipe, live-verified under AutoSlay (2 valid multi-combat runs, 0 transform exceptions):

1. **Deck permanence** — transforming a played card's `DeckVersion` **permanently** swaps its run-deck
   original; the new card is in the deck next combat, the old one never returns. ✅
2. **In-combat hand transform** — transforming a card sitting in HAND (the clone) visibly becomes the
   new card **in hand, playable this combat**. ✅
3. **Mid-run safety** — generated (`DeckVersion == null`) copies, upgraded originals, and even curses
   (`ASCENDERS_BANE`) all transform or guard-skip cleanly; 0 exceptions across a whole run. ✅

Authored 2026-07-15 (Opus 4.8 session, executing `VOCAB_EXPANSION_4_PLAN.md` §8). Method: decompile
static analysis (`_modref/decomp_full`) + a throwaway `spike_transform` op driven by a slot-04 tester
under AutoSlay. Throwaway C# **reverted before commit** (mod/ clean at HEAD, DLL rebuilt from HEAD);
only this doc + the gap lines are committed. **No vocab shipped.**

---

## 0. The API (decompile-proven)

`_modref/decomp_full/MegaCrit.Sts2.Core.Commands/CardCmd.cs`:

```csharp
// Transform ONE card into a specific replacement (the shape Phase AH wants):
public static async Task<CardPileAddResult?> Transform(CardModel original, CardModel replacement,
                                                       CardPreviewStyle style = HorizontalLayout)   // :348
// TransformTo<T> builds the replacement itself via original.CardScope.CreateCard<T>(original.Owner)  // :335
// TransformToRandom(original, rng, style)                                                            // :323
```

`Transform(original, replacement, style)` funnels into the batch worker `Transform(IEnumerable<CardTransformation>, rng, style)` (:369). Key body facts:

- **It operates on the pile the `original` card is in** — `pile = item.Original.Pile` (:391).
  So passing a **Deck-pile card** (a run-deck original) transforms the RUN DECK; passing a **Hand-pile
  card** (a combat clone) transforms in HAND. There is one method for both — the pile decides.
- **Run-deck branch** (`pile.Type == PileType.Deck`, :427-435): runs `Hook.ModifyCardBeingAddedToDeck`,
  sets `replacement.FloorAddedToDeck`, and records a `CardTransformationHistoryEntry` in the run map
  history. **This is the permanence mechanism** — the replacement is now a real run-deck member.
- **Hand branch** (:462-485): if the added card lands in Hand and `TestMode.IsOff`, it plays the
  `NCardTransformShineVfx` shine animation and `Cmd.Wait(num)`s its duration. Needs `NCard.FindOnTable`
  to resolve the hand node — throws `"Couldn't get hand node"` if the visual node is missing (did NOT
  happen under AutoSlay — the real game window has hand nodes).
- **Assertions that can throw** (all in :386-425): `original.AssertMutable()`; `!original.IsTransformable`
  → InvalidOperationException; `original.Pile == null` → "has no pile"; `replacement == null`;
  `replacement.Owner != original.Owner` → owner-mismatch throw. **These are the guard surface Phase AH's
  `Validate` + runtime null-checks must respect.**
- **Clone-safety (the AG lesson):** the post-transform hooks are `original.AfterTransformedFrom()` /
  `replacement.AfterTransformedTo()` (:449-450) — **virtual methods, not C# events**, so they survive
  `AfterCloned()` (which nulls event fields). No event-on-clone footgun in the transform path.

Base-game callers (all under `.../Models.Cards/`): `Compact.cs`, `Guards.cs`, `PrimalForce.cs` transform
**hand cards** built via `base.CombatState.CreateCard<T>(base.Owner)`; `Begone.cs` transforms a
`FromHand`-picked card; `Charge.cs`/`Seance.cs` use `TransformTo<T>`. **None transform a `DeckVersion`
in combat** — that path (our Q1) is novel, so it needed the live proof below.

`IsTransformable` (`CardModel.cs:739`): `IsRemovable ? true : (pile == null || pile.Type != Deck)` — a
normal removable card is always transformable; a Deck-pile card is transformable when removable.

---

## 1. Q1 — Deck permanence (run-permanent self-transform) · ✅ RECIPE

**Recipe** (mirrors the shipped `purge` op's `DeckVersion` guard at `EffectRunner.cs:194`):

```csharp
var replacement = ForgedCharacters.ResolveClassCardModel(k, targetCardId, owner); // owner-bound copy (Phase Q)
if (replacement != null
    && card.DeckVersion is { } deckCard
    && deckCard.Pile?.Type == PileType.Deck)                     // run-deck original present + in the Deck pile
{
    await CardCmd.Transform(deckCard, replacement, CardPreviewStyle.None);   // run-permanent swap
}
```

**Live evidence** (seed GAPTEST40 + GAPTEST40B; a `spike_transformer` card that transforms its own
DeckVersion into `spike_target` on play, starting-deck ×4):

```
[AH0-Q1] deck transform START: 'BLANKTHESPIRE-FORGED_CLASS04_CARD01' (DeckVersion pile=Deck, transformable=True) -> 'spike_target'.
[AH0-Q1] deck transform DONE: success=True, added='BLANKTHESPIRE-FORGED_CLASS04_CARD02'.
```

Permanence proof — a combat-start run-deck scan (`[AH0-Q1-VERIFY]`, from the relic's turn-1 hook):

```
'spike_target' x0, 'spike_transformer' x4     <- combat 1, turn 1 (before any transform)
'spike_target' x3, 'spike_transformer' x1     <- after 3 of 4 played+transformed
'spike_target' x4, 'spike_transformer' x0     <- all 4 permanently became spike_target
```

Across the whole run the transformed-in `spike_target` **stays in the deck every subsequent combat** and
`spike_transformer` **never reappears**. The in-combat clone the transform is triggered from keeps working
this combat (the `success=True` add lands in a combat pile). **Deck permanence CONFIRMED.**

`CardPreviewStyle.None` chosen to skip the deck-preview UI container (cosmetic; absent/irrelevant under
AutoSlay) — the Deck branch does no VFX regardless (`num` stays 0), so no wait.

---

## 2. Q2 — In-combat hand transform · ✅ RECIPE

**Recipe** (this is the base-game `Compact`/`Begone` shape — transform a Hand-pile card):

```csharp
var handCard = PileType.Hand.GetPile(owner).Cards
    .FirstOrDefault(c => c != null && c != card && c.IsTransformable);
if (handCard != null)
{
    var replacement = ForgedCharacters.ResolveClassCardModel(k, targetCardId, owner);
    await CardCmd.Transform(handCard, replacement, CardPreviewStyle.None);   // becomes the new card IN HAND
}
```

**Live evidence:**

```
[AH0-Q2] hand transform START: 'BLANKTHESPIRE-FORGED_CLASS04_CARD04' (pile=Hand) -> 'spike_target'.
[AH0-Q2] hand transform DONE: success=True, added='BLANKTHESPIRE-FORGED_CLASS04_CARD02', added-pile=Hand, playable=True.
```

`added-pile=Hand, playable=True` on every hand transform (14 in run A, 21 in run B). The new card
materializes in the SAME hand slot and is immediately playable this combat. It even transformed
`ASCENDERS_BANE` (a curse) in hand without incident. **In-combat hand transform CONFIRMED.**

**Consequence for Phase AH:** a `transform_card` op can transform BOTH the run-deck original (permanence)
AND this combat's in-hand clone (immediate effect) in one play — so the card visibly becomes the new card
THIS combat *and* the run deck is permanently rewritten. (For the self-transform v1, the played card is
already leaving play; the "combat clone" half is only relevant if you want the change felt before the next
draw — the deck half alone gives next-combat permanence.)

---

## 3. Q3 — Mid-run safety / guards · ✅ RECIPE

**Guard = the exact `DeckVersion` null-check the `purge`/`purge_card` ops already ship.** A generated copy
(from `add_card`) has `DeckVersion == null`, so the deck transform is skipped (combat-only) and nothing
faults:

```
[AH0-Q3] guarded skip: 'BLANKTHESPIRE-FORGED_CLASS04_CARD01' has no run-deck original (generated copy / DeckVersion null) — deck transform skipped.
```

18 (run A) / 20 (run B) guarded skips fired — one per played `add_card`-generated transformer token, all
clean. Upgraded originals (the tester ran an `upgrade_card cards:"all"` card so hand clones were upgraded
before transform) also transformed with no `AssertMutable`/mutability throw.

**Exception tally across both valid runs:**

| tag | run A | run B |
|---|---|---|
| `[AH0-Q1] deck transform DONE` | 3 | 6 |
| `[AH0-Q2] hand transform DONE` | 14 | 21 |
| `[AH0-Q3] guarded skip` | 18 | 20 |
| `[AH0-Q1-EXC]` / `[AH0-Q2-EXC]` / `[AH0-Q1-VERIFY-EXC]` | **0 / 0 / 0** | **0 / 0 / 0** |
| mod-frame exceptions (`BlankTheSpire` in stack) | **0** | **0** |

**Mid-run safety CONFIRMED.** The guards Phase AH needs are already precedented (the Phase-W `purge`
null-DeckVersion shape). Additional Phase-AH-only guards (all `Validate`-time, cheap): target must be a
same-class card that exists (reuse `ResolveClassCardModel`'s resolution, which no-ops on unknown ids);
no transform chains (target may not itself carry `transform_card` — the Phase-Q depth-1 precedent);
never in a trigger payload (card-OnPlay only); ⊥ `purge` on the same card.

---

## 4. Animate / hang under AutoSlay

- **Does it animate?** Yes for the HAND branch: AutoSlay sets only `NonInteractiveMode.AutoSlayerCheck`,
  NOT `TestMode`, so `TestMode.IsOff` is TRUE and the `NCardTransformShineVfx` shine + `Cmd.Wait(num)`
  path runs on hand transforms. The DECK branch has no VFX (`num` stays 0). No `"Couldn't get hand node"`
  errors — the real game window (AutoSlay is not truly headless) has the hand nodes the VFX needs.
- **Does it hang?** No. Both valid runs auto-played through many combats (Elite/Event/RestSite/Boss rooms)
  with transforms firing on nearly every turn. There was ONE self-resolving in-combat watchdog blip
  (`[Watchdog] No progress for 5.1s (last: Combat turn 2)`) on a heavy-transform turn — it recovered on
  its own (combat continued to turn 8). No terminal in-combat stall.
- **The card-select driver** (`Auto-selected …`) logged 18×, unrelated to transform (from the tester's
  `upgrade_card`) — confirms the AutoSlay harness was live.
- **The only terminal failure was the known boss-reward hang, NOT transform.** Both runs ended with
  `Finished Boss room` → `Rewards screen did not appear after combat` — the pre-existing
  **boss-reward-rarity soft-lock** (see MEMORY `boss-reward-rarity-hang`; a forged class stalls at the
  boss reward when no Rare is available). Combat completed and every transform resolved BEFORE the stall;
  no C# exception, no transform in the failing frame. This is a harness/known-bug outcome that does not
  gate the spike.

---

## 5. Go/no-go + effort for Phase AH

**GO.** The transform primitive is real, permanent, in-combat-capable, AutoSlay-safe, and its guards are
already precedented in shipped ops. No dead-ends.

| unknown | verdict | recipe |
|---|---|---|
| Q1 deck permanence | **✅ GO** | `CardCmd.Transform(card.DeckVersion, ResolveClassCardModel(k,id,owner), None)` under the `purge` DeckVersion guard |
| Q2 in-combat hand transform | **✅ GO** | `CardCmd.Transform(handCard, ResolveClassCardModel(...), None)` — base-game Compact/Begone shape |
| Q3 mid-run safety | **✅ GO** | reuse the `purge`/`purge_card` null-`DeckVersion` guard; 0 exceptions across a full run incl. curses + upgraded + generated copies |
| animate/hang | **✅ no hang** | hand VFX runs (TestMode off) but does not stall; only the unrelated boss-reward known-bug failed the runs |

**Effort re-estimate for Phase AH: MEDIUM (was scouted MEDIUM-HIGH — de-risk it down).** The runtime is a
~15-line executor built entirely from proven pieces (`CardCmd.Transform` + `ResolveClassCardModel` + the
`purge` guard), no new plumbing. The bulk of the 2-3 day estimate is the generation-side lockstep the
plan already specs — `Validate` chain-guard + `card_id` resolution, `card.schema.json`, `cardgen.describe`,
`validator.py`, `bts1.py` v38, blueprint/archetype `metamorph` entry, `tests/test_phase_ah.py`, catalog
BUILDABLE flips — plus the AutoSlay gate (already proven drivable here). **The one live risk the spike
retires** (deck permanence + hand transform + null-DeckVersion) is gone; what remains is deterministic
generation wiring. Keep the 3-seed all-aggression Gap Tester (`GAPTEST35/35B/35C`) as specced — but note
the boss-reward known-bug will red-flag full-run seeds; judge by `[AH] transform_card` tags + 0 mod
exceptions, not the tool verdict (same posture as spikes W/Z/AA).

**Validator note discovered during the spike:** the existing `Validate` rule "`'card_id'/'pile' only apply
to add_card`" (`ForgedCards.cs:809`) rejects `card_id` on any other op — Phase AH must add `transform_card`
to that allow-list (I did this temporarily for the spike op; it's reverted). Same for the trigger-side rule
at `:975` if `transform_card` were ever payload-legal (it should NOT be — card-only).

---

## 6. What was run (scope)

- **3 AutoSlay runs** (seeds GAPTEST40, GAPTEST40, GAPTEST40B): run 1 was INVALID (the spike op's `card_id`
  hit the `add_card`-only validator rule → transformer slot rejected → op never ran) — this itself surfaced
  the §5 validator note. After allowing `card_id` on the spike op, runs 2+3 were valid and answered every
  question. Both valid runs failed ONLY at the boss-reward known-bug, after all transforms resolved.
- **Throwaway code** (all reverted, mod/ clean at HEAD, DLL rebuilt from HEAD): a `spike_transform` op in
  `EffectRunner.Execute` (+ `SpikeTransform` method) keyed to a `card_id`; whitelist/no-var/validator
  entries in `ForgedCards.cs` + `DataCard.cs`; a `[AH0-Q1-VERIFY]` run-deck scan in
  `ForgedRelic.AfterPlayerTurnStart` (+ a temporary `DataCard.SpecId` accessor).
- **Tester** (slot-04, restored to the prior Tempersmith Tester afterward): 4× `spike_transformer`
  (transforms own DeckVersion + a hand card into `spike_target`), 1× `add_card` generator (null-DeckVersion
  Q3 case), 1× `upgrade_card cards:"all"` (upgraded-original Q3 case), 4× aggression filler.

## 7. Pointers

- Transform API: `_modref/decomp_full/MegaCrit.Sts2.Core.Commands/CardCmd.cs:323-509`.
- Base-game callers: `Compact.cs`, `Guards.cs`, `PrimalForce.cs`, `Begone.cs`, `Charge.cs`, `Seance.cs`
  (all `.../Models.Cards/`).
- `IsTransformable`/`DeckVersion`: `.../Models/CardModel.cs:739`, `:929`.
- Mod insertion point for Phase AH: `EffectRunner.cs` op switch (next to `purge` at `:185`); guard
  precedent `purge` `:194` + `purge_card` `:551`; replacement builder
  `ForgedCharacters.ResolveClassCardModel` `:84`.
