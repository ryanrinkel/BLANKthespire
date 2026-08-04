# Phase J — Forged Statuses (custom, generated status effects / Powers) — PLAN

Status: **✅ SHIPPED END-TO-END — reconciled 2026-06-27.** J-2 (generator) is live — `class_forge.py` declares a
class `status_pool` and the LLM forges custom statuses. The v9→v10 website redeploy noted below is long superseded:
the live site now ships vocab **v17**. Original J-1/J-2 status preserved below.

ORIGINAL STATUS: **J-1 ENGINE BUILT + DEPLOYED + VERIFIED IN-GAME 2026-06-17. Vocab v10. NEXT = J-2 (open to the LLM
contract). NOT in the LLM contract yet.** User confirmed Razor Focus (damage_dealt), Brittle (damage_taken
debuff), Quickstep (card_draw + lose_one_eot decay) and Ironweave (block_gained) all work — the unverified
`Modify*`/transform/decay conventions are CORRECT. (`energy_gain` shares card_draw's path; untested but expected OK.)

## J-1 — what shipped (engine only; mirrors H3/I)
- **Hooks (MVP additive set, all owner-gated):** `damage_dealt` (`ModifyDamageAdditive`, +stacks delta when
  `dealer==Owner`), `damage_taken` (`ModifyDamageAdditive`, `target==Owner`), `block_gained`
  (`ModifyBlockAdditive`, `target==Owner`), `energy_gain` (`ModifyEnergyGain`), `card_draw` (`ModifyHandDraw`).
  The two `*Additive` hooks return the BONUS DELTA (game sums returns + base, per the spike); the bare transform
  hooks (`ModifyEnergyGain`/`ModifyHandDraw`) are handed the running value and return `value + stacks`.
  **⚠️ Only `ModifyDamageAdditive` is spike-verified — the other 4 conventions are J-1's in-game test target.**
- **SCOPE CUT vs the hook table:** `hit_count` (`ModifyAttackHitCount`) is **DEFERRED** — `AttackCommand` exposes
  no clean dealer accessor, so a player hit-count buff couldn't be kept from boosting enemy attacks. `mode`
  multiplicative is **DEFERRED** (validator accepts `additive` only). Both are J-3/J-2-follow-up.
- **Decay** (`AfterTurnEnd`, gated to `Owner.Side`): `none`; `lose_all_eot` → `Owner.RemovePowerInternal(this)`;
  `lose_one_eot` → mutate `this.Amount-=1` (Amount HAS an accessible setter — confirmed at build) +
  `Owner.InvokePowerModified(this,-1,false)` to refresh, remove at 0.
- **Files:** new `Engine/StatusSpec.cs`, `Engine/IForgedStatusHost.cs`, `Powers/ForgedStatusPower.cs` (base +
  `Modify*` hooks + decay + emoji-icon loc + `(k,m)` registry + abstract `ApplyStacks` supplied by the leaf).
  Edits: `CharacterSpec` (`+StatusPool` init prop), `ForgedCharacters` (parse `status_pool` ≤4, validate
  hook/decay/mode/side/dup, `IsStatusClass`/`StatusSpecFor`/`ResolveStatusInstance`), `CardSpec` (`EffectSpec
  +StatusName`), `EffectRunner` (`apply_status_custom`: buff→self, debuff→card target(s) via `GetTargets`),
  `DataCard` (no-var case), `ForgedCards` (op + AmountOps + parse `status_name` + class-only validate + Describe
  fallback + `VocabVersion=10`), `slotgen.py` (`STATUSES_PER_CLASS=4` → `ForgedClassKStatusM` shells + leaf
  `IForgedStatusHost`/`StatusClass`; regen `ForgedClasses.g.cs` = **232 types**), `MainFile` (kick emoji per pool).
- **Test class STAGED to slot 04** (overwrote The Juggernaut; backed up to `generation/scratch/_backup_class04/`
  + recoverable from `the_juggernaut.btsc.txt`): **"The Bladedancer"** (HP75, status_pool = Razor Focus
  🗡️/damage_dealt, Ironweave 🛡️/block_gained, Brittle 💔/damage_taken-debuff, Quickstep 🌀/card_draw+lose_one_eot),
  13 cards. Staging script `generation/scratch/stage_phase_j_statuses.py`.
- **USER VERIFY:** quit+relaunch → pick The Bladedancer → Whet then Strike (6→8, Razor Focus delta on attacks) →
  Steel Up then Defend (5→7, Ironweave on block) → Expose's Brittle on an enemy makes the next hit land harder
  (debuff target + ModifyDamageAdditive on the enemy) → Flurry shows Razor Focus adds to EACH hit → Quickstep
  boosts NEXT turn's hand draw then loses 1 stack/turn (card_draw transform + decay) → emoji renders as both the
  status text glyph AND the on-creature icon badge (the .res trick) → reward pool offers only Bladedancer cards.
  Watch `%APPDATA%\SlayTheSpire2\logs\godot.log` for Modify*/InvokeGeneric/RemovePower exceptions and whether
  any hook double-applies or no-ops (the unverified-convention risk). **NEXT after verify:** J-2 (open to the LLM).

---

## J-2 — opened to the LLM generator (DONE + REAL-LLM VALIDATED 2026-06-17; AWAITING IN-GAME VERIFY + WEBSITE REDEPLOY)
Generation-side (one small C# lockstep rebuild for Describe). Edits: **`card.schema.json`** (`apply_status_custom` op
+ `status_name` field + required rule), **`VOCABULARY.md`** (op row + "Forged statuses (a CLASS IDENTITY)" section:
status_pool, the 5 hooks + required side, decay), **`cardgen.py`** (`effect_literal` emits
`new EffectSpec("apply_status_custom", N, StatusName:"…")`; `describe` keys verb off the card TARGET — self→"Gain",
enemy→"Apply"), **`ForgedCards.Describe`** (same target heuristic — lockstep), **`validator.py`**
(`CardValidator(extra_statuses=…)`; `apply_status_custom` ∈ `_BUILD_AROUND_OPS` + scored; `_engine_structural_errors`
checks status_name membership against the class pool → class-only), **`bts1.py`** VOCAB_VERSION 9→10, **`class_forge.py`**
(blueprint "THE STATUS POOL" section + format/RULES; `_validate_status_pool` mirror; `_status_pool_custom_names` →
validator; `_card_uses_custom_status` drop-safety; assemble `status_pool` into character; offline fake STATUS class +
`_CardFake` apply_status_custom branches). **Fixed a latent Windows bug:** `contract.py`/`character_contract.py` read
VOCABULARY with the cp1252 default codec → crashed on the new emoji; now `encoding="utf-8"`.
- **Card-text limitation (cosmetic, lockstep both sides):** describe keys "Gain" vs "Apply" off the card's `target`,
  so a SELF-BUFF applied by an ENEMY-target attack (e.g. an attack that also grants you Precision) mis-reads as
  "Apply N Precision" — the MECHANIC is correct (buff still lands on self), only the wording. A real fix needs the
  class status side (buff/debuff) + emoji threaded into Describe (it currently has no class context per-card); follow-up.
- **Validated:** schema valid + accepts the op; **303 generation tests pass** (127 validator + 104 character + 72 relic,
  0 failed); offline fake STATUS forge → 0 skips, status_pool round-trips at v10; cardgen literal+describe == C# by
  construction. **REAL forge (Anthropic .env key):** **"The Duelist"** (HP70, 14 cards, **0 rejected**) — the LLM
  invented a 3-status pool: **Precision** (damage_dealt buff), **Resolve** (block_gained buff), **Brittle**
  (damage_taken debuff, `lose_one_eot`) — and wired En Garde/Masterstroke (gain Precision+Resolve), Cripple/Expose/
  Flurry/Shattering Lunge (apply Brittle). BTSC round-trips at v10. Code `scratch/the_duelist.btsc.txt`; **staged to
  class slot 04** (overwrote the J-1 Bladedancer, re-stageable via `stage_phase_j_statuses.py`; Juggernaut backup in
  `scratch/_backup_class04/`).
- **REMAINING:** (1) user in-game verify The Duelist (select slot 04 → its custom statuses apply + work, reward pool
  clean); (2) **website redeploy** v9→v10 (scp `generation/btsgen`+`mod/contract` → DO droplet `/opt/btsweb` →
  `systemctl restart btsweb`; outward-facing — confirm first). After that Phase J is fully shipped end-to-end and
  [[creative-harness-vision]]'s last axis (a class that invents its own STATUSES) is realized.

---

Original feasibility note: **Feasibility CONFIRMED by an explore spike (2026-06-17) — see `custom-status-spike` memory.**
The spike (still in the tree, execution-only, NOT in the LLM contract) proved the two hard parts: a player-applied
custom `PowerModel` receives the **`Modify*` return-value hooks** mid-combat, and an **emoji** can be both the status
TEXT and the on-creature ICON. Spike files: `Powers/SpikeSharpenPower.cs`, `Engine/EmojiIconRenderer.cs`, op
`apply_custom` (test cards `forged/cards/27.json` + `28.json`).

The third and last unbuilt piece of the [[creative-harness-vision]] north-star: after orbs (a class invents its own
**elements**, Phase I) and triggers (a class builds its own **engines**, H3), forged statuses let a class invent its
own **status identities** — the signature buff/debuff a whole archetype is built around. Reuses the H3/I architecture
almost wholesale (a behaviour bound to a compiled shell, read from a class-level spec, run from a restricted vocab).
Build via [[sts2-mod-toolchain]]; sits alongside [[vocab-expansion-f]] vocab.

## Feasibility — CONFIRMED (spike, in-game verified 2026-06-17)
- **A custom status = a `CustomPowerModel`** (via the existing `Powers/BlankTheSpirePower : CustomPowerModel` base),
  same shape as `ForgedTriggerPower` (H3) and `ForgedOrb` (I): auto-registers (ICustomPower scan, no MainFile change),
  in-code `Localization` (return a **`PowerLoc(Title,Description,SmartDescription)`** — `BaseLib.Abstracts`), path-based
  icon (`CustomPackedIconPath`/`CustomBigIconPath`).
- **The MODIFIER family is the genuinely new capability** — return-value `Modify*` hooks no base power exposes
  generically. **`ModifyDamageAdditive` confirmed firing on a player power.** Full surface (reflect dump §11):
  `ModifyDamageAdditive/Multiplicative`, `ModifyBlockAdditive/Multiplicative`, `ModifyEnergyGain`, `ModifyMaxEnergy`,
  `ModifyHandDraw`, `ModifyAttackHitCount`, `ModifyXValue`, … = "while active, change a number."
- **⚠️ `Modify*Additive` returns the BONUS DELTA, not the new total** (game does `base + return`). Confirmed: returning
  `amount + Amount` made a 6 hit deal 15; returning `Amount` deals 9. So contribute just the bonus, `0m` otherwise.
  Gate on `dealer/target == Owner` — **`PowerModel.Owner` is a `Creature`** (has `.Player`/`.Side`), NOT a Player.
  Hooks fire MANY times per event (preview + intent + actual); each call is an independent eval (pure modifiers are
  idempotent, so this is fine; reactive payloads with side effects must NOT live on a per-eval hook).
- **Apply a custom power with a literal amount** (no card var) via the H3 path:
  `BetaMainCompatibility.PowerCmd_.Apply.InvokeGeneric<Task<T?>,T>(null, ctx, owner.Creature, (decimal)amt, owner.Creature, (CardModel?)null, false)`
  (`BetaMainCompatibility` ∈ `BaseLib.Utils`). Stacking via `PowerStackType.Counter`/`Single`; buff/debuff via `PowerType`.
- **EMOJI display — BOTH work:**
  - **Text:** put the emoji straight in the `PowerLoc` strings; the tooltip font renders it (🗡️ verified).
  - **Icon badge:** powers take a PATH icon only (no procedural sprite hook like orbs). A runtime `user://` **raw PNG
    does NOT load** (ResourceLoader needs a `.import` → the "purple blob" fallback). **THE FIX (verified): render the
    glyph to an `Image` via an off-screen `SubViewport`+`Label` with `C:/Windows/Fonts/seguiemj.ttf`
    (`FontFile.LoadDynamicFont`), make an `ImageTexture`, save it as a NATIVE `.res` via `ResourceSaver.Save` (loads at
    runtime, no import metadata), point `CustomPackedIconPath` at the `user://*.res`.** `EmojiIconRenderer` already does
    this for one hardcoded key — Phase J generalizes it to one `Kick(name, emoji)` per status.

## The constraint (same Q1/Q2 as cards/triggers/orbs)
One power = one compiled .NET Type, registered at init, frozen. So forged statuses are **data-driven shells** — a fixed
pool of generic `CustomPowerModel` subclasses, each reading a status-spec from JSON — exactly like `ForgedCardSlotNN` /
`ForgedTriggerPowerNN` / `ForgedClassKOrbM`.

---

## Two families (the design axis)
| Family | Mechanism | "While active, …" | Phase J |
|---|---|---|---|
| **Modifier** | `Modify*` return-value hooks | *…change a number* (deal/take ±dmg, +block, +draw, +energy, +hits) | **MVP (the gap)** |
| **Reactive** | `After*`/`Before*` event hooks + payload | *…when X happens, do Y* | **deferred** (J-3) — turn_end/turn_start already exist as `add_trigger` (H3) |

**The MVP targets the MODIFIER family only** — it's the missing capability and does NOT overlap `add_trigger`. Reactive
forged statuses (J-3) are a later generalization of triggers to more hooks, and are where the iconic *retaliate/Thorns*
case lives (needs the hook's context creature as target — the real reason to do it).

## The class status pool — modality system (mirror Phase I orbs)
A custom status is a class-level identity applied by multiple cards (an **orb**, not a per-card trigger). So statuses
are **strictly class-specific** (never global), and each class declares a **`status_pool`** — `0–4` custom status defs.
Cards apply a status **by lowercased name**. Buff statuses land on the player (self), debuffs on the card's target
(reuse `EffectRunner.SelfBuffStatuses` as the single source of truth for side, like every other status). Modalities:
- **none:** `status_pool: []` — a class that only uses base-game statuses (today's behaviour).
- **mixed:** base-status cards + a couple of signature custom statuses.
- **all-custom:** a class whose identity is its invented buffs/debuffs.

## Architecture (mirror H3 triggers / I orbs)
1. **`Engine/StatusSpec.cs`** (new record):
   ```
   StatusSpec { Name, Emoji, Description?, Type: buff|debuff, Stack: counter|single,
                Decay: none|lose_all_eot|lose_one_eot,
                Hook: damage_dealt|damage_taken|block_gained|energy_gain|card_draw|hit_count,
                Mode: additive|multiplicative }
   ```
   Rides the class: `CharacterSpec += StatusPool` (init prop, NOT positional — avoids the dup-member pitfall hit in I).
2. **`ForgedCharacters`** reads `"status_pool"` from `user://forged/characters/KK.json`:
   ```json
   "status_pool": [
     { "name":"Razor Focus", "emoji":"🗡️", "type":"buff", "stack":"counter",
       "hook":"damage_dealt", "mode":"additive" }
   ]
   ```
   Add `IsStatusClass(K)`, `StatusSpecFor(K,m)`, `StatusPoolNames(K)`, `ResolveStatusType(K, name)` (name→`ForgedClassKStatusM`
   Type), plus validation (known hook/mode, buff↔debuff side, ≤4 custom, dup names, sane bounds).
3. **`Powers/ForgedStatusPower.cs : BlankTheSpirePower`** — hand-written base. Reads its `StatusSpec` (null on an unfilled
   shell → harmless zero-modifier no-op, like the empty orb/trigger shells). Overrides EVERY supported `Modify*` hook,
   but each returns its bonus ONLY when `spec.Hook` matches and `dealer/target == Owner` (delta convention above; `0m`
   otherwise). `Type`/`StackType` from spec. `Decay` implemented in `AfterTurnEnd` (lose 1 / lose all) **if** no native
   decay flag exists (verify first). `Localization` = `PowerLoc(emoji+name, description, …)`. Icon =
   `EmojiIconRenderer.IconPath(name)` (`.res`), fallback to base placeholder.
4. **Generated shells (slotgen):** per class K, `ForgedClassKStatusM : ForgedStatusPower` (M = 1..4), each
   `protected override StatusSpec? Source => ForgedCharacters.StatusSpecFor(K, M)` and a `static (k,m)->instance` registry
   → `TypeForKey(k,m)` (so `ForgedCharacters.ResolveStatusType` maps name→Type without referencing generated symbols).
   Estimate ~96 shells (mirror `ORBS_PER_CLASS` → `STATUSES_PER_CLASS = 4`); regen `ForgedClasses.g.cs`.
5. **Card op `apply_status_custom`** (`EffectSpec += StatusName`; or reuse `Status` + a flag). The card leaf is
   `IForgedStatusHost` (carries `StatusClass => K`, the `IForgedOrbHost`/`IForgedTriggerHost` pattern). `EffectRunner`:
   resolve `StatusName` → Type via `ResolveStatusType(K, name)`, side from `SelfBuffStatuses`-equivalent (spec.Type),
   apply N stacks via the proven `InvokeGeneric` literal path. Validator-gated to class cards (a non-status-class card
   can't apply a custom status). `DataCard` needs a `case "apply_status_custom": break;` (no card var) — it has a
   `default: throw`.
6. **`EmojiIconRenderer` generalization:** at init, iterate every class `status_pool` and `Kick(name, emoji)` each;
   `IconPath(name)` per status. (Already built for one key — just loop the pool + key by status name.)
7. **Vocab version → 10.** Touchpoints (the house lockstep): `CharacterSpec`/`ForgedCharacters` (status pool),
   `Engine/StatusSpec.cs`, `Powers/ForgedStatusPower.cs`, `EffectRunner` (apply_status_custom + class resolver),
   `IForgedStatusHost`, `ForgedCards` (parse/validate/Describe + `VocabVersion=10`), `DataCard` (no-var case),
   `slotgen.py` (status shells + host wiring), the contract (`card.schema.json`/`VOCABULARY.md`), `cardgen.py`
   (status describe — lockstep with `ForgedCards.Describe`), `validator.py`, `bts1.py`, `class_forge.py` (blueprint
   declares the class's `status_pool`), the `character_*` import path.

## Modifier hook vocabulary (MVP)
Each custom status names ONE hook + mode. Value = stacks (additive) or a per-stack factor (multiplicative).
- **damage_dealt** — `ModifyDamageAdditive` (+stacks per hit; Strength-like) / `ModifyDamageMultiplicative`.
- **damage_taken** — `ModifyDamageAdditive`/`Multiplicative` on incoming (Frail/armor-like; gate `target == Owner`).
- **block_gained** — `ModifyBlockAdditive` (+block when you gain block; Dexterity-like).
- **energy_gain** — `ModifyEnergyGain` (+energy per turn).
- **card_draw** — `ModifyHandDraw` (+cards drawn).
- **hit_count** — `ModifyAttackHitCount` (+hits on multi-hit attacks).
Numbers fire every relevant event → the validator enforces sane caps (small additive stacks; tight multiplicative range).

## MVP cut & sequencing (house pattern)
- **J-1 (engine):** `StatusSpec` + `ForgedStatusPower` shell + class `status_pool` + the additive modifier hooks +
  decay + emoji icons (the `.res` generalization). Hand-author a test class (e.g. **"The Bladedancer"**: Razor Focus =
  damage_dealt additive buff; Ironweave = block_gained additive buff; a debuff like Brittle = damage_taken additive on
  enemies). **Stage → user verifies in-game** (each hook lands the right delta, decay/stacking correct, emoji text +
  badge render, reward pool clean). **NOT in the LLM contract.**
- **J-2 (generator):** open `status_pool` to the LLM — `card.schema.json` (`apply_status_custom` op + a
  `$defs/customStatus` enforcing hook/mode/side), `VOCABULARY.md`, `cardgen.py` mirror (lockstep `Describe`),
  `validator.py` (hook/amount/dup/side rules + `apply_status_custom` is class-only + a build-around op so it's not
  flagged flat-rare), `bts1.py` v10, `class_forge.py` blueprint modality ("a class built around one signature status"),
  fake + real forge one class per modality → **website redeploy** (the v9→v10 jump; outward-facing — confirm first).
- **J-3 (reactive, later):** generalize `add_trigger` to more hooks (`on_attack`/`on_damage_taken`/`on_card_played`)
  with **targeted reactive payloads** using the hook's context creature (true Thorns: on_damage_taken → hit the
  attacker). Multi-eval guarding required. This is the reactive family's real payoff.

## Decisions (taken for J-1)
1. **MVP family = MODIFIER only;** reactive deferred to J-3 (no overlap with existing `add_trigger`). ☑
2. **Statuses are class-level** (`status_pool`, ≤4 custom), applied by name; shared-pool inline statuses deferred. ☑
3. **Side** (buff→self / debuff→target) from the spec's `type` (custom statuses carry their own buff/debuff). ☑
4. **Decay** supported (none / lose-all-EOT / lose-one-EOT) — manual in `AfterTurnEnd` (no native flag found;
   `RemovePowerInternal` for all, `Amount-=1`+`InvokePowerModified` for one). ☑
5. **Emoji** is the default status art (text + `.res` icon); real per-status art deferred to [[assets-todo]]. ☑
6. **`STATUSES_PER_CLASS = 4`** (= `ForgedCharacters.MaxCustomStatuses`). ☑
7. **CUT for J-1:** `hit_count` deferred (no clean `AttackCommand` dealer gate); `mode` multiplicative deferred
   (additive only). Both are follow-ups once their conventions are spiked in-game. ☑

## Risk notes
- **Return-value conventions per hook:** only `ModifyDamageAdditive` is spike-verified. **Spike each remaining hook**
  (`ModifyBlockAdditive`, `ModifyEnergyGain`, `ModifyHandDraw`, `ModifyAttackHitCount`, and BOTH `*Multiplicative`)
  before exposing — additive almost certainly returns a delta; multiplicative/count conventions are unknown. Trust the
  dll dump (§11 signatures) over assumptions (the H3/I lesson).
- **Decay mechanism:** confirm whether `PowerModel`/`PowerStackType` has native per-turn decay before hand-rolling it;
  check how base `VulnerablePower`/`WeakPower` decrement.
- **Hook multi-fire:** fine for pure modifiers (idempotent); a hard reason reactive payloads stay OUT of the MVP.
- **Icon timing/caching:** the badge is requested mid-combat (well after the init render completes), so the `.res` is
  ready; confirm the game doesn't cache the first (placeholder) icon before the power is first applied.
- **Generator steering:** the modifier/reactive spec is more abstract than orbs — the `class_forge` blueprint must push
  the LLM toward ONE coherent signature status per archetype, not arbitrary hook+number combos. Keep the data-only
  safety model: every forged status re-validates against the live interpreter vocab, never executed as code.
