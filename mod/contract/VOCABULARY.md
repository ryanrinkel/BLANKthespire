# BLANK the spire — Card Effect Vocabulary (constrained)

This is the **complete** set of mechanics the mod's C# interpreter (`EffectRunner`) can execute today.
Compose cards ONLY from these. Anything outside this list cannot be played and will be rejected by the
validator. (The vocabulary grows as the interpreter grows — more ops/statuses are coming.)

## Effect ops
| op             | params            | meaning |
|----------------|-------------------|---------|
| `damage`       | `amount` (int ≥1), optional `hits` (int ≥2) | Deal `amount` attack damage to the card's target(s). Routed through Strength/Weak/Vulnerable/Block by the engine. Add `hits` to make it **multi-hit**: deal `amount` damage `hits` times (e.g. `amount:4, hits:3` = "Deal 4 damage 3 times"). At most one multi-hit effect per card. |
| `block`        | `amount` (int ≥1) | Gain `amount` Block (always on the player, regardless of the card's target). |
| `draw`         | `amount` (int ≥1) | Draw `amount` cards. |
| `apply_status` | `status`, `amount`| Apply `amount` stacks of a status to the card's target(s) (buffs go on the player, debuffs on enemies — see Statuses). |
| `gain_energy`  | `amount` (int ≥1) | Gain `amount` energy this turn. |
| `heal`         | `amount` (int ≥1) | Heal the player `amount` HP. |
| `lose_hp`      | `amount` (int ≥1) | The player loses `amount` HP (ignores Block; a self-cost, not an attack). |
| `exhaust`      | *(none)*          | This card Exhausts when played (removed from the deck for the rest of combat). A card property, not a targeted effect. |
| `innate`       | *(none)*          | This card starts in your opening hand every combat. A card property (no targeted effect). |
| `retain`       | *(none)*          | This card is NOT discarded at end of turn — it stays in your hand. A card property. |
| `ethereal`     | *(none)*          | If this card is still in your hand at end of turn, it Exhausts. A card property. |
| `purge`        | *(none)*          | **Purge** — when this card is played, it is removed from your **run deck for the rest of the run** (permanent deck-thinning; a stronger `exhaust` that never comes back). A card property. **Mutually exclusive with `exhaust`** (a card can't do both). **Never on a BASIC card.** Put it on a strong one-shot skill/attack you're happy to spend once to thin toward a lean engine (1–3 per class). A generated copy of a purge card (from `add_card`) just vanishes for the combat — it isn't in your run deck to remove. |
| `purge_card`   | *(none)*          | **Choose-a-card Purge** — when this card is played, **YOU pick a card in your hand and purge THAT card** (removed from your run deck for the rest of the run). The player-choice form of `purge`: instead of the played card removing itself, it lets you thin a *chosen* target — great for cutting a Basic/Curse/dead card you drew. Carries no amount/target. Empty hand = harmless no-op. Put it on a skill/attack (1–2 per class). A chosen generated copy (no run-deck original) just vanishes for the combat. |
| `forge`        | `amount` (int ≥1) | **Forge N** — stoke your per-combat **Forge** counter by `amount` (shown as a stacking power; resets each combat). The payoff is a damage/block effect with `scale:"forged"`, which ADDS your Forge to its printed amount. Income also works inside `add_trigger` payloads ("At the start of your turn, Forge 2") — see Triggers. A card set that Forges MUST also contain a `scale:"forged"` payoff, and vice versa. |
| `channel_orb`  | `orb` (lightning/frost/dark/**random**), optional `amount` (count) | Channel an orb into your next open slot. `orb:"random"` rolls one of lightning/frost/dark — **independently per orb** when `amount > 1`, so a multi-channel "pull" can come up all-matching (the slot-machine jackpot). **ORB-CLASS ONLY** — see Orbs below. |
| `evoke`        | optional `amount` (count) | Evoke (trigger + consume) your oldest orb(s) now. **ORB-CLASS ONLY.** |
| `gain_orb_slot`| `amount` (int ≥1) | Gain `amount` orb slots this combat. **ORB-CLASS ONLY.** |
| `add_trigger`  | `trigger` (turn_end/turn_start/ripen/on_hp_lost/on_exhaust/on_card_played/on_card_drawn/on_damage_dealt/on_block_gained/attacked/on_discard/on_blade_played), `effects` (1+), optional `when`, optional `once_per_turn`, `amount` (ripen only) | Grant an ongoing power that runs its `effects` payload: every turn (turn_end/turn_start), ONCE after `amount` turns (ripen), or REACTIVELY on an event (on_hp_lost / on_exhaust / on_card_played / on_card_drawn / on_damage_dealt / on_block_gained / attacked). Payload is SELF/orb-only unless an effect carries a `target` (see Triggers below). Best on `power`-type cards. **Exception — `on_discard`** is CARD-LATENT (Reflex, see Triggers): it grants NO power on play; its payload fires when THIS card is DISCARDED BY AN EFFECT. |
| `apply_status_custom` | `status_name`, `amount` | Apply `amount` stacks of one of the class's OWN custom statuses (by name). **STATUS-CLASS ONLY** — see Forged Statuses below. |
| `summon`       | `summon_name`, optional `amount` (HP) | Summon the class's OWN minion (by name) at `amount` HP, OR — if it's already out — raise its Max HP by `amount` (base-game Osty Summon keyword). One per class; passive bodyguard. **SUMMON-CLASS ONLY** — see Forged Summons below. |
| `summon_attack`| `amount` (per-hit), optional `hits` (≥2) | Deal `amount` damage **through your summon** (it's the attacker, scaling with its Strength); no-op if the summon isn't out. **SUMMON-CLASS ONLY** — see Forged Summons below. |
| `buff_summon`  | `amount`, optional `status` (self-buff, default `strength`) | Buff your living summon (e.g. Strength so its `summon_attack`s hit harder); no-op if the summon isn't out. **SUMMON-CLASS ONLY** — see Forged Summons below. |
| `heal_summon`  | `amount` (int 1–9) | Heal your living summon `amount` HP (the selfless "medic" op — spend a card to keep your bodyguard alive); no-op if the summon isn't out. Also legal inside `add_trigger` payloads (a per-turn medic engine: "At the start of your turn, heal your summon 3"). **SUMMON-CLASS ONLY** — see Forged Summons below. |
| `shield_summon`| `amount` (int 1–12) | Grant your living summon `amount` Block; no-op if the summon isn't out. Also legal inside `add_trigger` payloads. **SUMMON-CLASS ONLY** — see Forged Summons below. |
| `add_card`     | `card_id` (a card in THIS class's own set), `pile` (hand/discard/draw), optional `amount` (copies, 1–3, default 1) | Generate `amount` **combat-transient copies** of one of your class's OWN cards into a pile (the base-game "add a card to combat" — the copies vanish at combat end, never enter your deck). May reference itself (Anger). The referenced card must NOT itself `add_card` (depth-1 loop discipline). Also legal inside `add_trigger` payloads — the compost loop ("Whenever a card is Exhausted, add a copy of X to your discard pile"). **CLASS-ONLY.** |
| `discard`      | `amount` (int ≥1) | Discard `amount` RANDOM cards from your hand (choiceless — no card-selection UI). Pairs with the `on_discard` trigger (discard-fuel decks) and works inside `add_trigger` payloads ("At the start of your turn, discard 1" — forced churn). Discarding is an EFFECT: it triggers `on_discard` cards; end-of-turn hand cleanup does NOT. |
| `scry`         | `amount` (int ≥1) | **Scry `amount`** — look at the top `amount` cards of your DRAW pile and discard any of them you choose (keep the rest on top, in order). A draw-quality filter: dig past dead cards toward what you need, and *fuel discard payoffs* — a scry-discard triggers `on_discard` cards just like `discard` does. Great on the discard/`on_discard` archetype. Typical values 2–5. Card-only (not a repeating-trigger payload). |
| `corruption`   | *(none)*          | **Corruption** — while active this combat, **your Skills cost 0 but Exhaust when played** (the base-game Corruption power; the reckless-tempo engine). A flag-op granting a binary per-combat power (no stacking). Put it on a **POWER or SKILL** card (never an Attack). Card-only (never in a trigger payload). **At most one per class.** Pairs with Skill density + `on_exhaust` payoffs (Feel No Pain / Dark Embrace) — the exhausting free Skills feed the exhaust engine. |
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
| `thorns`        | buff   | When an enemy attacks you, it takes `amount` damage back. Permanent. |
| `regen`         | buff   | Heal `amount` HP at the end of your turn (typically decays). |
| `metallicize`   | buff   | Gain `amount` Block at the end of every turn. Permanent. |
| `artifact`      | buff   | Negate the next `amount` debuffs applied to you. |
| `buffer`        | buff   | Prevent the next `amount` instances of HP loss. |
| `blur`          | buff   | Your Block is NOT removed at the start of your next `amount` turn(s). |
| `intangible`    | buff   | Reduce ALL damage you take to 1 for `amount` turn(s). Very strong — rare-tier, keep `amount` tiny (1). |
| `ritual`        | buff   | Gain `amount` Strength at the end of every turn. Snowballs hard — rare-tier. |
| `barricade`     | buff   | Your Block is never removed (it persists between turns). A toggle — use `amount: 1`. |
| `focus`         | buff   | +`amount` to the value of every orb you channel (Lightning damage, Frost Block, Dark hit). **ORB-CLASS ONLY.** |

> `vulnerable`/`weak` are the most generic debuff filler and `strength`/`block`-shaped buffs the most generic
> buff filler — but prefer a card whose identity is a distinct shape (poison, thorns, metallicize/block-engine,
> intangible/ritual payoff, etc.). `intangible`, `ritual`, and `barricade` are powerful build-defining buffs:
> reserve them for `power`-type cards and the `rare` tier, with small numbers.

## Targeting (`target` field)
| target        | meaning |
|---------------|---------|
| `enemy`       | A single player-chosen enemy. |
| `all_enemies` | Every enemy (AoE). |
| `self`        | The player (use for pure skills like block/draw). |

## Structural mechanics (multi-hit & scaled amounts)
- **Multi-hit:** add `hits` (int ≥2) to a `damage` effect → it deals `amount` damage `hits` times
  (e.g. `{ "op":"damage", "amount":4, "hits":3 }` = "Deal 4 damage 3 times"). At most one per card. The
  per-hit damage is `amount`; an upgrade can raise either the per-hit damage or the hit count.
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
    stoke the counter with `forge` income (cards, per-turn triggers, maybe a relic), cash it with ONE or TWO
    `scale:"forged"` payoff cards. A set with `forge` income MUST include a `scale:"forged"` payoff and vice versa
    (income without a payoff is a dead engine; a payoff without income is a dead card).
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
    per 'strike' card you own." Tag 3–5 cards of the class with the same slug (see **`tags`** below), then add
    1–2 payoffs referencing it — the base-game strikes-matter identity.
  - The non-`x` scalars — `cards_in_hand`, `cards_retained`, `unspent_energy_last_turn`, `forged`,
    `damage_dealt_unblocked`, `target_debuff_count`, `tag_cards_owned` — have **no cost coupling** (use any cost).
    At most **one scaled damage/block per card** (a scaled `draw` or lifesteal `heal` is exempt). A scaled effect
    can't also be multi-hit.
- **Card `tags` (Phase AE, gap #25):** a card may carry an optional top-level **`tags`** array (1–2 lowercase
  slugs, e.g. `["strike"]`) — purely declarative metadata naming the card's kind. It has **no behavior on its
  own**; it exists so a `scale:"tag_cards_owned"` payoff can count cards by tag (above). Tag a family of 3–5
  cards with the same slug and give 1–2 payoffs the matching `tag`.

## Orbs (a CLASS IDENTITY — orb-class cards only)
Orbs are a Defect-style subsystem: a class with **orb slots** channels elemental orbs that trigger every turn and
can be "evoked" for a burst. **Only use the orb ops (`channel_orb`/`evoke`/`gain_orb_slot`) and the `focus` status
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
- `channel_orb` fills your next open slot; channeling into full slots evokes the oldest first. `evoke` triggers +
  consumes your oldest orb now. `focus` (a `power`) raises the value of every orb — the orb-class scaling payoff.
- Design an orb class as a **channel-engine** (cards that channel orbs) + **payoffs** (evoke bursts, Focus
  scaling). Keep slot counts small (3–4). Custom orbs are how a class expresses a wholly invented element set.

## Conditions (`when` — gate an effect on combat state)
Any effect may carry an optional `"when"` predicate; the effect runs **only if it holds** (it's still printed
on the card, just skipped when false). This is how you build **conditional payoffs** — the "if X, then a big
thing happens" half of a card. Shape: `"when": { "kind": "...", ... }`; add `"negate": true` to invert it
(worded "unless …"). One `when` per effect. There is no `else` — model it as a second effect with the negated
condition.

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
  Rage), `on_card_drawn` (you draw a card), `on_damage_dealt` (you deal card damage), `on_block_gained` (you gain
  Block — Juggernaut), `attacked` (an enemy deals you damage — reactive Thorns), `on_blade_played` (you play your
  signature blade — the Parry pattern; **FORGE-CLASS ONLY**). E.g.
  `{ "op": "add_trigger", "trigger": "on_exhaust", "effects": [ { "op": "block", "amount": 3 } ] }` = "Whenever a card
  is Exhausted, gain 3 Block."; `{ "op": "add_trigger", "trigger": "on_blade_played", "effects": [ { "op": "block", "amount": 8 } ] }` = "Whenever you play your blade, gain 8 Block."
- `once_per_turn` (optional, **reactive triggers only**): gate the payload to fire **at most once per turn**. Use it
  to keep a reactive engine in check (e.g. an on_card_played buff that shouldn't fire 5× on a big turn). Rejected on
  turn_start/turn_end/ripen (they already fire at most once per turn).
- `effects`: the payload, run each time it fires. By default **a trigger fires with no target**, so a payload effect
  is a **SELF/orb-only sub-vocabulary**: `block`, `draw`, `gain_energy`, `heal`, `lose_hp`, `apply_status` (**self-buffs
  ONLY** — strength/dexterity/thorns/regen/metallicize/artifact/buffer/intangible/ritual/blur/temp_strength/
  temp_dexterity/barricade/focus), `gain_orb_slot`, `channel_orb`, `evoke`, `forge` (fixed amount only — the Forge
  engine: "At the start of your turn, Forge 2"), `balance_step` (fixed amount only — the Balance engine: "At the
  start of your turn, shift 2 toward the Dark"), `add_card` (**CLASS-ONLY** — the compost loop: "Whenever a card is
  Exhausted, add a copy of Cinder to your discard pile"), `discard` (forced churn: "At the start of your turn,
  discard 1"), `upgrade_card` (**`random` only** — "At the start of your turn, upgrade a random card in your hand";
  `all` is card-only) — and no `hits`.
- **`on_discard` is CARD-LATENT (Reflex) — the exception to the whole model.** A card with
  `{ "op": "add_trigger", "trigger": "on_discard", "effects": [...] }` grants NO power when played; instead, its
  payload fires when THIS card is **discarded by an effect** (a `discard` op — yours or a `turn_start`→`discard`
  churn power). It does **NOT** fire when the card is played, nor at end-of-turn hand cleanup — only effect-driven
  discards count (base-StS Reflex behavior). Design these as discard FUEL: cards you keep in hand and throw away for
  value — e.g. "Whenever this card is discarded, gain 6 Block." `once_per_turn` caps it to one fire per turn (a card
  can be discarded, redrawn, and discarded again). The payload is the same SELF/orb-only (or targeted) sub-vocabulary.
- **Targeted payload effects** (the per-turn threat family — Noxious Fumes, Combust, Choke): a payload effect may
  carry a **`target`** (`"enemy"` or `"all_enemies"`) to hit enemies. Only `damage` and an **enemy-debuff**
  `apply_status` (vulnerable/weak/frail/poison) may be targeted; a targeted effect can't be scaled. E.g.
  `{ "op": "add_trigger", "trigger": "turn_start", "effects": [ { "op": "apply_status", "status": "poison", "amount": 3, "target": "all_enemies" } ] }`
  = "At the start of your turn, apply 3 Poison to ALL enemies."
- A **self** (untargeted) numeric payload effect may use **`"scale": "cards_retained"`** (and ONLY that scalar — not
  on channel_orb/evoke, not on a targeted effect) to make its amount the cards you held into this turn, re-read each
  turn it fires — e.g. "At the end of your turn, gain Block equal to cards retained."
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
- `type` — `buff` (applied to YOU; ride it on a `self`-target card → worded "Gain N <Name>") or `debuff` (applied to
  the enemy; ride it on an `enemy`-target card → "Apply N <Name>"). The side MUST match the hook (table above).
- `decay` — `none` (permanent), `lose_one_eot` (−1 stack at end of your turn), or `lose_all_eot` (clears at end of
  your turn). `emoji` is a single emoji (the status's text glyph + icon). Optional `stack` = `counter` (default) / `single`.
- Cards apply by name: a brief like "gain 2 Razor Focus" → `{ "op":"apply_status_custom", "status_name":"Razor Focus",
  "amount":2 }` on a self-target card; "apply 2 Brittle" → the same op on an enemy-target card. Numbers fire every
  relevant event, so keep them **small**.

> Reach for a `status_pool` when the class fantasy is a **signature condition** (a duelist's Razor Focus, an
> alchemist's Corrosion) rather than orbs or generic statuses. A class can be all-custom-status, or mix custom
> statuses with normal cards. (Custom statuses are STRICTLY per-class — never global.)

## Forged summons (a CLASS IDENTITY — summon-class cards only)
A class can invent its **own minion** — a base-game **Osty**-style bodyguard — by declaring a **`summon_pool`** on the
character (NOT on a card) with **exactly one** custom summon. The minion works *exactly* like Osty:
- **One on board at a time**, with its own HP and an HP bar.
- **Passive** — it does **nothing** on its own turn (no autonomous attacks).
- A **meat-shield**: it soaks the powered hits aimed at you, until it falls.
- **Per-combat** (cleared at combat end).

Its `summon_pool` entry is just a `name`, `max_hp` (1–60, its starting HP), and an optional `description`:
```json
{ "name": "Bone Thrall", "max_hp": 12, "description": "A raised servant that guards you and strikes at your command." }
```
The class's whole identity is **three card ops** that drive that minion (all SUMMON-CLASS ONLY — a class with a
`summon_pool`):
| card `op`      | params | what the card does |
|----------------|--------|--------------------|
| `summon`       | `summon_name` (the minion), optional `amount` (HP) | the base-game **Summon keyword**: if the minion is NOT out, summon it with `amount` HP (omit `amount` to use its `max_hp`); if it IS already out, instead **raise its Max HP by `amount`** (grow it). Usually a self-target skill. |
| `summon_attack`| `amount` (per-hit), optional `hits` (≥2) | deal damage **through the minion** — the *minion* is the attacker, so it scales with the minion's Strength (an "Osty attack"). Does nothing if the minion isn't out. Put it on attack cards (single-target, or all-enemies if the card is AoE). |
| `buff_summon`  | `amount`, optional `status` (a self-buff, default `strength`) | buff the living minion (e.g. **Strength** so its `summon_attack`s hit harder, or a defensive buff to make it tankier). Does nothing if the minion isn't out. |

The loop is: **summon** the minion (and grow its HP), **buff_summon** it (Strength), then strike through it with
**summon_attack** — its Strength scales those hits while it body-blocks for you. Example cards:
```json
{ "op": "summon", "summon_name": "Bone Thrall", "amount": 12 }   // a skill: summon your Thrall (12 HP)
{ "op": "summon_attack", "amount": 9 }                            // an attack: your summon strikes for 9
{ "op": "buff_summon", "amount": 3, "status": "strength" }        // a skill: your summon gains 3 Strength
```

> Reach for a `summon_pool` when the class fantasy is a **necromancer / beastmaster / conjurer** who fights through
> one loyal minion rather than orbs, statuses, or raw cards. A class can be all-summons or mix summon cards with
> normal cards. (Summons are STRICTLY per-class — never global.)
>
> *(The earlier autonomous-minion model — per-turn move cycles, ethereal minions, on-summon/on-death triggers, and
> multiple pets — is disabled for now; the runtime keeps it dormant for possible re-introduction.)*

## Card shape
- `id` (snake_case, unique), `name` (short human title), `type` (attack/skill/power),
  `rarity` (basic/common/uncommon/rare), `cost` (0–3 energy, or `"X"`), `target`, `effects` (1+),
  optional `upgrade.effects` (the improved version), optional `flavor`.
- Set `"source": "llm"`.

## Rarity guidance (using only the ops above)
- **basic** — Strike/Defend tier; one plain effect.
- **common** — one clear effect; a cheap, simple card.
- **uncommon** — two effects or a bigger swing (e.g. damage + a debuff, or block + draw).
- **rare** — a standout: large numbers and/or several effects (e.g. AoE damage + Vulnerable to all).
  (Deeper "build-around" rares need ops not yet supported; for now make rares hit hard and wide.)
