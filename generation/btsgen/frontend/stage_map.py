"""Stage 3+4 (merged): MAP clusters onto the archetype catalog, then COMPOSE candidate builds.

This is where thematic divergence converges onto buildable mechanics. Each cluster is matched to 1-2
catalog archetypes by metaphor resonance (explainable choices); concepts that fit no archetype are logged
as vocabulary gaps (never coded off-vocabulary — that's the closed-vocab safety guarantee). Then N candidate
class builds are composed, each fusing TWO archetypes in tension.

Phase 2 (triad — the DEFAULT since 2026-08-17, `triad_enabled()`; BTS_TRIAD=0 is the 2-archetype
kill-switch): a triad candidate fuses EXACTLY THREE archetypes in a TENSION TRIANGLE — three pairs
(AB/AC/BC), each a distinct game plan via `pair_lines`. The flag-off path is byte-for-byte the legacy
2-archetype compose (same prompts, same `strategic_lines` schema).

Output: {mappings:[...], candidates:[...], gaps:[...]} — one JSON object.
"""
from __future__ import annotations

import json

from ..class_forge import STRATEGIES, triad_enabled

# The strategic-lines requirement, shared verbatim by the fused compose and the interactive compose-only
# prompt. Strategies are NOT a class label: archetypes LEAN toward strategies, but a real class supports
# several game plans from one pool (base-STS Ironclad drafts Strength aggro OR block-matters control OR an
# exhaust/0-cost combo engine), and the player picks a lane mid-run.
_LINES_ASK = """Each candidate must also declare its STRATEGIC LINES — the 2-3 distinct game plans a player \
could draft toward from this ONE pool: "aggro" (maximize offense, win fast before enemies scale), "control" \
(survive and outlast — it ALWAYS needs a named finisher or the deck stalls), "combo" (assemble specific \
pieces into an engine that pops off; thinning/draw/retain/conditional payoffs are its parts). Give each line \
a "strategy" tag, a "line" (how THESE two archetypes play that plan), and a "win_condition" (how that deck \
actually closes a fight). At least 2 DISTINCT strategies per candidate — the two archetypes should carry \
different lines (that is their tension made real). The catalog's `leans` are hints, not limits. \
Optionally give a line an "idiom" — a SHORT free-text texture tag for how it FEELS to pilot (suggestions: \
turtle-scale, one-turn-burst, thin-and-loop, attrition-stall, all-in-gamble, midrange-tempo; or coin your \
own, a few words). It is FLAVOR only: never required, never checked against a list, and dropped if absent."""

_LINES_SCHEMA = """      "strategic_lines": [
        { "strategy": "aggro|control|combo", "line": "how these two archetypes play this plan", "win_condition": "how the deck closes a fight", "idiom": "optional short texture tag, e.g. turtle-scale" }
      ],"""

# --- TRIAD (Phase 2): three archetypes in a tension TRIANGLE. The three PAIRS (AB/AC/BC) ARE the strategic
# lines — each pair gets its own game plan (D3), all three DISTINCT, so three runs of the class feel like
# three classes. This replaces `strategic_lines` with a per-pair `pair_lines` when triad_enabled().
_PAIR_LINES_ASK = """This is a TRIAD candidate: EXACTLY THREE archetypes in a TENSION TRIANGLE. Its three \
PAIRS — AB, AC, BC — are its strategic lines: each PAIR is its own game plan, and the player commits to a \
pair mid-run through what they draft. Declare "pair_lines": one entry per pair (THREE total, covering all \
three pairs of your three ids), each giving the "pair" (two of the candidate's archetype ids), a "strategy" \
("aggro" = maximize offense, win fast; "control" = survive and outlast, ALWAYS needs a named finisher; \
"combo" = assemble pieces into an engine that pops off), a "line" (how THAT pair plays its plan), and a \
"win_condition" (how that pair's deck closes a fight). The three pairs must map to the THREE DISTINCT \
strategies (one aggro, one control, one combo) — that is the replay guarantee. The catalog's `leans` are \
hints, not limits."""

_PAIR_LINES_SCHEMA = """      "pair_lines": [
        { "pair": ["id_a", "id_b"], "strategy": "aggro|control|combo", "line": "how this PAIR plays its plan", "win_condition": "how this pair's deck closes a fight" }
      ],"""


def _pair_line_errors(c: dict, i: int) -> list[str]:
    """Validate one TRIAD candidate's pair_lines (D3): exactly the three pairs of its three archetype ids, each
    a distinct valid strategy, each with a win_condition. The triad analogue of _candidate_line_errors."""
    errs: list[str] = []
    ids = [str(x) for x in (c.get("archetype_ids") or [])]
    lines = c.get("pair_lines")
    if not isinstance(lines, list) or len(lines) < 3:
        return [f"candidate[{i}] is a triad and needs 'pair_lines' — one entry per pair (THREE total), each "
                f"with a 'pair' of two of its archetype ids, a distinct 'strategy' ({'/'.join(STRATEGIES)}), "
                "and a 'win_condition'"]
    all_pairs = {frozenset((ids[a], ids[b])) for a in range(len(ids)) for b in range(a + 1, len(ids))}
    seen_pairs: set[frozenset] = set()
    seen_strats: list[str] = []
    for j, l in enumerate(lines):
        if not isinstance(l, dict):
            errs.append(f"candidate[{i}].pair_lines[{j}] must be an object"); continue
        pr = l.get("pair")
        if not isinstance(pr, (list, tuple)) or len(pr) != 2 or str(pr[0]) == str(pr[1]) \
                or any(str(x) not in ids for x in pr):
            errs.append(f"candidate[{i}].pair_lines[{j}] 'pair' must name two DISTINCT archetype ids of this "
                        f"candidate {ids}")
        else:
            seen_pairs.add(frozenset((str(pr[0]), str(pr[1]))))
        s = str(l.get("strategy", "")).strip().lower()
        if s not in STRATEGIES:
            errs.append(f"candidate[{i}].pair_lines[{j}] strategy '{l.get('strategy')}' must be one of "
                        f"{'/'.join(STRATEGIES)}")
        else:
            seen_strats.append(s)
        if not str(l.get("win_condition", "")).strip():
            errs.append(f"candidate[{i}].pair_lines[{j}] needs a 'win_condition' (how that pair's deck closes a fight)")
    missing = all_pairs - seen_pairs
    if len(ids) == 3 and missing:
        errs.append(f"candidate[{i}].pair_lines must cover ALL THREE pairs of {ids}")
    if len(set(seen_strats)) < len(seen_strats):
        errs.append(f"candidate[{i}] pairs must serve THREE DISTINCT strategies (got {seen_strats})")
    return errs


def _candidate_line_errors(c: dict, i: int, triad: bool = False) -> list[str]:
    """Validate one candidate's strategy declaration. Legacy (2-arch): strategic_lines — 2-3 entries,
    strategies from the taxonomy, >=2 distinct, each with a win_condition. Triad: the per-pair pair_lines
    (see _pair_line_errors). Shared by the fused and the compose-only validators."""
    if triad:
        errs = _pair_line_errors(c, i)
        ids = c.get("archetype_ids")
        if isinstance(ids, list) and len(ids) != 3:
            errs.append(f"candidate[{i}] is a triad and must fuse EXACTLY THREE archetypes (got {ids})")
        return errs
    errs: list[str] = []
    lines = c.get("strategic_lines")
    if not isinstance(lines, list) or len(lines) < 2:
        return [f"candidate[{i}] needs 'strategic_lines' — 2-3 entries, at least 2 distinct strategies "
                f"({'/'.join(STRATEGIES)}), each with a win_condition"]
    seen: set[str] = set()
    for j, l in enumerate(lines):
        if not isinstance(l, dict):
            errs.append(f"candidate[{i}].strategic_lines[{j}] must be an object"); continue
        s = str(l.get("strategy", "")).strip().lower()
        if s not in STRATEGIES:
            errs.append(f"candidate[{i}].strategic_lines[{j}] strategy '{l.get('strategy')}' must be one of "
                        f"{'/'.join(STRATEGIES)}")
        else:
            seen.add(s)
        if not str(l.get("win_condition", "")).strip():
            errs.append(f"candidate[{i}].strategic_lines[{j}] needs a 'win_condition' (how the deck closes a fight)")
    if len(seen) < 2:
        errs.append(f"candidate[{i}] needs at least 2 DISTINCT strategies among its lines (got {sorted(seen)})")
    return errs


# Deterministic strategic lines for the offline fakes (both compose contracts).
_FAKE_LINES = [
    {"strategy": "aggro", "line": "cheap attacks plus stacking buffs", "win_condition": "kill before turn 6",
     "idiom": "one-turn-burst"},
    {"strategy": "control", "line": "block wall that outlasts", "win_condition": "survive, then the rare finisher closes",
     "idiom": "turtle-scale"},
]

# The three DISTINCT strategies, in order, for a triad fake's three pairs (D3).
_FAKE_TRIAD_STRATS = list(STRATEGIES)


def _fake_pair_lines(ids: list[str]) -> list[dict]:
    """Deterministic per-pair strategy mapping for a triad fake: the three pairs of `ids`, each a distinct
    strategy (aggro/control/combo), each with a win_condition — enough for _pair_line_errors to pass."""
    pairs = [(ids[a], ids[b]) for a in range(len(ids)) for b in range(a + 1, len(ids))]
    out: list[dict] = []
    for k, (a, b) in enumerate(pairs[:3]):
        s = _FAKE_TRIAD_STRATS[k % len(_FAKE_TRIAD_STRATS)]
        out.append({"pair": [a, b], "strategy": s, "line": f"the {a}+{b} {s} lane",
                    "win_condition": f"the {s} finisher closes"})
    return out


# The fused map+compose system prompt. Legacy (2-archetype) is byte-for-byte today's prompt; the triad variant
# (Phase 2, opt-in) swaps the "EXACTLY TWO archetypes in tension" ask for the tension-triangle ask and the
# strategic_lines schema for pair_lines. Built by a function so the flag picks the variant without a re-touch.
def _map_compose_system(triad: bool = False) -> str:
    if triad:
        compose_ask = ("3. COMPOSE the requested number of candidate class builds. Each candidate fuses "
                       "EXACTLY THREE archetypes in a TENSION TRIANGLE — the three pull against each other and "
                       "each PAIR (AB/AC/BC) is a distinct game plan, which is what makes the class a real "
                       "triangle of choices instead of a pile of synergies. STRONGLY prefer archetypes tagged "
                       "BUILDABLE; you MAY use a NEEDS-VOCAB archetype when it's the theme's most distinctive "
                       "idea, but know it will be flagged. Make the candidates genuinely DIFFERENT from each "
                       "other — different triangles, different fantasies.")
        lines_ask, lines_schema = _PAIR_LINES_ASK, _PAIR_LINES_SCHEMA
        ids_schema = '"archetype_ids": ["id_a", "id_b", "id_c"],\n      "tension": "how the three pull against each other (the triangle)",'
    else:
        compose_ask = ("3. COMPOSE the requested number of candidate class builds. Each candidate fuses EXACTLY "
                       "TWO archetypes that are in productive TENSION (they pull against each other — e.g. "
                       "patience vs. aggression, defense vs. sacrifice), which is what makes a class feel like a "
                       "real identity instead of a pile of synergies. STRONGLY prefer archetypes tagged BUILDABLE; "
                       "you MAY use a NEEDS-VOCAB archetype when it's the theme's most distinctive idea, but know "
                       "it will be flagged (its signature mechanic isn't in the engine yet). Make the candidates "
                       "genuinely DIFFERENT from each other — different spines, different fantasies.")
        lines_ask, lines_schema = _LINES_ASK, _LINES_SCHEMA
        ids_schema = '"archetype_ids": ["id_a", "id_b"],\n      "tension": "how the two pull against each other",'
    return """You are the convergent front-end of a class designer for "BLANK the spire", a Slay-the-Spire-like \
deckbuilder. You receive (a) a theme's concept CLUSTERS and (b) an ARCHETYPE CATALOG — reusable mechanical \
engines, each tagged with metaphors and a buildability flag. Do THREE things:

1. MAP every cluster to 1-2 catalog archetypes whose metaphors resonate with it. Cite the resonance (which \
metaphor / why) so the choice is explainable. The catalog's metaphors are a STARTING point — you may draw your \
own connection if it's strong. If a cluster wants a mechanic NO archetype covers, still map it to the closest \
one BUT set "off_vocab": true on that mapping and add a "gaps" entry describing the missing mechanic. NEVER \
invent a new archetype id — only use ids from the catalog.

2. Notice COLLISIONS: when two clusters map to the same archetype, that archetype is the theme's mechanical \
spine — lean into it rather than discarding a mapping.

""" + compose_ask + """

""" + lines_ask + """

Output EXACTLY ONE JSON object, nothing else:
{
  "mappings": [
    { "cluster": "cluster name", "archetype_id": "an id from the catalog", "metaphor": "the resonance, one line", "off_vocab": false }
  ],
  "candidates": [
    { "name": "<= 24 chars", "fantasy": "the class fantasy in one line", """ + ids_schema + """
""" + lines_schema + """
      "core_loop": "the turn-to-turn play loop",
      "weakness": "where the class is vulnerable", "suggested_max_hp": 72 }
  ],
  "gaps": [
    { "title": "short name", "fantasy": "what it would serve", "sketch": "the missing mechanic, one line" }
  ]
}
Return only the JSON object. "gaps" may be an empty list."""


class _MapComposeContract:
    def __init__(self, triad: bool | None = None) -> None:
        self.triad = triad_enabled(triad)

    def system_prompt(self) -> str:
        return _map_compose_system(self.triad)

    def user_brief(self, payload) -> str:
        clusters = payload.get("clusters") or []
        catalog_block = payload.get("catalog_block") or ""
        n = int(payload.get("n", 3) or 3)
        concept = payload.get("concept", "")
        recency = str(payload.get("recency", "")).strip()
        if self.triad:
            compose_line = (f"Map every cluster, then compose {n} DISTINCT candidate builds (3 archetypes each, "
                            "in a tension triangle, each with pair_lines covering all three pairs mapped to the "
                            "three DISTINCT strategies, each with a win_condition).")
        else:
            compose_line = (f"Map every cluster, then compose {n} DISTINCT candidate builds (2 archetypes each, "
                            "in tension, each with 2-3 strategic_lines covering at least 2 distinct strategies, "
                            "each line with a win_condition).")
        return (
            'Theme: "' + str(concept).strip() + '"\n\n'
            "THE CONCEPT CLUSTERS:\n" + json.dumps(clusters, indent=2) + "\n\n"
            "THE ARCHETYPE CATALOG (use these ids only):\n" + catalog_block + "\n\n"
            + (recency + "\n\n" if recency else "")
            + compose_line + " Prefer BUILDABLE archetypes. Return only the JSON object."
        )

    def repair_message(self, text: str, errors: list[str]) -> str:
        bullet = "\n".join(f"- {e}" for e in errors)
        return ("That map/compose output failed validation:\n" + bullet +
                "\n\nHere is what you returned:\n" + text +
                "\n\nReturn a corrected SINGLE JSON object with 'mappings' and 'candidates' (archetype ids from "
                "the catalog only). Only the JSON object.")

    def fake_output(self, payload) -> dict:
        catalog = payload.get("_catalog")
        bids = sorted(catalog.buildable_ids()) if catalog is not None else ["poison_attrition", "block_bulwark"]
        unbuildable = [e.id for e in (catalog.entries if catalog is not None else []) if not e.buildable]
        # Phase 2 (triad): a fake candidate carries THREE archetype ids + pair_lines; legacy stays two + lines.
        fill = (bids + ["poison_attrition", "block_bulwark", "power_ramp"])
        a, b, cc = fill[:3]
        clusters = payload.get("clusters") or [{"name": "Core"}, {"name": "Cost"}, {"name": "Payoff"}]
        cnames = [str(c.get("name", f"c{i}")) for i, c in enumerate(clusters)]
        # Two clusters map to the SAME archetype `a` -> exercises the collision/spine post-process.
        mappings = [
            {"cluster": cnames[0], "archetype_id": a, "metaphor": "fake resonance", "off_vocab": False},
            {"cluster": cnames[1 % len(cnames)], "archetype_id": a, "metaphor": "fake resonance (spine)", "off_vocab": False},
            {"cluster": cnames[2 % len(cnames)], "archetype_id": b, "metaphor": "fake resonance", "off_vocab": False},
        ]
        if self.triad:
            build_ids = [a, b, cc]
            good = {"name": "Fake Buildable", "fantasy": "an offline buildable triad candidate",
                    "archetype_ids": build_ids, "tension": "a/b/c triangle", "pair_lines": _fake_pair_lines(build_ids),
                    "core_loop": "loop", "weakness": "weak", "suggested_max_hp": 72}
        else:
            good = {"name": "Fake Buildable", "fantasy": "an offline buildable candidate",
                    "archetype_ids": [a, b], "tension": "a vs b", "strategic_lines": list(_FAKE_LINES),
                    "core_loop": "loop", "weakness": "weak", "suggested_max_hp": 72}
        candidates = [good]
        # Always compose a deliberately NEEDS-VOCAB second candidate so the picker has something to avoid
        # (exercises distinctive-among-buildable). Prefer a REAL NEEDS-VOCAB archetype; once the catalog is fully
        # buildable — every planned vocab gap shipped, as of Phase S / gap #1 — fall back to a sentinel id, which
        # hydrate_candidate marks NEEDS-VOCAB ("unknown archetype id"), keeping the contrast alive regardless.
        gap_arch = unbuildable[0] if unbuildable else "__needs_vocab_stub__"
        if self.triad:
            gap_ids = [a, b, gap_arch]
            candidates.append({"name": "Fake Distinctive", "fantasy": "an offline gap-bound triad candidate",
                               "archetype_ids": gap_ids, "tension": "a/b/gap triangle",
                               "pair_lines": _fake_pair_lines(gap_ids),
                               "core_loop": "loop", "weakness": "weak", "suggested_max_hp": 70})
        else:
            candidates.append({"name": "Fake Distinctive", "fantasy": "an offline gap-bound candidate",
                               "archetype_ids": [a, gap_arch], "tension": "a vs gap",
                               "strategic_lines": list(_FAKE_LINES),
                               "core_loop": "loop", "weakness": "weak", "suggested_max_hp": 70})
        return {"mappings": mappings, "candidates": candidates,
                "gaps": [{"title": "Fake Gap", "fantasy": "offline", "sketch": "a missing mechanic"}]}


# --- the INTERACTIVE split: map-only, then (after the player's archetype pick) compose-only -------
# The fused _MapComposeContract above stays the autonomous default. Interactive mode ("you pick the
# engines") needs a human between the two halves, so each half gets its own contract; the prompts are
# the fused prompt's steps re-cut, with compose gaining the player-pick constraint.

_MAP_SYSTEM = """You are the convergent front-end of a class designer for "BLANK the spire", a Slay-the-Spire-like \
deckbuilder. You receive (a) a theme's concept CLUSTERS and (b) an ARCHETYPE CATALOG — reusable mechanical \
engines, each tagged with metaphors and a buildability flag. Do TWO things:

1. MAP every cluster to 1-2 catalog archetypes whose metaphors resonate with it. Cite the resonance (which \
metaphor / why) so the choice is explainable. The catalog's metaphors are a STARTING point — you may draw your \
own connection if it's strong. If a cluster wants a mechanic NO archetype covers, still map it to the closest \
one BUT set "off_vocab": true on that mapping and add a "gaps" entry describing the missing mechanic. NEVER \
invent a new archetype id — only use ids from the catalog.

2. Notice COLLISIONS: when two clusters map to the same archetype, that archetype is the theme's mechanical \
spine — lean into it rather than discarding a mapping.

3. PITCH each mapping to the player. The player will choose which engines their class is built around, and the \
pitch is what they read to decide: EXACTLY ONE sentence, spoken to them, that says HOW THE DECK WINS — the \
concrete strategy first, in plain mechanical language (name the moves and the payoff), with the theme as light \
seasoning, never the other way round. E.g. "Use retain effects to power up cards for a huge swing, and survive \
until they're ready by healing yourself with nature magic." or "Use your orbs to stack defenses while thinning \
your deck to set up an infinite combo." One sentence — no pure imagery, no second sentence.

4. TITLE each mapping: a short, punchy name (2-4 words) that fuses the theme with the engine — the headline \
on the player's option card. E.g. "mansa musa" + a big-energy engine -> "Rich in Energy"; "prison inmate" + \
delayed payoff -> "Serving the Sentence". Themed words, not catalog jargon.

Output EXACTLY ONE JSON object, nothing else:
{
  "mappings": [
    { "cluster": "cluster name", "archetype_id": "an id from the catalog", "metaphor": "the resonance, one line",
      "title": "2-4 themed words — the option card's headline",
      "pitch": "ONE sentence, strategy first: how this deck wins (the moves and the payoff), theme as seasoning", "off_vocab": false }
  ],
  "gaps": [
    { "title": "short name", "fantasy": "what it would serve", "sketch": "the missing mechanic, one line" }
  ]
}
Return only the JSON object. "gaps" may be an empty list."""


class _MapOnlyContract:
    def system_prompt(self) -> str:
        return _MAP_SYSTEM

    def user_brief(self, payload) -> str:
        clusters = payload.get("clusters") or []
        catalog_block = payload.get("catalog_block") or ""
        concept = payload.get("concept", "")
        recency = str(payload.get("recency", "")).strip()
        return (
            'Theme: "' + str(concept).strip() + '"\n\n'
            "THE CONCEPT CLUSTERS:\n" + json.dumps(clusters, indent=2) + "\n\n"
            "THE ARCHETYPE CATALOG (use these ids only):\n" + catalog_block + "\n\n"
            + (recency + "\n\n" if recency else "")
            + "Map every cluster to 1-2 archetypes, each with a resonance line, a themed 2-4 word title, and "
            "a ONE-sentence pitch saying how the deck wins (strategy first, theme as seasoning). "
            "Return only the JSON object."
        )

    def repair_message(self, text: str, errors: list[str]) -> str:
        bullet = "\n".join(f"- {e}" for e in errors)
        return ("That map output failed validation:\n" + bullet +
                "\n\nHere is what you returned:\n" + text +
                "\n\nReturn a corrected SINGLE JSON object with 'mappings' (archetype ids from the catalog "
                "only) and 'gaps'. Only the JSON object.")

    def fake_output(self, payload) -> dict:
        catalog = payload.get("_catalog")
        bids = sorted(catalog.buildable_ids()) if catalog is not None else ["poison_attrition", "block_bulwark"]
        a, b = (bids + ["poison_attrition", "block_bulwark"])[:2]
        clusters = payload.get("clusters") or [{"name": "Core"}, {"name": "Cost"}, {"name": "Payoff"}]
        cnames = [str(c.get("name", f"c{i}")) for i, c in enumerate(clusters)]
        # Two clusters map to the SAME archetype `a` -> exercises the collision/spine post-process.
        return {"mappings": [
            {"cluster": cnames[0], "archetype_id": a, "metaphor": "fake resonance", "title": "Fake Core Title",
             "pitch": "stack a fake resource every turn and cash it in for one big hit.", "off_vocab": False},
            {"cluster": cnames[1 % len(cnames)], "archetype_id": a, "metaphor": "fake resonance (spine)",
             "title": "Fake Spine Title",
             "pitch": "build the fake spine engine while blocking until it snowballs.", "off_vocab": False},
            {"cluster": cnames[2 % len(cnames)], "archetype_id": b, "metaphor": "fake resonance",
             "title": "Fake Counter Title",
             "pitch": "trade fake hit points for cheap power, then claw them back.", "off_vocab": False},
        ], "gaps": [{"title": "Fake Gap", "fantasy": "offline", "sketch": "a missing mechanic"}]}


def validate_map_only(obj: dict) -> list[str]:
    errs: list[str] = []
    if not isinstance(obj, dict):
        return ["map output is not an object"]
    maps = obj.get("mappings")
    if not isinstance(maps, list) or not maps:
        errs.append("need a non-empty 'mappings' list")
    else:
        for i, m in enumerate(maps):
            if not isinstance(m, dict) or not str(m.get("archetype_id", "")).strip():
                errs.append(f"mapping[{i}] needs an 'archetype_id'")
            elif not str(m.get("pitch", "")).strip():
                errs.append(f"mapping[{i}] needs a player-facing 'pitch' (how the deck wins)")
            elif len(str(m.get("pitch", "")).strip()) > 220:
                errs.append(f"mapping[{i}] pitch too long — ONE sentence, ~160 chars max, strategy-first")
            elif not str(m.get("title", "")).strip():
                errs.append(f"mapping[{i}] needs a themed 2-4 word 'title' (the option card's headline)")
    return errs


# The compose-only system prompt (interactive path). Legacy is byte-for-byte today's; the triad variant swaps
# the two-archetype ask for the tension-triangle + pair_lines, and the pick constraint stays (<=2 picks, filled
# to three under triad). Built by a function so the flag picks the variant.
def _compose_system(triad: bool = False) -> str:
    if triad:
        fuse = ("Your job: COMPOSE the requested number of candidate class builds. Each candidate fuses EXACTLY "
                "THREE archetypes in a TENSION TRIANGLE — the three pull against each other and each PAIR "
                "(AB/AC/BC) is a distinct game plan. STRONGLY prefer archetypes tagged BUILDABLE; you MAY use a "
                "NEEDS-VOCAB archetype when it's the theme's most distinctive idea, but know it will be flagged. "
                "Make the candidates genuinely DIFFERENT from each other — different triangles, different fantasies.")
        pick = ("THE PLAYER MAY HAVE PICKED archetypes (the brief says so). When picks are present they are a HARD "
                "constraint: EVERY candidate MUST include ALL picked archetype ids, filling the triangle to THREE "
                "with partners from the theme's mappings. One pick = vary the OTHER TWO archetypes per candidate. "
                "Two picks = every candidate fuses those two plus a varied third. No picks = compose freely from "
                "the mappings.")
        lines_ask, lines_schema = _PAIR_LINES_ASK, _PAIR_LINES_SCHEMA
        ids_schema = '"archetype_ids": ["id_a", "id_b", "id_c"],\n      "tension": "how the three pull against each other (the triangle)",'
    else:
        fuse = ("Your job: COMPOSE the requested number of candidate class builds. Each candidate fuses EXACTLY "
                "TWO archetypes that are in productive TENSION (they pull against each other — e.g. patience vs. "
                "aggression, defense vs. sacrifice), which is what makes a class feel like a real identity instead "
                "of a pile of synergies. STRONGLY prefer archetypes tagged BUILDABLE; you MAY use a NEEDS-VOCAB "
                "archetype when it's the theme's most distinctive idea, but know it will be flagged. Make the "
                "candidates genuinely DIFFERENT from each other — different spines, different fantasies.")
        pick = ("THE PLAYER MAY HAVE PICKED archetypes (the brief says so). When picks are present they are a HARD "
                "constraint: EVERY candidate MUST include ALL picked archetype ids. One pick = vary the SECOND "
                "archetype per candidate (each partner in a different tension with the pick, drawn from the theme's "
                "mappings where possible). Two picks = every candidate fuses exactly those two; differentiate the "
                "candidates by fantasy, loop, and which archetype leads. No picks = compose freely from the mappings.")
        lines_ask, lines_schema = _LINES_ASK, _LINES_SCHEMA
        ids_schema = '"archetype_ids": ["id_a", "id_b"],\n      "tension": "how the two pull against each other",'
    return """You are the convergent front-end of a class designer for "BLANK the spire", a Slay-the-Spire-like \
deckbuilder. A theme has already been decomposed into concept CLUSTERS and MAPPED onto an ARCHETYPE CATALOG of \
reusable mechanical engines. """ + fuse + """

""" + pick + """

""" + lines_ask + """

Output EXACTLY ONE JSON object, nothing else:
{
  "candidates": [
    { "name": "<= 24 chars", "fantasy": "the class fantasy in one line", """ + ids_schema + """
""" + lines_schema + """
      "core_loop": "the turn-to-turn play loop",
      "weakness": "where the class is vulnerable", "suggested_max_hp": 72 }
  ],
  "gaps": [
    { "title": "short name", "fantasy": "what it would serve", "sketch": "the missing mechanic, one line" }
  ]
}
Return only the JSON object. "gaps" may be an empty list."""


class _ComposeOnlyContract:
    def __init__(self, triad: bool | None = None) -> None:
        self.triad = triad_enabled(triad)

    def system_prompt(self) -> str:
        return _compose_system(self.triad)

    def user_brief(self, payload) -> str:
        clusters = payload.get("clusters") or []
        mappings = payload.get("mappings") or []
        catalog_block = payload.get("catalog_block") or ""
        n = int(payload.get("n", 3) or 3)
        concept = payload.get("concept", "")
        recency = str(payload.get("recency", "")).strip()
        picked = [str(p) for p in (payload.get("picked") or [])]
        n_arch = 3 if self.triad else 2
        if picked:
            if self.triad:
                fill_how = ("all three of these plus a varied third" if len(picked) > 1 else
                            "this archetype (fill the triangle with two varied partners per candidate)")
            else:
                fill_how = ("both of these archetypes." if len(picked) > 1 else
                            "this archetype (vary its partner per candidate).")
            pick_line = ("THE PLAYER PICKED: " + ", ".join(picked) +
                         " — every candidate MUST include " + fill_how)
        else:
            pick_line = "THE PLAYER PICKED: nothing (compose freely from the mappings)."
        if self.triad:
            compose_line = (f"Compose {n} DISTINCT candidate builds (3 archetypes each, in a tension triangle, "
                            "each with pair_lines covering all three pairs mapped to the three DISTINCT "
                            "strategies, each with a win_condition).")
        else:
            compose_line = (f"Compose {n} DISTINCT candidate builds (2 archetypes each, in tension, each with 2-3 "
                            "strategic_lines covering at least 2 distinct strategies, each line with a "
                            "win_condition).")
        return (
            'Theme: "' + str(concept).strip() + '"\n\n'
            "THE CONCEPT CLUSTERS:\n" + json.dumps(clusters, indent=2) + "\n\n"
            "HOW THE CLUSTERS MAPPED:\n" + json.dumps(mappings, indent=2) + "\n\n"
            "THE ARCHETYPE CATALOG (use these ids only):\n" + catalog_block + "\n\n"
            + pick_line + "\n\n"
            + (recency + "\n\n" if recency else "")
            + compose_line + " Prefer BUILDABLE archetypes. Return only the JSON object."
        )

    def repair_message(self, text: str, errors: list[str]) -> str:
        bullet = "\n".join(f"- {e}" for e in errors)
        return ("That compose output failed validation:\n" + bullet +
                "\n\nHere is what you returned:\n" + text +
                "\n\nReturn a corrected SINGLE JSON object with 'candidates' (archetype ids from the catalog "
                "only; honor the player's picked archetypes in EVERY candidate). Only the JSON object.")

    def fake_output(self, payload) -> dict:
        catalog = payload.get("_catalog")
        bids = sorted(catalog.buildable_ids()) if catalog is not None else ["poison_attrition", "block_bulwark"]
        picked = [str(p) for p in (payload.get("picked") or [])]
        fill = [b for b in bids + ["poison_attrition", "block_bulwark", "power_ramp"] if b not in picked]
        if self.triad:
            # Phase 2 (triad): fill each candidate's triangle to THREE, honoring every pick.
            ids1 = (picked + fill)[:3]
            ids2 = (picked + fill[1:])[:3] if len(picked) < 3 else list(ids1)
            return {"candidates": [
                {"name": "Fake Picked", "fantasy": "an offline triad candidate honoring the pick",
                 "archetype_ids": ids1, "tension": "a/b/c triangle", "pair_lines": _fake_pair_lines(ids1),
                 "core_loop": "loop", "weakness": "weak", "suggested_max_hp": 72},
                {"name": "Fake Picked II", "fantasy": "a second offline triad candidate",
                 "archetype_ids": ids2, "tension": "a/b/c triangle", "pair_lines": _fake_pair_lines(ids2),
                 "core_loop": "loop", "weakness": "weak", "suggested_max_hp": 70},
            ], "gaps": []}
        pair1 = (picked + fill)[:2]
        pair2 = (picked + fill[1:])[:2] if len(picked) < 2 else list(pair1)
        return {"candidates": [
            {"name": "Fake Picked", "fantasy": "an offline candidate honoring the pick",
             "archetype_ids": pair1, "tension": "a vs b", "strategic_lines": list(_FAKE_LINES),
             "core_loop": "loop", "weakness": "weak", "suggested_max_hp": 72},
            {"name": "Fake Picked II", "fantasy": "a second offline candidate",
             "archetype_ids": pair2, "tension": "a vs c", "strategic_lines": list(_FAKE_LINES),
             "core_loop": "loop", "weakness": "weak", "suggested_max_hp": 70},
        ], "gaps": []}


def validate_compose_for(picked: list[str], triad: bool | None = None):
    """Validator closure for the compose-only stage: structural checks + the player-pick hard constraint
    (every candidate must include all picked ids) so a violation goes back through the repair loop. `triad`
    (default: triad_enabled()) switches candidate-line validation to the per-pair pair_lines (D3)."""
    need = [str(p) for p in (picked or [])]
    is_triad = triad_enabled(triad)

    def _validate(obj: dict) -> list[str]:
        errs: list[str] = []
        if not isinstance(obj, dict):
            return ["compose output is not an object"]
        cands = obj.get("candidates")
        if not isinstance(cands, list) or not cands:
            return ["need a non-empty 'candidates' list"]
        for i, c in enumerate(cands):
            if not isinstance(c, dict):
                errs.append(f"candidate[{i}] must be an object"); continue
            ids = c.get("archetype_ids")
            if not isinstance(ids, list) or not ids:
                errs.append(f"candidate[{i}] needs 'archetype_ids'")
                ids = []
            if not str(c.get("name", "")).strip():
                errs.append(f"candidate[{i}] needs a name")
            errs += _candidate_line_errors(c, i, triad=is_triad)
            for p in need:
                if p not in [str(x) for x in ids]:
                    errs.append(f"candidate[{i}] must include the player's picked archetype '{p}'")
        return errs

    return _validate


def validate_map_for(triad: bool | None = None):
    """Validator closure for the fused map+compose stage — the triad analogue of validate_compose_for. `triad`
    (default: triad_enabled()) switches candidate-line validation to pair_lines. `validate_map` below is the
    legacy (flag-off) default kept for callers that don't thread the flag."""
    is_triad = triad_enabled(triad)

    def _validate(obj: dict) -> list[str]:
        errs: list[str] = []
        if not isinstance(obj, dict):
            return ["map output is not an object"]
        if not isinstance(obj.get("mappings"), list):
            errs.append("need a 'mappings' list")
        cands = obj.get("candidates")
        if not isinstance(cands, list) or not cands:
            errs.append("need a non-empty 'candidates' list")
        else:
            for i, c in enumerate(cands):
                if not isinstance(c, dict):
                    errs.append(f"candidate[{i}] must be an object"); continue
                ids = c.get("archetype_ids")
                if not isinstance(ids, list) or not ids:
                    errs.append(f"candidate[{i}] needs 'archetype_ids'")
                if not str(c.get("name", "")).strip():
                    errs.append(f"candidate[{i}] needs a name")
                errs += _candidate_line_errors(c, i, triad=is_triad)
        return errs

    return _validate


def validate_map(obj: dict) -> list[str]:
    """Legacy (flag-off) fused map+compose validator. The builder now threads the flag via validate_map_for;
    this bare function stays as the 2-archetype default for back-compat."""
    return validate_map_for(False)(obj)
