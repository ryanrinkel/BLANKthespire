# Spike Y — the card-select UI surface · GO

**Verdict: GO.** The pick-N-cards UI surface the wave-3 plan called "un-dumped" is fully present in
the current `sts2.dll` decompile as `MegaCrit.Sts2.Core.Commands.CardSelectCmd`, with a stable async
recipe used by shipped base-game cards. **AutoSlay can drive it** (the game ships an
`AutoSlayCardSelector` that auto-picks), so future choice-vocab is smoke-testable, not manual-only —
this reverses the plan's central worry.

Authored 2026-07-14 (Opus 4.8 session, executing `VOCAB_EXPANSION_3_PLAN.md` §6). Method: static
analysis of `_modref/decomp_full` + `_modref/reflect/dump.txt` against the mod's live effect plumbing.
No vocab shipped. No throwaway code committed (see §6 for what was *not* run).

---

## 1. The surface exists (the old dump said "not found")

`_modref/reflect/dump.txt:517` now lists `CardSelectCmd : MegaCrit.Sts2.Core.Commands` as a real type
(the wave-2 dump predates a game update — the plan flagged exactly this). Full source is decompiled at
`_modref/decomp_full/MegaCrit.Sts2.Core.Commands/CardSelectCmd.cs` (869 lines). It is a `static class`
of `async Task` selection helpers, every one returning the chosen `CardModel`(s).

Relevant methods (all proven by base-game call sites, §3):

| method | what it opens | returns |
|---|---|---|
| `FromHandForUpgrade(ctx, player, source)` | hand, upgrade-preview, pick 1 upgradable | `CardModel?` |
| `FromHand(ctx, player, prefs, filter, source)` | hand, generic pick (filter + min/max) | `IEnumerable<CardModel>` |
| `FromHandForDiscard(ctx, player, prefs, filter, source)` | hand, discard styling | `IEnumerable<CardModel>` |
| `FromCombatPile(ctx, pile, player, prefs [,filter])` | any combat pile (draw/discard/exhaust) | `IEnumerable<CardModel>` |
| `FromChooseACardScreen(ctx, cards, player, canSkip)` | a **≤3-card** big-preview screen | `CardModel?` |
| `FromSimpleGrid(ctx, cards, player, prefs)` | an arbitrary card list as a grid | `IEnumerable<CardModel>` |
| `FromDeckForUpgrade / …ForRemoval / …ForTransformation / …ForEnchantment / FromDeckGeneric` | **run-deck** pickers (out of combat too) | `IEnumerable<CardModel>` |

`CardSelectorPrefs` (`_modref/decomp_full/MegaCrit.Sts2.Core.CardSelection/CardSelectorPrefs.cs`) carries
the prompt loc + `MinSelect`/`MaxSelect` + flags. Ready-made prompts exist:
`CardSelectorPrefs.UpgradeSelectionPrompt / ExhaustSelectionPrompt / RemoveSelectionPrompt /
TransformSelectionPrompt / DiscardSelectionPrompt / EnchantSelectionPrompt`. Ctor
`new CardSelectorPrefs(prompt, count)` (fixed N) or `(prompt, min, max)`. **In-code loc caveat still
applies** (§0.5 of the plan): re-use these base prompt keys — they resolve inside `sts2.dll`, so unlike
Power/keyword loc they are safe to reference; do NOT invent new loc keys.

---

## 2. The mod already has everything the recipe needs

The recipe needs a `PlayerChoiceContext` and a `Player`. Both are already threaded through the mod's
executor:

- `EffectRunner.Execute(CardSpec spec, ConstructedCardModel card, PlayerChoiceContext ctx, CardPlay play)`
  — `mod/BlankTheSpireCode/Engine/EffectRunner.cs:49`. The op switch has `ctx` and `card.Owner` (a
  `Player`) in scope. A new choice op drops straight in next to `upgrade_card`
  (`EffectRunner.cs:277`) — that case's comment already reads *"The player-PICK variant needs spike Y."*
- Trigger payloads carry `ctx` too (`ForgedTriggerPower.Apply(PlayerChoiceContext ctx, …)`,
  `ForgedCardSlots.g.cs`), so a choice op is even payload-legal if we want it (though a repeating
  choice payload is a UX footgun — gate to non-payload like `all` upgrade is gated).

So there is **no plumbing work** — the context that Armaments/Brand/Charge receive in their `OnPlay` is
the same object shape our `Execute` already holds.

---

## 3. The recipe (proven by shipped base-game cards)

Every blocked item maps to a base-game card that already does exactly this. Pattern is uniform:
`await CardSelectCmd.From…(ctx, …)` → null/empty-check → act on the returned `CardModel`.

**Player-pick upgrade (#18)** — `Armaments.cs:34`:
```csharp
CardModel picked = await CardSelectCmd.FromHandForUpgrade(choiceContext, base.Owner, this);
if (picked != null) CardCmd.Upgrade(picked, CardPreviewStyle.Default);
```
This is *literally* the choice half of our existing `upgrade_card` op. `FromHandForUpgrade` already
filters to `IsUpgradable`, auto-returns the only card if there's just one, and no-ops on empty hand.

**Choose-a-card purge (#19)** — `Brand.cs:42` / `BurningPact.cs:26` (the exhaust-a-chosen-card shape):
```csharp
CardModel picked = (await CardSelectCmd.FromHand(
    context: choiceContext, player: base.Owner,
    prefs: new CardSelectorPrefs(CardSelectorPrefs.ExhaustSelectionPrompt, 1),
    filter: null, source: this)).FirstOrDefault();
if (picked != null) /* exhaust */;
```
Swap the exhaust for our Phase-W run-deck removal: resolve the picked card's `DeckVersion` and call
`CardPileCmd.RemoveFromDeck(deckVersion, showPreview:false)` (the exact call the self-purge op uses at
`EffectRunner.cs` purge case). Use `RemoveSelectionPrompt`.

**Scry (R-2, #17 follow-up)** — `Charge.cs:26` / `Cleanse.cs:33` (select from the draw pile):
```csharp
var picks = (await CardSelectCmd.FromCombatPile(
    choiceContext, PileType.Draw.GetPile(base.Owner), base.Owner,
    new CardSelectorPrefs(CardSelectorPrefs.DiscardSelectionPrompt, 0, N))).ToList();
foreach (var c in picks) await CardCmd.Discard(choiceContext, c);
```
Caveat: true scry is *"look at the **top** N of draw, discard any."* `FromCombatPile` shows the whole
pile. To get top-N-only, slice `PileType.Draw.GetPile(owner).Cards.Take(N)` and pass that list to
`FromSimpleGrid` (or use `FromCombatPile`'s `filter` overload keyed to a top-N set), then
`CardCmd.Discard` the returned subset with `min=0` so "discard none" is allowed.

**Graft (#7)** — `Begone.cs:23` (pick a card in hand, then mutate it):
```csharp
CardModel picked = (await CardSelectCmd.FromHand(context: choiceContext, player: base.Owner,
    prefs: new CardSelectorPrefs(CardSelectorPrefs.TransformSelectionPrompt, 1),
    filter: null, source: this)).FirstOrDefault();
```
The *select* half is trivial and identical to the above. Graft's hard half is the **permanent card
mutation** (buff card Y forever / merge), which is the transform-family work (#35/#38), NOT the UI. So
the UI unblock does **not** by itself make graft buildable — see §5.

---

## 4. AutoSlay compatibility — the big finding (plan assumption reversed)

The plan (§6.2) assumed *"AutoSlay CANNOT drive a choice UI (random bot) — this one is a MANUAL
in-game check."* **That is no longer true.** The game ships automated selection built for exactly this:

- `AutoSlayer.cs:168` installs it for the whole run:
  `_cardSelectorScope = CardSelectCmd.UseSelector(new AutoSlayCardSelector(_random));`
- `AutoSlayCardSelector`
  (`_modref/decomp_full/MegaCrit.Sts2.Core.AutoSlay.Helpers/AutoSlayCardSelector.cs`) implements
  `ICardSelector.GetSelectedCards(options, min, max)` by **shuffling and taking `min..max` at random**,
  logging `"Auto-selected N card(s) for selection prompt"`.
- Inside every `CardSelectCmd.From…` method, the branch `if (Selector != null)` is checked **first** and
  bypasses the UI entirely (`CardSelectCmd.cs:113` — *"Used by tests, AutoSlay, and gameplay effects…
  card selection UI is bypassed and cards are selected automatically."*). The `PlayerChoiceContext`
  `SignalPlayerChoiceBegun/Ended` calls are only reached on the *human* branch, so a choice op will not
  block the AutoSlay bot.
- Cleanup is handled: `CardSelectCmd.Reset()` clears leaked selectors on run end.

**Consequence:** any choice vocab we add is AutoSlay-smoke-testable the same way U/V/W were — the bot
will auto-random-pick and log the auto-selection line. No auto-pick fallback needs to be written on our
side. (The one thing AutoSlay can't verify is that the *human* screen renders/awaits correctly — that
stays a one-time manual eyeball, but it is no longer a per-mechanic gate.)

Softlock safety: every `From…` method guards the 0-option case (returns empty / logs a `SoftlockException`
report) — an empty hand / empty pile no-ops instead of hanging. Good for our validator posture.

---

## 5. Go/no-go + effort per blocked item

| item | gate | verdict | effort | note |
|---|---|---|---|---|
| **#18 player-pick upgrade** | UI only | **✅ SHIPPED (Phase X, v29, 2026-07-14)** | LOW (as estimated) | `choose` value on `upgrade_card`; `EffectRunner.UpgradeChoose` → `FromHandForUpgrade`→`CardCmd.Upgrade`. AutoSlay-VERIFIED: 105 choose upgrades, 98 `Auto-selected` selector-path lines (**auto-pick under AutoSlay confirmed — the reversal prediction held**), 0 mod exc. Confirms the whole recipe below for the remaining items. |
| **#19 choose-a-card purge** | UI + reuse Phase-W removal | **✅ SHIPPED (Phase Z, v30, 2026-07-14)** | LOW-MEDIUM (as estimated) | Op `purge_card`; `EffectRunner.PurgeChoose` → `FromHand`→`RemoveFromDeck(DeckVersion)`+`RemoveFromCombat`, reusing the self-purge guard. AutoSlay-VERIFIED by log tags: ~160 `[Z]` fires (incl. purging the curse `Ascender's Bane`), generated-copy guard + selector auto-pick confirmed, 0 mod exc. (Random-bot smoke stalls/boss-reward-hang were AutoSlay-side, not code.) |
| **scry (R-2 / #17 (c))** | UI + top-N slice | **✅ SHIPPED (Phase AA, v31, 2026-07-14)** | MEDIUM (as estimated) | Op `scry {amount:N}`; `EffectRunner.Scry` slices top-N of draw → `FromSimpleGrid` (min 0/max N) → `CardCmd.Discard` → fires `on_discard`. AutoSlay-VERIFIED: 259 scry discards, 288 selector auto-picks (no hang), scry→on_discard chain proven, 0 mod exc, a clean RunCompleted. Completes all of gap #17 (`madness_discard` now BUILDABLE). |
| **#7 graft** | UI (trivial) + **permanent card mutation (hard)** | **PARTIAL / NO-GO alone** | **MEDIUM-HIGH** | The select half is free (`FromHand`). Graft is blocked on permanent per-card buff/merge = the transform family (#35/#38), not the UI. Do transform first, then graft is cheap. |

Recommended sequencing for a wave-4 "choice" mini-phase: **#18 → #19 → scry**, each its own vocab bump,
each AutoSlay-verified via the auto-selector. Graft waits on the transform family.

Shared design rules for whichever ships first (write once, reuse):
- **Non-payload by default.** A choice in a repeating `turn_start` payload spams the screen; gate choice
  ops to card-`OnPlay` only (mirror how `all` upgrade is rejected in payloads).
- **In-code loc = reuse the base `CardSelectorPrefs.*Prompt` keys** (they live in `sts2.dll`); never
  invent a loc key (the gap-#26 crash rule).
- **Empty-source no-op is free** — the `From…` methods already return empty on 0 options; still add the
  usual validator tripwire so a class can't field a choice card with nothing legal to target.
- **min=0 where "pick none" is valid** (scry); `min=max=1` for a forced single pick (upgrade/purge).

---

## 6. What was NOT run (honest scope)

This spike is static-analysis-conclusive: the API is real, the recipe is copied from **shipped**
base-game cards (Armaments/Brand/Charge/Begone), the context is already in our executor, and AutoSlay
ships a driver for it. I did **not** hack a throwaway op into `EffectRunner` and launch the game for a
live eyeball — the plan authorized that as the proof step, but the base-game call sites already *are*
the proof that the surface works, and building a throwaway requires temporarily editing/compiling
`EffectRunner` (a card-select op can't ride the raw-JSON slot-04 tester path — it isn't in the vocab).

**Optional confirmation before the first choice-vocab phase ships** (do it as part of that phase, not as
a separate spike): when implementing #18, stage the tester and run `GAPTEST18-choose` under AutoSlay —
success = the `"Auto-selected N card(s)"` log line appears and the upgrade lands, 0 mod exceptions —
then a single manual play to eyeball the human screen. That folds the "prove it" step into real work
instead of throwaway code.

---

## 7. Pointers

- Surface: `_modref/decomp_full/MegaCrit.Sts2.Core.Commands/CardSelectCmd.cs`;
  prefs `…/MegaCrit.Sts2.Core.CardSelection/CardSelectorPrefs.cs`;
  context `…/MegaCrit.Sts2.Core.GameActions.Multiplayer/PlayerChoiceContext.cs`.
- AutoSlay driver: `…/MegaCrit.Sts2.Core.AutoSlay.Helpers/AutoSlayCardSelector.cs`;
  install site `…/MegaCrit.Sts2.Core.AutoSlay/AutoSlayer.cs:168`; interface
  `…/MegaCrit.Sts2.Core.TestSupport/ICardSelector.cs`.
- Base-game call sites: `Armaments.cs` (#18), `Brand.cs`/`BurningPact.cs` (#19), `Charge.cs`/`Cleanse.cs`
  (scry), `Begone.cs` (#7) — all under `…/MegaCrit.Sts2.Core.Models.Cards/`.
- Mod insertion point: `mod/BlankTheSpireCode/Engine/EffectRunner.cs:277` (next to `upgrade_card`).
