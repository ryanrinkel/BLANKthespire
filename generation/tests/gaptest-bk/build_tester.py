"""Phase BK Gap Tester — `hits_scale`, the hit COUNT from a live read (vocab v63, gap #65).

    cd generation
    uv run python tests/gaptest-bk/build_tester.py            # validates, backs up slot 04, stages the tester there
    uv run python tests/gaptest-bk/build_tester.py --remove   # restores whatever slot 04 held before
    uv run btsgen-autoslay-smoke --seeds GAPTESTBK1 GAPTESTBK2 --character class4 --relic auto --timeout 900

The deck (slot 04, an all-aggression class with 3 orb slots so `orb_count` has orbs to read) carries one attack per
hits_scale source plus its fuel:
  * Kindling (x3, 0-cost Block + Exhaust) — exhaust fuel + Skills in hand
  * Gale Spin       — Whirlwind: X-cost, ALL enemies, 5 damage X times            [BK] hits_scale x
                      AutoSlay never pays energy: CardCmd.AutoPlay captures X = your CURRENT energy (CardCmd.cs:102),
                      so X reads the energy left when it is auto-played (not 0).
  * Closing Combo   — Finisher: 6 damage for each Attack played this turn          [BK] hits_scale attacks_played_this_turn
  * Needle Fan      — Flechettes: 4 damage for each Skill in your hand             [BK] hits_scale skills_in_hand
  * Hand Flurry     — 3 damage for each other card in your hand                    [BK] hits_scale cards_in_hand
  * Pyre Volley     — 4 damage for each card in your exhaust pile                  [BK] hits_scale exhaust_pile_size
  * Rising Tally    — 2 damage for each card played this combat (the CAP: 10)       [BK] hits_scale plays_this_combat
  * Old Scars       — 3 damage for each time you lost HP this combat               [BK] hits_scale hp_loss_events_this_combat
  * Helix Flurry    — 0-cost, 3 damage for each energy spent this turn              [BK] hits_scale energy_spent_this_turn
                      AutoSlay spends no energy, so this one proves the READ and the 0-hit skip tag.
  * Static Barrage  — channel 1 Lightning, then 3 damage for each orb              [BK] hits_scale orb_count
  * Ember Guard / Quick Study — plain Skills (Flechettes fuel; >= 3 non-basic Skills for the merchant)
  * Blood Toll (x2) — lose 2 HP, gain Block: HP-loss fuel for Old Scars
  * Steady Rhythm   — a Power, so the merchant has one to stock (iteration 2: the thin-pool shop stall)

Pass bar (plan rule 0.3): every source tag fires with a non-zero hit count where AutoSlay can make one (say which
could not and what it read), the cap (raw > 10 -> 10) at least once, 0 mod exceptions, no BlankTheSpire frame in a
stall stack, 0 "Localization formatting error". No picker. Every card is contract-VALID (validated before staging).
The saved tag greps live next to this file as godot_BK_tags_<SEED>.txt (TEST_AUDIT_2026-10 §7).
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
BAK_SUFFIX = ".bkgaptestbak"
CH = "bk_gap_tester"


def card(cid, name, ctype, rarity, cost, target, effects, upgrade=None, up_cost=None):
    c = {"id": cid, "name": name, "type": ctype, "rarity": rarity, "cost": cost, "target": target,
         "source": "llm", "character": CH, "effects": effects, "upgrade": {"effects": upgrade or effects}}
    if up_cost is not None:
        c["upgrade"]["cost"] = up_cost
    return c


def hs(amount, src):
    return {"op": "damage", "amount": amount, "hits_scale": src}


CARDS = [
    card("bk_strike", "Strike", "attack", "basic", 1, "enemy", [{"op": "damage", "amount": 6}], [{"op": "damage", "amount": 9}]),
    card("bk_defend", "Defend", "skill", "basic", 1, "self", [{"op": "block", "amount": 5}], [{"op": "block", "amount": 8}]),
    card("bk_kindling", "Kindling", "skill", "common", 0, "self",
         [{"op": "block", "amount": 3}, {"op": "exhaust"}], [{"op": "block", "amount": 5}, {"op": "exhaust"}]),
    card("bk_gale_spin", "Gale Spin", "attack", "uncommon", "X", "all_enemies", [hs(5, "x")], [hs(8, "x")]),
    card("bk_closing_combo", "Closing Combo", "attack", "uncommon", 1, "enemy",
         [hs(6, "attacks_played_this_turn")], [hs(8, "attacks_played_this_turn")]),
    card("bk_needle_fan", "Needle Fan", "attack", "uncommon", 1, "enemy", [hs(4, "skills_in_hand")], [hs(6, "skills_in_hand")]),
    card("bk_hand_flurry", "Hand Flurry", "attack", "uncommon", 1, "enemy", [hs(3, "cards_in_hand")], [hs(4, "cards_in_hand")]),
    card("bk_pyre_volley", "Pyre Volley", "attack", "uncommon", 1, "enemy",
         [hs(4, "exhaust_pile_size")], [hs(6, "exhaust_pile_size")]),
    card("bk_rising_tally", "Rising Tally", "attack", "rare", 1, "enemy",
         [hs(2, "plays_this_combat")], [hs(3, "plays_this_combat")]),
    card("bk_old_scars", "Old Scars", "attack", "uncommon", 1, "enemy",
         [hs(3, "hp_loss_events_this_combat")], [hs(4, "hp_loss_events_this_combat")]),
    card("bk_helix_flurry", "Helix Flurry", "attack", "uncommon", 0, "enemy",
         [hs(3, "energy_spent_this_turn")], [hs(4, "energy_spent_this_turn")]),
    card("bk_static_barrage", "Static Barrage", "attack", "uncommon", 1, "enemy",
         [{"op": "channel_orb", "orb": "lightning", "amount": 1}, hs(3, "orb_count")],
         [{"op": "channel_orb", "orb": "lightning", "amount": 1}, hs(4, "orb_count")]),
    card("bk_ember_guard", "Ember Guard", "skill", "common", 1, "self", [{"op": "block", "amount": 7}], [{"op": "block", "amount": 10}]),
    card("bk_quick_study", "Quick Study", "skill", "common", 1, "self",
         [{"op": "block", "amount": 4}, {"op": "draw", "amount": 1}], [{"op": "block", "amount": 6}, {"op": "draw", "amount": 1}]),
    # iteration 2 (GAPTESTBK1 first pass): a Power so the merchant can stock one (the thin-pool stall), and a self-HP
    # cost so hp_loss_events_this_combat has fuel on turn 1 (it read 0 on all 7 first-pass plays).
    card("bk_blood_toll", "Blood Toll", "skill", "common", 0, "self",
         [{"op": "lose_hp", "amount": 2}, {"op": "block", "amount": 6}], [{"op": "lose_hp", "amount": 2}, {"op": "block", "amount": 9}]),
    card("bk_steady_rhythm", "Steady Rhythm", "power", "uncommon", 1, "self",
         [{"op": "add_trigger", "trigger": "turn_start", "effects": [{"op": "block", "amount": 3}]}], up_cost=0),
]
# slot -> count (1-based card order). 21 cards: every payoff once, the Skill fuel doubled/tripled.
DECK = {"bk_strike": 2, "bk_defend": 1, "bk_kindling": 3, "bk_ember_guard": 2, "bk_quick_study": 1, "bk_blood_toll": 2}

CHARACTER = {
    "name": "BK Gap Tester",
    "description": "Phase BK (v63) tester: hits_scale — Whirlwind (X), Finisher, Flechettes, hand / exhaust-pile / "
                   "plays-this-combat (the 10-hit cap) / HP-loss / energy-spent / orb-count hit counts.",
    "max_hp": 80, "max_energy": 3, "orb_slots": 3,
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


def validate() -> int:
    v = CardValidator()
    v.known_cards |= {c["id"] for c in CARDS}
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
    print(f"staged slot {SLOT:02d}: {CHARACTER['name']} + {len(CARDS)} cards "
          f"({sum(s['count'] for s in CHARACTER['starting_deck'])} in the starting deck)")
    print("\nnow:  uv run btsgen-autoslay-smoke --seeds GAPTESTBK1 GAPTESTBK2 --character class4 --relic auto --timeout 900")
    print("then: uv run python tests/gaptest-bk/build_tester.py --remove")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
