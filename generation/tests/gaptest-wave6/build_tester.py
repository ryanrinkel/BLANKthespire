"""Wave 6 interaction tester — the v61..v70 mechanics COMBINED on single cards and in one deck (v0.4.0 release prep).

Not a coverage tester (each phase has its own under tests/gaptest-b<x>/): the goal is LOOPS and CRASHES between phases —
replays of autoplayed cards, Echo Form on a card that returns to hand, Havoc pulling a card that puts itself back on top,
generated cards that are cheaper when drawn, a stun next to a discard-pile tutor and a whole-hand dump, Fiend Fire with an
on-kill payoff under Doom, a reactive power that re-applies a debuff on every debuff, a thin deck that shuffles itself under
Sly grants, and a turn-start card generator next to the growing Rolling Boulder.

COMPLETE SMOKE RECIPE (Ryan pre-approved it). Close the game first.

    cd generation
    uv run python tests/gaptest-wave6/build_tester.py --validate-only   # validate the cards only (no game dir touched)
    ~/.dotnet/dotnet.exe build ../mod/BlankTheSpire.csproj -c Debug      # the v70 DLL must be deployed
    uv run python tests/gaptest-wave6/build_tester.py                   # validates, backs up slot 04, stages the tester
    uv run btsgen-autoslay-smoke --seeds GAPTESTW61 GAPTESTW62 --character class4 --relic auto --timeout 1500
    uv run python tests/gaptest-wave6/build_tester.py --remove          # restores whatever slot 04 held before
    (a Steam relaunch race -> re-run that seed alone; godot.log is overwritten per launch, so copy it after each seed)

The deck (slot 04, a NORMAL class with 3 orb slots — the BK precedent — so the one BQ card can channel; max HP 100):
  * Echo Barrage      — replay_next attack + autoplay draw_top on ONE card (the autoplayed Attack is replayed)  [BM] + [BN]
  * Echo Form         — the first card each turn plays twice (power)                                          [BM] echo_form
  * Particle Wall     — block + return_to_hand (Echo Form replays a card that returns to hand)                 [BO]
  * Make It So        — damage + to_draw_top, so Havoc / Echo Barrage autoplay it again and again             [BO]
  * Havoc             — autoplay draw_top                                                                      [BN]
  * Spark Foundry     — add_random_card attack + cost_delta on:drawn on ONE card                               [BN] + [BP]
  * Arsenal           — on_card_generated: 1 Block (fires for every generated card)                            [BP]
  * Whistle           — the class's ONE stun card (all guard rails: exhaust, cost 3, uncommon, single enemy)   [BR] stun
  * Second Look       — retrieve_card pile:"discard" choose + draw                                             [BO] (pre-v66 op)
  * Calculated Gamble — discard all + draw = cards_removed                                                     [BR]
  * Fiend Fire        — exhaust all + hits_scale cards_removed + heal when target_killed                       [BK] + [BR] + [BN]
  * Death Knell       — Doom 7                                                                                 [BL] doom
  * Doom Reaper       — damage = target_status_stacks doom, gain energy when target_killed                     [BJ] + [BN]
  * Fury Rhythm       — on_card_played Attack, this_turn + every_n 2 on ONE trigger (if the validators allow it) [BI]
  * Knife Juggler     — every 3rd Attack: 4 damage to a random enemy                                           [BI]
  * Sapping Echo      — on_debuff_applied: temp_strength_down 1 on that_enemy (a debuff that fires on debuffs) [BP] + [BL]
  * Sapping Hex       — strength_down + temp_strength_down                                                     [BL]
  * Bunker Down       — block + block_next_turn scale:block + retain_hand                                      [BM]
  * Battle Trance     — draw 3 + no_draw                                                                       [BM]
  * Snap              — damage + grant_keyword sly                                                             [BO]
  * Turning Tide      — on_shuffle: 3 Block (the deck is thin: it shuffles often)                              [BO]
  * Rolling Boulder   — turn_start: 4 damage to ALL enemies, +4 each turn                                      [BR]
  * Creative Spark    — turn_start: add a random Power to your hand (can generate Echo Form / Rolling Boulder) [BN]
  * Static Coil       — channel lightning + trigger_passive (the BQ tag on a normal class)                     [BQ]
  * War Drum          — turn_start +1 Strength + 4 Block (the Strength power that ends fights)
Combinations the validators FORBID are recorded in REJECTED below (that is the answer — not forced).

Pass bar (plan rule 0.3), per seed: the run completes (or dies to a boss — say which); 0 mod exceptions; no BlankTheSpire frame
in any exception or stall stack; 0 "Localization formatting error"; no hang at "Combat turn N"; no whole-game freeze; and a
non-zero tag count for every phase prefix [BI] [BJ] [BK] [BL] [BM] [BN] [BO] [BP] [BQ] [BR] across the two seeds.
Save the per-seed grep next to this file as godot_W6_tags_<SEED>.txt; test_wave6_interaction reads them.
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
BAK_SUFFIX = ".w6gaptestbak"
CH = "w6_gap_tester"
SMOKE_SEEDS = ("GAPTESTW61", "GAPTESTW62")
PHASE_PREFIXES = ("[BI]", "[BJ]", "[BK]", "[BL]", "[BM]", "[BN]", "[BO]", "[BP]", "[BQ]", "[BR]")
KILLED = {"kind": "target_killed"}


def card(cid, name, ctype, rarity, cost, target, effects, upgrade=None, up_cost=None):
    c = {"id": cid, "name": name, "type": ctype, "rarity": rarity, "cost": cost, "target": target,
         "source": "llm", "character": CH, "effects": effects, "upgrade": {"effects": upgrade or effects}}
    if up_cost is not None:
        c["upgrade"]["cost"] = up_cost
    return c


def trig(trigger, payload, **flags):
    t = {"op": "add_trigger", "trigger": trigger}
    t.update(flags)
    t["effects"] = payload
    return t


def power(cid, name, rarity, cost, trigger, payload, up_cost=None, **flags):
    return card(cid, name, "power", rarity, cost, "self", [trig(trigger, payload, **flags)], up_cost=up_cost)


def st(status, amount, **kw):
    e = {"op": "apply_status", "status": status, "amount": amount}
    e.update(kw)
    return e


CARDS = [
    card("w6_strike", "Strike", "attack", "basic", 1, "enemy", [{"op": "damage", "amount": 6}], [{"op": "damage", "amount": 9}]),
    card("w6_defend", "Defend", "skill", "basic", 1, "self", [{"op": "block", "amount": 5}], [{"op": "block", "amount": 8}]),
    # --- replay_next + autoplay draw_top on one card; Echo Form + a return_to_hand card; to_draw_top + Havoc ---
    card("w6_echo_barrage", "Echo Barrage", "skill", "uncommon", 1, "self",
         [{"op": "replay_next", "card_type": "attack", "count": 1}, {"op": "autoplay", "from": "draw_top"}], up_cost=0),
    card("w6_echo_form", "Echo Form", "power", "rare", 3, "self", [st("echo_form", 1)], up_cost=2),
    card("w6_particle_wall", "Particle Wall", "skill", "uncommon", 1, "self",
         [{"op": "block", "amount": 7}, {"op": "return_to_hand"}], [{"op": "block", "amount": 10}, {"op": "return_to_hand"}]),
    card("w6_make_it_so", "Make It So", "attack", "rare", 1, "enemy",
         [{"op": "damage", "amount": 6}, {"op": "to_draw_top"}], [{"op": "damage", "amount": 9}, {"op": "to_draw_top"}]),
    card("w6_havoc", "Havoc", "skill", "common", 1, "self", [{"op": "autoplay", "from": "draw_top"}], up_cost=0),
    # --- add_random_card + on_card_generated + cost_delta on:drawn ---
    card("w6_spark_foundry", "Spark Foundry", "skill", "uncommon", 2, "self",
         [{"op": "add_random_card", "card_type": "attack", "pile": "hand", "free_this_turn": True},
          {"op": "cost_delta", "on": "drawn", "scope": "combat", "amount": -1}],
         [{"op": "add_random_card", "card_type": "attack", "pile": "hand", "free_this_turn": True},
          {"op": "cost_delta", "on": "drawn", "scope": "combat", "amount": -1}]),
    power("w6_arsenal", "Arsenal", "rare", 1, "on_card_generated", [{"op": "block", "amount": 1}]),
    # --- stun (all guard rails) + retrieve_card pile:"discard" + Calculated Gamble ---
    card("w6_whistle", "Whistle", "attack", "uncommon", 3, "enemy",
         [{"op": "damage", "amount": 18}, {"op": "stun"}, {"op": "exhaust"}],
         [{"op": "damage", "amount": 24}, {"op": "stun"}, {"op": "exhaust"}]),
    card("w6_second_look", "Second Look", "skill", "uncommon", 1, "self",
         [{"op": "retrieve_card", "pile": "discard", "cards": "choose"}, {"op": "draw", "amount": 1}],
         [{"op": "retrieve_card", "pile": "discard", "cards": "choose"}, {"op": "draw", "amount": 2}]),
    card("w6_calculated_gamble", "Calculated Gamble", "skill", "uncommon", 0, "self",
         [{"op": "discard", "cards": "all"}, {"op": "draw", "amount": 1, "scale": "cards_removed"}, {"op": "exhaust"}],
         [{"op": "discard", "cards": "all"}, {"op": "draw", "amount": 1, "scale": "cards_removed"}]),
    # --- Fiend Fire + target_killed payoff + Doom + target_status_stacks doom ---
    card("w6_fiend_fire", "Fiend Fire", "attack", "rare", 2, "enemy",
         [{"op": "exhaust_card", "cards": "all"}, {"op": "damage", "amount": 7, "hits_scale": "cards_removed"},
          {"op": "heal", "amount": 3, "when": KILLED}, {"op": "exhaust"}],
         [{"op": "exhaust_card", "cards": "all"}, {"op": "damage", "amount": 10, "hits_scale": "cards_removed"},
          {"op": "heal", "amount": 4, "when": KILLED}, {"op": "exhaust"}]),
    card("w6_death_knell", "Death Knell", "skill", "uncommon", 1, "enemy", [st("doom", 7)], [st("doom", 9)]),
    card("w6_doom_reaper", "Doom Reaper", "attack", "rare", 1, "enemy",
         [{"op": "damage", "amount": 1, "scale": "target_status_stacks", "status": "doom"},
          {"op": "gain_energy", "amount": 1, "when": KILLED}],
         [{"op": "damage", "amount": 1, "scale": "target_status_stacks", "status": "doom"},
          {"op": "gain_energy", "amount": 2, "when": KILLED}]),
    # --- every_n + this_turn reactive + on_debuff_applied that_enemy + Strength Down ---
    card("w6_fury_rhythm", "Fury Rhythm", "skill", "common", 1, "self",
         [trig("on_card_played", [{"op": "block", "amount": 3}], card_type="attack", scope="this_turn", every_n=2)],
         [trig("on_card_played", [{"op": "block", "amount": 4}], card_type="attack", scope="this_turn", every_n=2)]),
    power("w6_knife_juggler", "Knife Juggler", "uncommon", 1, "on_card_played",
          [{"op": "damage", "amount": 4, "target": "random_enemy"}], card_type="attack", every_n=3),
    power("w6_sapping_echo", "Sapping Echo", "uncommon", 1, "on_debuff_applied",
          [st("temp_strength_down", 1, target="that_enemy")]),
    card("w6_sapping_hex", "Sapping Hex", "skill", "uncommon", 1, "enemy",
         [st("strength_down", 2), st("temp_strength_down", 3), {"op": "exhaust"}],
         [st("strength_down", 3), st("temp_strength_down", 4), {"op": "exhaust"}]),
    # --- block_next_turn scale:block + retain_hand + no_draw ---
    card("w6_bunker_down", "Bunker Down", "skill", "uncommon", 2, "self",
         [{"op": "block", "amount": 8}, {"op": "block_next_turn", "amount": 1, "scale": "block"}, {"op": "retain_hand"}],
         [{"op": "block", "amount": 11}, {"op": "block_next_turn", "amount": 1, "scale": "block"}, {"op": "retain_hand"}]),
    card("w6_battle_trance", "Battle Trance", "skill", "uncommon", 0, "self",
         [{"op": "draw", "amount": 3}, st("no_draw", 1)], [{"op": "draw", "amount": 4}, st("no_draw", 1)]),
    # --- grant_keyword sly + on_shuffle with a thin deck ---
    card("w6_snap", "Snap", "attack", "common", 1, "enemy",
         [{"op": "damage", "amount": 7}, {"op": "grant_keyword", "keyword": "sly", "cards": "choose"}],
         [{"op": "damage", "amount": 10}, {"op": "grant_keyword", "keyword": "sly", "cards": "choose"}]),
    power("w6_turning_tide", "Turning Tide", "uncommon", 1, "on_shuffle", [{"op": "block", "amount": 3}]),
    # --- Rolling Boulder + a turn_start add_random_card payload ---
    power("w6_rolling_boulder", "Rolling Boulder", "rare", 3, "turn_start",
          [{"op": "damage", "amount": 4, "grow": 4, "target": "all_enemies"}], up_cost=2),
    power("w6_creative_spark", "Creative Spark", "rare", 3, "turn_start",
          [{"op": "add_random_card", "card_type": "power", "pile": "hand"}], up_cost=2),
    # --- the one BQ card (a normal class with orb slots, the BK precedent) ---
    card("w6_static_coil", "Static Coil", "attack", "uncommon", 1, "enemy",
         [{"op": "damage", "amount": 4}, {"op": "channel_orb", "orb": "lightning"}, {"op": "trigger_passive", "amount": 1}],
         [{"op": "damage", "amount": 6}, {"op": "channel_orb", "orb": "lightning"}, {"op": "trigger_passive", "amount": 1}]),
    # --- run completion: a Strength + Block ramp ---
    power("w6_war_drum", "War Drum", "rare", 1, "turn_start",
          [{"op": "apply_status", "status": "strength", "amount": 1}, {"op": "block", "amount": 4}]),
]
# Combinations the validators rejected while this tester was written (card id -> the validator's reason). Recorded, not forced.
REJECTED: dict[str, str] = {}
# every card once, a second Strike (27 cards — "thin" relative to the draw / discard / shuffle churn of this deck).
DECK = {"w6_strike": 2}

CHARACTER = {
    "name": "Wave6 Interaction Tester",
    "description": "Wave 6 (v61-v70) interaction tester: replay + autoplay, Echo Form + return to hand, put-back + Havoc, "
                   "generated cards + cost changes, stun + tutor + Calculated Gamble, Fiend Fire + on-kill + Doom, reactive "
                   "debuff loops, retained hands, Sly grants + shuffles, Rolling Boulder + a card generator.",
    "max_hp": 100, "max_energy": 3, "orb_slots": 3,
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
        r = v.validate(dict(c))
        if not r.ok:
            bad += 1
            if verbose:
                print(f"INVALID {c['id']}: {r.errors}")
    # the class-level stun rails (one stun card per class, nothing re-buys it) hold for the tester too
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
        print(f"{len(CARDS)} cards valid ({len(REJECTED)} combinations rejected by the validators, recorded in REJECTED)")
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
    print("\nnow:  uv run btsgen-autoslay-smoke --seeds GAPTESTW61 GAPTESTW62 --character class4 --relic auto --timeout 1500")
    print("then: uv run python tests/gaptest-wave6/build_tester.py --remove")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
