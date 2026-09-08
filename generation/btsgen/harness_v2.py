"""harness_v2.py — the "Creative harness v2" anti-sameness toolkit (docs/plans/DEPLOYMENT_PLAN.md §2).

Everything here is gated behind ONE env flag, BTS_HARNESS_V2=1, read at CALL time via `enabled()` (never at
import), so production can A/B via the ledger and roll back by env var, and tests can toggle it with
monkeypatch. With the flag unset/0 every caller falls through to its historical (v1) code path unchanged.

What lives here (the shared, provider-agnostic helpers each fix needs):
- seeds: a stable per-concept hash + seeded shuffles (menus, catalog windows, exemplar draws all rotate on it)
- Fix A: the vocabulary-driven compositional clause (names only ops that EXIST in VOCABULARY.md), the
  curated exemplar pool (data/exemplar_pool.json) + a seeded picker, the class identity block, the
  "shapes already used" line
- Fix B: (menus live in coverage.py; the seeded shuffle is here)
- Fix C: metaphor stripping (catalog stock phrases stay in the cloud stage only)
- Fix D: the rotating homage-example pool (20 base-game cards), the name post-pass (recent-name + global
  top-50 rejection)
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from . import paths

FLAG = "BTS_HARNESS_V2"


def enabled() -> bool:
    """True iff BTS_HARNESS_V2 is set to a truthy value. Read at call time, never cached."""
    return os.environ.get(FLAG, "").strip().lower() in ("1", "true", "yes", "on")


# --- seeds -------------------------------------------------------------------------------------------

def seed_for(text: str) -> int:
    """A stable 64-bit seed for a concept sentence (stripped, lowercased) — the same concept always rotates
    the same way, two concepts practically never the same way."""
    return int.from_bytes(hashlib.sha256((text or "").strip().lower().encode("utf-8")).digest()[:8], "big")


def rng(seed: int, salt: str = "") -> random.Random:
    """A Random seeded by `seed` + a salt, so independent draws (menus, exemplars, window) don't correlate."""
    return random.Random(f"{seed}:{salt}")


def seeded_shuffle(items, seed: int, salt: str = "") -> list:
    out = list(items)
    rng(seed, salt).shuffle(out)
    return out


# --- Fix A: the compositional clause, generated from the live vocabulary -----------------------------

# Ops worth naming as "compositional" alternatives to a flat stat line, in preference order. Class-only
# ops (orbs / summons / custom statuses / blade) are deliberately absent — they're only legal on a class
# that declared the matching pool. The clause keeps ONLY the entries the live VOCABULARY.md actually has.
_PREFERRED_OPS = ["add_trigger", "transform_card", "graft_card", "scry", "balance_step", "purge", "purge_card",
                  "forge", "upgrade_card", "discard", "add_card", "corruption", "retain", "exhaust",
                  "ethereal", "innate", "lose_hp"]
_PREFERRED_SCALES = ["cards_in_hand", "cards_retained", "unspent_energy_last_turn", "forged",
                     "damage_dealt_unblocked", "target_debuff_count", "tag_cards_owned"]
_PREFERRED_CONDITIONS = ["hp_below_half", "no_block", "has_block", "turn_at_least", "enemy_count_ge",
                         "hand_size_ge", "retained_last_turn", "target_has_status", "draw_pile_empty",
                         "hp_lost_ge", "forged_ge"]
_PREFERRED_TRIGGERS = ["on_exhaust", "on_card_played", "on_hp_lost", "on_block_gained", "on_card_drawn",
                       "on_damage_dealt", "attacked", "on_discard", "ripen"]
_CLASS_ONLY_TOKENS = {"channel_orb", "evoke", "gain_orb_slot", "focus", "orbs_match", "orb_count_ge", "summon",
                      "summon_attack", "buff_summon", "heal_summon", "shield_summon", "apply_status_custom",
                      "blade_empower", "summon_blade", "on_blade_played"}

_OP_ROW_RE = re.compile(r"^\|\s*`([a-z][a-z0-9_]*)`\s*\|", re.MULTILINE)
_TOKEN_RE = re.compile(r"`\"?([a-z][a-z0-9_]*)\"?`")


def _section(text: str, heading: str) -> str:
    """The body of the `## <heading>` section (up to the next `## `), '' if absent."""
    m = re.search(r"^##\s+" + re.escape(heading) + r".*?$", text, re.MULTILINE)
    if not m:
        return ""
    rest = text[m.end():]
    nxt = re.search(r"^##\s+", rest, re.MULTILINE)
    return rest[:nxt.start()] if nxt else rest


def _vocab_text() -> str:
    try:
        return paths.VOCABULARY.read_text(encoding="utf-8")
    except OSError:
        return ""


def vocabulary_ops(text: str | None = None) -> list[str]:
    """Every op in the `## Effect ops` table of VOCABULARY.md, in table order."""
    return _OP_ROW_RE.findall(_section(text if text is not None else _vocab_text(), "Effect ops"))


def vocabulary_conditions(text: str | None = None) -> list[str]:
    return _OP_ROW_RE.findall(_section(text if text is not None else _vocab_text(), "Conditions"))


def vocabulary_scales(text: str | None = None) -> list[str]:
    toks = set(_TOKEN_RE.findall(_section(text if text is not None else _vocab_text(), "Structural mechanics")))
    return [s for s in _PREFERRED_SCALES if s in toks]


def vocabulary_triggers(text: str | None = None) -> list[str]:
    toks = set(_TOKEN_RE.findall(_section(text if text is not None else _vocab_text(), "Triggers")))
    return [t for t in _PREFERRED_TRIGGERS if t in toks]


def compositional_clause(text: str | None = None) -> str:
    """The card prompt's 'prefer compositional designs' bullet, built from the live vocabulary so it only ever
    names ops / conditions / scales / triggers that exist (the v1 clause named prototype-only ops the
    validator rejects — Cause 2)."""
    vt = text if text is not None else _vocab_text()
    ops = [o for o in _PREFERRED_OPS if o in set(vocabulary_ops(vt))]
    conds = [c for c in _PREFERRED_CONDITIONS if c in set(vocabulary_conditions(vt))]
    scales = vocabulary_scales(vt)
    trigs = vocabulary_triggers(vt)
    parts = []
    if trigs and "add_trigger" in ops:
        parts.append("an ongoing engine (`add_trigger` with a REACTIVE trigger: " + "/".join(trigs) + ")")
    if conds:
        parts.append("a `when` gate (" + "/".join(conds) + ")")
    if scales:
        parts.append("a state-scaled amount (`scale`: " + "/".join(scales) + ")")
    parts.append('an X-cost card (`"cost":"X"` + `scale:"x"`)')
    shape_ops = [o for o in ops if o not in ("add_trigger", "lose_hp")]
    if shape_ops:
        parts.append("a shape-changing op (" + ", ".join(f"`{o}`" for o in shape_ops) + ")")
    if "lose_hp" in ops:
        parts.append("a real `lose_hp` cost paying for a bigger effect")
    return ("prefer COMPOSITIONAL designs over another flat \"damage + debuff\" stat line: "
            + "; ".join(parts) + ". Every token named here exists in the vocabulary above; nothing else does.")


# --- Fix A: the curated exemplar pool -----------------------------------------------------------------

_EXEMPLAR_POOL = Path(__file__).resolve().parent / "data" / "exemplar_pool.json"


@lru_cache(maxsize=1)
def load_exemplar_pool() -> tuple:
    """The hand-written, schema-valid forged exemplars: a tuple of {archetypes, needs?, card} entries."""
    try:
        raw = json.loads(_EXEMPLAR_POOL.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    out = []
    for e in raw.get("exemplars") or []:
        if isinstance(e, dict) and isinstance(e.get("card"), dict):
            out.append({"archetypes": [str(a) for a in (e.get("archetypes") or [])],
                        "needs": str(e.get("needs") or ""), "card": e["card"]})
    return tuple(out)


def _pool_kind(bp_kind: str, archetype_ids) -> set[str]:
    """Which `needs` tags this class satisfies: its class_kind (orb/status/summon) + 'forge' on a forge class."""
    ok = {""}
    if bp_kind in ("orb", "status", "summon"):
        ok.add(bp_kind)
    if any("forge" in str(a) for a in (archetype_ids or [])):
        ok.add("forge")
    return ok


def pick_exemplars(archetype_ids, rarity: str, seed: int, *, class_kind: str = "normal", salt: str = "",
                   avoid_triples=None, n: int = 3) -> list[dict]:
    """Pick `n` exemplar cards for a card brief: class-appropriate (archetype match first, then rarity match),
    seeded, and — when `avoid_triples` (a set of frozenset(ids)) is given — never a set already dealt in this
    class. Returns bare card dicts (the pool wrapper stripped)."""
    pool = load_exemplar_pool()
    if not pool:
        return []
    ok = _pool_kind(class_kind, archetype_ids)
    arch = {str(a) for a in (archetype_ids or [])}
    r = rng(seed, "exemplars:" + salt)
    scored = []
    for e in pool:
        if e["needs"] not in ok:
            continue
        s = 0.0
        if arch & set(e["archetypes"]):
            s += 2.0
        if str(e["card"].get("rarity", "")) == str(rarity):
            s += 1.0
        scored.append((s + r.random() * 0.999, e["card"]))  # the seeded jitter breaks ties AND rotates the tail
    scored.sort(key=lambda t: -t[0])
    cards = [c for _, c in scored]
    avoid = set(avoid_triples or ())
    # walk the ranked list for the first window of n whose id-set is fresh; fall back to the top n.
    for start in range(0, max(1, len(cards) - n + 1)):
        window = cards[start:start + n]
        if len(window) < n:
            break
        if frozenset(c.get("id") for c in window) not in avoid:
            return [dict(c) for c in window]
    return [dict(c) for c in cards[:n]]


def exemplar_block(cards: list[dict]) -> str:
    if not cards:
        return ""
    body = "\n\n".join(json.dumps(c, indent=2) for c in cards)
    return ("EXEMPLAR CARDS (validated forged cards in this style — match their level of COMPOSITION and "
            "balance; do NOT copy them, and never reuse their ids or names):\n```json\n" + body + "\n```")


# --- Fix A: class identity + shapes already used -----------------------------------------------------

def identity_block(bp: dict, metaphors=None) -> str:
    """The class identity for the per-card SYSTEM prompt: name, fantasy, the archetypes, the pair/strategy
    lines, and any class-kind pool names. Replaces the v1 'Ironclad-like Strength/Block character' framing."""
    bp = bp or {}
    lines = [f'Class: "{bp.get("name", "")}"']
    desc = strip_metaphors(str(bp.get("description") or "").strip(), metaphors)
    if desc:
        lines.append(f"Fantasy: {desc}")
    archs = [a for a in (bp.get("archetypes") or []) if isinstance(a, dict)]
    if archs:
        lines.append("Archetypes (the engines this class is built on):")
        for a in archs:
            d = strip_metaphors(str(a.get("description") or "").strip(), metaphors)
            lines.append(f"- {a.get('name') or a.get('id') or 'engine'} [{a.get('id', '')}]: {d}")
    for l in (bp.get("v2_strategy_lines") or []):
        lines.append(f"- line: {strip_metaphors(str(l), metaphors)}")
    if not bp.get("v2_strategy_lines"):
        for pl in (bp.get("pair_lines") or []):
            if isinstance(pl, dict) and pl.get("pair"):
                lines.append(f"- line: {' + '.join(str(x) for x in pl['pair'])} -> {pl.get('strategy', '?')}")
    pools = []
    if int(bp.get("orb_slots", 0) or 0) > 0:
        pools.append(f"orb class ({bp.get('orb_slots')} slots)")
    names = [str(s.get("name")) for s in (bp.get("status_pool") or []) if isinstance(s, dict) and s.get("name")]
    if names:
        pools.append("custom statuses: " + ", ".join(names))
    names = [str(s.get("name")) for s in (bp.get("summon_pool") or []) if isinstance(s, dict) and s.get("name")]
    if names:
        pools.append("minion: " + ", ".join(names))
    if pools:
        lines.append("Class kind: " + "; ".join(pools))
    return "\n".join(lines)


def card_shape(card: dict) -> str:
    """A compact skeleton key for one card: its op set (with statuses / trigger kinds / when kinds / scales
    folded in), e.g. 'damage+apply_status:poison' or 'add_trigger:on_exhaust>draw'."""
    from . import census
    cc = census.walk_card(card or {})
    parts = []
    for op in sorted(cc.ops):
        if op == "apply_status":
            parts.append("apply_status:" + "/".join(sorted(cc.statuses)) if cc.statuses else op)
        elif op == "add_trigger":
            parts.append("add_trigger:" + "/".join(sorted(cc.triggers)) if cc.triggers else op)
        else:
            parts.append(op)
    key = "+".join(parts)
    if cc.whens:
        key += " when:" + "/".join(sorted(cc.whens))
    if cc.scales:
        key += " scale:" + "/".join(sorted(cc.scales))
    return key


def used_shapes_line(made: list[dict], *, max_items: int = 14) -> str:
    """The per-class 'already used shapes' line for the next card brief: the effect skeletons + statuses this
    class already has (non-basic, non-token), so the model differs by at least one op up front instead of
    hitting the reprint gate after the fact."""
    shapes: Counter = Counter()
    statuses: Counter = Counter()
    from . import census
    for m in made or []:
        card = m.get("card") or {}
        plan = m.get("plan") or {}
        if str(card.get("rarity", plan.get("rarity", ""))).lower() in ("basic", "token") or card.get("token"):
            continue
        if plan.get("role") in ("basic_attack", "basic_skill"):
            continue
        shapes[card_shape(card)] += 1
        statuses.update(census.walk_card(card).statuses.keys())
    if not shapes:
        return ""
    top = [f"[{k}] x{n}" if n > 1 else f"[{k}]" for k, n in shapes.most_common(max_items)]
    line = ("SHAPES ALREADY USED in this class (this card MUST differ from every one of these in at least one op, "
            "status, gate, or scale): " + ", ".join(top))
    if statuses:
        line += ". Statuses already applied: " + ", ".join(f"{s} x{n}" for s, n in statuses.most_common(8))
    return line + "."


# --- Fix C: metaphor stripping ------------------------------------------------------------------------

def strip_metaphors(text: str, metaphors) -> str:
    """Remove catalog metaphor phrases (case-insensitive, whole-phrase) from `text`, tidying doubled spaces and
    dangling separators. No-op when `metaphors` is empty/None. Used on the blueprint brief and the per-card
    class context so the catalog's stock phrases only ever reach the cloud stage."""
    if not text or not metaphors:
        return text or ""
    out = str(text)
    for m in sorted({str(x).strip() for x in metaphors if str(x).strip()}, key=len, reverse=True):
        out = re.sub(r"(?i)\b" + re.escape(m) + r"\b", "", out)
    out = re.sub(r"\(\s*\)", "", out)
    out = re.sub(r"\s+([,;.:])", r"\1", out)
    out = re.sub(r"([,;:])\s*(?=[,;.:])", "", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"(?m)^[ \t]+|[ \t]+$", "", out)
    return out.strip()


# --- Fix D: rotating homage examples + the name post-pass --------------------------------------------

# 20 base-game cards that express cleanly in the constrained vocabulary. Three are drawn per forge (seeded)
# for the blueprint prompt's REPRINT HOMAGE rule, replacing the fixed Deflect/Slice/Bludgeon trio (Cause 4).
HOMAGE_POOL: list[tuple[str, str]] = [
    ("Deflect", "0-cost skill, gain 4 Block"),
    ("Slice", "0-cost attack, deal 6 damage"),
    ("Bludgeon", "3-cost attack, deal 32 damage"),
    ("Anger", "0-cost attack, deal 6 damage and add a copy of Anger to your discard pile"),
    ("Pommel Strike", "1-cost attack, deal 9 damage and draw 1 card"),
    ("Twin Strike", "1-cost attack, deal 5 damage twice"),
    ("Cleave", "1-cost attack, deal 8 damage to ALL enemies"),
    ("Iron Wave", "1-cost attack, gain 5 Block and deal 5 damage"),
    ("Shrug It Off", "1-cost skill, gain 8 Block and draw 1 card"),
    ("Flex", "0-cost skill, gain 2 Strength this turn only (temp_strength)"),
    ("Inflame", "1-cost power, gain 2 Strength"),
    ("Metallicize", "1-cost power, gain 3 Block at the end of your turn"),
    ("Bloodletting", "0-cost skill, lose 3 HP and gain 2 energy"),
    ("Thunderclap", "1-cost attack, deal 4 damage and apply 1 Vulnerable to ALL enemies"),
    ("Clothesline", "2-cost attack, deal 12 damage and apply 2 Weak"),
    ("Poisoned Stab", "1-cost attack, deal 6 damage and apply 3 Poison"),
    ("Backflip", "1-cost skill, gain 5 Block and draw 2 cards"),
    ("Rampage", "1-cost attack, deal 8 damage; grows by 5 each time it is played this combat"),
    ("Feel No Pain", "1-cost power, whenever a card is Exhausted gain 3 Block"),
    ("Rupture", "1-cost power, whenever you lose HP from a card gain 1 Strength"),
]


def homage_examples(seed: int, n: int = 3) -> str:
    """'Deflect: 0-cost skill, gain 4 Block; ...' — `n` seeded draws from HOMAGE_POOL."""
    picks = seeded_shuffle(HOMAGE_POOL, seed, "homage")[:n]
    return "; ".join(f"{name}: {effect}" for name, effect in picks)


# The global top-50: names forged classes keep converging on (measured over scratch/_class_gen + the triad
# runs in the plan) plus the base-game names models reach for reflexively. A forged card carrying one of these
# is asked to rename in the post-pass.
GLOBAL_TOP_NAMES: list[str] = [
    "Held Breath", "Held Charge", "Coiled Strike", "Coiled Spring", "Patient Strike", "Patience", "Vigil",
    "Deflect", "Slice", "Bludgeon", "Iron Will", "Killing Blow", "The Killing Blow", "Feint", "Second Wind",
    "Bloodlust", "Last Stand", "Riposte", "Parry", "Bulwark", "Overheat", "Reforge", "Kindle", "Stoke",
    "Ember Strike", "Venom Strike", "Twin Fang", "Fever Dream", "Plague Lancet", "Catacomb Vault",
    "Battle Trance", "Shrug It Off", "Heavy Blow", "Sudden Lunge", "Precise Thrust", "Windbreak", "Stormsense",
    "Live Wire", "Voltage", "Squall Line", "Dented Plate", "Silk Guard", "Barrow Wall", "Ghost-Light Veil",
    "Deferred Judgement", "Apocalypse Hymn", "Spore Siphon", "Septic Scratch", "Tainted Bandage", "Hemlock Dram",
]


def banned_names(window, *, extra=None) -> set[str]:
    """Lower-cased names the post-pass rejects: every card name in the recent ledger window (v2 entries carry
    `card_names`) + the global top-50 + `extra`."""
    out = {n.lower() for n in GLOBAL_TOP_NAMES}
    for e in window or []:
        for n in (e.get("card_names") or []):
            if isinstance(n, str) and n.strip():
                out.add(n.strip().lower())
    for n in extra or []:
        if isinstance(n, str) and n.strip():
            out.add(n.strip().lower())
    return out


def name_collisions(made: list[dict], banned: set[str]) -> list[int]:
    """Indices of non-basic, non-token cards whose name is in `banned` (case-insensitive)."""
    out = []
    for i, m in enumerate(made or []):
        card = m.get("card") or {}
        plan = m.get("plan") or {}
        if plan.get("role") in ("basic_attack", "basic_skill") or card.get("token"):
            continue
        if str(card.get("rarity", "")).lower() in ("basic", "token"):
            continue
        if str(card.get("name", "")).strip().lower() in banned:
            out.append(i)
    return out


def rename_pass(made: list[dict], banned: set[str], rename, note, *, max_renames: int = 8) -> int:
    """The Fix D name post-pass. For every colliding card, `rename(card, reason) -> str | None` is asked for a
    fresh name (one cheap names-only call on the real path; the fakes return None/the same name and the pass
    becomes a logged no-op). A rename is accepted only if it is new, non-empty, and not itself banned. Mutates
    `made` in place; returns the number of cards renamed. Never raises."""
    renamed = 0
    for idx in name_collisions(made, banned)[:max_renames]:
        card = made[idx].get("card") or {}
        old = str(card.get("name", ""))
        reason = (f"the name '{old}' was already used in a recent forge (or is on the global overused-name "
                  "list); give this card a NEW, different name that fits the class")
        new = None
        try:
            new = rename(card, reason)
        except Exception as e:  # noqa: BLE001 — a rename failure must never break the forge
            note(f"name pass: rename call for '{old}' errored ({e}); keeping it")
            continue
        new = str(new or "").strip()
        if not new or new.lower() == old.lower() or new.lower() in banned:
            note(f"name pass: '{old}' collides with a recent/overused name; no fresh name offered, keeping it")
            continue
        card["name"] = new
        banned.add(new.lower())
        renamed += 1
        note(f"name pass: renamed '{old}' -> '{new}' (recent/overused name)")
    return renamed
