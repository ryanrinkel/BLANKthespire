"""bridges.py — required BRIDGE cards, the fusion enforcer (Phase O-1; triad-aware Phase 1).

A multi-archetype class earns its "several engines" claim only if some cards actually FUSE them. O-1 requires
MIN_BRIDGES pool cards tagged as bridges, each combining a PAIR of archetypes' engines in ONE card, with at
least one at rare (the fusion's poster card). `class_forge._validate_blueprint` enforces the tag-count + the
rare at the blueprint stage; this module supplies the pure post-generation WITNESS check (does a bridge card
actually TOUCH each engine?) that the N-1 coverage repair round runs after the whole set is designed.

Under TRIAD (three archetypes A/B/C) a bridge declares its PAIR — `"bridge": [id1, id2]` — and each of the
three pairs (AB/AC/BC) wants its own package (TARGET_BRIDGES_PER_PAIR each, floor MIN_BRIDGES_PER_PAIR + the
MIN_BRIDGES total floor). The witness check runs pairwise on the DECLARED pair's ops, so the core function is
unchanged; the new `third_wheel_tokens` names the excluded engine's unique tokens for the SOFT anti-blend
warning (an AB bridge should not quietly touch C). Two-archetype classes keep the boolean `"bridge": true`,
normalized to the only pair at parse time.

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
# of the pool fusing both engines is what makes a two-archetype class play as ONE deck. MIN_BRIDGES stays the
# TOTAL floor under triad; the per-pair pattern (TARGET/MIN) mirrors it for each of the three pairs.
MIN_BRIDGES = 4
TARGET_BRIDGES = 6
TARGET_BRIDGES_PER_PAIR = 2  # triad ask: 2 bridges per pair (6 total — same total as the 2-arch TARGET)
MIN_BRIDGES_PER_PAIR = 1    # triad floor: >=1 bridge for EACH of the three pairs (AND >=MIN_BRIDGES total)


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


def third_wheel_tokens(ops_x, ops_y, ops_z) -> set[str]:
    """The THIRD archetype's UNIQUE tokens for a pair (X, Y): ops(Z) - ops(X) - ops(Y). A pair bridge that
    touches any of these is quietly an ABC card (the anti-blend guard). SOFT check only — token overlap
    between engines is common, so this feeds a warn + repair-directive line, never a hard reject."""
    return set(ops_z or []) - set(ops_x or []) - set(ops_y or [])


def pair_key(id1: str, id2: str) -> tuple[str, str]:
    """A pair's normalized key: the two archetype ids as a sorted tuple, so AB and BA hash the same (used by
    validation and the ledger to bucket bridges/pairs regardless of declaration order)."""
    a, b = str(id1), str(id2)
    return (a, b) if a <= b else (b, a)


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
