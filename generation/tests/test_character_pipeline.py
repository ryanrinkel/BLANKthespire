"""Offline character-harness tests — no API key needed.

Run:  uv run python -m tests.test_character_pipeline     (from generation/)
Exits nonzero on any failure. Covers: the engine-contract CharacterValidator (authored classes
clean, ref-integrity/subset rejects), the BlueprintValidator design gate (the contract's own
example blueprint must pass it), and the FULL fake end-to-end pipeline: blueprint -> card set ->
starter relic -> assembled character -> quarantined bundle -> review reject cleans everything.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys

from btsgen import paths
from btsgen.character_contract import _EXAMPLE_BLUEPRINT, Brief, system_prompt
from btsgen.character_pipeline import generate_character
from btsgen.character_validator import (BlueprintValidator, CharacterValidator,
                                         combo_loop_warnings, debuff_monotony_warnings,
                                         identity_overlap_warnings, signature_mechanics)
from btsgen.cli_character_generate import main as gen_main
from btsgen.cli_character_review import main as review_main
from btsgen.validator import CardValidator

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


def _character(cid: str) -> dict:
    return json.loads((paths.CHARACTERS_DIR / f"{cid}.json").read_text())


# --------------------------------------------------------------- CharacterValidator
def test_authored_characters_validate(v: CharacterValidator) -> None:
    print("authored characters validate clean:")
    files = sorted(paths.CHARACTERS_DIR.glob("*.json"))
    check(len(files) >= 2, f"expected >=2 authored characters, found {len(files)}")
    for f in files:
        res = v.validate(json.loads(f.read_text()))
        check(res.ok, f"{f.name} should be valid: {res.errors}")
        check(not res.warnings, f"{f.name} unexpectedly warned: {res.warnings}")


def test_character_rejects(v: CharacterValidator) -> None:
    print("character hard-rejects:")
    base = _character("ironclad")

    bad = dict(base, starting_relic="no_such_relic")
    check(not v.validate(bad).ok, "unknown starting_relic must reject")

    bad = dict(base, starting_deck=base["starting_deck"] + ["no_such_card"])
    check(not v.validate(bad).ok, "unknown deck card must reject")

    bad = dict(base, signature_cards=["anger"])  # exists, but not in the starting deck
    check(not v.validate(bad).ok, "signature not in starting_deck must reject")

    bad = dict(base); bad.pop("max_hp")
    check(not v.validate(bad).ok, "missing max_hp must reject (schema)")

    bad = dict(base, id="Bad Id")
    check(not v.validate(bad).ok, "non-snake id must reject (schema)")


def test_character_warnings(v: CharacterValidator) -> None:
    print("character band warnings:")
    base = _character("ironclad")
    res = v.validate(dict(base, max_hp=200))
    check(res.ok and any("60..95" in w for w in res.warnings), "hp 200 should warn, not reject")
    res = v.validate(dict(base, starting_deck=["strike", "defend", "bash"], signature_cards=["bash"]))
    check(res.ok and any("deck" in w for w in res.warnings), "3-card deck should warn")


# --------------------------------------------------------------- BlueprintValidator
def test_blueprint_example_passes(bv: BlueprintValidator) -> None:
    print("the contract's own example blueprint passes the gate:")
    res = bv.validate(_EXAMPLE_BLUEPRINT)
    check(res.ok, f"example blueprint must validate: {res.errors}")
    # its id is the authored armor_dillo, so the only acceptable warning is the rename notice
    check(all("already exists" in w for w in res.warnings),
          f"example blueprint warnings should only be the rename notice: {res.warnings}")


def test_blueprint_rejects(bv: BlueprintValidator) -> None:
    print("blueprint hard-rejects:")
    def bp(**over):
        d = json.loads(json.dumps(_EXAMPLE_BLUEPRINT))
        d.update(over)
        return d

    check(not bv.validate("nope").ok, "non-object must reject")
    check(not bv.validate(bp(id="Bad Id")).ok, "non-snake id must reject")
    check(not bv.validate(bp(max_hp=300)).ok, "hp 300 must reject")
    check(not bv.validate(bp(archetypes=_EXAMPLE_BLUEPRINT["archetypes"][:1])).ok,
          "1 archetype must reject")

    d = bp()
    d["cards"] = [c for c in d["cards"] if c["role"] != "basic_attack"]
    check(not bv.validate(d).ok, "missing basic_attack must reject")

    d = bp()
    d["cards"][4]["archetype"] = "no_such_archetype"
    check(not bv.validate(d).ok, "pool card with unknown archetype must reject")

    d = bp()
    d["cards"][2]["deck_count"] = 3  # signature must be exactly 1
    check(not bv.validate(d).ok, "signature deck_count 3 must reject")

    d = bp()
    d["cards"][4]["rarity"] = "basic"  # pool can't be basic rarity
    check(not bv.validate(d).ok, "pool card rarity basic must reject")

    d = bp()
    d["archetypes"][0].pop("kind")
    check(not bv.validate(d).ok, "archetype without a kind must reject")

    d = bp()
    d["archetypes"][0]["kind"] = "novel"
    d["archetypes"][1]["kind"] = "novel"
    check(not bv.validate(d).ok, "two novel archetypes must reject (need one classic)")

    res = bv.validate(bp(max_hp=110))
    check(res.ok and any("60..95" in w for w in res.warnings), "hp 110 should warn, not reject")


# --------------------------------------------------------------- mechanic identity
def test_identity_ownership() -> None:
    print("signature-mechanic ownership + overlap warnings:")
    owned = signature_mechanics()
    check(owned.get("op:fuse") == "armor_dillo", f"fuse must be owned by armor_dillo: {owned}")
    check(owned.get("status:burrowed") == "armor_dillo", "burrowed must be owned by armor_dillo")
    check(owned.get("status:armor") == "armor_dillo", "armor must be owned by armor_dillo")
    check("op:damage" not in owned and "status:weak" not in owned,
          "generic currency must never be owned")
    check(all(ch != "ironclad" for ch in owned.values()),
          f"the vanilla baseline class owns nothing: {owned}")

    # the Frost Warden incident, reduced: a frosty fuse card warns and names the owner
    frosty = {"id": "icicle", "effects": [
        {"op": "fuse", "turns": 1, "effects": [{"op": "damage", "amount": 6}]}]}
    plain = {"id": "frost_bolt", "effects": [
        {"op": "damage", "amount": 7},
        {"op": "apply_status", "status": "vulnerable", "amount": 1}]}
    warns = identity_overlap_warnings([frosty, plain])
    check(len(warns) == 1, f"exactly one identity warning expected: {warns}")
    check(bool(warns) and "fuse" in warns[0] and "armor_dillo" in warns[0] and "icicle" in warns[0],
          f"warning must name the mechanic, its owner, and the cards: {warns}")
    check(not identity_overlap_warnings([plain]), "a generic-currency set must not warn")


def test_debuff_monotony() -> None:
    print("set-level vulnerable/weak monotony warning:")
    def card(i: int, status: str | None = None) -> dict:
        eff = [{"op": "damage", "amount": 6}]
        if status:
            eff.append({"op": "apply_status", "status": status, "amount": 2})
        return {"id": f"c{i}", "rarity": "common", "effects": eff}
    spam = [card(i, "vulnerable" if i % 2 else "weak") for i in range(6)]
    warns = debuff_monotony_warnings(spam)
    check(len(warns) == 1 and "6/6" in warns[0], f"an all-debuff set must warn: {warns}")
    clean = [card(i) for i in range(5)] + [card(9, "weak")]
    check(not debuff_monotony_warnings(clean), "an occasional debuff must not warn")
    check(not debuff_monotony_warnings(spam[:3]), "tiny sets are not judged")
    basics = [dict(c, rarity="basic") for c in spam]
    check(not debuff_monotony_warnings(basics), "basics don't count toward monotony")


def test_prompt_creativity_guard() -> None:
    print("blueprint prompt demands one novel + one classic archetype, no debuff spam:")
    sp = system_prompt()
    check("CLASS FANTASY & CREATIVITY" in sp, "prompt must carry the creativity section")
    check('"kind": "novel"' in sp and '"kind": "classic"' in sp,
          "prompt must define the novel/classic archetype kinds")
    check("DEBUFF MONOTONY" in sp, "prompt must carry the vulnerable/weak anti-monotony rule")
    check(_EXAMPLE_BLUEPRINT["archetypes"][0].get("kind") in ("novel", "classic")
          and _EXAMPLE_BLUEPRINT["archetypes"][0].get("kind")
          != _EXAMPLE_BLUEPRINT["archetypes"][1].get("kind"),
          "the example blueprint must model one kind of each")


def test_prompt_identity_guard() -> None:
    print("blueprint prompt carries the identity guard, not the fuse nudge:")
    sp = system_prompt()
    check("MECHANICAL IDENTITY" in sp, "prompt must state the identity rule")
    check("fuse (op)" in sp and "armor_dillo" in sp, "prompt must list the live owned-mechanics map")
    check("fuse for delayed bursts" not in sp, "the freeze->fuse translation nudge must be gone")
    check("ONLY to anchor the format" in sp, "the example blueprint must be marked format-only")


def test_combo_loops() -> None:
    print("set-level two-card free loop warning:")
    def c(cid: str, other: str, cost: int = 0, exhaust: bool = False) -> dict:
        return {"id": cid, "cost": cost, "exhaust": exhaust,
                "effects": [{"op": "add_card", "card_id": other, "pile": "hand"}]}
    warns = combo_loop_warnings([c("ping", "pong"), c("pong", "ping")])
    check(len(warns) == 1 and "ping" in warns[0] and "pong" in warns[0],
          f"a free A<->B loop must warn exactly once: {warns}")
    check(not combo_loop_warnings([c("ping", "pong", 2), c("pong", "ping", 2)]),
          "an expensive pair loop is allowed")
    check(not combo_loop_warnings([c("ping", "pong", 0, True), c("pong", "ping")]),
          "exhaust on either end breaks the loop")
    check(not combo_loop_warnings([c("a1", "b1"), c("b1", "c1"), c("c1", "a1")]),
          "3-card cycles are the earned version; never flagged")


def test_prompt_loop_guard() -> None:
    print("card and blueprint prompts carry the loop-discipline rule:")
    from btsgen.contract import system_prompt as card_system_prompt
    for name, sp in (("card", card_system_prompt()), ("blueprint", system_prompt())):
        check("LOOP DISCIPLINE" in sp, f"{name} prompt must carry the loop rule")
        check("THREE distinct cards" in sp, f"{name} prompt must state the 3-card rule")


def test_prompt_reprint_guard() -> None:
    print("card and blueprint prompts carry the existing-pool reprint discipline:")
    from btsgen.contract import system_prompt as card_system_prompt
    for name, sp in (("card", card_system_prompt()), ("blueprint", system_prompt())):
        check("EXISTING CARD POOL" in sp, f"{name} prompt must embed the pool catalog")
        check("- inflame (power, self, 1E, uncommon)" in sp,
              f"{name} prompt catalog must list inflame's effect line")
    check("wastes its slot" in system_prompt(),
          "blueprint prompt must warn that planning a reprint brief wastes the slot")


# --------------------------------------------------------------- fake end-to-end
def _reject(cid: str) -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        review_main(["reject", cid])


def test_fake_pipeline_end_to_end() -> None:
    print("fake pipeline end-to-end (generate -> bundle -> review -> reject):")
    made_ids: list[str] = []
    try:
        res = generate_character(Brief(concept="an offline test class", pool_cards_per_archetype=2),
                                 fake=True)
        check(res.ok, f"fake pipeline must succeed: {res.log[-3:]}")
        if not res.ok:
            return
        ch = res.character
        made_ids.append(ch["id"])
        check(ch["id"].startswith("test_subject"), f"unexpected class id {ch['id']}")
        check(len(res.card_ids) == 8, f"expected 8 set cards (4 deck + 2x2 pool), got {len(res.card_ids)}")
        check(len(ch["starting_deck"]) == 10, f"deck should be 10, got {len(ch['starting_deck'])}")
        check(len(ch["signature_cards"]) == 2, "expected 2 signatures")
        check(all(s in ch["starting_deck"] for s in ch["signature_cards"]), "signatures must be in deck")
        check(not res.skipped, f"nothing should be skipped: {res.skipped}")

        # the bundle is on disk, validated, tagged
        char_path = paths.GENERATED_CHARACTERS_DIR / f"{ch['id']}.json"
        meta_path = paths.GENERATED_CHARACTERS_DIR / f"{ch['id']}.meta.json"
        check(char_path.exists() and meta_path.exists(), "character + meta must be quarantined")
        meta = json.loads(meta_path.read_text())
        check(meta["cards"] == res.card_ids and meta["relic"] == res.relic_id,
              "meta manifest must list the bundle")
        cv = CardValidator()
        for cid in res.card_ids:
            p = paths.GENERATED_DIR / f"{cid}.json"
            check(p.exists(), f"set card {cid} must be quarantined")
            card = json.loads(p.read_text())
            check(card.get("character") == ch["id"], f"{cid} must be tagged character={ch['id']}")
            check(cv.validate(card).ok, f"{cid} must validate")
        relic = json.loads((paths.GENERATED_RELICS_DIR / f"{res.relic_id}.json").read_text())
        check(relic["tier"] == "starter" and relic["pool"] == "starter",
              "starter relic must be tier/pool starter")
        check(CharacterValidator().validate(ch).ok, "assembled character must validate")

        # second run: ids must uniquify, not clobber
        res2 = generate_character(Brief(concept="another", pool_cards_per_archetype=2), fake=True)
        check(res2.ok, "second fake run must succeed")
        if res2.ok:
            made_ids.append(res2.character["id"])
            check(res2.character["id"] == "test_subject_2",
                  f"second class id should uniquify, got {res2.character['id']}")
            check(not set(res2.card_ids) & set(res.card_ids), "set card ids must not collide")

        # review list sees both; reject removes a bundle completely
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            review_main(["list"])
        check("test_subject" in buf.getvalue(), "review list must show the bundle")
        _reject(ch["id"])
        check(not char_path.exists(), "reject must remove the character")
        check(not any((paths.GENERATED_DIR / f"{c}.json").exists() for c in res.card_ids),
              "reject must remove the bundle's cards")
        check(not (paths.GENERATED_RELICS_DIR / f"{res.relic_id}.json").exists(),
              "reject must remove the bundle's relic")
        made_ids.remove(ch["id"])
    finally:
        for cid in made_ids:
            _reject(cid)


def test_fake_cli_smoke() -> None:
    print("CLI smoke (--fake):")
    buf = io.StringIO()
    cid = None
    try:
        with contextlib.redirect_stdout(buf):
            rc = gen_main(["--concept", "cli smoke class", "--fake", "--pool-cards", "2"])
        check(rc == 0, "generate CLI must exit 0")
        lines = [l for l in buf.getvalue().splitlines() if l.startswith("BUNDLE ")]
        check(len(lines) == 1, "CLI must print exactly one BUNDLE line")
        if lines:
            cid = lines[0].split(" ", 1)[1].strip()
            check((paths.GENERATED_CHARACTERS_DIR / f"{cid}.json").exists(),
                  "BUNDLE id must point at a quarantined character")
    finally:
        if cid:
            _reject(cid)
    check(gen_main(["--concept", "   ", "--fake"]) == 1, "blank concept must exit 1")


def main() -> int:
    cv = CharacterValidator()
    bv = BlueprintValidator()
    test_authored_characters_validate(cv)
    test_character_rejects(cv)
    test_character_warnings(cv)
    test_blueprint_example_passes(bv)
    test_blueprint_rejects(bv)
    test_identity_ownership()
    test_debuff_monotony()
    test_prompt_creativity_guard()
    test_prompt_identity_guard()
    test_prompt_reprint_guard()
    test_combo_loops()
    test_prompt_loop_guard()
    test_fake_pipeline_end_to_end()
    test_fake_cli_smoke()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
