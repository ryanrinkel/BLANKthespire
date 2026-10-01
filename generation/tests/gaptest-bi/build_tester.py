"""Phase BI Gap Tester — card trigger filters (vocab v61, gap #62): card_type, every_n, scope:"this_turn", random_enemy.

    cd generation
    uv run python tests/gaptest-bi/build_tester.py            # validates, backs up slot 04, stages the tester there
    uv run python tests/gaptest-bi/build_tester.py --remove   # restores whatever slot 04 held before
    uv run btsgen-autoslay-smoke --seeds GAPTESTBI1 GAPTESTBI2 --character class4 --relic auto --timeout 900

The deck (slot 04, a NORMAL class, all aggression so AutoSlay plays everything it draws):
  * Battle Fury   — Skill, the Rage shape: "This turn, whenever you play an Attack, gain 3 Block."
                    (add_trigger on_card_played, card_type attack, scope this_turn)
  * Knife Juggler — Power, the Juggling/Juggernaut shape: "Every 3rd time you play an Attack, deal 4 damage to a
                    random enemy." (card_type attack, every_n 3, payload target random_enemy)
  * Static Loop   — Power, the Iteration shape: "Whenever you draw a Status, draw 1 card(s) (once per turn)."
                    (on_card_drawn, card_type status)
  * Reckless Swing — the Status FUEL: an Attack that shuffles 2 Wounds into the draw pile (add_status_card).

What it proves (grep %APPDATA%/SlayTheSpire2/logs/godot.log for "[BI]"):
  [BI] card_type attack matched (on_card_played: '<card>')   — the played-card filter (Fury + Juggler)
  [BI] card_type status matched (on_card_drawn: 'Wound')     — the drawn-card filter (Static Loop)
  [BI] every_n count n/3 — waiting|FIRES (on_card_played attack) — the per-combat counter (Juggler)
  [BI] this_turn trigger removed at turn end ('Battle Fury', on_card_played) — the RagePower self-removal
  [BI] random_enemy payload -> <monster> (of N).             — TriggerRunner.ResolveEnemies' random roll

Pass bar (plan rule 0.3): >=1 of each of the four [BI] tags, 0 mod exceptions (no BlankTheSpire frame in a stack),
no BlankTheSpire frame in a stall stack, 0 "Localization formatting error". No picker is involved (no
"Auto-selected" expected). Every card here is contract-VALID (validated before staging under the mod contract).
The saved tag greps live next to this file as godot_BI_tags_<SEED>.txt (TEST_AUDIT_2026-10 §7).
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
BAK_SUFFIX = ".bigaptestbak"
CH = "bi_gap_tester"

CHARACTER = {
    "name": "BI Gap Tester",
    "description": "Phase BI (v61) tester: typed / every-Nth / this-turn card triggers and a random-enemy payload.",
    "max_hp": 80, "max_energy": 3, "orb_slots": 0,
    # 12 cards: 4 Strike, 1 Defend, 2 Battle Fury, 1 Knife Juggler, 1 Static Loop, 3 Reckless Swing.
    "starting_deck": [{"slot": 1, "count": 4}, {"slot": 2, "count": 1}, {"slot": 3, "count": 2},
                      {"slot": 4, "count": 1}, {"slot": 5, "count": 1}, {"slot": 6, "count": 3}],
}


def card(cid, name, ctype, rarity, cost, target, effects, upgrade):
    return {"id": cid, "name": name, "type": ctype, "rarity": rarity, "cost": cost, "target": target,
            "source": "llm", "character": CH, "effects": effects, "upgrade": {"effects": upgrade}}


def _trig(trigger, payload, **flags):
    t = {"op": "add_trigger", "trigger": trigger, "effects": payload}
    t.update(flags)
    return t


CARDS = [
    card("bi_strike", "Strike", "attack", "basic", 1, "enemy",
         [{"op": "damage", "amount": 6}], [{"op": "damage", "amount": 9}]),
    card("bi_defend", "Defend", "skill", "basic", 1, "self",
         [{"op": "block", "amount": 5}], [{"op": "block", "amount": 8}]),
    # 3: the Rage shape (this_turn + Attack filter) — on a Skill, like the base card.
    card("bi_battle_fury", "Battle Fury", "skill", "common", 1, "self",
         [_trig("on_card_played", [{"op": "block", "amount": 3}], card_type="attack", scope="this_turn")],
         [_trig("on_card_played", [{"op": "block", "amount": 4}], card_type="attack", scope="this_turn")]),
    # 4: every 3rd Attack -> 4 damage to a random enemy (Juggling counter + Juggernaut target).
    card("bi_knife_juggler", "Knife Juggler", "power", "uncommon", 1, "self",
         [_trig("on_card_played", [{"op": "damage", "amount": 4, "target": "random_enemy"}], card_type="attack", every_n=3)],
         [_trig("on_card_played", [{"op": "damage", "amount": 6, "target": "random_enemy"}], card_type="attack", every_n=3)]),
    # 5: the Iteration shape (a Status drawn), once per turn.
    card("bi_static_loop", "Static Loop", "power", "common", 1, "self",
         [_trig("on_card_drawn", [{"op": "draw", "amount": 1}], card_type="status", once_per_turn=True)],
         [_trig("on_card_drawn", [{"op": "draw", "amount": 2}], card_type="status", once_per_turn=True)]),
    # 6: the Status fuel — Wounds into the draw pile so Static Loop has something to see.
    card("bi_reckless_swing", "Reckless Swing", "attack", "common", 1, "enemy",
         [{"op": "damage", "amount": 10}, {"op": "add_status_card", "card": "wound", "pile": "draw", "amount": 2}],
         [{"op": "damage", "amount": 13}, {"op": "add_status_card", "card": "wound", "pile": "draw", "amount": 2}]),
    # 7-8: pool filler, never in the starting deck — the merchant needs >= 2 non-basic Attacks and Skills to stock its
    # card row (GAPTESTBI1 with one of each: "There is no item to purchase" in PopulateCharacterCardEntries, then the
    # map-nav watchdog).
    card("bi_sweep", "Sweeping Cut", "attack", "common", 1, "all_enemies",
         [{"op": "damage", "amount": 7}], [{"op": "damage", "amount": 10}]),
    card("bi_brace", "Brace", "skill", "common", 1, "self",
         [{"op": "block", "amount": 7}, {"op": "draw", "amount": 1}], [{"op": "block", "amount": 10}, {"op": "draw", "amount": 1}]),
]


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


def validate() -> int:
    v = CardValidator()
    bad = 0
    for c in CARDS:
        r = v.validate(dict(c))
        if not r.ok:
            bad += 1
            print(f"INVALID {c['id']}: {r.errors}")
    return bad


def main(argv: list[str]) -> int:
    if "--remove" in argv:
        _unstage()
        print(f"unstaged slot {SLOT:02d}")
        return 0
    if validate():
        return 1
    if "--check" in argv:  # validate only (no game dir touched)
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
    print(f"staged slot {SLOT:02d}: {CHARACTER['name']} + {len(CARDS)} cards")
    print("\nnow:  uv run btsgen-autoslay-smoke --seeds GAPTESTBI1 GAPTESTBI2 --character class4 --relic auto --timeout 900")
    print("then: uv run python tests/gaptest-bi/build_tester.py --remove")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
