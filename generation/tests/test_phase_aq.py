"""Phase AQ — STATUS-POOL HOOKS (VOCAB_GAP_REMEDIATION_PLAN Wave 3, vocab v47) — offline, no API key.

Run:  uv run python -m tests.test_phase_aq       (from generation/)
Exits nonzero on any failure. Covers the v47 additions on the generation side, in lockstep with the C#:
  1. class-level `status_pool` gains two hooks — `damage_over_time` (DEBUFF, must decay) and `hit_count` (BUFF, must
     decay) — and `mode: multiplicative` on damage_dealt / damage_taken only: class_forge._validate_status_pool accepts
     every legal shape (both decays, both damage hooks in either mode, the untouched J-1 shapes) and rejects every
     illegal one (a DoT buff, a hit_count debuff, either with decay none, multiplicative on a non-damage hook, a bad
     mode) with the same wording family as ForgedCharacters.TryParseStatus;
  2. the C# mirror: ForgedCharacters' StatusHooks / StatusModes / MultiplicativeHooks / MustDecayHooks sets carry the
     tokens, ForgedStatusPower overrides ModifyAttackHitCount (gated on AttackCommand.Attacker), ModifyDamageMultiplicative
     (IsPoweredAttack gate, cap ×2) and BeforeSideTurnStart (the Poison props: Unblockable | Unpowered), and the
     VocabVersion stamp is 47;
  3. the card level is unchanged: a card applying a v47 status validates through the same apply_status_custom path
     (Apply N <Name> / Gain N <Name>), and the two new exemplars validate under the pool's placeholder context;
  4. the contract carries the tokens: VOCABULARY.md rows + the mode bullet, DESIGN_HEURISTICS pricing, app.js labels,
     archetype metaphors, the blueprint prompt (status-pool paragraph + the burn/flurry fantasy pointers), and the
     rule-0.9 prompt budget is reported.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen, paths  # noqa: E402
from btsgen.class_forge import _BlueprintContract, _validate_status_pool  # noqa: E402
from btsgen.harness_v2 import EXEMPLAR_CONTEXT, exemplar_validator  # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402

_PASS = 0
_FAIL = 0

MOD_CODE = paths.VOCABULARY.parents[1] / "BlankTheSpireCode"   # mod/contract/.. -> mod/BlankTheSpireCode
WEB_APP = paths.VOCABULARY.parents[2] / "web" / "static" / "app.js"


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _st(name, hook, typ, decay="none", mode=None, **extra):
    d = {"name": name, "emoji": "🔥", "type": typ, "hook": hook, "decay": decay, "description": f"{name}."}
    if mode is not None:
        d["mode"] = mode
    d.update(extra)
    return d


def _accepts(pool, label):
    errs = _validate_status_pool(pool)
    check(not errs, f"{label} validates: {errs}")


def _rejects(pool, needle, label):
    errs = _validate_status_pool(pool)
    check(any(needle.lower() in e.lower() for e in errs), f"{label} is rejected mentioning '{needle}': {errs}")


def test_version() -> None:
    print("Phase AQ vocab stamp is at least v47 (Python + C#):")
    check(bts1.VOCAB_VERSION >= 47, f"bts1.VOCAB_VERSION must be >= 47 (Phase AQ), got {bts1.VOCAB_VERSION}")
    fc = (MOD_CODE / "Engine" / "ForgedCards.cs").read_text(encoding="utf-8")
    m = re.search(r"public const int VocabVersion = (\d+);", fc)
    check(m is not None and int(m.group(1)) >= 47, f"ForgedCards.VocabVersion >= 47: {m and m.group(1)}")
    check(m is not None and int(m.group(1)) >= bts1.VOCAB_VERSION, "bts1.VOCAB_VERSION <= ForgedCards.VocabVersion")


def _t_pool_accepts() -> None:
    print("status_pool: every legal v47 shape validates (and the J-1 shapes are untouched):")
    _accepts([_st("Scorch", "damage_over_time", "debuff", "lose_one_eot")], "a Poison-shaped DoT (lose_one_eot)")
    _accepts([_st("Cinder", "damage_over_time", "debuff", "lose_all_eot")], "a one-shot DoT (lose_all_eot)")
    _accepts([_st("Flurry", "hit_count", "buff", "lose_all_eot")], "a hit_count stance (lose_all_eot)")
    _accepts([_st("Tempo", "hit_count", "buff", "lose_one_eot", stack="single")], "a single-stack hit_count (lose_one_eot)")
    _accepts([_st("Kindle", "damage_dealt", "buff", "none", mode="multiplicative")], "damage_dealt multiplicative buff")
    _accepts([_st("Ashen", "damage_taken", "debuff", "lose_one_eot", mode="multiplicative")], "damage_taken multiplicative debuff")
    _accepts([_st("Razor Focus", "damage_dealt", "buff", "none", mode="additive")], "explicit additive still validates")
    _accepts([_st("Razor Focus", "damage_dealt", "buff"), _st("Brittle", "damage_taken", "debuff"),
              _st("Ironweave", "block_gained", "buff"), _st("Quickstep", "card_draw", "buff", "lose_one_eot")],
             "the J-1 Bladedancer pool (no mode key)")
    _accepts([_st("Scorch", "damage_over_time", "debuff", "lose_one_eot"), _st("Flurry", "hit_count", "buff", "lose_all_eot"),
              _st("Kindle", "damage_dealt", "buff", mode="multiplicative"),
              _st("Ashen", "damage_taken", "debuff", "lose_one_eot", mode="multiplicative")],
             "the AQ gap-tester pool (4 statuses, every new shape)")


def _t_pool_rejects() -> None:
    print("status_pool: every illegal v47 shape rejects with the C# wording family:")
    _rejects([_st("Warmth", "damage_over_time", "buff", "lose_one_eot")], "must be a debuff", "a DoT declared as a buff")
    _rejects([_st("Scorch", "damage_over_time", "debuff", "none")], "must decay", "a DoT with decay none")
    _rejects([_st("Scorch", "damage_over_time", "debuff")], "must decay", "a DoT with the default decay (none)")
    _rejects([_st("Slow", "hit_count", "debuff", "lose_all_eot")], "must be a buff", "a hit_count debuff")
    _rejects([_st("Flurry", "hit_count", "buff", "none")], "must decay", "a permanent hit_count")
    for hook, typ in (("block_gained", "buff"), ("energy_gain", "buff"), ("card_draw", "buff"),
                      ("hit_count", "buff"), ("damage_over_time", "debuff")):
        _rejects([_st("X", hook, typ, "lose_one_eot", mode="multiplicative")], "multiplicative is only valid",
                 f"multiplicative on {hook}")
    _rejects([_st("X", "damage_dealt", "buff", mode="squared")], "mode must be one of", "an unknown mode")
    _rejects([_st("X", "burn", "debuff", "lose_one_eot")], "hook must be one of", "an unknown hook (burn is a fantasy, not a hook)")
    # the pre-AQ side rules still hold
    _rejects([_st("X", "damage_dealt", "debuff")], "must be a buff", "damage_dealt as a debuff")
    _rejects([_st("X", "damage_taken", "buff")], "must be a debuff", "damage_taken as a buff")


def _t_csharp_mirror() -> None:
    print("C# mirror: ForgedCharacters sets + ForgedStatusPower hooks carry the v47 shapes:")
    fch = (MOD_CODE / "Engine" / "ForgedCharacters.cs").read_text(encoding="utf-8")
    hooks = re.search(r"StatusHooks =\s*\[([^\]]*)\]", fch)
    check(hooks is not None and all(f'"{h}"' in hooks.group(1) for h in
                                    ("damage_dealt", "damage_taken", "block_gained", "energy_gain", "card_draw",
                                     "damage_over_time", "hit_count")), "ForgedCharacters.StatusHooks has all 7 hooks")
    modes = re.search(r"StatusModes =\s*\[([^\]]*)\]", fch)
    check(modes is not None and '"additive"' in modes.group(1) and '"multiplicative"' in modes.group(1),
          "ForgedCharacters.StatusModes = additive + multiplicative")
    mh = re.search(r"MultiplicativeHooks =\s*\[([^\]]*)\]", fch)
    check(mh is not None and set(re.findall(r'"(\w+)"', mh.group(1))) == {"damage_dealt", "damage_taken"},
          "ForgedCharacters.MultiplicativeHooks = the two damage hooks")
    md = re.search(r"MustDecayHooks =\s*\[([^\]]*)\]", fch)
    check(md is not None and set(re.findall(r'"(\w+)"', md.group(1))) == {"damage_over_time", "hit_count"},
          "ForgedCharacters.MustDecayHooks = damage_over_time + hit_count")
    fsp = (MOD_CODE / "Powers" / "ForgedStatusPower.cs").read_text(encoding="utf-8")
    check("public override int ModifyAttackHitCount(AttackCommand attack, int hitCount)" in fsp,
          "ForgedStatusPower overrides ModifyAttackHitCount(AttackCommand, int)")
    check("attack.Attacker != Owner" in fsp, "hit_count gates on AttackCommand.Attacker == Owner (the J-1 blocker is lifted)")
    check("public override decimal ModifyDamageMultiplicative(" in fsp, "ForgedStatusPower overrides ModifyDamageMultiplicative")
    check("props.IsPoweredAttack()" in fsp, "the multiplicative hook gates on IsPoweredAttack (Vulnerable/Weak/Strength convention)")
    check("MultiplicativeCap = 2.0m" in fsp and "MultiplicativeStep = 0.1m" in fsp, "x(1 + 0.1*stacks) capped at x2")
    check("public override async Task AfterSideTurnStart(" in fsp, "ForgedStatusPower overrides AfterSideTurnStart (Poison's hook) for the DoT tick")
    check("override async Task BeforeSideTurnStart(" not in fsp, "the DoT tick is NOT on BeforeSideTurnStart (a lethal tick there NREs the turn start)")
    check("new ThrowingPlayerChoiceContext()" in fsp, "the DoT tick uses Poison's ThrowingPlayerChoiceContext")
    check("ValueProp.Unblockable | ValueProp.Unpowered" in fsp, "the DoT tick uses Poison's props (Unblockable | Unpowered)")
    check('"damage_over_time" =>' in fsp and '"hit_count"    =>' in fsp, "Describe covers both new hooks")
    # the additive hook must NOT double-dip when the spec is multiplicative
    check('s.Mode == "multiplicative") return 0m' in fsp, "ModifyDamageAdditive returns 0 for a multiplicative spec")


def _t_card_level() -> None:
    print("card level: applying a v47 status is the unchanged apply_status_custom path; exemplars validate:")
    v = CardValidator(extra_statuses={"Scorch", "Flurry"})
    brand = {"id": "aq_brand", "name": "Brand", "type": "attack", "rarity": "common", "cost": 1, "target": "enemy",
             "source": "llm", "effects": [{"op": "damage", "amount": 5},
                                          {"op": "apply_status_custom", "status_name": "Scorch", "amount": 3}]}
    r = v.validate(dict(brand))
    check(r.ok, f"an enemy-target card applying Scorch validates: {r.errors}")
    check(cardgen.describe(brand["effects"], "enemy") == "Deal {Damage} damage.\nApply 3 Scorch.",
          f"describe: {cardgen.describe(brand['effects'], 'enemy')!r}")
    stance = {"id": "aq_stance", "name": "Stance", "type": "skill", "rarity": "uncommon", "cost": 1, "target": "self",
              "source": "llm", "effects": [{"op": "apply_status_custom", "status_name": "Flurry", "amount": 1}]}
    check(v.validate(dict(stance)).ok, f"a self-target card gaining Flurry validates: {v.validate(dict(stance)).errors}")
    check(cardgen.describe(stance["effects"], "self") == "Gain 1 Flurry.", f"describe: {cardgen.describe(stance['effects'], 'self')!r}")
    check(not CardValidator().validate(dict(brand)).ok, "without a status context the same card is rejected (class-only)")
    check({"Scorch", "Flurry"} <= set(EXEMPLAR_CONTEXT["extra_statuses"]), "EXEMPLAR_CONTEXT names Scorch + Flurry")
    data = pathlib.Path(paths.__file__).parent / "data"
    pool = json.loads((data / "exemplar_pool.json").read_text(encoding="utf-8"))
    by_id = {e["card"]["id"]: e for e in pool["exemplars"]}
    ev = exemplar_validator()
    for cid in ("ex_scorching_brand", "ex_flurry_stance"):
        check(cid in by_id and by_id[cid]["needs"] == "status", f"exemplar {cid} present (needs 'status')")
        if cid in by_id:
            rr = ev.validate(dict(by_id[cid]["card"]))
            check(rr.ok, f"exemplar {cid} validates: {rr.errors}")
    check(len(pool["exemplars"]) >= 112, f"pool grew to >= 112 (got {len(pool['exemplars'])})")


def _t_contract() -> None:
    print("contract / heuristics / web / archetypes / blueprint prompt carry the tokens:")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    check("| `damage_over_time` | **debuff** |" in vocab and "| `hit_count`    | **buff** |" in vocab,
          "VOCABULARY.md has both hook rows with their required sides")
    check("- `mode` (optional, v47)" in vocab and "multiplicative" in vocab, "VOCABULARY.md documents mode")
    heur = (paths.VOCABULARY.parent / "DESIGN_HEURISTICS.md").read_text(encoding="utf-8")
    check("damage_over_time" in heur and "hit_count" in heur and "multiplicative" in heur, "DESIGN_HEURISTICS.md prices all three")
    app = WEB_APP.read_text(encoding="utf-8")
    check("damage_over_time:" in app and "hit_count:" in app and 'st.mode === "multiplicative"' in app,
          "app.js labels both hooks and the multiplicative mode")
    data = pathlib.Path(paths.__file__).parent / "data"
    arch = json.loads((data / "archetypes.json").read_text(encoding="utf-8"))
    sig = next(a for a in arch["archetypes"] if a["id"] == "status_signature")
    check("the lingering burn" in sig["metaphors"] and "the extra cut" in sig["metaphors"], "status_signature gained the burn / extra-cut metaphors")
    prompt = _BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()
    for tok in ("`damage_over_time`", "`hit_count`", '"multiplicative"', "hook damage_over_time: Scorch", "hook hit_count"):
        check(tok in prompt, f"the blueprint prompt carries {tok}")
    check("or Poison;" not in prompt, "the burn fantasy no longer routes to Poison first")
    print(f"  (rule 0.9) blueprint prompt: {len(prompt):,} chars (Phase AP baseline 90,547)")


def main() -> int:
    test_version()
    _t_pool_accepts()
    _t_pool_rejects()
    _t_csharp_mirror()
    _t_card_level()
    _t_contract()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


# pytest entry point (re-runs main's checks in isolation for a clear failure name)
def test_phase_aq_all() -> None:
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
