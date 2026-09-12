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

W2.1 (vocab-gap remediation, 2026-09-09) widened what the census COUNTS so coverage.py / featured.py have a
detector for the whole vocabulary, not a slice: multi-hit (`hits` >= 2, now NON-plain), the four card
keywords (exhaust / retain / innate / ethereal), `apply_status_custom` statuses, `buff_summon` statuses and the
summon op mix (summon / summon_attack / medic / sacrifice_summon - Phase AV, v52),
the specialty statuses (poison / frail / focus — neither generic nor exotic), `tags`, `upgrade.cost`,
`once_per_turn` triggers, `ripen` amounts, and targeted trigger payloads. `format_report` prints EVERY counter.
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
    "temp_thorns",  # Phase AN (v44): the one-turn bristle (temp_focus joins focus in the specialty bucket)
})
# W2.1: the SPECIALTY statuses — neither the over-used generic debuffs nor "exotic" mitigation/buff exotica.
# Poison is the DoT debuff, Frail the block-side debuff, Focus the orb-class buff. Their own bucket so a
# poison class isn't scored as "generic" and an orb class's Focus isn't scored as "exotic".
SPECIALTY_STATUSES = frozenset({"poison", "frail", "focus", "temp_focus"})  # Phase AN (v44): temp_focus is orb-class too
# W2.1: the four card-property keywords (nullary ops). `multi_hit` joins them as a keyword KIND (see
# CardCensus.keyword_kinds) because "Deal 4 damage 3 times" is a card shape, not an op.
KEYWORD_OPS = frozenset({"exhaust", "retain", "innate", "ethereal"})
MULTI_HIT_KIND = "multi_hit"


@dataclass
class CardCensus:
    """What ONE card touches, walking base + upgrade + nested add_trigger payloads. The Counters hold
    occurrence counts (an op/status used twice counts twice); `.keys()` gives the distinct-kind set that
    the coverage quotas (N-1) read."""
    ops: Counter = field(default_factory=Counter)
    statuses: Counter = field(default_factory=Counter)     # apply_status statuses only (base game statuses)
    unblockable: int = 0                                    # Phase AN (v44): damage effects flagged unblockable:true
    triggers: Counter = field(default_factory=Counter)     # add_trigger trigger kinds
    whens: Counter = field(default_factory=Counter)        # `when` condition kinds
    scales: Counter = field(default_factory=Counter)       # scale sources (cards_in_hand, x, forged, ...)
    grow: int = 0                                          # Phase U (gap #23): count of `grow` (Rampage) damage effects
    x_cost: bool = False
    cost4: bool = False                                    # Phase AX (v53): the heavyweight (rare-only) cost slot
    plain: bool = False
    # --- W2.1 counters -------------------------------------------------------------------------------
    multi_hit: int = 0                                     # damage/summon_attack effects with hits >= 2
    keywords: Counter = field(default_factory=Counter)     # exhaust / retain / innate / ethereal (nullary ops)
    custom_statuses: Counter = field(default_factory=Counter)  # apply_status_custom status_name
    summon_buffs: Counter = field(default_factory=Counter)     # buff_summon status (default strength)
    tagged: bool = False                                   # the card declares `tags`
    upgrade_cost: bool = False                             # the upgrade carries an absolute `cost` (Phase AG)
    once_per_turn: int = 0                                 # add_trigger effects flagged once_per_turn
    once_per_combat: int = 0                               # Phase AK (v41): add_trigger effects flagged once_per_combat
    ripen_amounts: Counter = field(default_factory=Counter)    # ripen trigger countdowns (amount -> count)
    targeted_payloads: int = 0                             # effects INSIDE a trigger payload carrying a `target`
    # Phase AL (v42): what the trigger PAYLOADS reach for — the op tally inside payloads (so a class-kind engine
    # like summon_attack-in-a-trigger is detectable), payload effects carrying a `scale`, and multi-hit payloads.
    payload_ops: Counter = field(default_factory=Counter)
    scaled_payloads: int = 0
    multi_hit_payloads: int = 0

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

    @property
    def keyword_kinds(self) -> set[str]:
        """The card-shape keywords this card carries: exhaust / retain / innate / ethereal / multi_hit."""
        kinds = set(self.keywords)
        if self.multi_hit:
            kinds.add(MULTI_HIT_KIND)
        return kinds

    @property
    def specialty_status_kinds(self) -> set[str]:
        return set(self.statuses) & SPECIALTY_STATUSES


def _walk_effects(effects, cc: CardCensus, *, in_payload: bool = False) -> None:
    """Tally one effects list into `cc`, recursing into add_trigger payloads (`in_payload` marks the
    recursion so targeted payload effects can be counted)."""
    if not isinstance(effects, list):
        return
    for eff in effects:
        if not isinstance(eff, dict):
            continue
        op = eff.get("op")
        if isinstance(op, str) and op:
            cc.ops[op] += 1
            if op in KEYWORD_OPS:
                cc.keywords[op] += 1
        if op == "apply_status":
            status = eff.get("status")
            if isinstance(status, str) and status:
                cc.statuses[status] += 1
        if op == "apply_status_custom":
            sname = eff.get("status_name")
            if isinstance(sname, str) and sname:
                cc.custom_statuses[sname.strip().lower()] += 1
        if op == "buff_summon":
            bstatus = eff.get("status")
            cc.summon_buffs[bstatus.strip().lower() if isinstance(bstatus, str) and bstatus else "strength"] += 1
        hits = eff.get("hits")
        if op in ("damage", "summon_attack") and isinstance(hits, int) and not isinstance(hits, bool) and hits >= 2:
            cc.multi_hit += 1
        if op == "damage" and eff.get("unblockable") is True:  # Phase AN (v44)
            cc.unblockable += 1
        if in_payload and isinstance(eff.get("target"), str) and eff.get("target"):
            cc.targeted_payloads += 1
        if in_payload:  # Phase AL (v42)
            if isinstance(op, str) and op:
                cc.payload_ops[op] += 1
            if isinstance(eff.get("scale"), str) and eff.get("scale"):
                cc.scaled_payloads += 1
            if op in ("damage", "summon_attack") and isinstance(hits, int) and not isinstance(hits, bool) and hits >= 2:
                cc.multi_hit_payloads += 1
        if op == "add_trigger":
            trig = eff.get("trigger")
            if isinstance(trig, str) and trig:
                cc.triggers[trig] += 1
                if trig == "ripen":
                    amt = eff.get("amount")
                    if isinstance(amt, int) and not isinstance(amt, bool):
                        cc.ripen_amounts[amt] += 1
            if eff.get("once_per_turn") is True:
                cc.once_per_turn += 1
            if eff.get("once_per_combat") is True:  # Phase AK (v41)
                cc.once_per_combat += 1
            _walk_effects(eff.get("effects"), cc, in_payload=True)  # nested payload
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
    _c = card.get("cost")
    cc.cost4 = isinstance(_c, int) and not isinstance(_c, bool) and _c >= 4  # Phase AX (v53)
    tags = card.get("tags")
    cc.tagged = isinstance(tags, list) and any(isinstance(t, str) and t for t in tags)
    _walk_effects(card.get("effects"), cc)
    upgrade = card.get("upgrade")
    if isinstance(upgrade, dict):
        _walk_effects(upgrade.get("effects"), cc)
        uc = upgrade.get("cost")
        cc.upgrade_cost = isinstance(uc, int) and not isinstance(uc, bool)
    # Plain = a stat line only: op set ⊆ base ops, no conditional gate, no scaling, not X-cost, no grow
    # (Rampage), and (W2.1) no multi-hit — "Deal 4 damage 3 times" is a shape, not a stat line.
    cc.plain = (
        bool(cc.ops)
        and set(cc.ops) <= BASE_OPS
        and not cc.whens
        and not cc.scales
        and not cc.x_cost
        and not cc.grow
        and not cc.multi_hit
    )
    return cc


@dataclass
class Census:
    """Aggregate reading over a set of cards. Counters are summed occurrence counts; `per_card` keeps the
    individual readings (paired with the card dict) so quota code can pick victims."""
    total: int = 0
    plain: int = 0
    x_cost: int = 0
    cost4: int = 0  # Phase AX (v53): cards in the heavyweight cost-4 slot (rare-only)
    ops: Counter = field(default_factory=Counter)
    statuses: Counter = field(default_factory=Counter)
    triggers: Counter = field(default_factory=Counter)
    whens: Counter = field(default_factory=Counter)
    scales: Counter = field(default_factory=Counter)
    per_card: list = field(default_factory=list)  # list[tuple[dict, CardCensus]]
    # --- W2.1 counters (summed occurrence counts; the *_cards ints count CARDS carrying the feature) ---
    multi_hit: int = 0
    keywords: Counter = field(default_factory=Counter)
    custom_statuses: Counter = field(default_factory=Counter)
    summon_buffs: Counter = field(default_factory=Counter)
    tagged_cards: int = 0
    upgrade_cost_cards: int = 0
    once_per_turn: int = 0
    once_per_combat: int = 0
    ripen_amounts: Counter = field(default_factory=Counter)
    targeted_payloads: int = 0
    grow: int = 0
    payload_ops: Counter = field(default_factory=Counter)  # Phase AL (v42)
    scaled_payloads: int = 0
    multi_hit_payloads: int = 0

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

    @property
    def specialty_status_kinds(self) -> set[str]:
        return set(self.statuses) & SPECIALTY_STATUSES

    @property
    def keyword_kinds(self) -> set[str]:
        kinds = set(self.keywords)
        if self.multi_hit:
            kinds.add(MULTI_HIT_KIND)
        return kinds

    def add_card(self, card: dict, cc: CardCensus) -> None:
        """Fold one card's reading into this aggregate."""
        self.total += 1
        if cc.plain:
            self.plain += 1
        if cc.x_cost:
            self.x_cost += 1
        if cc.cost4:  # Phase AX (v53)
            self.cost4 += 1
        self.ops.update(cc.ops)
        self.statuses.update(cc.statuses)
        self.triggers.update(cc.triggers)
        self.whens.update(cc.whens)
        self.scales.update(cc.scales)
        self.multi_hit += cc.multi_hit
        self.keywords.update(cc.keywords)
        self.custom_statuses.update(cc.custom_statuses)
        self.summon_buffs.update(cc.summon_buffs)
        if cc.tagged:
            self.tagged_cards += 1
        if cc.upgrade_cost:
            self.upgrade_cost_cards += 1
        self.once_per_turn += cc.once_per_turn
        self.once_per_combat += cc.once_per_combat
        self.ripen_amounts.update(cc.ripen_amounts)
        self.targeted_payloads += cc.targeted_payloads
        self.grow += cc.grow
        self.payload_ops.update(cc.payload_ops)  # Phase AL (v42)
        self.scaled_payloads += cc.scaled_payloads
        self.multi_hit_payloads += cc.multi_hit_payloads
        self.per_card.append((card, cc))

    def merge(self, other: "Census") -> None:
        """Fold another aggregate into this one (per_card readings are NOT copied — the aggregate is the
        report's unit; callers that need victims keep their own per-class Census)."""
        self.total += other.total
        self.plain += other.plain
        self.x_cost += other.x_cost
        self.cost4 += other.cost4  # Phase AX (v53)
        for name in ("ops", "statuses", "triggers", "whens", "scales", "keywords", "custom_statuses",
                     "summon_buffs", "ripen_amounts", "payload_ops"):
            getattr(self, name).update(getattr(other, name))
        for name in ("multi_hit", "tagged_cards", "upgrade_cost_cards", "once_per_turn", "once_per_combat",
                     "targeted_payloads", "grow", "scaled_payloads", "multi_hit_payloads"):
            setattr(self, name, getattr(self, name) + getattr(other, name))


def census_cards(cards) -> Census:
    """Census a flat list of card dicts."""
    cen = Census()
    for card in cards or []:
        if not isinstance(card, dict):
            continue
        cen.add_card(card, walk_card(card))
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


def _all(counter: Counter) -> str:
    """Every key of a Counter, most-used first (ties alphabetical) — never a fixed subset (W2.1)."""
    if not counter:
        return "-"
    return " ".join(f"{k}={n}" for k, n in sorted(counter.items(), key=lambda kv: (-kv[1], str(kv[0]))))


# The module-docstring table's fixed columns, kept at the head of their lines so the N-0 baseline numbers stay
# readable at a glance; _all() then prints EVERYTHING else the census counted.
_STATUS_HEAD = ["vulnerable", "weak", "blur", "metallicize", "artifact", "buffer", "intangible", "ritual"]
_REACTIVE_HEAD = ["on_exhaust", "on_card_played", "attacked", "on_block_gained", "on_card_drawn", "on_damage_dealt"]


def format_report(named: list[tuple[str, Census]]) -> str:
    """Per-class one-liners + an aggregate block. The aggregate prints EVERY counter the census keeps (W2.1) —
    the docstring table's fixed columns lead each line, then the full tally."""
    lines: list[str] = []
    agg = Census()
    for name, cen in named:
        agg.merge(cen)
        lines.append(
            f"  {name:<22} cards={cen.total:>3}  plain={cen.plain:>3} ({round(cen.plain_share*100):>3}%)"
            f"  reactive_kinds={len(cen.reactive_trigger_kinds)}  when_kinds={len(set(cen.whens))}"
            f"  exotic={len(cen.exotic_status_kinds)}  keywords={len(cen.keyword_kinds)}"
            f"  multi_hit={cen.multi_hit}"
        )
    out = ["Per-class:"] + lines + ["", "Aggregate:"]
    out.append(f"  cards={agg.total}  plain={agg.plain} ({round(agg.plain_share*100)}%)  X-cost cards={agg.x_cost}"
               f"  multi_hit={agg.multi_hit}  grow={agg.grow}")
    out.append(f"  statuses: {_order(agg.statuses, _STATUS_HEAD)}  | all: {_all(agg.statuses)}")
    out.append(f"  specialty statuses: {_order(agg.statuses, sorted(SPECIALTY_STATUSES))}")
    out.append(f"  custom statuses (apply_status_custom): {_all(agg.custom_statuses)}")
    out.append(f"  summon buffs (buff_summon): {_all(agg.summon_buffs)}"
               f"  | summon ops: summon={agg.ops.get('summon', 0)} attack={agg.ops.get('summon_attack', 0)}"
               f" medic={agg.ops.get('heal_summon', 0) + agg.ops.get('shield_summon', 0)}"
               f" sacrifice={agg.ops.get('sacrifice_summon', 0)}")  # Phase AV (v52)
    # Phase AX (v53): the two new ops + the heavyweight cost slot (cost 4 is rare-only, so a non-zero count here
    # should always be matched by rares in the per-class lines above).
    out.append(f"  AX (v53): spend_forge={agg.ops.get('spend_forge', 0)}  spread_debuffs={agg.ops.get('spread_debuffs', 0)}"
               f"  cost4={agg.cost4}")
    out.append(f"  triggers: turn_end+turn_start={agg.triggers.get('turn_end',0)+agg.triggers.get('turn_start',0)}  "
               f"reactive[{'/'.join(_REACTIVE_HEAD)}]={'/'.join(str(agg.triggers.get(k,0)) for k in _REACTIVE_HEAD)}"
               f"  | all: {_all(agg.triggers)}")
    out.append(f"  trigger extras: once_per_turn={agg.once_per_turn}  once_per_combat={agg.once_per_combat}"
               f"  targeted_payloads={agg.targeted_payloads}  ripen_amounts: {_all(agg.ripen_amounts)}")
    out.append(f"  trigger payloads (AL): scaled_payloads={agg.scaled_payloads}  multi_hit_payloads={agg.multi_hit_payloads}"
               f"  payload_ops: {_all(agg.payload_ops)}")
    out.append(f"  when: {_order(agg.whens, ['turn_at_least','enemy_count_ge','hp_below_half'])}  | all: {_all(agg.whens)}")
    out.append(f"  scales: {_order(agg.scales, ['unspent_energy_last_turn','x'])}  | all: {_all(agg.scales)}")
    out.append(f"  keywords: {_order(agg.keywords, ['innate','ethereal','retain','exhaust'])}")
    out.append(f"  card fields: tagged_cards={agg.tagged_cards}  upgrade_cost_cards={agg.upgrade_cost_cards}")
    out.append(f"  ops (all): {_all(agg.ops)}")
    return "\n".join(out)
