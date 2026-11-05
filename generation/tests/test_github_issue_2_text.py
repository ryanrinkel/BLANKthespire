"""GitHub issue #2 (part 2b) regression: card text shows status AMOUNTS ("Apply 3 Poison.", "Gain 2 Thorns.").

ForgedCards.Describe used to print the bare status word ("Apply Poison.") although DataCard declares the PowerVar.
Both describes (C# ForgedCards.Describe and its Python mirror cardgen.describe) now emit the card's PowerVar as the
amount placeholder ("Apply {PoisonPower} Poison."), which the game resolves from the card's DynamicVarSet (an unnamed
PowerVar<T> is keyed typeof(T).Name). The status -> var table lives ONCE in C# (ForgedCards.StatusPowerVars, which
DataCard declares from) and once in Python (cardgen.STATUS_POWER_VAR); this test keeps the two in lockstep.

Run:  uv run python -m pytest tests/test_github_issue_2_text.py -q       (from generation/)
"""
from __future__ import annotations

import json
import re

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import cardgen, paths  # noqa: E402

MOD_CODE = paths.VOCABULARY.parents[1] / "BlankTheSpireCode"
CARD_SCHEMA = paths.VOCABULARY.parent / "card.schema.json"
# Statuses that declare NO PowerVar (their text uses a plain var in a special sentence).
NO_POWER_VAR = {"strength_down", "lose_strength", "lose_dexterity", "lose_focus"}
# Statuses with their own sentence (BM self statuses, strength_down): Describe never prints "Gain/Apply {amount} X.".
SPECIAL = set(cardgen._BM_SENTENCES) | {"strength_down"}


def _cs(*parts: str) -> str:
    return MOD_CODE.joinpath(*parts).read_text(encoding="utf-8-sig").replace("\r\n", "\n")


def _cs_table() -> dict[str, str]:
    """ForgedCards.StatusPowerVars parsed: status -> the var key (explicit name, else the power type name)."""
    fc = _cs("Engine", "ForgedCards.cs")
    body = fc[fc.index("StatusPowerVars ="):]
    body = body[:body.index("};")]
    rows = re.findall(r'\["(\w+)"\]\s*=\s*\(typeof\((\w+)\),\s*(?:null|"(\w+)")\)', body)
    return {st: (name or power) for st, power, name in rows}


def _schema_statuses() -> set[str]:
    schema = json.loads(CARD_SCHEMA.read_text(encoding="utf-8"))
    txt = json.dumps(schema)
    m = re.search(r'"status": \{"enum": \[(.*?)\]', txt)
    return set(re.findall(r'"(\w+)"', m.group(1)))


def _st(status, amount=3, **kw):
    e = {"op": "apply_status", "status": status, "amount": amount}
    e.update(kw)
    return e


def test_python_map_matches_the_csharp_table() -> None:
    cs = _cs_table()
    assert len(cs) >= 30, f"parsed only {len(cs)} StatusPowerVars rows"
    assert cs == cardgen.STATUS_POWER_VAR, (
        f"C# only: {sorted(set(cs.items()) - set(cardgen.STATUS_POWER_VAR.items()))}; "
        f"Python only: {sorted(set(cardgen.STATUS_POWER_VAR.items()) - set(cs.items()))}")


def test_every_vocabulary_status_is_covered() -> None:
    statuses = _schema_statuses()
    assert statuses, "could not read the status enum from card.schema.json"
    mapped = set(cardgen.STATUS_POWER_VAR)
    assert mapped | NO_POWER_VAR == statuses, f"unaccounted: {sorted(statuses - mapped - NO_POWER_VAR)}; " \
                                              f"stale: {sorted((mapped | NO_POWER_VAR) - statuses)}"
    assert not mapped & NO_POWER_VAR
    for st in NO_POWER_VAR:
        assert cardgen.status_power_var_key(st) is None


def test_datacard_declares_from_the_shared_table() -> None:
    dc = _cs("Engine", "DataCard.cs")
    body = dc[dc.index('case "apply_status":'):]
    body = body[:body.index('default:\n                    throw new NotSupportedException($"DataCard: unsupported op')]
    # no per-status Power<T> case is left to drift from the table
    assert not re.findall(r'case "(\w+)":\s+Power<', body), re.findall(r'case "(\w+)":\s+Power<', body)
    assert "ForgedCards.StatusPowerVars.TryGetValue(e.Status, out var pv)" in body
    assert "DeclarePower(pv.Power, vname ?? pv.Var, e.Amount, up);" in body
    assert 'case "doom":           if (e.IsScaled) break; goto default;' in body
    for st, var in (("strength_down", "StrengthLoss"), ("lose_strength", "SelfStrengthLoss"),
                    ("lose_dexterity", "SelfDexterityLoss"), ("lose_focus", "SelfFocusLoss")):
        assert re.search(r'case "%s":\s+WithVar\("%s", e\.Amount, up\); break;' % (st, var), body), st


def test_describe_prints_the_power_var() -> None:
    assert cardgen.describe([_st("poison")], "enemy") == "Apply {PoisonPower} Poison."
    assert cardgen.describe([_st("thorns", 2)], "self") == "Gain {ThornsPower} Thorns."
    assert cardgen.describe([_st("temp_thorns", 2)], "self") == "Gain {ForgedTempThornsPower} Thorns."
    assert cardgen.describe([_st("metallicize", 2)], "self") == "Gain {PlatingPower} Metallicize."
    assert cardgen.describe([_st("weak", 1)], "all_enemies") == "Apply {WeakPower} Weak to ALL enemies."
    assert cardgen.describe([_st("vulnerable", 1)], "random_enemy") == "Apply {VulnerablePower} Vulnerable to a random enemy."
    for st, key in cardgen.STATUS_POWER_VAR.items():
        if st in SPECIAL:
            continue
        d = cardgen.describe([_st(st)], "enemy")
        assert "{" + key + "} " in d, (st, d)


def test_gated_second_copy_uses_the_suffixed_var() -> None:
    effs = [_st("weak", 1), _st("weak", 2, when={"kind": "target_attacking"})]
    d = cardgen.describe(effs, "enemy")
    assert d.split("\n")[0] == "Apply {WeakPower} Weak."
    assert d.split("\n")[1].startswith("Apply {Weak2} Weak"), d
    # a two-word status keys its suffixed var with '-' (LocString.AddObj replaces ' ' with '-')
    assert cardgen._status_var_ref([_st("double_damage", 1), _st("double_damage", 1)], 1) == "{Double-Damage2}"


def test_special_sentences_unchanged() -> None:
    assert cardgen.describe([_st("strength_down", 2)], "enemy") == "The enemy loses {StrengthLoss} Strength."
    assert cardgen.describe([{"op": "damage", "amount": 6}, _st("doom", 0, scale="damage_dealt_unblocked")], "enemy") \
        == "Deal {Damage} damage.\nApply Doom equal to the unblocked damage dealt."
    for st, line in cardgen._BM_SENTENCES.items():
        assert cardgen.describe([_st(st, 1)], "self") == line, st
    assert cardgen._status_var_ref([_st("doom", 0, scale="damage_dealt_unblocked")], 0) == ""


def test_csharp_describe_and_zhs_carry_the_amount() -> None:
    fc = _cs("Engine", "ForgedCards.cs")
    assert 'Fx("card.status.gain", "Gain {amount} {status}.", ("amount", amount), ("unit", StatusUnit(e.Status))' in fc
    assert 'Fx("card.status.apply", "Apply {amount} {status}{to}.", ("amount", amount), ("unit", StatusUnit(e.Status))' in fc
    assert "else if (StatusVarRef(effects, ei) is { Length: > 0 } amount)" in fc
    assert 'return "{" + key.Replace(\' \', \'-\') + "}";' in fc
    # the special sentences stay as they were
    assert 'Tx("card.strength_down", "The enemy loses {StrengthLoss} Strength.")' in fc
    assert 'parts.Add(Tx("card.doom.unblocked", "Apply Doom equal to the unblocked damage dealt."));' in fc
    zhs = _cs("Engine", "ForgedText.zhs.cs")
    assert '["card.status.gain"] = "获得{amount}{unit}{status}。",' in zhs
    assert '["card.status.apply"] = "给予{who}{amount}{unit}{status}。",' in zhs


def test_jev_qa_text_fills_the_status_amount() -> None:
    """class_forge._card_text (the Jev QA prompt text) resolves {PoisonPower} / {Weak2} to the literal amount."""
    from btsgen.class_forge import _card_text

    card = {"target": "enemy", "effects": [
        {"op": "damage", "amount": 6},
        {"op": "apply_status", "status": "poison", "amount": 3},
        {"op": "apply_status", "status": "poison", "amount": 2, "when": {"kind": "target_below_half_hp"}},
    ]}
    text = _card_text(card)
    assert "{" not in text, text
    assert "Deal 6 damage." in text and "Apply 3 Poison." in text and "Apply 2 Poison" in text, text
