"""featured.py — the featured-mechanic roulette (Phase N-2).

Per concept, deterministically ROLL N_FEATURED mechanics off a menu and REQUIRE the blueprint to weave a
pool card around each (injected into both brief modes next to the pool ask). Each entry carries a detector
(over census.CardCensus) so the class's actual cards can be checked for the mechanic, and a repair
directive (the same phrasebook coverage.py uses) so a missing featured mechanic joins the N-1 repair round.

The roll is seeded ONLY by the concept (sha256 of its lowercased text) — reproducible per concept, never
the `random` module. Orb/status/summon-only mechanics stay OFF this menu (class-kind pools remain the
compose stage's call); every entry here is a base mechanic valid on any class kind.

Phase N-5 adds the THEME-AWARE roll (themed_roll): the staged front-end's cloud stage nominates a
resonance shortlist off menu_block(), and a seeded, recency-damped lottery fills slot 1 from that
shortlist (theme fit) and the remaining slot(s) wild off the whole menu (deliberate forced-collision
spice). The model only ever NOMINATES — code makes the final picks, so its favorites can't converge.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from . import coverage

N_FEATURED = 2


@dataclass(frozen=True)
class Featured:
    id: str
    injection: str          # the compact phrase for the REQUIRED brief block
    directive: str          # the repair directive if the mechanic is missing after the pool is built
    detect: object          # callable(census.CardCensus) -> bool
    exclusion: str = ""     # a note (e.g. "rare-tier"); no hard class-kind exclusions on this menu


def _d(key: str) -> str:
    return coverage.DIRECTIVE_BY_KEY[key]


# The menu — each detector checks a CardCensus for EXACTLY this mechanic.
FEATURED_MENU: list[Featured] = [
    Featured("reactive_played", 'a card that triggers when you PLAY a card (add_trigger "on_card_played", once_per_turn)',
             _d("on_card_played"), lambda cc: "on_card_played" in cc.triggers),
    Featured("reactive_drawn", 'a card that triggers when you DRAW a card (add_trigger "on_card_drawn")',
             'REQUIRED: add an ongoing power (op "add_trigger", trigger "on_card_drawn") that rewards drawing a card.',
             lambda cc: "on_card_drawn" in cc.triggers),
    Featured("reactive_damage", 'a card that triggers when you DEAL damage (add_trigger "on_damage_dealt")',
             'REQUIRED: add an ongoing power (op "add_trigger", trigger "on_damage_dealt") that rewards dealing damage.',
             lambda cc: "on_damage_dealt" in cc.triggers),
    Featured("reactive_block", 'a card that triggers when you GAIN Block (add_trigger "on_block_gained")',
             _d("on_block_gained"), lambda cc: "on_block_gained" in cc.triggers),
    Featured("counterattack", 'a counterattack that triggers when you are ATTACKED (add_trigger "attacked"; payload may hit the enemy)',
             _d("attacked"), lambda cc: "attacked" in cc.triggers),
    Featured("blood_engine", 'a card that triggers when you LOSE HP (add_trigger "on_hp_lost")',
             _d("on_hp_lost"), lambda cc: "on_hp_lost" in cc.triggers),
    Featured("long_fuse", 'a long-fuse card that fires ONCE after a countdown (add_trigger "ripen")',
             'REQUIRED: add an ongoing power (op "add_trigger", trigger "ripen", amount:2) that fires its payload ONCE after 2 turns.',
             lambda cc: "ripen" in cc.triggers),
    Featured("late_game", 'a card that powers up late in the fight (`when` turn_at_least)',
             _d("turn_at_least"), lambda cc: "turn_at_least" in cc.whens),
    Featured("horde_payoff", 'an AoE payoff for facing a crowd (all_enemies + `when` enemy_count_ge)',
             _d("enemy_count_ge"), lambda cc: "enemy_count_ge" in cc.whens),
    Featured("desperation", 'a last-stand payoff while below half HP (`when` hp_below_half)',
             _d("hp_below_half"), lambda cc: "hp_below_half" in cc.whens),
    Featured("patient_reserve", 'a card that rewards UNSPENT energy (scale "unspent_energy_last_turn")',
             'REQUIRED: make one damage/block/draw amount scale "unspent_energy_last_turn" (reward energy left over last turn).',
             lambda cc: "unspent_energy_last_turn" in cc.scales),
    Featured("x_dump", 'an X-cost dump card (cost "x" plus a scale "x" effect)',
             'REQUIRED: make this an X-cost card (cost "x") with one damage or block effect scale "x".',
             lambda cc: cc.x_cost),
    Featured("opening_gambit", 'an opening-hand card (op "innate")',
             'REQUIRED: give this card op "innate" (it starts in your opening hand every combat).',
             lambda cc: "innate" in cc.ops),
    Featured("fleeting_power", 'an over-statted ETHEREAL card - big now, gone at end of turn (op "ethereal")',
             'REQUIRED: give this card op "ethereal" and over-stat it for its cost (big now, exhausts at end of turn).',
             lambda cc: "ethereal" in cc.ops),
    Featured("untouchable", 'a mitigation card using buffer / artifact / intangible instead of flat Block',
             'REQUIRED: apply_status buffer, artifact, or intangible (mitigation exotica; keep it rare-tier).',
             lambda cc: bool(cc.statuses.keys() & {"buffer", "artifact", "intangible"}), exclusion="rare-tier"),
    Featured("burst_window", 'a burst card spiking temp_strength / temp_dexterity for one turn',
             'REQUIRED: apply_status temp_strength or temp_dexterity (a one-turn stat spike).',
             lambda cc: bool(cc.statuses.keys() & {"temp_strength", "temp_dexterity"})),
    Featured("token_conjure", 'a card that CONJURES copies of one of your OWN cards into a pile (op "add_card")',
             'REQUIRED: add a card with op "add_card" that copies one of THIS class\'s own cards into a pile '
             '(hand/discard/draw; small amounts — send self-copies to the discard pile). CLASS-ONLY.',
             lambda cc: "add_card" in cc.ops),
    Featured("discard_reflex", 'a Reflex card that pays off when DISCARDED (add_trigger "on_discard")',
             'REQUIRED: add a card with op "add_trigger", trigger "on_discard" — its payload fires when the card '
             'is discarded BY AN EFFECT (a discard-fuel card you keep in hand and throw away for value).',
             lambda cc: "on_discard" in cc.triggers),
    Featured("scry_filter", 'a card that SCRIES — look at the top of your draw pile and discard any (op "scry")',
             'REQUIRED: add a skill/attack with op "scry" (amount N) — the player looks at the top N cards of the '
             'draw pile and discards any; a draw-filter that also feeds on_discard payoffs (pick which fuel to pitch).',
             lambda cc: "scry" in cc.ops),
    Featured("balance_shift", 'a card that moves the two-pole BALANCE gauge (op "balance_step", light/dark)',
             'REQUIRED: add a card with op "balance_step" (pole light or dark, amount 1-5) moving the Balance '
             'gauge, and gate a payoff on it (`when` dark_ge/light_ge value 3-5 — a gate the deck can actually '
             'reach; opposing steps cancel, so lean one DOMINANT pole; `centered` only at value 0-1). A balance '
             'class needs income on BOTH poles + a pole/centered-gated payoff at uncommon or below.',
             lambda cc: "balance_step" in cc.ops),
    Featured("rampage_grow", 'a signature attack that GROWS each time you play it this combat (field "grow")',
             'REQUIRED: add ONE damage card carrying a "grow" field (1-9, <= its amount) so its damage climbs '
             'each time you play it this combat (base-StS Rampage); give it cheap draw/retain support so it recurs.',
             lambda cc: cc.grow > 0),
    Featured("battle_smith", 'a card that UPGRADES cards in your hand mid-fight (op "upgrade_card", choose/random/all)',
             'REQUIRED: add a skill with op "upgrade_card" (cards "choose" = YOU pick one card, "random" = one card, '
             'or "all" = the whole hand) that upgrades your hand for the rest of this combat (the Armaments fantasy); '
             'pair with retain/big hands so the upgrade sticks.',
             lambda cc: "upgrade_card" in cc.ops),
    Featured("ascetic_purge", 'a card that THINS your deck for the rest of the run (op "purge" self-thins, or "purge_card" thins a card you choose)',
             'REQUIRED: add either a strong over-statted one-shot skill/attack with the flag-op "purge" (it leaves '
             'your run deck permanently when played) OR a skill/attack with the op "purge_card" (you choose a card '
             'in hand to purge — targeted deck-thinning). Never on a basic; "purge" is mutually exclusive with '
             'exhaust; 1-3 per class.',
             lambda cc: "purge" in cc.ops or "purge_card" in cc.ops),
    Featured("corruption_engine", 'a POWER that makes your Skills cost 0 but Exhaust when played (flag-op "corruption")',
             'REQUIRED: add ONE power (or skill) carrying the flag-op "corruption" so that while it is active your '
             'Skills cost 0 but Exhaust when played (base-game Corruption). Give the class Skill density + an '
             '"on_exhaust" payoff (Feel No Pain / Dark Embrace) so the free exhausting Skills feed an engine. One per class.',
             lambda cc: "corruption" in cc.ops),
    Featured("strike_synergy", 'a payoff that scales with how many cards of a TAG you own (scale "tag_cards_owned")',
             'REQUIRED: tag 3-5 cards of the class with the SAME lowercase "tags" slug (e.g. ["strike"]), then add '
             '1-2 damage/block payoffs carrying scale:"tag_cards_owned" + a matching "tag" so they deal/block their '
             'printed amount PLUS 1 per tagged card you own (the Perfected-Strike identity).',
             lambda cc: "tag_cards_owned" in cc.scales),
    Featured("metamorph", 'a card that PERMANENTLY becomes another of your cards when played (op "transform_card")',
             'REQUIRED: add a card with op "transform_card" naming a DIFFERENT card in this class ("card_id") — when '
             'played it permanently becomes that card for the rest of the run. Two shapes: a RANK-UP (a weak card '
             'that transforms into a strong one, ideally behind a "when" gate — "transforms once forged enough") or '
             'a MODE-SWAP (two cards that each transform_card into the other — a stance/weapon-mode toggle A↔B). '
             'Never on a basic; never chain A→B→C; 1-3 per class.',
             lambda cc: "transform_card" in cc.ops),
    Featured("graft", 'a card that lets you PICK a card in hand and permanently reforge it into another (op "graft_card")',
             'REQUIRED: add a card with op "graft_card" naming a STRONG card in this class ("card_id") — when played, '
             'the player picks a card in HAND and THAT picked card permanently becomes card_id for the rest of the run '
             '(the choose form of transform_card, as purge_card is the choose form of purge). The prune-and-graft '
             'fantasy: cut a weak/Basic/dead draw and reforge it into a payoff. Never on a basic; mutually exclusive '
             'with purge/purge_card; counts toward the 1-3-per-class transform-family cap.',
             lambda cc: "graft_card" in cc.ops),
]

_BY_ID = {f.id: f for f in FEATURED_MENU}


def _seed_val(text: str) -> int:
    return int.from_bytes(hashlib.sha256((text or "").strip().lower().encode("utf-8")).digest(), "big")


def roll_featured(concept: str, n: int = N_FEATURED) -> list[Featured]:
    """Deterministically pick `n` distinct featured mechanics for this concept. Seeded ONLY by the concept
    (sha256 of its stripped, lowercased text) — same concept always rolls the same picks. This is the BLIND
    roll: the one-shot path uses it as-is; the staged front-end re-rolls via themed_roll after its cloud
    stage (Phase N-5)."""
    val = _seed_val(concept)
    pool = list(FEATURED_MENU)
    picks: list[Featured] = []
    while pool and len(picks) < n:
        j = val % len(pool)
        val //= len(pool)
        picks.append(pool.pop(j))
        if val == 0:  # extremely unlikely; reseed off the id so we never divide by a shrinking 0
            val = int.from_bytes(hashlib.sha256(picks[-1].id.encode()).digest(), "big")
    return picks


def themed_roll(concept: str, resonant_ids, recent=None, n: int = N_FEATURED) -> list[Featured]:
    """Phase N-5: the theme-aware roll — slot 1 RESONANT, the rest WILD, all picked by a code-side lottery.

    The model only ever NOMINATES (resonant_ids = the cloud stage's shortlist); the final picks are a
    seeded WEIGHTED lottery so the model's favorites can't converge across forges. Every entry's weight
    starts equal and is damped by `recent` (id -> recency-weighted use count from the ledger window):
    weight = 1/(1+uses) — a recently-rolled mechanic grows unlikely, never impossible. Slot 1 draws from
    the resonant shortlist (theme fit); remaining slots draw from the WHOLE remaining menu (the deliberate
    forced-collision spice). Empty/unknown shortlist -> every slot wild (the blind roll, now recency-aware).

    Seeded ONLY by the concept text, like roll_featured — same concept + same shortlist + same ledger
    window -> the same picks. The shortlist is canonicalized to menu order, so the model re-ordering its
    nominations cannot change the draw."""
    recent = dict(recent or {})
    val = _seed_val(concept)
    resonant_set = {str(i) for i in (resonant_ids or [])}
    shortlist = [f for f in FEATURED_MENU if f.id in resonant_set]
    picks: list[Featured] = []

    def _draw(pool: list[Featured]) -> None:
        nonlocal val
        pool = [f for f in pool if f not in picks]
        if not pool:
            return
        weights = [max(1, int(1000.0 / (1.0 + float(recent.get(f.id, 0.0) or 0.0)))) for f in pool]
        total = sum(weights)
        r = val % total
        val //= total
        if val == 0:  # extremely unlikely; reseed off the concept + first id so the stream never dies
            val = _seed_val(concept + pool[0].id)
        acc = 0
        for f, w in zip(pool, weights):
            acc += w
            if r < acc:
                picks.append(f)
                return
        picks.append(pool[-1])

    if shortlist:
        _draw(shortlist)
    while len(picks) < max(0, int(n)) and len(picks) < len(FEATURED_MENU):
        _draw(list(FEATURED_MENU))
    return picks


def resolve(ids) -> list[Featured]:
    """Featured entries for a list of ids (silently drops unknown ids)."""
    return [_BY_ID[i] for i in (ids or []) if i in _BY_ID]


def menu_block() -> str:
    """The full menu (id: fantasy phrase, one per line) for prompts that RATE the menu — the cloud stage's
    resonance shortlist (Phase N-5). Ids + injections only; detectors and directives stay code-side."""
    return "\n".join(f"- {f.id}: {f.injection}" for f in FEATURED_MENU)


def injection_block(ids) -> str:
    """The compact REQUIRED block injected into the blueprint brief (empty string if no featured)."""
    feats = resolve(ids)
    if not feats:
        return ""
    lines = "; ".join(f.injection for f in feats)
    return ("\nFEATURED MECHANICS (REQUIRED): weave at least one pool card around EACH of these - "
            f"{lines}.")


def presence(made: list[dict], feats: list[Featured]) -> dict:
    """id -> bool: is each featured mechanic carried by any measurable pool card? (Uses census over base +
    upgrade + nested payloads, so a mechanic buried in a trigger payload still counts.)"""
    from . import census
    from .coverage import measurable_indices
    ccs = [census.walk_card((made[i].get("card") or {})) for i in measurable_indices(made)]
    out = {}
    for f in feats:
        out[f.id] = any(f.detect(cc) for cc in ccs)
    return out
