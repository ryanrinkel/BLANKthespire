"""Orchestrate one relic: generate -> validate -> repair once -> quarantine (parallel to pipeline.py).

The engine consumes only what survives validation, and only after a human promotes it out of
quarantine (cli_relic_review). Quarantined relics are tagged source:"llm" and carry a sidecar
.meta.json with the computed power proxy + any balance warnings.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import paths, relic_contract
from .generator import AnthropicGenerator, extract_card_json
from .relic_contract import Brief
from .relic_validator import RelicValidator
from .validator import ValidationResult


@dataclass
class PipelineResult:
    ok: bool
    relic: dict | None = None
    result: ValidationResult | None = None
    quarantine_path: str | None = None
    attempts: int = 0
    repaired: bool = False
    log: list[str] = field(default_factory=list)


def _extract_or_error(text: str) -> tuple[dict | None, list[str]]:
    try:
        return extract_card_json(text), []   # generic single-JSON-object extractor
    except ValueError as e:
        return None, [str(e)]


def generate_relic(brief: Brief, gen: AnthropicGenerator | None = None,
                   validator: RelicValidator | None = None) -> PipelineResult:
    gen = gen or AnthropicGenerator(contract_mod=relic_contract)
    validator = validator or RelicValidator()
    res = PipelineResult(ok=False)

    # --- attempt 1 ---
    text, messages = gen.first_attempt(brief)
    res.attempts = 1
    relic, errors = _extract_or_error(text)
    if relic is not None:
        vr = validator.validate(relic)
        errors = vr.errors
        if vr.ok:
            res.ok, res.relic, res.result = True, relic, vr
            res.log.append("attempt 1: valid")
            return _quarantine(res, brief, gen.model, validator)
    res.log.append(f"attempt 1: {len(errors)} error(s)")

    # --- repair once ---
    text2, messages = gen.repair(messages, text, errors)
    res.attempts = 2
    res.repaired = True
    relic2, parse_errs2 = _extract_or_error(text2)
    if relic2 is None:
        res.log.append(f"repair: still unparseable ({'; '.join(parse_errs2)})")
        return res
    vr2 = validator.validate(relic2)
    if vr2.ok:
        res.ok, res.relic, res.result = True, relic2, vr2
        res.log.append("repair: valid")
        return _quarantine(res, brief, gen.model, validator)
    res.result = vr2
    res.log.append(f"repair: still {len(vr2.errors)} error(s) -> discarded")
    return res


def _unique_id(base: str, validator: RelicValidator) -> str:
    taken = validator.known_relics
    if base not in taken:
        return base
    n = 2
    while f"{base}_{n}" in taken:
        n += 1
    return f"{base}_{n}"


def _quarantine(res: PipelineResult, brief: Brief, model: str, validator: RelicValidator) -> PipelineResult:
    relic = dict(res.relic)
    relic["source"] = "llm"  # provenance tag

    new_id = _unique_id(relic["id"], validator)
    if new_id != relic["id"]:
        res.log.append(f"id '{relic['id']}' collides; renamed to '{new_id}'")
        relic["id"] = new_id

    paths.GENERATED_RELICS_DIR.mkdir(parents=True, exist_ok=True)
    relic_path = paths.GENERATED_RELICS_DIR / f"{new_id}.json"
    meta_path = paths.GENERATED_RELICS_DIR / f"{new_id}.meta.json"
    relic_path.write_text(json.dumps(relic, indent=2) + "\n")
    meta = {
        "id": new_id,
        "source": "llm",
        "model": model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "brief": brief.describe(),
        "score": round(res.result.score, 2),
        "warnings": res.result.warnings,
        "repaired": res.repaired,
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")

    res.relic = relic
    res.quarantine_path = str(relic_path)
    res.log.append(f"quarantined -> {relic_path}")
    return res
