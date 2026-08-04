"""Phase S balance-gauge tests (VOCABULARY_GAPS #1: op `balance_step` + light_ge/dark_ge/centered) — offline, no API key.

Run:  uv run python -m tests.test_phase_s       (from generation/)
Exits nonzero on any failure. Exercises the mod-contract validator + cardgen text/emit for the `balance_step`
op (card-level and in trigger payloads), the three gauge conditions, the class-level balance pairing warnings,
and the version/gap/catalog lockstep. Mirrors the C# ForgedCards / Conditions / EffectRunner / TriggerRunner /
ForgedBalancePower changes (vocab v24).
"""
from __future__ import annotations

import sys

# MUST repoint at the constrained mod contract BEFORE importing the btsgen modules that read paths.
from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen                          # noqa: E402
from btsgen.validator import CardValidator                # noqa: E402
from btsgen.character_validator import balance_pairing_warnings  # noqa: E402
from btsgen.frontend import catalog as C                  # noqa: E402

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
    base = {"id": "s_test", "name": "S Test", "type": "skill", "rarity": "uncommon",
            "cost": 1, "target": "self", "source": "llm", "effects": effects}
    base.update(kw)
    return base


# ---------------------------------------------------------------- 1. validator ACCEPTS
def test_accepts(v: CardValidator) -> None:
    print("valid Phase S cards validate:")
    # dark income (a cheap skill that shifts the gauge)
    dark = _card([{"op": "balance_step", "pole": "dark", "amount": 2}])
    check(v.validate(dark).ok, f"balance_step dark income should validate: {v.validate(dark).errors}")
    # light income
    light = _card([{"op": "balance_step", "pole": "light", "amount": 1}])
    check(v.validate(light).ok, f"balance_step light income should validate: {v.validate(light).errors}")
    # a dark-gated damage payoff (attack; conditional bonus on the base op is fine — gate the whole hit)
    dark_payoff = _card([{"op": "damage", "amount": 10, "when": {"kind": "dark_ge", "value": 5}}],
                        type="attack", target="enemy")
    check(v.validate(dark_payoff).ok, f"dark_ge-gated damage should validate: {v.validate(dark_payoff).errors}")
    # a light-gated block payoff
    light_payoff = _card([{"op": "block", "amount": 12, "when": {"kind": "light_ge", "value": 5}}])
    check(v.validate(light_payoff).ok, f"light_ge-gated block should validate: {v.validate(light_payoff).errors}")
    # a centered-gated rare bomb (the knife's-edge payoff)
    centered = _card([{"op": "damage", "amount": 20, "when": {"kind": "centered", "value": 2}}],
                     type="attack", target="all_enemies", rarity="rare")
    check(v.validate(centered).ok, f"centered-gated bomb should validate: {v.validate(centered).errors}")
    # a turn_start engine power that shifts the gauge (trigger-side income — the engine half)
    engine = _card([{"op": "add_trigger", "trigger": "turn_start",
                     "effects": [{"op": "balance_step", "pole": "dark", "amount": 2}]}], type="power")
    check(v.validate(engine).ok, f"turn_start -> balance_step engine should validate: {v.validate(engine).errors}")
    # income + a DIFFERENT-op gated payoff on one card (dark step now, block if already dark — legal, distinct vars)
    combo = _card([{"op": "balance_step", "pole": "dark", "amount": 2},
                   {"op": "block", "amount": 8, "when": {"kind": "dark_ge", "value": 4}}])
    check(v.validate(combo).ok, f"income + gated-block on one card should validate: {v.validate(combo).errors}")


# ---------------------------------------------------------------- 2. validator REJECTS
def test_rejects(v: CardValidator) -> None:
    print("Phase S misuse is rejected:")

    def bad(card: dict, why: str) -> None:
        check(not v.validate(card).ok, why)

    # balance_step needs a pole
    bad(_card([{"op": "balance_step", "amount": 2}]), "balance_step with no pole must be rejected")
    # invalid pole
    bad(_card([{"op": "balance_step", "pole": "grey", "amount": 2}]), "balance_step with a bad pole must be rejected")
    # amount cap is 5
    bad(_card([{"op": "balance_step", "pole": "dark", "amount": 6}]), "balance_step amount > 5 must be rejected")
    # needs amount >= 1
    bad(_card([{"op": "balance_step", "pole": "dark"}]), "balance_step with no amount must be rejected")
    bad(_card([{"op": "balance_step", "pole": "dark", "amount": 0}]), "balance_step amount 0 must be rejected")
    # can't be scaled (not damage/block/draw)
    bad(_card([{"op": "balance_step", "pole": "dark", "amount": 2, "scale": "cards_in_hand"}]),
        "scaled balance_step must be rejected")
    # 'pole' only applies to balance_step
    bad(_card([{"op": "block", "amount": 5, "pole": "dark"}]), "'pole' on a non-balance_step op must be rejected")
    # the three conditions need a value
    bad(_card([{"op": "damage", "amount": 8, "when": {"kind": "dark_ge"}}], type="attack", target="enemy"),
        "dark_ge with no value must be rejected")
    bad(_card([{"op": "damage", "amount": 8, "when": {"kind": "centered", "value": 0}}], type="attack", target="enemy"),
        "centered with value 0 must be rejected (schema value minimum 1)")
    # a trigger-payload balance_step can't be scaled (fixed drumbeat, like forge)
    bad(_card([{"op": "add_trigger", "trigger": "turn_start",
                "effects": [{"op": "balance_step", "pole": "dark", "amount": 2, "scale": "cards_retained"}]}],
              type="power"),
        "a scaled trigger balance_step must be rejected")
    # a trigger-payload balance_step needs a pole
    bad(_card([{"op": "add_trigger", "trigger": "turn_start",
                "effects": [{"op": "balance_step", "amount": 2}]}], type="power"),
        "a trigger balance_step with no pole must be rejected")


# ---------------------------------------------------------------- 3. text byte-match (mirrors C# Describe)
def test_text(_v: CardValidator) -> None:
    print("synthesized card text matches C# Describe/TriggerSentence/TriggerFragment:")

    def desc(effects: list[dict], target: str = "self") -> str:
        return cardgen.describe(effects, target)

    check(desc([{"op": "balance_step", "pole": "dark", "amount": 2}]) == "Shift 2 toward the Dark.",
          "dark income sentence")
    check(desc([{"op": "balance_step", "pole": "light", "amount": 3}]) == "Shift 3 toward the Light.",
          "light income sentence")
    check(desc([{"op": "damage", "amount": 10, "when": {"kind": "dark_ge", "value": 5}}], "enemy")
          == "Deal {Damage} damage if your Dark is 5+.",
          "dark_ge-gated damage sentence (condition woven in)")
    check(desc([{"op": "block", "amount": 12, "when": {"kind": "light_ge", "value": 5}}])
          == "Gain {Block} Block if your Light is 5+.",
          "light_ge-gated block sentence")
    check(desc([{"op": "damage", "amount": 20, "when": {"kind": "centered", "value": 2}}], "all_enemies")
          == "Deal {Damage} damage to ALL enemies if you are centered (within 2).",
          "centered-gated AoE bomb sentence")
    check(desc([{"op": "add_trigger", "trigger": "turn_start",
                 "effects": [{"op": "balance_step", "pole": "dark", "amount": 2}]}])
          == "At the start of your turn, shift 2 toward the Dark.",
          "turn_start -> balance engine fragment")


# ---------------------------------------------------------------- 4. C#-emit round-trip (effect_literal)
def test_emit(_v: CardValidator) -> None:
    print("effect_literal emits the expected C# EffectSpec literals:")
    check(cardgen.effect_literal({"op": "balance_step", "pole": "dark", "amount": 2})
          == 'new EffectSpec("balance_step", 2, Pole: "dark")',
          "balance_step literal (named Pole arg)")
    check(cardgen.effect_literal({"op": "balance_step", "pole": "light", "amount": 1,
                                  "when": {"kind": "centered", "value": 2}})
          == 'new EffectSpec("balance_step", 1, Pole: "light", When: new Condition("centered", 2, null, false))',
          "balance_step literal with a centered When")
    check(cardgen.effect_literal({"op": "damage", "amount": 8, "when": {"kind": "dark_ge", "value": 5}})
          == 'new EffectSpec("damage", 8, When: new Condition("dark_ge", 5, null, false))',
          "dark_ge-gated damage literal")
    check(cardgen.effect_literal({"op": "add_trigger", "trigger": "turn_start",
                                  "effects": [{"op": "balance_step", "pole": "dark", "amount": 2}]})
          == 'new EffectSpec("add_trigger", 0, Trigger: "turn_start", '
             'Triggered: [new EffectSpec("balance_step", 2, Pole: "dark")])',
          "turn_start -> balance_step add_trigger literal")


# ---------------------------------------------------------------- 5. class-level pairing warnings
def _pool_card(cid: str, effects: list[dict], **kw) -> dict:
    base = {"id": cid, "name": cid, "type": "skill", "rarity": "common",
            "cost": 1, "target": "self", "source": "llm", "effects": effects}
    base.update(kw)
    return base


def test_pairing() -> None:
    print("balance_pairing_warnings flags one-pole / no-payoff / dead-gate sets, passes a whole set:")
    dark_inc = _pool_card("dark_step", [{"op": "balance_step", "pole": "dark", "amount": 2}])
    light_inc = _pool_card("light_step", [{"op": "balance_step", "pole": "light", "amount": 2}])
    dark_gate = _pool_card("dark_bomb", [{"op": "damage", "amount": 10, "when": {"kind": "dark_ge", "value": 5}}],
                           type="attack", target="enemy", rarity="rare")
    centered_gate = _pool_card("held", [{"op": "block", "amount": 12, "when": {"kind": "centered", "value": 2}}],
                               rarity="rare")

    # one-pole income (only dark) + a gated payoff -> the one-pole warning fires (it's just Forge with steps)
    one_pole = balance_pairing_warnings([dark_inc, dark_gate])
    check(any("one-pole" in w for w in one_pole), f"one-pole income should warn: {one_pole}")
    # both-pole income but NO gated payoff -> the no-payoff warning fires
    no_payoff = balance_pairing_warnings([dark_inc, light_inc])
    check(any("no gated payoff" in w for w in no_payoff), f"income with no gated payoff should warn: {no_payoff}")
    # a gated payoff with NO gauge income anywhere -> the dead-gate warning fires
    dead_gate = balance_pairing_warnings([dark_gate])
    check(any("no gauge" in w for w in dead_gate), f"a gated payoff with no income should warn: {dead_gate}")
    # a well-formed set (income on BOTH poles + a centered-gated payoff) -> no warnings
    good = balance_pairing_warnings([dark_inc, light_inc, centered_gate])
    check(good == [], f"a both-pole set with a gated payoff should not warn: {good}")
    # a set that doesn't touch the gauge at all -> no balance warnings (not a balance class)
    none = balance_pairing_warnings([_pool_card("plain", [{"op": "damage", "amount": 6}], type="attack", target="enemy")])
    check(none == [], f"a non-balance set should not warn: {none}")


# ---------------------------------------------------------------- 6. version + gap + catalog lockstep
def test_version_gap_catalog() -> None:
    print("version bump, gap flip, and catalog buildability:")
    check(bts1.VOCAB_VERSION >= 24, f"bts1.VOCAB_VERSION must be >= 24 (Phase S), got {bts1.VOCAB_VERSION}")
    gaps = C.gap_status()
    check(gaps.get(1) == "done", f"gap #1 should parse as done (Phase S), got {gaps.get(1)}")
    cat = C.load_catalog()
    bg = cat.by_id.get("balance_gauge")
    check(bg is not None and bg.buildable,
          f"balance_gauge must be BUILDABLE (gap #1 done + balance_step token live): {bg.block_reasons if bg else 'missing'}")
    check(bg is not None and "balance_step" in bg.ops, "balance_gauge must carry the balance_step op token")
    live = C.live_vocab_tokens()
    for tok in ("balance_step", "light_ge", "dark_ge", "centered"):
        check(tok in live, f"{tok} must be a live (backticked) vocab token")


def main() -> int:
    v = CardValidator()
    for t in (test_accepts, test_rejects, test_text, test_emit):
        t(v)
    test_pairing()
    test_version_gap_catalog()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
