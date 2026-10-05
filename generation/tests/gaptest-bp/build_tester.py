"""Phase BP Gap Tester — `cost_delta` + the small reactive triggers on_card_generated / on_debuff_applied (vocab v67,
gaps #76 / #77).

    cd generation
    uv run python tests/gaptest-bp/build_tester.py --validate-only   # validate the cards only (no game dir touched)
    uv run python tests/gaptest-bp/build_tester.py                   # validates, backs up slot 04, stages the tester there
    uv run python tests/gaptest-bp/build_tester.py --remove          # restores whatever slot 04 held before
    uv run btsgen-autoslay-smoke --seeds GAPTESTBP1 GAPTESTBP2 --character class4 --relic auto --timeout 900

The deck (slot 04, a normal class, all-aggression so fights end; every BP card once + two Strikes):
  * Stomp            — 3-cost AoE 12, cost_delta attack_played -1 this_turn (STATELESS: TryModifyEnergyCostInCombat)
                                                                   [BP] cost_delta 'Stomp' on attack_played: a -> b (this_turn; ...)
  * Quick Study      — 2-cost 10 Block, cost_delta skill_played -1 this_turn (Pinpoint's shape, stateless)
                                                                   [BP] cost_delta 'Quick Study' on skill_played: ...
  * Crescendo        — 2-cost 10 damage, cost_delta card_played -1 this_turn (stateless)
                                                                   [BP] cost_delta 'Crescendo' on card_played: ...
  * Momentum Strike  — 1-cost 10 damage, cost_delta played set_zero combat (SetThisCombat(0))
                                                                   [BP] cost_delta 'Momentum Strike' on played: 1 -> 0 (combat, set_zero)
  * Kingly Kick      — 4-cost 27 damage, cost_delta drawn -1 combat (AddThisCombat(-1) in AfterCardDrawn)
                                                                   [BP] cost_delta 'Kingly Kick' on drawn: 4 -> 3 (combat, -1)
  * Modded           — 0-cost draw 1, cost_delta played +1 combat ("Costs 1 more each time you play it")
                                                                   [BP] cost_delta 'Modded' on played: 0 -> 1 (combat, +1)
  * Up My Sleeve     — 2-cost draw 2, cost_delta played -1 combat  [BP] cost_delta 'Up My Sleeve' on played: 2 -> 1 (combat, -1)
  * Ash Hunger       — 3-cost 16 damage, cost_delta card_exhausted -1 combat (AfterCardExhausted)
                                                                   [BP] cost_delta 'Ash Hunger' on card_exhausted: ...
    exhaust fuel: Burning Pact (exhaust_card choose 1 + draw 2) and Flare Shot (0-cost 5 damage, exhaust)
  * Arsenal          — power: on_card_generated -> gain 1 Strength  [BP] on_card_generated fired (...)
    generation fuel: Wild Strike (add_status_card wound -> draw pile) and Spark (add_card a copy of itself -> discard)
  * Vicious          — power: on_debuff_applied status vulnerable -> draw 1   [BP] on_debuff_applied fired (... filter vulnerable)
  * Sleight of Flesh — power: on_debuff_applied -> deal 3 damage to that_enemy  [BP] that_enemy -> '<monster>'
  * Spreading Rot    — power: on_debuff_applied -> apply 1 Poison to that_enemy — its payload applies a debuff, which
                       re-raises on_debuff_applied on the SAME power: the _firing guard must stop it
                                                                   [BP] re-entry blocked (on_debuff_applied)
    Vulnerable sources: Bash (8 damage + 2 Vulnerable) and Thunderclap (AoE 4 + 1 Vulnerable)
  * War Drum         — power: turn_start +1 Strength, 4 Block; max HP 110 (smoke iteration: GAPTESTBP2's first pass died to
                       The Insatiable after every [BP] tag had already fired)

What the smoke CAN'T prove: AutoSlay never pays energy (it plays through CardCmd.AutoPlay), so every cost_delta is
proven as a cost READ — the [BP] line logs CardEnergyCost.GetWithModifiers old -> new (Local for the mutating forms; the
stateless forms print the local read with the counted discount and the all-modifier read beside it), never as energy
actually paid. `on_evoke` is orb-class only — this normal-class tester cannot channel an orb, so it is NOT proven here
(Phase BQ's orb tester covers it; offline: test_phase_bp greps the AfterOrbEvoked override and its [BP] tag).

Tags: [BP] cost_delta '<card>' on <event>: <old> -> <new> (<scope>...) · [BP] on_card_generated fired (...) ·
[BP] on_debuff_applied fired (...) · [BP] that_enemy -> '<monster>' · [BP] re-entry blocked (on_debuff_applied).

Pass bar (plan rule 0.3): across the two seeds EVERY tag above fires at least once — cost_delta for all six `on` events
(played in all three shapes: set_zero, +1 and -1), both reactive kinds, that_enemy and the re-entry guard — plus 0 mod
exceptions, no BlankTheSpire frame in a stall stack, 0 "Localization formatting error". Burning Pact's picker should
log "Auto-selected" (the existing exhaust_card picker). The saved tag greps live next to this file as
godot_BP_tags_<SEED>.txt (TEST_AUDIT_2026-10 §7).
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
BAK_SUFFIX = ".bpgaptestbak"
CH = "bp_gap_tester"
GAPTEST_ONLY: set[str] = set()  # every BP card is a real contract card


def card(cid, name, ctype, rarity, cost, target, effects, upgrade=None, up_cost=None):
    c = {"id": cid, "name": name, "type": ctype, "rarity": rarity, "cost": cost, "target": target,
         "source": "llm", "character": CH, "effects": effects, "upgrade": {"effects": upgrade or effects}}
    if up_cost is not None:
        c["upgrade"]["cost"] = up_cost
    return c


def cd(on, scope, amount=None, set_zero=False):
    e = {"op": "cost_delta", "on": on, "scope": scope}
    if set_zero:
        e["set_zero"] = True
    else:
        e["amount"] = amount
    return e


def power(cid, name, rarity, cost, trigger, payload, **kw):
    t = {"op": "add_trigger", "trigger": trigger}
    t.update(kw)
    t["effects"] = payload
    return card(cid, name, "power", rarity, cost, "self", [t])


CARDS = [
    card("bp_strike", "Strike", "attack", "basic", 1, "enemy", [{"op": "damage", "amount": 6}], [{"op": "damage", "amount": 9}]),
    card("bp_defend", "Defend", "skill", "basic", 1, "self", [{"op": "block", "amount": 5}], [{"op": "block", "amount": 8}]),
    card("bp_stomp", "Stomp", "attack", "uncommon", 3, "all_enemies",
         [{"op": "damage", "amount": 12}, cd("attack_played", "this_turn", -1)],
         [{"op": "damage", "amount": 15}, cd("attack_played", "this_turn", -1)]),
    card("bp_quick_study", "Quick Study", "skill", "uncommon", 2, "self",
         [{"op": "block", "amount": 10}, cd("skill_played", "this_turn", -1)],
         [{"op": "block", "amount": 13}, cd("skill_played", "this_turn", -1)]),
    card("bp_crescendo", "Crescendo", "attack", "common", 2, "enemy",
         [{"op": "damage", "amount": 10}, cd("card_played", "this_turn", -1)],
         [{"op": "damage", "amount": 13}, cd("card_played", "this_turn", -1)]),
    card("bp_momentum_strike", "Momentum Strike", "attack", "common", 1, "enemy",
         [{"op": "damage", "amount": 10}, cd("played", "combat", set_zero=True)],
         [{"op": "damage", "amount": 13}, cd("played", "combat", set_zero=True)]),
    card("bp_kingly_kick", "Kingly Kick", "attack", "rare", 4, "enemy",
         [{"op": "damage", "amount": 27}, cd("drawn", "combat", -1)],
         [{"op": "damage", "amount": 35}, cd("drawn", "combat", -1)]),
    card("bp_modded", "Modded", "skill", "rare", 0, "self",
         [{"op": "draw", "amount": 1}, cd("played", "combat", 1)],
         [{"op": "draw", "amount": 2}, cd("played", "combat", 1)]),
    card("bp_up_my_sleeve", "Up My Sleeve", "skill", "uncommon", 2, "self",
         [{"op": "draw", "amount": 2}, cd("played", "combat", -1)],
         [{"op": "draw", "amount": 3}, cd("played", "combat", -1)]),
    card("bp_ash_hunger", "Ash Hunger", "attack", "uncommon", 3, "enemy",
         [{"op": "damage", "amount": 16}, cd("card_exhausted", "combat", -1)],
         [{"op": "damage", "amount": 20}, cd("card_exhausted", "combat", -1)]),
    card("bp_burning_pact", "Burning Pact", "skill", "common", 1, "self",
         [{"op": "exhaust_card", "cards": "choose", "amount": 1}, {"op": "draw", "amount": 2}],
         [{"op": "exhaust_card", "cards": "choose", "amount": 1}, {"op": "draw", "amount": 3}]),
    card("bp_flare_shot", "Flare Shot", "attack", "common", 0, "enemy",
         [{"op": "damage", "amount": 5}, {"op": "exhaust"}], [{"op": "damage", "amount": 8}, {"op": "exhaust"}]),
    power("bp_arsenal", "Arsenal", "rare", 1, "on_card_generated", [{"op": "apply_status", "status": "strength", "amount": 1}]),
    card("bp_wild_strike", "Wild Strike", "attack", "common", 1, "enemy",
         [{"op": "damage", "amount": 12}, {"op": "add_status_card", "card": "wound", "pile": "draw", "amount": 1}],
         [{"op": "damage", "amount": 17}, {"op": "add_status_card", "card": "wound", "pile": "draw", "amount": 1}]),
    card("bp_spark", "Spark", "attack", "common", 0, "enemy",
         [{"op": "damage", "amount": 4}, {"op": "add_card", "card_id": "bp_spark", "pile": "discard"}],
         [{"op": "damage", "amount": 6}, {"op": "add_card", "card_id": "bp_spark", "pile": "discard"}]),
    power("bp_vicious", "Vicious", "uncommon", 1, "on_debuff_applied", [{"op": "draw", "amount": 1}], status="vulnerable"),
    power("bp_sleight_of_flesh", "Sleight of Flesh", "uncommon", 2, "on_debuff_applied",
          [{"op": "damage", "amount": 3, "target": "that_enemy"}]),
    power("bp_spreading_rot", "Spreading Rot", "uncommon", 1, "on_debuff_applied",
          [{"op": "apply_status", "status": "poison", "amount": 1, "target": "that_enemy"}]),
    card("bp_bash", "Bash", "attack", "common", 2, "enemy",
         [{"op": "damage", "amount": 8}, {"op": "apply_status", "status": "vulnerable", "amount": 2}],
         [{"op": "damage", "amount": 10}, {"op": "apply_status", "status": "vulnerable", "amount": 3}]),
    card("bp_thunderclap", "Thunderclap", "attack", "common", 1, "all_enemies",
         [{"op": "damage", "amount": 4}, {"op": "apply_status", "status": "vulnerable", "amount": 1}],
         [{"op": "damage", "amount": 7}, {"op": "apply_status", "status": "vulnerable", "amount": 1}]),
    # Smoke iteration (2026-10-04): GAPTESTBP2's first pass died to The Insatiable (every [BP] tag had fired; no mod frame) —
    # a Strength + Block ramp and more HP so the run reaches the end.
    power("bp_war_drum", "War Drum", "rare", 1, "turn_start",
          [{"op": "apply_status", "status": "strength", "amount": 1}, {"op": "block", "amount": 4}]),
]
# slot -> count (1-based card order): every BP card once, two Strikes, one Defend (22 cards).
DECK = {"bp_strike": 2}

CHARACTER = {
    "name": "BP Gap Tester",
    "description": "Phase BP (v67) tester: self-cost rules (Stomp, Quick Study, Crescendo, Momentum Strike, Kingly Kick, "
                   "Modded, Up My Sleeve, Ash Hunger) and the small reactive triggers (Arsenal on created cards; Vicious, "
                   "Sleight of Flesh and Spreading Rot on applied debuffs).",
    "max_hp": 110, "max_energy": 3,
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
    print("\nnow:  uv run btsgen-autoslay-smoke --seeds GAPTESTBP1 GAPTESTBP2 --character class4 --relic auto --timeout 900")
    print("then: uv run python tests/gaptest-bp/build_tester.py --remove")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
