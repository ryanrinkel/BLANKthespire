"""Stage 5: the KEYSTONE relic INTENT.

Designs the relic that crystallizes the chosen build (relic-last, like Cracked Core defines the Defect's
orbs). This stage emits DESIGN INTENT only — name + fantasy + a one-line effect sketch — which is threaded
into the blueprint `bp` so the EXISTING constrained relic generator (_RelicContract, RELIC_VOCABULARY) turns
it into an actual validated, playable forged relic. So creativity names the keystone; the real relic stage
guarantees it's buildable.

Output: { "name", "fantasy", "effect_sketch" } — one JSON object.
"""
from __future__ import annotations

_SYSTEM = """You are a relic CONCEPT designer for "BLANK the spire", a Slay-the-Spire-like deckbuilder. Given a \
freshly-composed class (its name, fantasy, and two archetypes in tension), name the KEYSTONE starter relic that \
crystallizes the build — the relic the class is named around (like Cracked Core defines the Defect). Design ONE \
clean keystone idea that rewards the class's CORE LOOP, led by its DOMINANT archetype — the other archetype is \
flavor in the name, NOT a second mechanic. This is DESIGN INTENT, not final numbers: another stage turns it into \
the real always-on relic. Keep it modest, always-on, and SIMPLE — if you can't say it in one sentence, simplify.

Pick exactly ONE of the relic forms below and sketch it (the effect_sketch should describe a single mechanic):

Output EXACTLY ONE JSON object, nothing else:
{ "name": "<= 28 chars", "fantasy": "one line — what the relic IS", "effect_sketch": "one line — ONE thing it does each combat, modest and always-on" }
Return only the JSON object."""


def _system_with_forms() -> str:
    """_SYSTEM + the relic FORMS catalog (single source: DESIGN_HEURISTICS.md), so the intent is sketched as
    one of the simple forms rather than a busy multi-mechanic design."""
    from ..contract import relic_forms
    forms = relic_forms()
    return _SYSTEM + ("\n\n" + forms if forms else "")


class _RelicIntentContract:
    def system_prompt(self) -> str:
        return _system_with_forms()

    def user_brief(self, candidate) -> str:
        archs = " | ".join(f"{i}: {d}" for i, d in zip(candidate.archetype_ids, candidate.archetype_descs))
        return (f'Design the keystone relic INTENT for this class:\n'
                f'Name: "{candidate.name}"\nFantasy: {candidate.fantasy}\n'
                f'Core loop: {candidate.core_loop}\nArchetypes (in tension): {archs}\n\n'
                f'Return only the JSON object (name, fantasy, effect_sketch).')

    def repair_message(self, text: str, errors: list[str]) -> str:
        bullet = "\n".join(f"- {e}" for e in errors)
        return ("That relic intent failed validation:\n" + bullet +
                "\n\nHere is what you returned:\n" + text +
                "\n\nReturn a corrected SINGLE JSON object with name, fantasy, effect_sketch. Only the JSON object.")

    def fake_output(self, candidate) -> dict:
        return {"name": (f"{candidate.name} Sigil")[:28] or "Keystone Sigil",
                "fantasy": f"the keystone of {candidate.name or 'the class'}",
                "effect_sketch": "at the start of each combat, gain a small modest boon that rewards the core loop"}


def validate_relic_intent(obj: dict) -> list[str]:
    errs: list[str] = []
    if not isinstance(obj, dict):
        return ["relic intent is not an object"]
    if not str(obj.get("name", "")).strip():
        errs.append("relic intent needs a non-empty name")
    if not str(obj.get("effect_sketch", "")).strip() and not str(obj.get("fantasy", "")).strip():
        errs.append("relic intent needs an effect_sketch or fantasy")
    return errs
