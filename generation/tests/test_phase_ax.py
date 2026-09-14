"""Phase AX — STRUCTURAL CAPS + THE GAP #44/#45 OPS (VOCAB_GAP_REMEDIATION_PLAN Wave 4, vocab v53) — offline, no API key.

Run:  uv run python -m tests.test_phase_ax       (from generation/)
Exits nonzero on any failure. Covers the v53 change in lockstep with the C#:
  1. the vocab stamp is >= 53 on both sides (bts1.VOCAB_VERSION <= ForgedCards.VocabVersion);
  2. COST 0..4 — the schema band, the upgrade band, and the RARE-only gate on the heavyweight slot;
  3. UPGRADE MAY CHANGE ONE KEYWORD — append exactly one of exhaust/retain/innate/ethereal, or drop a trailing
     exhaust; every other length/keyword change still rejects, and DataCard turns the diff into BaseLib's
     UpgradeType.Add / UpgradeType.Remove;
  4. TWO OF A KIND — a second apply_status of the same status is legal when it is `when`-gated (it takes the
     suffixed "Weak2" var), rejected ungated, and a third is always rejected;
  5. `tags` maxItems 2 -> 3;
  6. `spend_forge` (amount 1..10, card-only, never on a BASIC, never alone, one per card) + the ordering rule
     that keeps a `when:forged_ge` payoff ahead of the spend that empties the counter;
  7. `spread_debuffs` (flag-op, single-enemy cards only, card-only, never on a BASIC, one per card);
  8. describe is a byte-match contract: cardgen.describe() == the C# sentences for both new ops;
  9. the contract surfaces — VOCABULARY rows, the schema enum + clauses, the exemplars, featured/harness menus,
     census counters and app.js — plus the rule-0.9 prompt budget.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen, census, featured, harness_v2, paths  # noqa: E402
from btsgen import class_forge as cf  # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402

_PASS = 0
_FAIL = 0

MOD_CODE = paths.VOCABULARY.parents[1] / "BlankTheSpireCode"   # mod/contract/.. -> mod/BlankTheSpireCode
CARD_SCHEMA = paths.VOCABULARY.parent / "card.schema.json"
APP_JS = paths.VOCABULARY.parents[2] / "web" / "static" / "app.js"
EXEMPLAR_POOL = pathlib.Path(cf.__file__).parent / "data" / "exemplar_pool.json"


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


# --------------------------------------------------------------------------- helpers
def _card(effects, ctype="skill", rarity="common", target="self", cost=1, upgrade=None, **extra):
    c = {"id": "ax_t", "name": "AX", "type": ctype, "rarity": rarity, "cost": cost, "target": target,
         "effects": effects}
    if upgrade is not None:
        c["upgrade"] = upgrade if isinstance(upgrade, dict) else {"effects": upgrade}
    c.update(extra)
    return c


def _errs(card, v=None) -> list[str]:
    return (v or CardValidator()).validate(card).errors


def _ok(card, v=None) -> bool:
    return not _errs(card, v)


DMG = {"op": "damage", "amount": 6}
BLOCK = {"op": "block", "amount": 5}


# --------------------------------------------------------------------------- 1. stamps
def test_version() -> None:
    print("Phase AX vocab stamp is at least 53 (Python + C#):")
    check(bts1.VOCAB_VERSION >= 53, f"bts1.VOCAB_VERSION >= 53 (Phase AY moved it to 54), got {bts1.VOCAB_VERSION}")
    fc = (MOD_CODE / "Engine" / "ForgedCards.cs").read_text(encoding="utf-8")
    m = re.search(r"public const int VocabVersion = (\d+);", fc)
    check(m is not None and int(m.group(1)) >= 53,
          f"ForgedCards.VocabVersion >= 53 (Phase AY moved it to 54), got {m and m.group(1)}")
    check(m is not None and bts1.VOCAB_VERSION <= int(m.group(1)), "bts1.VOCAB_VERSION <= ForgedCards.VocabVersion")
    check("Phase AX" in fc and "spend_forge" in fc and "spread_debuffs" in fc,
          "ForgedCards.cs VocabVersion comment names Phase AX + both new ops")
    bts1_src = pathlib.Path(bts1.__file__).read_text(encoding="utf-8")
    check("53: Phase AX" in bts1_src, "bts1.py's VOCAB_VERSION comment records the v53 (Phase AX) entry")


# --------------------------------------------------------------------------- 2. cost 0..4
def _t_cost() -> None:
    print("cost 0..4, with the heavyweight slot RARE-only:")
    schema = json.loads(CARD_SCHEMA.read_text(encoding="utf-8"))
    band = schema["properties"]["cost"]["oneOf"][0]
    check(band["maximum"] == 4 and band["minimum"] == 0, f"schema cost band is 0..4 (got {band})")
    up_cost = schema["properties"]["upgrade"]["properties"]["cost"]
    check(up_cost["maximum"] == 4, f"schema upgrade cost band tops out at 4 (got {up_cost['maximum']})")

    check(_ok(_card([DMG], ctype="attack", rarity="rare", target="enemy", cost=4)),
          "cost 4 validates at RARE")
    for rar in ("common", "uncommon", "basic"):
        errs = _errs(_card([DMG], ctype="attack", rarity=rar, target="enemy", cost=4))
        check(any("RARE-only" in e for e in errs), f"cost 4 is rejected at {rar}: {errs}")
    check(not _ok(_card([DMG], ctype="attack", rarity="rare", target="enemy", cost=5)),
          "cost 5 is still rejected")
    check(_ok(_card([DMG], ctype="attack", rarity="common", target="enemy", cost=3)),
          "cost 3 at common is unchanged")
    # the upgrade band widens with it (upgrades still only cheapen)
    check(_ok(_card([DMG], ctype="attack", rarity="rare", target="enemy", cost=4,
                    upgrade={"effects": [{"op": "damage", "amount": 9}], "cost": 3})),
          "an upgrade may cheapen a cost-4 rare to 3")
    check(not _ok(_card([DMG], ctype="attack", rarity="rare", target="enemy", cost=3,
                        upgrade={"effects": [{"op": "damage", "amount": 9}], "cost": 4})),
          "an upgrade still may not RAISE the cost")

    fc = (MOD_CODE / "Engine" / "ForgedCards.cs").read_text(encoding="utf-8")
    check("internal const int MaxCardCost = 4;" in fc, "C# MaxCardCost is 4")
    check("is RARE-only" in fc, "C# TryParseCardJson carries the rare gate")

    # census counts the heavyweight slot
    cc = census.walk_card(_card([DMG], ctype="attack", rarity="rare", target="enemy", cost=4))
    check(cc.cost4 is True, "census flags a cost-4 card")
    check(census.walk_card(_card([DMG], ctype="attack", target="enemy", cost=3)).cost4 is False,
          "census does not flag a cost-3 card")


# --------------------------------------------------------------------------- 3. upgrade keywords
def _t_upgrade_keyword() -> None:
    print("an upgrade may change ONE keyword (append one / drop a trailing exhaust):")
    # equal length: unchanged behaviour
    check(_ok(_card([DMG], ctype="attack", target="enemy", upgrade=[{"op": "damage", "amount": 9}])),
          "an equal-length upgrade still validates")
    # append one keyword
    for kw in ("exhaust", "retain", "innate", "ethereal"):
        card = _card([DMG], ctype="attack", target="enemy",
                     upgrade=[{"op": "damage", "amount": 9}, {"op": kw}])
        check(_ok(card), f"an upgrade may APPEND '{kw}': {_errs(card)}")
    # drop a trailing exhaust
    check(_ok(_card([DMG, {"op": "exhaust"}], ctype="attack", target="enemy",
                    upgrade=[{"op": "damage", "amount": 9}])),
          "an upgrade may DROP a trailing exhaust")
    # rejections
    bad = [
        ("append a non-keyword",
         _card([DMG], ctype="attack", target="enemy",
               upgrade=[{"op": "damage", "amount": 9}, BLOCK])),
        ("append a keyword the base already has",
         _card([DMG, {"op": "retain"}], ctype="attack", target="enemy",
               upgrade=[{"op": "damage", "amount": 9}, {"op": "retain"}, {"op": "retain"}])),
        ("drop a NON-trailing / non-exhaust effect",
         _card([DMG, BLOCK], ctype="attack", target="enemy",
               upgrade=[{"op": "damage", "amount": 9}])),
        ("swap a keyword at equal length",
         _card([DMG, {"op": "exhaust"}], ctype="attack", target="enemy",
               upgrade=[{"op": "damage", "amount": 9}, {"op": "retain"}])),
        ("change the length by two",
         _card([DMG], ctype="attack", target="enemy",
               upgrade=[{"op": "damage", "amount": 9}, {"op": "retain"}, {"op": "exhaust"}])),
    ]
    for label, card in bad:
        check(not _ok(card), f"rejected: {label}")

    # the smoke harness injects `ethereal` into a starting-deck card; that injection must keep every legal
    # upgrade shape legal (it used to append to both lists, which the AX rule rejects - the slot-05 drop-out).
    from btsgen import smoke_relic  # noqa: PLC0415
    shapes = {
        "equal length": {"effects": [dict(DMG)], "upgrade": {"effects": [{"op": "damage", "amount": 9}]}},
        "upgrade appends a keyword": {"effects": [dict(DMG)],
                                      "upgrade": {"effects": [{"op": "damage", "amount": 9}, {"op": "retain"}]}},
        "upgrade drops a trailing exhaust": {"effects": [dict(DMG), {"op": "exhaust"}],
                                             "upgrade": {"effects": [{"op": "damage", "amount": 9}]}},
        "no upgrade": {"effects": [dict(DMG)]},
    }
    for label, body in shapes.items():
        c = _card([], ctype="attack", target="enemy")
        c.pop("upgrade", None)
        c.update(body)
        smoke_relic._inject_ethereal(c)
        check(any(e["op"] == "ethereal" for e in c["effects"]), f"ethereal injected ({label})")
        check(_ok(c), f"the smoke ethereal injection keeps '{label}' importable: {_errs(c)}")

    fc = (MOD_CODE / "Engine" / "ForgedCards.cs").read_text(encoding="utf-8")
    check("private static string? ValidateUpgradeShape(" in fc, "C# has the shared upgrade-shape rule")
    check("UpgradeAddableKeywords" in fc, "C# names the appendable keyword set")
    dc = (MOD_CODE / "Engine" / "DataCard.cs").read_text(encoding="utf-8")
    check("UpgradeType.Add" in dc and "UpgradeType.Remove" in dc,
          "DataCard declares both BaseLib upgrade directions")
    check("DeclareUpgradeKeywords();" in dc, "DataCard declares the added keyword from the constructor")
    check("KeywordUpgrade(\"exhaust\")" in dc, "the base exhaust picks its UpgradeType from the base/upgrade diff")


# --------------------------------------------------------------------------- 4. two of a kind
def _t_two_of_a_kind() -> None:
    print("a SECOND apply_status of the same status, `when`-gated:")
    gated = {"op": "apply_status", "status": "weak", "amount": 2, "when": {"kind": "target_has_block"}}
    first = {"op": "apply_status", "status": "weak", "amount": 1}
    card = _card([DMG, first, gated], ctype="attack", target="enemy")
    check(_ok(card), f"a gated second Weak validates: {_errs(card)}")
    check(not _ok(_card([DMG, first, {"op": "apply_status", "status": "weak", "amount": 2}],
                        ctype="attack", target="enemy")),
          "an UNGATED second Weak is rejected")
    check(not _ok(_card([DMG, first, gated, dict(gated)], ctype="attack", target="enemy")),
          "a THIRD Weak is rejected")
    # a different status is unaffected
    check(_ok(_card([DMG, first, {"op": "apply_status", "status": "vulnerable", "amount": 1}],
                    ctype="attack", target="enemy")),
          "two DIFFERENT statuses are unchanged")

    v = CardValidator()
    effects = [DMG, first, gated]
    check(v._var_key_at(effects, 1) == "status:weak", "the first Weak keeps the plain var key")
    check(v._var_key_at(effects, 2) == "status:weak:2", "the second Weak takes the :2 var key")
    check(v._status_occurrence(effects, 2) == 1, "occurrence numbering is 0-based")

    fc = (MOD_CODE / "Engine" / "ForgedCards.cs").read_text(encoding="utf-8")
    check("internal static int StatusOccurrence(" in fc and "internal static string StatusVarName(" in fc,
          "C# exposes the occurrence + suffixed-var-name helpers")
    check('StatusDisplay(effects[i].Status) + (occ > 0 ? (occ + 1).ToString() : "")' in fc,
          'the C# suffix is the display name + "2"')
    er = (MOD_CODE / "Engine" / "EffectRunner.cs").read_text(encoding="utf-8")
    check("ForgedCards.StatusOccurrence(spec.Effects, i) > 0" in er,
          "EffectRunner routes the gated copy down the literal-amount path")


# --------------------------------------------------------------------------- 5. tags 1..3
def _t_tags() -> None:
    print("tags maxItems 2 -> 3:")
    schema = json.loads(CARD_SCHEMA.read_text(encoding="utf-8"))
    check(schema["properties"]["tags"]["maxItems"] == 3, "schema tags maxItems is 3")
    check(_ok(_card([DMG], ctype="attack", target="enemy", tags=["strike", "cheap", "opener"])),
          "three tags validate")
    check(not _ok(_card([DMG], ctype="attack", target="enemy", tags=["a", "b", "c", "d"])),
          "four tags are still rejected")


# --------------------------------------------------------------------------- 6. spend_forge
def _t_spend_forge() -> None:
    print("spend_forge (gap #44) — the Forge cash-out:")
    gated = {"op": "damage", "amount": 18, "when": {"kind": "forged_ge", "value": 4}}
    spend = {"op": "spend_forge", "amount": 4}
    good = _card([gated, spend], ctype="attack", rarity="uncommon", target="enemy", cost=2)
    check(_ok(good), f"the canonical shape validates: {_errs(good)}")

    check(not _ok(_card([{"op": "damage", "amount": 6}, {"op": "spend_forge", "amount": 11}],
                        ctype="attack", target="enemy")), "amount 11 is over the cap")
    check(not _ok(_card([{"op": "damage", "amount": 6}, {"op": "spend_forge", "amount": 0}],
                        ctype="attack", target="enemy")), "amount 0 is rejected")
    check(not _ok(_card([spend], ctype="attack", target="enemy")),
          "spend_forge can't be a card's ONLY effect")
    check(not _ok(_card([DMG, spend], ctype="attack", rarity="basic", target="enemy")),
          "spend_forge is rejected on a BASIC card")
    check(not _ok(_card([DMG, spend, dict(spend)], ctype="attack", target="enemy")),
          "two spend_forge effects are rejected")
    # the ordering rule: a forged_ge gate after the spend reads the counter the card just emptied
    check(not _ok(_card([spend, gated], ctype="attack", rarity="uncommon", target="enemy")),
          "a when:forged_ge payoff AFTER the spend is rejected")
    # card-only
    payload = _card([{"op": "add_trigger", "trigger": "turn_start",
                      "effects": [{"op": "spend_forge", "amount": 2}]}], ctype="power")
    check(not _ok(payload), "spend_forge is rejected inside an add_trigger payload")

    fc = (MOD_CODE / "Engine" / "ForgedCards.cs").read_text(encoding="utf-8")
    check('"spend_forge",' in fc and "SpendForgeMaxAmount = 10" in fc,
          "C# registers spend_forge with the same cap")
    check("a 'when:forged_ge' effect can't come after a 'spend_forge'" in fc,
          "the C# carries the ordering rule too")
    er = (MOD_CODE / "Engine" / "EffectRunner.cs").read_text(encoding="utf-8")
    check('case "spend_forge":' in er and "ForgedForgePower.Spend(" in er,
          "EffectRunner executes spend_forge through the power")
    check("[AX] spend_forge" in er, "the spend logs an [AX] tag")
    fp = (MOD_CODE / "Powers" / "ForgedForgePower.cs").read_text(encoding="utf-8")
    check("public static int Spend(" in fp, "ForgedForgePower exposes Spend")
    check("RemovePowerInternal(power)" in fp, "spending to 0 removes the counter")


# --------------------------------------------------------------------------- 7. spread_debuffs
def _t_spread_debuffs() -> None:
    print("spread_debuffs (gaps #45-#47) — contagion:")
    vuln = {"op": "apply_status", "status": "vulnerable", "amount": 2}
    spread = {"op": "spread_debuffs"}
    good = _card([vuln, spread], rarity="uncommon", target="enemy")
    check(_ok(good), f"the canonical shape validates: {_errs(good)}")

    for tgt in ("all_enemies", "self", "random_enemy"):
        check(not _ok(_card([vuln, spread], rarity="uncommon", target=tgt)),
              f"spread_debuffs is rejected on a {tgt} card")
    check(not _ok(_card([vuln, {"op": "spread_debuffs", "amount": 2}], rarity="uncommon", target="enemy")),
          "spread_debuffs carries no amount")
    check(not _ok(_card([vuln, spread], rarity="basic", target="enemy")),
          "spread_debuffs is rejected on a BASIC card")
    check(not _ok(_card([vuln, spread, dict(spread)], rarity="uncommon", target="enemy")),
          "two spread_debuffs effects are rejected")
    payload = _card([{"op": "add_trigger", "trigger": "turn_start",
                      "effects": [{"op": "spread_debuffs"}]}], ctype="power")
    check(not _ok(payload), "spread_debuffs is rejected inside an add_trigger payload")

    er = (MOD_CODE / "Engine" / "EffectRunner.cs").read_text(encoding="utf-8")
    check('case "spread_debuffs":' in er and "private static async Task SpreadDebuffs(" in er,
          "EffectRunner executes spread_debuffs")
    for pw in ("VulnerablePower", "WeakPower", "FrailPower", "PoisonPower"):
        check(f"Take<{pw}>(" in er, f"SpreadDebuffs copies {pw}")
    check("c.IsAlive && c != source" in er, "the source enemy is skipped and only living enemies are copied to")
    check("[AX] spread_debuffs" in er, "the spread logs an [AX] tag")


# --------------------------------------------------------------------------- 8. describe byte-match
def _t_describe() -> None:
    print("describe byte-match (cardgen.py == ForgedCards.Describe):")
    fc = (MOD_CODE / "Engine" / "ForgedCards.cs").read_text(encoding="utf-8")
    check('parts.Add($"Spend {Math.Max(1, e.Amount)} Forge.");' in fc,
          "the C# spend_forge sentence is the literal amount")
    check("""parts.Add("Copy the target's debuffs to all other enemies.");""" in fc,
          "the C# spread_debuffs sentence")
    txt = cardgen.describe([{"op": "spend_forge", "amount": 5}], "enemy")
    check(txt == "Spend 5 Forge.", f"cardgen spend_forge sentence, got {txt!r}")
    txt = cardgen.describe([{"op": "spread_debuffs"}], "enemy")
    check(txt == "Copy the target's debuffs to all other enemies.",
          f"cardgen spread_debuffs sentence, got {txt!r}")
    # the full card reads price-last, with the gate woven into the payoff
    txt = cardgen.describe([{"op": "damage", "amount": 18, "when": {"kind": "forged_ge", "value": 4}},
                            {"op": "spend_forge", "amount": 4}], "enemy")
    check(txt.endswith("Spend 4 Forge.") and "if your Forge is 4" in txt,
          f"the cash-out card reads gate-then-spend, got {txt!r}")


# --------------------------------------------------------------------------- 9. the contract surfaces
def _t_contract() -> None:
    print("contract surfaces (vocabulary / schema / exemplars / menus / app.js):")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    check("| `spend_forge`" in vocab, "VOCABULARY has a spend_forge op row")
    check("| `spread_debuffs`" in vocab, "VOCABULARY has a spread_debuffs op row")
    check("`cost` (0–4 energy" in vocab, "VOCABULARY's card shape says cost 0-4")
    check("Cost 4 is the heavyweight slot and is RARE-ONLY" in vocab, "VOCABULARY states the rare gate")
    check("APPEND exactly one keyword" in vocab, "VOCABULARY states the upgrade-keyword rule")
    check("Two of the same status on one card" in vocab, "VOCABULARY states the two-of-a-kind rule")
    check("`tags`: 1–3 slugs" in vocab, "VOCABULARY states the widened tag cap")

    schema = json.loads(CARD_SCHEMA.read_text(encoding="utf-8"))
    ops = set(schema["$defs"]["effect"]["properties"]["op"]["enum"])
    check({"spend_forge", "spread_debuffs"} <= ops, "the card op enum carries both new ops")
    payload_ops = set(schema["$defs"]["triggerEffect"]["properties"]["op"]["enum"])
    check(not ({"spend_forge", "spread_debuffs"} & payload_ops),
          "the triggerEffect op enum carries NEITHER (both are card-only)")

    pool = json.loads(EXEMPLAR_POOL.read_text(encoding="utf-8"))["exemplars"]
    by_id = {e["card"]["id"]: e for e in pool}
    for eid, tok in (("ex_quench_the_hoard", "spend_forge"),
                     ("ex_creeping_rot", "spread_debuffs"),
                     ("ex_second_wind_cut", "apply_status")):
        check(eid in by_id, f"exemplar {eid} exists")
        if eid in by_id:
            check(_ok(by_id[eid]["card"]), f"exemplar {eid} validates: {_errs(by_id[eid]['card'])}")
            check(tok in json.dumps(by_id[eid]["card"]), f"exemplar {eid} uses {tok}")
    check(by_id.get("ex_quench_the_hoard", {}).get("needs") == "forge",
          "the cash-out exemplar is tagged needs:forge")
    up = by_id.get("ex_second_wind_cut", {}).get("card", {}).get("upgrade", {}).get("effects", [])
    check(up and up[-1].get("op") == "retain", "the two-of-a-kind exemplar also demos the appended keyword")

    check(any(f.id == "contagion" for f in featured.FEATURED_MENU), "featured menu has the contagion entry")
    check(any(f.id == "forge_cashout" for f in featured.CLASS_KIND_MENU),
          "featured class-kind menu has the forge cash-out entry")
    check("spend_forge" in harness_v2._CLASS_ONLY_TOKENS, "spend_forge is class-only in the harness")
    check("spread_debuffs" in harness_v2._PREFERRED_OPS, "spread_debuffs is a preferred compositional op")

    js = APP_JS.read_text(encoding="utf-8")
    check('case "spend_forge": return `Spend ${a ?? 1} Forge`;' in js, "app.js renders spend_forge")
    check('case "spread_debuffs":' in js, "app.js renders spread_debuffs")

    bp = cf._BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()
    print(f"  (rule 0.9) blueprint prompt: {len(bp):,} chars (the ONE ceiling lives in tests/test_harness_v2.py)")
    print(f"  (rule 0.9) VOCABULARY.md:    {len(vocab):,} chars")
    # The 100,000 ceiling this used to re-declare now lives once, in test_harness_v2.py: one prompt, one ceiling.
    check("OPTIONAL CASH-OUT" in bp, "the forge section pitches the cash-out")


def main() -> int:
    test_version()
    _t_cost()
    _t_upgrade_keyword()
    _t_two_of_a_kind()
    _t_tags()
    _t_spend_forge()
    _t_spread_debuffs()
    _t_describe()
    _t_contract()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
