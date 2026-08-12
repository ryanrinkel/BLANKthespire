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
Each hook: `{ trigger, effects, target?, when?, once_per_combat? }`.

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
| `on_damage_dealt` | each time you deal damage with a CARD attack (reactive; per hit) | the player + (for damage/debuffs) the enemy target |
| `on_block_gained` | each time you gain Block (reactive) | the player + (for damage/debuffs) the enemy target |
| `on_hp_lost` | each time YOU lose HP on your OWN turn from a self/card-caused source (a `lose_hp` card, a self-damage cost — NOT enemy attacks, which fire `attacked`) | the player + (for damage/debuffs) the enemy target — the bleed/sacrifice payoff (Rupture-style) |

> There is **no `combat_start` trigger**. To do something **once at the start of combat**, use a `turn_start`
> hook with `"once_per_combat": true` — it fires on your first turn only (resets each combat). There is no
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
| `summon`      | `summon_name`, `amount` | **SUMMON CLASSES ONLY.** Summon `amount` of your class's minion named `summon_name` onto your side. A **companion** relic: pair with `turn_start` + `once_per_combat` for a minion each combat. No-op unless `summon_name` is in your class's minions. |

No multi-hit, no X-scaling, no custom-statuses, no `add_trigger` in a relic. Orbs/summons are allowed ONLY via the
class-conditional `channel_orb` / `summon` ops above (and only if your class has them).

### Statuses (for `apply_status`)
- **Buffs (land on you):** `strength`, `dexterity`, `thorns`, `regen`, `metallicize`, `artifact`, `buffer`,
  `intangible`, `ritual`, `blur`, `temp_strength`, `temp_dexterity`, `barricade` (`focus` is orb-only — don't use
  it on a relic). Numbers fire **every turn** the hook runs, so keep them **small** (1–2).
- **Debuffs (land on the enemy target):** `vulnerable`, `weak`, `frail`, `poison`. The hook needs `target`
  `enemy`/`all_enemies`.

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

## `modifiers[]` — passive stat bonuses
| `stat`         | effect                         |
|----------------|--------------------------------|
| `max_energy`   | +`amount` energy per turn (a Coffee-Dripper / Energy-Core style relic). |
| `first_attack` | +`amount` damage to your FIRST attack card each combat (an Akabeko-style relic). One-shot per combat. |
| `cost_reduction` | your cards cost `amount` less **energy** in combat (floored at 0). Always-on, so keep `amount` to **1** — a Mummified-Hand / Sundial-style tempo relic. |
| `start_combat_block` | begin each combat with `amount` Block (granted on turn 1) — an Orichalcum / Anchor-style defensive relic. |

A relic may have hooks, modifiers, or both — but at least one of the two (a relic that does nothing is rejected).

## Design guidance (it's a STARTER relic)
Forged relics are always the class's **starting relic** (`tier: "starter"`, never rolled into rewards). They are
**always-on**, so power must be modest AND simple: small per-turn numbers, and **ONE keystone idea — a single
hook (or a single modifier, no hook)**. A second hook only if it is a genuine drawback/cost; never add a hook
just to nod at the second archetype. Lead with the class's **dominant** archetype (the other is flavor in the
name, not an extra mechanic). Write the `description` to match the mechanics exactly, in trigger order. Design
it to reward the class's core loop. (For the menu of single-hook keystone shapes, see the RELIC FORMS section
of the design heuristics.)
