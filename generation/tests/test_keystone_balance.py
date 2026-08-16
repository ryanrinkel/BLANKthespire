"""Offline keystone-relic balance-gate tests — no API key needed.

Run:  uv run python -m tests.test_keystone_balance     (from generation/)
Exits nonzero on any failure. Covers class_forge._relic_balance_errors, the deck-aware power
gate (the "Diamond Hands" fix): a `when` condition the generated deck trivially satisfies
(hand_size_ge on a retain-heavy class) is no discount, so it must not unlock an always-on
payout like +1 energy; flat energy modifiers are boss power and never fit the starter budget.
"""
from __future__ import annotations

import sys

from btsgen.class_forge import (_cond_uptime, _keystone_deck_stats, _relic_balance_errors,
                                point_btsgen_at_mod_contract)

point_btsgen_at_mod_contract()  # repoint at the constrained mod contract BEFORE the validator reads paths

from btsgen.validator import CardValidator  # noqa: E402

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


_V = CardValidator()


def _card(cid: str, retain: bool = False) -> dict:
    effects = [{"op": "damage", "amount": 6}]
    if retain:
        effects.append({"op": "retain"})
    return {"id": cid, "name": cid, "type": "attack", "rarity": "common", "cost": 1,
            "effects": effects}


def _made(retain_pool: int, pool: int = 10, retain_basic: bool = False) -> list[dict]:
    """A stage-2.5-shaped card set: 2 basics + 1 signature + `pool` pool cards, `retain_pool`
    of which carry the retain op."""
    out = [{"plan": {"role": "basic_attack"}, "card": _card("basic_a", retain=retain_basic)},
           {"plan": {"role": "basic_skill"}, "card": _card("basic_s")},
           {"plan": {"role": "signature"}, "card": _card("sig")}]
    for i in range(pool):
        out.append({"plan": {"role": "pool"}, "card": _card(f"pool_{i}", retain=i < retain_pool)})
    return out


def _energy_on_hand6() -> dict:
    """The Diamond Hands shape: +1 energy every turn you hold 6+ cards at turn start."""
    return {"id": "dh", "name": "Diamond Hands", "tier": "starter",
            "hooks": [{"trigger": "turn_start", "when": {"kind": "hand_size_ge", "value": 6},
                       "effects": [{"op": "gain_energy", "amount": 1}]}]}


def test_diamond_hands_rejected_on_retain_deck() -> None:
    print("hand_size_ge 6 + gain_energy on a retain-heavy pool -> rejected:")
    errs = _relic_balance_errors(_energy_on_hand6(), _made(retain_pool=5), _V)
    check(bool(errs), "the gate must fire")
    check(errs and "hand_size_ge" in errs[0] and "always true" in errs[0],
          f"the error should name the free condition: {errs}")


def test_same_relic_ok_on_retainless_deck() -> None:
    print("the same relic on a deck with no retain -> a real condition, allowed:")
    errs = _relic_balance_errors(_energy_on_hand6(), _made(retain_pool=0), _V)
    check(not errs, f"hand_size_ge 6 with no retain is a genuine hoop: {errs}")


def test_retain_basic_counts_as_starting_deck() -> None:
    print("one retain BASIC (~5 starting copies) alone frees the condition -> rejected:")
    errs = _relic_balance_errors(_energy_on_hand6(), _made(retain_pool=0, retain_basic=True), _V)
    check(bool(errs), f"a retain basic saturates the starting deck: {errs}")


def test_unconditional_energy_rejected() -> None:
    print("unconditional turn_start gain_energy -> rejected on any deck:")
    relic = {"id": "r", "name": "r", "hooks": [
        {"trigger": "turn_start", "effects": [{"op": "gain_energy", "amount": 1}]}]}
    check(bool(_relic_balance_errors(relic, _made(retain_pool=0), _V)),
          "+1 energy every turn is boss power")


def test_max_energy_modifier_rejected() -> None:
    print("flat max_energy modifier -> rejected (Coffee Dripper is a boss relic):")
    relic = {"id": "r", "name": "r", "modifiers": [{"stat": "max_energy", "amount": 1}]}
    errs = _relic_balance_errors(relic, _made(retain_pool=0), _V)
    check(bool(errs) and "boss-relic" in errs[0], f"should name the flat energy stat: {errs}")


def test_modest_keystones_pass() -> None:
    print("base-game-shaped starters stay inside the budget:")
    ok_relics = [
        {"id": "bb", "name": "bb", "hooks": [  # Burning Blood
            {"trigger": "combat_end", "effects": [{"op": "heal", "amount": 6}]}]},
        {"id": "bk", "name": "bk", "hooks": [  # small per-turn block
            {"trigger": "turn_start", "effects": [{"op": "block", "amount": 3}]}]},
        {"id": "rs", "name": "rs", "hooks": [  # Ring of the Snake: draw 2, first turn only
            {"trigger": "turn_start", "once_per_combat": True,
             "effects": [{"op": "draw", "amount": 2}]}]},
        {"id": "an", "name": "an", "modifiers": [  # Anchor
            {"stat": "start_combat_block", "amount": 10}]},
        {"id": "hb", "name": "hb", "hooks": [  # conditional energy: a genuinely costly condition
            {"trigger": "turn_start", "when": {"kind": "hp_below_half"},
             "effects": [{"op": "gain_energy", "amount": 1}]}]},
    ]
    for r in ok_relics:
        errs = _relic_balance_errors(r, _made(retain_pool=2), _V)
        check(not errs, f"{r['id']} should pass: {errs}")


def test_per_turn_draw_engine_rejected() -> None:
    print("draw 1 EVERY turn (an always-on draw engine) -> rejected, nudged to once_per_combat:")
    relic = {"id": "r", "name": "r", "hooks": [
        {"trigger": "turn_start", "effects": [{"op": "draw", "amount": 1}]}]}
    check(bool(_relic_balance_errors(relic, _made(retain_pool=0), _V)),
          "a permanent +1 draw/turn is over the starter band")


def test_reactive_trigger_priced_per_event() -> None:
    print("on_card_played + gain_energy (a perpetual-motion engine) -> rejected:")
    relic = {"id": "r", "name": "r", "hooks": [
        {"trigger": "on_card_played", "effects": [{"op": "gain_energy", "amount": 1}]}]}
    check(bool(_relic_balance_errors(relic, _made(retain_pool=0), _V)),
          "per-card-played energy must never ship")
    tick = {"id": "r2", "name": "r2", "hooks": [
        {"trigger": "on_card_played", "target": "enemy", "effects": [{"op": "damage", "amount": 1}]}]}
    check(not _relic_balance_errors(tick, _made(retain_pool=0), _V),
          "a 1-damage per-card tick is a fine keystone")


def test_uptime_and_stats_helpers() -> None:
    print("helper sanity: deck stats + condition uptime:")
    stats = _keystone_deck_stats(_made(retain_pool=5))
    check(stats["share"] == 0.5, f"5/10 retain pool -> share 0.5: {stats}")
    check(_cond_uptime(None, stats) == 1.0, "no condition -> 1.0")
    check(_cond_uptime({"kind": "hand_size_ge", "value": 6}, stats) == 1.0,
          "retain-heavy: hand_size_ge 6 is free")
    lean = _keystone_deck_stats(_made(retain_pool=0))
    check(_cond_uptime({"kind": "hand_size_ge", "value": 6}, lean) < 0.5,
          "no retain: hand_size_ge 6 is a real hoop")
    check(_cond_uptime({"kind": "hp_below_half"}, lean) < 0.5, "hp_below_half is situational")
    check(_cond_uptime({"kind": "hp_below_half", "negate": True}, lean) > 0.5,
          "negate inverts the estimate")
    # the gate must never raise on garbage — it degrades to 'no errors', not a dead forge
    check(_relic_balance_errors({"hooks": [{"trigger": 7, "effects": "x"}]}, None, _V) == [],
          "garbage relic/made must not raise")


# --- the DEAD end of the gate (the Hidden Ledger fix, El Traficante 2026-08-12) ----------------------
# The power gate above prices generously HIGH; these cover the opposite failure: a keystone whose `when`
# ~never holds (it shipped, equipped, and never fired once all run).

def test_post_play_hand_gate_rejected() -> None:
    print("on_card_played + hand_size_ge 6 (checked AFTER the card leaves hand) -> rejected as near-dead:")
    relic = {"id": "hl", "name": "Hidden Ledger", "hooks": [
        {"trigger": "on_card_played", "once_per_combat": True,
         "when": {"kind": "hand_size_ge", "value": 6},
         "effects": [{"op": "gain_energy", "amount": 1}]}]}
    errs = _relic_balance_errors(relic, _made(retain_pool=3), _V)
    check(bool(errs) and "NEAR-DEAD" in errs[0] and "leaves your hand" in errs[0],
          f"the post-play timing trap must be named: {errs}")


def test_post_play_hand_gate_ok_low_value() -> None:
    print("the same shape with hand_size_ge 4 (reachable post-play) -> allowed:")
    relic = {"id": "hl2", "name": "hl2", "hooks": [
        {"trigger": "on_card_played", "once_per_combat": True,
         "when": {"kind": "hand_size_ge", "value": 4},
         "effects": [{"op": "gain_energy", "amount": 1}]}]}
    errs = _relic_balance_errors(relic, _made(retain_pool=3), _V)
    check(not errs, f"hand_size_ge 4 on on_card_played is a real but reachable gate: {errs}")


def test_never_true_condition_rejected() -> None:
    print("turn_start + hand_size_ge 9 on a retainless deck (~never true) -> rejected as near-dead:")
    relic = {"id": "r", "name": "r", "hooks": [
        {"trigger": "turn_start", "when": {"kind": "hand_size_ge", "value": 9},
         "effects": [{"op": "block", "amount": 3}]}]}
    errs = _relic_balance_errors(relic, _made(retain_pool=0), _V)
    check(bool(errs) and "never" in errs[0], f"a condition the deck never reaches must be flagged: {errs}")


def test_uptime_post_play_timing() -> None:
    print("_cond_uptime: on_card_played reads a one-smaller hand; realistic mode holds fewer cards:")
    lean = _keystone_deck_stats(_made(retain_pool=0))
    w = {"kind": "hand_size_ge", "value": 6}
    check(_cond_uptime(w, lean, "on_card_played") < _cond_uptime(w, lean),
          "the post-play hand is one smaller, so uptime must drop")
    mid = _keystone_deck_stats(_made(retain_pool=3))
    check(_cond_uptime(w, mid, "on_card_played", realistic=True) <= _cond_uptime(w, mid, "on_card_played"),
          "the realistic model must never exceed the generous power-gate model")


def test_relic_deck_note() -> None:
    print("_relic_deck_note(): the PROACTIVE prompt hint mirrors the gate's hand model:")
    from btsgen.class_forge import _RelicContract, _relic_deck_note
    note = _relic_deck_note(_made(retain_pool=5))
    check("DECK NOTE" in note and "hand_size_ge" in note,
          f"a retain-heavy deck yields the hand-size warning: {note[:80]}")
    check("~10" in note, f"the note states the gate's expected hand (share 0.5 -> 5 held -> ~10): {note}")
    check(all(ord(ch) < 128 for ch in note), "the note is ASCII (injection-line rule)")
    check(_relic_deck_note(_made(retain_pool=0)) == "", "a retainless deck gets no note")
    check(_relic_deck_note(_made(retain_pool=1)) == "", "one retain card in ten is below the warn threshold")
    check(_relic_deck_note([]) == "", "an empty set never raises")
    # the note rides the relic brief via bp["relic_deck_note"] (forge_class stashes it pre-call)
    bp = {"name": "Coil", "description": "d", "archetypes": [], "relic_deck_note": note}
    brief = _RelicContract().user_brief(bp)
    check("DECK NOTE" in brief, "user_brief folds the stashed note into the relic prompt")
    check("DECK NOTE" not in _RelicContract().user_brief({"name": "X", "archetypes": []}),
          "no stashed note -> the brief is unchanged")


def main() -> int:
    for t in (test_diamond_hands_rejected_on_retain_deck, test_same_relic_ok_on_retainless_deck,
              test_retain_basic_counts_as_starting_deck, test_unconditional_energy_rejected,
              test_max_energy_modifier_rejected, test_modest_keystones_pass,
              test_per_turn_draw_engine_rejected, test_reactive_trigger_priced_per_event,
              test_uptime_and_stats_helpers, test_post_play_hand_gate_rejected,
              test_post_play_hand_gate_ok_low_value, test_never_true_condition_rejected,
              test_uptime_post_play_timing, test_relic_deck_note):
        t()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
