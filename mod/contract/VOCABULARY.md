# BLANK the spire — Card Effect Vocabulary (constrained)

This is the **complete** set of mechanics the mod's C# interpreter (`EffectRunner`) can execute today.
Compose cards ONLY from these. Anything outside this list cannot be played and will be rejected by the
validator. (The vocabulary grows as the interpreter grows — more ops/statuses are coming.)

## Effect ops
| op             | params            | meaning |
|----------------|-------------------|---------|
| `damage`       | `amount` (int ≥1), optional `hits` (int ≥2) | Deal `amount` attack damage to the card's target(s). Routed through Strength/Weak/Vulnerable/Block by the engine. Add `hits` to make it **multi-hit**: deal `amount` damage `hits` times (e.g. `amount:4, hits:3` = "Deal 4 damage 3 times"). At most one multi-hit effect per card. Add `unblockable` (`"unblockable": true`, v44) and the hit **ignores Block** entirely ("Deal 9 damage, ignoring Block." — Strength/Vulnerable still apply; card-level only, never in a trigger payload; price it above a plain hit, uncommon/rare). |
| `block`        | `amount` (int ≥1) | Gain `amount` Block (always on the player, regardless of the card's target). |
| `draw`         | `amount` (int ≥1) | Draw `amount` cards. |
| `apply_status` | `status`, `amount`| Apply `amount` stacks of a status to the card's target(s) (buffs go on the player, debuffs on enemies — see Statuses). |
| `gain_energy`  | `amount` (int ≥1) | Gain `amount` energy this turn. |
| `heal`         | `amount` (int ≥1) | Heal the player `amount` HP. |
| `lose_hp`      | `amount` (int ≥1) | The player loses `amount` HP (ignores Block; a self-cost, not an attack). |
| `gain_max_hp`  | `amount` (int 1–5) | **Gain `amount` Max HP** for the rest of the run AND heal that much (the base-game **Feed** payoff; v44). A run-permanent stat, so it is **rare-tier**: uncommon/rare only, 1–3 typical, usually on an `exhaust` attack so it fires once; card-only (never in a trigger payload). |
| `exhaust`      | *(none)*          | This card Exhausts when played (removed from the deck for the rest of combat). A card property, not a targeted effect. |
| `innate`       | *(none)*          | This card starts in your opening hand every combat. A card property (no targeted effect). |
| `retain`       | *(none)*          | This card is NOT discarded at end of turn — it stays in your hand. A card property. |
| `ethereal`     | *(none)*          | If this card is still in your hand at end of turn, it Exhausts. A card property. |
| `purge`        | *(none)*          | **Purge** — when this card is played, it is removed from your **run deck for the rest of the run** (permanent deck-thinning; a stronger `exhaust` that never comes back). A card property. **Mutually exclusive with `exhaust`** (a card can't do both). **Never on a BASIC card.** Put it on a strong one-shot skill/attack you're happy to spend once to thin toward a lean engine (1–3 per class). A generated copy of a purge card (from `add_card`) just vanishes for the combat — it isn't in your run deck to remove. |
| `purge_card`   | *(none)*          | **Choose-a-card Purge** — when this card is played, **YOU pick a card in your hand and purge THAT card** (removed from your run deck for the rest of the run). The player-choice form of `purge`: instead of the played card removing itself, it lets you thin a *chosen* target — great for cutting a Basic/Curse/dead card you drew. Carries no amount/target. Empty hand = harmless no-op. Put it on a skill/attack (1–2 per class). A chosen generated copy (no run-deck original) just vanishes for the combat. |
| `forge`        | `amount` (int ≥1) | **Forge N** — stoke your **Forge** counter by `amount` (a stacking power; it resets each combat unless the class sets `forge_persist` — see Run-persistent Forge). Cash it with a `scale:"forged"` payoff (see Scaled amounts — the pairing is required both ways). Income also works inside `add_trigger` payloads ("At the start of your turn, Forge 2") — see Triggers. |
| `spend_forge`  | `amount` (int 1–10) | **Spend N Forge** (v53) — CONSUME that much of your per-combat Forge counter as this card's **price**; the rest of the card is what the Forge buys. The cash-out half of the ramp: a burst that empties the counter instead of riding the slow payoff. Gate the payoff with `when` `forged_ge` so it never fires on an empty counter, and put that gate FIRST with the `spend_forge` LAST — effects resolve top-to-bottom, so a gate after the spend would read the counter this card just emptied (the validator rejects that order). Spending more than you hold just empties it — weak, never broken. Never a card's only effect, never on a BASIC, one per card, card-only. **FORGE-CLASS ONLY.** |
| `spread_debuffs`| *(none)* | **Contagion** (v53) — copy EVERY debuff on the struck target (Vulnerable / Weak / Frail / Poison, at their current stack counts) onto **all other living enemies**. Needs a chosen target, so **single-enemy cards only** (`target: "enemy"`). The payoff of a debuff deck against a crowd: stack the debuffs on one enemy, then spread them. Pair it with a debuff EARLIER on the same card so it is never dead; an undebuffed target / a lone enemy is a harmless no-op. Never on a BASIC, one per card, card-only; uncommon/rare. |
| `channel_orb`  | `orb` (lightning/frost/dark/**random**), optional `amount` (count) | Channel an orb into your next open slot. `orb:"random"` rolls one of lightning/frost/dark — **independently per orb** when `amount > 1`, so a multi-channel "pull" can come up all-matching (the slot-machine jackpot). **ORB-CLASS ONLY** — see Orbs below. |
| `evoke`        | optional `amount` (count) | Evoke (trigger + consume) your oldest orb(s) now. **ORB-CLASS ONLY.** |
| `gain_orb_slot`| `amount` (int ≥1) | Gain `amount` orb slots this combat. **ORB-CLASS ONLY.** |
| `add_trigger`  | `trigger` (turn_end/turn_start/ripen/on_hp_lost/on_exhaust/on_card_played/on_card_drawn/on_damage_dealt/on_block_gained/attacked/on_discard/on_blade_played), `effects` (1+), optional `when`, optional `once_per_turn` or `once_per_combat`, `amount` (ripen only) | Grant an ongoing power that runs its `effects` payload: every turn (turn_end/turn_start), ONCE after `amount` turns (ripen), or REACTIVELY on an event (on_hp_lost / on_exhaust / on_card_played / on_card_drawn / on_damage_dealt / on_block_gained / attacked). Payload is SELF/orb-only unless an effect carries a `target` (see Triggers below). Best on `power`-type cards. **Exception — `on_discard`** is CARD-LATENT (Reflex, see Triggers): it grants NO power on play; its payload fires when THIS card is DISCARDED BY AN EFFECT. |
| `apply_status_custom` | `status_name`, `amount` | Apply `amount` stacks of one of the class's OWN custom statuses (by name). Also legal inside `add_trigger` payloads (v42 — the signature status as a per-turn engine: "At the start of your turn, gain 1 Razor Focus"; a custom DEBUFF in a payload takes a `target`). **STATUS-CLASS ONLY** — see Forged Statuses below. |
| `summon`       | `summon_name`, optional `amount` (HP) | Summon the class's OWN minion (by name) at `amount` HP, OR — if it's already out — raise its Max HP by `amount` (base-game Osty Summon keyword). One per class; passive bodyguard. **SUMMON-CLASS ONLY** — see Forged Summons below. |
| `summon_attack`| `amount` (per-hit), optional `hits` (≥2) | Deal `amount` damage **through your summon** (it's the attacker, scaling with its Strength); no-op if the summon isn't out. Also legal inside `add_trigger` payloads (v42 — the minion acting on its own each turn: "At the end of your turn, deal 4 damage 2 times with your summon"; a payload `target` picks enemy/all_enemies/attacker, default the first enemy). **SUMMON-CLASS ONLY** — see Forged Summons below. |
| `buff_summon`  | `amount`, optional `status` (self-buff, default `strength`) | Buff your living summon (e.g. Strength so its `summon_attack`s hit harder); no-op if the summon isn't out. Also legal inside `add_trigger` payloads (v42 — "At the start of your turn, your summon gains 1 Strength"). **SUMMON-CLASS ONLY** — see Forged Summons below. |
| `heal_summon`  | `amount` (int 1–9) | Heal your living summon `amount` HP (the selfless "medic" op — spend a card to keep your bodyguard alive); no-op if the summon isn't out. Also legal inside `add_trigger` payloads (a per-turn medic engine: "At the start of your turn, heal your summon 3"). **SUMMON-CLASS ONLY** — see Forged Summons below. |
| `shield_summon`| `amount` (int 1–12) | Grant your living summon `amount` Block; no-op if the summon isn't out. Also legal inside `add_trigger` payloads. **SUMMON-CLASS ONLY** — see Forged Summons below. |
| `sacrifice_summon` | *(none)* | **Sacrifice your summon** (v52) — consume your front-most living minion: it dies, so its pool `on_death` rattle fires. A **price**: the rest of the card is the payoff (10+ Block, 12+ damage, or 2 draws + energy). Never a card's only effect, never on a BASIC, one per card, card-only. No summon out = no-op. **SUMMON-CLASS ONLY**. |
| `add_card`     | `card_id` (a card in THIS class's own set), `pile` (hand/discard/draw), optional `amount` (copies, 1–3, default 1) | Generate `amount` **combat-transient copies** of one of your class's OWN cards into a pile (the base-game "add a card to combat" — the copies vanish at combat end, never enter your deck). May reference itself (Anger). The referenced card must NOT itself `add_card` (depth-1 loop discipline). Also legal inside `add_trigger` payloads — the compost loop ("Whenever a card is Exhausted, add a copy of X to your discard pile"). **CLASS-ONLY.** |
| `discard`      | `amount` (int ≥1), optional `cards` (random/choose) | Discard `amount` cards from your hand — `random` (default; choiceless churn) or **`choose`** (v46: YOU pick which to pitch — "Discard 1 card of your choice."; pitch the Reflex card on purpose). Pairs with the `on_discard` trigger and works inside `add_trigger` payloads ("At the start of your turn, discard 1" — **payloads are `random` only**). Discarding is an EFFECT: it triggers `on_discard` cards; end-of-turn cleanup does NOT. |
| `retrieve_card`| `pile` (discard/exhaust), `cards` (random/choose), optional `amount` (1–2) | **Return a card from your discard or exhaust pile to your hand** (v46 — Headbutt / Exhume): `choose` opens the pile and you pick ("Return a card of your choice from your discard pile to your hand."), `random` pulls blind; `pile:"exhaust"` brings back a SPENT card (price it higher; pair with a strong `exhaust` one-shot). Status/Curse cards never return; empty pile = no-op. Card-only; one per card; 1–2 per class. |
| `add_status_card`| `card` (dazed/wound/burn), `pile` (hand/discard/draw), optional `amount` (1–3) | **Add base-game STATUS cards to your own deck as a price** (v46 — Wild Strike / Power Through / Overclock): "Add a Wound to your discard pile." / "Add 2 Dazed to your draw pile." **Wound** = unplayable dead draw; **Dazed** = dead draw that Exhausts itself at end of turn; **Burn** = 2 damage to you if in hand at end of turn. Combat-transient. Only to make an OVER-STATTED card honest (a 1-cost 12-damage attack), never a stat line. Card-only; never on a BASIC; one per card; at most two such cards per class. |
| `scry`         | `amount` (int ≥1) | **Scry `amount`** — look at the top `amount` cards of your DRAW pile and discard any of them you choose (keep the rest on top, in order). A draw-quality filter: dig past dead cards toward what you need, and *fuel discard payoffs* — a scry-discard triggers `on_discard` cards just like `discard` does. Great on the discard/`on_discard` archetype. Typical values 2–5. Card-only (not a repeating-trigger payload). |
| `corruption`   | *(none)*          | **Corruption** — while active this combat, **your Skills cost 0 but Exhaust when played** (the base-game Corruption power; the reckless-tempo engine). A flag-op granting a binary per-combat power (no stacking). Put it on a **POWER or SKILL** card (never an Attack). Card-only (never in a trigger payload). **At most one per class.** Pairs with Skill density + `on_exhaust` payoffs (Feel No Pain / Dark Embrace) — the exhausting free Skills feed the exhaust engine. |
| `cost_shift`   | `card_type` (attack/skill/power/all), `amount` (int 1–2), `scope` (this_turn/combat), optional `count` (int 1–3) | **Cost Shift** (v45) — your cards of that type cost `amount` less energy: `scope:"this_turn"` = until the end of this turn ("Your Attacks cost 1 less this turn."); `scope:"combat"` = for the rest of the combat (**rare-only**, amount 1, at most one such card per class — "Your Skills cost 1 less this combat."). Add `count` N to discount only the NEXT N such cards you play ("Your next Skill costs 2 less this turn." — count 1 + amount 2 makes a 2-cost Skill free). Never below 0; X-cost cards are unaffected; `all` = your Attacks, Skills and Powers (a Status/Curse is never discounted); stacks with other discounts. Card-only (never in a trigger payload); at most one per card. The lighter cousin of `corruption` — a typed discount with no Exhaust tax. |
| `balance_step` | `pole` (light/dark), `amount` (int 1–5) | **Shift N toward the Light/Dark** — move your per-combat **Balance** gauge, a SIGNED counter (Light and Dark are opposite ends; 0 = centered; resets each combat). Read the gauge with the `light_ge` / `dark_ge` / `centered` conditions (see Conditions). Income also works inside `add_trigger` payloads ("At the start of your turn, shift 2 toward the Dark"). The gauge **BITES at the extremes**: while |gauge| ≥ 8, each turn-start the leaning pole penalizes you — the Dark drains 3 HP, the Light inflicts 1 Weak. **BALANCE-CLASS mechanic:** a class using `balance_step` needs income on BOTH poles AND at least one pole/`centered`-gated payoff — a one-pole gauge is just Forge with extra steps. Never sprinkle a lone balance card. |
| `blade_empower`| `amount` (int 2–3) | **Blade Empower ×N** — for the rest of THIS turn, your signature blade deals `amount` TIMES its damage (a burst spike distinct from the slow Forge ramp; re-applying refreshes, cleared at the start of your next turn). Only multiplies the blade token (not other `scale:"forged"` payoffs). **FORGE-CLASS ONLY** (needs a signature blade + forge income); put it on a **skill/power**; card-only (never in a trigger payload). |
| `transform_card`| `card_id` (a DIFFERENT card in THIS class's own set) | **Transform** — when this card is played, it **PERMANENTLY becomes `card_id` for the rest of the run** (the base-game Transform: the run-deck original is swapped, so it's the new card in every later combat; this combat's in-hand copies swap too). The self-rewrite / mode-swap primitive: a weak card that **ranks up** into a strong one (pair it with a `when` gate — "transforms once you've forged enough"), or a two-card **mode-swap** where two cards each `transform_card` into the other (A↔B — a stance/weapon-mode toggle). Rules: the target must be a **different** same-class card (never itself); **no chains** (the target may itself carry `transform_card` ONLY if it swaps back to this card — A↔B is fine, A→B→C is not); **never on a BASIC card**; **mutually exclusive with `purge`**; at most one per card; card-only (never in a trigger payload). Keep it to **1–3 per class**. **CLASS-ONLY.** |
| `graft_card`   | `card_id` (a card in THIS class's own set) | **Graft** — the CHOOSE form of `transform_card` (as `purge_card` is the choose form of `purge`). When this card is played, **YOU pick a card in your HAND and THAT picked card PERMANENTLY becomes `card_id` for the rest of the run** (the run-deck original is swapped + the picked hand copy transforms now, so the change is felt this combat). A targeted transform — cut a Basic/dead draw and reforge it into one of your strong cards. Rules: the target is a same-class card; **never on a BASIC card**; **mutually exclusive with `purge`/`purge_card`**; at most one per card; card-only (never in a trigger payload); counts toward the **1–3 per class** transform-family cap (shared with `transform_card`). **CLASS-ONLY.** (Under AutoSlay the hand picker auto-picks; empty hand / no selection is a harmless no-op.) |
| `summon_blade` | (none) | **Put your signature blade into your hand from anywhere** (the base-game Summon-Forth pattern) — retrieves your growing blade from your draw/discard/exhaust pile, or creates it if it isn't in combat yet. Takes no amount. Also legal inside `add_trigger` payloads. **FORGE-CLASS ONLY** (the blade-retrieval half of blade manipulation — see the Forge archetype). |
| `upgrade_card` | `cards` (random/all/choose) | **Upgrade cards in your hand for the rest of this combat** (the Armaments fantasy) — `random` upgrades ONE random upgradable card in your hand, `all` upgrades EVERY upgradable card in hand (Armaments+), `choose` lets YOU pick one upgradable card in hand (the true Armaments feel). Takes no amount. **COMBAT-SCOPED** (base-StS convention): the upgrade lasts this combat only — your run deck is untouched. Already-upgraded / non-upgradable cards are skipped; upgrading nothing is a harmless no-op. `random` is also legal inside `add_trigger` payloads — but the payload form is **`random` only** (`all` every turn is degenerate; `choose` would spam the pick UI). Pair with **retain** or big hands so an upgraded card sticks around to matter. |

## Effect order is a design lever
A card's `effects` resolve **strictly top-to-bottom**, each one fully before the next. Order is therefore part of the
design, not cosmetic — use it deliberately:
- Put an amplifying debuff/buff **before** the damage it should boost to amplify *this* card's hit, e.g.
  `[apply weak/vulnerable, damage]` or `[apply strength, damage]` → the listed damage benefits immediately.
- Put it **after** the damage to set up *future* turns instead (often the more interesting choice — a punchy hit now,
  then Vulnerable that pays off on your next attacks): `[damage, apply vulnerable]`.
Both are valid; pick the ordering that matches the card's intent, and let the card text (which is written in this same
order) read the way it actually plays.

## Statuses (for `apply_status`)
Every status takes an `amount` (the number of stacks). DEBUFFS go on the card's target(s) — use them on
`enemy`/`all_enemies` cards. BUFFS always land on **YOU** regardless of the card's `target`, so a buff can
ride any card (e.g. an attack that also grants you Block-over-time).

| status          | kind   | meaning |
|-----------------|--------|---------|
| `vulnerable`    | debuff | Target takes +50% attack damage (decays each turn). |
| `weak`          | debuff | Target deals −25% attack damage (decays each turn). |
| `frail`         | debuff | Target gains −25% Block from cards (decays each turn). |
| `poison`        | debuff | Target loses that many HP at the start of its turn, then the stack drops by 1. |
| `strength`      | buff   | +`amount` damage per attack hit. Permanent. |
| `dexterity`     | buff   | +`amount` Block gained per Block effect. Permanent. |
| `temp_strength` | buff   | Like `strength` but only for this turn (a safe burst with no lasting power). |
| `temp_dexterity`| buff   | Like `dexterity` but only for this turn. |
| `temp_thorns`   | buff   | Like `thorns` but only for this turn (v44 — a one-turn bristle: the riposte window without a permanent Thorns ramp). |
| `thorns`        | buff   | When an enemy attacks you, it takes `amount` damage back. Permanent. |
| `regen`         | buff   | Heal `amount` HP at the end of your turn (typically decays). |
| `metallicize`   | buff   | Gain `amount` Block at the end of every turn, then lose 1 stack at the start of each of your later turns (STS2 **Plating**: `amount` N yields N + (N-1) + … + 1 Block over N turns, NOT a permanent per-turn engine — it decays by one per turn, not when hit). |
| `artifact`      | buff   | Negate the next `amount` debuffs applied to you. |
| `buffer`        | buff   | Prevent the next `amount` instances of HP loss. |
| `blur`          | buff   | Your Block is NOT removed at the start of your next `amount` turn(s). |
| `intangible`    | buff   | Reduce ALL damage you take to 1 for `amount` turn(s). Very strong — rare-tier, keep `amount` tiny (1). |
| `ritual`        | buff   | Gain `amount` Strength at the end of every turn. Snowballs hard — rare-tier. |
| `barricade`     | buff   | Your Block is never removed (it persists between turns). A toggle — use `amount: 1`. |
| `focus`         | buff   | +`amount` to the value of every orb you channel (Lightning damage, Frost Block, Dark hit). **ORB-CLASS ONLY.** |
| `temp_focus`    | buff   | Like `focus` but only for this turn (v44 — boosts this turn's evokes AND the end-of-turn passives, then expires). **ORB-CLASS ONLY.** |
<!-- metallicize is implemented as PlatingPower (EffectRunner.cs:832 / TriggerRunner.cs:192 / DataCard.cs:199). Semantics verified 2026-09-09 against the decompiled PlatingPower.cs: +Amount Block at end of turn (BeforeSideTurnEndEarly); -1 stack at each player turn start after turn 1 (AfterSideTurnStart -> Decrement); no decay on being hit. -->

> `vulnerable`/`weak` are the most generic debuff filler and `strength`/`block`-shaped buffs the most generic
> buff filler — but prefer a card whose identity is a distinct shape (poison, thorns, metallicize/block-engine,
> intangible/ritual payoff, etc.). `intangible`, `ritual`, and `barricade` are powerful build-defining buffs:
> reserve them for `power`-type cards and the `rare` tier, with small numbers.

**Two of the same status on one card** (v53): a card normally declares each value once (one damage, one block, one
Weak…). The one exception is `apply_status`: you may apply the SAME status TWICE when the **second one is
`when`-gated** — the printed amount, then a conditional bonus ("Apply 2 Weak. Apply 2 Weak if the target has Block.").
An ungated pair is rejected (that should just be one bigger number), and a third copy is always rejected.

## Targeting (`target` field)
| target        | meaning |
|---------------|---------|
| `enemy`       | A single player-chosen enemy. |
| `all_enemies` | Every enemy (AoE). |
| `self`        | The player (use for pure skills like block/draw). |
| `random_enemy`| A **random** living enemy — the base-game Ricochet / Bouncing Flask feel. **Each damage HIT and each status effect rolls its own random enemy** (a multi-hit `damage` sprays; a following `apply_status` may land on a different enemy). Because there is no chosen target, a random_enemy card may NOT carry `when:target_has_status` or `scale:target_debuff_count`. Text reads "… to a random enemy". Great for chaos/gambler/scatter fantasies and as a cheap AoE-ish rider; keep it off precision ("follow-up") designs. |

## Structural mechanics (multi-hit & scaled amounts)
- **Multi-hit:** add `hits` (int ≥2) to a `damage` effect → it deals `amount` damage `hits` times
  (e.g. `{ "op":"damage", "amount":4, "hits":3 }` = "Deal 4 damage 3 times"). At most one per card. The
  per-hit damage is `amount`; an upgrade can raise either the per-hit damage or the hit count. Also legal (v42)
  on a trigger-payload `damage` / `summon_attack` ("Whenever you are attacked, deal 2 damage 3 times to the attacker").
- **Rampage (`grow`):** add `grow` (int 1..9) to a `damage` effect → the attack **grows every time you play
  it this combat**: damage dealt = `amount` + `grow` × (times THIS card was played earlier this combat).
  First play = the printed `amount`; the card shows its CURRENT (grown) damage in your hand.
  `{ "op":"damage", "amount":8, "grow":5 }` = "Deal 8 damage. Grows by 5 each time it is played this combat."
  — the base-game **Rampage**. Per-CARD-INSTANCE (a generated `add_card` copy grows on its own), per-combat
  reset. `grow` is **NOT a scale** (it's an additive per-play step) — it and `scale` are mutually exclusive on
  one effect, `grow` must be ≤ `amount`, and it counts as the card's one calculated value (so a card can't also
  carry a scaled damage/block). Not legal inside an `add_trigger` payload. Distinct from `forge`: `grow` is ONE
  card feeding itself; Forge is a CLASS-level counter many cards pump.
- **Scaled amounts (`scale`):** instead of a fixed number, a `damage`, `block`, or `draw` effect can scale its
  amount to a **live combat value**. Put `"scale": "<source>"` on the effect (still include a nominal `"amount"`,
  which is ignored). Sources:
  - `"x"` — energy spent. **X-cost ONLY:** set the card `"cost": "X"` (spends ALL energy on play) and put
    `scale:"x"` on exactly one damage/block/draw. An X-cost card MUST have a `scale:"x"` effect and vice-versa.
    `{ "op":"damage", "scale":"x" }` = "Deal X damage"; `block` = "Gain X Block"; `draw` = "Draw X cards".
  - `"cards_in_hand"` — the count of the OTHER cards currently in your hand. "Deal damage equal to the cards in
    your hand." Rewards a fat hand (good with draw/Retain).
  - `"cards_retained"` — how many cards you **held into this turn** (your hand size at turn start, before drawing).
    "Deal damage equal to the cards you retained." This is the **Retain payoff** — the coil-then-release engine.
  - `"unspent_energy_last_turn"` — energy left over at the end of your last turn. Rewards deliberate under-spend.
  - `"forged"` — **the ADDITIVE exception (the base-game Forge keyword payoff):** the effect deals/blocks its
    printed `amount` (**NOT ignored** here — keep it real, ≥1) **plus your Forge**, the per-combat counter the
    `forge` op builds. `damage`/`block` only (never `draw`). This is "the signature blade that grows hit-by-hit":
    stoke the counter with `forge` income, cash it with ONE or TWO `scale:"forged"` payoff cards. A set with
    `forge` income MUST include a `scale:"forged"` payoff and vice versa.
  - `damage_dealt_unblocked` — **HEAL-ONLY (lifesteal).** A `heal` effect heals for the **unblocked** damage this
    card's earlier `damage` effect(s) dealt this play (blocked damage doesn't count; multi-hit and AoE all add up).
    The card MUST place a `damage` op **before** the `heal`. "Deal 8 damage to ALL enemies. Heal HP equal to the
    unblocked damage dealt." — the Reaper. Put a nominal `amount` on the heal (ignored).
  - `target_debuff_count` — **DAMAGE-ONLY (flechettes).** A `damage` effect deals damage equal to the number of
    **debuffs on the struck target** (resolved per target, so an AoE hits each enemy for *its own* count). "Deal
    damage equal to the debuffs on the target." Pairs with Vulnerable/Weak/Frail/Poison enablers.
  - `tag_cards_owned` — **the ADDITIVE tag-synergy exception (Perfected Strike); `damage`/`block` only.** The
    effect deals/blocks its printed `amount` (**NOT ignored** — keep it real, ≥1) **plus 1 per card carrying a
    given tag** across your combat piles. Requires a sibling **`tag`** field (a lowercase slug that must be one of
    your class's declared card `tags`, present on **≥2** cards so the payoff is never dead). "Deal 6 damage, plus 1
    per 'strike' card you own." Tag 3–5 cards with the same slug (see **`tags`** below), then add 1–2 payoffs.
  - `block` — your current Block (`damage`/`block` only): "Deal damage equal to your Block" = **Body Slam**; on `block` = Entrench. One or two per class.
  - `hp_lost_this_turn` — the HP you have lost this turn, net of healing (`damage`/`block` only): "Lose 4 HP. Deal damage equal to the HP you have lost this turn."
  - `draw_pile_count` — the cards in your draw pile (`damage`/`block` only): a fat-deck payoff that shrinks as you draw.
  - `energy` — your current energy (`damage`/`block`/`draw`); **COST-0 CARDS ONLY** (the cost is paid before the card resolves — a paid card would preview one number and deal another). You keep the energy.
  - `plays_this_combat` — the cards you have played this combat (player-level, not counting this one; `damage`/`block` only). Grows all fight → uncommon/rare. The per-CARD count is `grow`.
  - The non-`x` scalars have **no cost coupling** (use any cost) — except `energy` (cost 0).
    At most **one scaled damage/block per card** (a scaled `draw` or lifesteal `heal` is exempt). A scaled effect
    can't also be multi-hit. The four PLAYER-level reads (`cards_retained`, `cards_in_hand`,
    `unspent_energy_last_turn`, `forged`) also work inside `add_trigger` payloads (v42) — see Triggers.
- **Card `tags` (Phase AE, gap #25):** a card may carry an optional top-level **`tags`** array (1–2 lowercase
  slugs, e.g. `["strike"]`) — purely declarative metadata naming the card's kind. It has **no behavior on its
  own**; it exists so a `scale:"tag_cards_owned"` payoff can count cards by tag (above). Tag a family of 3–5
  cards with the same slug and give 1–2 payoffs the matching `tag`.

## Orbs (a CLASS IDENTITY — orb-class cards only)
Orbs are a Defect-style subsystem: a class with **orb slots** channels elemental orbs that trigger every turn and
can be "evoked" for a burst. **Only use the orb ops (`channel_orb`/`evoke`/`gain_orb_slot`) and the `focus` / `temp_focus` statuses
for an ORB CLASS** — one whose character sets `orb_slots > 0`. On a non-orb class they do nothing (no slots), so
never sprinkle them onto an ordinary class.
- **Base orbs:** `lightning` (deal damage to an enemy each turn; bigger burst on evoke), `frost` (gain Block
  each turn), `dark` (accumulates a growing value, released as one big hit on evoke).
- **Custom orbs (forged, class-specific):** a class may invent up to **3 of its OWN orbs** via the class's
  **`orb_pool`** (declared on the character, not on a card). Each custom orb has a `passive` (fires every turn)
  and an `evoke` (burst), each a list of orb-effects with a `target` (self/enemy/all_enemies) — so a custom orb
  can sear an enemy each turn, shield you, debuff foes, etc. A class's `orb_pool` is an ordered mix of base
  names + custom orbs; cards `channel_orb` them **by pool name** (`orb:"ember"`), and `orb:"random"` rolls only
  that class's pool. (Custom orbs are STRICTLY per-class — never global, never in another class's `random`.)
- **Orb-effect `when` (v49):** any orb-effect may carry a `when` gate — every condition below EXCEPT the
  chosen-target / retained reads (`target_has_status`, `target_hp_below_half`, `target_has_block`,
  `retained_last_turn`: an orb fires with no card or chosen target). Checked each tick/evoke; the tooltip prints
  "… if …". E.g. `{"op":"damage","amount":12,"target":"all_enemies","when":{"kind":"orb_count_ge","value":3}}`.
- **`passive_timing` (v49):** a custom orb's passive ticks at `turn_end` (default) or `turn_start`. A passive that
  `gain_energy` / `draw` MUST be `"passive_timing": "turn_start"` (energy/cards gained at turn end are lost).
- **Recipes** (custom orbs, not base orbs): **Plasma** =
  `{"name":"Plasma","passive_val":1,"evoke_val":2,"passive_timing":"turn_start","passive":[{"op":"gain_energy","amount":1}],"evoke":[{"op":"gain_energy","amount":2}]}`;
  **Glass** (evoke-only: nothing while channeled, a big shatter) =
  `{"name":"Glass","passive_val":0,"evoke_val":12,"passive":[],"evoke":[{"op":"damage","amount":12,"target":"all_enemies"}]}`.
- `channel_orb` fills your next open slot; channeling into full slots evokes the oldest first. `evoke` triggers +
  consumes your oldest orb now. `focus` (a `power`) raises the value of every orb — the orb-class scaling payoff.
- Design an orb class as a **channel-engine** (cards that channel orbs) + **payoffs** (evoke bursts, Focus
  scaling). Keep slot counts small (3–4). Custom orbs are how a class expresses a wholly invented element set.

## Conditions (`when` — gate an effect on combat state)
Any effect may carry an optional `"when"` predicate; the effect runs **only if it holds** (it's still printed
on the card, just skipped when false). This is how you build **conditional payoffs** — the "if X, then a big
thing happens" half of a card. Shape: `"when": { "kind": "...", ... }`; add `"negate": true` to invert it
(worded "unless …"). One `when` per effect. There is no `else` — model it as a second effect with the negated
condition. (v49: the same `when` is legal inside a custom orb's `passive` / `evoke` effects — see Orbs.)

| condition `kind`    | extra param | true when |
|---------------------|-------------|-----------|
| `orbs_match`        | —           | you have ≥2 orbs and they are **all the same type** (the slot-machine **jackpot**). **ORB-CLASS ONLY.** |
| `orb_count_ge`      | `value` (int ≥1) | you have at least `value` orbs channeled. **ORB-CLASS ONLY.** |
| `target_has_status` | `status` (poison/vulnerable/weak/frail) | the attacked enemy has that debuff (an exploit/follow-up payoff). |
| `no_block`          | —           | you currently have 0 Block (a desperation/reward-for-aggression payoff). |
| `hp_below_half`     | —           | your current HP is below 50% (an execute/last-stand payoff). |
| `has_block`         | optional `value` (int, default 1) | you currently have at least `value` Block (a defensive follow-up). |
| `enemy_count_ge`    | `value` (int ≥1) | there are at least `value` living enemies (a reward-vs-crowds payoff; `negate` for a lone-elite bonus). |
| `turn_at_least`     | `value` (int ≥1) | it is turn `value` or later (a card that powers up as the fight drags on). |
| `hand_size_ge`      | `value` (int ≥1) | you currently hold at least `value` cards (a full-hand payoff; pairs with Retain/draw). |
| `retained_last_turn`| —           | THIS card was in your hand at the start of this turn (you held it). The on-hold bonus: "if retained, …". |
| `forged_ge`         | `value` (int ≥1) | your **Forge** counter is at least `value` (a Forge-class gated payoff: "If your Forge is 10+, …"). Pair with `forge` income only. |
| `draw_pile_empty`   | —           | your draw pile is empty (the **Grand Finale** gate — a very strong effect you can only fire once you've drawn your whole deck; pairs with heavy draw). |
| `dark_ge`           | `value` (int ≥1) | your **Balance** gauge leans Dark by at least `value` (a Dark-pole payoff: "If your Dark is 5+, …"). **BALANCE-CLASS** — pair with `balance_step` income on both poles. |
| `light_ge`          | `value` (int ≥1) | your **Balance** gauge leans Light by at least `value` (the mirror Light-pole payoff). **BALANCE-CLASS.** |
| `centered`          | `value` (int ≥1) | your **Balance** gauge is within `value` of center (|gauge| ≤ `value`) — the **knife's-edge** payoff, rewarding staying balanced rather than committing to a pole. **BALANCE-CLASS.** |
| `hp_lost_ge`        | `value` (int 1–15) | you have lost at least `value` **HP this turn** (any source, net of healing — mostly your own `lose_hp` / card costs). The **Ice Shatter** threshold: pair a self-damage `lose_hp` fuel effect earlier on the card with a payoff gated on `hp_lost_ge` ("Lose 3 HP. Deal 18 damage if you've lost 3+ HP this turn."). Resets each turn. |
| `target_hp_below_half` | —        | the **chosen enemy** is below half HP (an execute payoff: "Deal 7 damage. Gain 1 energy if the enemy is below half HP."). **Single-enemy cards only** (`target:"enemy"`); never on an `add_trigger`. |
| `target_has_block`  | —           | the **chosen enemy** has Block up (a shatter payoff: "Deal 6 damage. Apply Vulnerable if the enemy has Block."). **Single-enemy cards only**; never on an `add_trigger`. |
| `energy_ge`         | `value` (int 1–6) | you have at least `value` energy — on a card, the energy left AFTER this card's cost is paid; on a `turn_end` trigger, your unspent energy. |
| `cards_played_this_turn_ge` | `value` (int 1–10) | you have finished playing at least `value` OTHER cards this turn (the **Finisher** combo gate: "Deal 9 damage. Apply Weak if you have played 2+ cards this turn."; a `turn_end` trigger counts the whole turn). |

> Composition is the point: pair `channel_orb orb:"random"` (the pull) with effects gated on `when:{kind:"orbs_match"}`
> (the jackpot) to build a **"sentient slot machine"** orb class — channel random orbs, and great things happen when
> they match. Reserve large conditional numbers for `uncommon`/`rare`: a conditional payoff is a swing, not always-on.
>
> **One value per card.** A card may use each value only ONCE — never two `damage` effects, two `block` effects, or
> two of the same status on one card (the engine keeps one number per kind). So a conditional bonus must use a
> DIFFERENT op than the base: write "Deal 7. Gain 5 Block **if your orbs match**" or "Deal 7. Apply 2 Vulnerable
> **if your orbs match**" — NOT "Deal 7. Deal 6 more if matched". (Need a bigger hit on match? Gate the whole single
> `damage` on the condition, or pay it off with a debuff/Block/draw instead.)

## Triggers (`add_trigger` — an ongoing per-turn engine)
A card can grant an **ongoing power** that fires a payload **every turn**, with `add_trigger`. This is how you build
classic power cards: Metallicize ("at the end of your turn, gain Block"), a Demon-Form ramp ("…gain Strength"), a
draw/energy engine at turn start, an orb auto-channeler, etc.
```json
{ "op": "add_trigger", "trigger": "turn_end",
  "effects": [ { "op": "block", "amount": 4 } ] }
```
- `trigger`: `turn_end` (fires at the END of your turn) or `turn_start` (at the START) — both fire **every turn**;
  or `ripen` — a **one-shot delayed maturation**: it does nothing for `amount` turns, then fires its payload **ONCE**
  (a "plant now, reap later" / countdown card, distinct from per-turn powers). Set the add_trigger's `amount` to the
  number of turns to wait (>= 1), e.g. `{ "op": "add_trigger", "trigger": "ripen", "amount": 3, "effects": [ { "op": "apply_status", "status": "strength", "amount": 3 } ] }` = "After 3 turns, gain 3 Strength."
  Or one of the **reactive** kinds, which fire whenever an event happens (possibly **many times a turn** — see
  `once_per_turn`): `on_hp_lost` (you lose HP on your own turn — the bleed/sacrifice payoff, à la Rupture),
  `on_exhaust` (a card of yours is Exhausted — Feel No Pain / Dark Embrace), `on_card_played` (you play a card —
  Rage), `on_card_drawn` (you draw a card), `on_damage_dealt` (you deal damage with a card OR through your summon —
  every `summon_attack` hit counts, per hit), `on_block_gained` (you gain
  Block — Juggernaut), `attacked` (an enemy deals you damage — reactive Thorns), `on_blade_played` (you play your
  signature blade — the Parry pattern; **FORGE-CLASS ONLY**). E.g.
  `{ "op": "add_trigger", "trigger": "on_exhaust", "effects": [ { "op": "block", "amount": 3 } ] }` = "Whenever a card
  is Exhausted, gain 3 Block."; `{ "op": "add_trigger", "trigger": "on_blade_played", "effects": [ { "op": "block", "amount": 8 } ] }` = "Whenever you play your blade, gain 8 Block."
- `once_per_turn` (optional, **reactive triggers only**): gate the payload to fire **at most once per turn**. Use it
  to keep a reactive engine in check (e.g. an on_card_played buff that shouldn't fire 5× on a big turn). Rejected on
  turn_start/turn_end/ripen (they already fire at most once per turn).
- `once_per_combat` (optional, **power-hosted reactive triggers only** — every reactive kind except the card-latent
  `on_discard`): gate the payload to fire **at most once per combat** — the granted power is a fresh instance each
  combat, so it fires on the FIRST event and then sleeps (the relic-hook `once_per_combat`). The "first-strike" /
  "second-wind" shape: `{ "op": "add_trigger", "trigger": "attacked", "once_per_combat": true, "effects": [ { "op": "block", "amount": 12 } ] }`
  = "Whenever you are attacked, gain 12 Block (once per combat)." Lets a reactive payload be BIG (it can't compound).
  Never combine with `once_per_turn` (once per combat already implies it); rejected on turn_start/turn_end/ripen.
- `effects`: the payload, run each time it fires. By default **a trigger fires with no target**, so a payload effect
  is a **SELF/orb-only sub-vocabulary**: `block`, `draw`, `gain_energy`, `heal`, `lose_hp`, `apply_status` (**self-buffs
  ONLY** — strength/dexterity/thorns/regen/metallicize/artifact/buffer/intangible/ritual/blur/temp_strength/
  temp_dexterity/barricade/focus/temp_thorns/temp_focus), `gain_orb_slot`, `channel_orb` (any orb in YOUR class's pool — base, `random`, or
  a custom orb: "At the start of your turn, channel an Ember"), `evoke`, `forge` (fixed amount only — the Forge
  engine: "At the start of your turn, Forge 2"), `balance_step` (fixed amount only — the Balance engine: "At the
  start of your turn, shift 2 toward the Dark"), `add_card` (**CLASS-ONLY** — the compost loop: "Whenever a card is
  Exhausted, add a copy of Cinder to your discard pile"), `discard` (forced churn: "At the start of your turn,
  discard 1" — **`random` only**, `cards:"choose"` is card-only), `upgrade_card` (**`random` only** — "At the start of your turn, upgrade a random card in your hand";
  `all` is card-only), `heal_summon` / `shield_summon` (the medic engine) — and, from **v42**, the **class
  engines**: `apply_status_custom` (**STATUS-CLASS** — "At the start of your turn, gain 1 Razor Focus"; give a
  custom DEBUFF a `target`), `summon_attack` (**SUMMON-CLASS** — the minion strikes on its own each turn: "At the
  end of your turn, deal 4 damage 2 times with your summon"; optional `target`, default the first enemy) and
  `buff_summon` (**SUMMON-CLASS** — "At the start of your turn, your summon gains 1 Strength"). A payload
  `damage` / `summon_attack` may carry `hits` (multi-hit each fire, v42); no other payload op may.
- **`on_discard` is CARD-LATENT (Reflex) — the exception to the whole model.** A card with
  `{ "op": "add_trigger", "trigger": "on_discard", "effects": [...] }` grants NO power when played; instead, its
  payload fires when THIS card is **discarded by an effect** — this class's `discard` / `scry` ops (a card's, or a
  `turn_start`→`discard` churn power's) AND base-game discard sources (relics, potions, other-class cards). It does
  **NOT** fire when the card is played, nor at end-of-turn hand cleanup — only effect-driven discards count
  (base-StS Reflex behavior). Design these as discard FUEL: cards you keep in hand and throw away for
  value — e.g. "Whenever this card is discarded, gain 6 Block." `once_per_turn` caps it to one fire per turn (a card
  can be discarded, redrawn, and discarded again). The payload is the same SELF/orb-only (or targeted) sub-vocabulary.
- **Targeted payload effects** (the per-turn threat family — Noxious Fumes, Combust, Choke): a payload effect may
  carry a **`target`** (`"enemy"`, `"all_enemies"`, or — on the `attacked` trigger ONLY — `"attacker"`) to hit
  enemies. Only `damage`, an **enemy-debuff** `apply_status` (vulnerable/weak/frail/poison), `summon_attack` and
  a custom-debuff `apply_status_custom` may be targeted; of these only a targeted `damage` may be scaled (v42). E.g.
  `{ "op": "add_trigger", "trigger": "turn_start", "effects": [ { "op": "apply_status", "status": "poison", "amount": 3, "target": "all_enemies" } ] }`
  = "At the start of your turn, apply 3 Poison to ALL enemies."
  **`attacker`** (v41) is the creature that just hit you — the TRUE riposte: `{ "op": "add_trigger", "trigger": "attacked", "effects": [ { "op": "damage", "amount": 5, "target": "attacker" } ] }`
  = "Whenever you are attacked, deal 5 damage to the attacker." In a crowd it strikes the one that struck (where
  `enemy` would hit the first living enemy); if that enemy is already dead the riposte simply does nothing. Reach for
  `attacker` on every retaliation power; keep `enemy` for the passive per-turn threats.
- A numeric payload effect (`block` / `draw` / `gain_energy` / `heal` / `lose_hp` / `gain_orb_slot` / a self
  `apply_status`, or a TARGETED `damage`) may **`scale`** to one of the four **PLAYER-level reads** — re-read each
  time it fires: `cards_retained` (the cards you held into this turn — "At the end of your turn, gain Block equal
  to cards retained"), `cards_in_hand` (v42 — the cards in your hand when it fires: "At the start of your turn, deal
  damage equal to the cards in your hand to ALL enemies"; **not on `turn_end`** — the hand is already discarded when
  that fires, so it would read 0; use `turn_start` / a reactive trigger, or `cards_retained`), `unspent_energy_last_turn` (v42 — "At the start of your
  turn, gain Block equal to your unspent energy last turn"), or `forged` (v42 — ADDITIVE, damage/block only,
  amount ≥1: "At the end of your turn, gain 2 Block, plus your Forge" — a Forge class's second payoff). Never on
  channel_orb/evoke/forge/balance_step or the summon/custom-status/pile ops; never together with `hits`.
- Optional `when` on the add_trigger is the **fire-time** gate, re-checked each fire (e.g. "at end of turn, **if your
  orbs match**, gain Focus"). It may use any condition EXCEPT `target_has_status` (no target at trigger time).
- **One `add_trigger` per card.** Put it on a `power`-type card. The numbers are per-turn, so keep them modest —
  small per-turn value compounds fast (uncommon/rare territory).

> Composition: triggers + orbs + conditions together are the deepest designs — e.g. an orb class whose power reads
> "At the end of your turn, channel a random orb; if your orbs match, gain 2 Focus." Reach for triggers when a class
> wants an engine that builds over the fight rather than a one-shot effect.

## Forged statuses (a CLASS IDENTITY — status-class cards only)
A class can invent its **own signature buff/debuff** — like Strength or Vulnerable, but yours — by declaring a
**`status_pool`** on the character (NOT on a card): up to **4** custom statuses. Each is a MODIFIER: while active it
changes ONE number. Cards apply it **by name** with `apply_status_custom` (`status_name` + `amount` stacks). **Only a
class that declared a `status_pool` may use `apply_status_custom`** (it's class-only, like the orb ops).

Each `status_pool` entry is an object:
```json
{ "name": "Razor Focus", "emoji": "🗡️", "type": "buff", "hook": "damage_dealt", "decay": "none",
  "description": "Your attacks deal bonus damage equal to its stacks." }
```
- `hook` (and its REQUIRED side) — which number it changes:
  | hook | side | meaning |
  |------|------|---------|
  | `damage_dealt` | **buff** | your attacks deal +stacks damage (Strength-like) |
  | `damage_taken` | **debuff** | the afflicted enemy takes +stacks damage (a Brittle / expose) |
  | `block_gained` | **buff** | +stacks Block whenever you gain Block (Dexterity-like) |
  | `energy_gain`  | **buff** | +stacks energy per turn |
  | `card_draw`    | **buff** | draw +stacks cards |
  | `damage_over_time` | **debuff** | at the start of ITS turn the afflicted enemy loses HP = stacks, unblockable (Poison-shaped: the burn / bleed / venom fantasy; v47). MUST decay |
  | `hit_count`    | **buff** | your Attacks hit +stacks extra times (a flurry stance; v47). MUST decay — 1 stack is a lot |
- `type` — `buff` (applied to YOU; ride it on a `self`-target card → worded "Gain N <Name>") or `debuff` (applied to
  the enemy; ride it on an `enemy`-target card → "Apply N <Name>"). The side MUST match the hook (table above).
- `decay` — `none` (permanent), `lose_one_eot` (−1 stack at end of the owner's turn), or `lose_all_eot` (clears at
  end of the owner's turn) — a buff decays on YOUR turn end, a debuff on the ENEMY's. `damage_over_time` and
  `hit_count` may not be `none`. `emoji` is a single emoji (the status's text glyph + icon). Optional `stack` =
  `counter` (default) / `single`.
- `mode` (optional, v47) — `additive` (default: stacks are a flat bonus) or `multiplicative`, legal on `damage_dealt` /
  `damage_taken` ONLY: each stack is +10% damage on powered attacks, capped at ×2 (a Vulnerable-like scaler; stacks
  past 10 add nothing).
- Cards apply by name: a brief like "gain 2 Razor Focus" → `{ "op":"apply_status_custom", "status_name":"Razor Focus",
  "amount":2 }` on a self-target card; "apply 2 Brittle" → the same op on an enemy-target card. Numbers fire every
  relevant event, so keep them **small**.

> Reach for a `status_pool` when the class fantasy is a **signature condition** (a duelist's Razor Focus, an
> alchemist's Corrosion) rather than orbs or generic statuses. A class can be all-custom-status, or mix custom
> statuses with normal cards. (Custom statuses are STRICTLY per-class — never global.)

## Forged summons (a CLASS IDENTITY — summon-class cards only)
A class can invent its **own minion(s)** — base-game **Osty**-style allies — by declaring a **`summon_pool`** on the
character (NOT on a card) with **one or two** custom summons. The default shape is **PASSIVE**, exactly like Osty:
one of each name on board at a time, its own HP bar, a **meat-shield** soaking the powered hits aimed at you,
**per-combat**, and it does **nothing on its own turn** — your cards are its offense. Such an entry is just a
`name`, `max_hp` (1–100, its starting HP) and an optional `description`:
```json
{ "name": "Bone Thrall", "max_hp": 12, "description": "A raised servant that guards you and strikes at your command." }
```
Six card ops drive the minions (all SUMMON-CLASS ONLY). Only `summon` names one; every other op — including
`heal_summon` / `shield_summon` above — acts on your **FRONT-most living** minion ("your summon"):
| card `op`      | params | what the card does |
|----------------|--------|--------------------|
| `summon`       | `summon_name`, optional `amount` (HP) | the base-game **Summon keyword**: if THAT minion is NOT out, summon it with `amount` HP (omit `amount` to use its `max_hp`); if it IS out, instead **raise its Max HP by `amount`**. A second, differently-named minion joins the board beside the first. Usually a self-target skill. |
| `summon_attack`| `amount` (per-hit), optional `hits` (≥2) | deal damage **through the minion** — the *minion* is the attacker, so it scales with its Strength. Does nothing if no minion is out. Put it on attack cards. |
| `buff_summon`  | `amount`, optional `status` (self-buff, default `strength`) | buff the living minion (e.g. **Strength** so its `summon_attack`s hit harder). Does nothing if no minion is out. |
| `sacrifice_summon` | *(none)* | **consume** your front-most minion — it dies and its `on_death` rattle fires. The **price** half of a card: pair it with a real payoff on the same card. |

The passive loop: **summon** the minion (and grow its HP), **buff_summon** it, then strike through it with
**summon_attack** — its Strength scales those hits while it body-blocks.

**The AUTONOMOUS minion** (opt-in, v52 — at most ONE pool entry): give that entry **`moves`**, a per-turn action
cycle it performs BY ITSELF at the end of your turn (one move repeats; several rotate). Each move is
`{ "actions": [...] }` over the minion sub-vocabulary `attack` (`amount`, optional `hits`) / `block` / `heal_self` /
`apply_status`; a top-level `actions` is the one-move shorthand. It is a free engine, so keep it small: **≤8 total
damage** (amount x hits) or **≤6 Block** per move, `hits` ≤2, `max_hp` ≤20. Optional extras: **`"attackable": false`**
= **ETHEREAL** (an untargetable striker — no HP bar, never body-blocks, so it may hit harder; autonomous entries
only), **`on_summon`** (a battle cry, run once when it lands), **`on_death`** (a death rattle, **enemy-facing only**
— what `sacrifice_summon` cashes in), **`on_nth_attack`** `{ "n": 2–5, "actions": [...] }` (every `n`th hit it
lands, it also does this).
```json
{ "name": "Carrion Hawk", "max_hp": 6, "attackable": false,
  "moves": [ { "actions": [ {"op":"attack","amount":4} ] }, { "actions": [ {"op":"attack","amount":3,"hits":2} ] } ],
  "on_summon": [ {"op":"apply_status","status":"weak","amount":1} ],
  "on_death":  [ {"op":"attack","amount":6,"target":"all_enemies"} ],
  "on_nth_attack": { "n": 3, "actions": [ {"op":"attack","amount":5} ] } }
```

> Reach for a `summon_pool` when the class fantasy is a **necromancer / beastmaster / conjurer / commander** who
> fights through a minion rather than orbs, statuses, or raw cards. Three shapes: **Commander** (passive
> bodyguard + `buff_summon` / `summon_attack`), **Swarm** (a cheap autonomous minion whose `on_summon` /
> `on_death` payoffs are the real card), **Ethereal striker**. (Summons are per-class — never global.)

## Hybrid classes (two pool kinds)
The importer parses `orb_pool` / `status_pool` / `summon_pool` independently, so a character may declare TWO of them
(AutoSlay-verified: an orb HUD and custom status icons coexist and both engines fire). Generation keeps a hybrid a
SEASONING, not two half-classes: ONE full engine plus ONE **splash** pool — splash orb = 2–3 `orb_slots` + ≤1 custom
orb; splash status = ≤2 custom statuses; splash summon = ONE passive minion — and never all three.

## Run-persistent Forge (a CLASS knob — forge classes only)
Forge is per-combat by default (it is a power). A forge class may set the character flag **`"forge_persist": true`**
(v54): each combat ends by banking `min(Forge, 5)`, and the first turn of the next combat pays that carry back as
Forge income — down the first-Forge path, so the signature blade is summoned too. It rides the run save (surviving
save-and-quit) and a new run starts at 0. **FORGE-CLASS ONLY**: with no `forge` income there is nothing to carry and
generation rejects the flag. The cap is the point — a head start, not a snowball, so cards stay priced per combat.
Reach for it when the fantasy is an heirloom that REMEMBERS across the run. Default `false`.

## The signature potion (a CLASS knob — EVERY class declares one)

Every forged class ships **exactly one custom potion** (v55), declared on the character as
`"potion_pool": [ { … } ]` — one object. It is added to that class's potion drop table *alongside* the base game's
potions, never replacing them: the game concatenates the class's own pool with the shared table every time it rolls
a potion, so a run of this class sees the usual Fire Potion / Block Potion / Fruit Juice **plus** this one.

A potion is a one-shot, no-card effect fired on demand — mechanically the same shape as a relic hook, which is why
it uses the relic sub-vocabulary rather than the full card one.

| field | values |
|---|---|
| `name` | ≤ 24 chars. |
| `emoji` | ONE emoji — this **is** the potion's art (rendered to its icon at load), so pick one that reads small. |
| `rarity` | `common` \| `uncommon` \| `rare`. The game rolls a tier first (≈65 / 25 / 10) and then picks uniformly inside it, so a `rare` potion is the scarcest and should be the biggest swing. |
| `usage` | `combat` (default — usable in a fight) \| `any` (also on the map; then `heal` is the ONLY legal op, since every other op needs a live combat). |
| `target` | `self` \| `enemy` \| `all_enemies`. Unlike cards, a `self` potion still resolves against you — put every buff and every self-effect here. `damage` and debuffs need `enemy` / `all_enemies`. |
| `description` | One line of card-style text. |
| `effects` | 1–2 ops from the table below. |

**Potion ops** — the relic sub-vocabulary, minus the drawback ops (a potion is a boon you *choose* to drink, so it
never carries a price), plus `apply_status_custom`:

| op | note |
|---|---|
| `damage` | Needs `enemy` / `all_enemies`. |
| `block`, `draw`, `gain_energy`, `heal`, `lose_hp` | Always resolve on you. |
| `apply_status` + `status` | Buffs (`strength`, `dexterity`, `thorns`, `regen`, `metallicize`, `artifact`, `buffer`, `intangible`, `ritual`, `blur`, `focus`, `temp_strength`, `temp_dexterity`, `temp_thorns`, `temp_focus`, `barricade`) need `target: self`; debuffs (`vulnerable`, `weak`, `frail`, `poison`) need an enemy target. |
| `apply_status_custom` + `status_name` | **Status classes only** — hand out one of the class's OWN signature statuses. A custom buff needs `self`, a custom debuff an enemy target. |
| `channel_orb` + `orb` | **Orb classes only** — `"random"` or a name from the class's `orb_pool`. |
| `summon` + `summon_name` | **Summon classes only** — a minion from the class's `summon_pool`. |
| `forge` | **Forge classes only** in practice — Forge income, which also summons the blade on the first one. |

**Make it read as THIS class.** The last four ops exist so the potion can reach into the class's own subsystem: a
status class's potion hands out its signature status, an orb class's channels its orbs, a summon class's calls its
minion, a forge class's stokes the Forge. A class with none of those gets a plain brew from the first two rows —
still themed by name, emoji and text. Power level: 1–2 effects at roughly **1.5× a common card's numbers** (a potion
is a free one-shot with no energy cost, but it is also a limited resource and takes a belt slot).

Every class gets one whether or not the blueprint asks for it — an omitted `potion` is filled in from whatever class
content exists — so the only real choice is whether it is *interesting*.

## Card shape
- `id` (snake_case, unique), `name` (short human title), `type` (attack/skill/power),
  `rarity` (basic/common/uncommon/rare), `cost` (0–4 energy, or `"X"`), `target`, `effects` (1+),
  optional `upgrade.effects` (the improved version), optional `flavor`.
- Set `"source": "llm"`.
- **Cost 4 is the heavyweight slot and is RARE-ONLY** (v53). Costs 0–3 stay the normal band; reach for 4 only when the
  card carries a *headline* effect — an `add_trigger` engine, a `when`-gated bomb, a `scale` amount, or the class-kind
  engine — never for a bigger Strike. A 4-cost common/uncommon is a dead draw and is rejected.
- **`upgrade.effects` normally lists the SAME effects in the SAME order** (only the numbers change). Two exceptions
  (v53): the upgrade may **APPEND exactly one keyword** the base card lacks (`exhaust` / `retain` / `innate` /
  `ethereal` — "Rampage+ also Retains"), or **DROP a trailing `exhaust`** (the upgrade sheds the drawback). Any other
  change in length or keywords is rejected.
- `tags`: 1–3 slugs (v53 raised the cap from 2).

## Rarity guidance (using only the ops above)
- **basic** — Strike/Defend tier; one plain effect.
- **common** — one clear effect; a cheap, simple card.
- **uncommon** — two effects or a bigger swing (e.g. damage + a debuff, or block + draw).
- **rare** — a standout: large numbers and/or several effects (e.g. AoE damage + Vulnerable to all).
  Build-around rares are the ones to reach for: an `add_trigger` engine (a power that fires every turn or on an event),
  a `when`-gated payoff, a `scale` amount that grows with state, a `transform_card` rank-up, or the class-kind engine
  (`forge` / `channel_orb` / `summon` / `apply_status_custom` / `balance_step`) — not just a bigger Strike.
