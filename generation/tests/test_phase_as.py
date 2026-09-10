"""Phase AS — RELIC VOCABULARY (VOCAB_GAP_REMEDIATION_PLAN Wave 3, vocab v48) — offline, no API key.

Run:  uv run python -m tests.test_phase_as       (from generation/)
Exits nonzero on any failure. Covers the v48 additions on the generation side, in lockstep with the C#:
  1. relic hooks gain `card_type` (on_card_played only: attack/skill/power) and an `every_n` per-combat counter (2..9,
     not on combat_end); modifiers gain `attack_base` (1..3 generator-side, 1..5 import-side) and the SIGNED `max_hp`
     (-30..30); the relic drawback op `discard` (1..2, random only); a debuff on a self-target hook is legal (it lands on
     the owner) except poison. class_forge._validate_relic and relic.schema.json both accept every legal shape and reject
     every illegal one with the C# wording family;
  2. the keystone balance gate prices the new shapes: a flat energy stat is still rejected ALONE, but a drawback (max_hp
     -8 or lower, a per-turn lose_hp 2 / discard 1 / self weak 1 hook) is credited against it (capped), so "Coffee
     Dripper with a cost" is reachable; a typed every_n counter pays 1/N as often; attack_base 1-2 fit, 3 does not;
  3. the C# mirror: RelicSpec carries CardType/EveryN, ForgedCharacters' sets + bounds carry the tokens, RelicRunner
     filters/counts, ForgedRelic applies max_hp in AfterObtained (the DistinguishedCape recipe), passes the played card's
     type, shows the counter, adds attack_base in ModifyDamageAdditive; EffectRunner runs discard + the self-debuff;
     the VocabVersion stamp is 48;
  4. the contract carries the tokens: RELIC_VOCABULARY.md rows/sections, DESIGN_HEURISTICS relic forms ("Counter relic",
     "Boon with a price") reach relic_forms() and the relic prompt, app.js labels, the smoke + fake relics validate.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, paths, smoke_relic  # noqa: E402
from btsgen import class_forge as cf  # noqa: E402
from btsgen.contract import relic_forms  # noqa: E402
from btsgen.relic_validator import RelicValidator  # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402

_PASS = 0
_FAIL = 0

MOD_CODE = paths.VOCABULARY.parents[1] / "BlankTheSpireCode"   # mod/contract/.. -> mod/BlankTheSpireCode
WEB_APP = paths.VOCABULARY.parents[2] / "web" / "static" / "app.js"
RELIC_SCHEMA = paths.VOCABULARY.parent / "relic.schema.json"
RELIC_VOCAB = paths.VOCABULARY.parent / "RELIC_VOCABULARY.md"

_V = CardValidator()
_RV = RelicValidator()


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _relic(hooks=None, modifiers=None) -> dict:
    r = {"id": "as_r", "name": "AS Relic", "tier": "starter", "icon_emoji": "☕"}
    if hooks is not None:
        r["hooks"] = hooks
    if modifiers is not None:
        r["modifiers"] = modifiers
    return r


def _accepts(relic, label):
    errs = cf._validate_relic(relic)
    check(not errs, f"{label}: class_forge accepts: {errs}")
    r = _RV.validate(relic)
    check(r.ok, f"{label}: relic.schema.json accepts: {r.errors}")


def _rejects(relic, needle, label, schema_too=True):
    errs = cf._validate_relic(relic)
    check(any(needle.lower() in e.lower() for e in errs), f"{label}: class_forge rejects mentioning '{needle}': {errs}")
    if schema_too:
        check(not _RV.validate(relic).ok, f"{label}: relic.schema.json rejects it too")


def _gate(relic, made=None):
    return cf._relic_balance_errors(relic, made or [], _V)


def test_version() -> None:
    print("Phase AS vocab stamp is at least v48 (Python + C#):")
    check(bts1.VOCAB_VERSION >= 48, f"bts1.VOCAB_VERSION must be >= 48 (Phase AS), got {bts1.VOCAB_VERSION}")
    fc = (MOD_CODE / "Engine" / "ForgedCards.cs").read_text(encoding="utf-8")
    m = re.search(r"public const int VocabVersion = (\d+);", fc)
    check(m is not None and int(m.group(1)) >= 48, f"ForgedCards.VocabVersion >= 48: {m and m.group(1)}")
    check(m is not None and int(m.group(1)) >= bts1.VOCAB_VERSION, "bts1.VOCAB_VERSION <= ForgedCards.VocabVersion")


def _t_accepts() -> None:
    print("relic gate: every legal v48 shape validates (class_forge + schema):")
    _accepts(_relic(hooks=[{"trigger": "on_card_played", "card_type": "attack", "every_n": 3,
                            "effects": [{"op": "block", "amount": 3}]}]), "a typed counter (every 3rd Attack -> Block 3)")
    for ct in ("attack", "skill", "power"):
        _accepts(_relic(hooks=[{"trigger": "on_card_played", "card_type": ct, "effects": [{"op": "draw", "amount": 1}]}]),
                 f"a typed on_card_played ({ct})")
    _accepts(_relic(hooks=[{"trigger": "turn_start", "every_n": 2, "effects": [{"op": "draw", "amount": 1}]}]), "every other turn")
    _accepts(_relic(hooks=[{"trigger": "attacked", "every_n": 9, "target": "attacker", "effects": [{"op": "damage", "amount": 5}]}]),
             "every_n 9 on a reactive trigger")
    _accepts(_relic(hooks=[{"trigger": "turn_start", "effects": [{"op": "discard", "amount": 1}]}]), "the discard drawback")
    _accepts(_relic(hooks=[{"trigger": "turn_start", "effects": [{"op": "discard", "amount": 2, "cards": "random"}]}]),
             "discard 2 with an explicit random")
    for st in ("weak", "frail", "vulnerable"):
        _accepts(_relic(hooks=[{"trigger": "turn_start", "effects": [{"op": "apply_status", "status": st, "amount": 1}]}]),
                 f"a self {st} drawback")
    _accepts(_relic(modifiers=[{"stat": "attack_base", "amount": 1}]), "attack_base 1")
    _accepts(_relic(modifiers=[{"stat": "attack_base", "amount": 3}]), "attack_base 3 (the generator ceiling)")
    _accepts(_relic(modifiers=[{"stat": "max_hp", "amount": 10}]), "max_hp +10")
    _accepts(_relic(modifiers=[{"stat": "max_hp", "amount": -30}]), "max_hp -30 (the floor)")
    _accepts(_relic(modifiers=[{"stat": "max_energy", "amount": 1}, {"stat": "max_hp", "amount": -8}]),
             "the boon with a price (energy + max_hp -8)")
    _accepts(smoke_relic.SMOKE_RELIC, "the smoke relic (carries every v48 shape)")
    _accepts(cf._fake_relic({"name": "Ash"}), "the offline fake relic (carries every v48 shape)")
    check(any(h.get("every_n") for h in smoke_relic.SMOKE_RELIC["hooks"]) and
          any(m["stat"] == "max_hp" for m in smoke_relic.SMOKE_RELIC["modifiers"]), "the smoke relic exercises every_n + max_hp")


def _t_rejects() -> None:
    print("relic gate: every illegal v48 shape rejects with the C# wording family:")
    _rejects(_relic(hooks=[{"trigger": "turn_start", "card_type": "attack", "effects": [{"op": "block", "amount": 1}]}]),
             "only valid on the 'on_card_played'", "card_type off on_card_played")
    _rejects(_relic(hooks=[{"trigger": "on_card_played", "card_type": "curse", "effects": [{"op": "block", "amount": 1}]}]),
             "must be attack/skill/power", "an unknown card_type")
    _rejects(_relic(hooks=[{"trigger": "turn_start", "every_n": 1, "effects": [{"op": "block", "amount": 1}]}]),
             "must be 2..9", "every_n 1")
    _rejects(_relic(hooks=[{"trigger": "turn_start", "every_n": 10, "effects": [{"op": "block", "amount": 1}]}]),
             "must be 2..9", "every_n 10")
    _rejects(_relic(hooks=[{"trigger": "combat_end", "every_n": 2, "effects": [{"op": "heal", "amount": 3}]}]),
             "meaningless on 'combat_end'", "every_n on combat_end")
    _rejects(_relic(hooks=[{"trigger": "turn_start", "effects": [{"op": "apply_status", "status": "poison", "amount": 1}]}]),
             "never poisons its owner", "self poison", schema_too=False)
    _rejects(_relic(hooks=[{"trigger": "turn_start", "effects": [{"op": "discard", "amount": 3}]}]), "must be 1..2", "discard 3")
    _rejects(_relic(hooks=[{"trigger": "turn_start", "effects": [{"op": "discard", "amount": 1, "cards": "choose"}]}]),
             "must be random", "a chosen relic discard")
    _rejects(_relic(hooks=[{"trigger": "combat_end", "effects": [{"op": "discard", "amount": 1}]}]),
             "only use the 'heal'", "discard on combat_end")
    _rejects(_relic(modifiers=[{"stat": "attack_base", "amount": 4}]), "must be 1..3", "attack_base 4", schema_too=False)
    _rejects(_relic(modifiers=[{"stat": "attack_base", "amount": -1}]), "must be 1..3", "a negative attack_base")
    _rejects(_relic(modifiers=[{"stat": "max_hp", "amount": -31}]), "must be -30..30", "max_hp -31")
    _rejects(_relic(modifiers=[{"stat": "max_hp", "amount": 0}]), "non-zero", "max_hp 0")
    _rejects(_relic(modifiers=[{"stat": "max_energy", "amount": -1}]), "only max_hp may be negative", "a negative max_energy")
    _rejects(_relic(modifiers=[{"stat": "gold_income", "amount": 1}]), "stat must be one of", "an unknown stat")


def _t_balance() -> None:
    print("keystone balance gate: drawbacks are credited (capped), counters pay 1/N, attack_base is Vajra-priced:")
    energy = {"stat": "max_energy", "amount": 1}
    cost = {"stat": "cost_reduction", "amount": 1}
    errs = _gate(_relic(modifiers=[energy]))
    check(bool(errs) and "boss-relic" in errs[0] and "max_hp -8" in errs[0], f"max_energy ALONE still rejected, and the fix is named: {errs}")
    check(not _gate(_relic(modifiers=[energy, {"stat": "max_hp", "amount": -8}])), "max_energy 1 + max_hp -8 passes (Coffee Dripper with a cost)")
    check(bool(_gate(_relic(modifiers=[energy, {"stat": "max_hp", "amount": -7}]))), "max_energy 1 + max_hp -7 is not enough")
    check(not _gate(_relic(modifiers=[energy], hooks=[{"trigger": "turn_start", "effects": [{"op": "discard", "amount": 1}]}])),
          "max_energy 1 + discard 1 each turn passes")
    check(not _gate(_relic(modifiers=[energy], hooks=[{"trigger": "turn_start", "effects": [{"op": "lose_hp", "amount": 2}]}])),
          "max_energy 1 + lose 2 HP each turn passes")
    check(bool(_gate(_relic(modifiers=[energy], hooks=[{"trigger": "turn_start", "effects": [{"op": "lose_hp", "amount": 1}]}]))),
          "max_energy 1 + lose 1 HP each turn is not enough")
    check(not _gate(_relic(modifiers=[energy], hooks=[{"trigger": "turn_start",
                                                       "effects": [{"op": "apply_status", "status": "weak", "amount": 1}]}])),
          "max_energy 1 + self Weak each turn passes")
    check(not _gate(_relic(modifiers=[cost, {"stat": "max_hp", "amount": -15}],
                           hooks=[{"trigger": "turn_start", "effects": [{"op": "discard", "amount": 1}]}])),
          "cost_reduction 1 + max_hp -15 + discard 1 each turn passes (the heavy price)")
    check(bool(_gate(_relic(modifiers=[cost, {"stat": "max_hp", "amount": -10}]))), "cost_reduction 1 + max_hp -10 is not enough")
    errs = _gate(_relic(modifiers=[energy, cost, {"stat": "max_hp", "amount": -30}],
                        hooks=[{"trigger": "turn_start", "effects": [{"op": "discard", "amount": 2}]}]))
    check(bool(errs) and "drawbacks credited" in errs[0], f"the drawback credit is CAPPED (energy + cost never fit): {errs}")
    check(not _gate(_relic(modifiers=[{"stat": "attack_base", "amount": 1}])), "attack_base 1 passes (Vajra)")
    check(not _gate(_relic(modifiers=[{"stat": "attack_base", "amount": 2}])), "attack_base 2 passes (the edge)")
    check(bool(_gate(_relic(modifiers=[{"stat": "attack_base", "amount": 3}]))), "attack_base 3 is rejected")
    check(not _gate(_relic(modifiers=[{"stat": "max_hp", "amount": 10}])), "max_hp +10 passes (Strawberry)")
    check(not _gate(_relic(hooks=[{"trigger": "on_card_played", "card_type": "attack", "every_n": 3,
                                   "effects": [{"op": "block", "amount": 4}]}])), "every 3rd Attack -> Block 4 passes")
    check(bool(_gate(_relic(hooks=[{"trigger": "on_card_played", "effects": [{"op": "block", "amount": 4}]}]))),
          "the same payout on EVERY card is rejected")
    check(not _gate(_relic(hooks=[{"trigger": "turn_start", "every_n": 2, "effects": [{"op": "draw", "amount": 1}]}])),
          "draw 1 every other turn passes")
    check(bool(_gate(_relic(hooks=[{"trigger": "turn_start", "effects": [{"op": "draw", "amount": 1}]}]))),
          "draw 1 every turn is rejected")
    # the helpers themselves
    h = {"trigger": "on_card_played", "card_type": "power", "every_n": 2}
    check(abs(cf._relic_hook_freq(h) - 9.0 * 0.1 / 2) < 1e-9, "hook freq: on_card_played x power share / every_n")
    check(cf._relic_hook_freq({"trigger": "turn_start", "once_per_combat": True, "every_n": 3}) == 1.0, "once_per_combat still collapses to 1")
    check(cf._relic_effect_value({"op": "discard", "amount": 1}, "self", _V) < 0, "discard is priced negative")
    check(cf._relic_effect_value({"op": "apply_status", "status": "weak", "amount": 1}, "self", _V) < 0, "self weak is priced negative")
    check(cf._relic_effect_value({"op": "apply_status", "status": "weak", "amount": 1}, "enemy", _V) > 0, "enemy weak is still a payout")


def _t_csharp_mirror() -> None:
    print("C# mirror: RelicSpec / ForgedCharacters / RelicRunner / ForgedRelic / EffectRunner carry the v48 shapes:")
    rs = (MOD_CODE / "Engine" / "RelicSpec.cs").read_text(encoding="utf-8")
    check("string? CardType = null" in rs and "int EveryN = 0" in rs, "RelicHook has CardType + EveryN")
    fch = (MOD_CODE / "Engine" / "ForgedCharacters.cs").read_text(encoding="utf-8")
    stats = re.search(r"RelicModifierStats =\s*\[([^\]]*)\]", fch)
    check(stats is not None and '"attack_base"' in stats.group(1) and '"max_hp"' in stats.group(1), "RelicModifierStats has attack_base + max_hp")
    ops = re.search(r"RelicEffectOps =\s*\[([^\]]*)\]", fch)
    check(ops is not None and '"discard"' in ops.group(1), "RelicEffectOps has discard")
    check('RelicCardTypes = ["attack", "skill", "power"]' in fch, "RelicCardTypes = attack/skill/power")
    check("MinEveryN = 2, MaxEveryN = 9" in fch, "every_n bounds 2..9")
    check("only valid on the 'on_card_played' trigger" in fch, "card_type is on_card_played-only in the importer")
    check("System.Math.Abs(mamt) > 30" in fch and 'stat == "attack_base" && mamt > 5' in fch, "importer bounds: |max_hp| <= 30, attack_base <= 5")
    check('hookTarget == "self" && status == "poison"' in fch, "self poison rejected; other self debuffs pass the importer")
    check('op == "discard"' in fch and "must be random" in fch, "importer: relic discard 1..2 random")
    rr = (MOD_CODE / "Engine" / "RelicRunner.cs").read_text(encoding="utf-8")
    check("string? cardType = null, Dictionary<int, int>? counters = null" in rr, "RelicRunner.Fire takes cardType + counters")
    check("h.CardType != null && h.CardType != cardType" in rr and "n % h.EveryN != 0" in rr, "RelicRunner filters by type and counts every_n")
    check("[AS] every_n" in rr, "RelicRunner logs [AS] every_n")
    fr = (MOD_CODE / "Powers" / "ForgedRelic.cs").read_text(encoding="utf-8")
    check("public override async Task AfterObtained()" in fr and "CreatureCmd.LoseMaxHp(new ThrowingPlayerChoiceContext()" in fr
          and "CreatureCmd.GainMaxHp(Owner.Creature, delta)" in fr, "ForgedRelic.AfterObtained applies max_hp (DistinguishedCape recipe)")
    check('CardType.Attack => "attack"' in fr and 'FireGuarded("on_card_played", ctx, player, cardType: cardType)' in fr,
          "AfterCardPlayed passes the played card's type")
    check("public override bool ShowCounter => HasCounter" in fr and "public override int DisplayAmount" in fr, "the counter shows on the icon")
    check('m.Stat == "attack_base"' in fr and "if (!_firstAttackUsed) bonus +=" in fr, "ModifyDamageAdditive adds attack_base on every card hit")
    check("_counters.Clear()" in fr, "counters reset at combat start")
    er = (MOD_CODE / "Engine" / "EffectRunner.cs").read_text(encoding="utf-8")
    check('case "discard":' in er.split("RunRelicEffects")[1] and "DiscardRandom(amt, player, ctx)" in er, "RunRelicEffects runs discard (random)")
    check('if (hookTarget == "self")' in er and "[AS] self-debuff" in er, "ApplyRelicStatus lands a self-hook debuff on the owner")


def _t_contract() -> None:
    print("contract / heuristics / prompt / web carry the tokens:")
    schema = json.loads(RELIC_SCHEMA.read_text(encoding="utf-8"))
    hook = schema["$defs"]["hook"]["properties"]
    check(hook["card_type"]["enum"] == ["attack", "skill", "power"], "schema: hook card_type enum")
    check(hook["every_n"]["minimum"] == 2 and hook["every_n"]["maximum"] == 9, "schema: every_n 2..9")
    check("discard" in schema["$defs"]["effect"]["properties"]["op"]["enum"], "schema: discard op")
    mods = schema["$defs"]["modifier"]["properties"]["stat"]["enum"]
    check("attack_base" in mods and "max_hp" in mods, "schema: attack_base + max_hp stats")
    vocab = RELIC_VOCAB.read_text(encoding="utf-8")
    for tok in ("| `discard`", "### `card_type`", "### `every_n`", "| `attack_base`", "| `max_hp`", "land on **YOU**",
                "−8 or lower"):
        check(tok in vocab, f"RELIC_VOCABULARY.md carries {tok!r}")
    forms = relic_forms()
    check("**Counter relic**" in forms and "**Boon with a price**" in forms, "DESIGN_HEURISTICS relic forms: Counter relic + Boon with a price")
    check("`attack_base`" in forms and "`max_energy` / `cost_reduction` are NOT in this form" in forms, "the passive-modifier form moved the energy stats out")
    prompt = cf._RelicContract().system_prompt()
    for tok in ("Boon with a price", "`every_n`", "`attack_base`", "`max_hp`", "REJECTED on its own"):
        check(tok in prompt, f"the relic prompt carries {tok!r}")
    print(f"  (rule 0.9) relic prompt: {len(prompt):,} chars")
    bp = cf._BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()
    print(f"  (rule 0.9) blueprint prompt: {len(bp):,} chars (unchanged by AS — the relic vocab is not embedded there)")
    app = WEB_APP.read_text(encoding="utf-8")
    check('attack_base: "damage on every attack"' in app and 'max_hp: "max HP"' in app, "app.js labels both modifiers")
    check("h.every_n" in app and "h.card_type" in app and 'on_hp_lost: "On HP lost"' in app, "app.js renders every_n / card_type (+ the missing on_hp_lost label)")


def main() -> int:
    test_version()
    _t_accepts()
    _t_rejects()
    _t_balance()
    _t_csharp_mirror()
    _t_contract()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


# pytest entry point (re-runs main's checks in isolation for a clear failure name)
def test_phase_as_all() -> None:
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
