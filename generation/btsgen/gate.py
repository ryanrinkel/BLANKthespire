"""Card-stage vocabulary gating (docs/plans/JEV_EVALUATION_PLAN.md, Phases 1a + 1b).

The card system prompt pastes VOCABULARY.md whole (~58k chars) for every card. Most cards use two ops. This
module decides, per card BRIEF, which vocabulary families and op rows the designer needs, and lays the prompt
out so the gating does not throw away provider prefix caching:

    [ CORE: head + always-on vocab + card.schema.json (whole) + rarity/reprint/feedback/task ]   byte-identical
    [ # VOCABULARY ADD-ONS: triggers, conditions, scaling, forge, then extra op rows          ]   per card,
                                                                                                  canonical order
Rules (plan "Cache-safe layout"):
  1. The core is identical for every card in a forge, so it stays cached on OpenRouter / Ollama Cloud.
  2. Add-ons come after the core, always in the same canonical order.
  3. The FULL prompt (repairs, Jev failures) = core + every add-on in that order, so a repair still hits the
     core cache.
  4. Schema: Phase 1b (the default, $BTS_VOCAB_GATE_SCHEMA=split) splits card.schema.json the same way — the
     core keeps the card-level fields, the core ops and every rule it can't attribute; each gated element (an
     op's enum value and prose, its fields, its allOf rules, the triggerEffect/condition defs) moves to one
     "Schema additions" block at the end of the tail. `whole` = Phase 1a: the schema pasted whole in the core.
     The prompt schema is guidance only; the validator always checks the COMPLETE card.schema.json.

Class-kind tier (deterministic, no model): when the forge knows the class's pool kinds (orb / status / summon),
the matching CLASS-IDENTITY sections and their op rows go into the core for a class that owns them and are
dropped entirely for one that doesn't (those cards are dropped by class_forge's safety nets anyway). The
signature-potion section is a class knob and never a card's business, so it is always dropped.

Per-card tier: `BTS_VOCAB_GATE` =
  off        (default) the prompt is byte-for-byte today's prompt; nothing here runs.
  heuristic  keyword rules over the brief pick the families; every gateable op row is kept.
  jev        heuristic OR Jev >= 0.15 picks families; Jev >= 0.05 picks op rows (the Phase 0 union).
             Jev = TypeSafe's typed-decision model via OpenRouter's Decisions API on OPENROUTER_API_KEY.
             Any Jev failure (HTTP error, timeout, bad shape) degrades THAT card to the full prompt.

The families' question text and keyword rules are the ones measured in Phase 0 (tools/jev_gate_eval.py,
tools/jev_op_eval.py). Change them and the Phase 0 numbers no longer describe production.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

_log = logging.getLogger(__name__)

ENV = "BTS_VOCAB_GATE"
MODES = ("off", "heuristic", "jev")
SCHEMA_ENV = "BTS_VOCAB_GATE_SCHEMA"
SCHEMA_MODES = ("split", "whole")
JEV_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
JEV_MODEL = "typesafe/jev-1.13"
JEV_TIMEOUT_S = 15
SECTION_THRESHOLD = 0.15   # Phase 0a: union with the heuristic at 0.15 -> 96.7% of cards complete
OP_THRESHOLD = 0.05        # Phase 0b: Jev >= 0.05 OR the core op rows -> 97.9%

VOCAB_MARK = "# THE VOCABULARY (authoring reference)\n"
SCHEMA_MARK = "\n# THE JSON SCHEMA"
ADDON_HEADER = ("\n\n# VOCABULARY ADD-ONS (more of THE VOCABULARY above, selected for this card — same rules, "
                "same closed set)\n")
CORE_POINTER = ("\n> Layout note: this vocabulary is split. The sections below apply to every card; the sections "
                "and op rows this card may also need are listed at the very END of this prompt under VOCABULARY "
                "ADD-ONS. Compose only from what is described in either part.\n")

# Vocabulary section title prefixes -> family. Anything not listed here is CORE (a new section defaults to
# always-on, which is the safe direction).
SECTION_FAMILY = {
    "## Triggers": "triggers",
    "## Conditions": "conditions",
    "## Structural mechanics": "scaling",
    "## Run-persistent Forge": "forge",
    "## Orbs": "orbs",
    "## Forged statuses": "custom_status",
    "## Forged summons": "summons",
    "## Hybrid classes": "hybrid",
}
ALWAYS_DROP = ("## The signature potion",)
EFFECT_OPS = "## Effect ops"

# Class-kind families: decided per CLASS (constant within a forge) when the kinds are known.
KIND_FAMILY = {"orb": "orbs", "status": "custom_status", "summon": "summons"}
CLASS_FAMILIES = ("orbs", "custom_status", "summons", "hybrid")
# Per-card families, in the canonical add-on order (most often included first).
CARD_FAMILIES = ("triggers", "conditions", "scaling", "forge")
# When no class kinds are known (a bare card call), the class-kind families are gated per card too.
LOOSE_FAMILIES = CARD_FAMILIES + ("orbs", "custom_status", "summons")

FAMILY_OPS = {
    "orbs": ("channel_orb", "evoke", "gain_orb_slot"),
    "custom_status": ("apply_status_custom",),
    "summons": ("summon", "summon_attack", "buff_summon", "shield_summon", "heal_summon", "sacrifice_summon"),
    "forge": ("spend_forge", "summon_blade", "blade_empower"),
}

# Op rows always in the core: the three the eval never gated plus the top ops by frequency on the 576 real
# cards of Phase 0 (class-kind ops excluded, they follow the class). Under the whole schema (Phase 1a) add_trigger
# rides here because 28% of cards use it; under the schema split (1b) it joins the triggers family instead, so its
# ~8k-char payload schema can leave the core.
CORE_OPS = ("damage", "block", "apply_status", "add_trigger", "draw", "retain", "gain_energy", "exhaust",
            "heal", "forge", "lose_hp")
# Gateable op rows in canonical order (Phase 0 frequency, most used first; the never-used ones last). An op
# the vocabulary grows that is NOT in this list or in FAMILY_OPS stays in the core until someone measures it.
GATED_OP_ORDER = ("balance_step", "add_card", "discard", "upgrade_card", "scry", "purge_card", "purge",
                  "spread_debuffs", "retrieve_card", "innate", "cost_shift", "corruption", "add_status_card",
                  "ethereal", "gain_max_hp", "graft_card", "transform_card",
                  "sly",  # Phase BB (v56): unmeasured, so it rides the tail like the other rare keywords
                  "exhaust_card", "draw_until",  # Phase BC (v57): the hand ops, likewise unmeasured
                  "held_discount")  # Phase BD (v58)

# ---- Phase 1b: which gate UNIT each schema element belongs to. A unit is a gated op name or a family name. An
# element whose units are all gated moves to the tail (families are "fam:<name>", so the Forge family never
# collides with the `forge` op); anything else (an unlisted field, a rule naming a core op)
# stays in the core, so a schema that grows new fields is never silently cut.
FIELD_UNITS = {
    # `when` + the condition def (~4k chars) deliberately stay CORE: conditions is the weakest-recall family (88%
    # in Phase 0) and the 1b A/B showed that without its schema a gate miss becomes a repair; in 1a the schema
    # alone let the model write a valid gate the prose never showed it.
    "scale": ("fam:scaling",), "tag": ("fam:scaling",),
    "trigger": ("add_trigger",), "once_per_turn": ("add_trigger",), "once_per_combat": ("add_trigger",),
    "effects": ("add_trigger",),
    "orb": ("channel_orb",), "status_name": ("apply_status_custom",), "summon_name": ("summon",),
    "card_id": ("add_card", "transform_card", "graft_card"),
    "pile": ("add_card", "add_status_card", "retrieve_card"),
    "cards": ("discard", "retrieve_card", "upgrade_card", "exhaust_card"),  # Phase BC (v57)
    "pole": ("balance_step",), "card_type": ("cost_shift", "exhaust_card", "draw_until", "add_trigger"),  # Phase BC (v57) / BI (v61)
    "scope": ("cost_shift", "add_trigger"), "count": ("cost_shift",),
    "every_n": ("add_trigger",),  # Phase BI (v61, gap #62): the trigger filters
    "card": ("add_status_card",),
}
DEF_UNITS = {"triggerEffect": ("add_trigger",)}
# One vocabulary table row: `| \`token\` | ...`. Shared by the card gate's op-table split and the blueprint tree.
_ROW_RE = re.compile(r"^\|\s*`([a-z_]+)`\s*\|")
SCHEMA_ADDITIONS_HEADER = ("## Schema additions (for the add-ons above: they EXTEND `$defs.effect` in THE JSON SCHEMA; "
                           "the validator checks the complete schema)\n")


def schema_mode() -> str:
    m = (os.environ.get(SCHEMA_ENV) or "split").strip().lower()
    return m if m in SCHEMA_MODES else "split"


def _inline_json(o) -> str:
    if isinstance(o, dict):
        return ("{ " + ", ".join(f"{json.dumps(k, ensure_ascii=False)}: {_inline_json(v)}" for k, v in o.items())
                + " }") if o else "{}"
    if isinstance(o, list):
        return "[" + ", ".join(_inline_json(x) for x in o) + "]"
    return json.dumps(o, ensure_ascii=False)


def format_json(o, ind: int = 0, width: int = 400) -> str:
    """Pretty JSON close to card.schema.json's own hand layout (short objects inline), so a re-rendered schema
    costs about what the pasted file did."""
    one = _inline_json(o)
    if len(one) + ind <= width or not isinstance(o, (dict, list)) or not o:
        return one
    pad = " " * ind
    if isinstance(o, dict):
        return ("{\n" + ",\n".join(f"{pad}  {json.dumps(k, ensure_ascii=False)}: {format_json(v, ind + 2, width)}"
                                   for k, v in o.items()) + "\n" + pad + "}")
    return "[\n" + ",\n".join(pad + "  " + format_json(x, ind + 2, width) for x in o) + "\n" + pad + "]"


def _branch_units(branch: dict) -> set[str]:
    """The units an allOf rule is about: the op(s) its `if` names plus the units of the fields it tests."""
    cond = branch.get("if") or {}
    props = cond.get("properties") or {}
    units: set[str] = set()
    opspec = props.get("op")
    if isinstance(opspec, dict):
        units |= {opspec["const"]} if "const" in opspec else set(opspec.get("enum") or [])
    fields = set(cond.get("required") or []) | set(props)
    for alt in cond.get("anyOf") or []:
        fields |= set((alt or {}).get("required") or [])
    fields.discard("op")
    for f in fields:
        units |= set(FIELD_UNITS.get(f, (f"field:{f}",)))
    return units or {"field:?"}


# ---- Phase 0 family questions + keyword rules (verbatim from tools/jev_gate_eval.py) ------------------------
FAMILY_Q = {
    "triggers": "Will coding this card need an `add_trigger` ongoing engine: a power/effect that fires every "
                "turn (turn_start / turn_end), fires ONCE after N turns (ripen: 'plant', 'after N turns', "
                "'matures'), or fires reactively whenever an event happens (whenever you play/draw/exhaust/"
                "discard a card, gain Block, lose HP, deal damage, or are attacked)?",
    "conditions": "Will coding this card need a conditional `when` gate that checks combat state before an effect "
                  "fires: e.g. if the target has a status / block, if you have no block, if HP is below half, if "
                  "you hold at least N cards, if it is turn N or later, if you retained this card, if enemies "
                  "number at least N, if the draw pile is empty?",
    "scaling": "Will coding this card need multi-hit (deal X damage N times) or a SCALED amount: an amount "
               "that grows with a counter such as cards in hand, cards retained, cards played this turn, "
               "your Strength, your Forge, orbs, unspent energy, enemy count, or an X-cost?",
    "orbs": "Will coding this card need orb ops (channel an orb, evoke, gain an orb slot: lightning / "
            "frost / dark / a custom orb)?",
    "summons": "Will coding this card need summon ops (summon a minion/companion, make it attack, buff, shield, "
               "heal or sacrifice it)?",
    "custom_status": "Will coding this card need this class's own FORGED custom status (a class-specific named "
                     "stack such as Embers, Rust, Bloom, Chill: not the base statuses Vulnerable / Weak / Poison / "
                     "Strength / Dexterity / Frail / Thorns / Artifact / Plated Armor / Metallicize / Regen)?",
    "forge": "Will coding this card need Forge ops (forge N, spend Forge, summon or empower the signature "
             "blade)?",
}
FAMILY_KW = {
    "triggers": r"whenever|at the (start|end) of (your|each|every) turn|each turn|every turn|after \d+ turns?|"
                r"ripen|matur|\bpower\b|when(ever)? you (play|draw|exhaust|discard|gain block|lose hp|are attacked)|"
                r"thorns|reflex|plant|engine|ongoing|for the rest of (the )?combat"
                # Phase 1b A/B (2026-09-26): card-latent "on-discard fuel" briefs slipped past the Phase 0 rule.
                # Re-measured on the 576 Phase 0 cards: triggers recall 93.9% -> 97.0%, included on 36% (was 32%).
                r"|\bon[- ](discard|exhaust|draw|retain|play|death|hp[- ]lost|block)|"
                r"when (this card is|it is|it.s) (discarded|exhausted|drawn|retained)|(is|gets|are) discarded|"
                r"when discarded|if discarded|fuel",
    "conditions": r"\bif\b|\bunless\b|\bwhile\b|only when|when (you|your|the target|the enemy|an enemy) (have|has|"
                  r"hold|are|is)|below half|at least \d+|no block|has block|retained|held|debuffed|"
                  r"vulnerable target|target (is|has)|intends? to attack",  # Phase BJ (v62): the intent gate
    "scaling": r"\d+ times|twice|thrice|x times|multi[- ]?hit|\bhits?\b|per (card|enemy|orb|stack|turn|"
               r"forge|point)|for each|for every|equal to|scal|grows|plus your|based on|x-cost|\bx\b|"
               r"double your energy|until you have",  # Phase BJ (v62): Double Energy / Expertise read as scaled
    "orbs": r"\borbs?\b|channel|evoke|lightning|frost|\bdark\b|orb slot|focus",
    "summons": r"summon|minion|companion|familiar|ally|creature|beast|spirit|golem|wolf|pet",
    "custom_status": r"stacks? of|counter|custom|class status|\b(apply|gain|give|add)s? \d+ (?!strength|dexterity|"
                     r"block|vulnerable|weak|poison|frail|thorns|artifact|plated|metallicize|regen|temp|damage|"
                     r"energy)[a-z]+",
    "forge": r"forge|blade|anvil|temper|ember|smith",
}
_SECTION_CONTEXT = ("Card briefs for a Slay-the-Spire-like deckbuilder mod. Each card will be coded as "
                    "JSON from a closed effect vocabulary. Answer per card, from its brief line only.")
_OP_CONTEXT = ("Card briefs for a Slay-the-Spire-like deckbuilder mod. Each card will be coded as JSON "
               "from a closed effect vocabulary of named ops. For each card and op: will coding the card "
               "as briefed use that op? Answer from the brief line only.")


def mode() -> str:
    """The gate mode from $BTS_VOCAB_GATE, read at call time. Unknown values mean off (never a surprise gate)."""
    m = (os.environ.get(ENV) or "off").strip().lower()
    return m if m in MODES else "off"


def heuristic(brief_text: str) -> set[str]:
    """Families whose Phase 0 keyword rule fires on the brief."""
    b = (brief_text or "").lower()
    return {f for f, kw in FAMILY_KW.items() if re.search(kw, b)}


# ------------------------------------------------------------------------------------------------ decisions
@dataclass
class Decision:
    """What one card's prompt keeps. `families`/`ops` None = everything (the full prompt)."""
    mode: str
    families: frozenset | None = None
    ops: frozenset | None = None
    jev_ok: bool | None = None       # None = Jev not asked (heuristic mode / full)
    error: str = ""
    jev_cost: float = 0.0
    probs: dict = field(default_factory=dict)

    @property
    def full(self) -> bool:
        return self.families is None and self.ops is None


def _jev_post(key: str, state, questions: dict) -> dict:
    body = json.dumps({"model": JEV_MODEL, "state": state, "questions": questions}).encode()
    req = urllib.request.Request(JEV_ENDPOINT, data=body, method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=JEV_TIMEOUT_S) as r:
        return json.load(r)


def _jev_ask(key: str, state, questions: dict) -> dict:
    """One Decisions request with a single short backoff on 429/529. Raises on anything else."""
    try:
        return _jev_post(key, state, questions)
    except urllib.error.HTTPError as e:
        if e.code not in (429, 529):
            raise
        time.sleep(1.5)
        return _jev_post(key, state, questions)


def _jev_key() -> str:
    from .generator import load_env
    load_env()
    return (os.environ.get("OPENROUTER_API_KEY") or "").strip()


def _report_usage(on_usage, resp: dict) -> float:
    u = resp.get("usage") or {}
    cost = u.get("cost")
    try:
        cost_f = float(cost) if cost is not None and not isinstance(cost, bool) else 0.0
    except (TypeError, ValueError):
        cost_f = 0.0
    if on_usage is not None:
        try:
            # the stable slug, not resp["model"] (a dated build id), so the ledger keeps ONE gate row
            on_usage({"_role": "gate", "_model": JEV_MODEL,
                      "input_tokens": int(u.get("input_tokens", 0) or 0), "output_tokens": 0,
                      **({"cost": cost} if cost is not None else {})})
        except Exception:  # noqa: BLE001 — a telemetry sink must never break a forge
            pass
    return cost_f


def _decide_jev(brief_text: str, fams: tuple[str, ...], ops: tuple[str, ...], op_rows: dict[str, str],
                on_usage) -> tuple[dict[str, float], dict[str, float], float]:
    """Ask Jev the Phase 0 section questions and op questions for ONE card, the two requests in parallel
    (each with its own Phase 0 context string, so the measured behaviour carries over)."""
    key = _jev_key()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    cards = [{"card": 0, "brief": brief_text}]
    sec_q = {f"c0_{f}": {"type": "noul", "instructions": f"Card 0: {FAMILY_Q[f]}"} for f in fams}
    op_q = {f"c0_{op}": {"type": "noul",
                         "instructions": f"Card 0: will it use the op `{op}`? ({op_rows.get(op, '')})"}
            for op in ops}
    jobs = []
    with ThreadPoolExecutor(max_workers=2) as ex:
        if sec_q:
            jobs.append(("sec", ex.submit(_jev_ask, key, {"context": _SECTION_CONTEXT, "cards": cards}, sec_q)))
        if op_q:
            jobs.append(("op", ex.submit(_jev_ask, key, {"context": _OP_CONTEXT, "cards": cards}, op_q)))
        results = {name: fut.result() for name, fut in jobs}
    cost = 0.0
    sec_p, op_p = {}, {}
    for name, resp in results.items():
        cost += _report_usage(on_usage, resp)
        ans = resp.get("answers")
        if not isinstance(ans, dict):
            raise RuntimeError(f"Jev answered without an answers map: {str(resp)[:200]}")
        names = fams if name == "sec" else ops
        target = sec_p if name == "sec" else op_p
        for n in names:
            v = (ans.get(f"c0_{n}") or {}).get("noul")
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise RuntimeError(f"Jev gave no noul for {n}")
            target[n] = float(v)
    return sec_p, op_p, cost


_memo: "OrderedDict[tuple, Decision]" = OrderedDict()
_memo_lock = threading.Lock()
_MEMO_MAX = 512


def _memo_get(key):
    with _memo_lock:
        d = _memo.get(key)
        if d is not None:
            _memo.move_to_end(key)
        return d


def _memo_put(key, d: Decision) -> None:
    with _memo_lock:
        _memo[key] = d
        _memo.move_to_end(key)
        while len(_memo) > _MEMO_MAX:
            _memo.popitem(last=False)


def clear_memo() -> None:
    with _memo_lock:
        _memo.clear()


# ------------------------------------------------------------------------------------------------ the prompt
class GatedPrompt:
    """One card system prompt, parsed once per generator (i.e. once per forge, under the class scope), able to
    render the full cache-safe layout or a per-brief gated one. `core` is the shared prefix of both."""

    def __init__(self, text: str, kinds=None, gate_mode: str = "heuristic", schema: str = "split") -> None:
        if VOCAB_MARK not in text or SCHEMA_MARK not in text:
            raise ValueError("card system prompt has no VOCABULARY/SCHEMA markers to gate on")
        self.mode = gate_mode
        self.schema = schema if schema in SCHEMA_MODES else "split"
        self.kinds = None if kinds is None else frozenset(str(k) for k in kinds)
        # Under the schema split add_trigger joins the triggers family (as Phase 0 measured it), so its payload
        # schema (triggerEffect, ~8k chars) rides the tail with it. Whole-schema mode is exactly Phase 1a.
        self.family_ops = dict(FAMILY_OPS)
        if self.schema == "split":
            self.family_ops["triggers"] = ("add_trigger",)
        self.dropped_ops: set[str] = set()
        head, rest = text.split(VOCAB_MARK, 1)
        vocab, after = rest.split(SCHEMA_MARK, 1)
        pieces = re.split(r"^(?=## )", vocab, flags=re.M)
        owned = self._owned_families()
        core_vocab: list[str] = []
        self.addon_sections: dict[str, str] = {}
        self.op_rows: dict[str, str] = {}        # op -> table row line (gateable rows only)
        self.op_text: dict[str, str] = {}        # op -> row text for Jev questions (every row)
        self.table_head = ""
        for i, sec in enumerate(pieces):
            title = sec.splitlines()[0] if sec.strip() else ""
            if i == 0 and not title.startswith("## "):
                core_vocab.append(sec + CORE_POINTER)
                continue
            if any(title.startswith(d) for d in ALWAYS_DROP):
                continue
            fam = next((f for t, f in SECTION_FAMILY.items() if title.startswith(t)), None)
            if title.startswith(EFFECT_OPS):
                core_vocab.append(self._split_op_table(sec, owned))
            elif fam is None:
                core_vocab.append(sec)
            elif fam in CLASS_FAMILIES and self.kinds is not None:
                if fam in owned:
                    core_vocab.append(sec)   # the class owns it: constant for every card of this forge
                # else: dropped outright (the forge's safety nets drop such cards anyway)
            else:
                self.addon_sections[fam] = sec
        self.gate_families = CARD_FAMILIES if self.kinds is not None else LOOSE_FAMILIES
        self._schema_parts = None
        if self.schema == "split":
            after = self._split_schema(after)
        self.core = head + VOCAB_MARK + "".join(core_vocab).rstrip("\n") + "\n" + SCHEMA_MARK + after
        self.full = self.render(None)

    # ---- Phase 1b: the schema split ----
    def _gated_units(self) -> set[str]:
        return set(self.op_rows) | {f"fam:{f}" for f in self.gate_families if f in self.addon_sections}

    def _classify(self, units) -> str:
        units = set(units)
        if units and units <= self.dropped_ops:
            return "drop"
        gated = self._gated_units()
        if units and units <= (gated | self.dropped_ops):
            return "gated"
        return "core"

    def _split_schema(self, after: str) -> str:
        """Replace the pasted card.schema.json in `after` with its core part; keep the gated parts for render().
        Anything unexpected about the block leaves the schema whole (logged), never a broken prompt."""
        start = after.find("```json\n")
        end = after.find("\n```", start + 8) if start >= 0 else -1
        try:
            schema = json.loads(after[start + 8:end])
            eff = schema["$defs"]["effect"]
            assert isinstance(eff["properties"]["op"]["enum"], list)
        except Exception as e:  # noqa: BLE001
            _log.warning("vocab gate: schema block not splittable (%s) — keeping it whole", e)
            self.schema = "whole"
            return after
        import copy
        core = copy.deepcopy(schema)
        ceff = core["$defs"]["effect"]
        gated = self._gated_units()
        parts = {"ops": [], "segments": [], "props": [], "rules": [], "defs": []}
        # op enum + the op prose, split at each op's own "'op' (" / "'op' takes" lead-in
        enum = list(ceff["properties"]["op"]["enum"])
        ceff["properties"]["op"]["enum"] = [o for o in enum if self._classify({o}) == "core"]
        parts["ops"] = [o for o in enum if self._classify({o}) == "gated"]
        desc = ceff["properties"]["op"].get("description") or ""
        cuts = [(m.start(), m.group(1)) for m in re.finditer(
            r"(?:Phase [A-Z]+ \(v\d+\): )?'([a-z_]+)' (?=\(|takes)", desc) if m.group(1) in enum]
        core_desc, pos = [], 0
        for i, (at, op) in enumerate(cuts):
            if i == 0:
                core_desc.append(desc[:at])
            nxt = cuts[i + 1][0] if i + 1 < len(cuts) else len(desc)
            seg = desc[at:nxt]
            kind = self._classify({op})
            if kind == "core":
                core_desc.append(seg)
            elif kind == "gated":
                parts["segments"].append(({op}, seg))
        if not cuts:
            core_desc.append(desc)
        if desc:
            ceff["properties"]["op"]["description"] = "".join(core_desc).rstrip()
        for k in list(ceff["properties"]):
            if k == "op":
                continue
            units = set(FIELD_UNITS.get(k, (f"field:{k}",)))
            kind = self._classify(units)
            if kind != "core":
                spec = ceff["properties"].pop(k)
                if kind == "gated":
                    parts["props"].append((units & gated, k, spec))
        keep_rules = []
        for b in ceff.get("allOf") or []:
            units = _branch_units(b)
            kind = self._classify(units)
            if kind == "core":
                keep_rules.append(b)
            elif kind == "gated":
                parts["rules"].append((units & gated, b))
        if "allOf" in ceff:
            ceff["allOf"] = keep_rules
        for name, units in DEF_UNITS.items():
            if name not in core["$defs"]:
                continue
            kind = self._classify(units)
            spec = core["$defs"][name]
            self._prune_dropped(spec)
            if kind != "core":
                core["$defs"].pop(name)
                if kind == "gated":
                    parts["defs"].append((set(units) & gated, name, spec))
        self._schema_parts = parts
        return after[:start + 8] + format_json(core) + after[end:]

    def _prune_dropped(self, spec: dict) -> None:
        """Strip a class's unowned kinds out of a def (the trigger payload lists every op and field)."""
        if not self.dropped_ops:
            return
        props = spec.get("properties") or {}
        op = props.get("op")
        if isinstance(op, dict) and isinstance(op.get("enum"), list):
            op["enum"] = [o for o in op["enum"] if o not in self.dropped_ops]
        for k in list(props):
            units = FIELD_UNITS.get(k)
            if units and set(units) <= self.dropped_ops:
                props.pop(k)

    def _schema_additions(self, units: set[str] | None) -> str:
        p = self._schema_parts
        if not p:
            return ""
        inc = (lambda u: True) if units is None else (lambda u: bool(set(u) & units))
        add: dict = {}
        ops = [o for o in p["ops"] if units is None or o in units]
        if ops:
            add["more_op_values"] = ops
        notes = "".join(seg for u, seg in p["segments"] if inc(u)).strip()
        if notes:
            add["notes_on_those_ops"] = notes
        props = {k: spec for u, k, spec in p["props"] if inc(u)}
        if props:
            add["more_effect_fields"] = props
        rules = [b for u, b in p["rules"] if inc(u)]
        if rules:
            add["more_effect_rules"] = rules
        defs = {name: spec for u, name, spec in p["defs"] if inc(u)}
        if defs:
            add["more_defs"] = defs
        if not add:
            return ""
        return SCHEMA_ADDITIONS_HEADER + "```json\n" + format_json(add) + "\n```\n"

    def _owned_families(self) -> set[str]:
        if self.kinds is None:
            return set()
        owned = {KIND_FAMILY[k] for k in self.kinds if k in KIND_FAMILY}
        if len(owned) >= 2:
            owned.add("hybrid")
        return owned

    def _split_op_table(self, sec: str, owned: set[str]) -> str:
        """Keep core rows (and owned class-kind rows) in place; move gateable rows to the add-on table; drop
        rows of class kinds the class does not own."""
        not_owned_ops = set()
        if self.kinds is not None:
            for fam in ("orbs", "custom_status", "summons"):
                if fam not in owned:
                    not_owned_ops |= set(FAMILY_OPS[fam])
        self.dropped_ops = set(not_owned_ops)
        class_ops = set(FAMILY_OPS["orbs"]) | set(FAMILY_OPS["custom_status"]) | set(FAMILY_OPS["summons"])
        gateable = set(GATED_OP_ORDER) | set(FAMILY_OPS["forge"]) | set(self.family_ops.get("triggers", ()))
        if self.kinds is None:
            gateable |= class_ops
        keep, head_lines = [], []
        for line in sec.splitlines():
            m = _ROW_RE.match(line)
            if not m:
                if line.startswith("|") and not self.op_rows and len(head_lines) < 2:
                    head_lines.append(line)
                keep.append(line)
                continue
            op = m.group(1)
            self.op_text[op] = re.sub(r"\s+", " ", line[m.end():]).strip(" |")[:600]
            if op in not_owned_ops:
                continue
            if op in gateable:
                self.op_rows[op] = line
                continue
            keep.append(line)
        self.table_head = "\n".join(head_lines)
        return "\n".join(keep) + ("\n" if sec.endswith("\n") else "")

    def op_order(self) -> list[str]:
        order = list(self.family_ops.get("triggers", ())) + list(GATED_OP_ORDER)
        for fam in ("orbs", "custom_status", "summons", "forge"):
            order += [o for o in FAMILY_OPS[fam] if o not in order]
        return [o for o in order if o in self.op_rows]

    def render(self, decision: Decision | None) -> str:
        fams = None if decision is None else decision.families
        ops = None if decision is None else decision.ops
        order = list(self.gate_families)
        secs = [self.addon_sections[f] for f in order
                if f in self.addon_sections and (fams is None or f in fams)]
        if "hybrid" in self.addon_sections and fams is None:
            secs.append(self.addon_sections["hybrid"])  # only reachable with unknown kinds: full prompt keeps it
        rows = [self.op_rows[o] for o in self.op_order() if ops is None or o in ops]
        units = None if decision is None else {f"fam:{f}" for f in (fams or ())} | set(ops or ())
        additions = self._schema_additions(units)
        if not secs and not rows and not additions:
            return self.core
        tail = ADDON_HEADER + "".join(s if s.endswith("\n") else s + "\n" for s in secs)
        if rows:
            tail += "## Effect ops (continued)\n" + self.table_head + "\n" + "\n".join(rows) + "\n"
        return self.core + tail + additions

    # ---- the per-card decision ----
    def decide(self, brief_text: str, on_usage=None) -> Decision:
        key = (self.mode, self.schema, self.kinds, brief_text, tuple(self.gate_families),
               tuple(sorted(self.op_rows)))
        hit = _memo_get(key)
        if hit is not None:
            return hit
        heur = heuristic(brief_text) & set(self.gate_families)
        if self.mode == "heuristic":
            fams = frozenset(heur)
            ops = self._ops_for(fams, extra=None)
            d = Decision(mode="heuristic", families=fams, ops=ops)
        else:
            try:
                fam_q = tuple(f for f in self.gate_families if f in FAMILY_Q)
                sec_p, op_p, cost = _decide_jev(brief_text, fam_q, tuple(self.op_order()), self.op_text, on_usage)
            except Exception as e:  # noqa: BLE001 — any Jev problem costs tokens, never a card
                _log.warning("vocab gate: Jev failed (%s) — full prompt for this card", e)
                d = Decision(mode="jev", jev_ok=False, error=f"{type(e).__name__}: {e}"[:200])
                return d  # a failure is not memoized: the next card asks again
            fams = frozenset(heur | {f for f, p in sec_p.items() if p >= SECTION_THRESHOLD})
            picked = {o for o, p in op_p.items() if p >= OP_THRESHOLD}
            d = Decision(mode="jev", families=fams, ops=self._ops_for(fams, extra=picked), jev_ok=True,
                         jev_cost=cost, probs={**sec_p, **{f"op:{k}": v for k, v in op_p.items()}})
        _memo_put(key, d)
        return d

    def _ops_for(self, fams: frozenset, extra: set[str] | None) -> frozenset:
        """Op rows to keep: every family op of an included family, plus `extra` (Jev picks); extra None =
        every non-family gateable row (heuristic mode has no per-op signal)."""
        keep: set[str] = set()
        family_ops: set[str] = set()
        for fam, fops in self.family_ops.items():
            family_ops |= set(fops)
            if fam in fams:
                keep |= set(fops)
        if extra is None:
            keep |= {o for o in self.op_rows if o not in family_ops}
        else:
            keep |= set(extra)
        return frozenset(o for o in keep if o in self.op_rows)

    def for_brief(self, brief_text: str, on_usage=None) -> tuple[str, Decision]:
        d = self.decide(brief_text, on_usage=on_usage)
        return (self.full if d.full else self.render(d)), d


def build(system_text: str, scope: dict | None = None) -> GatedPrompt | None:
    """The gate for one card generator, or None when $BTS_VOCAB_GATE is off (or the prompt can't be parsed,
    which is logged and treated as off: an unparseable prompt must not change what the model sees)."""
    m = mode()
    if m == "off":
        return None
    kinds = (scope or {}).get("kinds")
    try:
        return GatedPrompt(system_text, kinds=kinds, gate_mode=m, schema=schema_mode())
    except ValueError as e:
        _log.warning("vocab gate disabled for this generator: %s", e)
        return None


def summary(decision: Decision, gp: GatedPrompt, text: str) -> dict:
    """A small JSON-able record of one gating decision, for the pipeline log and the forge stats."""
    return {"mode": decision.mode, "schema": gp.schema, "full": decision.full, "jev_ok": decision.jev_ok,
            "families": sorted(decision.families) if decision.families is not None else None,
            "ops": sorted(decision.ops) if decision.ops is not None else None,
            "chars": len(text), "full_chars": len(gp.full), "core_chars": len(gp.core),
            "jev_cost": round(decision.jev_cost, 6), "error": decision.error}


# ============================================================================================================
# Phase BH-3 (VOCAB_EXPANSION_6_PLAN §2.2): the vocabulary TREE for the blueprint (design) prompt.
#
# The design prompt used to paste VOCABULARY.md whole. By the time the staged front end writes the blueprint it
# already knows the chosen archetypes' ops and the class kind, so the tree lays the vocabulary out in two parts:
#
#   INDEX  (vocab_index)  one line per token, derived from VOCABULARY.md, identical for every forge -> it sits in
#                         the cached head of the prompt, and a new vocabulary row costs one ~80-char line there;
#   DETAIL (vocab_detail) the FULL rows (+ the prose that gives them meaning) for the tokens this forge selected,
#                         at the END of the system prompt under DETAIL_HEADER.
#
# A token that is only in the index can be asked for: the blueprint may carry `"nominate_ops": [...]`, and the
# front end re-issues the design call ONCE with those rows added to the detail (frontend/builder.py).
# $BTS_BLUEPRINT_VOCAB = tree (default) | full (the whole-file paste, byte-identical to the pre-BH prompt).
# ============================================================================================================
BLUEPRINT_ENV = "BTS_BLUEPRINT_VOCAB"
BLUEPRINT_MODES = ("tree", "full")
INDEX_HEADER = "# VOCABULARY INDEX (every mechanic, one line each; [orb]/[status]/[summon]/[forge] = that kind only)\n"
INDEX_END = "\n# END OF VOCABULARY INDEX\n"
TREE_POINTER = ("The full rules for the mechanics this class selected are under VOCABULARY DETAIL at the end; the "
                "index above names every other one. To use one of those, nominate it: add \"nominate_ops\": "
                "[\"token\", ...] to the blueprint for one more pass with its rules.")
DETAIL_HEADER = ("\n\n# VOCABULARY DETAIL (the full rules for the mechanics this class selected — same rules, same "
                 "closed set as the INDEX above)\n")
NOMINATE_MAX = 8

# Tree families: the card gate's FAMILY_OPS, plus the tokens a family's detail always carries along. Selecting
# any TRIGGER token pulls the whole family (its pulled tokens + its vocabulary section); `forge` is a core op,
# so it is pulled by the forge family but never triggers it.
TREE_FAMILY_PULL = {
    "orbs": FAMILY_OPS["orbs"] + ("focus", "temp_focus", "orbs_match", "orb_count_ge"),
    "custom_status": FAMILY_OPS["custom_status"],
    "summons": FAMILY_OPS["summons"],
    "forge": FAMILY_OPS["forge"] + ("forge", "forged_ge", "on_blade_played"),
}
TREE_FAMILY_TRIGGER = {f: tuple(t for t in toks if t not in CORE_OPS) for f, toks in TREE_FAMILY_PULL.items()}
TREE_TAG = {"orbs": "[orb]", "custom_status": "[status]", "summons": "[summon]", "forge": "[forge]"}
_TEXT_TAGS = (("ORB-CLASS", "[orb]"), ("STATUS-CLASS", "[status]"), ("SUMMON-CLASS", "[summon]"),
              ("FORGE-CLASS", "[forge]"))
# Sections whose tokens get a meaning line in the index; every other section is listed by name only (its prose
# is a class knob / card JSON shape / always in the detail).
_MEANING_SECTIONS = ("## Effect ops", "## Statuses", "## Conditions", "## Structural mechanics", "## Triggers")
# Sections the detail always carries whole (short, universal rules every design needs).
_ALWAYS_DETAIL = ("## Effect order", "## Targeting", "## Card shape", "## Rarity guidance")
_POTION = "## The signature potion"
_TRIGGERS = "## Triggers"
_STRUCTURAL = "## Structural mechanics"
_STATUSES = "## Statuses"
_TOKEN_RE = re.compile(r"`([a-z][a-z0-9_]*)`")          # = frontend.catalog._TOKEN_RE (live_vocab_tokens)
_BULLET_RE = re.compile(r'^\s*-\s+`"?([a-z][a-z0-9_]*)"?`\s*(.*)$')
_MAX_WORDS = 12              # §2.2: "first clause of its meaning, ≤ 12 words"
# §2.3 (a): the index stays <= INDEX_BUDGET chars. ~210 backticked tokens at 12 words each is ~8k, so the clause
# length ADAPTS: vocab_index uses the longest per-clause char cap (from _CLAUSE_CAPS) that fits the budget. A new
# vocabulary row therefore costs one name line and makes every clause a little terser — the index never grows past
# the budget until the names-only floor (~3.5k today) is reached. Raised 6,000 -> 8,500 on 2026-10-04 (Ryan) so the
# clause cap grows back toward the full 12 words (v61: 7,172 chars at the top 72-char cap; the shrink stays as the
# safety net for later rows).
INDEX_BUDGET = 8_500
_CLAUSE_CAPS = tuple(range(72, 15, -2))
_DANGLING = frozenset("a an the of to and or for at by in on with your its that this is are from into as "
                      "per when if it then".split())


def blueprint_mode() -> str:
    """$BTS_BLUEPRINT_VOCAB, read at call time: `tree` (default) or `full`. Unknown values mean tree."""
    m = (os.environ.get(BLUEPRINT_ENV) or "tree").strip().lower()
    return m if m in BLUEPRINT_MODES else "tree"


def _sections(vocab_text: str) -> list[tuple[str, str]]:
    """(title line, whole section text) per `## ` section, in file order; the preamble is dropped."""
    out = []
    for sec in re.split(r"^(?=## )", vocab_text, flags=re.M):
        if sec.startswith("## "):
            out.append((sec.splitlines()[0], sec))
    return out


def _table_rows(sec: str):
    """(token, meaning cell) per table row of a section (indented tables too), in order."""
    ncols = 0
    for line in sec.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            ncols = 0
            continue
        m = _ROW_RE.match(s)
        if not m:
            if ncols == 0:
                ncols = s.count("|") - 1          # the header row fixes the column count (a cell may hold "|x|")
            continue
        cells = s[m.end():].split("|", max(0, ncols - 2))
        yield m.group(1), cells[-1].strip(" |")


def _bullet_rows(sec: str):
    for line in sec.splitlines():
        m = _BULLET_RE.match(line)
        if m:
            yield m.group(1), m.group(2)


def _clause(text: str, max_chars: int = 72) -> str:
    """The first clause of a meaning cell — markdown and parentheticals stripped, at most _MAX_WORDS words and
    `max_chars` chars, cut at a word and never on a dangling article/preposition. A short bold lead that only
    restates the name ("**Forge N** — stoke ...") is skipped; the `amount` / `value` params read as N."""
    s = text.strip()
    lead = re.match(r"^\*\*([^*]+)\*\*", s)
    if lead and len(lead.group(1).split()) <= 3 and len(s) > lead.end() + 12:
        s = s[lead.end():]
    s = re.sub(r"`(?:amount|value)`", "N", s)
    s = s.replace("**", "").replace("`", "").replace('"', "").replace("\\|", "|")
    prev = None
    while prev != s:
        prev, s = s, re.sub(r"\s*\([^()]*\)", "", s)
    s = s.strip(" |—-:")
    parts = [p.split() for p in re.split(r"(?<=[a-z0-9%])\.\s|\s—\s|;\s|:\s", s)]
    words = next((p for p in parts if len(p) >= 2), s.split())[:_MAX_WORDS]
    while len(" ".join(words)) > max_chars and len(words) > 2:
        words = words[:-1]
    while len(words) > 2 and words[-1].lower().strip(",") in _DANGLING:
        words = words[:-1]
    return " ".join(words).rstrip(".,")


def _family_of(title: str) -> str | None:
    return next((f for t, f in SECTION_FAMILY.items() if title.startswith(t)), None)


class _VocabTree:
    """VOCABULARY.md parsed once: its sections, each token's HOME section, and the text its index line uses."""

    def __init__(self, vocab_text: str) -> None:
        self.text = vocab_text
        self.sections = _sections(vocab_text)
        self.home: dict[str, int] = {}              # token -> section index
        self.meaning: dict[str, str] = {}           # token -> meaning text (rows / bullets / trigger parens)
        self.row_text: dict[str, str] = {}          # token -> its own row/bullet text (for the class tags)
        self.index: str | None = None               # vocab_index's rendering, memoized with its clause cap
        self.index_cap = 0
        # BH-3 follow-up: the rows that document a `status` FIELD (apply_status, buff_summon, target_has_status —
        # the schema's if/then `status` requirements) and the ## Statuses rows such a selection pulls along.
        self.status_field: set[str] = set()
        self.status_rows: list[str] = []
        for i, (title, sec) in enumerate(self.sections):
            if title.startswith(_POTION) or title.startswith("## Card shape"):
                continue                            # field tables, not mechanics: listed by name below
            for tok, mean in list(_table_rows(sec)) + list(_bullet_rows(sec)):
                if tok not in self.home:
                    self.home[tok] = i
                    self.meaning[tok] = mean
                    self.row_text[tok] = mean
        for title, sec in self.sections:
            if title.startswith(_STATUSES):
                self.status_rows += [t for t, _m in _table_rows(sec) if t not in self.status_rows]
                continue
            for line in sec.splitlines():
                m = _ROW_RE.match(line.strip())
                if m and "`status`" in line.strip()[m.end():].rsplit("|", 2)[0]:
                    self.status_field.add(m.group(1))
        # every other backticked token: home = the section that mentions it most (the first one on a tie)
        counts: dict[str, list[int]] = {}
        for i, (_t, sec) in enumerate(self.sections):
            for tok in _TOKEN_RE.findall(sec):
                counts.setdefault(tok, [0] * len(self.sections))[i] += 1
        for tok, per in counts.items():
            if tok in self.home:
                continue
            self.home[tok] = max(range(len(per)), key=lambda k: (per[k], -k))
            title, sec = self.sections[self.home[tok]]
            if title.startswith(_TRIGGERS):         # trigger kinds read "`on_hp_lost` (you lose HP ...)"
                m = re.search(r"`" + re.escape(tok) + r"`\s*\(([^)]*)\)", sec)
                if m and len(m.group(1).split()) >= 3:
                    self.meaning[tok] = m.group(1)

    def tokens(self) -> set[str]:
        return set(self.home)

    def tag(self, tok: str) -> str:
        for fam, toks in TREE_FAMILY_PULL.items():
            if tok in toks and tok not in CORE_OPS:
                return TREE_TAG[fam]
        fam = _family_of(self.sections[self.home[tok]][0]) if tok in self.home else None
        if fam in TREE_TAG:
            return TREE_TAG[fam]
        row = self.row_text.get(tok, "")
        return next((t for marker, t in _TEXT_TAGS if marker in row), "")

    def section_tokens(self, i: int) -> list[str]:
        """The tokens whose HOME is section i, in order of first mention."""
        return [t for t in dict.fromkeys(_TOKEN_RE.findall(self.sections[i][1])) if self.home.get(t) == i]


_TREE_CACHE: dict[str, _VocabTree] = {}


def _tree(vocab_text: str) -> _VocabTree:
    t = _TREE_CACHE.get(vocab_text)
    if t is None:
        if len(_TREE_CACHE) >= 4:
            _TREE_CACHE.pop(next(iter(_TREE_CACHE)))
        t = _TREE_CACHE[vocab_text] = _VocabTree(vocab_text)
    return t


def vocab_tokens(vocab_text: str) -> set[str]:
    """Every backticked token of VOCABULARY.md (the set catalog.live_vocab_tokens reads from the same file)."""
    return _tree(vocab_text).tokens()


def vocab_index(vocab_text: str) -> str:
    """The INDEX: one line per mechanic, derived from VOCABULARY.md (never hand-kept), grouped under the file's
    own `## ` headings (the part before any parenthesis). Mechanic sections (ops / statuses / conditions /
    scale sources / triggers) get `` `token` — <first clause of its meaning> [tag] ``; their remaining backticked
    names (parameters, values) and the class-knob sections are listed by name; tokens every forge's DETAIL
    carries are listed as such. Deterministic: the same file always gives the same bytes (so the index rides the
    cached prompt head), and it fits INDEX_BUDGET by using the longest clause cap that does (see _CLAUSE_CAPS)."""
    tree = _tree(vocab_text)
    cached = tree.index
    if cached is None:
        text = ""
        for cap in _CLAUSE_CAPS:
            text = _render_index(tree, cap)
            if len(text) <= INDEX_BUDGET:
                break
        tree.index, tree.index_cap = text, cap
        cached = text
    return cached


def index_clause_cap(vocab_text: str) -> int:
    """The per-clause char cap vocab_index settled on (a reading for the phase tests; it shrinks as rows land)."""
    vocab_index(vocab_text)
    return _tree(vocab_text).index_cap


def _render_index(tree: "_VocabTree", cap: int) -> str:
    # Tokens EVERY forge's detail carries (the core op rows, the Triggers section — add_trigger is a core op —
    # the universal sections, the potion) are listed by name only: their full rules are always at the end.
    always = set(CORE_OPS) | {t for i, (title, _s) in enumerate(tree.sections)
                              if any(title.startswith(p) for p in (_TRIGGERS, _POTION) + _ALWAYS_DETAIL)
                              for t in tree.section_tokens(i)}
    blocks: list[str] = []
    for i, (title, _sec) in enumerate(tree.sections):
        toks = tree.section_tokens(i)
        if not toks:
            continue
        lines: list[str] = []
        detailed: list[str] = []
        listed: list[str] = []
        meaning_sec = any(title.startswith(p) for p in _MEANING_SECTIONS)
        for tok in toks:
            mean = tree.meaning.get(tok) if meaning_sec else None
            if tok in always:
                detailed.append(tok)
            elif mean:
                tag = tree.tag(tok)
                lines.append(f"`{tok}` — {_clause(mean, cap)}" + (f" {tag}" if tag else ""))
            else:
                listed.append(tok)
        if detailed:
            lines.insert(0, "always in DETAIL: " + " ".join(f"`{t}`" for t in detailed))
        if listed:
            tag = TREE_TAG.get(_family_of(title) or "", "")
            lines.append(("also" if lines else "names") + (f" {tag}" if tag else "") + ": "
                         + " ".join(f"`{t}`" for t in listed))
        blocks.append(title.split(" (")[0] + "\n" + "\n".join(lines))
    return INDEX_HEADER + "\n".join(blocks) + INDEX_END


def tree_selection(vocab_text: str, tokens, kinds=()) -> tuple[frozenset, frozenset]:
    """(the closed token set, the active families) for one forge — §2.2 point 2's closure rule: a family is
    active when the class OWNS its kind or any of its trigger tokens is selected, and an active family pulls
    all its tokens; two class-kind families make a hybrid. A selected token whose row documents a `status` field
    (`apply_status`, `buff_summon`, `target_has_status`) pulls every ## Statuses row that carries no class tag
    (the `[orb]` focus rows stay with the orb family; custom statuses stay with theirs). Tokens not in the
    vocabulary are dropped."""
    known = vocab_tokens(vocab_text)
    sel = {str(t) for t in (tokens or ()) if str(t) in known}
    kinds = {kinds} if isinstance(kinds, str) else {str(k) for k in (kinds or ())}
    fams = {KIND_FAMILY[k] for k in kinds if k in KIND_FAMILY}
    for fam, trig in TREE_FAMILY_TRIGGER.items():
        if sel & set(trig):
            fams.add(fam)
    for fam in fams:
        sel |= {t for t in TREE_FAMILY_PULL.get(fam, ()) if t in known}
    tree = _tree(vocab_text)
    if sel & tree.status_field:
        sel |= {t for t in tree.status_rows if not tree.tag(t)}
    if sum(1 for f in ("orbs", "custom_status", "summons") if f in fams) >= 2:
        fams.add("hybrid")
    return frozenset(sel), frozenset(fams)


def vocab_detail(vocab_text: str, tokens, kinds=(), *, keep_potion: bool = True) -> str:
    """The DETAIL block for one forge: the FULL rows for `tokens` (after tree_selection's closure) plus the
    prose that gives them meaning — the non-row text of every table section that contributed a row, the
    class-identity sections (SECTION_FAMILY) of the families the class owns or selected, the whole Triggers
    section when any trigger token is selected (add_trigger is a core op, so in practice always), the ## Statuses
    rows + intro when a `status`-field op is selected (apply_status is core, so in practice always), the whole
    Structural section when any of its tokens (`scale`, a scale source, `hits`, `grow` …) is selected, the short
    universal sections (_ALWAYS_DETAIL), and ALWAYS `## The signature potion` (the blueprint declares it).
    Sections keep the file's order and bytes; only unselected table rows are cut."""
    tree = _tree(vocab_text)
    sel, fams = tree_selection(vocab_text, tokens, kinds)
    out: list[str] = []
    for i, (title, sec) in enumerate(tree.sections):
        fam = _family_of(title)
        if title.startswith(_POTION):
            keep = keep_potion
        elif any(title.startswith(p) for p in _ALWAYS_DETAIL):
            keep = True
        elif fam in CLASS_FAMILIES or fam == "forge":
            keep = fam in fams
        elif title.startswith(_TRIGGERS):           # the trigger-kind "rows" are this section's prose
            keep = "add_trigger" in sel or bool(sel & set(tree.section_tokens(i)))
        elif title.startswith(_STRUCTURAL):         # the scale-source "rows" are this section's bullets
            keep = "scale" in sel or bool(sel & set(tree.section_tokens(i)))
        else:
            rows = [t for t, _m in _table_rows(sec)]
            if not rows:
                keep = True                           # a prose-only section the tree doesn't know: keep it
            elif sel & set(rows):
                lines = [ln for ln in sec.splitlines()
                         if not ((m := _ROW_RE.match(ln.strip())) and m.group(1) not in sel)]
                out.append("\n".join(lines) + ("\n" if sec.endswith("\n") else ""))
                continue
            else:
                keep = False
        if keep:
            out.append(sec)
    body = "".join(s if s.endswith("\n") else s + "\n" for s in out)
    return DETAIL_HEADER + body.rstrip("\n") + "\n"


def detail_row_tokens(detail_text: str) -> set[str]:
    """The tokens whose table ROWS appear in a rendered detail block (tests + the [tree] log)."""
    return {m.group(1) for line in detail_text.splitlines() if (m := _ROW_RE.match(line.strip()))}


def sanitize_nominate_ops(raw, vocab_text: str, *, have=()) -> list[str]:
    """A blueprint's `nominate_ops`: known vocabulary tokens only, not already selected, deduplicated, capped."""
    if not isinstance(raw, (list, tuple)):
        return []
    known = vocab_tokens(vocab_text)
    have = set(have or ())
    out: list[str] = []
    for t in raw:
        t = str(t or "").strip().strip("`").lower()
        if t in known and t not in have and t not in out:
            out.append(t)
    return out[:NOMINATE_MAX]


def tree_blocks(prompt: str) -> tuple[int, int]:
    """(index chars, detail chars) of a tree-mode prompt, measured from the block markers; 0 for a missing one."""
    idx = 0
    a = prompt.find(INDEX_HEADER)
    if a >= 0:
        b = prompt.find(INDEX_END, a)
        idx = (b + len(INDEX_END) - a) if b >= 0 else 0
    d = prompt.rfind(DETAIL_HEADER)
    return idx, (len(prompt) - d if d >= 0 else 0)
