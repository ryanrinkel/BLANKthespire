"""Phase AV — RE-ENABLE THE AUTONOMOUS MINION MODEL (VOCAB_GAP_REMEDIATION_PLAN Wave 4, vocab v52) — offline, no API key.

Run:  uv run python -m tests.test_phase_av       (from generation/)
Exits nonzero on any failure. Covers the v52 change in lockstep with the C#:
  1. the vocab stamp is 52 on both sides (bts1.VOCAB_VERSION <= ForgedCards.VocabVersion);
  2. the C# mirror — EffectRunner.SummonForged now RUNS spec.OnSummon (the battle cry that was parsed since K-3 but
     never fired) after LayoutPets and only on the FRESH-summon path; FindLivingSummon is name-keyed with a null
     default (name == null == "your summon" == the front-most living minion) so MaxSummons = 2 is reachable;
     ForgedCharacters parses on_nth_attack (n 2..5 + an action list); ForgedSummonPower counts the minion's own hits
     in AfterDamageGiven behind a re-entrancy guard; sacrifice_summon is in SupportedOps / Validate / Execute and
     kills through the game's own CreatureCmd.Kill; every new path carries an [AV] tag;
  3. describe is a byte-match contract: cardgen.describe() == the C# "Sacrifice your summon." sentence;
  4. the validator: sacrifice_summon under a summon context only, never alone / in a payload / on a BASIC / twice;
  5. _validate_summon_pool re-validates the K-3 fields and GATES them (<=1 autonomous minion, ethereal only on an
     autonomous one, on_nth_attack n 2..5, the tightened autonomous output caps, <=2 entries), and the v15
     _REMOVED_SUMMON_FIELDS rejection is gone;
  6. the contract wording (VOCABULARY no longer says "exactly one" / "disabled for now"; the schema enum carries
     sacrifice_summon), the sacrifice exemplar validates, app.js renders the new pool shape, and the rule-0.9
     prompt budget is printed.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen, harness_v2, paths  # noqa: E402
from btsgen import class_forge as cf  # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402

_PASS = 0
_FAIL = 0

MOD_CODE = paths.VOCABULARY.parents[1] / "BlankTheSpireCode"   # mod/contract/.. -> mod/BlankTheSpireCode
CARD_SCHEMA = paths.VOCABULARY.parent / "card.schema.json"
APP_JS = paths.VOCABULARY.parents[2] / "web" / "static" / "app.js"
EXEMPLAR_POOL = pathlib.Path(cf.__file__).parent / "data" / "exemplar_pool.json"
BP_AU = 93_623      # the blueprint prompt size Phase AU left behind (see the AU STATUS paragraph)
BP_ALLOWANCE = 1_600  # rule 0.9: "~+1,500 chars net" for the autonomous-minion paragraph


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


# --------------------------------------------------------------------------- helpers
def _card(effects, ctype="skill", rarity="common", target="self", upgrade=None):
    c = {"id": "av_t", "name": "AV", "type": ctype, "rarity": rarity, "cost": 1, "target": target,
         "effects": effects}
    if upgrade is not None:
        c["upgrade"] = {"effects": upgrade}
    return c


def _summon_validator():
    """A CardValidator with the gap-tester class's summon context (the pool names the cards may reference)."""
    return CardValidator(extra_summons={"Bone Thrall", "Carrion Hawk"})


PASSIVE = {"name": "Bone Thrall", "max_hp": 14, "description": "A raised servant."}
AUTONOMOUS = {
    "name": "Carrion Hawk", "max_hp": 6, "attackable": False,
    "moves": [{"actions": [{"op": "attack", "amount": 4}]},
              {"actions": [{"op": "attack", "amount": 3, "hits": 2}]}],
    "on_summon": [{"op": "apply_status", "status": "weak", "amount": 1}],
    "on_death": [{"op": "attack", "amount": 6, "target": "all_enemies"}],
    "on_nth_attack": {"n": 3, "actions": [{"op": "attack", "amount": 5}]},
}


# --------------------------------------------------------------------------- 1. stamps
def test_version() -> None:
    print("Phase AV vocab stamp is 52 (Python + C#):")
    check(bts1.VOCAB_VERSION >= 52, f"bts1.VOCAB_VERSION >= 52 (got {bts1.VOCAB_VERSION})")
    fc = (MOD_CODE / "Engine" / "ForgedCards.cs").read_text(encoding="utf-8")
    m = re.search(r"public const int VocabVersion = (\d+);", fc)
    check(m is not None and int(m.group(1)) == 52, f"ForgedCards.VocabVersion == 52 (got {m and m.group(1)})")
    check(m is not None and bts1.VOCAB_VERSION <= int(m.group(1)), "bts1.VOCAB_VERSION <= ForgedCards.VocabVersion")
    check("Phase AV" in fc and "sacrifice_summon" in fc,
          "ForgedCards.cs VocabVersion comment names Phase AV + the new op")
    bts1_src = pathlib.Path(bts1.__file__).read_text(encoding="utf-8")
    check("52: Phase AV" in bts1_src, "bts1.py's VOCAB_VERSION comment records the v52 (Phase AV) entry")


# --------------------------------------------------------------------------- 2. the C# mirror
def _t_summon_forged() -> None:
    print("C# mirror: SummonForged runs on_summon and is name-keyed:")
    er = (MOD_CODE / "Engine" / "EffectRunner.cs").read_text(encoding="utf-8")
    fn = er.split("internal static async Task SummonForged(", 1)[1].split("internal static async Task SacrificeSummon(", 1)[0]
    check("FindLivingSummon(player, summonClass, spec?.Name ?? name)" in fn,
          "the grow path looks up THIS NAMED minion (so a second name summons a second pet)")
    check("await SummonRunner.RunActions(cry, pet, ctx);" in fn, "on_summon is actually RUN (K-3 parsed it, never fired)")
    check("[AV] on_summon" in fn, "the on_summon [AV] tag")
    check("[AV] second summon" in fn, "the second-summon coexist [AV] tag")
    check(fn.index("Powers.ForgedSummon.LayoutPets(player);") < fn.index("RunActions(cry, pet, ctx)"),
          "the battle cry fires AFTER LayoutPets (the pet is on the board when it acts)")
    check(fn.index("await CreatureCmd.GainMaxHp(existing, hp);") < fn.index("RunActions(cry, pet, ctx)")
          and "return;" in fn.split("GainMaxHp(existing, hp);", 1)[1].split("}", 1)[0],
          "the GROW path returns before the cry (re-summoning to pump Max HP never re-triggers it)")

    print("C# mirror: FindLivingSummon keeps the name-less 'your summon' default:")
    find = er.split("internal static Creature? FindLivingSummon(", 1)[1].split("\n    }", 1)[0]
    check("Player player, int summonClass, string? name = null)" in find,
          "FindLivingSummon(player, summonClass, name = null) — the default is today's behaviour")
    check("want == null ||" in find, "a null name matches the FRONT-most living minion of the class")
    check("Trim().ToLowerInvariant()" in find, "a name match is case-insensitive + trimmed")
    # every other op stays name-less ("your summon" = the front-most living one)
    for call in ("FindLivingSummon(card.Owner, atkHost.SummonClass)",      # summon_attack
                 "FindLivingSummon(card.Owner, buffHost.SummonClass)",     # buff_summon
                 "FindLivingSummon(owner, summonClass)"):                  # heal/shield + sacrifice
        check(call in er, f"'{call}' stays name-less (your summon = the front-most living minion)")
    tr = (MOD_CODE / "Engine" / "TriggerRunner.cs").read_text(encoding="utf-8")
    check("EffectRunner.FindLivingSummon(player, k)" in tr, "the trigger payload path stays name-less too")


def _t_sacrifice() -> None:
    print("C# mirror: sacrifice_summon (SupportedOps / Validate / Execute / the death path):")
    fc = (MOD_CODE / "Engine" / "ForgedCards.cs").read_text(encoding="utf-8")
    er = (MOD_CODE / "Engine" / "EffectRunner.cs").read_text(encoding="utf-8")
    dc = (MOD_CODE / "Engine" / "DataCard.cs").read_text(encoding="utf-8")
    ops = fc.split("private static readonly HashSet<string> SupportedOps =", 1)[1].split("];", 1)[0]
    check('"sacrifice_summon"' in ops, "sacrifice_summon is in ForgedCards.SupportedOps")
    amt = fc.split("private static readonly HashSet<string> AmountOps =", 1)[1].split("];", 1)[0]
    check('"sacrifice_summon"' not in amt, "... and NOT in AmountOps (it is a flag-op)")
    trig = fc.split("private static readonly HashSet<string> TriggerOps =", 1)[1].split("];", 1)[0]
    check('"sacrifice_summon"' not in trig, "... and NOT in TriggerOps (card-only; ValidateTrigger rejects a payload one)")
    check('return "sacrifice_summon is only valid on a class card' in fc, "Validate: class-only")
    check('return "sacrifice_summon carries no amount' in fc, "Validate: no amount")
    check('return "at most one \'sacrifice_summon\' effect per card' in fc, "Validate: one per card")
    check('can\'t be a card\'s only effect' in fc, "Validate: never a card's only effect")
    check('case "sacrifice_summon": parts.Add("Sacrifice your summon.");' in fc,
          "Describe emits the byte-match sentence")
    check('case "sacrifice_summon":' in dc, "DataCard declares no card var for the flag-op")
    check('case "sacrifice_summon":' in er and "await SacrificeSummon(card.Owner, sacHost.SummonClass);" in er,
          "EffectRunner.Execute routes the op to SacrificeSummon")
    fn = er.split("internal static async Task SacrificeSummon(", 1)[1].split("\n    /// <summary>", 1)[0]
    check("await CreatureCmd.Kill(pet, true);" in fn,
          "the minion dies through the game's own CreatureCmd.Kill (force) — so Hook.AfterDeath fires the rattle")
    check("[AV] sacrifice_summon: no summon (no-op)." in fn, "no summon out => a logged no-op")
    check("[AV] sacrifice_summon '" in fn, "the sacrifice [AV] tag names the minion + its HP")
    sp = (MOD_CODE / "Powers" / "ForgedSummonPower.cs").read_text(encoding="utf-8")
    check("public override async Task AfterDeath(" in sp and "spec?.OnDeath is not { Length: > 0 }" in sp,
          "ForgedSummonPower.AfterDeath still runs the on_death rattle (what the sacrifice cashes in)")
    check("[AV] on_death rattle" in sp,
          "... and tags it (the AutoSlay proof that CreatureCmd.Kill reaches Hook.AfterDeath)")


def _t_on_nth_attack() -> None:
    print("C# mirror: on_nth_attack (spec field, parser, per-pet counter, describe):")
    ss = (MOD_CODE / "Engine" / "SummonSpec.cs").read_text(encoding="utf-8")
    check("SummonNthAttack? OnNthAttack = null" in ss, "SummonSpec gains OnNthAttack (defaulted null)")
    check("public sealed record SummonNthAttack(int N, SummonAction[] Actions);" in ss, "the SummonNthAttack record")
    fch = (MOD_CODE / "Engine" / "ForgedCharacters.cs").read_text(encoding="utf-8")
    check("private const int SummonNthMin = 2;" in fch and "private const int SummonNthMax = 5;" in fch,
          "the n band is 2..5 (mirrors class_forge._SUMMON_NTH_RANGE)")
    check('d.ContainsKey("on_nth_attack")' in fch, "TryParseSummon parses on_nth_attack")
    check("on_nth_attack: 'n' {n} out of range" in fch, "... and range-checks n")
    check("on_nth_attack: needs at least one action." in fch, "... and requires a non-empty action list")
    check("public const int MaxSummons = 2;" in fch, "MaxSummons is 2 (now reachable)")
    sp = (MOD_CODE / "Powers" / "ForgedSummonPower.cs").read_text(encoding="utf-8")
    check("public override async Task AfterDamageGiven(" in sp, "the counter rides the AfterDamageGiven hook")
    hook = sp.split("public override async Task AfterDamageGiven(", 1)[1].split("\n    // In-code tooltip", 1)[0]
    check("dealer != Owner" in hook, "only damage THIS minion deals counts")
    check("result.TotalDamage <= 0" in hook, "a 0-damage instance does not count")
    check("_hits++;" in hook and "_hits = 0;" in hook, "the counter increments and resets on the payoff")
    check("if (_firingNth" in hook and "_firingNth = true;" in hook and "finally { _firingNth = false; }" in hook,
          "the payoff's OWN attacks are excluded by the re-entrancy guard (try/finally)")
    check("[AV] on_nth_attack" in hook, "the on_nth_attack [AV] tag")
    sr = (MOD_CODE / "Engine" / "SummonRunner.cs").read_text(encoding="utf-8")
    check('body += $" Every {nth.N}th hit: {ActionsPhrase(nth.Actions)}.";' in sr,
          "SummonRunner.Describe appends the every-Nth-hit clause (after On summon / On death)")
    check(sr.index("On death:") < sr.index("Every {nth.N}th hit"), "... in that order")


# --------------------------------------------------------------------------- 3. describe byte-match
def _t_describe() -> None:
    print("describe byte-match: cardgen == ForgedCards.Describe:")
    d = cardgen.describe([{"op": "sacrifice_summon"}, {"op": "block", "amount": 12}], "self")
    check(d == "Sacrifice your summon.\nGain {Block} Block.", f"sacrifice + block sentence (got {d!r})")
    d2 = cardgen.describe([{"op": "sacrifice_summon"}, {"op": "draw", "amount": 2},
                           {"op": "gain_energy", "amount": 1}], "self")
    check(d2.splitlines()[0] == "Sacrifice your summon.", f"the sacrifice sentence leads (got {d2!r})")
    fc = (MOD_CODE / "Engine" / "ForgedCards.cs").read_text(encoding="utf-8")
    check('parts.Add("Sacrifice your summon.");' in fc, "the C# side emits the identical literal")


# --------------------------------------------------------------------------- 4. the card validator
def _t_validator() -> None:
    print("validator: sacrifice_summon is summon-class + card-only, never alone / on a BASIC / twice:")
    v = _summon_validator()
    ok = _card([{"op": "sacrifice_summon"}, {"op": "block", "amount": 12}])
    r = v.validate(dict(ok))
    check(r.ok, f"sacrifice + Block 12 validates under a summon class: {r.errors}")
    ok2 = _card([{"op": "sacrifice_summon"}, {"op": "draw", "amount": 2}, {"op": "gain_energy", "amount": 1}])
    check(v.validate(dict(ok2)).ok, f"sacrifice + draw 2 + energy validates: {v.validate(dict(ok2)).errors}")
    plain = CardValidator()
    check(not plain.validate(dict(ok)).ok, "REJECTED on a class with no summon_pool (class-only)")
    alone = _card([{"op": "sacrifice_summon"}])
    check(not v.validate(dict(alone)).ok, "REJECTED as a card's only effect (the sacrifice is the price)")
    basic = _card([{"op": "sacrifice_summon"}, {"op": "block", "amount": 12}], rarity="basic")
    check(not v.validate(dict(basic)).ok, "REJECTED on a BASIC card")
    twice = _card([{"op": "sacrifice_summon"}, {"op": "sacrifice_summon"}, {"op": "block", "amount": 12}])
    check(not v.validate(dict(twice)).ok, "REJECTED twice on one card")
    amount = _card([{"op": "sacrifice_summon", "amount": 3}, {"op": "block", "amount": 12}])
    check(not v.validate(dict(amount)).ok, "REJECTED with an amount (it is a flag-op)")
    payload = _card([{"op": "add_trigger", "trigger": "turn_end",
                      "effects": [{"op": "sacrifice_summon"}]}])
    check(not v.validate(dict(payload)).ok, "REJECTED inside an add_trigger payload (card-only)")
    # the sacrifice is a COST: it must not push the payoff half over the power ceiling
    check(v.score_card(dict(ok)) < v.score_card(_card([{"op": "block", "amount": 12}])),
          "the sacrifice scores NEGATIVE (a price), so the payoff half can be generous")
    # the op is class-only for the drop-safety pass too
    check(cf._card_uses_summons(dict(ok)), "class_forge._card_uses_summons sees sacrifice_summon")


# --------------------------------------------------------------------------- 5. the summon pool
def _t_summon_pool() -> None:
    print("_validate_summon_pool: the K-3 fields are back, gated:")
    check(not hasattr(cf, "_REMOVED_SUMMON_FIELDS"), "the v15 _REMOVED_SUMMON_FIELDS rejection is GONE")
    check(cf._MAX_SUMMONS == 2, f"_MAX_SUMMONS == 2 (got {cf._MAX_SUMMONS}) — matches ForgedCharacters.MaxSummons")
    src = pathlib.Path(cf.__file__).read_text(encoding="utf-8")
    check("_REMOVED_SUMMON_FIELDS" not in src, "... and the name is gone from class_forge.py entirely")

    good = cf._validate_summon_pool([dict(PASSIVE), dict(AUTONOMOUS)])
    check(good == [], f"a passive bodyguard + ONE autonomous ETHEREAL striker passes: {good}")
    check(cf._validate_summon_pool([dict(AUTONOMOUS)]) == [], "an autonomous minion alone passes")
    check(cf._validate_summon_pool([dict(PASSIVE)]) == [], "a lone passive minion still passes (the default shape)")

    two_auto = cf._validate_summon_pool([dict(AUTONOMOUS), {**AUTONOMOUS, "name": "Second Hawk"}])
    check(any("AUTONOMOUS" in e for e in two_auto), f"TWO autonomous minions rejected: {two_auto}")
    passive_ethereal = cf._validate_summon_pool([{**PASSIVE, "attackable": False}])
    check(any("ETHEREAL" in e for e in passive_ethereal),
          f"a PASSIVE ethereal minion rejected (it neither attacks nor shields): {passive_ethereal}")
    three = cf._validate_summon_pool([dict(PASSIVE), dict(AUTONOMOUS), {**PASSIVE, "name": "Third"}])
    check(any("at most 2 summons" in e for e in three), f"a THIRD pool entry rejected: {three}")

    nth_bad = cf._validate_summon_pool([{**AUTONOMOUS, "on_nth_attack": {"n": 7, "actions": [{"op": "attack", "amount": 4}]}}])
    check(any("on_nth_attack" in e for e in nth_bad), f"on_nth_attack n=7 rejected (2..5): {nth_bad}")
    nth_bad2 = cf._validate_summon_pool([{**AUTONOMOUS, "on_nth_attack": {"n": 1, "actions": [{"op": "attack", "amount": 4}]}}])
    check(any("on_nth_attack" in e for e in nth_bad2), "on_nth_attack n=1 rejected (that is what a move is for)")
    nth_empty = cf._validate_summon_pool([{**AUTONOMOUS, "on_nth_attack": {"n": 3, "actions": []}}])
    check(any("on_nth_attack" in e for e in nth_empty), "on_nth_attack with no actions rejected")

    print("_validate_summon_pool: the tightened autonomous output caps:")
    big = cf._validate_summon_pool([{**AUTONOMOUS, "moves": [{"actions": [{"op": "attack", "amount": 12}]}]}])
    check(any("too high" in e for e in big), f"a 12-damage move rejected (per-action cap 8): {big}")
    stacked = cf._validate_summon_pool([{**AUTONOMOUS,
                                         "moves": [{"actions": [{"op": "attack", "amount": 5},
                                                                {"op": "attack", "amount": 5}]}]}])
    check(any("total 'attack'" in e for e in stacked), f"5+5 in ONE move rejected (per-list cap 8): {stacked}")
    hits = cf._validate_summon_pool([{**AUTONOMOUS, "moves": [{"actions": [{"op": "attack", "amount": 2, "hits": 4}]}]}])
    check(any("hits" in e for e in hits), f"hits 4 rejected (cap 2): {hits}")
    fat = cf._validate_summon_pool([{**AUTONOMOUS, "max_hp": 40}])
    check(any("max_hp" in e for e in fat), f"an autonomous minion with 40 HP rejected (cap 20): {fat}")
    check(cf._validate_summon_pool([{**PASSIVE, "max_hp": 40}]) == [],
          "... but a PASSIVE bodyguard may still be fat (cap 100)")
    rattle = cf._validate_summon_pool([{**AUTONOMOUS, "on_death": [{"op": "block", "amount": 5}]}])
    check(any("on death" in e for e in rattle), f"a BLOCK on_death rejected (the minion is gone): {rattle}")
    check(cf._summon_is_autonomous(dict(AUTONOMOUS)) and not cf._summon_is_autonomous(dict(PASSIVE)),
          "_summon_is_autonomous keys on moves/actions")


# --------------------------------------------------------------------------- 6. contract / assets / budget
def _t_contract() -> None:
    print("contract: the autonomous model is documented again, the 'disabled' caveat is gone:")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    summons = vocab[vocab.index("## Forged summons"):vocab.index("## Card shape")]
    check("is disabled for now" not in vocab and "disabled for now" not in vocab,
          "VOCABULARY.md: the 'the autonomous model is disabled for now' paragraph is gone")
    check("exactly one" not in summons.lower(), "VOCABULARY.md: the summon section no longer says 'exactly one'")
    check("one or two" in summons.lower(), "... it says one or two minions")
    for token in ("`moves`", "attackable", "on_summon", "on_death", "on_nth_attack", "sacrifice_summon",
                  "ETHEREAL", "AUTONOMOUS"):
        check(token in summons, f"VOCABULARY.md Forged summons documents {token}")
    check("Carrion Hawk" in summons and '"hits":2' in summons,
          "... with a compact JSON example of an autonomous ethereal striker")
    ops_table = vocab[vocab.index("## Effect ops"):vocab.index("## Effect order")]
    check("| `sacrifice_summon` |" in ops_table, "VOCABULARY.md: sacrifice_summon has an Effect ops row")

    schema_text = CARD_SCHEMA.read_text(encoding="utf-8")
    schema = json.loads(schema_text)
    enum = schema["$defs"]["effect"]["properties"]["op"]["enum"] if "$defs" in schema else None
    if enum is None:   # tolerate either schema layout; the literal check below is the real contract
        check('"sacrifice_summon"' in schema_text, "card.schema.json: the op enum carries sacrifice_summon")
    else:
        check("sacrifice_summon" in enum, "card.schema.json: the op enum carries sacrifice_summon")
    check("sacrifice_summon" in schema_text and "SUMMON-CLASS ONLY" in schema_text,
          "card.schema.json: the op description explains the rules")
    trig_enum = re.search(r'"triggerEffect".*?"op": \{ "enum": \[(.*?)\]', schema_text, re.S)
    check(trig_enum is None or "sacrifice_summon" not in trig_enum.group(1),
          "card.schema.json: the trigger payload op enum does NOT carry it (card-only)")

    print("generation lockstep: prompt section, heuristics, archetypes, exemplar, app.js:")
    src = pathlib.Path(cf.__file__).read_text(encoding="utf-8")
    section = src[src.index("THE SUMMON POOL (optional"):src.index("STRATEGIC LINES (REQUIRED")]
    for token in ("AUTONOMOUS", "ETHEREAL", "on_nth_attack", "sacrifice_summon", "COMMANDER", "SWARM"):
        check(token in section, f"the blueprint SUMMON POOL section pitches {token}")
    check("NEVER attacks on its own" in section and "A PASSIVE minion" in section,
          "the 'never attacks on its own' rule is now CONDITIONAL on the passive minion")
    kinds = src[src.index('"summon": (\'This is a SUMMON CLASS'):]
    check("autonomous" in kinds[:400], "the summon class-kind sentence mentions the autonomous opt-in")
    registry = src[src.index('("THE SUMMON POOL", frozenset('):]
    check("sacrifice_summon" in registry[:400], "the prunable-section registry lists the op")

    heur = (paths.VOCABULARY.parent / "DESIGN_HEURISTICS.md").read_text(encoding="utf-8")
    note = heur[heur.index("<!-- archetype-note: summon_swarm -->"):heur.index("<!-- archetype-note: status_signature -->")]
    check("AUTONOMOUS" in note and "ETHEREAL" in note.upper(), "DESIGN_HEURISTICS prices the autonomous / ethereal minion")
    check("sacrifice_summon" in note, "... and the sacrifice payoff")

    pool = json.loads(EXEMPLAR_POOL.read_text(encoding="utf-8"))["exemplars"]
    sac = [e for e in pool if any(x.get("op") == "sacrifice_summon" for x in e["card"]["effects"])]
    check(len(sac) == 1, f"exactly one sacrifice_summon exemplar (got {len(sac)})")
    check(sac and sac[0]["needs"] == "summon", "... tagged needs='summon'")
    ev = harness_v2.exemplar_validator()
    bad = [e["card"]["id"] for e in pool if not ev.validate(dict(e["card"])).ok]
    check(not bad, f"every exemplar still validates under exemplar_validator: {bad}")

    js = APP_JS.read_text(encoding="utf-8")
    check('case "sacrifice_summon": return "Sacrifice your minion";' in js, "app.js labels the sacrifice card op")
    check("Ethereal (cannot be attacked)" in js, "app.js renders an ethereal minion")
    check("Each turn: " in js and "Turn ${i + 1}" in js, "app.js renders the move cycle (single + rotation)")
    for label in ("On summon: ", "On death: ", "th hit: "):
        check(label in js, f"app.js renders '{label.strip()}'")

    bp = cf._BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()
    print(f"  (rule 0.9) blueprint prompt: {len(bp):,} chars (AU left {BP_AU:,}; delta {len(bp) - BP_AU:+,})")
    print(f"  (rule 0.9) VOCABULARY.md:    {len(vocab):,} chars")
    # Repointed by Phase AW (the AU->AV precedent): an absolute size pin breaks on every later phase, so this now
    # asserts AV's paragraph is still IN the prompt; the running budget pin lives in the newest phase test.
    check("ONE AUTONOMOUS MINION" in bp, "rule 0.9: AV's autonomous-minion opt-in paragraph is still in the prompt")


def main() -> int:
    test_version()
    _t_summon_forged()
    _t_sacrifice()
    _t_on_nth_attack()
    _t_describe()
    _t_validator()
    _t_summon_pool()
    _t_contract()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
