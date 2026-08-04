"""census.py — measure the CREATIVE BREADTH of forged cards (the Phase N acceptance metric).

Pure functions over card JSON (the same shape `class_forge` emits and `bts1` encodes): walk a card's
`effects`, its `upgrade.effects`, and every nested `add_trigger` payload, tallying which ops / statuses /
trigger kinds / `when` conditions / scales it touches, whether it is an X-cost card, and whether it is a
"plain" stat-line card (op set is a subset of {damage, block, apply_status, draw} with no `when` guard,
no `scale`, and not X-cost). `census_cards` / `census_bundle` aggregate those per-card readings into
occurrence Counters plus a plain count.

The METRIC this reproduces (aggregate occurrence counts = base + upgrade + nested payloads) — census of
the 36-class overnight run (`generation/scratch/overnight-2026-07-06/codes/`, 965 cards, vocab v18):

| metric                                                        | baseline           |
|---------------------------------------------------------------|--------------------|
| cards using ONLY damage/block/apply_status/draw               | 25% (241/965)      |
| Vulnerable / Weak applications                                | 162 / 80           |
| Blur, Metallicize, Artifact, Buffer / Intangible, Ritual      | 2 each / 0 each    |
| turn_end+turn_start triggers vs six H4 reactive kinds         | 246 vs 20/8/6/6/0/0|
|   (on_exhaust/on_card_played/attacked/on_block_gained/on_card_drawn/on_damage_dealt)                  |
| `when`: turn_at_least / enemy_count_ge / hp_below_half        | 0 / 0 / 12         |
| scales: unspent_energy_last_turn / x                          | 0 / 10             |
| `innate` / `ethereal`                                         | 0 / 2              |

`btsgen-census <paths...>` decodes `.btsc.txt` codes (or reads bundle .json) and prints per-class + an
aggregate table — run it over the codes dir above to reproduce these numbers (the N-0 gate).
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import bts1

# --- vocabulary partitions the breadth metric cares about -------------------------------------------
# A "plain" card's whole op set lives inside this set (and it carries no when/scale/X — see walk_card).
BASE_OPS = frozenset({"damage", "block", "apply_status", "draw"})
# Triggers that are NOT reactive — the harness leans on these; breadth wants the H4 reactive kinds too.
NON_REACTIVE_TRIGGERS = frozenset({"turn_start", "turn_end"})
# The over-used generic debuffs ("use sparingly", measurably ignored by the 7B).
GENERIC_DEBUFFS = frozenset({"vulnerable", "weak"})
# The "exotic" statuses breadth wants to see instead of Vulnerable/Weak.
EXOTIC_STATUSES = frozenset({
    "thorns", "regen", "metallicize", "artifact", "buffer", "blur", "intangible",
    "ritual", "barricade", "temp_strength", "temp_dexterity",
})


@dataclass
class CardCensus:
    """What ONE card touches, walking base + upgrade + nested add_trigger payloads. The Counters hold
    occurrence counts (an op/status used twice counts twice); `.keys()` gives the distinct-kind set that
    the coverage quotas (N-1) read."""
    ops: Counter = field(default_factory=Counter)
    statuses: Counter = field(default_factory=Counter)     # apply_status statuses only (base game statuses)
    triggers: Counter = field(default_factory=Counter)     # add_trigger trigger kinds
    whens: Counter = field(default_factory=Counter)        # `when` condition kinds
    scales: Counter = field(default_factory=Counter)       # scale sources (cards_in_hand, x, forged, ...)
    grow: int = 0                                          # Phase U (gap #23): count of `grow` (Rampage) damage effects
    x_cost: bool = False
    plain: bool = False

    @property
    def reactive_trigger_kinds(self) -> set[str]:
        """Trigger kinds beyond turn_start/turn_end (the reactive engines breadth counts)."""
        return set(self.triggers) - NON_REACTIVE_TRIGGERS

    @property
    def exotic_status_kinds(self) -> set[str]:
        return set(self.statuses) & EXOTIC_STATUSES

    @property
    def uses_generic_debuff(self) -> bool:
        return bool(set(self.statuses) & GENERIC_DEBUFFS)

    @property
    def scaled_or_x(self) -> bool:
        return bool(self.scales) or self.x_cost


def _walk_effects(effects, cc: CardCensus) -> None:
    """Tally one effects list into `cc`, recursing into add_trigger payloads."""
    if not isinstance(effects, list):
        return
    for eff in effects:
        if not isinstance(eff, dict):
            continue
        op = eff.get("op")
        if isinstance(op, str) and op:
            cc.ops[op] += 1
        if op == "apply_status":
            status = eff.get("status")
            if isinstance(status, str) and status:
                cc.statuses[status] += 1
        if op == "add_trigger":
            trig = eff.get("trigger")
            if isinstance(trig, str) and trig:
                cc.triggers[trig] += 1
            _walk_effects(eff.get("effects"), cc)  # nested payload
        when = eff.get("when")
        if isinstance(when, dict):
            kind = when.get("kind")
            if isinstance(kind, str) and kind:
                cc.whens[kind] += 1
        scale = eff.get("scale")
        if isinstance(scale, str) and scale:
            cc.scales[scale] += 1
        if isinstance(eff.get("grow"), int) and eff.get("grow"):  # Phase U (gap #23): Rampage grow-on-play
            cc.grow += 1


def walk_card(card: dict) -> CardCensus:
    """Census one card dict (base effects + upgrade effects + nested trigger payloads)."""
    cc = CardCensus()
    if not isinstance(card, dict):
        return cc
    cc.x_cost = str(card.get("cost", "")).strip().lower() == "x"
    _walk_effects(card.get("effects"), cc)
    upgrade = card.get("upgrade")
    if isinstance(upgrade, dict):
        _walk_effects(upgrade.get("effects"), cc)
    # Plain = a stat line only: op set ⊆ base ops, no conditional gate, no scaling, not X-cost, no grow (Rampage).
    cc.plain = (
        bool(cc.ops)
        and set(cc.ops) <= BASE_OPS
        and not cc.whens
        and not cc.scales
        and not cc.x_cost
        and not cc.grow
    )
    return cc


@dataclass
class Census:
    """Aggregate reading over a set of cards. Counters are summed occurrence counts; `per_card` keeps the
    individual readings (paired with the card dict) so quota code can pick victims."""
    total: int = 0
    plain: int = 0
    x_cost: int = 0
    ops: Counter = field(default_factory=Counter)
    statuses: Counter = field(default_factory=Counter)
    triggers: Counter = field(default_factory=Counter)
    whens: Counter = field(default_factory=Counter)
    scales: Counter = field(default_factory=Counter)
    per_card: list = field(default_factory=list)  # list[tuple[dict, CardCensus]]

    @property
    def plain_share(self) -> float:
        return (self.plain / self.total) if self.total else 0.0

    @property
    def generic_debuff_count(self) -> int:
        return sum(self.statuses[s] for s in GENERIC_DEBUFFS)

    @property
    def reactive_trigger_kinds(self) -> set[str]:
        return set(self.triggers) - NON_REACTIVE_TRIGGERS

    @property
    def exotic_status_kinds(self) -> set[str]:
        return set(self.statuses) & EXOTIC_STATUSES


def census_cards(cards) -> Census:
    """Census a flat list of card dicts."""
    cen = Census()
    for card in cards or []:
        if not isinstance(card, dict):
            continue
        cc = walk_card(card)
        cen.total += 1
        if cc.plain:
            cen.plain += 1
        if cc.x_cost:
            cen.x_cost += 1
        cen.ops.update(cc.ops)
        cen.statuses.update(cc.statuses)
        cen.triggers.update(cc.triggers)
        cen.whens.update(cc.whens)
        cen.scales.update(cc.scales)
        cen.per_card.append((card, cc))
    return cen


def census_bundle(bundle: dict) -> Census:
    """Census a class bundle ({kind:'class', character, cards[]}) or a bare {cards:[...]}."""
    cards = bundle.get("cards") if isinstance(bundle, dict) else None
    return census_cards(cards or [])


# --- code / file decoding (reuse the reference codec) -----------------------------------------------

def decode_bundle(text: str) -> dict:
    """Decode a BTSC/BTS1 code OR raw bundle JSON into a bundle dict. A single BTS1 card decodes to a
    one-card bundle so the census walkers handle it uniformly."""
    text = text.strip()
    if text.startswith("BTSC.") or text.startswith("BTS1."):
        payload, kind = bts1.decode(text)
        obj = json.loads(payload)
        return obj if kind == "class" else {"kind": "card", "cards": [obj]}
    obj = json.loads(text)
    if isinstance(obj, dict) and "cards" in obj:
        return obj
    if isinstance(obj, list):
        return {"cards": obj}
    return {"cards": [obj]}  # a bare card object


def load_path(path) -> list[tuple[str, dict]]:
    """Load one path into [(name, bundle), ...]. A directory expands to its *.btsc.txt / *.json codes."""
    p = Path(path)
    out: list[tuple[str, dict]] = []
    if p.is_dir():
        files = sorted(list(p.glob("*.btsc.txt")) + list(p.glob("*.json")))
        for f in files:
            out.extend(load_path(f))
        return out
    name = p.stem.replace(".btsc", "")
    try:
        bundle = decode_bundle(p.read_text(encoding="utf-8"))
    except Exception as exc:  # keep going over a sweep even if one code is corrupt
        print(f"# WARN: could not decode {p}: {exc}")
        return out
    if isinstance(bundle.get("character"), dict) and bundle["character"].get("name"):
        name = bundle["character"]["name"]
    out.append((name, bundle))
    return out


# --- reporting --------------------------------------------------------------------------------------

def _order(counter: Counter, keys) -> str:
    return " ".join(f"{k}={counter.get(k, 0)}" for k in keys)


def format_report(named: list[tuple[str, Census]]) -> str:
    """Per-class one-liners + an aggregate block matching the module-docstring table."""
    lines: list[str] = []
    agg = Census()
    for name, cen in named:
        agg.total += cen.total
        agg.plain += cen.plain
        agg.x_cost += cen.x_cost
        agg.ops.update(cen.ops)
        agg.statuses.update(cen.statuses)
        agg.triggers.update(cen.triggers)
        agg.whens.update(cen.whens)
        agg.scales.update(cen.scales)
        lines.append(
            f"  {name:<22} cards={cen.total:>3}  plain={cen.plain:>3} ({round(cen.plain_share*100):>3}%)"
            f"  reactive_kinds={len(cen.reactive_trigger_kinds)}  when_kinds={len(set(cen.whens))}"
            f"  exotic={len(cen.exotic_status_kinds)}"
        )
    reactive_keys = ["on_exhaust", "on_card_played", "attacked", "on_block_gained", "on_card_drawn", "on_damage_dealt"]
    out = ["Per-class:"] + lines + ["", "Aggregate:"]
    out.append(f"  cards={agg.total}  plain={agg.plain} ({round(agg.plain_share*100)}%)  X-cost cards={agg.x_cost}")
    out.append(f"  statuses: {_order(agg.statuses, ['vulnerable','weak','blur','metallicize','artifact','buffer','intangible','ritual'])}")
    out.append(f"  triggers: turn_end+turn_start={agg.triggers.get('turn_end',0)+agg.triggers.get('turn_start',0)}  "
               f"reactive[{'/'.join(reactive_keys)}]={'/'.join(str(agg.triggers.get(k,0)) for k in reactive_keys)}")
    out.append(f"  when: {_order(agg.whens, ['turn_at_least','enemy_count_ge','hp_below_half'])}")
    out.append(f"  scales: {_order(agg.scales, ['unspent_energy_last_turn','x'])}")
    out.append(f"  properties: innate={agg.ops.get('innate',0)}  ethereal={agg.ops.get('ethereal',0)}")
    return "\n".join(out)
