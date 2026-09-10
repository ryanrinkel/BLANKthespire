"""Phase AP — PILE MANIPULATION AND STATUS CARDS (VOCAB_GAP_REMEDIATION_PLAN Wave 3, vocab v46) — offline, no API key.

Run:  uv run python -m tests.test_phase_ap       (from generation/)
Exits nonzero on any failure. Covers the v46 additions on the generation side, in lockstep with the C#:
  1. `discard` gains `cards: random|choose` — both validate at card level; `choose` (and any non-random mode) is rejected
     inside a trigger payload; a bad mode rejects; describe reads "... card(s) of your choice." for the chosen form and the
     Phase-R "... random card(s)." text is byte-unchanged; emit carries `Cards: "choose"` only for the chosen form;
  2. `retrieve_card {pile: discard|exhaust, cards: random|choose, amount?: 1..2}` validates in every shape; a missing/bad
     pile (draw / hand), a missing/bad mode, amount 3, a card_id, two per card, and a trigger-payload form all reject;
     describe byte-matches ForgedCards.RetrieveSentence in every shape; emit carries the named Pile / Cards args; it is a
     build-around op priced: random < choose, discard < exhaust, and under a plain draw for the random form;
  3. `add_status_card {card: dazed|wound|burn, pile: hand|discard|draw, amount?: 1..3}` validates; a missing/bad kind, the
     exhaust pile, amount 4, a card_id, a BASIC carrier, two per card, and a trigger-payload form all reject; describe
     byte-matches ForgedCards.StatusCardSentence (incl. the Dazed plural); emit carries Pile / StatusCard; it is priced
     NEGATIVE (burn < wound < dazed; hand stings more than discard) so an over-statted carrier balances;
  4. the stray-field rules: `card` on another op, `cards` on block, the exhaust pile on add_card all reject;
  5. the set-level warning fires only for >2 add_status_card cards; the census / card_tokens / featured detectors see both
     ops (grave_recall / tainted_power).
Plus: the vocab stamp is >= v46; the schema / vocabulary / heuristics / exemplars / archetypes / featured menu / blueprint
prompt carry the tokens, and the duplicated gain_max_hp vocabulary row is gone.
"""
from __future__ import annotations

import json
import pathlib
import sys

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, cardgen, census, featured, paths  # noqa: E402
from btsgen.bridges import card_tokens  # noqa: E402
from btsgen.character_validator import status_card_warnings  # noqa: E402
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
    base = {"id": "ap_test", "name": "AP Test", "type": "skill", "rarity": "uncommon",
            "cost": 1, "target": "self", "source": "llm", "effects": effects}
    base["upgrade"] = {"effects": up if up is not None else effects}
    base.update(kw)
    return base


def _power(trigger, payload):
    return _card([{"op": "add_trigger", "trigger": trigger, "effects": payload}], type="power")


def _rc(pile="discard", cards="choose", amount=None, **extra):
    e = {"op": "retrieve_card", "pile": pile, "cards": cards}
    if amount is not None:
        e["amount"] = amount
    e.update(extra)
    return e


def _sc(card="wound", pile="discard", amount=None, **extra):
    e = {"op": "add_status_card", "card": card, "pile": pile}
    if amount is not None:
        e["amount"] = amount
    e.update(extra)
    return e


def _rejects(v: CardValidator, card, needle: str, label: str) -> None:
    r = v.validate(card)
    check(not r.ok and any(needle.lower() in e.lower() for e in r.errors), f"{label} is rejected: {r.errors}")


def test_version() -> None:
    print("Phase AP vocab stamp is at least v46:")
    check(bts1.VOCAB_VERSION >= 46, f"bts1.VOCAB_VERSION must be >= 46 (Phase AP), got {bts1.VOCAB_VERSION}")


def _t_discard_choose(v: CardValidator) -> None:
    print("discard: random / choose validate at card level; choose is card-only; describe + emit in lockstep:")
    for mode in ("random", "choose"):
        c = _card([{"op": "discard", "amount": 1, "cards": mode}, {"op": "draw", "amount": 1}], cost=0, rarity="common")
        r = v.validate(c)
        check(r.ok, f"discard cards:{mode} + draw validates: {r.errors}")
    legacy = _card([{"op": "discard", "amount": 2}])
    check(v.validate(legacy).ok, "the Phase-R form (no cards field) still validates")
    _rejects(v, _card([{"op": "discard", "amount": 1, "cards": "all"}]), "discard 'cards'", "discard cards:all")
    _rejects(v, _power("turn_start", [{"op": "discard", "amount": 1, "cards": "choose"}]), "", "a payload discard choose (card-only)")
    r = v.validate(_power("turn_start", [{"op": "discard", "amount": 1, "cards": "random"}]))
    check(r.ok, f"a payload discard cards:random validates (the explicit Phase-R form): {r.errors}")
    check(cardgen.describe([{"op": "discard", "amount": 1, "cards": "choose"}], "self") == "Discard {Discard} card(s) of your choice.",
          "describe (choose)")
    check(cardgen.describe([{"op": "discard", "amount": 1}], "self") == "Discard {Discard} random card(s).", "describe (random, unchanged)")
    check(cardgen.describe([{"op": "discard", "amount": 1, "cards": "random"}], "self") == "Discard {Discard} random card(s).",
          "describe (explicit random == legacy)")
    _, src = cardgen.gen_class(_card([{"op": "discard", "amount": 1, "cards": "choose"}]))
    check('new EffectSpec("discard", 1, Cards: "choose")' in src, "emit (choose) carries the named Cards arg")
    _, src = cardgen.gen_class(_card([{"op": "discard", "amount": 1, "cards": "random"}]))
    check('new EffectSpec("discard", 1)' in src and "Cards:" not in src, "emit (random) stays the plain literal")
    # the trigger fragment is unchanged (a payload discard is always random)
    d = cardgen.describe([{"op": "add_trigger", "trigger": "turn_start", "effects": [{"op": "discard", "amount": 1}]}], "self")
    check(d == "At the start of your turn, discard 1 random card(s).", f"payload fragment unchanged: {d!r}")
    sc = v._score_effect({"op": "discard", "amount": 1, "cards": "choose"})
    check(0 < sc < v._score_effect({"op": "scry", "amount": 1}), f"a chosen discard is priced under scry per card ({sc})")
    check(v._score_effect({"op": "discard", "amount": 1}) == 0.0, "a random discard stays unpriced (the archetype notes price the cost)")


def _t_retrieve(v: CardValidator) -> None:
    print("retrieve_card: every legal shape validates; every malformed shape rejects; describe/emit/pricing in lockstep:")
    for pile in ("discard", "exhaust"):
        for cards in ("random", "choose"):
            for amt in (None, 1, 2):
                r = v.validate(_card([_rc(pile, cards, amt)]))
                check(r.ok, f"retrieve_card {pile}/{cards}/{amt} validates: {r.errors}")
    exhume = _card([_rc("exhaust", "choose", 1), {"op": "exhaust"}])
    check(v.validate(exhume).ok, f"Exhume (retrieve exhaust + exhaust) validates: {v.validate(exhume).errors}")
    headbutt = _card([{"op": "damage", "amount": 9}, _rc("discard", "choose")], type="attack", target="enemy")
    check(v.validate(headbutt).ok, f"Headbutt (damage + retrieve discard) validates: {v.validate(headbutt).errors}")
    bad = [
        (_card([{"op": "retrieve_card", "cards": "choose"}]), "pile", "missing pile"),
        (_card([_rc("draw", "choose")]), "pile", "pile draw"),
        (_card([_rc("hand", "choose")]), "pile", "pile hand"),
        (_card([{"op": "retrieve_card", "pile": "discard"}]), "cards", "missing cards"),
        (_card([_rc("discard", "all")]), "cards", "cards all"),
        (_card([_rc("discard", "choose", 3)]), "amount", "amount 3"),
        (_card([_rc("discard", "choose", 1, card_id="ap_test")]), "card_id", "a card_id on retrieve_card"),
        (_card([_rc("discard", "choose"), _rc("exhaust", "random")]), "at most one", "two retrieve_card on one card"),
        (_power("turn_start", [_rc("discard", "random")]), "", "retrieve_card inside a trigger payload (card-only)"),
    ]
    for card, needle, label in bad:
        _rejects(v, card, needle, label)
    want = [
        (_rc("discard", "random"), "Return a random card from your discard pile to your hand."),
        (_rc("discard", "choose"), "Return a card of your choice from your discard pile to your hand."),
        (_rc("exhaust", "random", 2), "Return 2 random cards from your exhaust pile to your hand."),
        (_rc("exhaust", "choose", 2), "Return 2 cards of your choice from your exhaust pile to your hand."),
        (_rc("discard", "choose", 1), "Return a card of your choice from your discard pile to your hand."),
    ]
    for eff, text in want:
        d = cardgen.describe([eff], "self")
        check(d == text, f"describe {eff}: {d!r} != {text!r}")
    d = cardgen.describe([{"op": "damage", "amount": 9}, _rc("discard", "choose")], "enemy")
    check(d == "Deal {Damage} damage.\nReturn a card of your choice from your discard pile to your hand.", f"composes after a hit: {d!r}")
    _, src = cardgen.gen_class(_card([_rc("exhaust", "choose", 1)]))
    check('new EffectSpec("retrieve_card", 1, Pile: "exhaust", Cards: "choose")' in src, "emit carries Pile / Cards")
    _, src = cardgen.gen_class(_card([_rc("discard", "random")]))
    check('new EffectSpec("retrieve_card", 1, Pile: "discard", Cards: "random")' in src, "emit defaults amount to 1")
    rnd = v._score_effect(_rc("discard", "random"))
    cho = v._score_effect(_rc("discard", "choose"))
    exh = v._score_effect(_rc("exhaust", "choose"))
    two = v._score_effect(_rc("discard", "choose", 2))
    draw = v._score_effect({"op": "draw", "amount": 1})
    check(0 < rnd < draw <= cho < exh < two, f"pricing order random({rnd}) < draw({draw}) <= choose({cho}) < exhume({exh}) < two({two})")
    from btsgen import validator as _val
    check("retrieve_card" in _val._BUILD_AROUND_OPS, "retrieve_card is a build-around op (not a blank stat line)")


def _t_status_card(v: CardValidator) -> None:
    print("add_status_card: every legal shape validates; malformed / BASIC / payload shapes reject; describe/emit/pricing:")
    for kind in ("dazed", "wound", "burn"):
        for pile in ("hand", "discard", "draw"):
            for amt in (None, 1, 2, 3):
                r = v.validate(_card([{"op": "damage", "amount": 12}, _sc(kind, pile, amt)], type="attack", target="enemy"))
                check(r.ok, f"add_status_card {kind}/{pile}/{amt} validates: {r.errors}")
    bad = [
        (_card([{"op": "add_status_card", "pile": "discard"}]), "card", "missing card"),
        (_card([_sc("slimed", "discard")]), "card", "card slimed"),
        (_card([{"op": "add_status_card", "card": "wound"}]), "pile", "missing pile"),
        (_card([_sc("wound", "exhaust")]), "pile", "pile exhaust"),
        (_card([_sc("wound", "discard", 4)]), "amount", "amount 4"),
        (_card([_sc("wound", "discard", 1, card_id="ap_test")]), "card_id", "a card_id on add_status_card"),
        (_card([{"op": "damage", "amount": 9}, _sc()], rarity="basic", type="attack", target="enemy"), "BASIC", "add_status_card on a basic"),
        (_card([_sc("wound", "discard"), _sc("dazed", "draw")]), "at most one", "two add_status_card on one card"),
        (_power("turn_start", [_sc("wound", "discard")]), "", "add_status_card inside a trigger payload (card-only)"),
    ]
    for card, needle, label in bad:
        _rejects(v, card, needle, label)
    want = [
        (_sc("wound", "discard"), "Add a Wound to your discard pile."),
        (_sc("wound", "hand", 2), "Add 2 Wounds to your hand."),
        (_sc("dazed", "draw", 2), "Add 2 Dazed to your draw pile."),
        (_sc("dazed", "hand"), "Add a Dazed to your hand."),
        (_sc("burn", "hand"), "Add a Burn to your hand."),
        (_sc("burn", "discard", 3), "Add 3 Burns to your discard pile."),
    ]
    for eff, text in want:
        d = cardgen.describe([eff], "self")
        check(d == text, f"describe {eff}: {d!r} != {text!r}")
    d = cardgen.describe([{"op": "damage", "amount": 12}, _sc("wound", "discard")], "all_enemies")
    check(d == "Deal {Damage} damage to ALL enemies.\nAdd a Wound to your discard pile.", f"composes after an AoE hit: {d!r}")
    _, src = cardgen.gen_class(_card([_sc("dazed", "draw", 2)]))
    check('new EffectSpec("add_status_card", 2, Pile: "draw", StatusCard: "dazed")' in src, "emit carries Pile / StatusCard")
    _, src = cardgen.gen_class(_card([_sc("wound", "discard")]))
    check('new EffectSpec("add_status_card", 1, Pile: "discard", StatusCard: "wound")' in src, "emit defaults amount to 1")
    burn, wound, dazed = (v._score_effect(_sc(k, "discard")) for k in ("burn", "wound", "dazed"))
    hand = v._score_effect(_sc("wound", "hand"))
    two = v._score_effect(_sc("wound", "discard", 2))
    check(burn < wound < dazed < 0, f"negative, ordered burn({burn}) < wound({wound}) < dazed({dazed}) < 0")
    check(hand < wound and two < wound, f"hand ({hand}) and amount 2 ({two}) sting more than one to the discard ({wound})")
    # an over-statted carrier is balanced by the drawback: 1-cost 12 damage + a Wound scores under the same card without it
    with_w = v._score_effect({"op": "damage", "amount": 12}) + wound
    check(with_w < v._score_effect({"op": "damage", "amount": 12}), "the drawback lowers the carrier's total")


def _t_stray_fields(v: CardValidator) -> None:
    print("stray fields: 'card' / 'cards' / the exhaust pile land only on their ops:")
    _rejects(v, _card([{"op": "block", "amount": 5, "card": "wound"}]), "only applies to add_status_card", "card on block")
    _rejects(v, _card([{"op": "block", "amount": 5, "cards": "choose"}]), "only applies to upgrade_card/discard/retrieve_card", "cards on block")
    _rejects(v, _card([{"op": "add_card", "card_id": "ap_test", "pile": "exhaust"}]), "pile", "add_card to the exhaust pile")
    _rejects(v, _card([{"op": "block", "amount": 5, "pile": "exhaust"}]), "pile", "pile on block")


def _t_set_warning_and_detectors() -> None:
    print("set-level: >2 add_status_card cards warn; census / card_tokens / featured detectors see both ops:")
    a = _card([{"op": "damage", "amount": 12}, _sc()], id="a", type="attack", target="enemy")
    b = _card([{"op": "draw", "amount": 3}, _sc("dazed", "draw")], id="b")
    c = _card([{"op": "block", "amount": 12}, _sc("burn", "hand")], id="c")
    d = _card([_rc("discard", "choose")], id="d")
    check(status_card_warnings([a, b, d]) == [], "two generators: no warning")
    w = status_card_warnings([a, b, c, d])
    check(len(w) == 1 and "a, b, c" in w[0], f"three generators: one warning naming all three: {w}")
    cc = census.walk_card(_card([_rc("exhaust", "choose"), _sc("wound", "discard")]))
    check(cc.ops["retrieve_card"] == 2 and cc.ops["add_status_card"] == 2, "census counts both ops (base + upgrade)")
    toks = card_tokens(_card([_rc("exhaust", "choose"), _sc("wound", "discard")]))
    check({"retrieve_card", "add_status_card"} <= toks, f"card_tokens carry both ops: {sorted(toks)}")
    plain = census.walk_card(_card([{"op": "block", "amount": 5}]))
    gr = next(f for f in featured.FEATURED_MENU if f.id == "grave_recall")
    tp = next(f for f in featured.FEATURED_MENU if f.id == "tainted_power")
    check(gr.detect(census.walk_card(d)) and not gr.detect(plain), "grave_recall detector keys off retrieve_card")
    check(tp.detect(census.walk_card(a)) and not tp.detect(plain), "tainted_power detector keys off add_status_card")


def _t_contract() -> None:
    print("schema / vocabulary / heuristics / exemplars / archetypes / featured menu / blueprint prompt carry the tokens:")
    schema = json.loads(paths.CARD_SCHEMA.read_text(encoding="utf-8"))
    eff = schema["$defs"]["effect"]["properties"]
    trig = schema["$defs"]["triggerEffect"]["properties"]
    for op in ("retrieve_card", "add_status_card"):
        check(op in eff["op"]["enum"] and op not in trig["op"]["enum"], f"schema: {op} is a card-level op only")
    check(set(eff["pile"]["enum"]) == {"hand", "discard", "draw", "exhaust"}, "schema: the pile enum gained exhaust")
    check(set(eff["card"]["enum"]) == {"dazed", "wound", "burn"}, "schema: the card property")
    check("card" not in trig and set(trig["pile"]["enum"]) == {"hand", "discard", "draw"}, "schema: triggerEffect has no card / exhaust pile")
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    check("`retrieve_card`" in vocab and "`add_status_card`" in vocab and "Discard 1 card of your choice." in vocab, "VOCABULARY.md names both ops + the chosen discard")
    check(vocab.count("| `gain_max_hp`") == 1, "VOCABULARY.md: the duplicated gain_max_hp row is gone")
    heur = (paths.VOCABULARY.parent / "DESIGN_HEURISTICS.md").read_text(encoding="utf-8")
    check("retrieve_card" in heur and "add_status_card" in heur, "DESIGN_HEURISTICS.md prices both")
    data = pathlib.Path(paths.__file__).parent / "data"
    pool = json.loads((data / "exemplar_pool.json").read_text(encoding="utf-8"))
    by_id = {e["card"]["id"]: e for e in pool["exemplars"]}
    v = CardValidator()
    for cid in ("ex_cull_the_hand", "ex_ash_recall", "ex_reckless_haymaker"):
        check(cid in by_id and by_id[cid]["needs"] == "", f"exemplar {cid} present (needs '')")
        if cid in by_id:
            r = v.validate(dict(by_id[cid]["card"]))
            check(r.ok, f"exemplar {cid} validates: {r.errors}")
    arch = json.loads((data / "archetypes.json").read_text(encoding="utf-8"))
    ops = {a["id"]: a["vocabulary"]["ops"] for a in arch["archetypes"]}
    check("retrieve_card" in ops["madness_discard"] and "retrieve_card" in ops["exhaust_pyre"], "archetypes list retrieve_card")
    check("add_status_card" in ops["strike_tempo"] and "add_status_card" in ops["big_energy"], "archetypes list add_status_card")
    ids = {f.id for f in featured.FEATURED_MENU}
    check({"grave_recall", "tainted_power"} <= ids, "featured menu carries grave_recall + tainted_power")
    from btsgen.class_forge import _BlueprintContract
    prompt = _BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()
    check("retrieve_card" in prompt and "add_status_card" in prompt and '"cards":"choose"' in prompt, "the blueprint prompt points at the three additions")


def main() -> int:
    v = CardValidator()
    test_version()
    _t_discard_choose(v)
    _t_retrieve(v)
    _t_status_card(v)
    _t_stray_fields(v)
    _t_set_warning_and_detectors()
    _t_contract()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


# pytest entry point (re-runs main's checks in isolation for a clear failure name)
def test_phase_ap_all() -> None:
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
