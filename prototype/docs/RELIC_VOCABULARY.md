# Relic vocabulary

A relic is **fully data-driven**, exactly like a card. There is no per-relic GDScript: a relic is a
JSON file, and the generic interpreter in `core/relics/Relic.gd` runs it. A new triggered relic is
*just data* — the same payoff the card model already has.

A relic is:

> **on `<trigger>`, [if `<condition>`], run `<effects>`** — plus optional passive **`<modifiers>`**.

```json
{
  "id": "burning_blood",
  "name": "Burning Blood",
  "tier": "starter",
  "pool": "starter",
  "description": "At the end of combat, heal 6 HP.",
  "hooks": [
    { "trigger": "combat_end", "condition": "victory", "effects": [ { "op": "heal", "amount": 6 } ] }
  ]
}
```

**Golden rule (same as cards):** a relic is composed *only* from the triggers, conditions, effect ops,
and modifier stats enumerated below. The model never invents new ones. When a mechanic isn't
expressible, a **human adds one primitive** (a trigger emission point + an interpreter line, or a
modifier stat + a pipeline read, or an effect op) and documents it here — then the model can compose it.

---

## `hooks[]` — triggered behavior

Each hook is `{ trigger, condition?, target?, once_per_combat?, effects }`.

### Triggers (closed set)

The hook's effects run under an `EffectContext` whose **source is always the player**; the **default
target** depends on the trigger:

| `trigger`      | fires when                                  | default target      |
|----------------|---------------------------------------------|---------------------|
| `combat_start` | after enemies spawn, before turn 1          | first alive enemy   |
| `turn_start`   | at the start of each player turn (post-draw)| first alive enemy   |
| `turn_end`     | at the end of each player turn              | first alive enemy   |
| `combat_end`   | when combat resolves                        | none                |
| `attacked`     | after the player takes unblocked attack HP  | **the attacker**    |

Notes:
- `combat_start` block (e.g. Anchor) **survives into turn 1** — turn 1 skips its block reset.
- `gain_energy` at `combat_start` would be wiped by the turn-1 energy refill — use `turn_start` +
  `once_per_combat` instead (that's how **Lantern** gives "1 energy on the first turn").
- A `turn_start` effect that kills the last enemy ends the combat cleanly (an end-check follows).

### Conditions (closed set)

`condition` is one value or an array (**all must hold**). Default: `always`.

| condition       | true when                                   |
|-----------------|---------------------------------------------|
| `always`        | always (the default)                        |
| `victory`       | combat ended in a win (use on `combat_end`) |
| `defeat`        | combat ended in a loss                      |
| `hp_below_half` | player HP ≤ 50% of max, at fire time        |

### `target` override (optional)

By default the trigger picks the target (table above). Override with:

| `target`      | effect                                                 |
|---------------|--------------------------------------------------------|
| `self`        | the player                                             |
| `enemy`       | the first alive enemy                                  |
| `all_enemies` | run the effects **once per alive enemy** (true AoE)    |

(Buffs route to the player and most debuffs route to the target regardless — see `apply_status`.)

### `once_per_combat` (optional)

`true` = the hook fires at most once per combat (e.g. **Centennial Puzzle** draws 3 the first time you
lose HP). Resets each combat.

### `effects[]`

**The exact same closed op vocabulary cards use** — see [VOCABULARY.md](VOCABULARY.md). `damage`,
`block`, `apply_status` (buffs→player, debuffs→target, `to` overrides), `draw`, `gain_energy`, `heal`,
`lose_hp`, `add_card`, `multi`, `from_state`, `conditional`, `set_flag`. `heal`/`lose_hp`/`block` act on
the actor (player); `damage`/`apply_status`-debuff act on the resolved target.

**Use `damage` with `"raw": true` for fixed relic damage** (Bronze Scales Thorns, Mercury Hourglass) —
it deals the flat amount through Block only, *unscaled* by Strength/Weak/Vulnerable, which is how those
relics behave in StS. Plain `damage` would (wrongly) grow with the player's Strength.

---

## `modifiers[]` — passive stat bonuses

For mechanics that aren't "run effects on an event" but **bend a computed pipeline**. Read directly by
the engine, not the effect queue.

| `stat`        | effect                                              | `when`                    |
|---------------|-----------------------------------------------------|---------------------------|
| `attack_base` | adds to the player's attack **base** damage         | `always` or `first_attack`|
| `max_energy`  | adds to the player's energy per turn                | (n/a)                     |

- `attack_base` + `when: "first_attack"` = **Akabeko** (first attack each combat +8).
- `max_energy` = **Energy Core** (+1 energy/turn). A relic may carry **both** hooks and modifiers —
  **Philosopher's Stone** = `max_energy +1` modifier *and* a `combat_start` hook giving every enemy 1
  Strength.

---

## Authored set (the few-shot corpus)

`combat_start`: Vajra (+1 Str), Anchor (+10 Block), Bag of Marbles (Vuln all), Bag of Preparation
(draw 2), Blood Vial (heal 2), Oddly Smooth Stone (+1 Dex), Philosopher's Stone (1 Str to all enemies).
`turn_start`: Lantern (+1 energy turn 1), Mercury Hourglass (3 dmg to all enemies).
`combat_end`: Burning Blood (heal 6 on win), Meat on the Bone (heal 12 if ≤50% HP).
`attacked`: Bronze Scales (Thorns 3), Centennial Puzzle (draw 3 once).
modifiers: Akabeko (first attack +8), Energy Core (+1 energy), Philosopher's Stone (+1 energy).

---

## Extending the vocabulary (human-only)

The same three-step gate cards use:
1. **New trigger** — emit `Relic.trigger_<x>` at the right point in `CombatManager`, add it to
   `RELIC_TRIGGERS` (`ContentValidator.gd`) and `relic.schema.json`, and give it a row above.
2. **New modifier stat** — read it in the relevant compute pipeline, add it to `RELIC_MOD_STATS` and
   the schema, document it.
3. **New effect op** — that's a card-vocabulary change (see VOCABULARY.md); relics get it for free.

Counters/periods ("every 3rd attack", "every 6 turns") are **not yet expressible** — they'd need a
per-relic counter primitive. Add it deliberately if a relic needs it.
