"""The staged creative front-end (cloud -> cluster -> map -> compose -> relic-intent).

Produces a "creative dossier" that the reframed blueprint stage turns into the `bp` dict — an AUGMENT
of the single one-shot blueprint call, not a replacement. All downstream card-gen safety nets stay intact.
"""
from __future__ import annotations

from .builder import BlueprintBuilder, BlueprintBuildError
from .catalog import ArchetypeCatalog, append_vocab_gaps, load_catalog
from .dossier import Candidate, Dossier

__all__ = [
    "BlueprintBuilder", "BlueprintBuildError",
    "ArchetypeCatalog", "load_catalog", "append_vocab_gaps",
    "Candidate", "Dossier",
]
