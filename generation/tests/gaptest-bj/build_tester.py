"""Phase BJ Gap Tester — combat-history scales + conditions (vocab v62, gaps #63/#64).

    cd generation
    uv run python tests/gaptest-bj/build_tester.py            # validates, backs up slot 04, stages the tester there
    uv run python tests/gaptest-bj/build_tester.py --remove   # restores whatever slot 04 held before
    uv run btsgen-autoslay-smoke --seeds GAPTESTBJ1 GAPTESTBJ2 --character class4 --relic auto --timeout 900

The deck (slot 04, a NORMAL class, all aggression so AutoSlay plays everything it draws) carries one card per new scale
plus its fuel, and one card per new condition:
  * Kindling (x3, 0-cost Block + Exhaust)  — exhaust fuel (exhaust_pile_size, exhausted_this_turn) + add_card's copy target
  * Ashen Brand     — damage = the cards in your exhaust pile                         [BJ] scale exhaust_pile_size
  * Stacked Ledger  — Block = the cards in your discard pile                          [BJ] scale discard_pile_size
  * Memento         — discard 2 random, damage = the cards discarded this turn        [BJ] scale discards_this_turn
  * Forced March    — draw 2, damage = the cards drawn this turn                      [BJ] scale cards_drawn_this_turn
  * Long Tally      — damage = every card drawn this combat                           [BJ] scale cards_drawn_this_combat
  * Helix Bore      — damage = the energy spent this turn (0-cost)                    [BJ] scale energy_spent_this_turn
                      AutoSlay never spends energy (AutoPlay), so this one proves the READ only: it logs 0.
  * Old Wounds      — damage = the times you lost HP this combat                      [BJ] scale hp_loss_events_this_combat
  * Echo Kindling   — add a Kindling copy to hand (the generation fuel)
  * Collapsing Star — damage = the cards you created this combat                      [BJ] scale cards_generated_this_combat
  * Venom Dart (x2) — Poison fuel; Miasma Bloom — damage = the Poison on ALL enemies  [BJ] scale total_enemy_poison
  * Pick On         — apply 2 Vulnerable, then damage = the enemy's Vulnerable        [BJ] scale target_status_stacks
  * Studied Hand    — Expertise: draw until you hold 6                                [BJ] draw to_hand_size
  * Double Charge   — Double Energy (+ Exhaust)                                       [BJ] gain_energy x energy
  * Ember Gaze      — Evil Eye: draw 1 if you Exhausted a card this turn              [BJ] cond exhausted_this_turn
  * Carried Momentum — draw 2 if you played 2+ cards last turn                        [BJ] cond played_cards_last_turn_ge
  * Eye Gouge       — Go for the Eyes: Weak 1 if the enemy intends to attack          [BJ] cond target_intends_attack
  * Ash Ward        — power: at the end of your turn, Block = the exhaust pile        [BJ] scale exhaust_pile_size (payload)

Pass bar (plan rule 0.3): every [BJ] scale tag fires (non-zero where the deck makes it possible), both executor tags,
all three cond tags (true at least once), 0 mod exceptions, no BlankTheSpire frame in a stall stack, 0 "Localization
formatting error". No picker is involved. Every card is contract-VALID (validated before staging under the mod
contract). The saved tag greps live next to this file as godot_BJ_tags_<SEED>.txt (TEST_AUDIT_2026-10 §7).
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
BAK_SUFFIX = ".bjgaptestbak"
CH = "bj_gap_tester"


def card(cid, name, ctype, rarity, cost, target, effects, upgrade=None, up_cost=None):
    c = {"id": cid, "name": name, "type": ctype, "rarity": rarity, "cost": cost, "target": target,
         "source": "llm", "character": CH, "effects": effects, "upgrade": {"effects": upgrade or effects}}
    if up_cost is not None:
        c["upgrade"]["cost"] = up_cost
    return c


def sc(op, scale, amount=1, **kw):
    e = {"op": op, "amount": amount, "scale": scale}
    e.update(kw)
    return e


CARDS = [
    card("bj_strike", "Strike", "attack", "basic", 1, "enemy", [{"op": "damage", "amount": 6}], [{"op": "damage", "amount": 9}]),
    card("bj_defend", "Defend", "skill", "basic", 1, "self", [{"op": "block", "amount": 5}], [{"op": "block", "amount": 8}]),
    card("bj_kindling", "Kindling", "skill", "common", 0, "self",
         [{"op": "block", "amount": 3}, {"op": "exhaust"}], [{"op": "block", "amount": 5}, {"op": "exhaust"}]),
    card("bj_ashen_brand", "Ashen Brand", "attack", "uncommon", 1, "enemy", [sc("damage", "exhaust_pile_size")], up_cost=0),
    card("bj_stacked_ledger", "Stacked Ledger", "skill", "common", 1, "self", [sc("block", "discard_pile_size")], up_cost=0),
    card("bj_memento", "Memento", "attack", "uncommon", 0, "enemy",
         [{"op": "discard", "amount": 2}, sc("damage", "discards_this_turn")],
         [{"op": "discard", "amount": 3}, sc("damage", "discards_this_turn")]),
    card("bj_forced_march", "Forced March", "attack", "uncommon", 1, "enemy",
         [{"op": "draw", "amount": 2}, sc("damage", "cards_drawn_this_turn")],
         [{"op": "draw", "amount": 3}, sc("damage", "cards_drawn_this_turn")]),
    card("bj_long_tally", "Long Tally", "attack", "rare", 2, "enemy", [sc("damage", "cards_drawn_this_combat")], up_cost=1),
    card("bj_helix_bore", "Helix Bore", "attack", "uncommon", 0, "enemy", [sc("damage", "energy_spent_this_turn")]),
    card("bj_old_wounds", "Old Wounds", "attack", "rare", 2, "enemy", [sc("damage", "hp_loss_events_this_combat")], up_cost=1),
    card("bj_echo_kindling", "Echo Kindling", "skill", "common", 1, "self",
         [{"op": "block", "amount": 4}, {"op": "add_card", "card_id": "bj_kindling", "pile": "hand"}],
         [{"op": "block", "amount": 7}, {"op": "add_card", "card_id": "bj_kindling", "pile": "hand"}]),
    card("bj_collapsing_star", "Collapsing Star", "attack", "uncommon", 1, "enemy",
         [sc("damage", "cards_generated_this_combat")], up_cost=0),
    card("bj_venom_dart", "Venom Dart", "attack", "common", 1, "enemy",
         [{"op": "damage", "amount": 3}, {"op": "apply_status", "status": "poison", "amount": 4}],
         [{"op": "damage", "amount": 4}, {"op": "apply_status", "status": "poison", "amount": 6}]),
    card("bj_miasma_bloom", "Miasma Bloom", "attack", "uncommon", 1, "all_enemies", [sc("damage", "total_enemy_poison")], up_cost=0),
    card("bj_pick_on", "Pick On", "attack", "common", 1, "enemy",
         [{"op": "apply_status", "status": "vulnerable", "amount": 2}, sc("damage", "target_status_stacks", status="vulnerable")],
         [{"op": "apply_status", "status": "vulnerable", "amount": 3}, sc("damage", "target_status_stacks", status="vulnerable")]),
    card("bj_studied_hand", "Studied Hand", "skill", "uncommon", 1, "self",
         [sc("draw", "to_hand_size", amount=6)], [sc("draw", "to_hand_size", amount=7)]),
    card("bj_double_charge", "Double Charge", "skill", "uncommon", 1, "self",
         [sc("gain_energy", "energy"), {"op": "exhaust"}], up_cost=0),
    card("bj_ember_gaze", "Ember Gaze", "skill", "common", 1, "self",
         [{"op": "block", "amount": 6}, {"op": "draw", "amount": 1, "when": {"kind": "exhausted_this_turn"}}],
         [{"op": "block", "amount": 9}, {"op": "draw", "amount": 1, "when": {"kind": "exhausted_this_turn"}}]),
    card("bj_carried_momentum", "Carried Momentum", "skill", "common", 1, "self",
         [{"op": "block", "amount": 6}, {"op": "draw", "amount": 2, "when": {"kind": "played_cards_last_turn_ge", "value": 2}}],
         [{"op": "block", "amount": 9}, {"op": "draw", "amount": 2, "when": {"kind": "played_cards_last_turn_ge", "value": 2}}]),
    card("bj_eye_gouge", "Eye Gouge", "attack", "common", 0, "enemy",
         [{"op": "damage", "amount": 3}, {"op": "apply_status", "status": "weak", "amount": 1, "when": {"kind": "target_intends_attack"}}],
         [{"op": "damage", "amount": 4}, {"op": "apply_status", "status": "weak", "amount": 2, "when": {"kind": "target_intends_attack"}}]),
    card("bj_ash_ward", "Ash Ward", "power", "uncommon", 1, "self",
         [{"op": "add_trigger", "trigger": "turn_end", "effects": [sc("block", "exhaust_pile_size")]}], up_cost=0),
]
# slot -> count (1-based card order). 25 cards: every payoff once, the fuel doubled/tripled.
DECK = {"bj_strike": 2, "bj_defend": 1, "bj_kindling": 3, "bj_venom_dart": 2}

CHARACTER = {
    "name": "BJ Gap Tester",
    "description": "Phase BJ (v62) tester: combat-history scales (exhaust/discard piles, draws, discards, energy spent, "
                   "HP-loss events, cards created, total Poison, target stacks), Expertise, Double Energy, and the "
                   "exhausted / last-turn / intent gates.",
    "max_hp": 80, "max_energy": 3, "orb_slots": 0,
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
    v.known_cards |= {c["id"] for c in CARDS}  # the class's own cards (add_card targets), as class_forge registers them
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
    print("\nnow:  uv run btsgen-autoslay-smoke --seeds GAPTESTBJ1 GAPTESTBJ2 --character class4 --relic auto --timeout 900")
    print("then: uv run python tests/gaptest-bj/build_tester.py --remove")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
