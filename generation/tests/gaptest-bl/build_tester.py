"""Phase BL Gap Tester — enemy Strength loss, strip Block / Artifact, Doom (vocab v64, gaps #66 / #67).

    cd generation
    uv run python tests/gaptest-bl/build_tester.py --validate-only   # validate the cards only (no game dir touched)
    uv run python tests/gaptest-bl/build_tester.py                   # validates, backs up slot 04, stages the tester there
    uv run python tests/gaptest-bl/build_tester.py --remove          # restores whatever slot 04 held before
    uv run python tests/gaptest-bl/build_tester.py --with-artifact-op   # ALSO stage Warding Gift (needs an OLD DLL, below)
    uv run btsgen-autoslay-smoke --seeds GAPTESTBL1 GAPTESTBL2 --character class4 --relic auto --timeout 900

The deck (slot 04, an all-aggression class, 16 cards):
  * Shrill Keening (x2) — Piercing Wail: temp_strength_down 6 to ALL enemies      [BL] temp_strength_down +N / expired
  * Iron Fetters        — Dark Shackles: temp_strength_down 9 to one enemy        (same tags; the single-target form)
  * Sapping Hex         — Malaise: strength_down 2 (permanent, the -N literal)    [BL] strength_down -N
  * Lay Bare            — Expose: strip_block, strip_artifact, then Vulnerable 2   [BL] strip_block / [BL] strip_artifact
  * Death Knell         — a Doom stacker: Doom 9                                   [BL] doom +N (… doomed=<bool>)
  * Reckoning Hour      — Time's Up: damage = target_status_stacks status doom     ([BJ] scale target_status_stacks)
  * Blighted Edge       — Blight Strike: 8 damage, then Doom = unblocked dealt     [BL] doom from unblocked <n>
  * Final Rites         — 5 damage, draw 1 if the enemy has doom (condition phrase "the enemy has doom")
  * Plague Kiss         — Doom 3 then spread_debuffs (Doom + Strength Down are debuffs: decision 12)
  * Doom Bell (Power)   — turn_start: apply 3 Doom to ALL enemies (the payload path; also the merchant's Power)
  * Warding Gift (TEST) — innate 0-cost: gaptest_enemy_artifact 2 on ALL enemies   [BL] gaptest: '<m>' gains Artifact
                          ONLY with --with-artifact-op (default OFF). A GAPTEST-ONLY op (not in the LLM contract, like
                          apply_custom), skipped by the Python validator here. **The op was STRIPPED from the engine
                          for the v0.4.0 release** (DataCard / EffectRunner / ForgedCards, 2026-10-05): the sign-flip
                          proof lives in godot_BL_tags_GAPTESTBL1/2.txt, which test_phase_bl asserts. A shipped DLL
                          rejects the card, so --with-artifact-op needs a DLL built from a commit that still has the
                          op (0792e7a or earlier on `wave6`). Without it the deck is 15 cards and the artifact check
                          only fires if a later-act Artifact monster (Chomper / Punch Construct) shows up.

THE ARTIFACT CHECK (the wave's sign-flip risk; as run for the saved tag files, WITH the op). Warding Gift is Innate, so every combat opens with 2 Artifact on
every enemy; the debuffs played after it in the same turn eat those stacks first. When a Strength Down is the one
eaten, the engine logs
    [BL] artifact check: '<monster>' Artifact <a> blocked temp_strength_down, Str now <s> (shell 0->0).
That line proves the fix: the Debuff-typed shell (ForgedTempStrengthDownPower.Type) was negated WHOLE — Strength
unchanged and NO shell left on the enemy — so nothing can restore +N at its turn end. (Had the shell stayed a Buff,
the line would read "shell 0->N" and a "[BL] temp_strength_down expired (Str now s+N)" would follow for that monster.)
Act-1 monsters do not carry Artifact reliably (Chomper / Punch Construct live in later acts), hence the injection.

Tags: [BL] temp_strength_down +N on '<monster>' (Str now <s>) · [BL] temp_strength_down expired (Str now <s>) ·
[BL] strength_down -N on '<monster>' (Str now <s>) · [BL] strip_block <b>->0 on '<monster>' ·
[BL] strip_artifact (had <n>) on '<monster>' · [BL] doom +N on '<monster>' (HP <hp>, Doom <d>, doomed=<bool>) ·
[BL] doom from unblocked <n> · [BL] artifact check: '<monster>' Artifact <a> blocked strength_down, Str now <s>.

Pass bar (plan rule 0.3): every tag above fires on at least one seed — the artifact check at least once for
temp_strength_down with "shell 0->0" — strip_artifact at least once with had > 0, doom at least once with
doomed=True or a Doom kill; 0 mod exceptions, no BlankTheSpire frame in a stall stack, 0 "Localization formatting
error". The saved tag greps live next to this file as godot_BL_tags_<SEED>.txt (TEST_AUDIT_2026-10 §7).
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
BAK_SUFFIX = ".blgaptestbak"
CH = "bl_gap_tester"
# Cards carrying the GAPTEST-ONLY op (not in the LLM contract): the Python validator would reject the op, the in-game
# importer accepts it. Validated by the engine at import instead.
GAPTEST_ONLY = {"bl_warding_gift"}


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


CARDS = [
    card("bl_strike", "Strike", "attack", "basic", 1, "enemy", [{"op": "damage", "amount": 6}], [{"op": "damage", "amount": 9}]),
    card("bl_defend", "Defend", "skill", "basic", 1, "self", [{"op": "block", "amount": 5}], [{"op": "block", "amount": 8}]),
    card("bl_shrill_keening", "Shrill Keening", "skill", "common", 1, "all_enemies",
         [st("temp_strength_down", 6)], [st("temp_strength_down", 8)]),
    card("bl_iron_fetters", "Iron Fetters", "skill", "uncommon", 1, "enemy",
         [st("temp_strength_down", 9), {"op": "exhaust"}], [st("temp_strength_down", 9)]),
    card("bl_sapping_hex", "Sapping Hex", "skill", "uncommon", 1, "enemy",
         [st("strength_down", 2), {"op": "exhaust"}], [st("strength_down", 3), {"op": "exhaust"}]),
    card("bl_lay_bare", "Lay Bare", "skill", "uncommon", 1, "enemy",
         [{"op": "strip_block"}, {"op": "strip_artifact"}, st("vulnerable", 2)],
         [{"op": "strip_block"}, {"op": "strip_artifact"}, st("vulnerable", 3)]),
    card("bl_death_knell", "Death Knell", "skill", "uncommon", 1, "enemy", [st("doom", 9)], [st("doom", 9)], up_cost=0),
    card("bl_reckoning_hour", "Reckoning Hour", "attack", "rare", 1, "enemy",
         [{"op": "damage", "amount": 1, "scale": "target_status_stacks", "status": "doom"}],
         [{"op": "damage", "amount": 1, "scale": "target_status_stacks", "status": "doom"}], up_cost=0),
    card("bl_blighted_edge", "Blighted Edge", "attack", "uncommon", 1, "enemy",
         [{"op": "damage", "amount": 8}, st("doom", 1, scale="damage_dealt_unblocked")],
         [{"op": "damage", "amount": 11}, st("doom", 1, scale="damage_dealt_unblocked")]),
    card("bl_final_rites", "Final Rites", "attack", "common", 1, "enemy",
         [{"op": "damage", "amount": 5}, {"op": "draw", "amount": 1, "when": {"kind": "target_has_status", "status": "doom"}}],
         [{"op": "damage", "amount": 7}, {"op": "draw", "amount": 1, "when": {"kind": "target_has_status", "status": "doom"}}]),
    card("bl_plague_kiss", "Plague Kiss", "skill", "uncommon", 1, "enemy",
         [st("doom", 3), {"op": "spread_debuffs"}], [st("doom", 5), {"op": "spread_debuffs"}]),
    card("bl_doom_bell", "Doom Bell", "power", "rare", 1, "self",
         [{"op": "add_trigger", "trigger": "turn_start", "effects": [st("doom", 3, target="all_enemies")]}], up_cost=0),
]
# The Artifact injection card (GAPTEST-only op, stripped from the engine for v0.4.0) — staged only with
# --with-artifact-op, on a DLL that still carries the op (see the docstring).
ARTIFACT_OP_CARD = card("bl_warding_gift", "Warding Gift", "skill", "common", 0, "all_enemies",
                        [{"op": "gaptest_enemy_artifact", "amount": 2}, {"op": "innate"}])


def cards_for(with_artifact_op: bool = False) -> list[dict]:
    return CARDS + [ARTIFACT_OP_CARD] if with_artifact_op else list(CARDS)


# slot -> count (1-based card order). 16 cards; every BL card at least once, the Piercing Wail form doubled.
DECK = {"bl_strike": 2, "bl_defend": 2, "bl_shrill_keening": 2}

CHARACTER = {
    "name": "BL Gap Tester",
    "description": "Phase BL (v64) tester: enemy Strength loss (Piercing Wail / Dark Shackles / Malaise), Expose "
                   "(strip Block / Artifact), Doom (stacker, Blight Strike, Time's Up, payload, spread) and the "
                   "Artifact sign-flip check.",
    "max_hp": 80, "max_energy": 3,
    "starting_deck": [{"slot": n, "count": DECK.get(c["id"], 1)} for n, c in enumerate(CARDS, start=1)],
}


def character_for(cards: list[dict]) -> dict:
    ch = dict(CHARACTER)
    ch["starting_deck"] = [{"slot": n, "count": DECK.get(c["id"], 1)} for n, c in enumerate(cards, start=1)]
    return ch


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


def validate(verbose: bool = True, cards: list[dict] | None = None) -> int:
    cards = CARDS if cards is None else cards
    v = CardValidator()
    v.known_cards |= {c["id"] for c in cards}
    bad = 0
    for c in cards:
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
    cards = cards_for("--with-artifact-op" in argv)
    character = character_for(cards)
    gaptest = sum(1 for c in cards if c["id"] in GAPTEST_ONLY)
    if validate(cards=cards):
        return 1
    if "--validate-only" in argv or "--check" in argv:  # validate only (no game dir touched)
        print(f"{len(cards) - gaptest} cards valid (+{gaptest} gaptest-only card, needs a pre-v0.4.0 DLL)")
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
    char_json.write_text(json.dumps(character, indent=2, ensure_ascii=False), encoding="utf-8")
    for n, c in enumerate(cards, start=1):
        (cards_dir / f"{n:02d}.json").write_text(json.dumps(c, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"staged slot {SLOT:02d}: {character['name']} + {len(cards)} cards "
          f"({sum(s['count'] for s in character['starting_deck'])} in the starting deck)")
    print("\nnow:  uv run btsgen-autoslay-smoke --seeds GAPTESTBL1 GAPTESTBL2 --character class4 --relic auto --timeout 900")
    print("then: uv run python tests/gaptest-bl/build_tester.py --remove")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
