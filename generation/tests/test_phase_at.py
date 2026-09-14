"""Phase AT — SUMMON DAMAGE COUNTS AS "YOU DEAL DAMAGE" (VOCAB_GAP_REMEDIATION_PLAN Wave 3, vocab v50) — offline, no API key.

Run:  uv run python -m tests.test_phase_at       (from generation/)
Exits nonzero on any failure. Covers the v50 change on the generation side, in lockstep with the C#:
  1. the vocab stamp is 50 on both sides (bts1.VOCAB_VERSION <= ForgedCards.VocabVersion);
  2. the C# mirror: ForgedTriggerPower.AfterDamageGiven and ForgedRelic.AfterDamageGiven accept a PET dealer whose owner is
     the hook's owner (the base game's ReaperFormPower / HandDrill idiom), the card path is unchanged (dealer == Owner AND
     cardSource != null), the relic's first_attack one-shot is consumed ONLY on the card path, both log an [AT] tag, and
     PetDamageAttributionPatch stays scoped to PersonalHivePower (the plan's suggested mechanism was NOT widened);
  3. no describe change: "Whenever you deal damage" is still the byte-match sentence for on_damage_dealt (card side), and a
     summon-class pack-tactics card (on_damage_dealt -> buff_summon / draw) validates under the summon context and is
     rejected without it (buff_summon is class-only) — the same rule as before, nothing new to learn;
  4. the contract wording drops "card": VOCABULARY.md, card.schema.json, RELIC_VOCABULARY.md all say the summon's hits
     count; DESIGN_HEURISTICS' summon_swarm note names the on_damage_dealt + summon_attack engine; the new exemplar
     ex_blood_scent (needs summon) validates under exemplar_validator; app.js keeps its label; rule-0.9 budget printed.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen, paths  # noqa: E402
from btsgen import class_forge as cf  # noqa: E402
from btsgen.harness_v2 import exemplar_validator  # noqa: E402
from btsgen.relic_validator import RelicValidator  # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402

_PASS = 0
_FAIL = 0

MOD_CODE = paths.VOCABULARY.parents[1] / "BlankTheSpireCode"   # mod/contract/.. -> mod/BlankTheSpireCode
WEB_APP = paths.VOCABULARY.parents[2] / "web" / "static" / "app.js"
CARD_SCHEMA = paths.VOCABULARY.parent / "card.schema.json"
RELIC_VOCAB = paths.VOCABULARY.parent / "RELIC_VOCABULARY.md"
HEURISTICS = paths.VOCABULARY.parent / "DESIGN_HEURISTICS.md"


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _card(effects, ctype="power", target="self"):
    return {"id": "at_t", "name": "AT", "type": ctype, "rarity": "uncommon", "cost": 1, "target": target,
            "effects": effects}


def _trig(payload, **flags):
    t = {"op": "add_trigger", "trigger": "on_damage_dealt", "effects": payload}
    t.update(flags)
    return [t]


def test_version() -> None:
    print("Phase AT vocab stamp is 50 (Python + C#):")
    check(bts1.VOCAB_VERSION >= 50, f"bts1.VOCAB_VERSION >= 50 (got {bts1.VOCAB_VERSION})")
    fc = (MOD_CODE / "Engine" / "ForgedCards.cs").read_text(encoding="utf-8")
    m = re.search(r"public const int VocabVersion = (\d+);", fc)
    check(m is not None and int(m.group(1)) >= 50, f"ForgedCards.VocabVersion >= 50 (got {m and m.group(1)})")
    check(m is not None and bts1.VOCAB_VERSION <= int(m.group(1)), "bts1.VOCAB_VERSION <= ForgedCards.VocabVersion")
    check("Phase AT" in fc and "PetOwner" in fc, "ForgedCards.cs VocabVersion comment names Phase AT + the PetOwner idiom")


def _t_csharp_mirror() -> None:
    print("C# mirror: ForgedTriggerPower / ForgedRelic accept a pet dealer (the ReaperForm / HandDrill idiom):")
    tp = (MOD_CODE / "Powers" / "ForgedTriggerPower.cs").read_text(encoding="utf-8")
    body = tp.split("AfterDamageGiven", 1)[1].split("AfterBlockGained", 1)[0]
    check("bool byCard = dealer == Owner && cardSource != null;" in body, "card path unchanged: dealer == Owner && cardSource != null")
    check("dealer.PetOwner?.Creature == Owner" in body, "pet path: dealer.PetOwner?.Creature == Owner")
    check("dealer != Owner" in body, "pet path never double-counts the owner itself")
    check("if (!byCard && !byPet) return;" in body, "either path fires the same FireReactive")
    check("[AT] on_damage_dealt: pet" in body, "ForgedTriggerPower logs the [AT] tag on a pet-attributed fire")
    check('await FireReactive("on_damage_dealt", ctx);' in body, "still routed through FireReactive (re-entrancy + once_* gates)")

    fr = (MOD_CODE / "Powers" / "ForgedRelic.cs").read_text(encoding="utf-8")
    rbody = fr.split("public override async Task AfterDamageGiven", 1)[1].split("AfterBlockGained", 1)[0]
    check("dealer?.Player is Player cardPlayer && cardSource is not null" in rbody, "relic card path unchanged")
    check("dealer?.PetOwner is Player petOwner && petOwner == Owner" in rbody, "relic pet path: dealer.PetOwner == Owner (HandDrill)")
    card_branch = rbody.split("PetOwner", 1)[0]
    pet_branch = rbody.split("PetOwner", 1)[1]
    check("_firstAttackUsed = true;" in card_branch and "_firstAttackUsed" not in pet_branch,
          "first_attack (Akabeko) is consumed on the CARD path only")
    check("[AT] relic on_damage_dealt: pet" in rbody, "ForgedRelic logs the [AT] tag on a pet-attributed fire")
    check('await FireGuarded("on_damage_dealt", ctx, player);' in rbody, "still routed through FireGuarded")
    # ModifyDamageAdditive (first_attack / attack_base) stays card-gated — a pet hit is not a card attack.
    mda = fr.split("public override decimal ModifyDamageAdditive", 1)[1].split("cost_reduction", 1)[0]
    check("if (dealer?.Player == null || cardSource == null) return 0m;" in mda, "ModifyDamageAdditive stays gated to player card hits")

    patch = (MOD_CODE / "Engine" / "PetDamageAttributionPatch.cs").read_text(encoding="utf-8")
    check('[HarmonyPatch(typeof(PersonalHivePower), "AfterDamageReceived")]' in patch and patch.count("HarmonyPatch(") == 1,
          "PetDamageAttributionPatch stays scoped to PersonalHivePower (not widened for AT)")
    check("Phase AT" in patch, "the patch documents why AT does not route through it")
    fch = (MOD_CODE / "Engine" / "ForgedCharacters.cs").read_text(encoding="utf-8")
    check("Phase AT (v50), your pet's summon_attack hits" in fch, "ForgedCharacters hook doc names the pet path")
    # No new token anywhere: the trigger list is unchanged on both sides.
    check(fch.count('"on_damage_dealt"') >= 1 and '"on_pet_damage"' not in fch and '"on_summon_attack"' not in fch,
          "no new trigger token was minted (on_damage_dealt is the spelling)")


def _t_generation() -> None:
    print("generation: describe unchanged, summon-class pack-tactics cards validate under the summon context only:")
    fx = _trig([{"op": "draw", "amount": 1}], once_per_turn=True)
    d = cardgen.describe(fx, "self")
    check(d.startswith("Whenever you deal damage"), f"describe still opens 'Whenever you deal damage' (got {d!r})")
    fc = (MOD_CODE / "Engine" / "ForgedCards.cs").read_text(encoding="utf-8")
    check('"on_damage_dealt" => "Whenever you deal damage"' in fc, "C# TriggerFragment unchanged (byte-match contract)")
    plain = CardValidator()
    summon = CardValidator(extra_summons={"Bone Thrall"})
    check(plain.validate(_card(fx)).ok and summon.validate(_card(fx)).ok, "on_damage_dealt -> draw is legal for any class")
    buff = _trig([{"op": "buff_summon", "amount": 1, "status": "strength"}], once_per_turn=True)
    check(summon.validate(_card(buff)).ok, f"on_damage_dealt -> buff_summon validates under a summon context: {summon.validate(_card(buff)).errors}")
    check(not plain.validate(_card(buff)).ok, "... and is rejected without one (buff_summon is class-only, unchanged)")
    sic = _card([{"op": "summon_attack", "amount": 5, "hits": 2}], ctype="attack", target="enemy")
    check(summon.validate(sic).ok, f"the feeder (summon_attack x2) validates: {summon.validate(sic).errors}")
    # Relic twin: an on_damage_dealt hook validates as before (no new shape).
    relic = {"id": "at_r", "name": "Hunter's Bell", "tier": "starter", "icon_emoji": "\U0001F514",
             "hooks": [{"trigger": "on_damage_dealt", "effects": [{"op": "block", "amount": 1}]}]}
    errs = cf._validate_relic(relic)
    check(not errs and RelicValidator().validate(relic).ok, f"relic on_damage_dealt hook validates: {errs}")
    check(cf._HOOK_FREQ["on_damage_dealt"] == 6.0, "the keystone payout rate for on_damage_dealt is unchanged (6/fight)")


def _t_contract() -> None:
    print("contract / heuristics / exemplar / web carry the wording:")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    check("`on_damage_dealt` (you deal damage with a card OR through your summon" in vocab, "VOCABULARY.md: on_damage_dealt counts the summon")
    check("`on_damage_dealt` (you deal card damage)" not in vocab, "VOCABULARY.md: the card-only wording is gone")
    schema_text = CARD_SCHEMA.read_text(encoding="utf-8")
    json.loads(schema_text)  # still valid JSON after the wording edit
    check("'on_damage_dealt' = you deal damage with a card OR through your summon" in schema_text, "card.schema.json: trigger description counts the summon")
    rv = RELIC_VOCAB.read_text(encoding="utf-8")
    check("| `on_damage_dealt` | each time you deal damage with a CARD attack or THROUGH YOUR SUMMON" in rv, "RELIC_VOCABULARY.md row counts the summon")
    heur = HEURISTICS.read_text(encoding="utf-8")
    note = heur.split("<!-- archetype-note: summon_swarm -->", 1)[1].split("<!-- archetype-note:", 1)[0]
    check("`on_damage_dealt` + summon_attack" in note, "DESIGN_HEURISTICS summon_swarm note names the pack-tactics engine")

    data = pathlib.Path(paths.__file__).parent / "data"
    pool = json.loads((data / "exemplar_pool.json").read_text(encoding="utf-8"))
    by_id = {e["card"]["id"]: e for e in pool["exemplars"]}
    ex = by_id.get("ex_blood_scent")
    check(ex is not None and ex["needs"] == "summon" and "summon_swarm" in ex["archetypes"], "exemplar ex_blood_scent present (needs summon, summon_swarm)")
    if ex is not None:
        rr = exemplar_validator().validate(dict(ex["card"]))
        check(rr.ok, f"exemplar ex_blood_scent validates: {rr.errors}")
        check(ex["card"]["effects"][0]["trigger"] == "on_damage_dealt"
              and ex["card"]["effects"][0]["effects"][0]["op"] == "buff_summon", "the exemplar IS the on_damage_dealt -> buff_summon engine")
    check(len(pool["exemplars"]) >= 113, f"pool grew to >= 113 (got {len(pool['exemplars'])})")
    app = WEB_APP.read_text(encoding="utf-8")
    check('on_damage_dealt: "On damage dealt"' in app, "app.js keeps the on_damage_dealt label (no new token)")
    bp = cf._BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()
    print(f"  (rule 0.9) blueprint prompt: {len(bp):,} chars (the ONE ceiling lives in tests/test_harness_v2.py)")
    # AT's rule-0.9 contribution is a WORDING swap in VOCABULARY / card.schema.json / RELIC_VOCABULARY (asserted
    # above), not prompt growth, so there is nothing size-shaped to assert here. The private "+5% of AR" ceiling
    # this used to carry was removed at Phase AY: one prompt, one ceiling, in test_harness_v2.py.


def main() -> int:
    test_version()
    _t_csharp_mirror()
    _t_generation()
    _t_contract()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
