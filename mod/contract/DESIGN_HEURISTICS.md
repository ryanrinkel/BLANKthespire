# DESIGN HEURISTICS — the single source for the forge's design rules

This file is the **one place** to add, tweak, or remove the design heuristics the creative harness
injects into its prompts. It is plain prose — **no code change is needed to edit a rule**. Edits ship
to a live deployment through the normal flow: `git push` → pull + redeploy on the server
(the file is read by path at forge time, so a deps reinstall isn't required for it to take effect).

## How it works (so you can edit safely)

Each rule is a block introduced by an HTML-comment **marker**. The harness extracts the text between a
marker and the next marker. There are two kinds:

- `<!-- heuristic: KEY -->` — a **global** rule folded into the card / blueprint / relic prompts.
  The `KEY` is matched in code (`contract.py`), so **don't rename a key** unless you also change its
  reader. The prose under it is free to rewrite however you like.
- `<!-- archetype-note: ARCHETYPE_ID -->` — a **per-archetype** balance note. The `ARCHETYPE_ID` must
  match an `id` in `archetypes.json`. It surfaces as the `balance:` line for that archetype in the
  MAP/compose stage. To add a note to another archetype, copy the block and change the id.

Notes:
- Two global rules (`rarity_ladder`, `reprint_section`) have a **dynamically generated tail** appended in
  code — the live card pool and the real StS2 examples. Only the static *rule* prose lives here; the data
  tail is added automatically. Everything else in the matching block is yours to edit.
- A `\` at the end of a line is a soft line-wrap (the readers join wrapped lines). Keep it or drop it —
  it only affects how the prose is reflowed into the prompt.
- Backtick-quoted `tokens` are not parsed here (unlike VOCABULARY.md); write freely.

---

# GLOBAL HEURISTICS

<!-- heuristic: rarity_ladder -->
# THE RARITY LADDER (how power and complexity scale with rarity)
- basic: deliberately plain (Strike/Defend tier). Never exciting.
- common: ONE clear, simple effect — a cheap enabler that feeds an archetype. 1-2 effect \
nodes, modest numbers.
- uncommon: an AMPLIFIER — two effects, a condition, or a twist that visibly rewards \
committing to an archetype.
- rare: the archetype PAYOFF — the card players draft the whole deck around. It must be \
clearly stronger than a same-cost common AND read more ambitious: a build-around engine \
(multi / conditional / from_state / fuse compositions, X-cost) or splashy headline numbers. \
A rare with one plain effect at common-tier numbers is a DESIGN FAILURE and will be flagged.

<!-- heuristic: reprint_section -->
# THE EXISTING CARD POOL (reprint discipline)
Every card below already exists in the game. A design whose effects rebuild one of these
lines -- the same effect skeleton with identical or merely nudged numbers -- is a functional
REPRINT, not a new card. The validator HARD-REJECTS reprints at uncommon and rare and flags
them at common. An occasional familiar effect at common is fine; an uncommon or rare must be
a design that does NOT already exist -- when a concept lands on one of these lines, compose
differently (conditions, scaling, multi, X-cost, recursion) instead of renaming a stat line.

<!-- heuristic: loop_discipline -->
# LOOP DISCIPLINE (combo engines must be earned)
Infinite or self-sustaining loops are welcome, but only as EARNED payoffs: an engine that \
can iterate without bound must take at least THREE distinct cards to assemble, OR charge a \
real price per iteration (>= 2 net energy, meaningful HP loss, or exhaust). A card that \
re-adds ITSELF to hand for 0-1 net energy is a one-card engine and a design failure (the \
validator flags it for review); so is a two-card A<->B free loop. The sanctioned self-copy \
pattern sends copies to the DISCARD pile (cf. Anger) -- the deck cycle gates each iteration.

<!-- heuristic: hp_economy -->
# HP <-> STRENGTH ECONOMY (sacrifice must cost something)
Strength is the most expensive buff in the game: it is permanent and compounds across every later \
attack. Price self-inflicted Strength at AT LEAST 3 HP per 1 Strength at baseline, and vary from \
there -- charge MORE when the Strength is unconditional/immediate or stacks every turn, LESS when it \
is one-shot, conditional, or capped. A "lose HP for Strength" engine only creates strategic tension \
if the HP it spends stays NET NEGATIVE over the loop: never hand back (heal/regen/lifesteal) as much \
or more HP than the same card or per-turn loop spends, or the cost is a fiction and the "berserker \
bargain" has no downside. A relic/card that loses 1 HP for +1 Strength and then heals >=1 HP is a \
free permanent buff -- a design failure; either drop the heal, make the heal smaller than the loss, \
or raise the HP price so the player genuinely bleeds for the power.
CREATIVE DEFAULT -- don't put healing and an HP cost on the SAME card/relic. A card/relic that both \
spends HP (lose_hp, an HP payment) and restores it (heal/regen) cancels its own cost and reads as a \
wash; it almost always wants to be one or the other. Let the COST live here and pay it back ELSEWHERE \
-- a different card, relic, or the run's wider HP economy -- so each piece stays legible and the \
sacrifice is felt. Break this only with a deliberate reason (e.g. a heal strictly smaller than the \
loss used as drawback mitigation, or a conditional lifesteal that can whiff), never by reflex.

---

# RELIC DESIGN

<!-- heuristic: relic_forms -->
# RELIC FORMS (a forged starter relic is ONE keystone idea)
A forged class's keystone is its STARTER relic: always-on, so it must be small AND simple. Pick EXACTLY \
ONE form below and fill it for this class. Default to a SINGLE hook (or a single modifier, no hook). A \
second hook is allowed ONLY when it is a genuine drawback/cost that creates tension (see the HP economy \
rule) -- NEVER add a hook just to nod at the second archetype. Lead with the class's DOMINANT archetype; \
the other archetype lives in the name and flavor, not in extra mechanics. If you can't say the relic in \
one sentence, it's too complicated.

Choose the form that matches what the class's dominant archetype already WANTS to do:

- **Combat-start boon** — `turn_start` + `once_per_combat` -> ONE buff (or `channel_orb` for orb classes, \
`summon` for summon classes). The default keystone; cf. Cracked Core, Anchor. Fits almost any class.
- **Per-turn drip** — `turn_start` (every turn) -> a SMALL recurring buff or block (1-2). Fits block / \
power-ramp / engine classes. Keep numbers tiny: they fire every turn.
- **Reactive counter** — `attacked` -> small damage to the `attacker` (thorns) or a small self-buff. Cf. \
Bronze Scales. Fits block / retaliation / "punish the aggressor" classes.
- **Do-what-you-do payoff** — hook the action the class SPAMS (`on_card_played` / `on_exhaust` / \
`on_block_gained` / `on_damage_dealt` / `on_card_drawn`) -> a small reward; gate with `once_per_combat` \
if the trigger fires often. This is usually the most identity-defining form -- it rewards the core loop \
directly. Fits combo / tempo / exhaust / block-engine classes.
- **Victory heal** — `combat_end` -> `heal` only. Cf. Burning Blood. Fits attrition / sacrifice / \
lifesteal-flavored classes (and respects the HP economy rule: the heal is the payoff for surviving, not a \
same-turn refund of a cost).
- **Passive modifier** — NO hook; a single `modifiers[]` entry (`max_energy` / `first_attack` / \
`cost_reduction` / `start_combat_block`). Cf. Energy Core, Akabeko. The simplest form; fits tempo / aggro \
/ any class that just wants a clean always-on edge.

Note on the bleed/sacrifice archetype: there is no "whenever you lose HP" trigger yet, so a bleed payoff \
relic uses either a **Reactive counter** (`attacked`) or a **Per-turn drip** gated by `when hp_below_half` \
("power up while wounded") -- not a literal on-HP-loss hook.

---

# PER-ARCHETYPE BALANCE NOTES

<!-- archetype-note: strength_berserk -->
Strength is the priciest buff: it is permanent and compounds every attack. When this class buys Strength with HP, charge AT LEAST 3 HP per 1 Strength at baseline and vary from there (more when the Strength is unconditional/per-turn, less when one-shot or conditional). The HP cost must stay NET NEGATIVE over the loop -- never refund (heal/regen) as much HP as the bargain spends, or the sacrifice has no tension.

<!-- archetype-note: self_sacrifice -->
The 'claw it back' is a DECK-WIDE economy, not a same-card refund: put the HP cost on one card and the healing on DIFFERENT cards, never both on the same card/relic (a card that spends HP and heals it cancels its own cost). Even across the deck the clawback must stay net-negative over a loop. If HP is traded for Strength, price it at >=3 HP per 1 Strength at baseline (see strength_berserk).

<!-- archetype-note: reaper_lifesteal -->
Full lifesteal (a `heal` scaled by `damage_dealt_unblocked`) is rare-tier power: 1-2 cards per class MAX, uncommon or rare only -- never on a basic or common -- and the biggest one wants `exhaust` or a condition. Sustain must be able to LOSE to incoming damage on a bad turn: the identity is winning attrition SLOWLY, not making damage irrelevant. Never stack a second sustain engine on top -- if the cards carry lifesteal, the starter relic must NOT also heal in combat (pick another relic form; a `combat_end` victory heal is the sanctioned exception), and a passive per-turn heal power counts as one of the 1-2 lifesteal slots.

<!-- archetype-note: iron_regrowth -->
Healing is the win condition, so ration it like one: small numbers on repeatable heals (1-3 HP), and anything bigger gated (once per combat, conditional, or exhaust). The class's total per-turn sustain -- cards plus powers plus relic -- must stay BELOW what a hard-hitting enemy turn deals, so the regrower survives by outlasting, not by being unhittable. Don't stack sustain engines: if the cards heal, the starter relic must NOT also heal in combat (a `combat_end` victory heal is fine), and keep passive per-turn heal powers to ONE per class.
