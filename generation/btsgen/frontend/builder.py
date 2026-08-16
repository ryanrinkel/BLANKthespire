"""BlueprintBuilder — the staged front-end orchestrator.

Runs cloud+cluster -> map+compose -> (pick) -> relic-intent, threading a Dossier, then calls the REFRAMED
blueprint stage (_BlueprintContract(mode="dossier")) to emit the `bp` dict the rest of forge_class already
consumes. AUGMENT, not replace: the bp shape is identical, so every downstream safety net stays intact.

Provider-agnostic: it depends only on an injected `make_gen(contract_mod, *, max_tokens)` that returns a
duck-typed generator (Anthropic / OpenAI-compat / fake). Progress flows through the existing `on_event(str)`
sink. The human checkpoint is an injected callback `checkpoint(candidates, dossier) -> Candidate`, so the CLI
(stdin) and the web (SSE round-trip) can both supply it without the builder knowing about either.
"""
from __future__ import annotations

import os
from collections import Counter

from ..class_forge import _BlueprintContract, _extract, triad_enabled, validate_blueprint_for
from .dossier import Candidate, Dossier, DossierBrief
from .stage_cloud import _CloudClusterContract, validate_cloud
from .stage_map import (_ComposeOnlyContract, _MapComposeContract, _MapOnlyContract, validate_compose_for,
                        validate_map_for, validate_map_only)
from .stage_relic import _RelicIntentContract, validate_relic_intent

# class_kind distinctiveness weight — a special pool (orb/summon/status) is a bolder identity than a generic
# normal class, so the "distinctive-among-buildable" picker leans toward it (when it's buildable).
_KIND_WEIGHT = {"orb": 3.0, "summon": 2.0, "status": 1.5, "normal": 0.0}

# Fidelity (mechanics drawn from the theme's DRIVER subject) dominates the pick. Weighted above the
# distinctiveness ceiling (~6.0: max _KIND_WEIGHT 3.0 + uniqueness ~2.0 + spine 1.0) so a fully-faithful
# candidate always outranks an off-theme one — distinctiveness only breaks ties among the equally faithful.
_FIDELITY_WEIGHT = 10.0


class BlueprintBuildError(RuntimeError):
    """A front-end stage failed after its one repair attempt (the caller aborts the class, like a bad blueprint)."""


class BlueprintBuilder:
    def __init__(self, make_gen, *, catalog, on_event=None, checkpoint=None, auto: bool = True,
                 gap_log_append=None, n_candidates: int = 3, archetype_checkpoint=None,
                 triad: bool | None = None) -> None:
        self._make_gen = make_gen
        self._catalog = catalog
        self._on_event = on_event
        self._checkpoint = checkpoint
        self._auto = auto
        self._gap_log_append = gap_log_append
        self._n = max(2, int(n_candidates))
        # Phase 2 (triad experiment): when on, compose THREE archetypes in a tension triangle and reframe the
        # blueprint stage in triad mode. Default reads BTS_TRIAD (triad_enabled); the web layer passes a
        # per-request flag. Threaded into every stage contract + validator so the whole front-end is one mode.
        self._triad = triad_enabled(triad)
        # Interactive forge mode: `archetype_checkpoint(options, dossier) -> list[archetype_id]` is called
        # between MAP and COMPOSE with the theme-matched archetypes; the player's picks (<=2) become a hard
        # compose constraint AND the fidelity drivers. None (default) = the fused autonomous map+compose.
        self._archetype_checkpoint = archetype_checkpoint
        self.last_dossier: Dossier | None = None
        # Phase N-4 recency signals (populated per build() from the cross-forge ledger).
        self._recency_window: list = []
        self._recency_line: str = ""

    # --- progress + the universal per-stage loop ------------------------------------------------
    def _note(self, m: str) -> None:
        if self._on_event is not None:
            try:
                self._on_event(m)
            except Exception:
                pass

    # --- creative-process narration (verbose follow-along of each front-end stage) ----------------
    # ASCII only: these stream to the website log AND print to the CLI's Windows console (which can't
    # encode fancy unicode). Each call is one log line.
    def _narrate_facets(self, dossier: Dossier) -> None:
        if not dossier.facets:
            return
        parts = []
        for f in dossier.facets:
            role = str(f.get("role", "?")).lower()
            rich = str(f.get("richness", "")).strip()
            tag = role.upper() + (f", {rich}" if rich else "")
            parts.append(f"{f.get('name', '?')} [{tag}]")
        self._note(f"      decomposed the theme into {len(dossier.facets)} idea(s): " + "; ".join(parts))
        drivers = [str(f.get("name", "?")) for f in dossier.facets if str(f.get("role", "")).lower() == "driver"]
        flavors = [str(f.get("name", "?")) for f in dossier.facets if str(f.get("role", "")).lower() != "driver"]
        if drivers:
            skin = f"; {', '.join(flavors)} -> the skin (names, look, feel)" if flavors else ""
            self._note(f"      {', '.join(drivers)} -> the mechanical loop{skin}")

    def _build_skin(self, dossier: Dossier) -> dict:
        """The FLAVOR skin: the SUBJECT (driver facet names — what the class mechanically is) plus the flavor
        facets and their concept imagery (how it looks/sounds/is named). Harvested from the cloud data with NO
        extra model call. Empty imagery/flavor for a single-driver theme (nothing to skin with) — that's fine."""
        facets = dossier.facets or []
        drivers = [str(f.get("name", "")).strip() for f in facets if str(f.get("role", "")).lower() == "driver"]
        flavors = [str(f.get("name", "")).strip() for f in facets if str(f.get("role", "")).lower() != "driver"]
        flavor_lc = {f.lower() for f in flavors if f}

        def _is_flavor(facet_name: str) -> bool:
            f = (facet_name or "").strip().lower()
            return any(fl and (fl in f or f in fl) for fl in flavor_lc)

        imagery: list[str] = []
        feelings: list[str] = []
        seen: set[str] = set()
        for cl in (dossier.clusters or []):
            if not _is_flavor(str(cl.get("facet", ""))):
                continue
            if cl.get("feeling"):
                feelings.append(str(cl.get("feeling")))
            for c in (cl.get("concepts") or []):
                k = str(c).strip().lower()
                if k and k not in seen:
                    seen.add(k); imagery.append(str(c).strip())
        return {"subject": [d for d in drivers if d], "flavor": [f for f in flavors if f],
                "imagery": imagery[:12], "feelings": feelings[:5]}

    def _narrate_skin(self, dossier: Dossier) -> None:
        sk = dossier.skin_bank or {}
        if not (sk.get("flavor") or sk.get("imagery")):
            return
        flav = ", ".join(sk.get("flavor") or []) or "the theme"
        img = ", ".join((sk.get("imagery") or [])[:6])
        line = f"      skin: dressing the class in {flav}"
        if img:
            line += f" — motifs like {img}"
        self._note(line)

    def _narrate_cloud(self, dossier: Dossier) -> None:
        if dossier.concepts:
            shown = ", ".join(dossier.concepts[:18])
            more = f" (+{len(dossier.concepts) - 18} more)" if len(dossier.concepts) > 18 else ""
            self._note(f"      free-associated {len(dossier.concepts)} ideas (balanced across facets): {shown}{more}")
        if dossier.clusters:
            self._note(f"      grouped them into {len(dossier.clusters)} thematic thread(s):")
            for cl in dossier.clusters:
                name = cl.get("name") or "?"
                feeling = cl.get("feeling") or ""
                facet = str(cl.get("facet") or "").strip()
                members = ", ".join(cl.get("concepts") or [])
                line = f"        - {name}"
                if facet:
                    line += f" <{facet}>"
                if feeling:
                    line += f": {feeling}"
                if members:
                    line += f"  [{members}]"
                self._note(line)

    def _narrate_mappings(self, dossier: Dossier) -> None:
        if not dossier.mappings:
            return
        self._note(f"      matched {len(dossier.mappings)} thread(s) to archetypes:")
        for m in dossier.mappings:
            cluster = m.get("cluster") or m.get("name") or "?"
            aid = m.get("archetype_id") or "?"
            metaphor = m.get("metaphor") or ""
            line = f"        - '{cluster}' -> {aid}"
            if metaphor:
                line += f": {metaphor}"
            self._note(line)

    def _narrate_candidate(self, c: Candidate) -> None:
        tag = "buildable now" if c.buildable else f"needs new vocab ({'; '.join(c.block_reasons) or 'gap'})"
        spine = f"  [spine: {c.spine_archetype}]" if c.spine_archetype else ""
        self._note(f"      * {c.name}: {c.fantasy}")
        self._note(f"          fuses {' + '.join(c.archetype_ids)}  [{tag}]{spine}")
        if c.core_loop:
            self._note(f"          loop: {c.core_loop}")
        if c.tension:
            self._note(f"          tension: {c.tension}")
        # Triad: narrate the three pair-lines (each pair its own game plan, D3); else the strategic_lines.
        if getattr(c, "pair_lines", None):
            for l in c.pair_lines:
                if isinstance(l, dict) and l.get("strategy"):
                    pr = " + ".join(str(x) for x in (l.get("pair") or []))
                    win = f" -> wins by: {l['win_condition']}" if l.get("win_condition") else ""
                    self._note(f"          {pr} ({l['strategy']}): {l.get('line', '')}{win}")
        else:
            for l in (c.strategic_lines or []):
                if isinstance(l, dict) and l.get("strategy"):
                    win = f" -> wins by: {l['win_condition']}" if l.get("win_condition") else ""
                    idiom = f" [plays like: {l['idiom']}]" if l.get("idiom") else ""  # O-3 texture tag
                    self._note(f"          {l['strategy']} line: {l.get('line', '')}{win}")
        if c.weakness:
            self._note(f"          weakness: {c.weakness}")

    def _narrate_choice(self, c: Candidate) -> None:
        extra = []
        if c.class_kind and c.class_kind != "normal":
            extra.append(f"{c.class_kind} class")
        if c.spine_archetype:
            extra.append(f"spine: {c.spine_archetype}")
        if c.suggested_max_hp:
            extra.append(f"{c.suggested_max_hp} HP")
        suffix = f" ({', '.join(extra)})" if extra else ""
        self._note(f"      => chose {c.name}{suffix}: {c.fantasy}")

    def _narrate_relic(self, ri: dict) -> None:
        line = f"      keystone relic: {ri.get('name') or '?'}"
        if ri.get("fantasy"):
            line += f" - {ri['fantasy']}"
        if ri.get("effect_sketch"):
            line += f"  [{ri['effect_sketch']}]"
        self._note(line)

    def _run_stage(self, gen, brief, validate, label: str) -> dict:
        # Each attempt = one fresh generation + one repair. BTS_STAGE_ATTEMPTS>1 re-rolls the whole stage
        # when repair still fails — a weak/local model (e.g. a 7B on the strict blueprint dict) whiffs the
        # top-level structure often enough that a fresh re-roll beats hammering the same broken output.
        # Default 1 reproduces the historical single-attempt-with-repair behaviour exactly (Anthropic/web path).
        attempts = max(1, int(os.environ.get("BTS_STAGE_ATTEMPTS", "1")))
        last_errs: list[str] = [f"unparseable {label}"]
        for attempt in range(attempts):
            text, messages = gen.first_attempt(brief)
            obj = _extract(text)
            errs = validate(obj) if obj is not None else [f"unparseable {label}"]
            if errs:
                self._note(f"{label}: {len(errs)} issue(s); repairing"
                           + (f" (attempt {attempt + 1}/{attempts})" if attempts > 1 else ""))
                text, messages = gen.repair(messages, text, errs)
                obj = _extract(text)
                errs = validate(obj) if obj is not None else [f"unparseable {label}"]
            if not errs:
                return obj
            last_errs = errs
        raise BlueprintBuildError(f"{label} failed: " + "; ".join(last_errs[:4]))

    # --- the build --------------------------------------------------------------------------------
    def build(self, brief) -> dict:
        concept = getattr(brief, "concept", "") or ""
        dossier = Dossier(theme=concept)
        self.last_dossier = dossier

        # Phase N-4: read the cross-forge usage ledger ONCE (guarded) — steers map/compose away from recent
        # repeats and feeds the picker's novelty tie-breaker. A missing/corrupt ledger -> empty window.
        try:
            from .. import ledger
            self._recency_window = ledger.read_window()
            self._recency_line = ledger.payload_line(self._recency_window)
        except Exception:
            self._recency_window, self._recency_line = [], ""
        if self._recency_line:
            self._note("      recency: " + self._recency_line)

        # stage 1+2: cloud -> clusters
        self._note(f"[1/6] cloud: brainstorming free associations on '{concept}'...")
        cloud = self._run_stage(self._make_gen(_CloudClusterContract(), max_tokens=8000),
                                brief, validate_cloud, "cloud/cluster")
        dossier.facets = list(cloud.get("facets") or [])
        dossier.concepts = list(cloud.get("concepts") or [])
        dossier.clusters = list(cloud.get("clusters") or [])
        dossier.skin_bank = self._build_skin(dossier)
        self._narrate_facets(dossier)
        self._narrate_cloud(dossier)
        self._narrate_skin(dossier)
        # Phase N-5: theme-aware featured re-roll. The cloud stage NOMINATED resonant mechanics; a seeded,
        # recency-damped lottery makes the final picks (slot 1 resonant, the rest wild). brief.featured is
        # mutated in place — the DossierBrief stamp below AND forge_class's post-build re-resolve read it.
        self._reroll_featured(brief, cloud, dossier)

        # stage 3+4: map onto the catalog + compose candidates. Interactive mode splits the two halves and
        # puts the player between them (their archetype pick constrains compose); auto keeps the fused call.
        interactive = self._archetype_checkpoint is not None
        self._note("[2/6] map: matching each thread to the game's mechanical archetypes...")
        payload = {"concept": concept, "clusters": dossier.clusters,
                   "catalog_block": self._catalog.prompt_block(), "n": self._n, "_catalog": self._catalog,
                   "recency": self._recency_line}
        if interactive:
            mc = self._map_compose_interactive(payload, dossier)  # narrates mappings before the pick
        else:
            mc = self._run_stage(self._make_gen(_MapComposeContract(self._triad), max_tokens=12000),
                                 payload, validate_map_for(self._triad), "map/compose")
        dossier.mappings = list(mc.get("mappings") or [])
        dossier.candidates = [self._catalog.hydrate_candidate(c) for c in (mc.get("candidates") or [])]
        self._apply_collision_check(dossier)
        if not interactive:
            self._narrate_mappings(dossier)
        self._log_gaps(dossier, mc)
        fuse_desc = "three archetypes in a tension triangle" if self._triad else "two archetypes in tension"
        self._note(f"[3/6] compose: sketching {len(dossier.candidates)} class identities, each fusing "
                   f"{fuse_desc}:")
        for c in dossier.candidates:
            self._narrate_candidate(c)

        # pick
        self._note("[4/6] pick: weighing the candidates for distinctiveness, taking the boldest buildable one...")
        chosen = self._pick(dossier)
        if chosen is None:
            raise BlueprintBuildError("no candidate could be chosen")
        dossier.chosen = chosen
        self._narrate_choice(chosen)

        # stage 5: keystone relic INTENT (non-fatal — feeds the real relic generator via bp)
        try:
            self._note("[5/6] relic: designing the keystone relic that embodies this build...")
            ri = self._run_stage(self._make_gen(_RelicIntentContract(), max_tokens=2000),
                                 chosen, validate_relic_intent, "relic-intent")
            dossier.relic_intent = ri
            chosen.relic_intent = ri
            self._narrate_relic(ri)
        except BlueprintBuildError as e:
            self._note(f"[5/6] relic: keystone skipped ({e}); the relic stage will design one from the class")

        # reframed blueprint: dossier -> bp (identical shape; downstream untouched). Validated against the
        # candidate's DECLARED strategic lines — the pool must build the packages the compose stage promised.
        self._note(f"[6/6] blueprint: translating '{chosen.name}' into card briefs, pools, and numbers...")
        # The declared strategies the pool must cover: a triad's come from its per-PAIR lines (D3 — three
        # distinct), a 2-archetype class's from its strategic_lines. validate_blueprint_for checks each.
        if self._triad and getattr(chosen, "pair_lines", None):
            declared = [l.get("strategy") for l in chosen.pair_lines if isinstance(l, dict)]
        else:
            declared = [l.get("strategy") for l in (chosen.strategic_lines or []) if isinstance(l, dict)]
        dbrief = DossierBrief(candidate=chosen, relic_intent=dossier.relic_intent, concept=concept,
                              skin=dossier.skin_bank or None, featured=getattr(brief, "featured", None))
        bp = self._run_stage(self._make_gen(_BlueprintContract(mode="dossier", triad=self._triad), max_tokens=48000),
                             dbrief, validate_blueprint_for(declared), "blueprint")
        # Phase N-4: stamp the AUTHORITATIVE catalog archetype ids (the 7B often echoes display names into
        # bp["archetypes"][*].id, which would make the ledger + novelty penalty compare names-vs-ids and
        # silently never match). The chosen candidate's ids are the catalog ids the picker also uses.
        if getattr(chosen, "archetype_ids", None):
            bp["archetype_ids"] = list(chosen.archetype_ids)
        # thread the keystone intent so the existing relic generator designs THIS relic
        if dossier.relic_intent is not None:
            bp["relic_intent"] = dossier.relic_intent
        # thread the flavor skin so the splash-art stage dresses the class in the theme's flavor (not mechanics)
        if dossier.skin_bank:
            bp["skin"] = dossier.skin_bank
        self._enrich_archetypes(bp, dossier)
        return bp

    def _reroll_featured(self, brief, cloud: dict, dossier: Dossier) -> None:
        """Phase N-5: replace the blind concept-hash roll with the theme-aware lottery. Wholly guarded —
        the re-roll is an enhancement, so ANY failure keeps the blind roll and never breaks the forge."""
        if self._triad:
            # TRIAD EXPERIMENT: the featured roulette is OFF (forge_class skips the blind roll too) — the
            # wild slot kept landing off-theme subsystems. The cloud stage's nominations are ignored.
            brief.featured = []
            return
        try:
            from .. import featured as featured_mod
            raw = [e for e in (cloud.get("featured_resonance") or [])
                   if isinstance(e, dict) and str(e.get("id", "")).strip()]
            known = {f.id for f in featured_mod.resolve([str(e["id"]) for e in raw])}
            entries = [e for e in raw if str(e["id"]) in known]
            dossier.featured_resonance = entries
            try:
                from .. import ledger
                recent = ledger.featured_recency(self._recency_window)
            except Exception:
                recent = {}
            res_ids = [str(e["id"]) for e in entries]
            picks = featured_mod.themed_roll(dossier.theme, res_ids, recent)
            if not picks:
                return
            brief.featured = [f.id for f in picks]
            why = {str(e["id"]): str(e.get("why") or "").strip() for e in entries}
            parts = [f"{f.id} (resonant: {why[f.id]})" if why.get(f.id)
                     else (f"{f.id} (resonant)" if f.id in known else f"{f.id} (wild roll)")
                     for f in picks]
            self._note("      featured mechanics (theme-aware lottery): " + "; ".join(parts))
            if not res_ids:
                self._note("      (no resonance shortlist from the cloud stage — all slots rolled wild)")
        except Exception as e:  # noqa: BLE001 — never break the forge over the featured re-roll
            self._note(f"      featured re-roll skipped ({e}); keeping the concept-hash roll")

    def _enrich_archetypes(self, bp: dict, dossier: Dossier) -> None:
        """Stamp the map stage's player-facing skin (themed title + strategy pitch) onto bp["archetypes"] so
        the final report can show the same option cards the player chose from. First non-empty mapping wins,
        matching _archetype_options. A bp name that is just the id (the fake/fallback path) gets the catalog's
        display name; wildcard picks have no mapping and keep name + description as their card text."""
        for a in bp.get("archetypes") or []:
            if not isinstance(a, dict):
                continue
            aid = str(a.get("id") or "")
            for m in dossier.mappings:
                if str(m.get("archetype_id") or "") != aid:
                    continue
                if not a.get("title"):
                    a["title"] = str(m.get("title") or "").strip()
                if not a.get("pitch"):
                    a["pitch"] = str(m.get("pitch") or "").strip()
                if a.get("title") and a.get("pitch"):
                    break
            entry = self._catalog.by_id.get(aid)
            if entry is not None and (not a.get("name") or a.get("name") == aid):
                a["name"] = entry.name

    # --- interactive mode: map -> the player's archetype pick -> constrained compose ----------------
    def _map_compose_interactive(self, payload: dict, dossier: Dossier) -> dict:
        """The split map/compose with the human in the middle. Returns the same {mappings, candidates, gaps}
        shape as the fused stage so everything downstream is untouched. A checkpoint that fails/declines
        (empty picks) degrades to unconstrained compose — the forge NEVER blocks on the player."""
        mo = self._run_stage(self._make_gen(_MapOnlyContract(), max_tokens=6000),
                             payload, validate_map_only, "map")
        dossier.mappings = list(mo.get("mappings") or [])
        self._narrate_mappings(dossier)

        options = self._archetype_options(dossier)
        dossier.offered_archetypes = [o["id"] for o in options]
        self._note("[2.5/6] your call: pick up to 2 of the matched engines to build around...")
        try:
            picks = list(self._archetype_checkpoint(options, dossier) or [])
        except Exception:  # noqa: BLE001 — a checkpoint failure must never kill the forge
            picks = []
        known: list[str] = []
        for p in picks:
            pid = str(p)
            if pid in self._catalog.by_id and pid not in known:
                known.append(pid)
        dossier.picked_archetypes = known[:2]
        if dossier.picked_archetypes:
            names = ", ".join(self._catalog.by_id[p].name for p in dossier.picked_archetypes)
            self._note(f"      you chose: {names} — composing every candidate around your pick")
        else:
            self._note("      no pick made — the forge decides (autonomous compose)")

        cpayload = {**payload, "mappings": dossier.mappings, "picked": dossier.picked_archetypes}
        co = self._run_stage(self._make_gen(_ComposeOnlyContract(self._triad), max_tokens=12000),
                             cpayload, validate_compose_for(dossier.picked_archetypes, self._triad), "compose")
        return {"mappings": dossier.mappings, "candidates": list(co.get("candidates") or []),
                "gaps": list(mo.get("gaps") or []) + list(co.get("gaps") or [])}

    def _archetype_options(self, dossier: Dossier) -> list[dict]:
        """The menu the player picks from: every catalog archetype the map stage matched, carrying its
        theme-specific resonance lines ('<cluster>' — <metaphor>) so the choice is explainable. Sorted
        spine-first (most clusters matched), then buildable-first. Padded with buildable WILDCARDS (bold
        class_kinds first) to at least 4 options so the menu is a real choice even on a narrow theme."""
        by_id: dict[str, dict] = {}
        for m in dossier.mappings:
            aid = str(m.get("archetype_id") or "")
            e = self._catalog.by_id.get(aid)
            if e is None:
                continue
            o = by_id.setdefault(aid, {"id": aid, "name": e.name, "description": e.description,
                                       "class_kind": e.class_kind, "buildable": e.buildable,
                                       "block_reasons": list(e.block_reasons), "wildcard": False,
                                       "title": "", "pitch": "", "resonance": []})
            # title + pitch are the player-facing skin (themed headline + WHY); keep the first non-empty
            # ones — for a spine (several clusters, several mappings) the first mapping's are representative
            if not o["title"]:
                o["title"] = str(m.get("title") or "").strip()
            if not o["pitch"]:
                o["pitch"] = str(m.get("pitch") or "").strip()
            cluster = str(m.get("cluster") or "").strip()
            met = str(m.get("metaphor") or "").strip()
            if cluster and met:
                o["resonance"].append(f"'{cluster}' — {met}")
            elif cluster or met:
                o["resonance"].append(met or f"'{cluster}'")
        options = sorted(by_id.values(), key=lambda o: (-len(o["resonance"]), not o["buildable"]))
        if len(options) < 4:
            pool = [e for e in self._catalog.entries if e.buildable and e.id not in by_id]
            pool.sort(key=lambda e: -_KIND_WEIGHT.get(e.class_kind, 0.0))
            for e in pool[:4 - len(options)]:
                options.append({"id": e.id, "name": e.name, "description": e.description,
                                "class_kind": e.class_kind, "buildable": True, "block_reasons": [],
                                "wildcard": True, "title": "", "pitch": "", "resonance": [],
                                "metaphors": list(e.metaphors[:3])})
        return options

    # --- post-processing -------------------------------------------------------------------------
    def _apply_collision_check(self, dossier: Dossier) -> None:
        """When >=2 clusters map to the same archetype, that archetype is the theme's spine — tag any candidate
        that uses it (surface the mechanical center of gravity rather than silently overwriting a mapping)."""
        counts = Counter(str(m.get("archetype_id")) for m in dossier.mappings if m.get("archetype_id"))
        spines = {aid for aid, n in counts.items() if n >= 2}
        if not spines:
            return
        for c in dossier.candidates:
            for aid in c.archetype_ids:
                if aid in spines:
                    c.spine_archetype = aid
                    break

    def _log_gaps(self, dossier: Dossier, mc: dict) -> None:
        """Surface off-vocab gaps the map stage found. They are ALWAYS streamed as a progress note (so they're
        visible); they are only WRITTEN to VOCABULARY_GAPS.md when `gap_log_append` is provided. The website
        passes None — it treats the gap log as a read-only, git-managed single source (a server write would
        dirty the tracked file and block `git pull --ff-only` on deploy), so curate gaps into git instead."""
        entries = []
        for g in (mc.get("gaps") or []):
            if isinstance(g, dict) and str(g.get("title", "")).strip():
                entries.append({"title": g.get("title"), "surfaced_by": f'staged front-end ("{dossier.theme[:40]}")',
                                "fantasy": g.get("fantasy", ""), "sketch": g.get("sketch", "")})
        if not entries:
            return
        titles = ", ".join(str(e["title"]) for e in entries)
        self._note(f"front-end: surfaced {len(entries)} off-vocab gap(s): {titles}")
        if self._gap_log_append is None:
            return  # read-only source (website): gaps surfaced, not written
        try:
            dossier.gaps_logged = self._gap_log_append(entries)
            if dossier.gaps_logged:
                self._note(f"front-end: recorded {dossier.gaps_logged} gap(s) for triage")
        except Exception as e:  # noqa: BLE001 — a gap-log write must never break generation
            self._note(f"front-end: could not append vocab gaps ({e})")

    # --- the picker: faithful-then-distinctive-among-buildable -----------------------------------
    def _pick(self, dossier: Dossier) -> Candidate | None:
        cands = dossier.candidates
        if not cands:
            return None
        # human checkpoint (CLI stdin / web SSE round-trip) wins when not autonomous
        if not self._auto and self._checkpoint is not None:
            picked = self._checkpoint(cands, dossier)
            if isinstance(picked, Candidate):
                return picked
        buildable = [c for c in cands if c.buildable]
        pool = buildable if buildable else cands
        if not buildable:
            self._note("front-end: no fully-buildable candidate; picking the closest (some cards may substitute)")
        # Phase N-4: log the novelty penalty per candidate so the recency pressure is visible in the log.
        if self._recency_window:
            for c in pool:
                pen = self._novelty_penalty(c)
                if pen > 0:
                    self._note(f"      recency penalty {pen:.2f} for {'+'.join(c.archetype_ids)} "
                               "(seen in recent forges)")
        chosen = max(pool, key=lambda c: self._score(c, dossier, cands))
        # Narrate WHY when we can measure fidelity (i.e. the theme had driver facets to be faithful to).
        if dossier.picked_archetypes:
            self._note(f"      fidelity: '{chosen.name}' draws {self._fidelity(chosen, dossier):.0%} of its "
                       "mechanics from YOUR pick — your choice leads the loop")
        elif self._driver_archetypes(dossier):
            self._note(f"      fidelity: '{chosen.name}' draws {self._fidelity(chosen, dossier):.0%} of its "
                       "mechanics from the theme's driver(s) — the verb-rich subject leads the loop")
        return chosen

    def _score(self, c: Candidate, dossier: Dossier, all_cands: list[Candidate]) -> float:
        """FIDELITY dominates (does the candidate's engine come from the theme's driver subject?), then
        distinctiveness breaks ties (bold + unique among the equally-faithful). Fidelity is weighted so a
        fully-faithful candidate always outranks an off-theme one, no matter how exotic the off-theme one is —
        this is what stops the picker drifting to a bold-but-unrelated build (the 'El Pulque' failure).

        Phase N-4: a small novelty penalty (<= _NOVELTY_MAX 2.0, STRICTLY below _FIDELITY_WEIGHT) nudges
        away from archetype pairs/ops the recent forges overused — it only ever breaks ties, like
        distinctiveness, never overriding fidelity."""
        return (_FIDELITY_WEIGHT * self._fidelity(c, dossier)
                + self._distinctiveness(c, all_cands)
                - self._novelty_penalty(c))

    def _novelty_penalty(self, c: Candidate) -> float:
        """Recency-weighted repeat penalty for this candidate's archetypes (0 with no ledger)."""
        try:
            from .. import ledger
            return ledger.pair_penalty(getattr(c, "archetype_ids", None), self._recency_window)
        except Exception:
            return 0.0

    def _driver_archetypes(self, dossier: Dossier) -> set[str]:
        """Archetype ids the map stage drew from a DRIVER-facet cluster (the theme's verb-rich subject). A
        candidate built on these honors the driver. Empty when we can't tell (no facets/mappings) -> fidelity
        goes neutral and the picker degrades to pure distinctiveness (old behavior).

        Interactive mode: an explicit player pick IS the driver — their choice outranks what the theme's
        facets suggest, so fidelity scores candidates by how much of their engine comes from the pick."""
        if dossier.picked_archetypes:
            return set(dossier.picked_archetypes)
        driver_facets = {str(f.get("name", "")).strip().lower()
                         for f in (dossier.facets or []) if str(f.get("role", "")).lower() == "driver"}
        if not driver_facets:
            return set()
        cl_facet = {str(cl.get("name", "")).strip().lower(): str(cl.get("facet", "")).strip().lower()
                    for cl in (dossier.clusters or [])}

        def _is_driver(facet_name: str) -> bool:
            f = (facet_name or "").strip().lower()
            return any(d and (d in f or f in d) for d in driver_facets)

        out: set[str] = set()
        for m in (dossier.mappings or []):
            aid = m.get("archetype_id")
            if aid and _is_driver(cl_facet.get(str(m.get("cluster", "")).strip().lower(), "")):
                out.add(str(aid))
        return out

    def _fidelity(self, c: Candidate, dossier: Dossier) -> float:
        """Fraction of the candidate's archetypes drawn from the driver (verb-rich subject). Neutral (1.0) when
        undeterminable, so the picker falls back to distinctiveness rather than penalizing everyone to zero."""
        drivers = self._driver_archetypes(dossier)
        if not drivers or not c.archetype_ids:
            return 1.0
        hits = sum(1 for aid in c.archetype_ids if aid in drivers)
        return hits / len(c.archetype_ids)

    def _distinctiveness(self, c: Candidate, all_cands: list[Candidate]) -> float:
        """Higher = bolder + more unique. A special class_kind is bolder; rarer archetypes (less shared across
        the candidate set) are more distinctive; a spine (collision) marks a strong thematic center."""
        share = Counter(aid for cand in all_cands for aid in cand.archetype_ids)
        uniqueness = sum(1.0 / share[aid] for aid in c.archetype_ids if share.get(aid))
        spine_bonus = 1.0 if c.spine_archetype else 0.0
        return _KIND_WEIGHT.get(c.class_kind, 0.0) + uniqueness + spine_bonus
