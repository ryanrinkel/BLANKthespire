# Effect Vocabulary — the Content Generation Contract

This document is the **closed vocabulary** all content is built from. It is paired with the JSON Schemas in `core/validation/schema/`. Together they are:

- the **authoring reference** for humans,
- the **generation prompt** for the future LLM pipeline,
- the **definition** the `ContentValidator` enforces.

**Golden rule:** content (cards, enemies, relics) is composed *only* from the ops, statuses, and targets below. Nothing here lets data invoke new behavior. When a desired mechanic isn't expressible, a **human adds one primitive** (a small GDScript class + a schema entry + a row in this doc) — the model never writes code. Growing this table is how the model's expressive range expands safely.

---

## Effect ops

Each effect is `{ "op": "...", ... }`. `amount`/`times`/`value` accept a **scalar** (see below).

| op | fields | meaning | notes |
|----|--------|---------|-------|
| `damage` | `amount`, `raw?` | Deal attack damage to the card/move target. | Routed through the damage pipeline: +Strength → ×Weak → ×Vulnerable → −Block. Counts as an "attack" for triggers. `raw: true` deals the fixed amount straight through Block only — no Strength/Weak/Vulnerable, no Akabeko/Thorns (fixed-damage relic ticks like Bronze Scales / Mercury Hourglass). |
| `block` | `amount` | Gain Block (absorbs damage until your next turn start). | Routed through +Dexterity → ×Frail. |
| `apply_status` | `status`, `amount`, `to?` | Apply N stacks of a **declared status**. | `status` must exist in `data/statuses/`. Routing: by default a **buff** lands on the actor and a **debuff** on the receiver; `to` (`self`/`target`) overrides this for off-side cases (Disarm: `−strength` `to:target`). `amount` may be negative. |
| `draw` | `amount` | Draw N cards. | Reshuffles discard→draw (seeded) if needed. Suppressed if `no_draw_this_turn` flag set. |
| `gain_energy` | `amount` | Gain N energy this turn. | |
| `lose_hp` | `amount` | Lose HP directly, ignoring Block. | Self-damage (Bloodletting). Use on `self` targets. |
| `heal` | `amount` | Restore HP up to max. | |
| `add_card` | `card_id`, `pile`, `amount?` | Create N copies of a card into hand/discard/draw. | `card_id` must exist. Used for card-gen (Anger) and status-cards (Slimed). |
| `multi` | `times`, `effects[]` | Run a sub-effect list N times. | The combinator for multi-hit (Twin Strike) — Strength applies per hit. |
| `from_state` | `emit`, `value` | Emit a `damage`/`block`/`heal` whose magnitude is read from live state. | Body Slam = `emit: damage, value: {state: block}`. |
| `conditional` | `if`, `then[]`, `else?` | Run `then` if predicate true, else `else`. | Predicate tests combat state (see schema `$defs/predicate`). |
| `set_flag` | `flag` | Set a turn-scoped flag. | Currently only `no_draw_this_turn` (Battle Trance). |
| `fuse` | `turns`, `scope?`, `effects[]`, `label?` | Plant a **delayed charge**: after `turns` of your end-of-turns, run `effects` once per target in `scope` (`all` = every enemy **and you** \| `all_enemies` \| `self`). | Detonates at the END of your turn, so a same-turn **Burrow** protects you. **Sourceless**: no Strength scaling, but the target's Vulnerable amplifies it, Burrowed nullifies it, and Block soaks it (the Armor Dillo mining combo). Miner's TNT = `turns:3, scope:all, effects:[{damage 24}]`. |

### Scalars
An `amount`/`times`/`value` is either:
- an **integer**, or
- a **state reference**: `{ "state": "<name>", "scale": <number=1> }`.

Allowed `state` names: `block`, `energy`, `strength`, `hand_size`, `cards_played_this_turn`, `hp_lost`.

---

## Targets (card-level `target`)

| target | meaning |
|--------|---------|
| `self` | The player. Use for block/draw/buff/self-damage. |
| `enemy` | A single enemy the player picks. |
| `random_enemy` | One random (seeded) enemy. |
| `all_enemies` | Every living enemy (AoE). |
| `none` | No target needed (pure self/utility with effects that target self implicitly). |

---

## Statuses / Powers (apply via `apply_status`)

Each has a hand-written behavior class in `core/powers/` and a declaration in `data/statuses/`. The model may **apply** these; it does not define new ones.

| id | kind | decay | effect |
|----|------|-------|--------|
| `vulnerable` | debuff | decrement/turn | Target takes ×1.5 attack damage. |
| `weak` | debuff | decrement/turn | Target deals ×0.75 attack damage. |
| `strength` | buff | none | +N attack damage per hit (permanent for the combat). |
| `strength_temp` | buff | remove/turn | +N attack damage per hit, but **removed at the end of your turn** (Flex-style burst). Stacks additively with `strength`. Use this for cheap "gain Strength this turn" cards so they don't power-creep permanent-Strength sources. |
| `dexterity` | buff | none | +N Block gained. |
| `frail` | debuff | decrement/turn | ×0.75 Block gained. |
| `ritual` | buff | none | (enemy) gain N Strength at end of turn. |
| `armor` | buff | none | **Barricade:** while you have it, your Block stops resetting between turns and accumulates. Presence is what matters (stack count unused). (Armor Dillo keyword.) |
| `burrowed` | buff | remove/next-turn-start | **Underground:** invulnerable to attacks (incoming attack damage ×0) until your next turn; while burrowed you **cannot play Attacks**. Clears at your next turn start, so it covers exactly the next enemy turn. Raw/`lose_hp` damage still gets through. (Armor Dillo keyword.) |

> **Permanent vs temporary Strength:** `strength` lasts the whole combat — it is power-tier value (cf. Inflame: an *uncommon power*, 1 energy, +2 `strength` and nothing else). Reserve permanent Strength for powers / exhaust / conditional cards. For cheap repeatable skills, use `strength_temp` (built 2026-06-08): the burst lasts only the turn you play it, so a 1-energy "gain Strength" skill stays fair.

---

## Intents (enemy move `intent`)

Display-only telegraph derived from a move's primary effect: `attack`, `block`, `buff`, `debuff`, `attack_block`, `attack_buff`, `unknown`.

---

## Balance guidance (validator: warn, don't reject)

A rough power score the validator uses to flag outliers. Tune against StS2 reference numbers in M4.

- **Damage** ≈ 1 point / dmg. **Block** ≈ 0.8 / block. **Draw** ≈ 5 / card. **Energy** ≈ 6 / energy. **Status** ≈ apply-amount × (2 vulnerable, 1.5 weak, 4 strength). `lose_hp` is a **discount** (negative cost).
- Expected score by cost (basic/common): roughly `cost × 7 (+5 baseline)`. Uncommon/rare may exceed by design.
- Hard rejects (not warnings): unknown `op`/`status`/`target`, missing required field, `card_id`/`status` reference that doesn't resolve, `cost` out of range.

---

## Extending the vocabulary (human-only)

To add a primitive: (1) add the `op`/state/status to the relevant schema, (2) add its row here with semantics, (3) implement the behavior class. Only after all three does generated content gain access to it. This three-step gate is the contract boundary between safe code and open generation.
