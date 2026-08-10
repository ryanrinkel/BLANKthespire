"""Stage 1+2 (merged): DECOMPOSE the theme -> balanced association CLOUD -> CLUSTERS.

Pure thematic divergence then convergence — NO mechanics yet. The cloud is where creativity comes from;
keeping it mechanics-free stops the model from collapsing the theme onto a generic build too early.

The theme is first broken into its distinct IDEAS (facets), each tagged with a ROLE by how action-rich it is:
a "driver" facet is verb/action-rich (the natural engine of a class); a "flavor" facet is imagery/mood-rich
(it dresses the class — names, look, feel). This is what stops a vivid flavor idea (e.g. "Mexican culture")
from crowding out the mechanically-natural driver idea (e.g. "soccer") — every facet gets a per-facet concept
QUOTA, and every driver facet must survive into the clusters, so the driver's actions can't be dropped.

Phase N-5 adds one MECHANIC touch at the very end: a RESONANCE shortlist over the featured-mechanic menu
(which menu entries FEEL made for this theme). It runs strictly AFTER the pure thematic work so the menu
cannot steer the cloud; the shortlist only NOMINATES — featured.themed_roll makes the final picks code-side.

Output: one JSON object {facets:[...], concepts:[...], clusters:[...], featured_resonance:[{id, why}]}.
"""
from __future__ import annotations

import json
import re

from ..featured import FEATURED_MENU, menu_block

_SYSTEM = """You are the divergent front-end of a class designer for "BLANK the spire", a Slay-the-Spire-like \
deckbuilder. Given a player's THEME, you brainstorm — first break the theme into its distinct ideas, then \
free-associate on each. For the first three tasks you do NOT talk about game mechanics, cards, damage, or \
numbers; they are pure thematic association, the raw material a designer free-associates before deciding how \
anything works. Only the LAST task (resonance) touches mechanics, and only as a shortlist.

Do FOUR things:

1. DECOMPOSE the theme into its 1-4 distinct IDEAS (facets). "haunted lighthouse keeper" -> [ghosts/haunting, \
the lighthouse, solitude]; a single-idea theme like "vampires" has just one facet. For EACH facet assign a \
ROLE by how ACTION-rich it is:
   - "driver": rich in VERBS / actions / interactions — things you DO (a sport, a fighting style, a job full of \
tasks). These are the natural engine of a class.
   - "flavor": rich in IMAGERY / mood / names but few actions (a culture, a place, an aesthetic). These dress a \
class — its names, look, and feel.
   There MUST be at least one driver: pick the MOST action-rich facet as a driver even if the theme is mostly \
flavor. Give a one-line "why". Be honest — a sport or craft is a driver; a culture or mood is flavor.

2. CLOUD — free-associate a BALANCED concept cloud: brainstorm 6-10 short evocative concepts for each facet \
(images, feelings, objects, roles, places, verbs), then pour them ALL into ONE flat list. Every facet gets its \
FAIR SHARE — do NOT let a vivid facet crowd out the others. Diverge hard; surprise yourself; include the obvious \
AND the oblique.

3. CLUSTER the cloud into 3-6 named threads, each with a one-line "feeling" and the "facet" (by name) it springs \
from. EVERY driver facet MUST yield at least one cluster — a driver's actions are the class's future mechanics \
and cannot be dropped. Threads should pull in different directions, not restate each other.

4. RESONATE — ONLY now, with the thematic work done: from the MECHANIC MENU below, shortlist the 4-8 mechanics \
whose FANTASY most resonates with this theme (which would feel made-for-it in play), each with a one-line "why" \
tying it to a facet or cluster you produced. Judge by feel and fantasy, not power. This is a NOMINATION, not a \
choice — a lottery makes the final picks. Do NOT let the menu steer tasks 1-3.

MECHANIC MENU (id: fantasy):
{menu}

Output EXACTLY ONE JSON object, nothing else, in this shape:
{
  "facets": [
    { "name": "short idea name", "role": "driver|flavor", "richness": "verb-rich|image-rich|...", "why": "one line" }
  ],
  "concepts": ["concept one", "concept two", "... one FLAT array of plain strings, all facets mixed together ..."],
  "clusters": [
    { "name": "Short Thread Name", "feeling": "one line", "facet": "which facet name it springs from",
      "concepts": ["pulled", "from", "the", "cloud"] }
  ],
  "featured_resonance": [
    { "id": "a mechanic id from the MENU", "why": "one line tying it to a facet/cluster" }
  ]
}
"concepts" is a FLAT array of plain strings — never nest arrays or objects inside it, never put a key: inside it. \
Emit strictly valid JSON. Return only the JSON object.""".replace("{menu}", menu_block())


class _CloudClusterContract:
    def system_prompt(self) -> str:
        return _SYSTEM

    def user_brief(self, brief) -> str:
        concept = getattr(brief, "concept", None) or (brief.get("concept") if isinstance(brief, dict) else "") or ""
        return ('Theme to diverge on:\n"' + concept.strip() + '"\n\n'
                "Decompose it into 1-4 facets (each tagged driver/flavor by how action-rich it is), brainstorm a "
                "BALANCED cloud (6-10 concepts per facet), then cluster into 3-6 threads. Every driver facet must "
                "yield a cluster. Finish with the featured_resonance shortlist (4-8 menu ids + why). "
                "Return only the JSON object.")

    def repair_message(self, text: str, errors: list[str]) -> str:
        bullet = "\n".join(f"- {e}" for e in errors)
        return ("That decompose/cloud/cluster output failed validation:\n" + bullet +
                "\n\nHere is what you returned:\n" + text +
                "\n\nReturn a corrected SINGLE JSON object with 'facets', 'concepts' and 'clusters' (every driver "
                "facet must have at least one cluster whose 'facet' names it). Only the JSON object.")

    def fake_output(self, brief) -> dict:
        concept = getattr(brief, "concept", None) or (brief.get("concept") if isinstance(brief, dict) else "") or ""
        words = [w for w in re.split(r"[^a-zA-Z]+", concept) if len(w) > 2][:6] or ["theme"]
        base = [f"{w} {suffix}" for w in words
                for suffix in ("imagery", "echo", "shadow")][:18]
        concepts = base + ["ritual", "the threshold", "patience", "the turning point", "old power", "the cost"]
        # Two facets so the offline path exercises the driver/flavor split + driver-coverage check.
        driver = f"{words[0].title()} (action)"
        flavor = f"{words[-1].title()} (flavor)" if len(words) > 1 else "Mood"
        facets = [
            {"name": driver, "role": "driver", "richness": "verb-rich", "why": "the action-rich core (offline)"},
            {"name": flavor, "role": "flavor", "richness": "image-rich", "why": "dresses the class (offline)"},
        ]
        clusters = [
            {"name": f"{words[0].title()} Core", "feeling": "the obvious heart of the theme", "facet": driver,
             "concepts": concepts[:6]},
            {"name": "The Hidden Cost", "feeling": "what the theme takes from you", "facet": flavor,
             "concepts": concepts[6:12]},
            {"name": "The Turning Point", "feeling": "the moment it pays off", "facet": driver,
             "concepts": concepts[12:18]},
        ]
        # A deterministic slice of the menu so the offline path exercises the N-5 resonance -> themed_roll flow.
        resonance = [{"id": f.id, "why": f"echoes {words[0]} (offline)"} for f in FEATURED_MENU[:4]]
        return {"facets": facets, "concepts": concepts, "clusters": clusters, "featured_resonance": resonance}


def validate_cloud(obj: dict) -> list[str]:
    errs: list[str] = []
    if not isinstance(obj, dict):
        return ["cloud output is not an object"]
    facets = obj.get("facets")
    drivers: list[str] = []
    if not isinstance(facets, list) or not facets:
        errs.append("need a 'facets' list of at least 1 entry")
    else:
        for i, f in enumerate(facets):
            if not isinstance(f, dict) or not str(f.get("name", "")).strip():
                errs.append(f"facet[{i}] needs a name"); continue
            if str(f.get("role", "")).strip().lower() == "driver":
                drivers.append(str(f.get("name")).strip().lower())
        if not drivers:
            errs.append("at least one facet must have role 'driver' (the most action-rich idea)")
    concepts = obj.get("concepts")
    if not isinstance(concepts, list) or len(concepts) < 8:
        errs.append("need a 'concepts' list of at least 8 entries")
    clusters = obj.get("clusters")
    if not isinstance(clusters, list) or len(clusters) < 2:
        errs.append("need a 'clusters' list of at least 2 threads")
    else:
        covered = set()
        for i, cl in enumerate(clusters):
            if not isinstance(cl, dict) or not str(cl.get("name", "")).strip():
                errs.append(f"cluster[{i}] needs a name"); continue
            covered.add(str(cl.get("facet", "")).strip().lower())
        # driver coverage: every driver facet must be the origin of at least one cluster (tolerant substring match)
        for d in drivers:
            if not any(d and (d in c or c in d) for c in covered if c):
                errs.append(f"driver facet '{d}' has no cluster — its actions can't be dropped; add one")
    # featured_resonance is an ENHANCEMENT, never a blocker: a missing/empty shortlist degrades to the wild
    # roll in the builder, so only a wrong TYPE is worth a repair round (unknown ids are filtered downstream).
    fr = obj.get("featured_resonance")
    if fr is not None and not isinstance(fr, list):
        errs.append("'featured_resonance' must be a list of {id, why} objects (or omitted)")
    return errs
