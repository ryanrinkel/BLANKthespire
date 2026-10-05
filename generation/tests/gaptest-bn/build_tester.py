"""Phase BN Gap Tester — on-kill payoff (`when target_killed`), random generation (`add_random_card`) and auto-play
(`autoplay`) (vocab v69, gaps #71-#73), on a NORMAL class; plus the BP `on_card_generated` proof for generated cards.

COMPLETE SMOKE RECIPE (Ryan pre-approved it). Close the game first.

    cd generation
    uv run python tests/gaptest-bn/build_tester.py --validate-only   # validate the cards only (no game dir touched)
    ~/.dotnet/dotnet.exe build ../mod/BlankTheSpire.csproj -c Debug  # (or pass --build to the smoke) — the v69 DLL must be deployed
    uv run python tests/gaptest-bn/build_tester.py                   # validates, backs up slot 04, stages the tester there
    uv run btsgen-autoslay-smoke --seeds GAPTESTBN1 GAPTESTBN2 --character class4 --relic auto --timeout 900
    uv run python tests/gaptest-bn/build_tester.py --remove          # restores whatever slot 04 held before

The deck (slot 04, a normal class, all-aggression so fights end; every BN card once + two Strikes + a Defend). The class
pool IS these cards, so add_random_card draws from them (Basics are never generated; add_random_card cards never are):
  * Feed            — rare exhaust attack: 10 damage, gain 3 Max HP if this kills the enemy (single target, Feed-exact)
                                                      [BN] target_killed gate OPEN|closed (killed=<b>, fatal=<b>) ('Feed')
  * Reaping Strike  — common attack (the repeatable on-kill read): 9 damage, heal 4 HP if this kills the enemy
  * Sunder          — AoE: 12 damage to ALL enemies, gain 2 energy if this kills an enemy (ANY kill, plan §7 decision 5)
  * Mercy Cut       — the NEGATED gate: 8 damage, apply 2 Weak unless this kills the enemy   ... (negated) ...
  * Discovery       — choose 1 of 3 random Skills to add to your hand, free this turn, Exhaust
                                                      [BN] add_random_card skill x1 -> Hand (...; free=True; choose_of=3)
                                                      + AutoSlay's "Auto-selected 1 card(s)" (FromChooseACardScreen)
  * Infernal Blade  — add a random Attack to your hand, free this turn, Exhaust
                                                      [BN] add_random_card attack x1 -> Hand (...; free=True; choose_of=0)
  * Scatter Notes   — 4 Block + add 2 random cards to your discard pile
                                                      [BN] add_random_card any x2 -> Discard (...; free=False; choose_of=0)
  * Havoc           — play the top card of your draw pile and Exhaust it      [BN] autoplay draw_top '<card>' -> <target|none> (depth 1)
  * Uproar          — 5 damage x2, then play a random Attack from your draw pile
                                                      [BN] autoplay draw_random '<card>' -> <target|none> (depth 1)
  * Creative Spark  — power (Creative AI): at the start of your turn, add a random Power to your hand
                                                      [BN] add_random_card power x1 -> Hand (...) ('payload')
  * Mayhem          — power: at the start of your turn, play the top card of your draw pile and Exhaust it — fired from
                      AfterAutoPrePlayPhaseEntered    [BN] mayhem payload from AfterAutoPrePlayPhaseEntered ('Mayhem')
                                                      + [BN] autoplay draw_top '<card>' ... ('payload')
  * Arsenal         — the BP on_card_generated power (gain 1 Block per created card) — proves add_random_card cards count
                                                      [BP] on_card_generated fired ('Arsenal': '<generated card>' created)
  * War Drum        — power: turn_start +1 Strength, 4 Block (the BO/BP run-completion fix); max HP 100.

Pass bar (plan rule 0.3), across the two seeds:
  - [BN] target_killed gate OPEN at least once (and closed lines — both branches), with fatal=True on an OPEN line; a
    "(negated)" line from Mercy Cut.
  - EVERY add_random_card form: choose_of=3 (Discovery) + an "Auto-selected 1 card(s)" line, the free Attack (Infernal
    Blade), the x2 discard-pile form (Scatter Notes) and the turn_start payload ('payload', Creative Spark).
  - BOTH autoplay forms: "[BN] autoplay draw_top" and "[BN] autoplay draw_random", and the Mayhem line
    "[BN] mayhem payload from AfterAutoPrePlayPhaseEntered".
  - "[BP] on_card_generated fired" naming a card that an add_random_card line generated.
  - 0 mod exceptions, no BlankTheSpire frame in a stall stack, 0 "Localization formatting error".
  - Map-nav FAIL is expected (AutoSlay verdict); gate on the godot.log tags. Known non-mod failures: the Steam relaunch race
    (the second seed never reaches the game -> re-run it alone) and the Phase BM Act-3 whole-process freeze (unreproduced).
  - Not provable here: "[BN] autoplay depth guard hit" (autoplay cards are never auto-play candidates, so the guard is a
    belt behind that brace) and "[BN] add_random_card: empty pool, skipped" (every type has candidates in this pool);
    test_phase_bn pins both offline. AutoSlay never pays energy, so "free this turn" is proven as the card being added
    (SetToFreeThisTurn), never as energy saved.
Save the per-seed tag grep next to this file as godot_BN_tags_<SEED>.txt (TEST_AUDIT_2026-10 §7), in the format of
tests/gaptest-bp/godot_BP_tags_<SEED>.txt; test_phase_bn reads them (a missing file fails the test).
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
BAK_SUFFIX = ".bngaptestbak"
CH = "bn_gap_tester"
GAPTEST_ONLY: set[str] = set()  # every BN card is a real contract card

KILLED = {"kind": "target_killed"}


def card(cid, name, ctype, rarity, cost, target, effects, upgrade=None, up_cost=None):
    c = {"id": cid, "name": name, "type": ctype, "rarity": rarity, "cost": cost, "target": target,
         "source": "llm", "character": CH, "effects": effects, "upgrade": {"effects": upgrade or effects}}
    if up_cost is not None:
        c["upgrade"]["cost"] = up_cost
    return c


def power(cid, name, rarity, cost, trigger, payload, up_cost=None):
    return card(cid, name, "power", rarity, cost, "self", [{"op": "add_trigger", "trigger": trigger, "effects": payload}],
                up_cost=up_cost)


CARDS = [
    card("bn_strike", "Strike", "attack", "basic", 1, "enemy", [{"op": "damage", "amount": 6}], [{"op": "damage", "amount": 9}]),
    card("bn_defend", "Defend", "skill", "basic", 1, "self", [{"op": "block", "amount": 5}], [{"op": "block", "amount": 8}]),
    # --- gap #71: on-kill ---
    card("bn_feed", "Feed", "attack", "rare", 1, "enemy",
         [{"op": "damage", "amount": 10}, {"op": "gain_max_hp", "amount": 3, "when": KILLED}, {"op": "exhaust"}],
         [{"op": "damage", "amount": 12}, {"op": "gain_max_hp", "amount": 4, "when": KILLED}, {"op": "exhaust"}]),
    card("bn_reaping_strike", "Reaping Strike", "attack", "common", 1, "enemy",
         [{"op": "damage", "amount": 9}, {"op": "heal", "amount": 4, "when": KILLED}],
         [{"op": "damage", "amount": 12}, {"op": "heal", "amount": 5, "when": KILLED}]),
    card("bn_sunder", "Sunder", "attack", "uncommon", 3, "all_enemies",
         [{"op": "damage", "amount": 12}, {"op": "gain_energy", "amount": 2, "when": KILLED}],
         [{"op": "damage", "amount": 16}, {"op": "gain_energy", "amount": 2, "when": KILLED}]),
    card("bn_mercy_cut", "Mercy Cut", "attack", "common", 1, "enemy",
         [{"op": "damage", "amount": 8}, {"op": "apply_status", "status": "weak", "amount": 2, "when": dict(KILLED, negate=True)}],
         [{"op": "damage", "amount": 11}, {"op": "apply_status", "status": "weak", "amount": 2, "when": dict(KILLED, negate=True)}]),
    # --- gap #72: random generation ---
    card("bn_discovery", "Discovery", "skill", "uncommon", 1, "self",
         [{"op": "add_random_card", "card_type": "skill", "pile": "hand", "choose_of": 3, "free_this_turn": True}, {"op": "exhaust"}],
         [{"op": "add_random_card", "card_type": "skill", "pile": "hand", "choose_of": 3, "free_this_turn": True}]),
    card("bn_infernal_blade", "Infernal Blade", "skill", "uncommon", 1, "self",
         [{"op": "add_random_card", "card_type": "attack", "pile": "hand", "free_this_turn": True}, {"op": "exhaust"}],
         up_cost=0),
    card("bn_scatter_notes", "Scatter Notes", "skill", "common", 1, "self",
         [{"op": "block", "amount": 4}, {"op": "add_random_card", "pile": "discard", "amount": 2}],
         [{"op": "block", "amount": 7}, {"op": "add_random_card", "pile": "discard", "amount": 2}]),
    # --- gap #73: autoplay ---
    card("bn_havoc", "Havoc", "skill", "common", 1, "self", [{"op": "autoplay", "from": "draw_top"}], up_cost=0),
    card("bn_uproar", "Uproar", "attack", "uncommon", 2, "enemy",
         [{"op": "damage", "amount": 5, "hits": 2}, {"op": "autoplay", "from": "draw_random", "card_type": "attack"}],
         [{"op": "damage", "amount": 7, "hits": 2}, {"op": "autoplay", "from": "draw_random", "card_type": "attack"}]),
    # --- the payload forms + the BP proof ---
    power("bn_creative_spark", "Creative Spark", "rare", 3, "turn_start",
          [{"op": "add_random_card", "card_type": "power", "pile": "hand"}], up_cost=2),
    power("bn_mayhem", "Mayhem", "rare", 2, "turn_start", [{"op": "autoplay", "from": "draw_top"}], up_cost=1),
    power("bn_arsenal", "Arsenal", "rare", 1, "on_card_generated", [{"op": "block", "amount": 1}]),
    power("bn_war_drum", "War Drum", "rare", 1, "turn_start",
          [{"op": "apply_status", "status": "strength", "amount": 1}, {"op": "block", "amount": 4}]),
]
# every BN card once, two Strikes, one Defend (16 cards).
DECK = {"bn_strike": 2}

CHARACTER = {
    "name": "BN Gap Tester",
    "description": "Phase BN (v69) tester: on-kill payoffs (Feed, Reaping Strike, Sunder, Mercy Cut), random generation "
                   "(Discovery, Infernal Blade, Scatter Notes, Creative Spark) and auto-play (Havoc, Uproar, Mayhem), plus "
                   "Arsenal to prove generated cards fire on_card_generated.",
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
    print("\nnow:  uv run btsgen-autoslay-smoke --seeds GAPTESTBN1 GAPTESTBN2 --character class4 --relic auto --timeout 900")
    print("then: uv run python tests/gaptest-bn/build_tester.py --remove")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
