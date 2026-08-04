"""btsgen — BLANK the spire LLM content-generation harness (PRD M5 / §10).

Engine-independent. Emits *validated* JSON cards the Godot engine ingests via
ContentDB.ingest_card(). The engine never imports this package; this package
only reads the published schema + vocabulary and writes JSON into data/.
"""

__all__ = [
    "paths", "contract", "validator", "generator", "pipeline",
    "relic_contract", "relic_validator", "relic_pipeline",
    "character_contract", "character_validator", "character_pipeline", "fakes",
]
