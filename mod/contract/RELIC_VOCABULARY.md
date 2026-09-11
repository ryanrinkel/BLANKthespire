# BLANK the spire — Forged Relic Vocabulary (constrained, v1)

This is the **complete** set of relic mechanics the mod's C# runtime (`ForgedRelic` + `RelicRunner` +
`EffectRunner.RunRelicEffects`) can execute today. A forged class may declare ONE custom **starter relic**.
Compose it ONLY from what's below — anything else is rejected by the validator and by the engine on import.

A relic is **fully data-driven**, like a card:

> **`hooks`** (on a trigger, optionally if a condition holds, run effects) **+ `modifiers`** (passive stat bonuses).

```json
{
  "id": "snake_case_unique",
  "name": "Short Title (<= 32 chars)",
  "description": "One line that matches the mechanics exactly.",
  "icon_emoji": "🔥",
  "tier": "starter",
  "modifiers": [ { "stat": "max_energy", "amount": 1 } ],
  "hooks": [
    { "trigger": "turn_start", "once_per_combat": true, "effects": [ { "op": "apply_status", "status": "strength", "amount": 1 } ] },
    { "trigger": "turn_start", "effects": [ { "op": "block", "amount": 3 } ] },
    { "trigger": "turn_end", "target": "enemy", "effects": [ { "op": "damage", "amount": 3 } ] },
    { "trigger": "attacked", "target": "attacker", "effects": [ { "op": "damage", "amount": 2 } ] }
  ],
  "source": "llm"
}
```

### `icon_emoji` — the relic's icon
One single emoji that best pictures the relic (its object/theme, not its mechanics) — it is rendered
into the in-game relic icon. Prefer a concrete THING (🗡️ 🛡️ 🕯️ 💀 🧪 ⚙️ 🔮 🌩️) over an abstract symbol.

## `hooks[]` — triggered behaviour
Each hook: `{ trigger, effects, target?, when?, once_per_combat?, card_type?, every_n? }`.

### Triggers (closed set — v1)
| `trigger`     | fires | the effects get |
|---------------|-------|-----------------|
| `turn_start`  | at the START of each of your turns | the player + (for damage/debuffs) the enemy target |
| `turn_end`    | at the END of each of your turns   | same |
| `attacked`    | each time an enemy DEALS YOU DAMAGE (reactive; fires per hit, so multi-hit attacks fire it multiple times) | the player + the `attacker` (the enemy that just hit you) — the Thorns / Bronze-Scales pattern |
| `on_exhaust`  | each time one of YOUR cards is Exhausted (reactive; fires once per exhausted card) | the player + (for damage/debuffs) the enemy target — the Compost-Bin pattern (no `attacker`) |
| `on_card_played` | each time you play a card (reactive; fires per card played — gate with `once_per_combat` for a "first card" effect) | the player + (for damage/debuffs) the enemy target (no `attacker`) |
| `combat_end` | when you WIN a combat (a Burning Blood / Meat-on-the-Bone payoff) | **`heal` only** — combat is over, so no other effect is allowed |
| `on_card_drawn` | each time you draw a card (reactive; fires per card drawn) | the player + (for damage/debuffs) the enemy target |
| `on_damage_dealt` | each time you deal damage with a CARD attack or THROUGH YOUR SUMMON (every `summon_attack` hit; reactive; per hit) | the player + (for damage/debuffs) the enemy target |
| `on_block_gained` | each time you gain Block (reactive) | the player + (for damage/debuffs) the enemy target |
| `on_hp_lost` | each time YOU lose HP on your OWN turn from a self/card-caused source (a `lose_hp` card, a self-damage cost — NOT enemy attacks, which fire `attacked`) | the player + (for damage/debuffs) the enemy target — the bleed/sacrifice payoff (Rupture-style) |

> There is **no `combat_start` trigger**. To do something **once at the start of combat**, use a `turn_start`
> hook with `"once_per_combat": true` — it fires on your first turn only (resets each combat).
> There is no loss hook either: `combat_end` fires only when you WIN.
> The reactive triggers (`attacked`, `on_exhaust`, `on_card_played`, `on_card_drawn`, `on_damage_dealt`,
> `on_block_gained`, `on_hp_lost`) can fire many times a turn — keep their numbers **small**, or gate with
> `"once_per_combat": true` for a "first time each combat" effect.

### `effects[]` — the SAME closed op vocabulary cards use (no card, so a restricted subset)
| op            | params              | meaning |
|---------------|---------------------|---------|
| `damage`      | `amount` (≥1)       | Deal `amount` damage to the hook's enemy target. **Requires `target` enemy/all_enemies.** |
| `block`       | `amount` (≥1)       | You gain `amount` Block. |
| `draw`        | `amount` (≥1)       | Draw `amount` cards. |
| `gain_energy` | `amount` (≥1)       | Gain `amount` energy this turn. |
| `heal`        | `amount` (≥1)       | Heal yourself `amount` HP. |
| `lose_hp`     | `amount` (≥1)       | You lose `amount` HP (a self-cost; ignores Block). |
| `apply_status`| `status`, `amount`  | Apply a status: a **buff** lands on YOU; a **debuff** lands on the enemy target (**requires an enemy `target`**). |
| `forge`       | `amount` (≥1)       | **FORGE CLASSES ONLY** (a class whose cards use the `forge` keyword / `scale:"forged"` payoffs). Stoke the player's per-combat **Forge** counter by `amount` — a "smoldering heirloom" keystone (e.g. `turn_start` + Forge 1). No-op value if the class has no `scale:"forged"` payoff cards. |
| `channel_orb` | `orb`, `amount`     | **ORB CLASSES ONLY.** Channel `amount` orbs (`orb`: `"random"` or one of your class's orb names). A **Cracked-Core**-style relic: pair with `turn_start` + `once_per_combat` to channel at the start of combat. No-op if your class has no orbs. |
| `summon`      | `summon_name`, `amount` (HP) | **SUMMON CLASSES ONLY.** Summon your class's ONE minion named `summon_name` onto your side at `amount` HP — or, if it is already out, raise its Max HP by `amount` (the base-game Osty Summon keyword: one passive bodyguard on board at a time, never a swarm). A **companion** relic: pair with `turn_start` + `once_per_combat` for the minion each combat. No-op unless `summon_name` is in your class's minions. |
| `cost_shift`  | `card_type` (attack/skill/power/all), `amount` (1–2), `scope` (`this_turn` ONLY), optional `count` (1–3) | **A this-turn discount** (v45): your cards of that type cost `amount` less this turn. `turn_start` + `count:1` + `card_type:"all"` = "your first card each turn costs 1 less" (the patient-apprentice keystone); `attacked` + `card_type:"attack"` = a riposte discount. `scope` must be `this_turn` (the whole-combat relic discount is the `cost_reduction` modifier). |
| `discard`     | `amount` (1–2)      | **A DRAWBACK** (v48): discard `amount` random cards from your hand (fuels `on_discard` cards). The classic price of a boon: `turn_start` + `discard 1`. Random only. |

No multi-hit, no X-scaling, no custom-statuses, no `add_trigger` in a relic. Orbs/summons are allowed ONLY via the
class-conditional `channel_orb` / `summon` ops above (and only if your class has them).

### Statuses (for `apply_status`)
- **Buffs (land on you):** `strength`, `dexterity`, `thorns`, `regen`, `metallicize`, `artifact`, `buffer`,
  `intangible`, `ritual`, `blur`, `temp_strength`, `temp_dexterity`, `temp_thorns`, `barricade` (`focus` / `temp_focus`
  are orb-only — don't use them on a relic). Numbers fire **every turn** the hook runs, so keep them **small** (1–2).
- **Debuffs:** `vulnerable`, `weak`, `frail`, `poison`. On an enemy `target` (`enemy`/`all_enemies`/`attacker`) they land
  on the enemy. On a `self` hook (v48) `weak`/`frail`/`vulnerable` land on **YOU** — a **drawback** (`turn_start` +
  `apply_status weak 1` = "you start each turn Weak"). `poison` always needs an enemy target.

### `target` (optional, default `self`)
`self` (no enemy — for block/draw/heal/buff/lose_hp), `enemy` (first alive enemy), `all_enemies` (every alive
enemy), `attacker` (the enemy that just hit you — **`attacked` hooks only**). A `damage` effect or a debuff
`apply_status` **requires** an enemy target (`enemy` / `all_enemies` / `attacker`). On an `attacked` hook, use
`attacker` to hit back the enemy that struck you (Thorns).

### `when` (optional — a fire-time condition; the hook runs only if it holds)
`{ "kind": <kind>, "value": N, "negate": false }`. Kinds (all read YOUR state — there is no enemy target at fire time):
- `hp_below_half` — your HP < 50%
- `no_block` — you have 0 Block · `has_block` — you have Block (or `value`+ Block)
- `enemy_count_ge` (needs `value` ≥ 1) — there are `value`+ enemies (so `value: 2` = a crowd; `negate` it for a lone elite)
- `turn_at_least` (needs `value` ≥ 1) — it is turn `value`+ (a relic that powers up late)
- `hand_size_ge` (needs `value` ≥ 1) — you hold `value`+ cards. **Timing:** the condition is read AT FIRE
  TIME — on an `on_card_played` hook that is AFTER the played card has left your hand, so the player must have
  held `value`+1 cards *before* playing. With a 5-card draw, `hand_size_ge 5`+ on `on_card_played` ~never fires;
  keep it ≤ 4 there, or read the full hand from `turn_start` / `turn_end` instead.

`negate: true` inverts any of them.

### `once_per_combat` (optional, default false)
`true` = the hook fires at most once per combat (resets each combat). This is how you do a "combat start" effect.

### `card_type` (optional — `on_card_played` hooks only; v48)
`"card_type": "attack" | "skill" | "power"` — the hook fires only when the played card is that type ("whenever you
play an Attack…", the Ornamental-Fan / Watering-Can pattern). Omit it to fire on every card.

### `every_n` (optional — a COUNTER relic; v48)
`"every_n": N` (2–9) — the hook fires on the Nth, 2Nth… matching occurrence, counted per combat (the relic icon shows
the running count). `on_card_played` + `"card_type": "attack"` + `"every_n": 3` = "every 3rd Attack you play"
(Shuriken / Nunchaku); `turn_start` + `"every_n": 2` = "every other turn". Because it fires 1/N as often, the payoff
can be medium (Block 3–5, draw 1, a 1-stack buff). Not on `combat_end`.

## `modifiers[]` — passive stat bonuses
| `stat`         | effect                         |
|----------------|--------------------------------|
| `max_energy`   | +`amount` energy per turn (a Coffee-Dripper / Energy-Core style relic). |
| `first_attack` | +`amount` damage to your FIRST attack card each combat (an Akabeko-style relic). One-shot per combat. |
| `cost_reduction` | your cards cost `amount` less **energy** in combat (floored at 0). Always-on, so keep `amount` to **1** — a Mummified-Hand / Sundial-style tempo relic. |
| `start_combat_block` | begin each combat with `amount` Block (granted on turn 1) — an Orichalcum / Anchor-style defensive relic. |
| `attack_base` | +`amount` damage to EVERY card attack you play (1–3; v48). Always-on Strength that never decays — a Vajra-style relic. `attack_base 1` is a whole starter relic by itself. |
| `max_hp` | ±`amount` Max HP, granted once when the run starts (−30..30; v48). **Negative is the standard PRICE of a boon:** `max_energy 1` and `cost_reduction 1` are boss-relic power and are REJECTED alone — pair them with `max_hp` **−8 or lower** (or a per-turn cost hook: `lose_hp` 2 / `discard` 1 / a self `weak` 1) for a Coffee-Dripper-with-a-cost. Positive `max_hp` is a small Strawberry-style boon (≤ +10). |

A relic may have hooks, modifiers, or both — but at least one of the two (a relic that does nothing is rejected).
A **drawback** (a `lose_hp` / `discard` / self-`weak` hook, or a negative `max_hp`) SUBTRACTS from the relic's power
price, so it is the only way a flat energy stat fits a starter.

## Design guidance (it's a STARTER relic)
Forged relics are always the class's **starting relic** (`tier: "starter"`, never rolled into rewards). They are
**always-on**, so power must be modest AND simple: small per-turn numbers, and **ONE keystone idea — a single
hook (or a single modifier, no hook)**. A second hook only if it is a genuine drawback/cost; never add a hook
just to nod at the second archetype. Lead with the class's **dominant** archetype (the other is flavor in the
name, not an extra mechanic). Write the `description` to match the mechanics exactly, in trigger order. Design
it to reward the class's core loop. (For the menu of single-hook keystone shapes — including the v48 "Counter relic"
and "Boon with a price" — see the RELIC FORMS section of the design heuristics.)
