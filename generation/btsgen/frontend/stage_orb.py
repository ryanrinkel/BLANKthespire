"""Stage 5b: the ORB POOL INTENT (orb classes only).

Decides, FROM THE FANTASY, what an orb class actually channels — before the blueprint stage writes the pool.
Mirrors the keystone relic intent (stage_relic): this emits DESIGN INTENT only (a modality + named orbs), which
is threaded into the blueprint `bp` as `orb_intent`; the blueprint prompt renders it as an order, and
_validate_blueprint rejects a pool that contradicts it (so a repair pass fixes it).

Why this stage exists (2026-09-21): a WW2 Sherman tank class invented a lovely "shell rack" orb engine and then
padded its pool with lightning + frost because the blueprint prompt's only worked example is MIXED and nothing
upstream had said "the shells ARE the orbs". The blueprint LLM writes 34 briefs at once; the modality decision
deserves its own small call where the fantasy is the whole context.

Output: { "mode": "custom_only" | "mixed" | "base_only",
          "orbs": [ {"name", "fantasy"}, ... ]   # the CUSTOM orbs (<= cap; [] for base_only)
          "base_orbs": ["lightning" | "frost" | "dark", ...],  # [] for custom_only
          "why": "one line" }
"""
from __future__ import annotations

BASE_ORBS = ("lightning", "frost", "dark")
MODES = ("custom_only", "mixed", "base_only")

_SYSTEM = """You are an orb-pool CONCEPT designer for "BLANK the spire", a Slay-the-Spire-like deckbuilder. The game \
has a Defect-style ORB engine: a class channels orbs into slots; each orb ticks a small passive every turn and bursts \
when evoked. The three BASE orbs are the Defect's elements — lightning (shocks an enemy), frost (block), dark (a \
growing single-target burst). A class may instead invent its OWN orbs (custom orbs), each a named thing with its own \
passive/evoke, designed by a later stage.

Your one job: decide WHAT THIS CLASS CHANNELS, from its fantasy, so the orbs ARE the fantasy.
- "custom_only": the class channels its own things — ammunition, seeds, dice, potions, spirits, songs, gears, anything \
that is NOT literally lightning/frost/dark. This is the DEFAULT for almost every concept. Name 2-3 orbs (never more \
than the cap you are given) that read as the same family — a rack of shells, a set of dice, a clutch of seeds — each \
with a distinct role (e.g. one damage-over-time, one burst, one defensive/utility).
- "base_only": ONLY when the fantasy is literally the elemental/electrical/frost/shadow magic the base orbs already \
depict (a storm mage, a cryomancer, a Defect homage). Pick the 1-3 base orbs that fit.
- "mixed": RARE — only when the fantasy genuinely spans both (a storm-caller who also forges her own thunder-heads). \
A non-elemental fantasy must NEVER carry a base orb "to fill slots": three custom orbs is a full pool.

Names: <= 16 characters, distinct, in the class's own vocabulary (the fantasy's nouns, not "Fire Orb"). One-line \
fantasy per orb: what it IS and roughly what it does (passive tick vs evoke burst), no numbers.

Output EXACTLY ONE JSON object, nothing else:
{ "mode": "custom_only" | "mixed" | "base_only",
  "orbs": [ { "name": "<= 16 chars", "fantasy": "one line" }, ... ],
  "base_orbs": [ "lightning" | "frost" | "dark", ... ],
  "why": "one line — why this modality fits the fantasy" }
"orbs" is [] for base_only; "base_orbs" is [] for custom_only. Return only the JSON object."""


def custom_cap_for(candidate) -> int:
    """How many custom orbs this class may declare: the full cap when orbs are its PRIMARY kind, the splash cap when
    orbs are the hybrid's second pool (class_forge enforces the same budgets on the blueprint)."""
    from ..class_forge import _MAX_CUSTOM_ORBS, _SPLASH_ORB_CUSTOM_MAX  # lazy: class_forge imports this package
    kinds = list(getattr(candidate, "class_kinds", None) or [])
    if not kinds:
        k = getattr(candidate, "class_kind", "normal")
        kinds = [k] if k and k != "normal" else []
    return _MAX_CUSTOM_ORBS if (kinds and kinds[0] == "orb") else _SPLASH_ORB_CUSTOM_MAX


def is_orb_class(candidate) -> bool:
    kinds = list(getattr(candidate, "class_kinds", None) or [])
    return "orb" in kinds or getattr(candidate, "class_kind", "") == "orb"


class _OrbIntentContract:
    def __init__(self, concept: str = "", cap: int = 3) -> None:
        self.concept = concept or ""
        self.cap = max(1, int(cap))

    def system_prompt(self) -> str:
        return _SYSTEM

    def user_brief(self, candidate) -> str:
        archs = " | ".join(f"{i}: {d}" for i, d in zip(candidate.archetype_ids, candidate.archetype_descs))
        splash = "" if self.cap >= 3 else (
            f" Orbs are this class's SECOND (splash) pool, so the cap is {self.cap} custom orb — "
            f"for custom_only name exactly {self.cap}.")
        return (f'Decide the ORB POOL INTENT for this class (custom-orb cap: {self.cap}).{splash}\n'
                f'Player concept (verbatim): "{self.concept}"\n'
                f'Name: "{candidate.name}"\nFantasy: {candidate.fantasy}\n'
                f'Core loop: {candidate.core_loop}\nArchetypes: {archs}\n\n'
                f'Return only the JSON object (mode, orbs, base_orbs, why).')

    def repair_message(self, text: str, errors: list[str]) -> str:
        bullet = "\n".join(f"- {e}" for e in errors)
        return ("That orb intent failed validation:\n" + bullet +
                "\n\nHere is what you returned:\n" + text +
                "\n\nReturn a corrected SINGLE JSON object with mode, orbs, base_orbs, why. Only the JSON object.")

    def fake_output(self, candidate) -> dict:
        # Matches the offline fake blueprints exactly (class_forge._fake_blueprint's "Test Tempest" MIXED pool for a
        # primary orb class; _fake_splash's ["lightning"] for a splash orb pool), so the --fake path validates.
        if self.cap >= 3:
            return {"mode": "mixed",
                    "orbs": [{"name": "Ember", "fantasy": "a sear that ticks then bursts"},
                             {"name": "Plasma", "fantasy": "a spark of energy each turn"}],
                    "base_orbs": ["lightning"], "why": "offline fake: mirrors the Test Tempest pool"}
        return {"mode": "base_only", "orbs": [], "base_orbs": ["lightning"],
                "why": "offline fake: mirrors the splash-orb seed"}


def validate_orb_intent(obj: dict, cap: int = 3) -> list[str]:
    errs: list[str] = []
    if not isinstance(obj, dict):
        return ["orb intent is not an object"]
    mode = str(obj.get("mode", "")).strip().lower()
    if mode not in MODES:
        errs.append(f"orb intent mode must be one of {'/'.join(MODES)}")
    orbs = obj.get("orbs")
    if orbs is None:
        orbs = []
    if not isinstance(orbs, list):
        errs.append("orb intent 'orbs' must be a list")
        orbs = []
    names: list[str] = []
    for i, o in enumerate(orbs):
        nm = str(o.get("name", "")).strip() if isinstance(o, dict) else str(o or "").strip()
        if not nm:
            errs.append(f"orbs[{i}] needs a non-empty name")
        elif len(nm) > 16:
            errs.append(f"orbs[{i}] name '{nm}' is over 16 characters")
        elif nm.lower() in BASE_ORBS:
            errs.append(f"orbs[{i}] '{nm}' is a base orb — list it under base_orbs, not as a custom orb")
        if nm.lower() in names:
            errs.append(f"duplicate orb name '{nm}'")
        names.append(nm.lower())
    if len(orbs) > cap:
        errs.append(f"at most {cap} custom orb(s) for this class (got {len(orbs)})")
    base = obj.get("base_orbs")
    if base is None:
        base = []
    if not isinstance(base, list):
        errs.append("orb intent 'base_orbs' must be a list")
        base = []
    for b in base:
        if str(b).strip().lower() not in BASE_ORBS:
            errs.append(f"base_orbs entry '{b}' must be one of lightning/frost/dark")
    if mode == "custom_only":
        if not orbs:
            errs.append("custom_only needs at least one custom orb in 'orbs'")
        if base:
            errs.append("custom_only must have an empty base_orbs (no lightning/frost/dark)")
    elif mode == "base_only":
        if orbs:
            errs.append("base_only must have an empty 'orbs' list")
        if not base:
            errs.append("base_only needs at least one base orb in base_orbs")
    elif mode == "mixed":
        if not orbs or not base:
            errs.append("mixed needs at least one custom orb AND at least one base orb")
    return errs


def normalize_orb_intent(obj: dict) -> dict:
    """The validated intent, trimmed to the shape the blueprint prompt + validator read."""
    return {
        "mode": str(obj.get("mode", "")).strip().lower(),
        "orbs": [{"name": str(o.get("name", "")).strip(), "fantasy": str(o.get("fantasy", "")).strip()}
                 for o in (obj.get("orbs") or []) if isinstance(o, dict)],
        "base_orbs": [str(b).strip().lower() for b in (obj.get("base_orbs") or [])],
        "why": str(obj.get("why", "")).strip(),
    }
