"""Phase BR Gap Tester — stun (re-opened gap #11), `discard cards:"all"` + `scale` / `hits_scale` `cards_removed`, and growing
turn-start damage (gap #79) (vocab v70), on a NORMAL class.

COMPLETE SMOKE RECIPE (Ryan pre-approved it). Close the game first.

    cd generation
    uv run python tests/gaptest-br/build_tester.py --validate-only   # validate the cards only (no game dir touched)
    ~/.dotnet/dotnet.exe build ../mod/BlankTheSpire.csproj -c Debug  # (or pass --build to the smoke) — the v70 DLL must be deployed
    uv run python tests/gaptest-br/build_tester.py                   # validates, backs up slot 04, stages the tester there
    uv run btsgen-autoslay-smoke --seeds GAPTESTBR1 GAPTESTBR2 --character class4 --relic auto --timeout 900
    uv run python tests/gaptest-br/build_tester.py --remove          # restores whatever slot 04 held before
    (use --timeout 1500 if a seed is slow but still progressing; a Steam relaunch race -> re-run that seed alone)

The deck (slot 04, a normal class, all-aggression so fights end; 13 cards). Whistle is the class's ONE stun card (the
class-level rule counts distinct cards) — the deck holds TWO COPIES so a second stun lands on an already-STUNNED enemy (the
locked-move no-op the base SetMoveImmediate gives us):
  * Whistle          — uncommon 3-cost Exhaust attack: 20 damage, then Stun the enemy (x2 in the deck)
                       [BR] stun '<enemy>': next move <old> -> STUNNED (applied=True)
                       [BR] stun '<enemy>': next move STUNNED -> STUNNED (applied=False) + [BR] stun skipped: already stunned
                       [BR] stun skipped: cannot transition '<enemy>' (locked move '<id>', ...)   (a boss / locked move)
                       [BR] stunned turn performed '<enemy>' (the Func overload of CreatureCmd.Stun runs on the STUNNED turn)
  * Fiend Fire       — rare 2-cost Exhaust attack: Exhaust your hand, 7 damage for each card Exhausted
                       [BC] exhaust_card all x<n> + [BR] cards_removed -> <n> ('Fiend Fire') (hits) + [BK] hits_scale cards_removed -> <n> hits
  * Scatter Volley   — rare 1-cost attack: Discard your hand, 4 damage for each card Discarded
                       [BR] discard all x<n> + [BR] cards_removed -> <n> ('Scatter Volley') (hits) + [BK] hits_scale cards_removed
  * Calculated Gamble — uncommon 0-cost Exhaust skill: Discard your hand, draw cards equal to the cards Discarded
                       [BR] discard all x<n> + [BR] cards_removed -> <n> ('Calculated Gamble') (draw)
  * Flicker Guard    — common Sly skill (7 Block): a whole-hand discard plays it for free (the batch CardCmd.Discard keeps Sly)
  * Rolling Boulder  — rare 3-cost power: at the start of your turn, deal 5 damage to ALL enemies, +5 each turn
                       [BR] turn_start grow: 5+5x<fires> = <dmg> (from ForgedTriggerPower.AfterSideTurnStart, a
                       ThrowingPlayerChoiceContext — never BeforeSideTurnStart, never the base RollingBoulderPower)
  * Quick Slash / Brace — common pool fillers (the merchant needs non-basic Attacks + Skills); War Drum — power: turn_start +1
    Strength, 4 Block (the Strength power that ends fights); max HP 100.

Pass bar (plan rule 0.3 + the Phase BR gate), across the two seeds:
  - "[BR] stun" with applied=True at least once AND at least one "applied=False" / "[BR] stun skipped" line (already stunned or
    a locked boss move — say which), and "[BR] stunned turn performed" (the enemy lost its turn).
  - "[BR] cards_removed -> <n>" non-zero for BOTH a discard form (Scatter Volley / Calculated Gamble) and the exhaust form
    (Fiend Fire); "[BR] discard all x<n>"; Fiend Fire's hits from "[BK] hits_scale cards_removed -> <n> hits".
  - "[BR] turn_start grow: 5+5x<fires>" with fires >= 2 (the growth is visible).
  - 0 mod exceptions, no BlankTheSpire frame in a stall stack, 0 "Localization formatting error", and NO hang at "Combat turn N"
    (if one happens, the turn-start pitfall — a lethal tick on BeforeSideTurnStart — is the first suspect).
  - Map-nav FAIL is expected (AutoSlay verdict); gate on the godot.log tags. AutoSlay never pays energy (the 3-cost Whistle /
    Rolling Boulder are played at no cost — the stun and growth are proven, the price is not).
Save the per-seed tag grep next to this file as godot_BR_tags_<SEED>.txt (TEST_AUDIT_2026-10 §7), in the format of
tests/gaptest-bn/godot_BN_tags_<SEED>.txt; test_phase_br reads them (until they exist it prints "smoke pending").
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
BAK_SUFFIX = ".brgaptestbak"
CH = "br_gap_tester"
GAPTEST_ONLY: set[str] = set()  # every BR card is a real contract card


def card(cid, name, ctype, rarity, cost, target, effects, upgrade=None, up_cost=None):
    c = {"id": cid, "name": name, "type": ctype, "rarity": rarity, "cost": cost, "target": target,
         "source": "llm", "character": CH, "effects": effects, "upgrade": {"effects": upgrade or effects}}
    if up_cost is not None:
        c["upgrade"]["cost"] = up_cost
    return c


def power(cid, name, rarity, cost, trigger, payload, upgrade_payload=None, up_cost=None):
    up = [{"op": "add_trigger", "trigger": trigger, "effects": upgrade_payload}] if upgrade_payload else None
    return card(cid, name, "power", rarity, cost, "self", [{"op": "add_trigger", "trigger": trigger, "effects": payload}],
                up, up_cost=up_cost)


CARDS = [
    card("br_strike", "Strike", "attack", "basic", 1, "enemy", [{"op": "damage", "amount": 6}], [{"op": "damage", "amount": 9}]),
    card("br_defend", "Defend", "skill", "basic", 1, "self", [{"op": "block", "amount": 5}], [{"op": "block", "amount": 8}]),
    # --- gap #11: stun (the class's ONE stun card; two copies in the deck) ---
    card("br_whistle", "Whistle", "attack", "uncommon", 3, "enemy",
         [{"op": "damage", "amount": 20}, {"op": "stun"}, {"op": "exhaust"}],
         [{"op": "damage", "amount": 26}, {"op": "stun"}, {"op": "exhaust"}]),
    # --- gap #79: the whole-hand dump + cards_removed ---
    card("br_fiend_fire", "Fiend Fire", "attack", "rare", 2, "enemy",
         [{"op": "exhaust_card", "cards": "all"}, {"op": "damage", "amount": 7, "hits_scale": "cards_removed"}, {"op": "exhaust"}],
         [{"op": "exhaust_card", "cards": "all"}, {"op": "damage", "amount": 10, "hits_scale": "cards_removed"}, {"op": "exhaust"}]),
    card("br_scatter_volley", "Scatter Volley", "attack", "rare", 1, "enemy",
         [{"op": "discard", "cards": "all"}, {"op": "damage", "amount": 4, "hits_scale": "cards_removed"}],
         [{"op": "discard", "cards": "all"}, {"op": "damage", "amount": 6, "hits_scale": "cards_removed"}]),
    card("br_calculated_gamble", "Calculated Gamble", "skill", "uncommon", 0, "self",
         [{"op": "discard", "cards": "all"}, {"op": "draw", "amount": 1, "scale": "cards_removed"}, {"op": "exhaust"}],
         [{"op": "discard", "cards": "all"}, {"op": "draw", "amount": 1, "scale": "cards_removed"}]),
    card("br_flicker_guard", "Flicker Guard", "skill", "common", 1, "self",
         [{"op": "block", "amount": 7}, {"op": "sly"}], [{"op": "block", "amount": 10}, {"op": "sly"}]),
    # --- gap #79: growing turn-start damage (Rolling Boulder, mod-native) ---
    power("br_rolling_boulder", "Rolling Boulder", "rare", 3, "turn_start",
          [{"op": "damage", "amount": 5, "grow": 5, "target": "all_enemies"}], up_cost=2),
    # --- pool fillers + the Strength power ---
    card("br_quick_slash", "Quick Slash", "attack", "common", 1, "enemy",
         [{"op": "damage", "amount": 8}, {"op": "draw", "amount": 1}], [{"op": "damage", "amount": 11}, {"op": "draw", "amount": 1}]),
    card("br_brace", "Brace", "skill", "common", 1, "self",
         [{"op": "block", "amount": 6}, {"op": "draw", "amount": 1}], [{"op": "block", "amount": 9}, {"op": "draw", "amount": 1}]),
    power("br_war_drum", "War Drum", "rare", 1, "turn_start",
          [{"op": "apply_status", "status": "strength", "amount": 1}, {"op": "block", "amount": 4}]),
]
# every BR card once, plus a second Strike and a second Whistle (13 cards).
DECK = {"br_strike": 2, "br_whistle": 2}

CHARACTER = {
    "name": "BR Gap Tester",
    "description": "Phase BR (v70) tester: Whistle (stun, two copies of the class's one stun card), Fiend Fire / Scatter Volley / "
                   "Calculated Gamble (the whole-hand dump + cards_removed), Flicker Guard (Sly under a whole-hand discard) and "
                   "Rolling Boulder (growing turn-start damage), with War Drum for Strength.",
    "max_hp": 100, "max_energy": 3,
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
    # Phase BR (v70): the class-level stun rails (one stun card per class, nothing re-buys it) hold for the tester too.
    from btsgen.class_forge import _stun_class_conflict
    made: list[dict] = []
    for c in CARDS:
        why = _stun_class_conflict(made, c)
        if why:
            bad += 1
            if verbose:
                print(f"CLASS-LEVEL {c['id']}: {why}")
        made.append(c)
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
    print("\nnow:  uv run btsgen-autoslay-smoke --seeds GAPTESTBR1 GAPTESTBR2 --character class4 --relic auto --timeout 900")
    print("then: uv run python tests/gaptest-br/build_tester.py --remove")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
