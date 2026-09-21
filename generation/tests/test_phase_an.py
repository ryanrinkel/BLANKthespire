"""Phase AN — SMALL OPS (VOCAB_GAP_REMEDIATION_PLAN Wave 3, vocab v44) — offline, no API key.

Run:  uv run python -m tests.test_phase_an       (from generation/)
Exits nonzero on any failure. Covers the v44 card-level mechanics on the generation side, in lockstep with the C#:
  1. `gain_max_hp` (the Feed payoff: raise Max HP for the run AND heal that much) — validates 1..5, describes
     byte-identically ("Gain {MaxHp} Max HP."), emits `new EffectSpec("gain_max_hp", N)`; REJECTED above 5, twice on
     one card (one MaxHp var), and inside a trigger payload (card-only);
  2. the `damage` flag `unblockable:true` — validates, describes with the ", ignoring Block" clause in every damage
     shape (plain / AoE / multi-hit / scaled / grow / X), emits the named `Unblockable: true`; REJECTED on a non-damage
     op and inside a trigger payload; `unblockable:false` is a plain hit;
  3. the one-turn self-buffs `temp_thorns` / `temp_focus` — validate, word as "Gain Thorns." / "Gain Focus." (like the
     temp stats), emit, are legal as a SELF trigger payload and never as a targeted debuff; census buckets them
     (temp_thorns exotic, temp_focus specialty); class_forge treats temp_focus as an orb-class mechanic like focus.
Plus: the vocab stamp is >= v44; the schema / vocabulary / statuses dir / relic contract / exemplars / archetypes /
featured menus / coverage menu / blueprint prompt carry the tokens.
"""
from __future__ import annotations

import json
import pathlib
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen, census, class_forge, coverage, featured, paths  # noqa: E402
from btsgen.bridges import card_tokens  # noqa: E402
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


def _card(effects, up=None, **kw):
    base = {"id": "an_test", "name": "AN Test", "type": "attack", "rarity": "uncommon",
            "cost": 1, "target": "enemy", "source": "llm", "effects": effects}
    base["upgrade"] = {"effects": up if up is not None else effects}
    base.update(kw)
    return base


def _power(trigger, payload, **flags):
    trig = {"op": "add_trigger", "trigger": trigger, "effects": payload}
    trig.update(flags)
    return _card([trig], type="power", target="self")


def test_version() -> None:
    print("Phase AN vocab stamp is at least v44:")
    check(bts1.VOCAB_VERSION >= 44, f"bts1.VOCAB_VERSION must be >= 44 (Phase AN), got {bts1.VOCAB_VERSION}")


def _t_gain_max_hp(v: CardValidator) -> None:
    print("gain_max_hp: validates 1..5, describes byte-identically, emits; >5 / twice / in a payload reject:")
    feed = _card([{"op": "damage", "amount": 10}, {"op": "gain_max_hp", "amount": 3}, {"op": "exhaust"}],
                 [{"op": "damage", "amount": 12}, {"op": "gain_max_hp", "amount": 4}, {"op": "exhaust"}], rarity="rare")
    r = v.validate(feed)
    check(r.ok, f"the Feed shape validates: {r.errors}")
    for n in (1, 5):
        check(v.validate(_card([{"op": "gain_max_hp", "amount": n}], type="skill", target="self")).ok, f"gain_max_hp {n} validates")
    r = v.validate(_card([{"op": "gain_max_hp", "amount": 6}], type="skill", target="self"))
    check(not r.ok and any("at most 5" in e or "maximum" in e for e in r.errors), f"gain_max_hp 6 is rejected: {r.errors}")
    check(not v.validate(_card([{"op": "gain_max_hp", "amount": 0}], type="skill", target="self")).ok, "gain_max_hp 0 is rejected")
    check(not v.validate(_card([{"op": "gain_max_hp"}], type="skill", target="self")).ok, "gain_max_hp without an amount is rejected")
    r = v.validate(_card([{"op": "gain_max_hp", "amount": 2}, {"op": "gain_max_hp", "amount": 1}], type="skill", target="self"))
    check(not r.ok and any("MaxHp" in e for e in r.errors), f"two gain_max_hp on one card is rejected (one MaxHp var): {r.errors}")
    check(not v.validate(_power("turn_start", [{"op": "gain_max_hp", "amount": 1}])).ok, "gain_max_hp inside a trigger payload is rejected (card-only)")
    d = cardgen.describe(feed["effects"], "enemy")
    check(d == "Deal {Damage} damage.\nGain {MaxHp} Max HP.\nExhaust.", f"Feed describe: {d!r}")
    _, src = cardgen.gen_class(feed)
    check('new EffectSpec("gain_max_hp", 3)' in src and 'new EffectSpec("gain_max_hp", 4)' in src, "emit carries the plain positional amount (base + upgrade)")
    cc = census.walk_card(feed)
    check(cc.ops["gain_max_hp"] == 2 and "gain_max_hp" in card_tokens(feed), "census / card_tokens see the op")
    dev = next(f for f in featured.FEATURED_MENU if f.id == "devourer")
    check(dev.detect(cc) and not dev.detect(census.walk_card(_card([{"op": "damage", "amount": 6}]))), "devourer detector keys off the op")


def _t_unblockable(v: CardValidator) -> None:
    print("unblockable: validates on damage, describes the clause in every shape, emits the named arg; misuse rejects:")
    pierce = _card([{"op": "damage", "amount": 7, "unblockable": True}], [{"op": "damage", "amount": 10, "unblockable": True}])
    r = v.validate(pierce)
    check(r.ok, f"an unblockable hit validates: {r.errors}")
    want = [
        ("enemy", {"op": "damage", "amount": 7, "unblockable": True}, "Deal {Damage} damage, ignoring Block."),
        ("all_enemies", {"op": "damage", "amount": 7, "unblockable": True}, "Deal {Damage} damage to ALL enemies, ignoring Block."),
        ("random_enemy", {"op": "damage", "amount": 7, "unblockable": True}, "Deal {Damage} damage to a random enemy, ignoring Block."),
        ("enemy", {"op": "damage", "amount": 3, "hits": 3, "unblockable": True}, "Deal {Damage} damage {Hits} times, ignoring Block."),
        ("enemy", {"op": "damage", "amount": 1, "scale": "block", "unblockable": True}, "Deal damage equal to your Block, ignoring Block."),
        ("enemy", {"op": "damage", "amount": 1, "scale": "x", "unblockable": True}, "Deal X damage, ignoring Block."),
        ("enemy", {"op": "damage", "amount": 8, "grow": 3, "unblockable": True}, "Deal {CalculatedDamage} damage, ignoring Block. Grows by 3 each time it is played this combat."),
        ("enemy", {"op": "damage", "amount": 7, "unblockable": False}, "Deal {Damage} damage."),
        ("enemy", {"op": "damage", "amount": 7}, "Deal {Damage} damage."),
    ]
    for tgt, eff, text in want:
        d = cardgen.describe([eff], tgt)
        check(d == text, f"describe {tgt} {eff}: {d!r}")
    for tgt, ty in (("all_enemies", "attack"), ("random_enemy", "attack")):
        check(v.validate(_card([{"op": "damage", "amount": 6, "unblockable": True}], target=tgt, type=ty)).ok, f"unblockable on a {tgt} card validates")
    check(v.validate(_card([{"op": "damage", "amount": 3, "hits": 3, "unblockable": True}])).ok, "unblockable + hits validates")
    check(v.validate(_card([{"op": "damage", "amount": 1, "scale": "x", "unblockable": True}], cost="X")).ok, "unblockable on an X-cost damage validates")
    _, src = cardgen.gen_class(pierce)
    check('new EffectSpec("damage", 7, Unblockable: true)' in src and 'new EffectSpec("damage", 10, Unblockable: true)' in src, "emit carries Unblockable: true")
    _, src = cardgen.gen_class(_card([{"op": "damage", "amount": 4, "hits": 2, "unblockable": True}]))
    check('new EffectSpec("damage", 4, null, 2, Unblockable: true)' in src, "emit: hits + unblockable")
    _, src = cardgen.gen_class(_card([{"op": "damage", "amount": 7, "unblockable": False}]))
    check('new EffectSpec("damage", 7)' in src and "Unblockable" not in src, "unblockable:false emits a plain hit")
    r = v.validate(_card([{"op": "block", "amount": 5, "unblockable": True}], type="skill", target="self"))
    check(not r.ok and any("only applies to damage" in e or "unblockable" in e for e in r.errors), f"unblockable on block is rejected: {r.errors}")
    check(not v.validate(_power("attacked", [{"op": "damage", "amount": 3, "target": "attacker", "unblockable": True}])).ok,
          "unblockable inside a trigger payload is rejected (card-level only)")
    cc = census.walk_card(pierce)
    check(cc.unblockable == 2 and "unblockable" in card_tokens(pierce), f"census counts the flag (base + upgrade): {cc.unblockable}")
    check(census.walk_card(_card([{"op": "damage", "amount": 7, "unblockable": False}])).unblockable == 0, "unblockable:false is not counted")
    ps = next(f for f in featured.FEATURED_MENU if f.id == "piercing_strike")
    check(ps.detect(cc) and not ps.detect(census.walk_card(_card([{"op": "damage", "amount": 6}]))), "piercing_strike detector keys off the flag")


def _t_temp_statuses(v: CardValidator) -> None:
    print("temp_thorns / temp_focus: validate, word like the temp stats, emit; self-only in a payload; census buckets:")
    bristle = _card([{"op": "apply_status", "status": "temp_thorns", "amount": 4}, {"op": "block", "amount": 5}], type="skill", target="self")
    check(v.validate(bristle).ok, f"temp_thorns validates: {v.validate(bristle).errors}")
    flash = _card([{"op": "apply_status", "status": "temp_focus", "amount": 2}, {"op": "channel_orb", "orb": "lightning", "amount": 1}],
                  type="skill", target="self", cost=0)
    check(v.validate(flash).ok, f"temp_focus validates: {v.validate(flash).errors}")
    d = cardgen.describe(bristle["effects"], "self")
    check(d == "Gain Thorns.\nGain {Block} Block.", f"temp_thorns describe: {d!r}")
    d = cardgen.describe([{"op": "damage", "amount": 6}, {"op": "apply_status", "status": "temp_thorns", "amount": 3}], "all_enemies")
    check(d == "Deal {Damage} damage to ALL enemies.\nGain Thorns.", f"a self-buff rides an AoE attack without the suffix: {d!r}")
    d = cardgen.describe(flash["effects"], "self")
    check(d.startswith("Gain Focus.\n"), f"temp_focus describe: {d!r}")
    _, src = cardgen.gen_class(bristle)
    check('new EffectSpec("apply_status", 4, "temp_thorns")' in src, "emit carries the status name")
    tp = _power("turn_start", [{"op": "apply_status", "status": "temp_thorns", "amount": 3}])
    check(v.validate(tp).ok, f"temp_thorns as a SELF trigger payload validates: {v.validate(tp).errors}")
    d = cardgen.describe(tp["effects"], "self")
    check(d.startswith("At the start of your turn, ") and d.endswith("gain 3 Thorns."), f"trigger wording: {d!r}")
    check(not v.validate(_power("turn_start", [{"op": "apply_status", "status": "temp_thorns", "amount": 3, "target": "enemy"}])).ok,
          "a TARGETED temp_thorns payload is rejected (self-buffs only)")
    cc = census.walk_card(bristle)
    check("temp_thorns" in cc.exotic_status_kinds, f"temp_thorns is an exotic status: {cc.exotic_status_kinds}")
    cf = census.walk_card(flash)
    check("temp_focus" in cf.specialty_status_kinds and not cf.exotic_status_kinds, f"temp_focus is a specialty status: {cf.specialty_status_kinds}")
    check(class_forge._card_uses_orbs(flash) and class_forge._card_uses_orbs(_card([{"op": "apply_status", "status": "temp_focus", "amount": 1}], type="skill", target="self")),
          "class_forge treats temp_focus as an orb-class mechanic")
    check(not class_forge._card_uses_orbs(bristle), "temp_thorns is not an orb-class mechanic")
    from btsgen import validator as _val
    check("temp_thorns" in _val._STATUS_WEIGHT and "temp_focus" in _val._STATUS_WEIGHT
          and {"temp_thorns", "temp_focus"} <= _val._SELF_BUFF_STATUSES, "validator weights + self-buff set carry both")
    check({"temp_thorns", "temp_focus"} <= cardgen._BUFFS and cardgen.STATUS_NAME["temp_thorns"] == "Thorns"
          and cardgen.STATUS_NAME["temp_focus"] == "Focus", "cardgen buff set + display names")
    bw = next(f for f in featured.FEATURED_MENU if f.id == "burst_window")
    check(bw.detect(cc), "burst_window detects temp_thorns")
    ff = next(f for f in featured.CLASS_KIND_MENU if f.id == "orb_flash_focus")
    check(ff.detect(cf) and not ff.detect(cc), "orb_flash_focus detects temp_focus only")


def _t_contract() -> None:
    print("schema / vocabulary / statuses dir / relic contract / exemplars / archetypes / menus / blueprint prompt carry the tokens:")
    schema = json.loads(paths.CARD_SCHEMA.read_text(encoding="utf-8"))
    eff = schema["$defs"]["effect"]["properties"]
    trig = schema["$defs"]["triggerEffect"]["properties"]
    check("gain_max_hp" in eff["op"]["enum"] and "gain_max_hp" not in trig["op"]["enum"], "schema: gain_max_hp is a card-level op only")
    check("unblockable" in eff and eff["unblockable"]["type"] == "boolean" and "unblockable" not in trig, "schema: unblockable is a card-level effect flag only")
    check({"temp_thorns", "temp_focus"} <= set(eff["status"]["enum"]) and {"temp_thorns", "temp_focus"} <= set(trig["status"]["enum"]),
          "schema: both status enums carry the temp statuses")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    for tok in ("gain_max_hp", "temp_thorns", "temp_focus", "unblockable"):
        check(f"`{tok}`" in vocab, f"VOCABULARY.md names `{tok}`")
    check("ignoring Block" in vocab and "Feed" in vocab and "Gain `amount` Max HP" in vocab, "VOCABULARY.md shows the wordings")
    check((paths.STATUSES_DIR / "temp_thorns.json").exists() and (paths.STATUSES_DIR / "temp_focus.json").exists(), "statuses dir has both ids")
    rschema = json.loads(paths.RELIC_SCHEMA.read_text(encoding="utf-8"))
    check("temp_thorns" in json.dumps(rschema) and "temp_focus" in json.dumps(rschema), "relic schema status enum carries both")
    check("`temp_thorns`" in paths.RELIC_VOCABULARY.read_text(encoding="utf-8"), "RELIC_VOCABULARY.md lists temp_thorns")
    data = pathlib.Path(paths.__file__).parent / "data"
    pool = json.loads((data / "exemplar_pool.json").read_text(encoding="utf-8"))
    by_id = {e["card"]["id"]: e for e in pool["exemplars"]}
    for cid, needs in (("ex_devouring_bite", ""), ("ex_piercing_lunge", ""), ("ex_bristle_up", ""), ("ex_flash_focus", "orb")):
        check(cid in by_id and by_id[cid]["needs"] == needs, f"exemplar {cid} present with needs={needs!r}")
    arch = json.loads((data / "archetypes.json").read_text(encoding="utf-8"))
    ops = {a["id"]: a["vocabulary"]["ops"] for a in arch["archetypes"]}
    check("gain_max_hp" in ops["iron_regrowth"] and "unblockable" in ops["strike_tempo"]
          and "temp_thorns" in ops["burst_window"] and "temp_focus" in ops["orb_channel"], "archetypes list the new tokens")
    ids = {f.id for f in featured.FEATURED_MENU}
    check({"devourer", "piercing_strike"} <= ids and "orb_flash_focus" in {f.id for f in featured.CLASS_KIND_MENU}, "featured menus carry the AN entries")
    check("temp_thorns" in {k for k, _ in coverage.EXOTIC_MENU_V2} and "temp_thorns" in coverage.DIRECTIVE_BY_KEY
          and "temp_thorns" in coverage.CENSUS_DETECTOR, "coverage exotic menu v2 carries temp_thorns")
    from btsgen.class_forge import _BlueprintContract
    prompt = _BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()
    check("gain_max_hp" in prompt and "unblockable" in prompt and "temp_thorns" in prompt and "temp_focus" in prompt,
          "the blueprint prompt points at the new tokens")


def main() -> int:
    v = CardValidator()
    test_version()
    _t_gain_max_hp(v)
    _t_unblockable(v)
    _t_temp_statuses(v)
    _t_contract()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


# pytest entry point (re-runs main's checks in isolation for a clear failure name)
def test_phase_an_all() -> None:
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
