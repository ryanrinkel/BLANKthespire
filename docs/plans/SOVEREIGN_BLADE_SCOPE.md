# Scope — the Sovereign Blade signature token (forge classes)

**Status:** TIER 1 SHIPPED (2026-07-07, vocab v20). **TIER 2 SUPERSEDED by Phase T (2026-07-10, vocab v25)** —
`FORGE_SUMMON_BLADE_PLAN.md` delivered the true base-game blade: NOT in the deck, SUMMONED to hand on your first
Forge (`ForgedForgePower.Stoke`), real `token` rarity, cost 2 / base 10, + a `summon_blade` retrieval op and the
`on_blade_played` Parry trigger. This doc is retained for the Tier-1 history; see that plan for Tier 2. Follow-on
to `PHASE_M_FORGE_PLAN.md` (v19 Forge counter shipped & AutoSlay-verified). **Goal:** give forge classes a
base-game-style *signature blade* — one growing weapon whose damage climbs as you stoke the Forge counter —
instead of scattered `scale:"forged"` payoffs on ordinary cards.

## Tier 1 — what shipped (2026-07-07)
The **Innate Blade**: a forge class ships EXACTLY one reserved attack (`innate` + `retain` + `damage
scale:"forged"`), seeded 1 copy in the starting deck and marked a non-drafted **token**. It opens in hand every
combat, is held until swung, and grows with the Forge counter; it is never offered as a reward/draft nor listed
in the compendium. **Decisions taken:** #1 ship Tier 1 first (this); #2 the blade is the PRIMARY forged payoff
but a class may keep 1 extra `scale:"forged"` card; #3 discard-on-play (Retain only holds it unplayed); #6 base
damage priced low (6→9 upgraded — the Forge counter carries the scaling).

- **Generation** (`class_forge.py`): a new `signature_blade` blueprint role (basic, deck_count 1), SYNTHESIZED
  deterministically (`_synthesize_blade`, like Strike/Defend) so the exact innate+retain+forged shape + the
  `token:true` marker are guaranteed — the blueprint only names/themes it. Prompt (FORGE/SIGNATURE-BLADE block +
  FORMAT + RULES) rewritten to design the blade. Counted in the starting-deck normalization + the cap-guard
  protected set. A **blade-safety net** auto-injects a default blade for any forge class (Forge income present —
  card, trigger, or relic hook) that lacks one. Offline `--fake` forge fake + `_CardFake` forge branch added.
- **Bundle marker**: the blade card carries `"token": true` (schema documents it; `bts1.py`/`ForgedCards.cs`
  VOCAB bumped 19→20 so a v20 blade code isn't silently mis-imported by a v19 mod that would leak it into rewards).
- **Mod**: `CardSpec.IsToken`; `ForgedCards.TryBuildSpec` reads `token`; `DataCard` registers a token card
  `autoAdd:false` + `showInCardLibrary:false` (like an empty slot) — yet it still seeds the starting deck,
  because the deck is built from `starting_deck` slot refs (`ModelDb.Card<T>()`), independent of `autoAdd`.
- **Verified**: full generation test suite (blade shape/text/pairing/validation) + mod build (0 errors) + an
  in-game load — the forge class + `Sovereign Blade` (slot 03, token) registered and embarked cleanly. The
  full-run AutoSlay smoke stalled at the generic `Room type not assigned` map-generation wait (the known
  environmental embark stall / window-foreground focus-throttle — unrelated to the blade); the four blade
  behaviors rest on shipped, already-AutoSlay-verified keywords (innate/retain/forged) + the token flag, whose
  autoAdd:false path is the long-established empty-slot mechanism. NOT yet observed live in combat.

## Why — the gap this closes

Base StS2 Forge is anchored to a **card**: the **Sovereign Blade**, a `Token`-rarity Attack with `Retain`
(`generation/reference/sts2_cards.json:19745-19778`, vars `{Damage:10, CalculationBase:0, CalculationExtra:1,
baseDamage:10}` → damage = `baseDamage + CalculationExtra × Forge`). Regent cards carry a numeric `Forge: N`
(`sts2_cards.json:2889`, Bulwark "Forge 10"); playing them fires `AfterForge(Decimal amount, Player forger, …)`
(`_modref/reflect/dump.txt:1273`) which pumps a counter the blade reads. The base game seeds the blade via a
relic/character-power (NOT in the reflected dump) and/or a card like `SUMMON_FORTH` "Put Sovereign Blade into your
Hand from anywhere" (`sts2_cards.json:21000-21037`).

Our v19 Forge (`ForgedForgePower` + `scale:"forged"`) faithfully reproduces the *number* (verified live in the
gunsmith run: 364 income events, counter 1→199, `forged payoff: damage base 5 + Forge 23`), but there is **no
signature card** — any card can carry `scale:"forged"`, so the identity is diffuse. This scope adds the card.

## Key finding — the mechanic already exists; the gap is *identity + pool membership*

"Starts in hand every combat + retained + grows with Forge" is **fully expressible in the shipped vocab today**:

- `op:"innate"` → `CardKeyword.Innate`, "starts in opening hand every combat" (`DataCard.cs:102`,
  `mod/contract/VOCABULARY.md:18`, `card.schema.json:30`).
- `op:"retain"` → held across turns if unplayed (`DataCard.cs`, `VOCABULARY.md:19`).
- `damage` + `scale:"forged"` → prints `Deal N damage, plus your Forge.` and resolves additively
  (`EffectRunner.cs:75-78`, `cardgen.py:251`, `card.schema.json:35`).

So the blade spec `{"type":"attack","cost":1,"rarity":"basic","effects":[{"op":"damage","amount":N,
"scale":"forged"},{"op":"retain"},{"op":"innate"}]}` **emits and runs today with zero engine or cardgen changes.**
What's missing is everything that makes it a *signature*: forcing exactly one per forge class, marking *which* card
is the blade, and keeping it out of the draft/reward pool. There is **no `token` / not-drafted concept anywhere**
(`bts1.py:83-90` — `cards[]` doubles as pool + starting-deck source; a filled slot defaults `autoAdd:true`,
`DataCard.cs:46`, so any blade leaks into rewards).

This splits the work into two tiers with a real fidelity/cost tradeoff.

---

## Tier 1 — the **Innate Blade** (recommended first step)

The blade is a **deck card**: a reserved forge-class attack = `innate` + `retain` + `damage scale:"forged"`, seeded
**1 copy** in the starting deck, flagged not-drafted. Opens in hand turn 1 of every combat, retains until you cash
it, grows with the Forge counter. **~80% of the base-game feel; no new runtime code, no new op, no combat-start
hook, no codegen bump** (it uses one of the existing 40 pool slots — forge classes use ~27).

**Divergence from base-game:** it lives in the deck — after you play it, it goes to discard and reshuffles like a
normal card (redrawable), and it occupies one deck slot (draws are 1-card diluted). Base-game's blade is a non-deck
Token. Minor in play; note it and judge in playtest.

### T1 build slices

**T1-gen — generation is where most of this lands.**
- **Blueprint role** (`class_forge.py:310-329`): add a `signature_blade` role (or reuse `signature` + a
  `blade:true` marker). Forge classes (forge_ramp as spine OR secondary) must emit **exactly one**. Add it to the
  cap-guard protected set (`class_forge.py:1304`, today `{basic_attack,basic_skill,signature}`) and exempt it from
  the MIN_RARES / merchant-type pool counts (`class_forge.py:664-675`).
- **Emit** (`cardgen.py`): no change — `innate` (`:276-277`), `retain` (`:278-279`), forged damage (`:251`) already
  emit. The blueprint just has to produce the effect list above with `rarity:"basic"`, `deck_count:1`.
- **Validate** (`validator.py` / `character_validator.py`): new rule — a forge class has exactly one card carrying
  `scale:"forged"` + `retain` + `innate`, marked not-drafted. `forge_pairing_warnings`
  (`character_validator.py:147-164`) treats the blade as auto-satisfying the "payoff" half.
- **Prompt** (`class_forge.py:233-243`, the FORGE/SIGNATURE-BLADE block): rewrite to design **the blade** as the
  class's signature payoff (name it, theme it), with forge income feeding it.
- **Bundle marker** (`bts1.py` / assembly `class_forge.py:1313-1355`): add a per-card `"token":true` (schema allows
  it — `card.schema.json:6` `additionalProperties:true`) and/or a `character.signature_card` slot pointer, so the
  mod knows which card is THE blade and to keep it out of rewards.

**T1-mod — one small flag.**
- Honor the `token`/not-drafted flag on `CardSpec`: set `autoAdd:false` + `showInCardLibrary:false` for that card so
  it seeds the starting deck but is never offered as a reward (mirror the `EmptySlot` handling, `DataCard.cs:39-46`).
- (Optional) expose the blade slot on the character for UI/tooltip ("your Sovereign Blade").

**T1-verify:** forge a class, confirm the blade opens in hand turn 1 every combat, retains, grows (`[M] forged
payoff` log climbs), and does **not** appear in card rewards. AutoSlay smoke (window foreground).

**T1 effort:** Small–Medium — generation-heavy, one mod flag, no engine/op/codegen work. Roughly half a Phase-M.

---

## Tier 2 — the **True Token** (full fidelity, gated on a spike)

The blade is a real Token: in hand each combat but **never in the deck** (not shuffled, not drawn, not drafted),
injected fresh at combat start. Matches base-game exactly. Adds genuinely new runtime code to Tier 1.

### T2 build slices (additive to T1)

**T2-mod — the new capability.**
- **New op** `add_card` / `make_card` (or a dedicated blade-seed): an `EffectRunner`/`TriggerRunner` executor that
  resolves the blade's compiled model (`ModelDb.Card<ForgedClassKCardNN>()`, `ForgedClasses.g.cs:453`) and calls the
  **reflected-but-unwrapped** `CardPileCmd.Add(card, PileType.Hand, position, source, skipVisuals)`
  (`dump.txt:523-525`) or `AddGeneratedCardToCombat(...)` (`dump.txt:532`). The `summon` path is the precedent for
  "canonical model → mutable instance → add to combat state" (`EffectRunner.SummonForged`, `EffectRunner.cs:415-441`),
  but it targets the creature system; card-into-hand needs a new wrapper. **The `BetaMainCompatibility` shim today
  exposes only `PowerCmd_.Apply`** — a `CardPileCmd.Add` wrapper is net-new.
- **Combat-start seed:** there is **no `combat_start` trigger** (`RELIC_VOCABULARY.md:49`, `RelicSpec.cs:10-12`,
  `ForgedCharacters.cs:314`). Hang the seed on **turn-1 `turn_start` + `once_per_combat`**, the exact pattern of
  `ForgedRelic.GrantStartCombatBlock` (`ForgedRelic.cs:196`, fired from `AfterPlayerTurnStart` `:113`).
- **Reserved slot:** give the blade a dedicated per-class slot NOT in `starting_deck`. Cleanest is a real reserved
  slot → bump `ForgedCharacters.CardsPerClass 40→41` (`ForgedCharacters.cs:25`) **and regenerate `ForgedClasses.g.cs`
  via `slotgen.py`** (both annotated "keep in sync"). Alternatively reuse a pool slot flagged token + not-in-deck.

**T2-gen:** mark the blade token (not in `starting_deck`, not drafted); the mod seeds it at combat start from the
token flag — no `innate` needed (the seed replaces it).

### T2 risks
- The reflected `CardPileCmd.Add` path is **never called by the mod today** — needs a runtime spike to de-risk:
  `PileType.Hand` enum member is **not in the dump** (resolve at runtime, `dump.txt` only enumerates `CardKeyword`
  at `:741-751`); hand-size cap handling (BaseLib patches `CardPileCmd.Add` for MaxHandSize — behavior on a full hand
  is unverified); card-node visuals (`CreateCardNodeAndUpdateVisuals`, `dump.txt:539`).
- Codegen regen touches generated `ForgedClasses.g.cs` — mechanical but must round-trip through `slotgen.py`.

**T2 effort:** Medium–Large, front-loaded on a ~half-day spike proving `CardPileCmd.Add`-to-hand works from a forged
trigger. If the spike is clean, the rest is wiring.

---

## Design decisions (decide before build)

1. **Tier 1 vs Tier 2** — the main call. Recommendation: **ship Tier 1, playtest, then decide on Tier 2.** Tier 1
   delivers the signature-in-hand-that-grows feel on proven vocab; only build the true-token if the deck-card
   divergence (redrawable, +1 deck slot) actually reads wrong in play.
2. **Blade is the sole forged payoff, or one of several?** Recommend: the blade is the *primary* forged payoff and
   the identity anchor, but classes may keep 1 extra `scale:"forged"` card. (Loosen `forge_pairing` accordingly.)
3. **On-play behavior:** base-game blade → discard on play, `Retain` only holds it *unplayed*. Keep that (no
   auto-return-to-hand). `ModifyCardPlayResultPileTypeAndPosition` (`dump.txt:1353`) could force return-to-hand later
   if desired — out of scope now.
4. **Per-combat reset stays** — matches base-game inference and current behavior (Forge counter dies at combat end).
5. **Do secondary-forge classes get a blade?** (e.g. shipwright = self_sacrifice + forge_ramp.) Recommend yes if
   they ship forged payoffs — the pairing rule already governs forge presence.
6. **Cost/damage tuning:** base Sovereign Blade is 1-cost, 10 base + Forge, Retain. Price the forged base low
   (5–10) since the Forge counter carries the scaling; validator `_score_effect` already prices `forged` payoffs.

## Out of scope
- Run-persistent Forge (base-game blade flavor across a run) — still deferred; per-combat is the model.
- Base-game `AfterForge`/Sovereign-Blade machinery — untouched; ours stays parallel/closed-vocab.
- Blade-specific synergy cards (base-game Parry/Sword Sage/Summon Forth analogues) — future.
