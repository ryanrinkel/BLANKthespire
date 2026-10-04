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
The 'claw it back' is a DECK-WIDE economy, not a same-card refund: put the HP cost on one card and the healing on DIFFERENT cards, never both on the same card/relic (a card that spends HP and heals it cancels its own cost). Even across the deck the clawback must stay net-negative over a loop. If HP is traded for Strength, price it at >=3 HP per 1 Strength at baseline (see strength_berserk). Self-drawbacks (v65) are prices like `lose_hp`: `lose_strength` 1-2 / `lose_dexterity` 1 on a strong card (Friendship, Shared Fate), `no_block_gain` 2 turns on a big-Block exhaust (Panic Button), `dex_decay` 1 on a rare Power with a headline payoff (Wraith Form). Your own Artifact eats these (they are debuffs), so never pair them with a self-`artifact` on the same card.

<!-- archetype-note: reaper_lifesteal -->
Full lifesteal (a `heal` scaled by `damage_dealt_unblocked`) is rare-tier power: 1-2 cards per class MAX, uncommon or rare only -- never on a basic or common -- and the biggest one wants `exhaust` or a condition. Sustain must be able to LOSE to incoming damage on a bad turn: the identity is winning attrition SLOWLY, not making damage irrelevant. Never stack a second sustain engine on top -- if the cards carry lifesteal, the starter relic must NOT also heal in combat (pick another relic form; a `combat_end` victory heal is the sanctioned exception), and a passive per-turn heal power counts as one of the 1-2 lifesteal slots. Blight Strike (v64): `apply_status` `doom` scaled by `damage_dealt_unblocked` after the hit -- price it like the lifesteal heal (uncommon, single-enemy), and keep Doom cards to 4 per class.

<!-- archetype-note: iron_regrowth -->
Healing is the win condition, so ration it like one: small numbers on repeatable heals (1-3 HP), and anything bigger gated (once per combat, conditional, or exhaust). The class's total per-turn sustain -- cards plus powers plus relic -- must stay BELOW what a hard-hitting enemy turn deals, so the regrower survives by outlasting, not by being unhittable. Don't stack sustain engines: if the cards heal, the starter relic must NOT also heal in combat (a `combat_end` victory heal is fine), and keep passive per-turn heal powers to ONE per class.

<!-- archetype-note: retain_hold -->
Retain is a tempo tax the class pays voluntarily, so the `cards_retained` payoff must be worth the held turn: 2-3 damage/Block per retained card, and remember a 5-card hand caps it (a 4-retained turn should feel like a rare, not a routine). Only 1-2 cards read scale:"cards_retained"; the rest are cheap retain enablers and draw. Don't ALSO over-stat the retained cards themselves -- the payoff is the release, not the hold. The on-card payoffs (v58) follow the same tax: a `grow_held` card prints BELOW a same-cost Strike (7 + 4 per held turn, never 10 + 4) and a `held_discount` card is a 2-3 cost bomb that is worth waiting on, 1-2 of each per class; never both on one card, never on a 0-cost. `retain_hand` (v65, Equilibrium) holds the whole hand for one turn: put it on a 2-cost Block skill (12-15 Block), uncommon, one or two per class -- it doubles every `cards_retained` payoff, so never with a `cards_retained` scale on the same card. (v66) `grant_keyword` retain rides a common attack (Snap: 7 damage), `put_back` from hand is a 0-cost draw-2 exhaust (Thinking Ahead), and `return_to_hand` is a 1-cost Defend that keeps coming back (Particle Wall: 9 Block, uncommon, no draw / energy on it); one or two per class. A `cost_delta` on "drawn" (v67, Kingly Kick) is the drawn-twin of held_discount: a 3-4 cost bomb that gets 1 cheaper per draw; never both on one card.

<!-- archetype-note: forge_ramp -->
Forge is a per-combat counter, so price income low (Forge 1-3 per card or per trigger fire) and let the scale:"forged" payoff attacks carry the class -- 1-2 payoff attacks. Income without a payoff (or the reverse) is a broken class. Any effect that multiplies an attack's damage (x2 or more) is a rare with a real cost (exhaust or 2+ energy). Never stack Forge income with an unconditional Strength engine: the ramp IS the class's Strength. For burst prefer `vigor` (v60: +N on the next attack, blade or not) over blade_empower; 1-2 vigor cards per class.

<!-- archetype-note: rampage_grow -->
`grow` is one card feeding itself, so the growth step is small (2-4 per play) and the base damage sits BELOW a same-cost Strike: weak on swing one, a finisher by swing four. Keep to 1-2 grow attacks per class, backed by cheap draw/retain so it recurs, and NEVER give a grow card an add_card self-copy (two copies growing in parallel is a one-card engine).

<!-- archetype-note: battle_smith -->
Combat-scoped upgrades are a tempo resource: cards:"choose" and cards:"random" belong on cheap (0-1 cost) skills, cards:"all" is an uncommon-or-rare swing that wants a real cost. 1-2 upgrade cards per class, plus at most one turn_start random-upgrade power at rare. The upgrades ARE the value -- don't also over-stat the smithing card itself.

<!-- archetype-note: ascetic_purge -->
Thinning here is mostly COMBAT-scoped: exhaust and ethereal are the everyday tools, and permanent `purge` is the rare exception. At most ONE purge-family card per class, and it must be earned: a costly one-shot, or `purge_card` behind a `when` gate the player engineers. Never a cheap, repeatable purge. Exhaust-as-cost cards are fine at 2-4 per class if each one pays back the card it burns (`exhaust_card` v57 counts here: "choose"/"up_to" let the player thin what they pick; `draw_until` is the cycling half). The draw_pile_empty finisher gets Grand-Finale numbers because a thin deck is the price; ONE per class. Don't pair heavy thinning with a conjure/compost loop that refills the deck. Draw-pile tools (v66): a `retrieve_card` `pile:"draw"` tutor is a rare 0-cost exhaust skill (Secret Weapon); `to_draw_top` costs ~2 of value (it is your next draw); an `on_shuffle` power fires often in a thin deck, so 3-4 Block or 1 draw per fire, ONE per class; `shuffle_hand` (Reboot) is a rare exhaust with a big draw.

<!-- archetype-note: poison_attrition -->
Poison is damage-over-time that ignores Block, so price it below direct damage: 3-5 Poison on a common, 6-9 on an uncommon, and a rare that doubles or spreads it. 1-2 poison-scaling cards at most, and never a target_has_status:poison gate on every attack. Don't stack Poison with big front-loaded damage on the same card; the class wins over turns, not in one. An `on_poison_damage` power (v59) fires per poisoned enemy per turn, so its payload is 1-3 Block / 1 draw / 1 debuff and it wants once_per_turn against crowds; ONE such power per class, rare or uncommon, and never a damage payload (Poison already is the damage). An `on_debuff_applied` power with `status` poison (v67) fires per Poison application: keep the payload small (1-2 Block) and never apply Poison in it (the re-entry guard stops the loop, but the card reads wrong).

<!-- archetype-note: block_bulwark -->
Block is cheap to print, so the ENGINE is the identity: on_block_gained / turn_end payoffs at 1-3 per fire, Dexterity at +1/+2 (never +3 on a common). One barricade-style retention effect per class MAX, and a Block-into-damage attack (Body Slam) counts as the class's payoff -- one or two, not every attack. Block numbers on skills stay Defend-tier (5-8 at 1 energy); the engine does the compounding. Enemy Strength loss (v64) is defense too: `temp_strength_down` 3-6 on a 1-cost common (Piercing Wail), the permanent `strength_down` 1-2 at uncommon/rare; Artifact negates either, so pair it with `strip_artifact`. `block_next_turn` (v65) banks Block for next turn at ~0.7 of Block now: a fixed 6-10 rides a Defend-tier skill; Prolong (scale block, your current Block) is uncommon with exhaust, after a Block op on the same card.

<!-- archetype-note: strike_tempo -->
The flurry is repeated `hits` on one target -- amount x hits should total a little BELOW a same-cost single-hit Strike (Strength and Vulnerable are what make it pull ahead). Finishers are big and splashy: rares at 2-3 energy or X-cost, a couple per class at most; everything else is cheap swings. Don't put a per-hit Strength engine AND the hits payoff on the same rare. `draw_until` (v57, Pillage) is priced as draw 2 and belongs on an attack in an Attack-dense deck (card_type non_attack digs to the one Skill); ONE per class, never on a deck that is mostly the wanted type (it would draw one card). `hits_scale` (v63) prices per-hit damage x the expected count: Finisher (`attacks_played_this_turn`, ~2 hits) prints 5-6 per hit at 1 cost, Flechettes (`skills_in_hand`, ~1-2) 4-5; one or two per class, uncommon. A `cost_delta` on "attack_played" (v67, Stomp) is the finisher discount: a 3-cost AoE that is cheap after two Attacks, printed at a fair 3-cost number.

<!-- archetype-note: orb_channel -->
Orbs are per-turn value, so the channel cards themselves are cheap (0-1 cost) and modest; the burst is `evoke`. Focus is the priciest number: +1 per card at uncommon, +2 only at rare with a cost, and NEVER a per-turn Focus power. One gain_orb_slot card (or a slot on the rare power) per class -- every extra slot makes every orb card better and compounds fast. A custom orb's `when`-gated effect (v49) is the cheap way to pay off orb COUNT without Focus (a Glass evoke that shatters harder with 3+ orbs); a Plasma-style energy passive (`passive_timing` turn_start) is worth a full energy per turn per orb -- cap it at 1 and never stack it with `max_energy`. An `on_evoke` power (v67) fires per evoke: 2-3 Block or 1 draw per fire at uncommon.

<!-- archetype-note: slot_machine -->
The jackpot is `orbs_match`: a channel_orb orb:"random" pull is a gamble, so the matched payoff must be BIG (rare-tier numbers) while the pull itself is cheap and unmatched orbs still tick for value. Gate at most 1-2 cards on orbs_match; the rest are pulls, orb_count_ge filler, and evoke. Don't let the class also print Focus stacks -- guaranteed value cancels the gamble.

<!-- archetype-note: summon_swarm -->
Every point of summon HP is effectively a point of player HP, so price it like Block, matching the base-game Necrobinder: about 5-6 HP per energy on basics and commons (Bodyguard 5 for 1, Afterlife 6 for 1), 7 on an uncommon, and a rare may stretch to 8 (Reanimate is 20 for 3). The card validator enforces those caps (a 0-cost card counts as half an energy; an upgrade may add 3). Re-summoning raises Max HP at the same rate. ONE bodyguard at a time; the payoff is summon_attack (per-hit damage BELOW a same-cost Strike, since the pet's Strength scales it). buff_summon Strength at +1/+2; heal_summon/shield_summon in the 3-6 band, and at most one per-turn medic power. Never a summon on a basic, and never a summon-buff engine on top of a player-Strength engine. The pet's hits count as YOU dealing damage, so `on_damage_dealt` + summon_attack is the class's pack-tactics engine (once_per_turn; small reward). An AUTONOMOUS minion's per-turn moves power is priced at 4-6 damage or Block per turn (cap 8 / 6) with 10-20 HP; an ETHEREAL striker (`attackable`: false) never body-blocks, so it takes the low end of that HP band and the high end of the damage band. `sacrifice_summon`'s payoff must be >= 10 Block, 12 damage, or 2 draws + 1 energy.

<!-- archetype-note: status_signature -->
The custom status IS the class, so its per-stack number must be small (1-2 damage/Block per stack) and its appliers cheap; the rare is the multiplier that reads the stack count, not a bigger applier. 3-6 cards apply the status, 1-2 cash it in. Don't also give the class a second base-game engine (Poison, Strength ramp) -- the signature status should be the only counter the player is watching. A `damage_over_time` status is priced like Poison (3-5 stacks on a common applier, 6-9 on an uncommon; it ignores Block, so never above direct damage); a `hit_count` stance is worth a whole card per stack (1 stack on a 1-cost, `lose_all_eot`), never a permanent counter; a `multiplicative` damage status is a Vulnerable-like scaler, so its appliers read 2-4 stacks (+20-40%), not 10.

<!-- archetype-note: tempo_draw -->
Draw and energy are the most abusable numbers: draw 1-2 on a common (3 at uncommon with a cost), gain_energy 1 per card and never on a 0-cost card without exhaust. The snowball turn is the payoff -- a rare that scales with the turn, not a cheap draw-3. Never a per-turn gain_energy power below rare, and never draw + energy + damage on one common. A cost_shift discount (v45) is energy in disguise: price a this-turn typed discount at about two-thirds of gain_energy, and a whole-combat one is rare-only (amount 1, one per class). History scales (v62): replace-semantics reads are priced at their typical value -- `cards_drawn_this_turn` ~3-5, `to_hand_size` amount 5-7 (Expertise is uncommon); `cards_drawn_this_combat` and `hp_loss_events_this_combat` grow without bound, so they are rare, 2-cost, one per class. A `cost_delta` (v67) counted discount ("Costs 1 less this turn for each Skill you play") belongs on a 2-3 cost card whose printed effect is fair at full price; a +1 tax (Modded) only on a 0-cost draw card.

<!-- archetype-note: debuff_expose -->
Vulnerable/Weak are worth about half a card's damage, so the appliers are cheap (1-2 stacks per common) and the payoff attacks read target_has_status / scale:"target_debuff_count" at 2-4 per debuff. 1-2 payoff attacks per class MAX -- a class where every attack gates on Vulnerable just plays Bash forever. Don't stack the debuff-count scalar with `hits` on the same card. `target_status_stacks` (v62) reads one status's stacks (Bully): with 2-3 Vulnerable up it is a common 1-cost hit; on Poison it is a rare-ish finisher. Expose (v64): `strip_block` / `strip_artifact` go BEFORE the debuff on the same single-enemy card (a strip after the debuff is wasted). Doom (v64) never decays, so it is an execute line: 4-7 per uncommon, 10-12 rare-only, at most 4 Doom cards per class, and a Time's Up payoff (`target_status_stacks` status doom) to cash it. Artifact eats Strength Down and Doom like any debuff. An `on_debuff_applied` power (v67) fires per debuff application (an AoE debuff fires once per enemy): 2-3 damage to `that_enemy` (Sleight of Flesh) or a filtered draw 1 on Vulnerable (Vicious) at uncommon.

<!-- archetype-note: power_ramp -->
Per-turn powers compound, so each fires for 1-2 (Strength +1/turn is rare-tier; Block/draw drips are uncommon). Two ramp powers per class MAX, and the class needs cheap early cards to survive turns 1-3 (the payoff is the long game, not the opener). Never stack two Strength-per-turn engines, and never put a ramp power at common. Trigger filters (v61): a `card_type` filter sees about half the plays, so its payload may be ~1.5x an unfiltered one; an `every_n` payload fires once in N, so print it ~N times bigger (every 3rd Attack -> 4-6 damage); a `scope:"this_turn"` Rage is a 1-cost Skill at 3-4 Block per Attack, and a second copy the same turn adds nothing. Replays (v65): `echo_form` is the rare Power (amount 1, ONE per class, usually ethereal or 3-cost: every first card of the turn plays twice); `replay_next` power (Signal Boost: your next Power plays twice, persists until used) is an uncommon 1-cost Skill.

<!-- archetype-note: countdown_ripen -->
A `ripen` payload fires ONCE after N turns, so pay for the wait: the payload should be about 1.5x what an immediate effect at that cost would print, with amount 2-3 turns (a 1-turn ripen is just a slow card; 4+ never fires in a 3-turn hallway fight). Keep 2-3 ripen cards per class and pair them with per-turn survival, never a second ripen on the same card. Doom (v64) is the enemy-side countdown: it kills at the end of the enemy turn once HP <= Doom and never decays -- 3-5 per card stacks toward the execute; 10+ is rare-only.

<!-- archetype-note: balance_gauge -->
Income is balance_step 1-3 per card; the class needs income AND payoffs on both poles plus at least one `centered` payoff -- a one-pole class is just Forge with extra steps. The engine applies a penalty at |8| (Dark: lose 3 HP per turn; Light: gain 1 Weak per turn), so pole payoffs should switch on around 4-6, before the penalty zone. They're the rare-tier cards; don't also give the class unconditional big numbers, and the player must always be able to steer back.

<!-- archetype-note: madness_discard -->
Discard is RANDOM from hand by default, so the cost must be real (1-2 cards per enabler). A card's `on_discard` bonus should be a modest extra (2-5 Block/damage/draw) on top of a card that is fair to play normally. A `cards:"choose"` discard (v46) is card selection, not a cost -- price it like a small scry. `retrieve_card` (v46) is recursion: a chosen return is a tutor (draw-priced), an exhaust-pile return is Exhume (uncommon+, exhaust the retriever). `add_status_card` (v46) is a price, never a payoff: only on a card that is clearly over-statted for its cost, at most two such cards per class. A discard payoff that also draws replaces its own cost and becomes free churn -- gate it once_per_turn. Never a turn_start discard power below uncommon. `sly` (v56) is the base-game free replay: a Sly card is priced a touch UNDER its cost (the pitch is the rest of its value), 2-4 per class and never without a discard/scry outlet to fire it; never with retain, never on a Power. Recursion (v66): `put_back` from the discard pile rides a full-price attack (Headbutt: 9 damage at 1 cost), `grant_keyword` sly on a Defend-tier skill (Hand Trick: 7 Block), and a `return_next_turn` attack prints LOW (Bolas: 3-4 at 0 cost) because it comes back every turn; one of each per class.

<!-- archetype-note: token_conjurer -->
`add_card` copies are combat-transient, so a token's value is what it does when played: keep tokens cheap (0-1 cost) and modest, and the conjurer pays a fair rate for 1-3 copies. A self-copying card sends copies to the DISCARD pile (Anger), never hand, and the on_exhaust -> add_card compost engine is the class's rare. Never conjure a card that itself conjures (depth-1), and never conjure a grow/forge payoff. An `on_card_generated` power (v67, Arsenal) fires per created card, Wounds too: 1-2 Block per fire at uncommon; Strength per fire is rare-only.

<!-- archetype-note: exhaust_pyre -->
`on_exhaust` fires per card, so the payoff is 1-3 per fire (Feel-No-Pain-tier Block; 1 Strength only at rare) and the class needs 3-4 cheap exhaust fodder cards to feed it. corruption is at most ONE card per class, rare, and the exhaust payoffs are priced knowing Skills are free under it. Don't stack an on_exhaust engine with an add_card compost loop AND corruption -- pick two. `exhaust_card` (v57) is the fuel: 1-3 such cards per class, each paying back the cards it burns (Burning Pact draws 2 for 1; Second Wind blocks 5 per card) -- never a bare "exhaust a card" with nothing attached, and `all` only with a `non_attack` filter or at rare. `exhaust_pile_size` (v62) reads ~2 early and 6+ late: a 1-cost common hit, never a 0-cost one; `exhausted_this_turn` is a ~40% gate, price the bonus at 0.6x. `exhaust_card` `pile:"draw"` (v66) burns a card you have not drawn yet: price it like the hand form, and keep it to choose / random.

<!-- archetype-note: strike_synergy -->
scale:"tag_cards_owned" reads the run deck, so the per-tag step is small (2-3 damage per tagged card) and the base damage sits below a Strike; the payoff scales with DRAFTING, not with the turn. One or two payoff cards per class, and the tagged family itself must be plain (Strike-tier) -- if the tagged cards are also good, the class is over-tuned twice. Never pair the tag scalar with `hits`.

<!-- archetype-note: metamorph -->
A `transform_card` rank-up is a permanent upgrade, so the weak form is genuinely weak (common-tier or worse) and its `when` gate must take real setup; the strong form is priced as a rare. Keep transform/graft to 1-3 cards per class, never on a basic, and never chain (A<->B only). A mode-swap pair should be two SIDEGRADES, not a weak card and a strong one.

<!-- archetype-note: big_energy -->
gain_energy is worth a card's whole cost, so an energy card must give something up (exhaust, lose_hp, or a 2+ cost that nets 1). The payoff is 2-3 cost / X-cost cards with headline numbers -- 1-2 per class, rare. Never a per-turn energy power below rare, and never energy gain + draw on the same common. Double Energy (`gain_energy` scale `energy`, v62) is uncommon with exhaust; `energy_spent_this_turn` is a 0-1 cost late-turn payoff. Whirlwind (`hits_scale:"x"`, v63) is X damage-per-hit at ~2.5 hits: 5 per hit (8 upgraded), uncommon, one or two per class. Drawbacks (v65): `no_draw` is the price of a big draw (Battle Trance: draw 3 at 0 cost, then no more draws this turn -- the validator requires the draw/energy on the same card); `no_energy_gain` follows an energy burst (Expect a Fight). One or two per class. `cost_delta` set_zero (v67, Momentum Strike) pays off from the second play on, so print the card at a fair full price (a 2-cost 13 damage), one or two per class.

<!-- archetype-note: counter_riposte -->
Thorns and `attacked` payloads fire per enemy hit, so numbers are small (Thorns 2-4, riposte damage 3-6) because enemy crowds multiply them. on_hp_lost here is the self-damage twin -- if the class bleeds for its counters, the HP economy rule applies (net-negative, no same-card refund). One retaliation power per class MAX; the cards are Block and a couple of hit-back attacks, not five thorns sources.

<!-- archetype-note: threshold_duelist -->
A `when` gate is a discount: the gated payoff prints about 1.5x its ungated cost, and the gate must be one the player can ENGINEER (no_block, turn_at_least 3, hp_below_half), not luck. 2-3 gated payoffs per class; the rest must work ungated or the deck bricks when the moment never comes. Don't stack two gates on one card, and never gate a basic.

<!-- archetype-note: horde_breaker -->
all_enemies damage is worth 2-3x single-target against a crowd and nothing extra against a boss, so price AoE at about 60% of a single-target card and let `enemy_count_ge` unlock the headline numbers. One or two count-scaled payoffs per class; the class still needs 2-3 single-target attacks for elites. Never combine `hits` with all_enemies below rare. An X-cost AoE `hits_scale:"x"` (Whirlwind, v63) is the exception: 5 per hit at uncommon.

<!-- archetype-note: ambush_alpha -->
`innate` guarantees the opening hand, so an innate card is priced as if it's played EVERY fight: modest (a 1-cost 8 damage, or +1 energy), and 1-2 innate cards per class MAX. The class falls off as fights drag, so make the rare a tempo swing, not a third innate. Never innate + gain_energy + draw on one card. A `when` turn_at_most gate (v56) is the cheaper way to say "opener": value 2-3, the gated bonus about 1.5x, on 1-3 cards -- it lets the deck front-load without innate on everything, and the card must still be worth playing once the window shuts. `target_intends_attack` (v62) holds on ~2/3 of enemy turns: price the gated bonus at 0.6x.

<!-- archetype-note: fleeting_flux -->
`ethereal` over-stats by about 30% (a 1-cost 9 damage, a 1-cost 8 Block) because the card is wasted if unplayed -- that IS the tax, so don't add exhaust on top. 3-5 ethereal cards per class with cheap draw to cycle into them; the rare is the payoff that rewards the churn, not a bigger ethereal. Never ethereal on a basic or a power. `grant_keyword` ethereal (v66) is mostly a price: give it to a cheap draw skill, never to a card that also pays you.

<!-- archetype-note: untouchable_ward -->
Exotic mitigation is stronger than Block. Intangible: 2-3 sources per class, each with a real cost (exhaust, 2+ energy, a gate or a multi-turn countdown), and never Intangible every turn. Buffer 1-2 and Artifact 1-2 at uncommon, Blur 1-2. Never two exotic mitigations on the same card. A per-turn engine that regrants a ward is rare-only and grants 1 at a time. The class still needs Defend-tier Block for the turns the wards are down. `temp_strength_down` (v64, Piercing Wail) is the offensive ward: blunt the big hit instead of absorbing it -- 6 to ALL enemies is an uncommon, exhaust at common.

<!-- archetype-note: burst_window -->
temp_strength / temp_dexterity expire at end of turn, so price them at about a third of permanent Strength: +3-4 temp Strength at 1 cost is fine, but it needs several attacks the same turn or it's wasted -- draw/energy on the burst card is the enabler. One or two burst cards per class; never stack temp Strength with a permanent Strength ramp, and never a per-turn temp-stat power (that's just permanent Strength). temp_thorns / temp_focus (v44) follow the same one-turn pricing: about half of permanent Thorns / Focus, and the card wants a reason the turn matters (an enemy attack incoming; an evoke this turn). `vigor` (v60) is the one-ATTACK spike: 3-6 on a 1-cost with a draw or energy so the attack lands this turn, 1-3 cards per class; `double_damage` (v60) is a whole turn of doubled Attacks -- rare, amount 1, ONE per class, and it needs a real cost (2+ energy, exhaust, or a gate). Never double_damage AND temp_strength on one card. Replays (v65): `replay_next` skill/attack count 1 is an uncommon 1-cost Skill (Burst / One-Two Punch), count 2 is rare-ish; `all` (Duplication) is rare-only. A replay wants the window to be full -- draw or energy nearby -- and it re-runs the WHOLE card, so never pair it with a card that is already a rare bomb. `no_draw` (v65) prices a setup draw.
