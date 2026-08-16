"""The threaded state of the staged front-end: a Candidate (one composed class build) and the Dossier
(everything the stages produced). The chosen Candidate + relic intent is what the reframed blueprint
stage consumes to emit the `bp` dict."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Candidate:
    """One composed class build = two (or, under triad, THREE) archetypes in tension, hydrated against the
    catalog. A triad candidate is a TRIANGLE of pairs: `tension` summarizes the triangle and `pair_lines`
    assigns each pair its own strategy (D3)."""
    name: str
    fantasy: str
    archetype_ids: list[str]
    archetype_descs: list[str]
    core_loop: str = ""
    weakness: str = ""
    tension: str = ""                    # how the archetypes pull against each other (the triangle summary under triad)
    # 2-3 draftable game plans this ONE pool supports (the Ironclad test): [{strategy: aggro|control|combo,
    # line: how these two archetypes play it, win_condition: how that deck closes a fight}]. The blueprint
    # stage builds a card package (enablers/amplifiers/rare finisher) for each.
    strategic_lines: list[dict] = field(default_factory=list)
    # Phase 2 (triad): the per-PAIR strategy mapping (D3) — [{pair: [id_a, id_b], strategy, line, win_condition}]
    # for the three pairs of a triad; empty on a 2-archetype candidate. The reframed blueprint stage maps these
    # onto the top-level `pair_lines` the triad validator (_validate_pair_lines) enforces.
    pair_lines: list[dict] = field(default_factory=list)
    class_kind: str = "normal"           # normal | orb | status | summon (drives which pool the blueprint declares)
    suggested_max_hp: int = 72
    buildable: bool = True               # all referenced archetypes expressible in the live vocabulary
    gap_refs: list[str] = field(default_factory=list)
    block_reasons: list[str] = field(default_factory=list)
    spine_archetype: str | None = None   # set by the collision check when >=2 clusters map the same archetype
    relic_intent: dict | None = None     # filled by the relic-intent stage

    def preview(self) -> str:
        tag = "buildable-now" if self.buildable else f"needs-vocab ({'; '.join(self.block_reasons) or 'gap'})"
        spine = f"  [spine: {self.spine_archetype}]" if self.spine_archetype else ""
        lines = "".join(f"\n    {l.get('strategy', '?')}: {l.get('win_condition') or l.get('line', '')}"
                        + (f" [{l['idiom']}]" if l.get('idiom') else "")  # O-3 texture tag
                        for l in self.strategic_lines if isinstance(l, dict))
        return (f"{self.name} — {self.fantasy}\n"
                f"    archetypes: {', '.join(self.archetype_ids)} [{tag}]{spine}\n"
                f"    loop: {self.core_loop}\n"
                f"    weakness: {self.weakness}" + lines)


@dataclass
class DossierBrief:
    """What the reframed blueprint stage (mode='dossier') consumes: the chosen Candidate + relic intent.
    Carries `concept` too so the contract can fall back / reference the original theme, and `skin` — the
    flavor-facet material (imagery/names) the blueprint dresses the class in (mechanics come from the driver)."""
    candidate: Candidate
    relic_intent: dict | None = None
    concept: str = ""
    skin: dict | None = None
    featured: list | None = None   # Phase N-2 roulette picks, threaded from the ClassBrief for the brief block


@dataclass
class Dossier:
    theme: str = ""
    facets: list[dict] = field(default_factory=list)         # [{name, role: driver|flavor, richness, why}]
    concepts: list[str] = field(default_factory=list)
    clusters: list[dict] = field(default_factory=list)      # [{name, feeling, facet, concepts:[...]}]
    mappings: list[dict] = field(default_factory=list)       # [{cluster, archetype_id, metaphor, off_vocab?}]
    # Interactive mode (the mid-forge archetype pick): what the player was shown, and what they chose.
    # Empty picked = auto (skipped / timed out / non-interactive) — the picker falls back to theme fidelity.
    offered_archetypes: list[str] = field(default_factory=list)
    picked_archetypes: list[str] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    chosen: Candidate | None = None
    relic_intent: dict | None = None
    skin_bank: dict = field(default_factory=dict)   # {subject:[driver names], flavor:[names], imagery:[...], feelings:[...]}
    featured_resonance: list[dict] = field(default_factory=list)  # [{id, why}] the cloud stage's menu shortlist (N-5)
    gaps_logged: int = 0
