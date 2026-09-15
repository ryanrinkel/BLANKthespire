"""Phase AY — RUN-PERSISTENT FORGE (VOCAB_GAP_REMEDIATION_PLAN Wave 4, vocab v54) — offline, no API key.

Run:  uv run python -m tests.test_phase_ay       (from generation/)
Exits nonzero on any failure. Covers the v54 change in lockstep with the C#:
  1. the vocab stamp is 54 on both sides (bts1.VOCAB_VERSION <= ForgedCards.VocabVersion) and both comments
     record the Phase AY entry;
  2. THE ENGINE — the spike's answer, wired: CharacterSpec.ForgePersist, ForgedCharacters parses `forge_persist`
     and exposes the class/player reads, ForgedForgePower.PersistCap + the combat-end Bank, and ForgePersist.cs
     (a BaseLib CustomSingletonModel on the COMBAT hook list holding a SavedSpireField<Player,int>, restoring at
     the first player turn start through Stoke so the blade is summoned too);
  3. THE CAP IS MIRRORED — class_forge._FORGE_PERSIST_CAP == ForgedForgePower.PersistCap;
  4. BLUEPRINT VALIDATION — the flag must be a bool and the class must be a FORGE class (a signature_blade row);
     absent / false always passes, and _validate_blueprint runs the check;
  5. ASSEMBLY — the offline forge fake carries the flag into the bundle's character; a non-forge class never
     emits the key; the flag is DROPPED when the assembled class has no `forge` income (self-healing);
  6. CENSUS — census_bundle reads the character-level flag and format_report prints the AY line;
  7. CODEC — a bundle carrying the flag round-trips through the BTSC codec at v54;
  8. CONTRACT SURFACES — the VOCABULARY.md section + the forge op row, the blueprint prompt's format block and
     rule line, the FORGE archetype pitch, and the rule-0.9 prompt budget.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import tempfile

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, census, paths  # noqa: E402
from btsgen import class_forge as cf  # noqa: E402
from btsgen.class_forge import ClassBrief, _CardFake, forge_class  # noqa: E402

_PASS = 0
_FAIL = 0

MOD_CODE = paths.VOCABULARY.parents[1] / "BlankTheSpireCode"   # mod/contract/.. -> mod/BlankTheSpireCode


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _cs(*parts: str) -> str:
    return (MOD_CODE.joinpath(*parts)).read_text(encoding="utf-8")


def _bp(cards, **extra) -> dict:
    """A blueprint stub for the _validate_forge_persist unit (it only reads `forge_persist` + card roles)."""
    bp = {"name": "T", "description": "d", "max_hp": 70, "cards": cards}
    bp.update(extra)
    return bp


_BLADE = {"role": "signature_blade", "name_hint": "Blade", "type": "attack", "rarity": "token"}
_PLAIN = {"role": "pool", "name_hint": "Jab", "type": "attack", "rarity": "common"}


# --------------------------------------------------------------------------- 1. stamps
def test_version() -> None:
    # `>=`, not `==`: the stamp is a shared global that every later phase bumps, and pinning it here made this
    # test a measuring stick for someone else's number (the AZ rule-0.9 lesson). AY owns `forge_persist`, below.
    print("Phase AY vocab stamp is 54+ (Python + C#):")
    check(bts1.VOCAB_VERSION >= 54, f"bts1.VOCAB_VERSION >= 54 (got {bts1.VOCAB_VERSION})")
    fc = _cs("Engine", "ForgedCards.cs")
    m = re.search(r"public const int VocabVersion = (\d+);", fc)
    check(m is not None and int(m.group(1)) >= 54, f"ForgedCards.VocabVersion >= 54 (got {m and m.group(1)})")
    check(m is not None and bts1.VOCAB_VERSION <= int(m.group(1)), "bts1.VOCAB_VERSION <= ForgedCards.VocabVersion")
    check("Phase AY" in fc and "forge_persist" in fc,
          "ForgedCards.cs VocabVersion comment names Phase AY + the new flag")
    src = pathlib.Path(bts1.__file__).read_text(encoding="utf-8")
    check("54: Phase AY" in src, "bts1.py's VOCAB_VERSION comment records the v54 (Phase AY) entry")


# --------------------------------------------------------------------------- 2. the engine
def _t_engine() -> None:
    print("the engine: the character flag, the bank, and the restore model:")
    spec = _cs("Engine", "CharacterSpec.cs")
    check("public bool ForgePersist { get; init; } = false;" in spec,
          "CharacterSpec carries ForgePersist, defaulting to false (pre-v54 classes are unchanged)")

    chars = _cs("Engine", "ForgedCharacters.cs")
    check('Bool(d, "forge_persist", false)' in chars, "ForgedCharacters parses the character's forge_persist")
    check("ForgePersist = forgePersist" in chars, "the parsed flag reaches the CharacterSpec")
    check("public static bool IsForgePersistClass(int k)" in chars
          and "public static bool IsForgePersistPlayer(Player? player)" in chars,
          "ForgedCharacters exposes the class + player reads")

    power = _cs("Powers", "ForgedForgePower.cs")
    m = re.search(r"public const int PersistCap = (\d+);", power)
    check(m is not None and int(m.group(1)) == 5, f"ForgedForgePower.PersistCap == 5 (got {m and m.group(1)})")
    check("public override Task AfterCombatEnd(CombatRoom room)" in power,
          "the bank runs at combat end — the hook still sees the live power (powers are cleared later)")
    check("Math.Min(Math.Max(stacks, 0), PersistCap)" in power, "the bank is capped at PersistCap")
    check("IsForgePersistPlayer(player)" in power, "only a forge_persist class banks anything")
    check("resets each combat — unless your class keeps its edge" in power,
          "the Forge tooltip covers BOTH regimes (loc is baked once at ModelDb init, so it cannot read the class)")

    persist = _cs("Engine", "ForgePersist.cs")
    check("class ForgePersist : CustomSingletonModel" in persist,
          "the restore lives on a BaseLib CustomSingletonModel (no forge class is guaranteed a relic)")
    check("base(HookType.Combat)" in persist,
          "it subscribes to the COMBAT hook list — AfterPlayerTurnStart iterates that, not the run subscribers")
    check("static readonly SavedSpireField<Player, int> Banked" in persist,
          "the bank is a STATIC SavedSpireField<Player,int> (BaseLib's post-mod-init scan registers it)")
    check("public override async Task AfterPlayerTurnStart" in persist and "_restored" in persist,
          "the restore rides turn start, once per combat (no combat-start hook hands out a ctx+player)")
    check("Banked.Set(player, 0);" in persist,
          "the bank empties as it is paid out (a mid-combat reload must not pay it twice)")
    check("ForgedForgePower.Stoke(ctx, player, carry)" in persist,
          "the restore goes through Stoke, so it also summons the signature blade")


# --------------------------------------------------------------------------- 3. the cap is mirrored
def _t_cap() -> None:
    print("the carry cap is mirrored on both sides:")
    power = _cs("Powers", "ForgedForgePower.cs")
    cs_cap = int(re.search(r"public const int PersistCap = (\d+);", power).group(1))
    check(cf._FORGE_PERSIST_CAP == cs_cap,
          f"class_forge._FORGE_PERSIST_CAP ({cf._FORGE_PERSIST_CAP}) == ForgedForgePower.PersistCap ({cs_cap})")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    check(f"banking `min(Forge, {cs_cap})`" in vocab, "VOCABULARY.md quotes the same cap")


# --------------------------------------------------------------------------- 4. blueprint validation
def _t_validation() -> None:
    print("blueprint validation: bool, and FORGE-CLASS ONLY:")
    check(cf._validate_forge_persist(_bp([_PLAIN]), [_PLAIN]) == [],
          "a blueprint with no forge_persist key passes")
    check(cf._validate_forge_persist(_bp([_PLAIN], forge_persist=False), [_PLAIN]) == [],
          "forge_persist: false passes on any class")
    check(cf._validate_forge_persist(_bp([_PLAIN], forge_persist=None), [_PLAIN]) == [],
          "an explicit null is treated as absent")
    errs = cf._validate_forge_persist(_bp([_PLAIN], forge_persist="yes"), [_PLAIN])
    check(len(errs) == 1 and "must be a boolean" in errs[0], f"a non-bool is rejected: {errs}")
    errs = cf._validate_forge_persist(_bp([_PLAIN], forge_persist=True), [_PLAIN])
    check(len(errs) == 1 and "not a forge class" in errs[0],
          f"forge_persist on a class with no signature_blade is rejected: {errs}")
    check(cf._validate_forge_persist(_bp([_PLAIN, _BLADE], forge_persist=True), [_PLAIN, _BLADE]) == [],
          "forge_persist on a forge class (a signature_blade row) passes")
    src = pathlib.Path(cf.__file__).read_text(encoding="utf-8")
    check("errs += _validate_forge_persist(bp, cards)" in src,
          "_validate_blueprint runs the check (it is not dead code)")


# --------------------------------------------------------------------------- 5. assembly
def _fake(concept: str) -> dict:
    saved = os.environ.get("BTS_FORGE_LEDGER")
    os.environ["BTS_FORGE_LEDGER"] = os.path.join(tempfile.mkdtemp(prefix="bts_ay_"), "ledger.jsonl")
    try:
        res = forge_class(ClassBrief(concept=concept), blueprint_gen=None,
                          card_gen_factory=lambda: _CardFake(), relic_gen=None, fake=True, triad=False)
    finally:
        if saved is None:
            os.environ.pop("BTS_FORGE_LEDGER", None)
        else:
            os.environ["BTS_FORGE_LEDGER"] = saved
    check(res.ok, f"fake forge succeeds for '{concept}'")
    return (res.bundle or {}).get("character") or {}


def _t_assembly() -> None:
    print("assembly: the bundle carries the flag only when it is earned:")
    ch = _fake("a molten forge sovereign")
    check(ch.get("forge_persist") is True,
          f"the offline FORGE fake carries forge_persist into the bundle, got {ch.get('forge_persist')!r}")
    ch2 = _fake("a storm channeler")
    check("forge_persist" not in ch2,
          f"a non-forge class never emits the key (a pre-v54 bundle stays byte-identical), got {sorted(ch2)}")
    src = pathlib.Path(cf.__file__).read_text(encoding="utf-8")
    check("if forge_persist and not has_income:" in src,
          "assembly drops the flag when the class ended up with no `forge` income (self-healing)")
    check('note("forge_persist dropped' in src, "the drop is narrated, never silent")


# --------------------------------------------------------------------------- 6. census
def _t_census() -> None:
    print("census reads the character-level flag:")
    on = {"kind": "class", "character": {"name": "A", "forge_persist": True}, "cards": []}
    off = {"kind": "class", "character": {"name": "B"}, "cards": []}
    check(census.census_bundle(on).forge_persist == 1, "a persist class counts 1")
    check(census.census_bundle(off).forge_persist == 0, "a normal class counts 0")
    check(census.census_bundle({"cards": []}).forge_persist == 0, "a bare card list has no character to read")
    agg = census.Census()
    agg.merge(census.census_bundle(on))
    agg.merge(census.census_bundle(off))
    check(agg.forge_persist == 1, f"merge sums the class count, got {agg.forge_persist}")
    report = census.format_report([("A", census.census_bundle(on)), ("B", census.census_bundle(off))])
    check("AY (v54): forge_persist_classes=1" in report, "the report prints the AY line")


# --------------------------------------------------------------------------- 7. codec
def _t_codec() -> None:
    print("the codec round-trips a bundle carrying the flag:")
    bundle = {"kind": "class",
              "character": {"name": "Emberkeep", "description": "d", "max_hp": 74, "max_energy": 3,
                            "orb_slots": 0, "forge_persist": True, "starting_deck": []},
              "cards": []}
    code = bts1.encode_class(json.dumps(bundle))
    check(code.startswith("BTSC.54."), f"the class code stamps v54, got {code[:12]!r}")
    payload, kind = bts1.decode(code)
    check(kind == "class", f"decodes as a class bundle, got {kind!r}")
    check(json.loads(payload)["character"]["forge_persist"] is True, "forge_persist survives the round trip")


# --------------------------------------------------------------------------- 8. contract surfaces
def _t_contract() -> None:
    print("the contract surfaces say it:")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    check("## Run-persistent Forge (a CLASS knob — forge classes only)" in vocab,
          "VOCABULARY.md has the Run-persistent Forge section")
    check("unless the class sets `forge_persist`" in vocab,
          "the `forge` op row no longer claims the counter always resets")
    check("FORGE-CLASS ONLY" in vocab and "head start" in vocab,
          "the section states the forge-class rule and that the cap makes it a head start")

    bp = cf._BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()
    check('"forge_persist": false,' in bp, "the blueprint format block shows the field")
    check('- "forge_persist": true ONLY on a FORGE class' in bp, "the RULES list carries the one-line rule")
    check(f'CARRIES up to {cf._FORGE_PERSIST_CAP} into the next one if you set "forge_persist"' in bp,
          "the FORGE archetype section pitches run persistence with the cap, in one line")
    print(f"  (rule 0.9) blueprint prompt: {len(bp):,} chars (the ONE ceiling lives in tests/test_harness_v2.py)")
    print(f"  (rule 0.9) VOCABULARY.md:    {len(vocab):,} chars")
    # The 100,000 ceiling this used to re-declare now lives once, in test_harness_v2.py: one prompt, one ceiling.


def main() -> int:
    test_version()
    _t_engine()
    _t_cap()
    _t_validation()
    _t_assembly()
    _t_census()
    _t_codec()
    _t_contract()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
