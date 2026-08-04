"""Phase U — Rampage grow-on-play (VOCABULARY_GAPS #23) — offline, no API key.

Run:  uv run python -m tests.test_phase_u       (from generation/)
Exits nonzero on any failure. Exercises the mod-contract validator (grow shape + damage-only + ⊥scale +
grow<=amount + one-calc-var + no-payload), cardgen text/emit for the `grow` field, the census tally, the
set-level rampage warning, and the catalog `rampage_grow` entry. Mirrors the C# ForgedCards / EffectRunner /
DataCard / CardSpec changes (vocab v26).
"""
from __future__ import annotations

import sys

# MUST repoint at the constrained mod contract BEFORE importing the btsgen modules that read paths.
from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen, census                # noqa: E402
from btsgen.validator import CardValidator              # noqa: E402
from btsgen.character_validator import rampage_grow_warnings  # noqa: E402
from btsgen.frontend import catalog as C                # noqa: E402
from btsgen import featured                             # noqa: E402

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _card(effects, up=None, **kw):
    base = {"id": "u_test", "name": "U Test", "type": "attack", "rarity": "uncommon",
            "cost": 1, "target": "enemy", "source": "llm", "effects": effects}
    base["upgrade"] = {"effects": up if up is not None else effects}
    base.update(kw)
    return base


def test_version() -> None:
    print("Phase U vocab stamp is at least v26:")
    check(bts1.VOCAB_VERSION >= 26, f"bts1.VOCAB_VERSION must be >= 26 (Phase U), got {bts1.VOCAB_VERSION}")


def test_accepts(v: CardValidator) -> None:
    print("valid grow cards validate:")
    ok = _card([{"op": "damage", "amount": 8, "grow": 5}], up=[{"op": "damage", "amount": 12, "grow": 5}])
    check(v.validate(ok).ok, f"a grow attack should validate: {v.validate(ok).errors}")
    # grow == amount is allowed (boundary)
    edge = _card([{"op": "damage", "amount": 6, "grow": 6}])
    check(v.validate(edge).ok, f"grow == amount should validate: {v.validate(edge).errors}")
    # grow riding alongside a plain block on the same card (one calc-var only — grow is THE calc-var)
    combo = _card([{"op": "damage", "amount": 8, "grow": 4}, {"op": "block", "amount": 5}])
    check(v.validate(combo).ok, f"grow damage + flat block should validate: {v.validate(combo).errors}")


def test_rejects(v: CardValidator) -> None:
    print("invalid grow cards are rejected:")

    def bad(card, why):
        check(not v.validate(card).ok, why)

    bad(_card([{"op": "block", "amount": 8, "grow": 5}], **{"type": "skill", "target": "self"}),
        "grow on a non-damage op must reject")
    bad(_card([{"op": "damage", "amount": 8, "grow": 5, "scale": "forged"}]),
        "grow + scale on one effect must reject")
    bad(_card([{"op": "damage", "amount": 8, "grow": 12}]),
        "grow > 9 must reject")
    bad(_card([{"op": "damage", "amount": 8, "grow": 0}]) if False else
        _card([{"op": "damage", "amount": 5, "grow": 8}]),
        "grow > amount must reject")
    # two calc-vars (grow damage + scaled block) on one card
    bad(_card([{"op": "damage", "amount": 8, "grow": 4}, {"op": "block", "amount": 5, "scale": "x"}], cost="X"),
        "grow damage + scaled block = two calc-vars must reject")
    # grow inside a trigger payload
    payload = _card([{"op": "add_trigger", "trigger": "turn_start",
                      "effects": [{"op": "damage", "amount": 6, "grow": 3, "target": "enemy"}]}],
                    **{"type": "power", "target": "self"})
    bad(payload, "grow inside a trigger payload must reject")


def test_text_bytematch() -> None:
    print("grow card text byte-matches the C# Describe:")
    desc = cardgen.describe([{"op": "damage", "amount": 8, "grow": 5}], "enemy")
    check(desc == "Deal {Damage} damage. Grows by 5 each time it is played this combat.",
          f"grow describe mismatch: {desc!r}")
    # AoE suffix threads through
    aoe = cardgen.describe([{"op": "damage", "amount": 8, "grow": 5}], "all_enemies")
    check(aoe == "Deal {Damage} damage to ALL enemies. Grows by 5 each time it is played this combat.",
          f"grow AoE describe mismatch: {aoe!r}")


def test_emit() -> None:
    print("grow emits a Grow: named arg in the C# EffectSpec literal:")
    lit = cardgen.effect_literal({"op": "damage", "amount": 8, "grow": 5})
    check(lit == 'new EffectSpec("damage", 8, Grow: 5)', f"grow emit mismatch: {lit!r}")
    # a grow damage with a `when` still appends When: after the Grow positional-name args
    litw = cardgen.effect_literal({"op": "damage", "amount": 8, "grow": 5,
                                   "when": {"kind": "hp_below_half"}})
    check("Grow: 5" in litw and "When:" in litw, f"grow+when emit mismatch: {litw!r}")


def test_census() -> None:
    print("census tallies grow and un-plains a grow card:")
    cc = census.walk_card(_card([{"op": "damage", "amount": 8, "grow": 5}]))
    # walk_card tallies base + upgrade (like every op count), so a grow in both reads as 2.
    check(cc.grow == 2, f"census should count grow across base+upgrade, got {cc.grow}")
    check(not cc.plain, "a grow card is NOT a plain stat line")
    cc2 = census.walk_card(_card([{"op": "damage", "amount": 8}]))
    check(cc2.grow == 0 and cc2.plain, "a plain damage card has grow 0 and is plain")


def test_pricing(v: CardValidator) -> None:
    print("a grow attack scores above an equal flat attack:")
    flat = v.score_card(_card([{"op": "damage", "amount": 8}]))
    grow = v.score_card(_card([{"op": "damage", "amount": 8, "grow": 5}]))
    check(grow > flat, f"grow attack ({grow}) should price above flat ({flat})")


def test_set_warning() -> None:
    print("more than two grow cards warns (identity, not wallpaper):")
    two = [_card([{"op": "damage", "amount": 8, "grow": 5}], id="a"),
           _card([{"op": "damage", "amount": 6, "grow": 3}], id="b")]
    check(rampage_grow_warnings(two) == [], "two grow cards is fine")
    three = two + [_card([{"op": "damage", "amount": 7, "grow": 4}], id="c")]
    check(len(rampage_grow_warnings(three)) == 1, "three grow cards warns")


def test_catalog_and_featured() -> None:
    print("catalog rampage_grow entry + featured menu entry exist:")
    cat = C.load_catalog()
    check("rampage_grow" in cat.by_id, "rampage_grow archetype must exist in the catalog")
    e = cat.by_id["rampage_grow"]
    check("grow" in e.ops, "rampage_grow must declare the grow op/token")
    check(any("VOCABULARY_GAPS#23" in r for r in e.gap_refs), "rampage_grow must gap_ref #23")
    check("rampage_grow" in featured._BY_ID, "rampage_grow featured menu entry must exist")
    cc = census.walk_card(_card([{"op": "damage", "amount": 8, "grow": 5}]))
    check(featured._BY_ID["rampage_grow"].detect(cc), "featured detect fires on a grow card")


def main() -> int:
    v = CardValidator()
    test_version()
    test_accepts(v)
    test_rejects(v)
    test_text_bytematch()
    test_emit()
    test_census()
    test_pricing(v)
    test_set_warning()
    test_catalog_and_featured()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
