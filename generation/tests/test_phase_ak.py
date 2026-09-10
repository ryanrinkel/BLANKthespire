"""Phase AK — ATTACKER TARGET + ONCE PER COMBAT (VOCAB_GAP_REMEDIATION_PLAN Wave 3, vocab v41) — offline, no API key.

Run:  uv run python -m tests.test_phase_ak       (from generation/)
Exits nonzero on any failure. Covers the two v41 mechanics on the generation side, in lockstep with the C#:
  1. a trigger-payload effect on the `attacked` trigger may carry target:"attacker" — validates, describes
     byte-identically ("… to the attacker"), emits the named C# arg, and is REJECTED on any other trigger;
  2. `once_per_combat` on an add_trigger with a power-hosted reactive trigger — validates, describes
     "(once per combat)", emits `OncePerCombat: true`, and is REJECTED on turn_start/turn_end/ripen, on the
     card-latent on_discard, on a payload effect, at card level, and together with once_per_turn.
Plus: the vocab stamp is v41; the census counts once_per_combat; the schema/vocabulary/exemplars carry the tokens.
"""
from __future__ import annotations

import json
import re
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen, census, paths  # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _power(cid, trigger, payload, **flags):
    trig = {"op": "add_trigger", "trigger": trigger, "effects": payload}
    trig.update(flags)
    return {"id": cid, "name": cid.replace("_", " ").title(), "type": "power", "rarity": "uncommon",
            "cost": 1, "target": "self", "source": "llm", "effects": [trig]}


def test_version() -> None:
    print("Phase AK vocab stamp is v41:")
    check(bts1.VOCAB_VERSION >= 41, f"bts1.VOCAB_VERSION must be >= 41 (Phase AK), got {bts1.VOCAB_VERSION}")


def _t_attacker(v: CardValidator) -> None:
    print("target:'attacker' on an attacked payload validates, describes, emits; rejected elsewhere:")
    rip = _power("ak_riposte", "attacked", [{"op": "damage", "amount": 5, "target": "attacker"}])
    r = v.validate(rip)
    check(r.ok, f"riposte (attacked -> damage to the attacker) should validate: {r.errors}")
    d = cardgen.describe(rip["effects"], "self")
    check(d == "Whenever you are attacked, deal 5 damage to the attacker.", f"describe: {d!r}")
    _, src = cardgen.gen_class(rip)
    check('Target: "attacker"' in src, "emitted C# carries the named Target arg")
    # a debuff riposte reads the same suffix
    weak = _power("ak_weak_back", "attacked", [{"op": "apply_status", "status": "weak", "amount": 1, "target": "attacker"}])
    r = v.validate(weak)
    check(r.ok, f"attacked -> apply Weak to the attacker should validate: {r.errors}")
    check(cardgen.describe(weak["effects"], "self") == "Whenever you are attacked, apply 1 Weak to the attacker.",
          f"debuff describe: {cardgen.describe(weak['effects'], 'self')!r}")
    # once_per_turn + attacker together (the gated counterstroke) is fine
    gated = _power("ak_gated", "attacked", [{"op": "damage", "amount": 12, "target": "attacker"}], once_per_turn=True)
    check(v.validate(gated).ok, f"once_per_turn riposte validates: {v.validate(gated).errors}")
    check(cardgen.describe(gated["effects"], "self") == "Whenever you are attacked, deal 12 damage to the attacker (once per turn).",
          "gated riposte describe")
    # the old 'enemy' form still validates (first hittable enemy — the passive threat family)
    old = _power("ak_old", "attacked", [{"op": "damage", "amount": 4, "target": "enemy"}])
    check(v.validate(old).ok, "target:enemy on attacked stays legal")
    # attacker is REJECTED on every other trigger
    for trig in ("on_card_played", "turn_start", "on_hp_lost", "on_damage_dealt", "on_discard"):
        bad = _power(f"ak_bad_{trig}", trig, [{"op": "damage", "amount": 3, "target": "attacker"}])
        r = v.validate(bad)
        check(not r.ok and any("attacker" in e and "attacked" in e for e in r.errors),
              f"target:attacker on '{trig}' must be rejected naming the rule: {r.errors}")
    # attacker never at card level, and only on damage / enemy-debuff apply_status
    card_level = {"id": "ak_cl", "name": "Cl", "type": "attack", "rarity": "common", "cost": 1, "target": "enemy",
                  "source": "llm", "effects": [{"op": "damage", "amount": 6, "target": "attacker"}]}
    check(not v.validate(card_level).ok, "a card-level effect can't carry target:attacker")
    buff = _power("ak_buff_att", "attacked", [{"op": "apply_status", "status": "strength", "amount": 1, "target": "attacker"}])
    check(not v.validate(buff).ok, "a targeted apply_status must be an enemy debuff (strength rejected)")
    # Phase AL (v42) lifted the "targeted can't be scaled" rule for DAMAGE only — a targeted debuff still can't scale
    scaled = _power("ak_scaled_att", "attacked", [{"op": "apply_status", "status": "weak", "amount": 1, "scale": "cards_retained", "target": "attacker"}])
    check(not v.validate(scaled).ok, "a targeted (non-damage) payload can't be scaled")


def _t_once_per_combat(v: CardValidator) -> None:
    print("once_per_combat on a power-hosted reactive trigger validates, describes, emits; rejected elsewhere:")
    sw = _power("ak_second_wind", "attacked", [{"op": "block", "amount": 12}, {"op": "draw", "amount": 1}], once_per_combat=True)
    r = v.validate(sw)
    check(r.ok, f"once_per_combat attacked power should validate: {r.errors}")
    d = cardgen.describe(sw["effects"], "self")
    check(d == "Whenever you are attacked, gain 12 Block, draw 1 card(s) (once per combat).", f"describe: {d!r}")
    _, src = cardgen.gen_class(sw)
    check("OncePerCombat: true" in src, "emitted C# carries OncePerCombat: true")
    check("OncePerTurn: true" not in src, "no once_per_turn leaks into the emit")
    # every power-hosted reactive kind accepts it
    for trig in ("on_hp_lost", "on_exhaust", "on_card_played", "on_card_drawn", "on_damage_dealt", "on_block_gained", "on_blade_played"):
        c = _power(f"ak_opc_{trig}", trig, [{"op": "block", "amount": 6}], once_per_combat=True)
        r = v.validate(c)
        check(r.ok, f"once_per_combat on '{trig}' validates: {r.errors}")
    # with a fire-time when + a riposte target (the whole shape at once)
    full = _power("ak_full", "attacked", [{"op": "damage", "amount": 15, "target": "attacker"}],
                  once_per_combat=True, when={"kind": "hp_below_half"})
    r = v.validate(full)
    check(r.ok, f"once_per_combat + when + attacker validates: {r.errors}")
    check(cardgen.describe(full["effects"], "self")
          == "Whenever you are attacked, deal 15 damage to the attacker (once per combat) if your HP is below half.",
          f"full describe: {cardgen.describe(full['effects'], 'self')!r}")
    # rejections: non-reactive kinds, the card-latent on_discard, both flags, payload-level, card-level
    for trig in ("turn_start", "turn_end", "ripen", "on_discard"):
        c = _power(f"ak_bad_opc_{trig}", trig, [{"op": "block", "amount": 6}], once_per_combat=True)
        if trig == "ripen":
            c["effects"][0]["amount"] = 2
        r = v.validate(c)
        check(not r.ok and any("once_per_combat" in e for e in r.errors),
              f"once_per_combat on '{trig}' must be rejected: {r.errors}")
    both = _power("ak_both", "attacked", [{"op": "block", "amount": 6}], once_per_combat=True, once_per_turn=True)
    r = v.validate(both)
    check(not r.ok and any("set one, not both" in e for e in r.errors), f"both flags rejected: {r.errors}")
    payload = _power("ak_payload", "attacked", [{"op": "block", "amount": 6, "once_per_combat": True}])
    check(not v.validate(payload).ok, "once_per_combat on a payload effect is rejected")
    card_level = {"id": "ak_cl2", "name": "Cl2", "type": "skill", "rarity": "common", "cost": 1, "target": "self",
                  "source": "llm", "effects": [{"op": "block", "amount": 6, "once_per_combat": True}]}
    check(not v.validate(card_level).ok, "once_per_combat on a non-add_trigger op is rejected")


def _t_census_and_contract() -> None:
    print("census counts once_per_combat; schema / vocabulary / exemplars / archetypes carry the tokens:")
    sw = _power("ak_c1", "attacked", [{"op": "damage", "amount": 5, "target": "attacker"}], once_per_combat=True)
    cc = census.walk_card(sw)
    check(cc.once_per_combat == 1 and cc.targeted_payloads == 1, f"census: opc={cc.once_per_combat} tp={cc.targeted_payloads}")
    agg = census.census_cards([sw, sw])
    check(agg.once_per_combat == 2, "aggregate once_per_combat")
    check("once_per_combat=2" in census.format_report([("X", agg)]), "report prints once_per_combat")
    schema = json.loads(paths.CARD_SCHEMA.read_text(encoding="utf-8"))
    check("attacker" in schema["$defs"]["triggerEffect"]["properties"]["target"]["enum"], "schema payload target enum has attacker")
    check("once_per_combat" in json.dumps(schema), "schema declares once_per_combat")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    tokens = set(re.findall(r"`([a-z][a-z0-9_]*)`", vocab))
    check({"attacker", "once_per_combat"} <= tokens, "VOCABULARY.md backticks both tokens")
    check("to the attacker" in vocab and "(once per combat)" in vocab, "VOCABULARY.md shows both wordings")
    pool = json.loads((paths.__file__ and __import__("pathlib").Path(paths.__file__).parent / "data" / "exemplar_pool.json").read_text(encoding="utf-8"))
    cards = [e["card"] for e in pool["exemplars"]]
    flat = json.dumps(cards)
    check('"target": "attacker"' in flat and '"once_per_combat": true' in flat, "exemplar pool carries both shapes")
    v = CardValidator()
    for c in cards:
        if '"attacker"' in json.dumps(c) or c.get("effects", [{}])[0].get("once_per_combat"):
            r = v.validate(dict(c, source="llm"))
            check(r.ok, f"exemplar {c['id']} validates: {r.errors}")


def main() -> int:
    v = CardValidator()
    test_version()
    _t_attacker(v)
    _t_once_per_combat(v)
    _t_census_and_contract()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


# pytest entry point (re-runs main's checks in isolation for a clear failure name)
def test_phase_ak_all() -> None:
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
