"""Explicit mechanical REQUESTS in the player's concept -> hard constraints on the staged front-end.

The front-end is built to be creative FROM a theme: the cloud stage is deliberately mechanics-free, the
catalog window (harness v2) shows ~15 of 34 archetypes matched on cluster words, and the picker scores
cluster fidelity + distinctiveness. That is right for "a haunted lighthouse keeper" and wrong for "an ORB
class that loads shells as orbs" — the player NAMED the engine, and the 2026-09-27 Sherman forge (web class
#67) came back as block_bulwark + untouchable_ward + forge_ramp with zero orb slots.

This module reads the concept for the mechanics a player can ask for by name — a pool KIND (an orb / summon
/ custom-status class) or a catalog archetype by its plain-language handle — and turns each into a
Requirement the rest of the front-end honors:
  - the satisfying archetypes are PINNED into the catalog window (the map stage can't pick what it can't see);
  - the map / compose prompts carry a HARD RULE naming them;
  - the compose validator asks for at least one candidate that carries each (a SOFT error: one repair
    round, never a failed forge);
  - the picker restricts itself to the honoring candidates — "as best we can": when no candidate honors
    everything, the ones honoring the most;
  - the requested archetypes count as fidelity DRIVERS (an explicit ask outranks what the clusters suggest).

Conservative on purpose: only words that unambiguously name a mechanic count. "block", "draw", "strike",
"forge" are everyday words in a theme sentence (and "forge" is what the site does) — they are NOT requests
unless qualified ("a block class", "card draw"). A negated mention ("not an orb class", "no minions") is
not a request either.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# A triad has three slots; honoring more than two explicit asks would leave the harness no room to compose.
# (The interactive archetype pick has the same <=2 cap.)
MAX_REQUIREMENTS = 2

# Pool KINDS a player can ask for. The satisfying archetypes are every catalog entry of that class_kind, so a
# new orb archetype in archetypes.json joins the set with no edit here.
_KIND_PATTERNS: dict[str, str] = {
    "orb": r"\borbs?\b|\borb[- ]?slots?\b|\bevoke(?:s|d)?\b",
    "summon": r"\bsummon(?:s|er|ers|ing|ed)?\b|\bminions?\b|\bnecromancer\b|\bbeast ?master\b",
    "status": r"\b(?:custom|signature|unique|own) (?:status(?:es)?|condition|debuff|buff)\b|\bstatus class\b",
}
_KIND_LABELS: dict[str, str] = {
    "orb": "an ORB class (orb slots; channel / evoke)",
    "summon": "a SUMMON class (a minion you raise and command)",
    "status": "a custom-STATUS class (a signature buff/debuff of its own)",
}

# Catalog archetypes a player can ask for by a plain-language handle. Keep every pattern SPECIFIC: a word
# that could sit in an ordinary theme sentence without meaning the mechanic must be qualified.
_ARCHETYPE_PATTERNS: dict[str, str] = {
    "poison_attrition": r"\bpoison(?:s|ous|ed|ing)?\b|\bvenom(?:ous)?\b|\btoxic\b",
    "madness_discard": r"\bdiscard(?:s|ing|ed)?\b",
    "exhaust_pyre": r"\bexhaust(?:s|ing|ed)?\b",
    "retain_hold": r"\bretain(?:s|ing|ed)?\b",
    "reaper_lifesteal": r"\blife ?steal(?:ing)?\b|\bdrain(?:s|ing)? (?:life|hp|health)\b",
    "counter_riposte": r"\bthorns\b|\bripostes?\b|\bcounter[- ]?attack(?:s|ing)?\b|\bretaliat(?:e|es|ion|ing)\b",
    "rampage_grow": r"\brampage\b",
    "strength_berserk": r"\bstrength[- ](?:class|build|deck|scaling|stacking)\b|\bstack(?:s|ing)? strength\b|\bberserk(?:er)?\b",
    "block_bulwark": r"\bblock[- ](?:class|build|deck|engine)\b|\bturtle\b|\bbulwark\b",
    "slot_machine": r"\bslot[- ]machine\b|\broulette\b|\bjackpot\b|\bgambl(?:e|er|ers|ing)\b",
    "token_conjurer": r"\btoken[- ](?:class|build|deck|cards?|generat\w+|conjur\w+)\b|\bconjur(?:e|er|es|ing)\b",
    "countdown_ripen": r"\bcountdowns?\b|\bripen(?:s|ing)?\b|\bdelayed (?:payoffs?|fuses?|effects?)\b|\btime ?bombs?\b",
    "balance_gauge": r"\bbalance (?:gauge|meter|bar)\b|\blight (?:and|/|&) dark\b|\byin (?:and|/|&) yang\b",
    "self_sacrifice": r"\b(?:spend|pay|sacrific\w+) (?:your |my |its )?(?:hp|health|life|blood)\b|\bself[- ]sacrifice\b|\bblood (?:magic|price)\b",
    "debuff_expose": r"\bdebuff(?:s|ing|er)?\b|\bvulnerable\b",
    "power_ramp": r"\bpowers? (?:class|build|deck|engine)\b|\bsnowball(?:s|ing)?\b",
    "tempo_draw": r"\bcard draw\b|\bdraw (?:class|build|deck|engine)\b",
    "big_energy": r"\bbig energy\b|\benergy (?:class|build|deck|engine|generation)\b|\boverload\b",
    "horde_breaker": r"\baoe\b|\barea[- ]of[- ]effect\b|\bmulti[- ]?target\b|\bhit(?:s|ting)? (?:all|every) enem(?:y|ies)\b|\bcleave\b",
    "strike_tempo": r"\bsingle[- ]target\b|\bmulti[- ]?hit\b|\bflurr(?:y|ies)\b",
    "ambush_alpha": r"\bambush(?:es|er)?\b|\bopening burst\b|\balpha strike\b",
    "fleeting_flux": r"\bethereal\b",
    "untouchable_ward": r"\bintangible\b|\bblur\b|\bdodg(?:e|es|ing)\b|\bphase[- ]shift\w*\b",
    "burst_window": r"\bburst[- ]window\b|\btemp(?:orary)? (?:strength|stats?)\b",
    "iron_regrowth": r"\bregen(?:erat\w+)?\b|\bhealing (?:class|build|deck)\b|\bhealer\b|\bself[- ]heal\w*\b",
    "strike_synergy": r"\bstrikes?[- ]matter\b|\bstrike synergy\b",
    "metamorph": r"\btransform(?:s|ing|ation)?\b|\bmetamorph\w*\b|\bevolv(?:e|es|ing|ution)\b",
    "threshold_duelist": r"\bexecutes?\b|\bthresholds?\b",
    "battle_smith": r"\bupgrad(?:e|es|ing) (?:cards?|in[- ]combat|mid[- ]fight)\b|\barmaments?\b",
    "ascetic_purge": r"\bdeck[- ]thin\w*\b|\bthin(?:s|ning)? (?:the|your|my) deck\b|\bpurge\b|\bremov\w+ cards\b",
    "forge_ramp": r"\bforge (?:counter|class|build|engine)\b",
}

# A mention right after one of these is a negation ("not an orb class", "without minions"), not a request.
_NEGATION_RE = re.compile(r"\b(?:no|not|never|without|avoid(?:s|ing)?|isn't|is not|aren't|don't|doesn't)\b"
                          r"(?:\s+\w+){0,3}\s*$")


@dataclass
class Requirement:
    """One explicit ask: satisfied by a candidate that carries ANY of `archetype_ids`."""
    label: str                              # player-facing: "an ORB class (orb slots; channel / evoke)"
    archetype_ids: list[str]                # the catalog ids that satisfy it
    kind: str = ""                          # the pool kind ("orb"/"summon"/"status") or "" for an archetype ask
    evidence: str = ""                      # the concept words that triggered it
    position: int = 0                       # where in the concept it was found (ordering)

    def satisfied_by(self, archetype_ids) -> bool:
        have = {str(a) for a in (archetype_ids or [])}
        return any(a in have for a in self.archetype_ids)

    def as_dict(self) -> dict:
        return {"label": self.label, "archetype_ids": list(self.archetype_ids), "kind": self.kind,
                "evidence": self.evidence}


def _first_match(pattern: str, text: str) -> re.Match | None:
    """The first NON-negated match of `pattern` in `text` (case-insensitive)."""
    for m in re.finditer(pattern, text, flags=re.IGNORECASE):
        if not _NEGATION_RE.search(text[max(0, m.start() - 40):m.start()]):
            return m
    return None


def detect_requests(concept: str, catalog, *, cap: int = MAX_REQUIREMENTS) -> list[Requirement]:
    """The explicit asks in `concept`, kinds first (an "orb class" is the whole identity), then archetypes,
    each in order of appearance, capped at `cap`. An archetype ask whose id already satisfies an earlier kind
    ask (a "gambler" in an "orb class") is folded into it rather than spending a second slot."""
    text = str(concept or "")
    if not text.strip():
        return []
    by_id = getattr(catalog, "by_id", {}) or {}
    found: list[Requirement] = []
    for kind, pat in _KIND_PATTERNS.items():
        m = _first_match(pat, text)
        if m is None:
            continue
        ids = [e.id for e in getattr(catalog, "entries", []) if getattr(e, "class_kind", "") == kind]
        if not ids:
            continue
        found.append(Requirement(label=_KIND_LABELS[kind], archetype_ids=ids, kind=kind,
                                 evidence=m.group(0), position=m.start()))
    found.sort(key=lambda r: r.position)
    covered = {a for r in found for a in r.archetype_ids}
    arch: list[Requirement] = []
    for aid, pat in _ARCHETYPE_PATTERNS.items():
        if aid not in by_id or aid in covered:
            continue
        m = _first_match(pat, text)
        if m is None:
            continue
        e = by_id[aid]
        arch.append(Requirement(label=f"the {e.name} engine ({aid})", archetype_ids=[aid], kind="",
                                evidence=m.group(0), position=m.start()))
    arch.sort(key=lambda r: r.position)
    return (found + arch)[:max(0, int(cap))]


def requested_ids(reqs) -> list[str]:
    """Every archetype id that satisfies some requirement, in requirement order, deduplicated."""
    out: list[str] = []
    for r in (reqs or []):
        for a in r.archetype_ids:
            if a not in out:
                out.append(a)
    return out


def requested_tokens(reqs, catalog) -> set[str]:
    """The vocabulary tokens the player's explicit asks name: every `vocabulary.ops` token of every archetype
    that satisfies a requirement. Phase BH-3: these rows join the blueprint's VOCABULARY DETAIL even when the
    chosen candidate did not carry the requested archetype (the ask is "as best we can")."""
    by_id = getattr(catalog, "by_id", {}) or {}
    out: set[str] = set()
    for aid in requested_ids(reqs):
        e = by_id.get(aid)
        if e is not None:
            out |= {str(o) for o in (getattr(e, "ops", None) or ())}
    return out


def request_line(reqs) -> str:
    """The HARD RULE paragraph for the map / compose prompts ("" when there is nothing to ask)."""
    if not reqs:
        return ""
    parts = [f'{r.label} — the theme says "{r.evidence}" — so EVERY candidate must include at least one of: '
             + ", ".join(r.archetype_ids) for r in reqs]
    return ("HARD RULE (the player's EXPLICIT ask, it outranks metaphor resonance, the COLD rule and the "
            "recency line): the player asked for " + "; AND ".join(parts) + ".")


def map_line(reqs) -> str:
    """The map-only variant (interactive mode): the mapping must surface the requested engines."""
    if not reqs:
        return ""
    parts = [f'{r.label} ("{r.evidence}") -> map at least one cluster to one of: ' + ", ".join(r.archetype_ids)
             for r in reqs]
    return "The player EXPLICITLY asked for " + "; AND ".join(parts) + " (their ask outranks metaphor resonance)."


def honored_count(reqs, archetype_ids) -> int:
    """How many of `reqs` a candidate with `archetype_ids` satisfies."""
    return sum(1 for r in (reqs or []) if r.satisfied_by(archetype_ids))


def request_validator(reqs):
    """A SOFT validator for a compose output: an error per requirement that NO candidate honors. Soft = the
    builder sends it through one repair round but accepts the output if the model still won't comply, so an
    explicit ask can never turn into a failed (and refunded) forge."""
    reqs = list(reqs or [])

    def _validate(obj) -> list[str]:
        if not reqs or not isinstance(obj, dict):
            return []
        cands = [c for c in (obj.get("candidates") or []) if isinstance(c, dict)]
        errs: list[str] = []
        for r in reqs:
            if not any(r.satisfied_by(c.get("archetype_ids") or c.get("archetypes") or []) for c in cands):
                errs.append(f"the player EXPLICITLY asked for {r.label} but no candidate includes any of "
                            f"{', '.join(r.archetype_ids)} — every candidate should")
        return errs

    return _validate
