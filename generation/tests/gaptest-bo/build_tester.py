"""Phase BO Gap Tester — self-routing recursion, put-back, draw-pile tutor, on_shuffle, grant_keyword (vocab v66,
gaps #74 / #75).

    cd generation
    uv run python tests/gaptest-bo/build_tester.py --validate-only   # validate the cards only (no game dir touched)
    uv run python tests/gaptest-bo/build_tester.py                   # validates, backs up slot 04, stages the tester there
    uv run python tests/gaptest-bo/build_tester.py --remove          # restores whatever slot 04 held before
    uv run btsgen-autoslay-smoke --seeds GAPTESTBO1 GAPTESTBO2 --character class4 --relic auto --timeout 900

The deck (slot 04, a normal class, a THIN 19-card deck so the draw pile reshuffles every few turns; attack-leaning so
fights end):
  * Particle Wall      — 9 Block, return_to_hand (cost 1)                 [BO] return_to_hand 'Particle Wall'
  * Bolas              — 3 damage, return_next_turn (0-cost rare attack)  [BO] return_next_turn 'Bolas' <- Discard
  * Make It So         — 6 damage, to_draw_top (named for the plan; the base Make It So is a Skill-count return —
                         this is the Rebound shape on the card itself)     [BO] to_draw_top 'Make It So'
  * Headbutt           — 9 damage, put_back from discard                  [BO] put_back discard '<card>' -> draw top
  * Thinking Ahead     — draw 2, put_back from hand                       [BO] put_back hand '<card>' -> draw top
  * Secret Weapon      — retrieve_card pile draw, choose, card_type attack [BO] retrieve draw [attack] '<card>'
  * Rummage            — 5 Block, retrieve_card pile draw, random Skill   [BO] retrieve draw [skill] '<card>'
  * Deep Kindling      — 8 Block, exhaust_card pile draw, choose 1; Exhaust [BO] exhaust_card draw '<card>'
  * Snap               — 7 damage, grant_keyword sly                      [BO] grant_keyword sly -> '<card>'
  * Steady Grip        — 6 Block, grant_keyword retain                    [BO] grant_keyword retain -> '<card>'
  * Fading Ink         — draw 1, grant_keyword ethereal                   [BO] grant_keyword ethereal -> '<card>'
  * Turning Tide (Power) — on_shuffle: gain 4 Block                       [BO] on_shuffle fired (+ [H4] reactive
                                                                           trigger 'on_shuffle' fired)
  * Reboot             — shuffle_hand + draw 3 (Reboot-lite, 0-cost rare)  [BO] shuffle_hand <n> cards (and an
                                                                           on_shuffle fire right after it)
  * Twin Jab           — a plain non-basic attack (the merchant stall needs >= 3 non-basic Attacks + Skills + 1 Power)
  * War Drum (Power)   — turn_start: gain 1 Strength (smoke iteration: so a long boss fight ends; GAPTESTBO1's passing run
                         predates it — GAPTESTBO2 twice hit AutoSlay's 100-turn cap against Knowledge Demon without it)

Picker proof (rule 0.4/0.5): AutoSlay's selector logs "Auto-selected N card(s) for selection prompt" whenever a picker
had more than one candidate — Headbutt / Thinking Ahead (put_back), Secret Weapon (retrieve draw choose), Deep Kindling
(exhaust draw choose), Snap / Steady Grip / Fading Ink (grant_keyword). The custom prompts come from DataCard's CardLoc
ExtraLoc keys (boPutBackPrompt / boGrantKeywordPrompt / boRetrievePrompt); a missing key would fall back to a stock
prompt, never throw.

What the smoke CAN'T prove: AutoSlay never pays energy, so a return_to_hand card's "infinite loop" guard is offline-only
(the validator rule: cost 1+, no draw / gain_energy on the card; the bot tries each instance once per turn anyway).

Tags: [BO] return_to_hand '<card>' · [BO] to_draw_top '<card>' · [BO] return_next_turn '<card>' <- <pile> ·
[BO] put_back <from> '<card>' -> draw top · [BO] retrieve draw [<type>] '<card>' · [BO] exhaust_card draw '<card>' ·
[BO] on_shuffle fired · [BO] grant_keyword <kw> -> '<card>' · [BO] shuffle_hand <n> cards.

Pass bar (plan rule 0.3): across the two seeds EVERY tag above fires at least once (put_back for both hand and discard,
grant_keyword for sly / retain / ethereal, retrieve draw for attack and skill), "Auto-selected" appears, plus 0 mod
exceptions, no BlankTheSpire frame in a stall stack, 0 "Localization formatting error". Each new DataCard override has
its own tag (GetResultPileTypeForCardPlay / ModifyCardPlayResultPileTypeAndPosition / BeforeHandDraw) and
ForgedTriggerPower.AfterShuffle has [BO] on_shuffle fired — a hook that never fires is the failure mode (Phase BD).
The saved tag greps live next to this file as godot_BO_tags_<SEED>.txt (TEST_AUDIT_2026-10 §7).
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from btsgen.class_forge import point_btsgen_at_mod_contract  # noqa: E402

point_btsgen_at_mod_contract()
from btsgen import game_paths  # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402

SLOT = 4
ROOT = game_paths.game_user_dir() / "forged" / "characters"
BAK_SUFFIX = ".bogaptestbak"
CH = "bo_gap_tester"
GAPTEST_ONLY: set[str] = set()  # every BO card is a real contract card


def card(cid, name, ctype, rarity, cost, target, effects, upgrade=None, up_cost=None):
    c = {"id": cid, "name": name, "type": ctype, "rarity": rarity, "cost": cost, "target": target,
         "source": "llm", "character": CH, "effects": effects, "upgrade": {"effects": upgrade or effects}}
    if up_cost is not None:
        c["upgrade"]["cost"] = up_cost
    return c


def gk(kw, ck=None):
    e = {"op": "grant_keyword", "keyword": kw, "cards": "choose"}
    if ck:
        e["card_type"] = ck
    return e


def put_back(frm):
    return {"op": "put_back", "from": frm, "cards": "choose"}


def tutor(cards, ck):
    return {"op": "retrieve_card", "pile": "draw", "cards": cards, "card_type": ck}


CARDS = [
    card("bo_strike", "Strike", "attack", "basic", 1, "enemy", [{"op": "damage", "amount": 6}], [{"op": "damage", "amount": 9}]),
    card("bo_defend", "Defend", "skill", "basic", 1, "self", [{"op": "block", "amount": 5}], [{"op": "block", "amount": 8}]),
    card("bo_particle_wall", "Particle Wall", "skill", "uncommon", 1, "self",
         [{"op": "block", "amount": 9}, {"op": "return_to_hand"}], [{"op": "block", "amount": 12}, {"op": "return_to_hand"}]),
    card("bo_bolas", "Bolas", "attack", "rare", 0, "enemy",
         [{"op": "damage", "amount": 3}, {"op": "return_next_turn"}], [{"op": "damage", "amount": 4}, {"op": "return_next_turn"}]),
    card("bo_make_it_so", "Make It So", "attack", "rare", 1, "enemy",
         [{"op": "damage", "amount": 6}, {"op": "to_draw_top"}], [{"op": "damage", "amount": 9}, {"op": "to_draw_top"}]),
    card("bo_headbutt", "Headbutt", "attack", "common", 1, "enemy",
         [{"op": "damage", "amount": 9}, put_back("discard")], [{"op": "damage", "amount": 12}, put_back("discard")]),
    card("bo_thinking_ahead", "Thinking Ahead", "skill", "uncommon", 0, "self",
         [{"op": "draw", "amount": 2}, put_back("hand")]),
    card("bo_secret_weapon", "Secret Weapon", "skill", "rare", 0, "self", [tutor("choose", "attack")]),
    card("bo_rummage", "Rummage", "skill", "uncommon", 1, "self",
         [{"op": "block", "amount": 5}, tutor("random", "skill")], [{"op": "block", "amount": 8}, tutor("random", "skill")]),
    card("bo_deep_kindling", "Deep Kindling", "skill", "uncommon", 1, "self",
         [{"op": "block", "amount": 8}, {"op": "exhaust_card", "pile": "draw", "cards": "choose", "amount": 1}, {"op": "exhaust"}],
         [{"op": "block", "amount": 11}, {"op": "exhaust_card", "pile": "draw", "cards": "choose", "amount": 1}, {"op": "exhaust"}]),
    card("bo_snap", "Snap", "attack", "common", 1, "enemy",
         [{"op": "damage", "amount": 7}, gk("sly")], [{"op": "damage", "amount": 10}, gk("sly")]),
    card("bo_steady_grip", "Steady Grip", "skill", "common", 1, "self",
         [{"op": "block", "amount": 6}, gk("retain")], [{"op": "block", "amount": 9}, gk("retain")]),
    card("bo_fading_ink", "Fading Ink", "skill", "common", 0, "self",
         [{"op": "draw", "amount": 1}, gk("ethereal"), {"op": "exhaust"}], [{"op": "draw", "amount": 2}, gk("ethereal"), {"op": "exhaust"}]),
    card("bo_turning_tide", "Turning Tide", "power", "uncommon", 1, "self",
         [{"op": "add_trigger", "trigger": "on_shuffle", "effects": [{"op": "block", "amount": 4}]}],
         [{"op": "add_trigger", "trigger": "on_shuffle", "effects": [{"op": "block", "amount": 6}]}]),
    card("bo_reboot", "Reboot", "skill", "rare", 0, "self",
         [{"op": "shuffle_hand"}, {"op": "draw", "amount": 3}], [{"op": "shuffle_hand"}, {"op": "draw", "amount": 4}]),
    card("bo_twin_jab", "Twin Jab", "attack", "common", 1, "enemy",
         [{"op": "damage", "amount": 4, "hits": 2}], [{"op": "damage", "amount": 5, "hits": 2}]),
    # Smoke iteration (2026-10-04, GAPTESTBO2): a Strength ramp so a long boss fight ends — the BO2 re-runs reached AutoSlay's
    # 100-turn cap against Knowledge Demon twice with the plain deck (no mod frame, no exception).
    card("bo_war_drum", "War Drum", "power", "rare", 1, "self",
         [{"op": "add_trigger", "trigger": "turn_start", "effects": [{"op": "apply_status", "status": "strength", "amount": 1}]}]),
]
# slot -> count (1-based card order). A THIN 19-card deck (every BO card once, three Strikes) so the draw pile empties and
# reshuffles often — the on_shuffle power's fuel. Smoke iteration (2026-10-04): the self-burners (Deep Kindling's
# exhaust-from-draw, Fading Ink's Ethereal grant) Exhaust themselves, so a long fight can't burn the deck down to a
# damage-less stalemate (GAPTESTBO2 hit AutoSlay's 100-turn cap against Knowledge Demon); max HP 90.
DECK = {"bo_strike": 3}

CHARACTER = {
    "name": "BO Gap Tester",
    "description": "Phase BO (v66) tester: recursion (Particle Wall, Bolas, a to_draw_top attack), put-back (Headbutt, "
                   "Thinking Ahead), the draw-pile tutor (Secret Weapon, Rummage), exhaust from the draw pile, keyword "
                   "grants (Sly / Retain / Ethereal), an on_shuffle power and Reboot.",
    "max_hp": 90, "max_energy": 3,
    "starting_deck": [{"slot": n, "count": DECK.get(c["id"], 1)} for n, c in enumerate(CARDS, start=1)],
}


def _unstage() -> None:
    char_json = ROOT / f"{SLOT:02d}.json"
    cdir = ROOT / f"{SLOT:02d}"
    if char_json.exists():
        char_json.unlink()
    if cdir.exists():
        shutil.rmtree(cdir)
    bak = ROOT / f"{SLOT:02d}.json{BAK_SUFFIX}"
    if bak.exists():
        bak.rename(char_json)
        print(f"  slot {SLOT:02d}: restored the backed-up character")
    bakd = ROOT / f"{SLOT:02d}{BAK_SUFFIX}"
    if bakd.exists():
        bakd.rename(cdir)
        print(f"  slot {SLOT:02d}: restored the backed-up cards")


def validate(verbose: bool = True) -> int:
    v = CardValidator()
    v.known_cards |= {c["id"] for c in CARDS}
    bad = 0
    for c in CARDS:
        if c["id"] in GAPTEST_ONLY:
            continue
        r = v.validate(dict(c))
        if not r.ok:
            bad += 1
            if verbose:
                print(f"INVALID {c['id']}: {r.errors}")
    return bad


def main(argv: list[str]) -> int:
    if "--remove" in argv:
        _unstage()
        print(f"unstaged slot {SLOT:02d}")
        return 0
    if validate():
        return 1
    if "--validate-only" in argv or "--check" in argv:  # validate only (no game dir touched)
        print(f"{len(CARDS)} cards valid")
        return 0
    char_json = ROOT / f"{SLOT:02d}.json"
    cdir = ROOT / f"{SLOT:02d}"
    if (ROOT / f"{SLOT:02d}.json{BAK_SUFFIX}").exists():
        print("a backup already exists (tester still staged?) — run --remove first")
        return 2
    # Back up whatever is staged there now, so --remove puts it back byte-for-byte.
    if char_json.exists():
        char_json.replace(ROOT / f"{SLOT:02d}.json{BAK_SUFFIX}")
    if cdir.exists():
        cdir.replace(ROOT / f"{SLOT:02d}{BAK_SUFFIX}")
    cards_dir = cdir / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    char_json.write_text(json.dumps(CHARACTER, indent=2, ensure_ascii=False), encoding="utf-8")
    for n, c in enumerate(CARDS, start=1):
        (cards_dir / f"{n:02d}.json").write_text(json.dumps(c, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"staged slot {SLOT:02d}: {CHARACTER['name']} + {len(CARDS)} cards "
          f"({sum(s['count'] for s in CHARACTER['starting_deck'])} in the starting deck)")
    print("\nnow:  uv run btsgen-autoslay-smoke --seeds GAPTESTBO1 GAPTESTBO2 --character class4 --relic auto --timeout 900")
    print("then: uv run python tests/gaptest-bo/build_tester.py --remove")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
