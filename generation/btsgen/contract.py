"""Build the generation prompt = the contract.

System prompt = VOCABULARY.md + card.schema.json + a few exemplar cards (few-shot).
User message = the brief (type / rarity / theme / target cost).

The model composes effects from the enumerated vocabulary only; it never writes code.
We can't use Anthropic structured-outputs to *force* the shape (the schema is recursive),
so the contract is carried in the prompt and enforced afterward by CardValidator.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from . import paths

# --- DESIGN_HEURISTICS.md loader -----------------------------------------------------------------
# The forge's design rules live as editable prose in mod/contract/DESIGN_HEURISTICS.md (one source the
# designer can tweak without touching code). Each rule is a block introduced by a marker comment:
#   <!-- heuristic: KEY -->        a global rule, read by rarity_ladder()/reprint_section()/etc.
#   <!-- archetype-note: ID -->    a per-archetype note, read by the catalog (frontend) by archetype id.
# A block runs from its marker to the next marker (or EOF). Read live each call (cheap; like the live
# pool/status reads), so edits land without a restart. If the file is absent, sections resolve to "".
_MARKER_RE = re.compile(r"<!--\s*(heuristic|archetype-note):\s*([A-Za-z0-9_\-]+)\s*-->")


def _parse_heuristics() -> dict[tuple[str, str], str]:
    try:
        text = paths.DESIGN_HEURISTICS.read_text(encoding="utf-8")
    except OSError:
        return {}
    out: dict[tuple[str, str], str] = {}
    marks = list(_MARKER_RE.finditer(text))
    for i, m in enumerate(marks):
        start = m.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out[(m.group(1), m.group(2))] = text[start:end].strip()
    return out


def _heuristic(key: str) -> str:
    """The prose block for `<!-- heuristic: key -->` in DESIGN_HEURISTICS.md ("" if missing)."""
    return _parse_heuristics().get(("heuristic", key), "")


def archetype_balance_note(archetype_id: str) -> str:
    """The per-archetype note for `<!-- archetype-note: id -->` in DESIGN_HEURISTICS.md ("" if none).
    Read by the front-end catalog so an archetype's balance guidance lives in the same single source."""
    return _parse_heuristics().get(("archetype-note", archetype_id), "")

# Exemplars chosen to span the vocabulary: plain damage/block, apply_status (+/- with `to`),
# from_state, multi, add_card (self-ref), set_flag, lose_hp/gain_energy, a power.
_FEW_SHOT_IDS = [
    "strike", "defend", "bash", "body_slam", "twin_strike",
    "disarm", "battle_trance", "anger", "bloodletting", "inflame",
]


@dataclass
class Brief:
    card_type: str = "attack"        # attack | skill | power
    rarity: str = "common"           # basic | common | uncommon | rare
    target_cost: int | None = None   # energy; None = let the model choose (0..3 typical)
    theme: str = ""                  # free-text flavor/mechanical nudge, e.g. "block-and-counter"
    context: str = ""                # extra design context (e.g. the class/set a card belongs to);
                                     # appended to the user message by the character set-generator

    def describe(self) -> str:
        parts = [f"type: {self.card_type}", f"rarity: {self.rarity}"]
        if self.target_cost is not None:
            parts.append(f"target cost: {self.target_cost} energy")
        if self.theme:
            parts.append(f"theme: {self.theme}")
        return ", ".join(parts)


def declared_status_ids() -> list[str]:
    """The status ids actually declared in data/statuses/ — the live closed set, so prompts
    never go stale as the vocabulary grows (e.g. armor/burrowed/strength_temp)."""
    out = []
    for f in sorted(paths.STATUSES_DIR.glob("*.json")):
        try:
            d = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(d, dict) and isinstance(d.get("id"), str):
            out.append(d["id"])
    return out


def _exemplars() -> str:
    blocks = []
    for cid in _FEW_SHOT_IDS:
        f = paths.CARDS_DIR / f"{cid}.json"
        if f.exists():
            # reflow to compact-but-readable JSON for the prompt
            blocks.append(json.dumps(json.loads(f.read_text()), indent=2))
    return "\n\n".join(blocks)


def rarity_ladder() -> str:
    """The rarity design contract + (when distilled) real StS2 examples per tier. Born from
    review feedback: generated 'rares' kept rolling out as flat stat lines indistinguishable
    from commons. Shared by the card and blueprint prompts. The rule prose is editable in
    DESIGN_HEURISTICS.md (`heuristic: rarity_ladder`); the StS2 examples tail is appended live."""
    out = _heuristic("rarity_ladder")
    if paths.STS2_EXAMPLES.exists():
        # drop the digest's title + provenance paragraphs; embed just the ## sections
        out += ("\n\nReal Slay-the-Spire examples of the ladder (calibrate POWER and COMPLEXITY "
                "to these; they are NOT vocabulary — compose only from the closed vocabulary "
                "above):\n" + paths.STS2_EXAMPLES.read_text().split("\n\n", 2)[-1])
    return out


def _existing_pool_lines() -> list[str]:
    """One compact line per distinct design in the live authored pool, ids merged when
    several classes share the same line (each class's literal basics, body_slam twins)."""
    groups: dict[str, list[str]] = {}
    for f in sorted(paths.CARDS_DIR.glob("*.json")):
        try:
            c = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(c, dict) or not isinstance(c.get("id"), str):
            continue
        line = "(%s, %s, %sE, %s): %s" % (
            c.get("type"), c.get("target"), c.get("cost"), c.get("rarity"),
            json.dumps(c.get("effects"), separators=(",", ":")))
        groups.setdefault(line, []).append(c["id"])
    return ["- %s %s" % (" / ".join(sorted(ids)), line)
            for line, ids in sorted(groups.items(), key=lambda kv: sorted(kv[1])[0])]


def reprint_section() -> str:
    """The anti-reprint contract + the live pool catalog. Born from review: generated sets
    kept shipping existing cards under new names (three classes in a row each 'invented'
    Inflame, a +2 Strength power). Shared by the card and blueprint prompts; the validator
    enforces the same rule (CardValidator.reprint_findings), so the threat here is real.
    The rule prose is editable in DESIGN_HEURISTICS.md (`heuristic: reprint_section`); the live
    pool catalog is read fresh here (like declared_status_ids) so promotions keep it current."""
    return _heuristic("reprint_section") + "\n" + "\n".join(_existing_pool_lines())


def relic_forms() -> str:
    """The relic-simplicity contract: a forged starter relic is ONE keystone idea, composed by picking a
    single 'form' (a single-hook template tied to what an archetype wants). Shared by both relic prompts
    (the keystone-intent stage and the constrained _RelicContract). Born from forged relics coming out far
    busier than a starter relic should be. Editable in DESIGN_HEURISTICS.md (`heuristic: relic_forms`)."""
    return _heuristic("relic_forms")


def loop_discipline() -> str:
    """The combo-engine pricing rule, shared by the card and blueprint prompts. Player rule
    (from the Hand Out a Rose incident -- a 0-cost signature that re-added itself to hand):
    infinite combos are WELCOME, but by default they must take 3+ cards to assemble; tighter
    loops have to charge a real price. Enforced softly: the validator only flags (warnings,
    never rejects), so emergent hilarity can still ship past a human reviewer.
    Editable in DESIGN_HEURISTICS.md (`heuristic: loop_discipline`)."""
    return _heuristic("loop_discipline")


def hp_economy() -> str:
    """The HP<->Strength pricing rule, shared by the card, blueprint, and relic prompts. Born from a
    forged keystone relic that lost 1 HP for +1 Strength each turn and then HEALED 2 -- a net-positive
    'sacrifice' with no tension at all. Three halves: Strength is expensive (a permanent stat that
    compounds every attack), a self-cost only bites if it stays net-negative, and -- as a creative
    default -- healing and an HP cost should not live on the SAME card/relic at all. Advisory (steers
    the prompt); there is no hard validator gate, so unusual-but-honest bargains can still ship.
    Editable in DESIGN_HEURISTICS.md (`heuristic: hp_economy`)."""
    return _heuristic("hp_economy")


# Canonical categories live in feedback_store (with the loader/retriever); re-exported here because
# web/forge.py and older callers import them from the contract.
from .feedback_store import _FEEDBACK_LABELS  # noqa: F401 (re-export)


def feedback_section(max_entries: int = 20) -> str:
    """Player card ratings (the in-game CardInspect buttons and the website's feedback buttons)
    folded back into the prompt: 'great' cards as examples to emulate, everything else as
    anti-examples with the player's complaint attached. When the player typed an explanation into
    the optional "why" box, their own words ride the line (a `note` field on the JSONL entry) —
    far more instructive than the category alone. Reads the curated log plus any live sources
    (feedback_store), most recent `max_entries`. Empty string when no feedback has been filed yet."""
    from . import feedback_store
    entries = feedback_store.load_entries()
    if not entries:
        return ""
    return feedback_store.render_section(
        entries[-max_entries:],
        header="PLAYER FEEDBACK ON PAST CARDS (in-game ratings; let it steer your design)")


def system_prompt() -> str:
    paths.assert_project_present()
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    schema = paths.CARD_SCHEMA.read_text(encoding="utf-8")
    return f"""You are a card designer for "BLANK the spire", a Slay-the-Spire-like deckbuilder for a \
single Ironclad-like Strength/Block character. You compose cards as JSON, drawn ONLY from a \
closed effect vocabulary. You never invent ops, statuses, states, or targets — if a mechanic \
isn't expressible with the vocabulary below, you pick a different design that is.

# THE VOCABULARY (authoring reference)
{vocab}

# THE JSON SCHEMA (the hard contract — your output is validated against this)
```json
{schema}
```

# EXEMPLAR CARDS (authored; match this style and balance)
```json
{_exemplars()}
```

{rarity_ladder()}

{reprint_section()}

{loop_discipline()}

{hp_economy()}
{feedback_section()}
# YOUR TASK
Design ONE new card matching the brief. Requirements:
- Output a SINGLE JSON object, schema-valid, and NOTHING else — no prose, no markdown fences, no comments.
- Use a fresh, unique snake_case `id` and a short human `name`. Do NOT reuse an exemplar id.
- Compose `effects` only from the vocabulary ops; reference only declared statuses \
({", ".join(declared_status_ids())}) and existing card ids.
- If the brief carries a class context, design for THAT class instead of the Ironclad and set the \
`character` / `archetype` fields it specifies.
- Set `"source": "llm"`.
- Include an `upgrade` (the Rest-site/reward improvement) when it fits the design.
- Aim for the power level implied by the cost/rarity balance guidance — neither overtuned nor weak.
- No functional reprints: check THE EXISTING CARD POOL above before settling on a design. At \
uncommon/rare a reprint (same skeleton, same-or-nudged numbers) is rejected outright. ONE exception: \
when the brief itself asks for a 'Reprint of <Name> (base game)', recreate THAT base-game card \
faithfully in the vocabulary — keep its name and stay close to its original numbers. The no-reprint \
rule guards against copying the pool above, not against a deliberate base-game homage.
- Creativity discipline: vulnerable/weak are the game's most generic filler — reach for them LAST, \
never as a card's whole identity, and only when the brief itself asks for debuffs. If the brief \
names an archetype engine, the card's PRIMARY effect must serve that engine; prefer compositional \
designs (multi, from_state, conditional, state-scaled amounts, X-cost, add_card recursion, lose_hp \
costs) over another flat "damage + debuff" stat line.
- BRIDGE cards: when the brief marks this card as a BRIDGE (fusion) card, it MUST visibly combine BOTH \
named engines in the one design — one effect serving each, or one engine's mechanic gating/scaling the \
other engine's payoff. A "bridge" that serves only one engine is a failed design; do not turn one in.
- Give it character: a clear mechanical identity, plus optional one-line `flavor`."""


def user_brief(brief: Brief) -> str:
    msg = f"Design a card with — {brief.describe()}.\n"
    if brief.context:
        msg += f"\n{brief.context}\n"
    # Targeted feedback fold-in: past player ratings on designs SIMILAR to this brief (the system
    # prompt's feedback section is recency-global; this one is per-card). Empty string when nothing
    # relevant has been rated, so most briefs are untouched.
    from . import feedback_store
    fb = feedback_store.similar_feedback_section(
        f"{brief.card_type} {brief.rarity} {brief.theme} {brief.context}")
    if fb:
        msg += fb
    msg += "Return only the JSON object."
    return msg


def repair_message(card_text: str, errors: list[str]) -> str:
    bullet = "\n".join(f"- {e}" for e in errors)
    return (
        "That card failed validation:\n"
        f"{bullet}\n\n"
        "Here is what you returned:\n"
        f"{card_text}\n\n"
        "Return a corrected SINGLE JSON object that fixes every error above and still "
        "matches the brief. Output only the JSON object."
    )
