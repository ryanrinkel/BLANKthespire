"""Phase AU — on_discard FIRES ON BASE-GAME DISCARDS (VOCAB_GAP_REMEDIATION_PLAN W0.2 Issue B, vocab v51) — offline, no API key.

Run:  uv run python -m tests.test_phase_au       (from generation/)
Exits nonzero on any failure. Covers the v51 change in lockstep with the C#:
  1. the vocab stamp is 51 on both sides (bts1.VOCAB_VERSION <= ForgedCards.VocabVersion);
  2. the C# mirror — the mechanism is the GAME's hook, not a Harmony patch: DataCard overrides
     AbstractModel.AfterCardDiscarded (CardCmd.Discard -> Hook.AfterCardDiscarded reaches every card in every pile),
     filters on `card == this`, and routes to the Phase-R FireOnDiscard; the no-cascade guard moved INTO DataCard and
     wraps the TriggerRunner.Run payload; EffectRunner's FireOnDiscardFor is GONE and DiscardRandom / DiscardChoose /
     Scry no longer fire on_discard by hand (that would double-fire) but do bracket their CardCmd.Discard with
     ModDiscardDepth for the tag's source= attribution; the new [AU] tag and the retained [R] line;
  3. no describe change: "Whenever this card is discarded, gain 6 Block." is still the byte-match sentence, the
     validator still accepts an on_discard card and still rejects once_per_combat on it (card-latent, no power);
  4. the contract wording: VOCABULARY.md's W0.2-B caveat is gone, card.schema.json says base-game discards count,
     neither says "only THIS class"; rule-0.9 prompt budget printed (AU REMOVES text, so it shrinks).
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
from btsgen.validator import CardValidator  # noqa: E402

_PASS = 0
_FAIL = 0

MOD_CODE = paths.VOCABULARY.parents[1] / "BlankTheSpireCode"   # mod/contract/.. -> mod/BlankTheSpireCode
CARD_SCHEMA = paths.VOCABULARY.parent / "card.schema.json"
BP_AT = 93_750   # the blueprint prompt size Phase AT left behind (see the AT STATUS paragraph)


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _card(effects, ctype="skill", target="self"):
    return {"id": "au_t", "name": "AU", "type": ctype, "rarity": "common", "cost": 1, "target": target,
            "effects": effects}


def _reflex(payload, **flags):
    t = {"op": "add_trigger", "trigger": "on_discard", "effects": payload}
    t.update(flags)
    return [t]


def test_version() -> None:
    print("Phase AU vocab stamp is 51 (Python + C#):")
    check(bts1.VOCAB_VERSION >= 51, f"bts1.VOCAB_VERSION >= 51 (got {bts1.VOCAB_VERSION})")
    fc = (MOD_CODE / "Engine" / "ForgedCards.cs").read_text(encoding="utf-8")
    m = re.search(r"public const int VocabVersion = (\d+);", fc)
    check(m is not None and int(m.group(1)) == 51, f"ForgedCards.VocabVersion == 51 (got {m and m.group(1)})")
    check(m is not None and bts1.VOCAB_VERSION <= int(m.group(1)), "bts1.VOCAB_VERSION <= ForgedCards.VocabVersion")
    check("Phase AU" in fc and "AfterCardDiscarded" in fc,
          "ForgedCards.cs VocabVersion comment names Phase AU + the AfterCardDiscarded hook")
    bts1_src = pathlib.Path(bts1.__file__).read_text(encoding="utf-8")
    check("51: Phase AU" in bts1_src, "bts1.py's VOCAB_VERSION comment records the v51 (Phase AU) entry")


def _t_datacard_hook() -> None:
    print("C# mirror: DataCard overrides the GAME's AfterCardDiscarded hook (no Harmony patch):")
    dc = (MOD_CODE / "Engine" / "DataCard.cs").read_text(encoding="utf-8")
    check("public override Task AfterCardDiscarded(PlayerChoiceContext choiceContext, CardModel card)" in dc,
          "DataCard overrides AfterCardDiscarded(PlayerChoiceContext, CardModel)")
    hook = dc.split("AfterCardDiscarded(PlayerChoiceContext choiceContext, CardModel card)", 1)[1].split("</summary>", 1)[0]
    hook = hook.split("internal async Task FireOnDiscard", 1)[0]
    check("card == this" in hook, "the hook filters to THIS card (it reaches every card in every pile)")
    check("FireOnDiscard(choiceContext)" in hook, "... and routes to the Phase-R FireOnDiscard payload runner")
    check("Owner != null" in hook, "... Owner null-safe (FireOnDiscard reads Owner.Creature.CombatState)")
    check("Task.CompletedTask" in hook, "... and is a no-op for every other card")
    # The hook is the mechanism, so no Harmony patch was minted for it.
    check(not (MOD_CODE / "Engine" / "DiscardHookPatch.cs").exists(), "no Harmony patch file was added for AU")
    check("HarmonyPatch" not in dc, "DataCard stays patch-free (it IS a CardModel; the hook is a virtual)")

    print("C# mirror: the no-cascade guard moved into DataCard and wraps the payload:")
    check("private static bool _firingOnDiscard;" in dc, "the static guard now lives in DataCard")
    fire = dc.split("internal async Task FireOnDiscard", 1)[1]
    check("if (_firingOnDiscard) return;" in fire, "FireOnDiscard bails when already inside an on_discard payload")
    check("_firingOnDiscard = true;" in fire and "finally { _firingOnDiscard = false; }" in fire,
          "the guard is set/cleared around the payload in a try/finally")
    body = fire.split("_firingOnDiscard = true;", 1)[1]
    check("await TriggerRunner.Run(t, Owner, ctx);" in body, "the guard wraps the TriggerRunner.Run payload")
    check("_onDiscardLastRound" in fire, "the once_per_turn round gate (Phase R) is unchanged")

    print("C# mirror: the [AU] tag with source= attribution, and the [R] line retained:")
    check("[AU] on_discard via Hook.AfterCardDiscarded" in fire, "the new [AU] tag string")
    check("EffectRunner.ModDiscardDepth > 0 ? \"mod-op\" : \"base-game\"" in fire,
          "source= is mod-op when inside one of our own discard ops, base-game otherwise")
    check("[R] on_discard fired" in fire, "the [R] line is retained (older tests / logs grep it)")
    check(fire.index("[AU] on_discard") < fire.index("[R] on_discard fired"), "[AU] is logged BEFORE [R]")


def _t_effectrunner() -> None:
    print("C# mirror: EffectRunner stopped firing on_discard itself (no double-fire):")
    er = (MOD_CODE / "Engine" / "EffectRunner.cs").read_text(encoding="utf-8")
    check("FireOnDiscardFor" not in er, "EffectRunner.FireOnDiscardFor is deleted (the hook does the work)")
    check("_firingOnDiscard" not in er, "the guard no longer lives in EffectRunner")
    check("internal static int ModDiscardDepth;" in er, "ModDiscardDepth (tag attribution only) is declared")
    for name, end in (("DiscardRandom", "internal static async Task DiscardChoose"),
                      ("DiscardChoose", "private static bool Retrievable"),
                      ("Scry", "internal static void UpgradeInHand")):
        fn = er.split(f"internal static async Task {name}(", 1)[1].split(end, 1)[0]
        check("await CardCmd.Discard(ctx," in fn, f"{name} still discards through CardCmd.Discard (-> the game hook)")
        check("dc.FireOnDiscard" not in fn and "FireOnDiscardFor" not in fn,
              f"{name} no longer fires on_discard by hand")
        check("ModDiscardDepth++;" in fn and "finally { ModDiscardDepth--; }" in fn,
              f"{name} brackets its CardCmd.Discard with ModDiscardDepth (try/finally)")
    # The contract note lives in the code too: turn-end cleanup is a different path.
    dc = (MOD_CODE / "Engine" / "DataCard.cs").read_text(encoding="utf-8")
    check("AfterFlush" in dc, "DataCard documents why turn-end cleanup (CardPileCmd.Add + Hook.AfterFlush) never fires")
    check("Gambling Chip" in dc or "Gambler's Brew" in dc, "DataCard names the base-game discard sources")


def _t_generation() -> None:
    print("generation: no describe change, validator rules unchanged:")
    d = cardgen.describe(_reflex([{"op": "block", "amount": 6}]), "self")
    check(d == "Whenever this card is discarded, gain 6 Block.", f"byte-match sentence unchanged (got {d!r})")
    fc = (MOD_CODE / "Engine" / "ForgedCards.cs").read_text(encoding="utf-8")
    check('"on_discard"      => "Whenever this card is discarded"' in fc, "C# TriggerFragment unchanged (byte-match contract)")
    v = CardValidator()
    check(v.validate(_card(_reflex([{"op": "block", "amount": 6}]))).ok,
          f"on_discard Reflex card still validates: {v.validate(_card(_reflex([{'op': 'block', 'amount': 6}]))).errors}")
    opt = _card(_reflex([{"op": "draw", "amount": 1}], once_per_turn=True))
    check(v.validate(opt).ok, f"on_discard + once_per_turn still validates: {v.validate(opt).errors}")
    opc = _card(_reflex([{"op": "draw", "amount": 1}], once_per_combat=True))
    check(not v.validate(opc).ok, "once_per_combat is still REJECTED on the card-latent on_discard (no power hosts it)")
    # the enablers that now also traverse the game hook
    check(v.validate(_card([{"op": "discard", "amount": 1}, {"op": "draw", "amount": 1}])).ok, "discard random still validates")
    check(v.validate(_card([{"op": "discard", "amount": 1, "cards": "choose"}, {"op": "draw", "amount": 1}])).ok,
          "discard choose still validates")
    check(v.validate(_card([{"op": "scry", "amount": 3}])).ok, "scry still validates")
    # no new token was minted on either side
    check('"on_pet_discard"' not in fc and '"on_any_discard"' not in fc, "no new trigger token (on_discard is the spelling)")


def _t_contract() -> None:
    print("contract: the W0.2-B caveat is gone, base-game discards count:")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    trig = vocab[vocab.index("## Triggers"):]
    check("fires ONLY from THIS class's own" not in vocab, "VOCABULARY.md: the 'only THIS class' caveat is gone")
    check("do NOT fire it" not in vocab, "VOCABULARY.md: the 'base-game discards do NOT fire it' sentence is gone")
    check("base-game discard sources (relics, potions, other-class cards)" in trig,
          "VOCABULARY.md: base-game discard sources DO fire on_discard")
    check("end-of-turn hand cleanup" in trig and "**NOT** fire when the card is played" in trig,
          "VOCABULARY.md: play / end-of-turn cleanup still do not fire it")
    check("enemy-forced" not in vocab and "relic/enemy" not in vocab,
          "VOCABULARY.md never says 'enemy' (no monster calls CardCmd.Discard in this build)")
    schema_text = CARD_SCHEMA.read_text(encoding="utf-8")
    json.loads(schema_text)  # still valid JSON after the wording edit
    check("base-game discard sources (relics, potions, other-class cards)" in schema_text,
          "card.schema.json: the trigger description counts base-game discards")
    check("NOT when played and NOT at turn-end hand cleanup" in schema_text,
          "card.schema.json: play / turn-end cleanup still excluded")
    check("only THIS class" not in schema_text and "only THIS class" not in vocab,
          "neither contract file says 'only THIS class'")
    # the blueprint prompt block needed no 'only this class' fix either
    cfs = pathlib.Path(cf.__file__).read_text(encoding="utf-8")
    churn = cfs.split("DISCARD / HAND-CHURN", 1)[1].split("CORRUPTION (", 1)[0]
    check("only THIS class" not in churn and "do NOT fire it" not in churn,
          "class_forge.py's DISCARD/HAND-CHURN block never said 'only this class'")
    check("DISCARDED BY AN EFFECT (not when played, not at end-of-turn cleanup)" in churn,
          "... and still states the two things that DON'T fire it")
    bp = cf._BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()
    print(f"  (rule 0.9) blueprint prompt: {len(bp):,} chars (AT left {BP_AT:,}; AU removes the caveat)")
    check(len(bp) <= BP_AT, f"rule 0.9: AU shrinks the prompt (got {len(bp):,}, AT was {BP_AT:,})")


def main() -> int:
    test_version()
    _t_datacard_hook()
    _t_effectrunner()
    _t_generation()
    _t_contract()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
