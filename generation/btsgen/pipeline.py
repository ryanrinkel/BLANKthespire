"""Orchestrate one card: generate -> validate -> repair once -> quarantine.

This is the PRD §10.3 pipeline. The engine consumes only what survives validation,
and only after a human promotes it out of quarantine (cli_review). Quarantined cards
are tagged source:"llm" and carry a sidecar .meta.json with the computed balance score.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import paths
from .contract import Brief
from .generator import AnthropicGenerator, extract_card_json
from .validator import CardValidator, ValidationResult


@dataclass
class PipelineResult:
    ok: bool
    card: dict | None = None
    result: ValidationResult | None = None
    quarantine_path: str | None = None
    attempts: int = 0
    repaired: bool = False
    balance_repaired: bool = False      # an overtuned card was renumbered by the balance pass
    balance_repair: dict | None = None  # {attempted, accepted, score_before, score_after, ceiling}
    log: list[str] = field(default_factory=list)
    # Every validation error this card drew, across ALL attempts — kept even when the repair SUCCEEDS,
    # because an attempt-1 reach for a missing vocab token is demand signal (validator.vocab_misses)
    # regardless of whether the model then settled for a legal card.
    all_errors: list[str] = field(default_factory=list)


# Balance repair fires only when the score clears the ceiling by this factor. The ceiling already sits
# 25-60% above the cost baseline, and the score is a coarse heuristic (X~3 energy, {state}~3, x0.6
# conditionals) — a 0-10% exceedance is inside heuristic noise and stays a plain warning.
_BALANCE_REPAIR_GRACE = 1.10


def _extract_or_error(text: str) -> tuple[dict | None, list[str]]:
    try:
        return extract_card_json(text), []
    except ValueError as e:
        return None, [str(e)]


def generate_card(brief: Brief, gen: AnthropicGenerator | None = None,
                  validator: CardValidator | None = None) -> PipelineResult:
    gen = gen or AnthropicGenerator()
    validator = validator or CardValidator()
    res = PipelineResult(ok=False)

    # --- attempt 1 ---
    text, messages = gen.first_attempt(brief)
    res.attempts = 1
    card, errors = _extract_or_error(text)
    if card is not None:
        card["source"] = "llm"  # provenance is the harness's call, not model compliance
        vr = validator.validate(card)
        errors = vr.errors
        if vr.ok:
            res.ok, res.card, res.result = True, card, vr
            res.log.append("attempt 1: valid")
            _maybe_balance_repair(res, messages, gen, validator)
            return _quarantine(res, brief, gen.model, validator)
    res.all_errors += errors
    res.log.append(f"attempt 1: {len(errors)} error(s)")

    # --- repair once (PRD §10.3 step 3) ---
    text2, messages = gen.repair(messages, text, errors)
    res.attempts = 2
    res.repaired = True
    card2, parse_errs2 = _extract_or_error(text2)
    if card2 is None:
        res.log.append(f"repair: still unparseable ({'; '.join(parse_errs2)})")
        return res
    card2["source"] = "llm"
    vr2 = validator.validate(card2)
    if vr2.ok:
        res.ok, res.card, res.result = True, card2, vr2
        res.log.append("repair: valid")
        _maybe_balance_repair(res, messages, gen, validator)
        return _quarantine(res, brief, gen.model, validator)
    res.result = vr2
    res.all_errors += vr2.errors
    res.log.append(f"repair: still {len(vr2.errors)} error(s) -> discarded")
    return res


def _maybe_balance_repair(res: PipelineResult, messages: list[dict], gen, validator: CardValidator) -> None:
    """Overtuned-card pass, two layers: (1) ONE extra repair call asking for the same design with smaller
    numbers; (2) whatever survives layer 1 still over the ceiling gets its amounts deterministically clamped
    down to the budget (the ceiling is a guarantee, not a request). Never fatal — a card only ships over
    budget if it has no shrinkable numbers left (flat-scored ops), and then its warning survives."""
    try:
        ceiling = validator.power_ceiling(res.card)
        if res.result.score <= ceiling * _BALANCE_REPAIR_GRACE:
            return
        res.balance_repair = {"attempted": True, "accepted": False,
                              "score_before": round(res.result.score, 2), "score_after": None,
                              "ceiling": round(ceiling, 2)}
        _llm_renumber(res, messages, gen, validator, ceiling)
        _clamp_to_budget(res, validator)
    except Exception as e:  # noqa: BLE001 — balance tuning must never kill a valid card
        res.log.append(f"balance repair: errored ({e}) -> kept original")


def _llm_renumber(res: PipelineResult, messages: list[dict], gen, validator: CardValidator,
                  ceiling: float) -> None:
    """Layer 1: ask the model for the same design with smaller numbers (it distributes the cut with taste,
    which the mechanical clamp can't). Any failure just falls through to the clamp."""
    try:
        card, old_score = res.card, res.result.score
        instruction = (
            f"overtuned: power score {old_score:.1f} exceeds the ~{ceiling:.1f} budget for cost "
            f"{card.get('cost', 0)} / {card.get('rarity', 'common')}. KEEP the design EXACTLY as returned "
            "-- same id, name, type, ops, conditions, triggers and effect structure -- and ONLY reduce "
            "numeric amounts (and/or raise the cost by 1) until the power fits the cost/rarity budget. "
            "Do not add, remove, or swap any effect."
        )
        # canonical JSON as prev_text (not the raw model text) so fences/prose can't confuse the renumbering
        text, _ = gen.repair(messages, json.dumps(card), [instruction])
        tuned, _errs = _extract_or_error(text)
        if tuned is None:
            res.log.append("balance repair: unparseable -> kept original")
            return
        tuned["source"] = "llm"
        vr = validator.validate(tuned)
        if not vr.ok:
            res.log.append("balance repair: invalid -> kept original")
            return
        # design preserved: same effect skeleton (numbers stripped), same rarity, cost same or exactly +1
        if validator._reprint_key_nums(tuned)[0] != validator._reprint_key_nums(card)[0] \
                or tuned.get("rarity") != card.get("rarity") \
                or not _cost_same_or_plus_one(card.get("cost", 0), tuned.get("cost", 0)):
            res.log.append("balance repair: design changed -> kept original")
            return
        # renumbering must land under the budget, or at least strictly improve
        if vr.score > validator.power_ceiling(tuned) and vr.score >= old_score:
            res.log.append(f"balance repair: no better ({vr.score:.1f}) -> kept original")
            return
        res.card, res.result = tuned, vr
        res.balance_repaired = True
        res.balance_repair.update(accepted=True, score_after=round(vr.score, 2))
        res.log.append(f"balance repair: {old_score:.1f} -> {vr.score:.1f} (budget ~{ceiling:.1f})")
    except Exception as e:  # noqa: BLE001 — balance tuning must never kill a valid card
        res.log.append(f"balance repair: errored ({e}) -> kept original")


# ops whose integer `amount` raises the power score — the knobs the deterministic clamp may turn.
# lose_hp is deliberately absent (shrinking a self-cost makes the card STRONGER); add_card's amount is
# copies (unscored); `times`/`hits` are design structure, not tuning knobs.
_CLAMP_AMOUNT_OPS = {"damage", "block", "draw", "gain_energy", "heal", "forge", "balance_step",
                     "blade_empower", "apply_status", "apply_status_custom", "summon",
                     "summon_attack", "buff_summon", "scry"}


def _clamp_to_budget(res: PipelineResult, validator: CardValidator) -> None:
    """Layer 2: the deterministic backstop. If the card (original or LLM-renumbered) still scores over its
    ceiling, scale every score-raising amount down proportionally (floored at 1) until it fits. Design is
    untouched by construction — only integer amounts shrink, in both base and upgrade effects."""
    try:
        card = res.card
        ceiling = validator.power_ceiling(card)
        old_score = res.result.score
        if old_score <= ceiling:
            return
        tuned = copy.deepcopy(card)
        for _ in range(12):  # flooring at 1 loses precision; iterate until under budget or out of knobs
            score = validator.score_card(tuned)
            if score <= ceiling:
                break
            factor = ceiling / score
            changed = _shrink_amounts(tuned.get("effects"), factor)
            # keep the upgrade proportional so Upgrade stays a same-shaped improvement, not a relic of
            # the untuned numbers (upgrade effects aren't scored, so shrink by the same factor blindly)
            changed |= _shrink_amounts((tuned.get("upgrade") or {}).get("effects"), factor)
            if not changed:
                break
        vr = validator.validate(tuned)
        if not vr.ok or vr.score >= old_score:
            res.log.append(f"balance clamp: no shrinkable amounts ({old_score:.1f} > ~{ceiling:.1f}) "
                           "-> kept card, warning stands")
            return
        res.card, res.result = tuned, vr
        res.balance_repaired = True
        if res.balance_repair is None:
            res.balance_repair = {"attempted": True, "accepted": False,
                                  "score_before": round(old_score, 2), "score_after": None,
                                  "ceiling": round(ceiling, 2)}
        res.balance_repair.update(clamped=True, score_after=round(vr.score, 2))
        res.log.append(f"balance clamp: {old_score:.1f} -> {vr.score:.1f} (budget ~{ceiling:.1f})")
    except Exception as e:  # noqa: BLE001 — the clamp must never kill a valid card
        res.log.append(f"balance clamp: errored ({e}) -> kept card")


def _shrink_amounts(effects, factor: float) -> bool:
    """Scale the score-raising integer amounts in an effect tree by `factor` (floor 1, always at least
    -1 so the loop makes progress). Returns True if anything changed."""
    changed = False
    for eff in effects or []:
        if not isinstance(eff, dict):
            continue
        if eff.get("op") in _CLAMP_AMOUNT_OPS:
            changed |= _shrink_field(eff, "amount", factor)
            if eff.get("op") == "damage":
                changed |= _shrink_field(eff, "grow", factor)  # Phase U: grow is a numeric knob too
        for key in ("effects", "then", "else"):  # multi/fuse/add_trigger payloads + conditional branches
            if isinstance(eff.get(key), list):
                changed |= _shrink_amounts(eff[key], factor)
    return changed


def _shrink_field(eff: dict, key: str, factor: float) -> bool:
    v = eff.get(key)
    if not isinstance(v, int) or isinstance(v, bool) or v <= 1:
        return False
    eff[key] = max(1, min(v - 1, int(v * factor)))
    return True


def _cost_same_or_plus_one(old, new) -> bool:
    if isinstance(old, str) or isinstance(new, str):
        return old == new  # "X" must stay "X"
    return new in (old, old + 1)


def _unique_id(base: str, validator: CardValidator) -> str:
    taken = validator.known_cards
    if base not in taken:
        return base
    n = 2
    while f"{base}_{n}" in taken:
        n += 1
    return f"{base}_{n}"


def _quarantine(res: PipelineResult, brief: Brief, model: str, validator: CardValidator) -> PipelineResult:
    card = dict(res.card)
    card["source"] = "llm"  # provenance tag (PRD §10.3 step 4)

    new_id = _unique_id(card["id"], validator)
    if new_id != card["id"]:
        res.log.append(f"id '{card['id']}' collides; renamed to '{new_id}'")
        card["id"] = new_id

    paths.GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    card_path = paths.GENERATED_DIR / f"{new_id}.json"
    meta_path = paths.GENERATED_DIR / f"{new_id}.meta.json"
    card_path.write_text(json.dumps(card, indent=2) + "\n")
    meta = {
        "id": new_id,
        "source": "llm",
        "model": model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "brief": brief.describe(),
        "score": round(res.result.score, 2),
        "warnings": res.result.warnings,
        "repaired": res.repaired,
        "balance_repaired": res.balance_repaired,
    }
    if res.balance_repair is not None:
        meta["balance_repair"] = res.balance_repair
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")

    res.card = card
    res.quarantine_path = str(card_path)
    res.log.append(f"quarantined -> {card_path}")
    return res
