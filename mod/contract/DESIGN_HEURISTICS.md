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
(an `add_trigger` power, a `when`-gated payoff, a `scale` amount, repeated `hits`, an `add_card` \
loop, X-cost, a `grow` attack, a `transform_card` rank-up) or splashy headline numbers. \
A rare with one plain effect at common-tier numbers is a DESIGN FAILURE and will be flagged.

<!-- heuristic: reprint_section -->
# THE EXISTING CARD POOL (reprint discipline)
Every card below already exists in the game. A design whose effects rebuild one of these
lines -- the same effect skeleton with identical or merely nudged numbers -- is a functional
REPRINT, not a new card. The validator HARD-REJECTS reprints at uncommon and rare and flags
them at common. An occasional familiar effect at common is fine; an uncommon or rare must be
a design that does NOT already exist -- when a concept lands on one of these lines, compose
differently (a `when` gate, a `scale` amount, extra `hits`, an `add_trigger` engine, `add_card`
recursion, X-cost, `grow`, `transform_card`) instead of renaming a stat line.

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
- **Passive modifier** — NO hook; a single `modifiers[]` entry (`first_attack` / `start_combat_block` / \
`attack_base`). Cf. Akabeko, Anchor, Vajra. The simplest form; fits tempo / aggro / any class that just wants a \
clean always-on edge. (`max_energy` / `cost_reduction` are NOT in this form -- they are boss power and only ship \
as a Boon with a price, below.)
- **Counter relic** — `on_card_played` (+ `card_type` attack/skill/power) or `turn_start`, with `every_n` 2-5 -> \
a MEDIUM payoff on the Nth occurrence (Block 3-5, draw 1, a 1-stack buff, or 3-5 damage to `enemy`). Cf. \
Shuriken, Nunchaku, Ink Bottle. Fits attack-spam / skill-spam / tempo classes; the running count on the relic \
icon makes the loop legible. Keep N >= 3 on `on_card_played` (it fires per card).
- **Boon with a price** — ONE flat modifier that is boss power alone (`max_energy 1` or `cost_reduction 1`) PAID \
FOR by a drawback: `max_hp` -8 to -15, or a per-turn cost hook (`turn_start` -> `lose_hp` 2 / `discard` 1 / a \
self `weak` 1). Cf. Coffee Dripper, Ectoplasm, Cursed Key. The one form where a second hook is expected; the \
price must be felt every fight and never refunded by the deck (see the HP economy rule).
- **Bleed payoff** — `on_hp_lost` (fires on your OWN-turn, self/card-caused HP loss: `lose_hp` costs and \
self-damage; enemy hits fire `attacked` instead) -> ONE small buff or Block (1-2). Cf. Rupture. Fits bleed / \
sacrifice / berserker classes. Respect the HP economy rule: the payoff is Strength / Block / draw, NEVER a heal \
that refunds the HP just spent -- the relic must not turn the class's blood price into a wash.
- **Class-kind boon** — the class-conditional ops on a `turn_start` + `once_per_combat` hook: `forge` for a \
Forge class (a smoldering heirloom: Forge 1-2 at combat start), `channel_orb` for an orb class (Cracked Core), \
`summon` for a summon class (the companion that walks in with you). Only if the class HAS that kind -- the op \
is a no-op otherwise. Prefer this over a generic boon whenever the class's identity IS its kind.

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

<!-- archetype-note: retain_hold -->
Retain is a tempo tax the class pays voluntarily, so the `cards_retained` payoff must be worth the held turn: 2-3 damage/Block per retained card, and remember a 5-card hand caps it (a 4-retained turn should feel like a rare, not a routine). Only 1-2 cards read scale:"cards_retained"; the rest are cheap retain enablers and draw. Don't ALSO over-stat the retained cards themselves -- the payoff is the release, not the hold.

<!-- archetype-note: forge_ramp -->
Forge is a per-combat counter, so price income low (Forge 1-3 per card, 1-2 per turn from a power) and let the scale:"forged" payoff attacks carry the class -- 1-2 payoff attacks plus at most one `blade_empower`. Income without a payoff (or the reverse) is a broken class, and a x3 blade_empower must be a rare with a real cost (exhaust or 2+ energy). Never stack Forge income with an unconditional Strength engine: the ramp IS the class's Strength.

<!-- archetype-note: rampage_grow -->
`grow` is one card feeding itself, so the growth step is small (2-4 per play) and the base damage sits BELOW a same-cost Strike: weak on swing one, a finisher by swing four. Keep to 1-2 grow attacks per class, backed by cheap draw/retain so it recurs, and NEVER give a grow card an add_card self-copy (two copies growing in parallel is a one-card engine).

<!-- archetype-note: battle_smith -->
Combat-scoped upgrades are a tempo resource: cards:"choose" and cards:"random" belong on cheap (0-1 cost) skills, cards:"all" is an uncommon-or-rare swing that wants a real cost. 1-2 upgrade cards per class, plus at most one turn_start random-upgrade power at rare. The upgrades ARE the value -- don't also over-stat the smithing card itself.

<!-- archetype-note: ascetic_purge -->
A `purge` card is spent ONCE for the whole run, so over-stat it for its cost (about one rarity tier up) -- but keep purge/purge_card to 1-3 cards per class and never on a basic. The draw_pile_empty finisher gets Grand-Finale numbers precisely because a thinned deck is the price; ONE such finisher per class. Don't pair purging with a conjure/compost loop -- a class that both thins and manufactures copies is fighting itself.

<!-- archetype-note: poison_attrition -->
Poison is damage-over-time that ignores Block, so price it below direct damage: 3-5 Poison on a common, 6-9 on an uncommon, and a rare that doubles or spreads it. The payoff is the slow tide -- 1-2 poison-scaling cards at most, and never a target_has_status:poison gate on every attack. Don't stack Poison with big front-loaded damage on the same card; the class wins over turns, not in one.

<!-- archetype-note: block_bulwark -->
Block is cheap to print, so the ENGINE is the identity: on_block_gained / turn_end payoffs at 1-3 per fire, Dexterity at +1/+2 (never +3 on a common). One barricade-style retention effect per class MAX, and a Block-into-damage attack (Body Slam) counts as the class's payoff -- one or two, not every attack. Block numbers on skills stay Defend-tier (5-8 at 1 energy); the engine does the compounding.

<!-- archetype-note: strike_tempo -->
The flurry is repeated `hits` on one target -- amount x hits should total a little BELOW a same-cost single-hit Strike (Strength and Vulnerable are what make it pull ahead). One decisive finisher per class (a rare at 2-3 energy or X-cost); everything else is cheap swings. Don't put a per-hit Strength engine AND the hits payoff on the same rare.

<!-- archetype-note: orb_channel -->
Orbs are per-turn value, so the channel cards themselves are cheap (0-1 cost) and modest; the burst is `evoke`. Focus is the priciest number: +1 per card at uncommon, +2 only at rare with a cost, and NEVER a per-turn Focus power. One gain_orb_slot card (or a slot on the rare power) per class -- every extra slot makes every orb card better and compounds fast. A custom orb's `when`-gated effect (v49) is the cheap way to pay off orb COUNT without Focus (a Glass evoke that shatters harder with 3+ orbs); a Plasma-style energy passive (`passive_timing` turn_start) is worth a full energy per turn per orb -- cap it at 1 and never stack it with `max_energy`.

<!-- archetype-note: slot_machine -->
The jackpot is `orbs_match`: a channel_orb orb:"random" pull is a gamble, so the matched payoff must be BIG (rare-tier numbers) while the pull itself is cheap and unmatched orbs still tick for value. Gate at most 1-2 cards on orbs_match; the rest are pulls, orb_count_ge filler, and evoke. Don't let the class also print Focus stacks -- guaranteed value cancels the gamble.

<!-- archetype-note: summon_swarm -->
ONE minion at a time, so `summon` is the class's setup card (HP 8-15 at 1-2 cost; re-summoning raises Max HP) and the payoff is summon_attack (per-hit damage BELOW a same-cost Strike, since the pet's Strength scales it). buff_summon Strength at +1/+2; heal_summon/shield_summon in the 3-6 band, and at most one per-turn medic power. Never put a summon on a basic, and never stack a summon-buff engine on top of a player-Strength engine. The pet's hits count as YOU dealing damage, so `on_damage_dealt` + summon_attack is the class's pack-tactics engine (once_per_turn; small reward).

<!-- archetype-note: status_signature -->
The custom status IS the class, so its per-stack number must be small (1-2 damage/Block per stack) and its appliers cheap; the rare is the multiplier that reads the stack count, not a bigger applier. 3-6 cards apply the status, 1-2 cash it in. Don't also give the class a second base-game engine (Poison, Strength ramp) -- the signature status should be the only counter the player is watching. A `damage_over_time` status is priced like Poison (3-5 stacks on a common applier, 6-9 on an uncommon; it ignores Block, so never above direct damage); a `hit_count` stance is worth a whole card per stack (1 stack on a 1-cost, `lose_all_eot`), never a permanent counter; a `multiplicative` damage status is a Vulnerable-like scaler, so its appliers read 2-4 stacks (+20-40%), not 10.

<!-- archetype-note: tempo_draw -->
Draw and energy are the most abusable numbers: draw 1-2 on a common (3 at uncommon with a cost), gain_energy 1 per card and never on a 0-cost card without exhaust. The snowball turn is the payoff -- a rare that scales with the turn, not a cheap draw-3. Never a per-turn gain_energy power below rare, and never draw + energy + damage on one common. A cost_shift discount (v45) is energy in disguise: price a this-turn typed discount at about two-thirds of gain_energy, and a whole-combat one is rare-only (amount 1, one per class).

<!-- archetype-note: debuff_expose -->
Vulnerable/Weak are worth about half a card's damage, so the appliers are cheap (1-2 stacks per common) and the payoff attacks read target_has_status / scale:"target_debuff_count" at 2-4 per debuff. 1-2 payoff attacks per class MAX -- a class where every attack gates on Vulnerable just plays Bash forever. Don't stack the debuff-count scalar with `hits` on the same card.

<!-- archetype-note: power_ramp -->
Per-turn powers compound, so each fires for 1-2 (Strength +1/turn is rare-tier; Block/draw drips are uncommon). Two ramp powers per class MAX, and the class needs cheap early cards to survive turns 1-3 (the payoff is the long game, not the opener). Never stack two Strength-per-turn engines, and never put a ramp power at common.

<!-- archetype-note: countdown_ripen -->
A `ripen` payload fires ONCE after N turns, so pay for the wait: the payload should be about 1.5x what an immediate effect at that cost would print, with amount 2-3 turns (a 1-turn ripen is just a slow card; 4+ never fires in a 3-turn hallway fight). Keep 2-3 ripen cards per class and pair them with per-turn survival, never a second ripen on the same card.

<!-- archetype-note: balance_gauge -->
The gauge bites at |8|, so income is balance_step 1-3 per card, and the class needs income on BOTH poles plus at least one `centered` payoff -- a one-pole class is just Forge with extra steps. The pole payoffs (light_ge/dark_ge 4-6) are the rare-tier cards; don't also give the class unconditional big numbers, and never make the penalty pole the only income (the player must be able to steer back).

<!-- archetype-note: madness_discard -->
Discard is RANDOM from hand by default, so the cost must be real (1-2 cards per enabler) and the `on_discard` fuel cards read 4-8 Block/damage when pitched (they're dead in hand otherwise); a `cards:"choose"` discard (v46) is card selection, not a cost -- pay for it like a small scry. `retrieve_card` (v46) is recursion: a chosen return is a tutor (draw-priced), an exhaust-pile return is Exhume (uncommon+, exhaust the retriever). `add_status_card` (v46) is a price, never a payoff: only on a card that is clearly over-statted for its cost, at most two such cards per class. 2-3 fuel cards + 2-3 enablers + one scry per class; a discard payoff that also draws replaces its own cost and becomes free churn -- gate it once_per_turn. Never a turn_start discard power below uncommon.

<!-- archetype-note: token_conjurer -->
`add_card` copies are combat-transient, so a token's value is what it does when played: keep tokens cheap (0-1 cost) and modest, and the conjurer pays a fair rate for 1-3 copies. A self-copying card sends copies to the DISCARD pile (Anger), never hand, and the on_exhaust -> add_card compost engine is the class's rare. Never conjure a card that itself conjures (depth-1), and never conjure a grow/forge payoff.

<!-- archetype-note: exhaust_pyre -->
`on_exhaust` fires per card, so the payoff is 1-3 per fire (Feel-No-Pain-tier Block; 1 Strength only at rare) and the class needs 3-4 cheap exhaust fodder cards to feed it. corruption is at most ONE card per class, rare, and the exhaust payoffs are priced knowing Skills are free under it. Don't stack an on_exhaust engine with an add_card compost loop AND corruption -- pick two.

<!-- archetype-note: strike_synergy -->
scale:"tag_cards_owned" reads the run deck, so the per-tag step is small (2-3 damage per tagged card) and the base damage sits below a Strike; the payoff scales with DRAFTING, not with the turn. One or two payoff cards per class, and the tagged family itself must be plain (Strike-tier) -- if the tagged cards are also good, the class is over-tuned twice. Never pair the tag scalar with `hits`.

<!-- archetype-note: metamorph -->
A `transform_card` rank-up is a permanent upgrade, so the weak form is genuinely weak (common-tier or worse) and its `when` gate must take real setup; the strong form is priced as a rare. Keep transform/graft to 1-3 cards per class, never on a basic, and never chain (A<->B only). A mode-swap pair should be two SIDEGRADES, not a weak card and a strong one.

<!-- archetype-note: big_energy -->
gain_energy is worth a card's whole cost, so an energy card must give something up (exhaust, lose_hp, or a 2+ cost that nets 1). The payoff is 2-3 cost / X-cost cards with headline numbers -- 1-2 per class, rare. Never a per-turn energy power below rare, and never energy gain + draw on the same common.

<!-- archetype-note: counter_riposte -->
Thorns and `attacked` payloads fire per enemy hit, so numbers are small (Thorns 2-4, riposte damage 3-6) because enemy crowds multiply them. on_hp_lost here is the self-damage twin -- if the class bleeds for its counters, the HP economy rule applies (net-negative, no same-card refund). One retaliation power per class MAX; the cards are Block and a couple of hit-back attacks, not five thorns sources.

<!-- archetype-note: threshold_duelist -->
A `when` gate is a discount: the gated payoff prints about 1.5x its ungated cost, and the gate must be one the player can ENGINEER (no_block, turn_at_least 3, hp_below_half), not luck. 2-3 gated payoffs per class; the rest must work ungated or the deck bricks when the moment never comes. Don't stack two gates on one card, and never gate a basic.

<!-- archetype-note: horde_breaker -->
all_enemies damage is worth 2-3x single-target against a crowd and nothing extra against a boss, so price AoE at about 60% of a single-target card and let `enemy_count_ge` unlock the headline numbers. One or two count-scaled payoffs per class; the class still needs 2-3 single-target attacks for elites. Never combine `hits` with all_enemies below rare.

<!-- archetype-note: ambush_alpha -->
`innate` guarantees the opening hand, so an innate card is priced as if it's played EVERY fight: modest (a 1-cost 8 damage, or +1 energy), and 1-2 innate cards per class MAX. The burst wants a finish -- past turn 3 the class is on its back foot -- so make the rare a tempo swing, not a third innate. Never innate + gain_energy + draw on one card.

<!-- archetype-note: fleeting_flux -->
`ethereal` over-stats by about 30% (a 1-cost 9 damage, a 1-cost 8 Block) because the card is wasted if unplayed -- that IS the tax, so don't add exhaust on top. 3-5 ethereal cards per class with cheap draw to cycle into them; the rare is the payoff that rewards the churn, not a bigger ethereal. Never ethereal on a basic or a power.

<!-- archetype-note: untouchable_ward -->
Exotic mitigation is stronger than Block: Intangible 1 is rare-only with a real cost, Buffer 1-2 and Artifact 1-2 at uncommon, Blur 1-2. One of each per class at most, never two on the same card, and never a per-turn power granting any of them below rare. The class still needs Defend-tier Block for the turns the wards are down.

<!-- archetype-note: burst_window -->
temp_strength / temp_dexterity expire at end of turn, so price them at about a third of permanent Strength: +3-4 temp Strength at 1 cost is fine, but it needs several attacks the same turn or it's wasted -- draw/energy on the burst card is the enabler. One or two burst cards per class; never stack temp Strength with a permanent Strength ramp, and never a per-turn temp-stat power (that's just permanent Strength). temp_thorns / temp_focus (v44) follow the same one-turn pricing: about half of permanent Thorns / Focus, and the card wants a reason the turn matters (an enemy attack incoming; an evoke this turn).
