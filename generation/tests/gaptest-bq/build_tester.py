"""Phase BQ Gap Tester — orb extras (vocab v68, gap #78) + the BP `on_evoke` trigger, on an ORB class.

COMPLETE SMOKE RECIPE (the BN agent runs this together with BN's smoke; Ryan pre-approved it). Close the game first.

    cd generation
    uv run python tests/gaptest-bq/build_tester.py --validate-only   # validate the cards + orb pool only (no game dir touched)
    ~/.dotnet/dotnet.exe build ../mod/BlankTheSpire.csproj -c Debug  # (or pass --build to the smoke) — the v68 DLL must be deployed
    uv run python tests/gaptest-bq/build_tester.py                   # validates, backs up slot 04, stages the tester there
    uv run btsgen-autoslay-smoke --seeds GAPTESTBQ1 GAPTESTBQ2 --character class4 --relic auto --timeout 900
    uv run python tests/gaptest-bq/build_tester.py --remove          # restores whatever slot 04 held before

Character slot: the tester is staged into forged slot 04 and run with `--character class4` (the same slot / flag every
earlier orb tester used: gaptest-ar staged its Glass Cannon orb class into slot 04 and ran `--character class4`; gaptest-bk
ran an orb_slots-3 class from slot 04 the same way). The class declares `orb_slots: 4` and an `orb_pool` of the three base
orbs plus two CUSTOM orbs (Ember: passive 3 damage / evoke 7 to ALL; Bulwark: passive 3 Block / evoke 8 Block) so the new
ForgedOrb.Passive override has custom orbs to answer for (the base orbs answer OrbCmd.Passive on their own).

The deck (slot 04, every BQ card once + two Strikes; channel-heavy so the rack fills and evokes happen every fight):
  * Twin Cast        — Dualcast: evoke keep (EvokeNext dequeue:false, then EvokeNext)   [BQ] evoke next keep=true -> '<orb>'
  * Last Spark       — evoke which newest (OrbCmd.EvokeLast) + 5 Block                   [BQ] evoke newest keep=false -> '<orb>'
  * Night Pulse      — Darkness-lite: channel Ember, trigger_passive x2 on your NEXT orb [BQ] trigger_passive x2 on '<orb>' (orbs=first)
  * Coil Lash        — Tesla-Coil-lite: 0-cost 3 damage, trigger_passive x1 on ALL orbs [BQ] trigger_passive x1 on '<orb>' (orbs=all)
  * Feedback Loop    — Loop power: apply_status loop 1 (the base LoopPower)              [BQ] loop applied by 'Feedback Loop'
                       each later turn start (LoopTickTagPatch, log-only Harmony prefix)  [BQ] loop tick -> '<front orb>' x<n>
  * a custom orb answering OrbCmd.Passive (Loop / trigger_passive on Ember or Bulwark)    [BQ] passive override: '<orb>' passive via OrbRunner
  * Overclock        — Bulk Up-lite power: lose_orb_slot + 2 Strength + 2 Dexterity      [BQ] lose_orb_slot -> <cap> (4 -> 3)
  * Compile Driver   — 7 damage + draw = the DIFFERENT orbs you have (scale orb_types)   [BQ] orb_types -> <n> ('Compile Driver') (draw)
  * Rack Slam        — damage = the orbs you have (scale orb_count)                      [BQ] orb_count -> <n> ('Rack Slam') (damage)
  * Frost Ward       — 6 Block + draw 1 if you have 2+ Frost orbs (base-name filter)     [BQ] orb_count_ge[frost] -> <true|false>
  * Ember Brand      — 6 damage + 2 Vulnerable if you have 1+ Ember orbs (CUSTOM filter) [BQ] orb_count_ge[ember] -> <true|false>
  * Cold Snap        — Chill: channel a Frost orb for each enemy (per_enemy), Exhaust    [BQ] channel per_enemy x<n>
  * Arc Recoil       — the BP on_evoke power: whenever you Evoke an orb, deal 3 damage to a random enemy
                                                                                          [BP] on_evoke fired ('Arc Recoil': <OrbType>)
  * channel fuel: Static Tap (0-cost Lightning), Ember Call (Ember + 3 Block), Roulette (2 random pool orbs), Surge (6 damage +
    a Bulwark); War Drum (turn_start +1 Strength, 4 Block — the BO/BP run-completion fix); max HP 100.

Pass bar (plan rule 0.3), across the two seeds:
  - EVERY tag above fires at least once: evoke keep=true, evoke newest, trigger_passive (orbs=first) AND (orbs=all), loop
    applied, loop tick, passive override (a custom orb), lose_orb_slot -> <cap>, orb_types ->, orb_count ->,
    orb_count_ge[frost] AND orb_count_ge[ember] (both true and false outcomes expected over a run), channel per_enemy x<n>
    (x1 and x2+ when a fight has several enemies), and [BP] on_evoke fired — this tester is BP's on_evoke proof.
  - NO DOUBLE-FIRE: every "[BQ] passive override: '<orb>'" line follows a "[BQ] trigger_passive … on '<orb>'" or
    "[BQ] loop tick -> '<orb>'" line for the SAME custom orb (Ember / Bulwark) — the per-turn tick calls OrbRunner.RunPassive
    directly and logs no [BQ] line, so a passive-override count above (trigger_passive times + loop ticks on a custom orb)
    would be a double fire.
  - 0 mod exceptions, no BlankTheSpire frame in a stall stack, 0 "Localization formatting error" (Loop's card text is literal;
    the LoopPower hover tip is the base game's own loc).
  - Map-nav FAIL is expected (AutoSlay verdict); gate on the godot.log tags. Known non-mod failures: the Steam relaunch race
    (the second seed never reaches the game -> re-run it alone) and the Phase BM Act-3 whole-process freeze (unreproduced).
  - AutoSlay never pays energy (CardCmd.AutoPlay), which does not matter here (no cost reads in BQ).
Save the per-seed tag grep next to this file as godot_BQ_tags_<SEED>.txt (TEST_AUDIT_2026-10 §7), in the format of
tests/gaptest-bp/godot_BP_tags_<SEED>.txt: a header (`# [BQ] lines: N`, `# mod exceptions: 0`, `# BlankTheSpire stack
frames: 0`, `# Localization formatting errors: 0`, the run end line), per-tag counts, then the [BQ] + "[BP] on_evoke fired"
lines. test_phase_bq reads them (until they exist it prints "smoke pending").
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
from btsgen.class_forge import _validate_orb_pool  # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402

SLOT = 4
ROOT = game_paths.game_user_dir() / "forged" / "characters"
BAK_SUFFIX = ".bqgaptestbak"
CH = "bq_gap_tester"
ORB_SLOTS = 4

ORB_POOL = [
    "lightning", "frost", "dark",
    {"name": "Ember", "passive_val": 3, "evoke_val": 7, "hue": 0.04,
     "description": "Sears an enemy each turn; bursts over ALL enemies on evoke.",
     "passive": [{"op": "damage", "amount": 3, "target": "enemy"}],
     "evoke": [{"op": "damage", "amount": 7, "target": "all_enemies"}]},
    {"name": "Bulwark", "passive_val": 3, "evoke_val": 8, "hue": 0.6,
     "description": "Shields you each turn; a big wall on evoke.",
     "passive": [{"op": "block", "amount": 3}],
     "evoke": [{"op": "block", "amount": 8}]},
]


def card(cid, name, ctype, rarity, cost, target, effects, upgrade=None, up_cost=None):
    c = {"id": cid, "name": name, "type": ctype, "rarity": rarity, "cost": cost, "target": target,
         "source": "llm", "character": CH, "effects": effects, "upgrade": {"effects": upgrade or effects}}
    if up_cost is not None:
        c["upgrade"]["cost"] = up_cost
    return c


def power(cid, name, rarity, cost, effects, upgrade=None, up_cost=None):
    return card(cid, name, "power", rarity, cost, "self", effects, upgrade, up_cost)


CARDS = [
    card("bq_strike", "Strike", "attack", "basic", 1, "enemy", [{"op": "damage", "amount": 6}], [{"op": "damage", "amount": 9}]),
    card("bq_defend", "Defend", "skill", "basic", 1, "self", [{"op": "block", "amount": 5}], [{"op": "block", "amount": 8}]),
    # --- the BQ cards ---
    card("bq_twin_cast", "Twin Cast", "skill", "uncommon", 1, "self", [{"op": "evoke", "keep": True}], up_cost=0),
    card("bq_last_spark", "Last Spark", "skill", "common", 1, "self",
         [{"op": "evoke", "which": "newest"}, {"op": "block", "amount": 5}],
         [{"op": "evoke", "which": "newest"}, {"op": "block", "amount": 8}]),
    card("bq_night_pulse", "Night Pulse", "skill", "uncommon", 1, "self",
         [{"op": "channel_orb", "orb": "ember"}, {"op": "trigger_passive", "amount": 2}],
         [{"op": "channel_orb", "orb": "ember"}, {"op": "trigger_passive", "amount": 3}]),
    card("bq_coil_lash", "Coil Lash", "attack", "uncommon", 0, "enemy",
         [{"op": "damage", "amount": 3}, {"op": "trigger_passive", "orbs": "all", "amount": 1}],
         [{"op": "damage", "amount": 4}, {"op": "trigger_passive", "orbs": "all", "amount": 1}]),
    power("bq_feedback_loop", "Feedback Loop", "uncommon", 1, [{"op": "apply_status", "status": "loop", "amount": 1}], up_cost=0),
    power("bq_overclock", "Overclock", "uncommon", 2,
          [{"op": "lose_orb_slot"}, {"op": "apply_status", "status": "strength", "amount": 2},
           {"op": "apply_status", "status": "dexterity", "amount": 2}],
          [{"op": "lose_orb_slot"}, {"op": "apply_status", "status": "strength", "amount": 3},
           {"op": "apply_status", "status": "dexterity", "amount": 3}]),
    card("bq_compile_driver", "Compile Driver", "attack", "common", 1, "enemy",
         [{"op": "damage", "amount": 7}, {"op": "draw", "amount": 1, "scale": "orb_types"}],
         [{"op": "damage", "amount": 10}, {"op": "draw", "amount": 1, "scale": "orb_types"}]),
    card("bq_rack_slam", "Rack Slam", "attack", "common", 1, "enemy",
         [{"op": "damage", "amount": 1, "scale": "orb_count"}], up_cost=0),
    card("bq_frost_ward", "Frost Ward", "skill", "common", 1, "self",
         [{"op": "block", "amount": 6}, {"op": "draw", "amount": 1, "when": {"kind": "orb_count_ge", "value": 2, "orb": "frost"}}],
         [{"op": "block", "amount": 9}, {"op": "draw", "amount": 1, "when": {"kind": "orb_count_ge", "value": 2, "orb": "frost"}}]),
    card("bq_ember_brand", "Ember Brand", "attack", "common", 1, "enemy",
         [{"op": "damage", "amount": 6},
          {"op": "apply_status", "status": "vulnerable", "amount": 2, "when": {"kind": "orb_count_ge", "value": 1, "orb": "ember"}}],
         [{"op": "damage", "amount": 9},
          {"op": "apply_status", "status": "vulnerable", "amount": 2, "when": {"kind": "orb_count_ge", "value": 1, "orb": "ember"}}]),
    card("bq_cold_snap", "Cold Snap", "skill", "uncommon", 0, "self",
         [{"op": "channel_orb", "orb": "frost", "per_enemy": True}, {"op": "exhaust"}],
         [{"op": "channel_orb", "orb": "frost", "per_enemy": True}]),
    # --- the BP on_evoke proof (orb classes only; the BP normal-class tester could not channel) ---
    power("bq_arc_recoil", "Arc Recoil", "uncommon", 1,
          [{"op": "add_trigger", "trigger": "on_evoke", "effects": [{"op": "damage", "amount": 3, "target": "random_enemy"}]}]),
    # --- channel fuel ---
    card("bq_static_tap", "Static Tap", "skill", "common", 0, "self",
         [{"op": "channel_orb", "orb": "lightning"}], [{"op": "channel_orb", "orb": "lightning", "amount": 2}]),
    card("bq_ember_call", "Ember Call", "skill", "common", 1, "self",
         [{"op": "channel_orb", "orb": "ember"}, {"op": "block", "amount": 3}],
         [{"op": "channel_orb", "orb": "ember"}, {"op": "block", "amount": 6}]),
    card("bq_roulette", "Roulette", "skill", "uncommon", 1, "self",
         [{"op": "channel_orb", "orb": "random", "amount": 2}], [{"op": "channel_orb", "orb": "random", "amount": 3}]),
    card("bq_surge", "Surge", "attack", "common", 1, "enemy",
         [{"op": "damage", "amount": 6}, {"op": "channel_orb", "orb": "bulwark"}],
         [{"op": "damage", "amount": 9}, {"op": "channel_orb", "orb": "bulwark"}]),
    # --- run completion (the BO / BP lesson): a Strength + Block ramp ---
    power("bq_war_drum", "War Drum", "rare", 1,
          [{"op": "add_trigger", "trigger": "turn_start",
            "effects": [{"op": "apply_status", "status": "strength", "amount": 1}, {"op": "block", "amount": 4}]}]),
]
# slot -> count (1-based card order): every card once, two Strikes (20 cards).
DECK = {"bq_strike": 2}

CHARACTER = {
    "name": "BQ Gap Tester",
    "description": "Phase BQ (v68) tester: an orb class with base + custom orbs — Dualcast, the newest evoke, Darkness / "
                   "Tesla Coil passive triggers, Loop, Bulk Up's slot loss, Compile Driver / orb-count scales, typed orb "
                   "gates, Chill — plus the BP on_evoke power.",
    "max_hp": 100, "max_energy": 3, "orb_slots": ORB_SLOTS,
    "orb_pool": ORB_POOL,
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
    bad = 0
    perrs = _validate_orb_pool(ORB_POOL, ORB_SLOTS)
    if perrs:
        bad += 1
        if verbose:
            print(f"INVALID orb_pool: {perrs}")
    v = CardValidator(extra_orbs={o["name"].lower() for o in ORB_POOL if isinstance(o, dict)})
    v.known_cards |= {c["id"] for c in CARDS}
    for c in CARDS:
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
        print(f"{len(CARDS)} cards valid (orb pool: {', '.join(o if isinstance(o, str) else o['name'] for o in ORB_POOL)})")
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
    print("\nnow:  uv run btsgen-autoslay-smoke --seeds GAPTESTBQ1 GAPTESTBQ2 --character class4 --relic auto --timeout 900")
    print("then: uv run python tests/gaptest-bq/build_tester.py --remove")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
