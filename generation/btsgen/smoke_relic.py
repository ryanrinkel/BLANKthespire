"""Canonical broad-coverage "smoke relic", and helpers to stage/unstage it onto forged class slots.

This folds the Phase L forged-relic runtime into the standing AutoSlay smoke gate (AUTOSLAY_TESTING_PLAN.md):
every smoke run can now carry a relic that exercises a wide swath of the relic vocabulary in ONE run, so a
relic-runtime crash/hang surfaces in the routine gate — not only in one-off scratch/stage_phase_l*.py runs.

What the smoke relic covers (all PROVEN clean across Phase L AutoSlay runs):
  - triggers:   turn_start, attacked (thorns), on_exhaust, on_card_played, combat_end (heal),
                on_card_drawn, on_damage_dealt, on_block_gained
  - the load-bearing RE-ENTRANCY GUARD: an on_block_gained -> block hook that re-raises its own event
    (this is the hang regression we most want the standing gate to catch)
  - a gated condition: turn_start when enemy_count_ge 2 -> Weak all enemies
  - modifiers:  max_energy, first_attack (Akabeko), cost_reduction, start_combat_block

Deliberately EXCLUDED: the compose ops (channel_orb / summon). They are class-conditional (no-op unless the
class declares orbs / a summon pool) and would need per-class names, so they don't belong on a generic relic.
Class-specific compose coverage stays in scratch/stage_phase_l_compose.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from . import game_paths
from .class_forge import _validate_relic  # the lockstep gate (mirrors C# TryParseRelic)

FORGED_CHARACTERS = game_paths.game_user_dir() / "forged" / "characters"
_BACKUP_SUFFIX = ".smokebak"

# The broad-coverage smoke relic. Distinctive numbers so each effect is unmistakable in godot.log.
SMOKE_RELIC = {
    "id": "bts_smoke_coverage_sigil",
    "name": "Smoke Coverage Sigil",
    "description": "Standing-gate relic exercising the Phase L forged-relic runtime.",
    "tier": "starter",
    "modifiers": [
        {"stat": "max_energy", "amount": 1},
        {"stat": "first_attack", "amount": 5},        # Akabeko: +5 to the first card attack each combat
        {"stat": "cost_reduction", "amount": 1},      # your cards cost 1 less energy in combat
        {"stat": "start_combat_block", "amount": 4},  # Orichalcum / Anchor
    ],
    "hooks": [
        {"trigger": "turn_start", "effects": [{"op": "block", "amount": 3}]},
        {"trigger": "attacked", "target": "attacker", "effects": [{"op": "damage", "amount": 3}]},  # thorns
        {"trigger": "on_exhaust", "effects": [{"op": "block", "amount": 2}]},                       # compost
        {"trigger": "on_card_played", "once_per_combat": True, "effects": [{"op": "block", "amount": 2}]},
        {"trigger": "combat_end", "effects": [{"op": "heal", "amount": 5}]},                        # Burning Blood
        {"trigger": "on_card_drawn", "once_per_combat": True, "effects": [{"op": "block", "amount": 1}]},
        {"trigger": "on_damage_dealt", "once_per_combat": True, "target": "enemy",
         "effects": [{"op": "damage", "amount": 1}]},
        # RE-ENTRANCY GUARD STRESS TEST: this re-raises AfterBlockGained from inside its own handler. If the
        # guard regresses, the run hangs and the gate reports a HANG timeout. NOT once_per_combat, so it fires
        # freely every time block is gained.
        {"trigger": "on_block_gained", "effects": [{"op": "block", "amount": 1}]},
        # Phase P (gap #9 relic mirror): on_hp_lost fires on your own unblocked, self/card-caused HP loss. Its
        # payload draws — a lose_hp inside a payload can't recurse (FireGuarded's per-trigger guard), and draw
        # doesn't cause HP loss, so this is a safe fixed exercise of the new relic hook.
        {"trigger": "on_hp_lost", "once_per_combat": True, "effects": [{"op": "draw", "amount": 1}]},
        # Gated-condition sample: only when 2+ enemies are alive, weaken them all.
        {"trigger": "turn_start", "when": {"kind": "enemy_count_ge", "value": 2}, "target": "all_enemies",
         "effects": [{"op": "apply_status", "status": "weak", "amount": 1}]},
    ],
}


def validate() -> list[str]:
    """Self-check the canonical relic against the lockstep validator. Empty list == valid."""
    return _validate_relic(SMOKE_RELIC)


def _slot_file(slot: int) -> Path:
    return FORGED_CHARACTERS / f"{slot:02d}.json"


def slot_from_character(character: str | None) -> int | None:
    """Map a smoke-gate --character value to a forged slot number.

    Accepts the same loose forms the C# hook does: 'ForgedCharacterSlot01', 'class1', '01', '1' -> 1.
    Returns None when no slot can be derived (e.g. --character omitted).
    """
    if not character:
        return None
    digits = "".join(c for c in str(character) if c.isdigit())
    return int(digits) if digits else None


def existing_slots() -> list[int]:
    """Forged character slots currently staged on disk (01..99)."""
    if not FORGED_CHARACTERS.is_dir():
        return []
    out: list[int] = []
    for p in FORGED_CHARACTERS.glob("*.json"):
        try:
            out.append(int(p.stem))
        except ValueError:
            continue
    return sorted(out)


def _restore_one(path: Path) -> None:
    bak = path.with_suffix(path.suffix + _BACKUP_SUFFIX)
    if bak.exists():
        path.write_text(bak.read_text(encoding="utf-8"), encoding="utf-8")
        bak.unlink()


def ensure_relic(slot: int, force: bool = False) -> Callable[[], None] | None:
    """Ensure forged class `slot` carries a relic so a smoke run exercises the relic runtime.

    auto  (force=False): if the class already has a relic, leave it untouched (test its OWN relic);
                         otherwise inject the broad-coverage SMOKE_RELIC + make one deck card ethereal.
    force (force=True):  always inject SMOKE_RELIC (+ ethereal), replacing any existing relic, for maximum
                         and consistent coverage.

    Backs up every file it edits (<file>.smokebak) and returns a restore() callable that reverts them.
    Returns None when nothing was changed (no such slot, or auto + a relic already present).
    """
    charfile = _slot_file(slot)
    if not charfile.exists():
        return None

    d = json.loads(charfile.read_text(encoding="utf-8"))
    if d.get("relic") and not force:
        return None  # auto: keep the class's authentic relic

    errs = validate()
    if errs:  # should never happen — the canonical relic is fixed and lockstep-valid
        raise ValueError(f"SMOKE_RELIC failed validation: {errs}")

    edited: list[Path] = []

    # 1) inject the relic onto the character dict (the C# shell reads RelicSpecFor(slot) from here).
    charfile.with_suffix(charfile.suffix + _BACKUP_SUFFIX).write_text(
        json.dumps(d), encoding="utf-8")
    d["relic"] = SMOKE_RELIC
    charfile.write_text(json.dumps(d), encoding="utf-8")
    edited.append(charfile)

    # 2) make one non-primary starting-deck card ethereal so on_exhaust reliably fires (an ethereal card
    #    Exhausts if still in hand at end of turn). Skip silently if the deck shape isn't as expected.
    cardfile = _ethereal_target(slot, d)
    if cardfile is not None and cardfile.exists():
        card = json.loads(cardfile.read_text(encoding="utf-8"))
        effs = card.setdefault("effects", [])
        if not any(e.get("op") == "ethereal" for e in effs):
            cardfile.with_suffix(cardfile.suffix + _BACKUP_SUFFIX).write_text(
                json.dumps(card), encoding="utf-8")
            effs.append({"op": "ethereal"})
            # The mod rejects a card whose upgrade effect count differs from its base (ForgedCards.Validate).
            # If the target has an upgrade, mirror the injected ethereal into it too, so the card still imports
            # (otherwise the ethereal target silently drops from the smoke deck — the slot-05 rejection).
            up = card.get("upgrade")
            if isinstance(up, dict) and isinstance(up.get("effects"), list) \
                    and not any(e.get("op") == "ethereal" for e in up["effects"]):
                up["effects"].append({"op": "ethereal"})
            cardfile.write_text(json.dumps(card), encoding="utf-8")
            edited.append(cardfile)

    def restore() -> None:
        for p in edited:
            _restore_one(p)

    return restore


def _ethereal_target(slot: int, char_dict: dict) -> Path | None:
    """Pick a starting-deck card to make ethereal: a non-first deck slot (avoid gutting the primary attack)."""
    deck_slots = sorted({e.get("slot") for e in (char_dict.get("starting_deck") or [])
                         if isinstance(e, dict) and isinstance(e.get("slot"), int)})
    if not deck_slots:
        return None
    pick = 5 if 5 in deck_slots else deck_slots[-1]
    return FORGED_CHARACTERS / f"{slot:02d}" / "cards" / f"{pick:02d}.json"
