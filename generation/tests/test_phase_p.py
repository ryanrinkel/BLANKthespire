"""Phase P precision-reads tests (VOCABULARY_GAPS #21 lifesteal / #22 flechettes / #24 Grand-Finale
gate + #9-relic on_hp_lost) — offline, no API key.

Run:  uv run python -m tests.test_phase_p       (from generation/)
Exits nonzero on any failure. Exercises the mod-contract validator + cardgen text/emit for the two new
scalars, the draw_pile_empty condition, and the relic on_hp_lost hook. Mirrors the C# ForgedCards /
EffectRunner / Conditions / ForgedRelic changes (vocab v21).
"""
from __future__ import annotations

import sys

# MUST repoint at the constrained mod contract BEFORE importing the btsgen modules that read paths.
from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen           # noqa: E402
from btsgen import smoke_relic             # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402
from btsgen.frontend import catalog as C   # noqa: E402

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
    base = {"id": "p_test", "name": "P Test", "type": "attack", "rarity": "uncommon",
            "cost": 1, "target": "enemy", "source": "llm", "effects": effects}
    base.update(kw)
    return base


# ---------------------------------------------------------------- 1. validator ACCEPTS
def test_accepts(v: CardValidator) -> None:
    print("valid Phase P cards validate:")
    # #21 lifesteal: AoE damage then heal for the unblocked damage dealt (heal AFTER damage, same list).
    reaper = _card([{"op": "damage", "amount": 8},
                    {"op": "heal", "amount": 1, "scale": "damage_dealt_unblocked"}],
                   target="all_enemies")
    check(v.validate(reaper).ok, f"lifesteal (damage then scaled heal) should validate: {v.validate(reaper).errors}")
    # single-target lifesteal, multi-hit damage feeding the heal
    stab = _card([{"op": "damage", "amount": 4, "hits": 3},
                  {"op": "heal", "amount": 1, "scale": "damage_dealt_unblocked"}])
    check(v.validate(stab).ok, f"multi-hit lifesteal should validate: {v.validate(stab).errors}")
    # #22 flechettes: damage scaling with the debuffs on the target
    flech = _card([{"op": "damage", "amount": 1, "scale": "target_debuff_count"}])
    check(v.validate(flech).ok, f"flechettes (target_debuff_count damage) should validate: {v.validate(flech).errors}")
    # #24 Grand Finale: a big bomb gated on an empty draw pile
    finale = _card([{"op": "damage", "amount": 30, "when": {"kind": "draw_pile_empty"}},
                    {"op": "exhaust"}], rarity="rare", cost=2)
    check(v.validate(finale).ok, f"draw_pile_empty-gated bomb should validate: {v.validate(finale).errors}")
    # lifesteal heal + a separate scaled flechette damage on ONE card (heal-scaled is exempt from the
    # one-calculated-var rule, which counts only damage/block).
    combo = _card([{"op": "damage", "amount": 1, "scale": "target_debuff_count"},
                   {"op": "heal", "amount": 1, "scale": "damage_dealt_unblocked"}])
    check(v.validate(combo).ok, f"flechette damage + lifesteal heal should validate: {v.validate(combo).errors}")


# ---------------------------------------------------------------- 2. validator REJECTS
def test_rejects(v: CardValidator) -> None:
    print("Phase P misuse is rejected:")

    def bad(card: dict, why: str) -> None:
        check(not v.validate(card).ok, why)

    # damage_dealt_unblocked on a non-heal op (block)
    bad(_card([{"op": "damage", "amount": 5},
               {"op": "block", "amount": 1, "scale": "damage_dealt_unblocked"}]),
        "damage_dealt_unblocked on block must be rejected (heal-only)")
    # lifesteal heal with NO preceding damage in the same list
    bad(_card([{"op": "heal", "amount": 1, "scale": "damage_dealt_unblocked"}], type="skill", target="self"),
        "lifesteal heal with no preceding damage must be rejected")
    # lifesteal heal BEFORE the damage (order matters — same-list, top-to-bottom)
    bad(_card([{"op": "heal", "amount": 1, "scale": "damage_dealt_unblocked"},
               {"op": "damage", "amount": 5}]),
        "lifesteal heal placed before the damage must be rejected")
    # target_debuff_count on a non-damage op (block)
    bad(_card([{"op": "block", "amount": 1, "scale": "target_debuff_count"}], type="skill", target="self"),
        "target_debuff_count on block must be rejected (damage-only)")
    # the new scalars are forbidden inside a trigger payload (only cards_retained is allowed there)
    bad(_card([{"op": "add_trigger", "trigger": "turn_end",
                "effects": [{"op": "heal", "amount": 1, "scale": "damage_dealt_unblocked"}]}], type="power"),
        "damage_dealt_unblocked inside a trigger payload must be rejected")


# ---------------------------------------------------------------- 3. text byte-match (mirrors C# Describe)
def test_text(_v: CardValidator) -> None:
    print("synthesized card text matches C# Describe/ScalePhrase/Conditions.Phrase:")

    def desc(effects: list[dict], target: str = "enemy") -> str:
        return cardgen.describe(effects, target)

    check(desc([{"op": "damage", "amount": 8},
                {"op": "heal", "amount": 1, "scale": "damage_dealt_unblocked"}], "all_enemies")
          == "Deal {Damage} damage to ALL enemies.\nHeal HP equal to the unblocked damage dealt.",
          "lifesteal sentence (AoE damage + scaled heal)")
    check(desc([{"op": "damage", "amount": 1, "scale": "target_debuff_count"}])
          == "Deal damage equal to the debuffs on the target.",
          "flechettes sentence")
    check(desc([{"op": "damage", "amount": 30, "when": {"kind": "draw_pile_empty"}}])
          == "Deal {Damage} damage if your draw pile is empty.",
          "draw_pile_empty gate woven into the sentence")
    check(cardgen.cond_phrase({"kind": "draw_pile_empty"}) == "your draw pile is empty",
          "draw_pile_empty condition phrase")


# ---------------------------------------------------------------- 4. C#-emit round-trip (effect_literal)
def test_emit(_v: CardValidator) -> None:
    print("effect_literal emits the expected C# EffectSpec/Condition literals:")
    check(cardgen.effect_literal({"op": "heal", "amount": 1, "scale": "damage_dealt_unblocked"})
          == 'new EffectSpec("heal", 1, null, 1, "damage_dealt_unblocked")',
          "scaled-heal literal")
    check(cardgen.effect_literal({"op": "damage", "amount": 1, "scale": "target_debuff_count"})
          == 'new EffectSpec("damage", 1, null, 1, "target_debuff_count")',
          "scaled-damage literal")
    check(cardgen.condition_literal({"kind": "draw_pile_empty"})
          == 'new Condition("draw_pile_empty", 0, null, false)',
          "draw_pile_empty condition literal (no value)")


# ---------------------------------------------------------------- 5. relic on_hp_lost hook
def test_relic_on_hp_lost() -> None:
    print("relic on_hp_lost hook validates; the smoke relic (now exercising it) is clean:")
    check(smoke_relic.validate() == [], f"smoke relic must validate with on_hp_lost: {smoke_relic.validate()}")
    relic = {"name": "Bleeding Charm", "id": "bleeding_charm", "description": "On self-harm, draw.",
             "tier": "starter",
             "hooks": [{"trigger": "on_hp_lost", "once_per_combat": True,
                        "effects": [{"op": "draw", "amount": 1}]}]}
    from btsgen.class_forge import _validate_relic
    check(_validate_relic(relic) == [], f"on_hp_lost relic hook must validate: {_validate_relic(relic)}")
    bogus = {"name": "X", "id": "x", "description": "d", "tier": "starter",
             "hooks": [{"trigger": "on_potion_used", "effects": [{"op": "draw", "amount": 1}]}]}
    check(_validate_relic(bogus) != [], "unknown relic trigger must still be rejected")


# ---------------------------------------------------------------- 6. version + gap + catalog lockstep
def test_version_gap_catalog() -> None:
    print("version bump, gap flips, and catalog buildability:")
    check(bts1.VOCAB_VERSION >= 21, f"bts1.VOCAB_VERSION must be >= 21 (Phase P floor), got {bts1.VOCAB_VERSION}")
    gaps = C.gap_status()
    for n in (21, 22, 24):
        check(gaps.get(n) == "done", f"gap #{n} should parse as done, got {gaps.get(n)}")
    cat = C.load_catalog()
    reaper = cat.by_id.get("reaper_lifesteal")
    check(reaper is not None and reaper.buildable,
          "reaper_lifesteal must be BUILDABLE (gap #21 done + tokens live)")
    check("target_debuff_count" in cat.by_id["debuff_expose"].ops,
          "debuff_expose must carry the target_debuff_count token")
    live = C.live_vocab_tokens()
    for tok in ("damage_dealt_unblocked", "target_debuff_count", "draw_pile_empty"):
        check(tok in live, f"{tok} must be a live (backticked) vocab token")


def test_when_gate_balance_discount(v: CardValidator) -> None:
    print("when-gated effects are score-discounted (draw_pile_empty deepest — the Grand-Finale budget):")
    plain = {"op": "damage", "amount": 30}
    gated = {"op": "damage", "amount": 30, "when": {"kind": "draw_pile_empty"}}
    soft = {"op": "damage", "amount": 30, "when": {"kind": "turn_at_least", "value": 3}}
    s_plain = v._score_effect(plain)
    check(abs(v._score_effect(gated) - s_plain * 0.35) < 1e-9,
          "draw_pile_empty gate must discount to 0.35x (base-game Grand Finale prints ~3x behind it)")
    check(abs(v._score_effect(soft) - s_plain * 0.6) < 1e-9,
          "a generic when gate must discount to 0.6x (matches the prototype conditional op)")
    # The payoff of the discount: a Grand-Finale-strength bomb now fits its budget instead of being
    # auto-tuned into an always-on stat line — while the same numbers UNGATED still trip the ceiling.
    finale = _card([{"op": "damage", "amount": 40, "when": {"kind": "draw_pile_empty"}},
                    {"op": "exhaust"}], rarity="rare", cost=2)
    check(v.balance_warnings(finale) == [],
          f"a 40-damage draw_pile_empty rare must fit the budget: {v.balance_warnings(finale)}")
    ungated_bomb = _card([{"op": "damage", "amount": 40}, {"op": "exhaust"}], rarity="rare", cost=2)
    check(v.balance_warnings(ungated_bomb) != [], "the same numbers UNGATED must still trip the ceiling")


def main() -> int:
    v = CardValidator()
    for t in (test_accepts, test_rejects, test_text, test_emit, test_when_gate_balance_discount):
        t(v)
    test_relic_on_hp_lost()
    test_version_gap_catalog()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
