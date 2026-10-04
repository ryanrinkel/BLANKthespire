"""Phase BM Gap Tester — base-power statuses: self-drawbacks, replay, next-turn Block, retain hand (vocab v65,
gaps #68 / #69 / #70).

    cd generation
    uv run python tests/gaptest-bm/build_tester.py --validate-only   # validate the cards only (no game dir touched)
    uv run python tests/gaptest-bm/build_tester.py                   # validates, backs up slot 04, stages the tester there
    uv run python tests/gaptest-bm/build_tester.py --remove          # restores whatever slot 04 held before
    uv run btsgen-autoslay-smoke --seeds GAPTESTBM1 GAPTESTBM2 --character class4 --relic auto --timeout 900

The deck (slot 04, a normal class, 22 cards; Skill-heavy so Burst / Echo Form have something to replay):
  * Battle Trance       — draw 3, then no_draw (NoDrawPower)                     [BM] self-debuff no_draw +1 on player
  * Expect a Fight      — gain 2 energy, then no_energy_gain (NoEnergyGainPower)  [BM] self-debuff no_energy_gain +1
  * Panic Button        — 16 Block, no_block_gain 2 (NoBlockPower), exhaust      [BM] self-debuff no_block_gain +2
  * Wraith Form (Power) — Intangible 2 + dex_decay 1 (WraithFormPower)           [BM] self-debuff dex_decay +1 /
                                                                                  [BM] decay tick dex_decay -1
  * Shared Fate         — the enemy loses 2 Strength, you lose 2 (lose_strength) [BM] self-debuff lose_strength +2
  * Reckless Lunge      — 11 damage, lose 1 Dexterity (lose_dexterity)          [BM] self-debuff lose_dexterity +1
  * Burst (x2)          — replay_next skill x2 (BurstPower)                      [BM] replay_next skill x2 +
                                                                                  [BM] replay play #2 of '<card>'
  * One-Two Punch       — replay_next attack x1 (OneTwoPunchPower) + draw 1      [BM] replay_next attack x1
  * Signal Flare        — replay_next power x1 (SignalBoostPower) + draw 1       [BM] replay_next power x1
  * Doubletake (rare)   — replay_next all x1 (DuplicationPower)                  [BM] replay_next all x1
  * Echo Form (Power)   — echo_form 1 (EchoFormPower)                            [BM] echo_form applied
  * Banked Wall         — 5 Block + block_next_turn 6 (fixed)                    [BM] block_next_turn +6 (scale=fixed)
  * Prolong             — 5 Block + block_next_turn scale block                  [BM] block_next_turn +N (scale=block)
  * Equilibrium         — 12 Block + retain_hand (RetainHandPower)               [BM] retain_hand
  * Quick Hands         — cost_shift skill -1 for the next 2 Skills + draw 1     ([AO] cost_shift; a replayed Skill logs
                                                                                  [BM] cost_shift: replay #2 ... burns no
                                                                                  discount use — the PlayIndex decision)
  * Twin Jab / Heavy Swing — plain non-basic attacks (the merchant stall's three Attacks with Reckless Lunge)

What the smoke CAN'T prove: AutoSlay plays every card through CardCmd.AutoPlay and never pays energy, so
`no_energy_gain` is proven APPLIED (the tag + the power on the player), never as a denied gain; Focus drawbacks
(`focus_decay` / `lose_focus`) are orb-class tokens and stay offline-only here (the engine path is the same literal
ApplyBmSelfStatus as the other six).

Tags: [BM] self-debuff <status> +N on player (Artifact <a>) · [BM] replay_next <kind> x<n> · [BM] replay play #<k> of
'<card>' · [BM] echo_form applied · [BM] block_next_turn +<n> (scale=<block|fixed>) · [BM] retain_hand ·
[BM] decay tick dex_decay -N · (opportunistic) [BM] cost_shift: replay #<k> of '<card>' burns no discount use.

Pass bar (plan rule 0.3): across the two seeds every tag above fires at least once — self-debuff for each of no_draw /
no_energy_gain / no_block_gain / dex_decay / lose_strength / lose_dexterity, replay_next for each of skill / attack /
power / all, a replay play #2, both block_next_turn forms — plus 0 mod exceptions, no BlankTheSpire frame in a stall
stack, 0 "Localization formatting error". The saved tag greps live next to this file as godot_BM_tags_<SEED>.txt
(TEST_AUDIT_2026-10 §7).
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
BAK_SUFFIX = ".bmgaptestbak"
CH = "bm_gap_tester"
GAPTEST_ONLY: set[str] = set()  # every BM card is a real contract card


def card(cid, name, ctype, rarity, cost, target, effects, upgrade=None, up_cost=None):
    c = {"id": cid, "name": name, "type": ctype, "rarity": rarity, "cost": cost, "target": target,
         "source": "llm", "character": CH, "effects": effects, "upgrade": {"effects": upgrade or effects}}
    if up_cost is not None:
        c["upgrade"]["cost"] = up_cost
    return c


def st(status, amount, **kw):
    e = {"op": "apply_status", "status": status, "amount": amount}
    e.update(kw)
    return e


def replay(kind, n):
    return {"op": "replay_next", "card_type": kind, "count": n}


CARDS = [
    card("bm_strike", "Strike", "attack", "basic", 1, "enemy", [{"op": "damage", "amount": 6}], [{"op": "damage", "amount": 9}]),
    card("bm_defend", "Defend", "skill", "basic", 1, "self", [{"op": "block", "amount": 5}], [{"op": "block", "amount": 8}]),
    card("bm_battle_trance", "Battle Trance", "skill", "uncommon", 0, "self",
         [{"op": "draw", "amount": 3}, st("no_draw", 1)], [{"op": "draw", "amount": 4}, st("no_draw", 1)]),
    card("bm_expect_a_fight", "Expect a Fight", "skill", "uncommon", 1, "self",
         [{"op": "gain_energy", "amount": 2}, st("no_energy_gain", 1)], [{"op": "gain_energy", "amount": 3}, st("no_energy_gain", 1)]),
    card("bm_panic_button", "Panic Button", "skill", "uncommon", 0, "self",
         [{"op": "block", "amount": 16}, st("no_block_gain", 2), {"op": "exhaust"}],
         [{"op": "block", "amount": 20}, st("no_block_gain", 2), {"op": "exhaust"}]),
    card("bm_wraith_form", "Wraith Form", "power", "rare", 3, "self",
         [st("intangible", 2), st("dex_decay", 1)], [st("intangible", 3), st("dex_decay", 1)]),
    card("bm_shared_fate", "Shared Fate", "skill", "uncommon", 0, "enemy",
         [st("strength_down", 2), st("lose_strength", 2), {"op": "exhaust"}],
         [st("strength_down", 3), st("lose_strength", 2), {"op": "exhaust"}]),
    card("bm_reckless_lunge", "Reckless Lunge", "attack", "common", 1, "enemy",
         [{"op": "damage", "amount": 11}, st("lose_dexterity", 1)], [{"op": "damage", "amount": 14}, st("lose_dexterity", 1)]),
    card("bm_burst", "Burst", "skill", "uncommon", 1, "self", [replay("skill", 2)], up_cost=0),
    card("bm_one_two_punch", "One-Two Punch", "skill", "uncommon", 1, "self",
         [replay("attack", 1), {"op": "draw", "amount": 1}], [replay("attack", 1), {"op": "draw", "amount": 2}]),
    card("bm_signal_flare", "Signal Flare", "skill", "uncommon", 1, "self",
         [replay("power", 1), {"op": "draw", "amount": 1}], [replay("power", 1), {"op": "draw", "amount": 2}]),
    card("bm_doubletake", "Doubletake", "skill", "rare", 1, "self", [replay("all", 1)], up_cost=0),
    card("bm_echo_form", "Echo Form", "power", "rare", 3, "self", [st("echo_form", 1)], up_cost=2),
    card("bm_banked_wall", "Banked Wall", "skill", "common", 1, "self",
         [{"op": "block", "amount": 5}, {"op": "block_next_turn", "amount": 6}],
         [{"op": "block", "amount": 7}, {"op": "block_next_turn", "amount": 8}]),
    card("bm_prolong", "Prolong", "skill", "uncommon", 1, "self",
         [{"op": "block", "amount": 5}, {"op": "block_next_turn", "amount": 1, "scale": "block"}],
         [{"op": "block", "amount": 8}, {"op": "block_next_turn", "amount": 1, "scale": "block"}]),
    card("bm_equilibrium", "Equilibrium", "skill", "uncommon", 2, "self",
         [{"op": "block", "amount": 12}, {"op": "retain_hand"}], [{"op": "block", "amount": 15}, {"op": "retain_hand"}]),
    card("bm_quick_hands", "Quick Hands", "skill", "common", 1, "self",
         [{"op": "cost_shift", "card_type": "skill", "amount": 1, "scope": "this_turn", "count": 2}, {"op": "draw", "amount": 1}]),
    card("bm_twin_jab", "Twin Jab", "attack", "common", 1, "enemy",
         [{"op": "damage", "amount": 4, "hits": 2}], [{"op": "damage", "amount": 5, "hits": 2}]),
    card("bm_heavy_swing", "Heavy Swing", "attack", "common", 2, "enemy",
         [{"op": "damage", "amount": 13}], [{"op": "damage", "amount": 17}]),
]
# slot -> count (1-based card order). 22 cards; every BM card at least once, Burst doubled (the Skill-heavy replay hand).
DECK = {"bm_strike": 2, "bm_defend": 2, "bm_burst": 2}

CHARACTER = {
    "name": "BM Gap Tester",
    "description": "Phase BM (v65) tester: self-drawbacks (Battle Trance, Expect a Fight, Panic Button, Wraith Form, "
                   "Shared Fate, a lose-Dexterity attack), replays (Burst, One-Two Punch, Signal Flare, Doubletake, Echo "
                   "Form), next-turn Block (fixed + Prolong) and Equilibrium.",
    "max_hp": 80, "max_energy": 3,
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
    print("\nnow:  uv run btsgen-autoslay-smoke --seeds GAPTESTBM1 GAPTESTBM2 --character class4 --relic auto --timeout 900")
    print("then: uv run python tests/gaptest-bm/build_tester.py --remove")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
