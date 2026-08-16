"""bridges.py — required BRIDGE cards, the fusion enforcer (Phase O-1).

A two-archetype class earns its "two engines" claim only if some cards actually FUSE them. O-1 requires
MIN_BRIDGES pool cards tagged `"bridge": true`, each combining BOTH archetypes' engines in ONE card, with at
least one at rare (the fusion's poster card). `class_forge._validate_blueprint` enforces the tag-count + the
rare at the blueprint stage; this module supplies the pure post-generation WITNESS check (does a bridge card
actually TOUCH each engine?) that the N-1 coverage repair round runs after the whole set is designed.

Witness math: each archetype's WITNESS tokens = its catalog `ops` MINUS the partner's (the mechanics unique
to it in THIS pair). A bridge card is witnessed if it touches >=1 witness token of EACH archetype. When a
pair overlaps so heavily that a witness set is empty, fall back to: the card touches >=2 distinct tokens
from the union of both engines. "Touches" walks the card's effects (incl. add_trigger payloads), its `when`
kinds, its scales, and its applied statuses — census.walk_card already surfaces all of these.

Pure functions over card JSON + two ops lists; the catalog resolution (bp archetype ids -> ops) lives in
class_forge (which owns the blueprint) and hands the resolved ops down, so this module imports only census
and never the frontend catalog (no import cycle).
"""
from __future__ import annotations

from . import census

# The validation FLOOR (hard: _validate_blueprint rejects below it) vs the prompt ASK (the TARGET_RARES /
# MIN_RARES pattern): models land near the ask, the floor keeps a shortfall from aborting a forge. ~a quarter
# of the pool fusing both engines is what makes a two-archetype class play as ONE deck.
MIN_BRIDGES = 4
TARGET_BRIDGES = 6


def card_tokens(card: dict) -> set[str]:
    """The flat set of vocabulary tokens a card TOUCHES — ops, applied statuses, add_trigger trigger kinds,
    `when` kinds, and scaling (the literal `scale` token plus each source, and `x` for an X-cost). Aligned
    with the archetype-`ops` vocabulary in the catalog so witness tokens can be matched against it."""
    cc = census.walk_card(card or {})
    toks: set[str] = set(cc.ops) | set(cc.statuses) | set(cc.triggers) | set(cc.whens) | set(cc.scales)
    if cc.scales:
        toks.add("scale")
    if cc.x_cost:
        toks.add("x")
    return toks


def witness_sets(ops_a, ops_b) -> tuple[set[str], set[str]]:
    """(tokens unique to A, tokens unique to B) within this pair."""
    a, b = set(ops_a or []), set(ops_b or [])
    return a - b, b - a


def is_witnessed(card: dict, ops_a, ops_b) -> bool:
    """True if the card fuses BOTH engines. Disjoint pair: touch >=1 witness token of each side. Overlapping
    pair (a witness set is empty): touch >=2 distinct tokens from the union of both engines."""
    a, b = set(ops_a or []), set(ops_b or [])
    toks = card_tokens(card)
    wit_a, wit_b = a - b, b - a
    if wit_a and wit_b:
        return bool(toks & wit_a) and bool(toks & wit_b)
    union = a | b
    return len(toks & union) >= 2


def repair_directive(name_a: str, name_b: str, ops_a, ops_b) -> str:
    """A compact REQUIRED line (the coverage phrasebook style) naming both engines + a few concrete witness
    tokens as 7B anchors, so a bridge card that failed to fuse is regenerated to actually touch both."""
    wit_a, wit_b = witness_sets(ops_a, ops_b)
    if wit_a and wit_b:
        ta = ", ".join(sorted(wit_a)[:3])
        tb = ", ".join(sorted(wit_b)[:3])
        return (f"REQUIRED: this is a BRIDGE card - it must FUSE both archetypes in ONE card. Use at least "
                f"one of [{ta}] (the {name_a} engine) AND at least one of [{tb}] (the {name_b} engine).")
    union = ", ".join(sorted(set(ops_a or []) | set(ops_b or []))[:5]) or "both engines"
    return (f"REQUIRED: this is a BRIDGE card - it must FUSE the {name_a} and {name_b} engines in ONE card, "
            f"touching at least TWO of [{union}].")
