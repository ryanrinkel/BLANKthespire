"""Phase R discard-subsystem tests (VOCABULARY_GAPS #17: op `discard` + trigger `on_discard`) — offline, no API key.

Run:  uv run python -m tests.test_phase_r       (from generation/)
Exits nonzero on any failure. Exercises the mod-contract validator + cardgen text/emit for the `discard` op
(card-level and in trigger payloads) and the CARD-LATENT `on_discard` (Reflex) trigger. Mirrors the C#
ForgedCards / EffectRunner / TriggerRunner / DataCard changes (vocab v23). scry (R-2) was deferred.
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
    base = {"id": "r_test", "name": "R Test", "type": "skill", "rarity": "uncommon",
            "cost": 1, "target": "self", "source": "llm", "effects": effects}
    base.update(kw)
    return base


# ---------------------------------------------------------------- 1. validator ACCEPTS
def test_accepts(v: CardValidator) -> None:
    print("valid Phase R cards validate:")
    # a cheap attack with a discard rider
    churn = _card([{"op": "damage", "amount": 6}, {"op": "discard", "amount": 1}], type="attack", target="enemy")
    check(v.validate(churn).ok, f"attack + discard rider should validate: {v.validate(churn).errors}")
    # a Reflex card: on_discard payload gains Block (CARD-LATENT)
    reflex = _card([{"op": "add_trigger", "trigger": "on_discard", "effects": [{"op": "block", "amount": 6}]}])
    check(v.validate(reflex).ok, f"on_discard Reflex card should validate: {v.validate(reflex).errors}")
    # on_discard with once_per_turn (it's a multi-fire trigger — discard/redraw/discard in one turn)
    reflex_opt = _card([{"op": "add_trigger", "trigger": "on_discard", "once_per_turn": True,
                         "effects": [{"op": "draw", "amount": 2}]}])
    check(v.validate(reflex_opt).ok, f"on_discard + once_per_turn should validate: {v.validate(reflex_opt).errors}")
    # a churn engine power: turn_start -> discard 1 (forced churn in a trigger payload)
    engine = _card([{"op": "add_trigger", "trigger": "turn_start", "effects": [{"op": "discard", "amount": 1}]}],
                   type="power")
    check(v.validate(engine).ok, f"turn_start -> discard churn power should validate: {v.validate(engine).errors}")
    # an on_discard payload may TARGET an enemy (H4 targeted payload)
    reflex_dmg = _card([{"op": "add_trigger", "trigger": "on_discard",
                         "effects": [{"op": "damage", "amount": 8, "target": "enemy"}]}])
    check(v.validate(reflex_dmg).ok, f"on_discard with a targeted damage payload should validate: {v.validate(reflex_dmg).errors}")


# ---------------------------------------------------------------- 2. validator REJECTS
def test_rejects(v: CardValidator) -> None:
    print("Phase R misuse is rejected:")

    def bad(card: dict, why: str) -> None:
        check(not v.validate(card).ok, why)

    # discard needs amount >= 1 (schema minimum + AmountOps)
    bad(_card([{"op": "discard"}]), "discard with no amount must be rejected")
    bad(_card([{"op": "discard", "amount": 0}]), "discard amount 0 must be rejected")
    # discard can't be scaled (it's not damage/block/draw)
    bad(_card([{"op": "discard", "amount": 1, "scale": "cards_in_hand"}]), "scaled discard must be rejected")
    # once_per_turn only on a multi-fire trigger — a turn_start discard engine can't be once_per_turn
    bad(_card([{"op": "add_trigger", "trigger": "turn_start", "once_per_turn": True,
                "effects": [{"op": "discard", "amount": 1}]}], type="power"),
        "once_per_turn on a turn_start trigger must be rejected")
    # two discards on one card collide on the 'Discard' var (dup-var crash guard)
    bad(_card([{"op": "discard", "amount": 1}, {"op": "discard", "amount": 2}]),
        "two discard ops on one card must be rejected (dup 'Discard' var)")


# ---------------------------------------------------------------- 3. text byte-match (mirrors C# Describe)
def test_text(_v: CardValidator) -> None:
    print("synthesized card text matches C# Describe/TriggerSentence/TriggerFragment:")

    def desc(effects: list[dict], target: str = "self") -> str:
        return cardgen.describe(effects, target)

    check(desc([{"op": "damage", "amount": 6}, {"op": "discard", "amount": 1}], "enemy")
          == "Deal {Damage} damage.\nDiscard {Discard} random card(s).",
          "discard rider sentence (uses the {Discard} var)")
    check(desc([{"op": "add_trigger", "trigger": "on_discard", "effects": [{"op": "block", "amount": 6}]}])
          == "Whenever this card is discarded, gain 6 Block.",
          "on_discard Reflex sentence")
    check(desc([{"op": "add_trigger", "trigger": "turn_start", "effects": [{"op": "discard", "amount": 1}]}])
          == "At the start of your turn, discard 1 random card(s).",
          "turn_start -> discard churn fragment")


# ---------------------------------------------------------------- 4. C#-emit round-trip (effect_literal)
def test_emit(_v: CardValidator) -> None:
    print("effect_literal emits the expected C# EffectSpec literals:")
    check(cardgen.effect_literal({"op": "discard", "amount": 2}) == 'new EffectSpec("discard", 2)',
          "discard literal (positional Op, Amount)")
    check(cardgen.effect_literal({"op": "add_trigger", "trigger": "on_discard",
                                  "effects": [{"op": "block", "amount": 6}]})
          == 'new EffectSpec("add_trigger", 0, Trigger: "on_discard", Triggered: [new EffectSpec("block", 6)])',
          "on_discard add_trigger literal")


# ---------------------------------------------------------------- 5. version + gap + catalog lockstep
def test_version_gap_catalog() -> None:
    print("version bump, gap flip, and catalog buildability:")
    check(bts1.VOCAB_VERSION >= 23, f"bts1.VOCAB_VERSION must be >= 23 (Phase R), got {bts1.VOCAB_VERSION}")
    gaps = C.gap_status()
    check(gaps.get(17) == "done", f"gap #17 should parse as done (R-1), got {gaps.get(17)}")
    cat = C.load_catalog()
    md = cat.by_id.get("madness_discard")
    check(md is not None and md.buildable,
          f"madness_discard must be BUILDABLE (gap #17 done + discard token live): {md.block_reasons if md else 'missing'}")
    check("discard" in md.ops, "madness_discard must carry the discard op token")
    live = C.live_vocab_tokens()
    for tok in ("discard", "on_discard"):
        check(tok in live, f"{tok} must be a live (backticked) vocab token")


def main() -> int:
    v = CardValidator()
    for t in (test_accepts, test_rejects, test_text, test_emit):
        t(v)
    test_version_gap_catalog()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
