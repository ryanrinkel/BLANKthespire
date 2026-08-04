"""Phase Q token-generation tests (VOCABULARY_GAPS #16 add_card; completes #8 compost) — offline, no API key.

Run:  uv run python -m tests.test_phase_q       (from generation/)
Exits nonzero on any failure. Exercises the mod-contract validator (shape + ref-integrity + loop discipline)
and cardgen text/emit for the `add_card` op, both at card level and inside an add_trigger payload (the compost
loop). Mirrors the C# ForgedCards / EffectRunner / TriggerRunner / ForgedCharacters changes (vocab v22).
"""
from __future__ import annotations

import sys

# MUST repoint at the constrained mod contract BEFORE importing the btsgen modules that read paths.
from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen            # noqa: E402
from btsgen.validator import CardValidator   # noqa: E402
from btsgen.frontend import catalog as C     # noqa: E402

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _card(effects: list[dict], **kw) -> dict:
    base = {"id": "q_test", "name": "Q Test", "type": "skill", "rarity": "uncommon",
            "cost": 1, "target": "self", "source": "llm", "effects": effects}
    base.update(kw)
    return base


# ---------------------------------------------------------------- 1. validator ACCEPTS
def test_accepts(v: CardValidator) -> None:
    print("valid Phase Q cards validate:")
    # conjure 2 copies of a known card into hand
    conjure = _card([{"op": "add_card", "card_id": "quick_jab", "pile": "hand", "amount": 2}])
    check(v.validate(conjure).ok, f"add_card (2 copies of a known card to hand) should validate: {v.validate(conjure).errors}")
    # single copy, no amount (defaults to 1)
    one = _card([{"op": "add_card", "card_id": "quick_jab", "pile": "draw"}])
    check(v.validate(one).ok, f"add_card with no amount (default 1) should validate: {v.validate(one).errors}")
    # Anger-style SELF-copy to the DISCARD pile (sanctioned — the deck cycle gates the loop; no warning)
    anger = _card([{"op": "damage", "amount": 6}, {"op": "add_card", "card_id": "anger_q", "pile": "discard"}],
                  id="anger_q", type="attack", target="enemy", cost=0)
    r = v.validate(anger)
    check(r.ok and not any("one-card engine" in w for w in r.warnings),
          f"self-copy to DISCARD (Anger pattern) should validate with no loop warning: {r.errors} / {r.warnings}")
    # the COMPOST loop: a power grants on_exhaust -> add_card into the discard pile
    compost = _card([{"op": "add_trigger", "trigger": "on_exhaust",
                      "effects": [{"op": "add_card", "card_id": "cinder_q", "pile": "discard"}]}],
                    type="power")
    check(v.validate(compost).ok, f"on_exhaust -> add_card compost loop should validate: {v.validate(compost).errors}")


# ---------------------------------------------------------------- 2. validator REJECTS
def test_rejects(v: CardValidator) -> None:
    print("Phase Q misuse is rejected:")

    def bad(card: dict, why: str) -> None:
        check(not v.validate(card).ok, why)

    # missing pile (schema: pile required on add_card)
    bad(_card([{"op": "add_card", "card_id": "quick_jab"}]),
        "add_card with no pile must be rejected")
    # missing card_id (schema: card_id required on add_card)
    bad(_card([{"op": "add_card", "pile": "hand"}]),
        "add_card with no card_id must be rejected")
    # amount over the cap of 3 (schema max + structural mirror)
    bad(_card([{"op": "add_card", "card_id": "quick_jab", "pile": "hand", "amount": 5}]),
        "add_card amount > 3 must be rejected")
    # unknown card_id (ref-integrity)
    bad(_card([{"op": "add_card", "card_id": "no_such_card_xyzzy", "pile": "hand"}]),
        "add_card referencing an unknown card must be rejected")
    # invalid pile value (schema enum)
    bad(_card([{"op": "add_card", "card_id": "quick_jab", "pile": "exhaust"}]),
        "add_card with an invalid pile must be rejected")
    # card_id on a non-add_card op (structural: card_id/pile only apply to add_card)
    bad(_card([{"op": "damage", "amount": 5, "card_id": "quick_jab"}], type="attack", target="enemy"),
        "card_id on a non-add_card op must be rejected")


# ---------------------------------------------------------------- 3. loop discipline (WARNING, not reject)
def test_loop_discipline(v: CardValidator) -> None:
    print("the 0-cost self-to-hand one-card engine warns (never rejects):")
    looper = _card([{"op": "add_card", "card_id": "looper_q", "pile": "hand"}],
                   id="looper_q", cost=0)
    r = v.validate(looper)
    check(r.ok, f"a self-to-hand loop is a WARNING, not a reject: {r.errors}")
    check(any("one-card engine" in w for w in r.warnings),
          f"a 0-cost self-to-hand add_card should raise the one-card-engine warning: {r.warnings}")


# ---------------------------------------------------------------- 4. text byte-match (mirrors C# Describe)
def test_text(_v: CardValidator) -> None:
    print("synthesized card text matches C# Describe/AddCardSentence/PilePhrase:")

    def desc(effects: list[dict], target: str = "self") -> str:
        return cardgen.describe(effects, target)

    check(desc([{"op": "add_card", "card_id": "ember_bolt", "pile": "discard", "amount": 2}])
          == "Add 2 copies of Ember Bolt to your discard pile.",
          "add_card N-copies sentence (discard pile)")
    check(desc([{"op": "add_card", "card_id": "cinder", "pile": "hand"}])
          == "Add a copy of Cinder to your hand.",
          "add_card single-copy sentence (hand)")
    check(desc([{"op": "add_card", "card_id": "spark", "pile": "draw"}])
          == "Add a copy of Spark to your draw pile.",
          "add_card single-copy sentence (draw pile)")
    # the compost fragment woven into the trigger sentence
    check(desc([{"op": "add_trigger", "trigger": "on_exhaust",
                 "effects": [{"op": "add_card", "card_id": "cinder", "pile": "discard"}]}])
          == "Whenever a card is Exhausted, add a copy of Cinder to your discard pile.",
          "on_exhaust + add_card compost fragment")


# ---------------------------------------------------------------- 5. C#-emit round-trip (effect_literal)
def test_emit(_v: CardValidator) -> None:
    print("effect_literal emits the expected C# EffectSpec literals:")
    check(cardgen.effect_literal({"op": "add_card", "card_id": "ember_bolt", "pile": "discard", "amount": 2})
          == 'new EffectSpec("add_card", 2, CardId: "ember_bolt", Pile: "discard")',
          "add_card literal (amount 2)")
    check(cardgen.effect_literal({"op": "add_card", "card_id": "cinder", "pile": "hand"})
          == 'new EffectSpec("add_card", 1, CardId: "cinder", Pile: "hand")',
          "add_card literal (default amount 1)")


# ---------------------------------------------------------------- 6. version + gap + catalog lockstep
def test_version_gap_catalog() -> None:
    print("version bump, gap flips, and catalog buildability:")
    check(bts1.VOCAB_VERSION >= 22, f"bts1.VOCAB_VERSION must be >= 22 (Phase Q), got {bts1.VOCAB_VERSION}")
    gaps = C.gap_status()
    check(gaps.get(16) == "done", f"gap #16 should parse as done, got {gaps.get(16)}")
    check(gaps.get(8) == "done", f"gap #8 (compost) should parse as done, got {gaps.get(8)}")
    cat = C.load_catalog()
    tc = cat.by_id.get("token_conjurer")
    check(tc is not None and tc.buildable,
          f"token_conjurer must be BUILDABLE (gap #16 done + add_card token live): {tc.block_reasons if tc else 'missing'}")
    check("add_card" in tc.ops, "token_conjurer must carry the add_card op token")
    check(cat.by_id["exhaust_pyre"].buildable, "exhaust_pyre stays buildable (its ops are unchanged)")
    check("add_card" in C.live_vocab_tokens(), "add_card must be a live (backticked) vocab token")


def main() -> int:
    v = CardValidator()
    for t in (test_accepts, test_rejects, test_loop_discipline, test_text, test_emit):
        t(v)
    test_version_gap_catalog()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
