"""Phase BA — FORGED POTIONS (VOCAB_GAP_REMEDIATION_PLAN Wave 4, vocab v55) — offline, no API key.

Run:  uv run python -m tests.test_phase_ba       (from generation/)
Exits nonzero on any failure.

Every forged class now ships EXACTLY ONE custom potion, declared on the character as `potion_pool`. What this
file pins, in lockstep with the C#:

  1. the vocab stamp is 55 on both sides (bts1.VOCAB_VERSION <= ForgedCards.VocabVersion);
  2. the C# engine — a PotionSpec record, CharacterSpec.PotionPool defaulting EMPTY (so every pre-v55 class
     parses byte-identically), the ForgedCharacters parse/accessors, and the ForgedPotion model: it maps
     rarity/usage/target onto the game's enums, runs its effects through EffectRunner.RunRelicEffects (the BA-0
     find — OnUse is handed a PlayerChoiceContext, so no new runner exists), and takes its icon from the
     emoji renderer;
  3. the POOL decision, which BA-0 forced rather than chose: per-class pools, because PotionPoolModel caches
     AllPotions and ModHelper freezes a pool at first read. slotgen emits ForgedClassPotionPoolKK + the shells,
     the character template points at its OWN pool, and an unfilled slot is withheld in GetUnlockedPotions
     (the one un-cached seam);
  4. the vocabulary is the same set on both sides (Python _POTION_OPS == C# PotionEffectOps), and the Python
     validator rejects exactly what the C# importer rejects;
  5. an ABSENT potion is not an error — assembly defaults one in, so no class ever ships potionless and no
     blueprint ever burns a repair round-trip on it;
  6. the contract: VOCABULARY.md documents the potion, the blueprint prompt requires it, and the website
     renders it (it carries no card text, so the panel is the only place a player can read it).

No private rule-0.9 ceiling lives here — the one budget is in tests/test_harness_v2.py (the AT/AW regression).
"""
from __future__ import annotations

import pathlib
import re
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, paths  # noqa: E402
from btsgen import class_forge as cf  # noqa: E402

_PASS = 0
_FAIL = 0

MOD_CODE = paths.VOCABULARY.parents[1] / "BlankTheSpireCode"   # mod/contract/.. -> mod/BlankTheSpireCode
REPO = paths.VOCABULARY.parents[2]                             # mod/contract/.. -> the repo root


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _cs(*parts: str) -> str:
    return (MOD_CODE.joinpath(*parts)).read_text(encoding="utf-8")


def _potion(**over) -> dict:
    p = {"name": "Emberdraught", "emoji": "\U0001F525", "rarity": "common", "usage": "combat",
         "target": "enemy", "description": "Deal 12 damage.",
         "effects": [{"op": "damage", "amount": 12}]}
    p.update(over)
    return p


def _bp(potion=None, **extra) -> dict:
    bp = {"name": "T", "description": "d", "max_hp": 70, "cards": []}
    if potion is not None:
        bp["potion"] = potion
    bp.update(extra)
    return bp


# --------------------------------------------------------------------------- 1. stamps
def test_version() -> None:
    print("Phase BA vocab stamp is 55+ (Python + C#):")
    check(bts1.VOCAB_VERSION >= 55, f"bts1.VOCAB_VERSION >= 55 (got {bts1.VOCAB_VERSION})")
    fc = _cs("Engine", "ForgedCards.cs")
    m = re.search(r"public const int VocabVersion = (\d+);", fc)
    check(m is not None and int(m.group(1)) >= 55, f"ForgedCards.VocabVersion >= 55 (got {m and m.group(1)})")
    check(m is not None and bts1.VOCAB_VERSION <= int(m.group(1)), "bts1.VOCAB_VERSION <= ForgedCards.VocabVersion")
    check("Phase BA" in fc and "potion_pool" in fc,
          "ForgedCards.cs VocabVersion comment names Phase BA + the new potion_pool key")
    src = pathlib.Path(bts1.__file__).read_text(encoding="utf-8")
    check("55: Phase BA" in src, "bts1.py's VOCAB_VERSION comment records the v55 (Phase BA) entry")


# --------------------------------------------------------------------------- 2. the C# engine
def _t_engine() -> None:
    print("the engine: the spec, the character field, and the parse:")
    spec = _cs("Engine", "PotionSpec.cs")
    for field in ("string Id", "string Name", "string Description", "string Emoji",
                  "string Rarity", "string Usage", "string Target", "EffectSpec[] Effects"):
        check(field in spec, f"PotionSpec carries {field}")

    ch = _cs("Engine", "CharacterSpec.cs")
    check("public PotionSpec[] PotionPool { get; init; } = [];" in ch,
          "CharacterSpec carries PotionPool, defaulting EMPTY (every pre-v55 class parses unchanged)")

    chars = _cs("Engine", "ForgedCharacters.cs")
    check('d.ContainsKey("potion_pool")' in chars, "ForgedCharacters parses the character's potion_pool")
    check("PotionPool = potionPool" in chars, "... and puts it on the CharacterSpec")
    check("public const int MaxPotions = 1;" in chars, "MaxPotions is 1 (one signature potion per class)")
    check("public static PotionSpec? PotionSpecFor(int k, int m)" in chars, "PotionSpecFor(k, m) accessor")
    check("public static bool HasForgedPotions(int k)" in chars, "HasForgedPotions(k) accessor")
    # The pools are parsed FIRST so a potion op can be checked against the class's own content.
    i_status = chars.index('d.ContainsKey("status_pool")')
    i_potion = chars.index('d.ContainsKey("potion_pool")')
    check(i_status < i_potion,
          "potion_pool is parsed AFTER the orb/status/summon pools (so its ops can be checked against them)")

    print("the engine: ForgedPotion maps onto the game's enums and reuses the relic runner:")
    fp = _cs("Powers", "ForgedPotion.cs")
    check("public abstract class ForgedPotion : CustomPotionModel" in fp, "ForgedPotion is a CustomPotionModel")
    check("PotionRarity.Uncommon" in fp and "PotionRarity.Rare" in fp and "PotionRarity.Common" in fp,
          "rarity maps onto the three tiers PotionFactory rolls")
    check("PotionUsage.AnyTime" in fp and "PotionUsage.CombatOnly" in fp, "usage maps onto PotionUsage")
    check("TargetType.AnyEnemy" in fp and "TargetType.AllEnemies" in fp and "TargetType.Self" in fp,
          "target maps onto TargetType")
    check("protected override async Task OnUse(PlayerChoiceContext choiceContext, Creature? target)" in fp,
          "OnUse overrides the game's entry point with its real (nullable-target) signature")
    check("EffectRunner.RunRelicEffects(" in fp,
          "BA-0: the effects run through RunRelicEffects — no new effect runner was built")
    check("public bool IsEmptySlot => Source == null;" in fp, "an unfilled slot reports IsEmptySlot")
    check("EmojiIconRenderer.IconPath(IconKey)" in fp, "the icon is the class's emoji, rendered at init")
    check("RelicImagePath()" in fp, "... with a SHIPPED fallback path (a null image would NRE the potion node)")
    check("new PotionLoc(" in fp, "in-code localization (no .pck rebuild) supplies name + description")
    check('$"potion{PotionClass}_{PotionIndex}"' in fp, "the icon key matches MainFile's pre-render key")

    main = _cs("MainFile.cs")
    check('Engine.EmojiIconRenderer.Kick($"potion{k}_{m}", po.Emoji)' in main,
          "MainFile pre-renders every class potion's emoji at init")

    print("the engine: apply_status_custom reached the no-card runner (so a status class's potion can use it):")
    er = _cs("Engine", "EffectRunner.cs")
    relic_part = er.split("RunRelicEffects", 1)[1]
    check('case "apply_status_custom":' in relic_part, "RunRelicEffects handles apply_status_custom")
    check("ResolveStatusInstance(relicClass, e.StatusName)" in relic_part,
          "... resolving against the running class's own status pool")
    check("[BA] apply_status_custom" in relic_part, "... with a [BA] tag on both the buff and debuff paths")


# --------------------------------------------------------------------------- 3. the pool decision
def _t_pool() -> None:
    print("the pool: PER CLASS (forced by the AllPotions cache), composing with the base table:")
    sg = (REPO / "generation" / "btsgen" / "slotgen.py").read_text(encoding="utf-8")
    check("POTIONS_PER_CLASS = 1" in sg, "slotgen declares POTIONS_PER_CLASS = 1 (== ForgedCharacters.MaxPotions)")
    check("CLASS_POTION_POOL_TMPL" in sg and "CLASS_POTION_LINE" in sg, "slotgen has the pool + shell templates")
    check("caches AllPotions" in sg and "FREEZES" in sg,
          "slotgen records WHY the pool is per-class (the cache + freeze), not just that it is")

    gen = (MOD_CODE / "Cards" / "Forged" / "ForgedClasses.g.cs").read_text(encoding="utf-8")
    for k in (1, 2, 3, 4):
        check(f"public sealed class ForgedClassPotionPool{k:02} : CustomPotionPoolModel" in gen,
              f"class {k:02} has its OWN potion pool")
        check(f"[Pool(typeof(ForgedClassPotionPool{k:02}))]" in gen,
              f"class {k:02}'s potion shell is bound to that pool")
        check(f"public sealed class ForgedClass{k:02}Potion1 : BlankTheSpire.BlankTheSpireCode.Powers.ForgedPotion"
              in gen, f"class {k:02} has its potion shell")
        check(f"ModelDb.PotionPool<ForgedClassPotionPool{k:02}>()" in gen,
              f"character slot {k:02} points at its own potion pool")
    check("ModelDb.PotionPool<BlankTheSpirePotionPool>()" not in gen,
          "no forged character still points at the SHARED pool (that was the cross-class bleed)")
    check("GetUnlockedPotions(UnlockState unlockState)" in gen and "IsEmptySlot" in gen,
          "an undeclared slot is withheld in GetUnlockedPotions — the seam that is NOT cached")


# --------------------------------------------------------------------------- 4. vocabulary lockstep
def _t_lockstep() -> None:
    print("lockstep: the Python and C# potion vocabularies are the SAME set:")
    chars = _cs("Engine", "ForgedCharacters.cs")
    block = chars.split("PotionEffectOps =", 1)[1].split("];", 1)[0]
    cs_ops = set(re.findall(r'"([a-z_]+)"', block))
    check(cs_ops == cf._POTION_OPS,
          f"_POTION_OPS == C# PotionEffectOps (python-only {sorted(cf._POTION_OPS - cs_ops)}, "
          f"c#-only {sorted(cs_ops - cf._POTION_OPS)})")
    for name, pyset in (("PotionRarities", cf._POTION_RARITIES), ("PotionTargets", cf._POTION_TARGETS)):
        blk = chars.split(f"{name} =", 1)[1].split("];", 1)[0]
        check(set(re.findall(r'"([a-z_]+)"', blk)) == pyset, f"{name} matches the Python set")
    usages = chars.split("PotionUsages =", 1)[1].split("];", 1)[0]
    check(set(re.findall(r'"([a-z_]+)"', usages)) == {"combat", "any"}, "PotionUsages is combat/any")
    check("discard" not in cs_ops, "the relic DRAWBACK op is not in the potion vocabulary (a potion is a boon)")


# --------------------------------------------------------------------------- 5. validation
def _t_validation() -> None:
    print("validation: a well-formed potion passes:")
    check(cf._validate_potion(_bp(_potion())) == [], "a plain damage potion validates")
    check(cf._validate_potion(_bp(_potion(target="self", effects=[{"op": "block", "amount": 18}]))) == [],
          "a self block potion validates")
    check(cf._validate_potion(_bp(_potion(usage="any", target="self",
                                          effects=[{"op": "heal", "amount": 10}]))) == [],
          "an out-of-combat HEAL potion validates")

    print("validation: an ABSENT potion is not an error (assembly defaults one in):")
    check(cf._validate_potion(_bp()) == [], "no potion declared -> no blueprint error")

    print("validation: the same things the C# importer rejects:")
    bad = [
        ("unknown op", _bp(_potion(effects=[{"op": "transform_card", "amount": 1}]))),
        ("self-target damage", _bp(_potion(target="self", effects=[{"op": "damage", "amount": 9}]))),
        ("buff on an enemy target", _bp(_potion(target="enemy",
                                                effects=[{"op": "apply_status", "status": "strength", "amount": 2}]))),
        ("debuff on a self target", _bp(_potion(target="self",
                                                effects=[{"op": "apply_status", "status": "poison", "amount": 5}]))),
        ("unsupported status", _bp(_potion(target="enemy",
                                           effects=[{"op": "apply_status", "status": "confused", "amount": 1}]))),
        ("bad rarity", _bp(_potion(rarity="legendary"))),
        ("bad target", _bp(_potion(target="everyone"))),
        ("bad usage", _bp(_potion(usage="whenever"))),
        ("amount below 1", _bp(_potion(effects=[{"op": "damage", "amount": 0}]))),
        ("no effects", _bp(_potion(effects=[]))),
        ("three effects", _bp(_potion(target="self", effects=[{"op": "block", "amount": 5},
                                                             {"op": "draw", "amount": 1},
                                                             {"op": "gain_energy", "amount": 1}]))),
        ("usage any with a non-heal op", _bp(_potion(usage="any", target="self",
                                                     effects=[{"op": "block", "amount": 8}]))),
        ("apply_status_custom on a class with no status_pool",
         _bp(_potion(target="self", effects=[{"op": "apply_status_custom", "status_name": "Ember", "amount": 2}]))),
        ("channel_orb on a class with no orb_pool",
         _bp(_potion(target="self", effects=[{"op": "channel_orb", "orb": "random", "amount": 2}]))),
        ("summon on a class with no summon_pool",
         _bp(_potion(target="self", effects=[{"op": "summon", "summon_name": "Wisp", "amount": 1}]))),
    ]
    for label, bp in bad:
        check(cf._validate_potion(bp) != [], f"rejected: {label}")

    print("validation: the class-conditional ops are ACCEPTED when the class does declare the content:")
    status_bp = _bp(_potion(target="self", effects=[{"op": "apply_status_custom", "status_name": "Ember", "amount": 3}]),
                    status_pool=[{"name": "Ember", "type": "buff", "hook": "damage_dealt"}])
    check(cf._validate_potion(status_bp) == [], "a status class's potion may apply its OWN status")
    check(cf._validate_potion(
        _bp(_potion(target="self", effects=[{"op": "apply_status_custom", "status_name": "Nope", "amount": 3}]),
            status_pool=[{"name": "Ember", "type": "buff", "hook": "damage_dealt"}])) != [],
        "... but not a status that is not in its pool")
    orb_bp = _bp(_potion(target="self", effects=[{"op": "channel_orb", "orb": "random", "amount": 2}]),
                 orb_pool=["lightning"])
    check(cf._validate_potion(orb_bp) == [], "an orb class's potion may channel its orbs")
    summon_bp = _bp(_potion(target="self", effects=[{"op": "summon", "summon_name": "Wisp", "amount": 1}]),
                    summon_pool=[{"name": "Wisp"}])
    check(cf._validate_potion(summon_bp) == [], "a summon class's potion may call its minion")

    print("validation: a custom DEBUFF still needs an enemy target:")
    check(cf._validate_potion(
        _bp(_potion(target="self", effects=[{"op": "apply_status_custom", "status_name": "Rot", "amount": 3}]),
            status_pool=[{"name": "Rot", "type": "debuff", "hook": "damage_taken"}])) != [],
        "a custom debuff on a self-target potion is rejected")


# --------------------------------------------------------------------------- 6. the default
def _t_default() -> None:
    print("the default potion: every class gets one, and it still reaches for the class's own content:")
    d = cf._default_potion({"name": "Ashen", "status_pool": [{"name": "Ember", "type": "buff", "emoji": "\U0001F525"}]}, [])
    check(d["effects"][0]["op"] == "apply_status_custom" and d["effects"][0]["status_name"] == "Ember",
          "a status class defaults to its own buff")
    d = cf._default_potion({"name": "Ashen", "orb_pool": ["lightning"]}, [])
    check(d["effects"][0]["op"] == "channel_orb", "an orb class defaults to channelling")
    d = cf._default_potion({"name": "Ashen", "summon_pool": [{"name": "Wisp"}]}, [])
    check(d["effects"][0]["op"] == "summon" and d["effects"][0]["summon_name"] == "Wisp",
          "a summon class defaults to its minion")
    d = cf._default_potion({"name": "Ashen"}, [{"role": "signature_blade"}])
    check(d["effects"][0]["op"] == "forge", "a forge class defaults to Forge income")
    d = cf._default_potion({"name": "Ashen"}, [])
    check(d["effects"][0]["op"] == "block", "a plain class defaults to a defensive brew")
    # Whatever it defaults to must itself be importable.
    for bp_extra, cards in (({"status_pool": [{"name": "Ember", "type": "buff"}]}, []),
                            ({"orb_pool": ["lightning"]}, []),
                            ({"summon_pool": [{"name": "Wisp"}]}, []),
                            ({}, [{"role": "signature_blade"}]),
                            ({}, [])):
        bp = {"name": "Ashen", **bp_extra}
        bp["potion"] = cf._default_potion(bp, cards)
        check(cf._validate_potion(bp) == [], f"the default for {bp_extra or 'a plain class'} validates")

    print("assembly: the bundle ALWAYS carries a potion_pool:")
    src = pathlib.Path(cf.__file__).read_text(encoding="utf-8")
    check('character["potion_pool"] = [potion]' in src, "assembly writes potion_pool onto the character")
    check("_default_potion(bp, bp.get(\"cards\") or [])" in src, "... defaulting it when the blueprint shipped none")


# --------------------------------------------------------------------------- 7. the contract
def _t_contract() -> None:
    print("contract: the vocabulary documents the potion:")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    check("## The signature potion" in vocab, "VOCABULARY.md has a signature-potion section")
    sec = vocab.split("## The signature potion", 1)[1].split("\n## ", 1)[0]
    check("potion_pool" in sec, "... names the bundle key")
    for op in sorted(cf._POTION_OPS):
        check(op in sec, f"... documents the {op} op")
    check("never replacing them" in sec or "alongside" in sec,
          "... states the load-bearing fact: it ADDS to the base potion table")
    check("EVERY class declares one" in vocab, "... and that every class has one")

    print("contract: the blueprint prompt requires it:")
    bp = cf._BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()
    check('"potion" (REQUIRED, exactly one)' in bp, "the blueprint RULES require exactly one potion")
    check('"potion": {' in bp, "the blueprint FORMAT block shows the potion's shape")
    check("Make it read as THIS class" in bp, "... and asks for a class-specific one")
    print(f"  (rule 0.9) blueprint prompt: {len(bp):,} chars "
          f"(scaffolding {len(bp) - len(paths.VOCABULARY.read_text(encoding='utf-8')):,}; "
          f"the ONE ceiling lives in tests/test_harness_v2.py)")

    print("contract: the website renders it (a potion carries no card text):")
    js = (REPO / "web" / "static" / "app.js").read_text(encoding="utf-8")
    check('pool: "potion_pool"' in js, "app.js lists potion_pool among the class mechanics")
    check("function potionLines(" in js, "app.js formats the potion's lines")
    check("Drops alongside the usual potions" in js, "... and tells the player it is an ADDITION to the table")
    check('potion: "How\'s this potion?"' in js, "the feedback popout has a potion prompt")
    fg = (REPO / "web" / "forge.py").read_text(encoding="utf-8")
    check('"potion"' in fg.split("ELEMENT_KINDS", 1)[1].split("\n", 1)[0],
          "the server accepts potion as a rateable element kind")


def main() -> int:
    test_version()
    _t_engine()
    _t_pool()
    _t_lockstep()
    _t_validation()
    _t_default()
    _t_contract()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


def test_phase_ba_all() -> None:
    """The pytest entry point: run every section and FAIL the run if any check did.

    (The older phase files expose only `test_version` to pytest and keep the rest behind `main()`, so a
    regression in those sections is invisible under `pytest`. This one asserts.)"""
    global _PASS, _FAIL
    _PASS = _FAIL = 0
    rc = main()
    assert rc == 0, f"{_FAIL} Phase BA check(s) failed - see the FAIL lines above"


if __name__ == "__main__":
    sys.exit(main())
