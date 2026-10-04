"""Phase BH-3 — the VOCABULARY TREE for the blueprint (design) prompt + rule 0.9 on the real path
(VOCAB_EXPANSION_6_PLAN §2.2 / §2.3; no vocab bump) — offline, no model calls, no keys.
Run:  uv run python -m tests.test_phase_bh   (from generation/)

Pins: gate.vocab_index is derived from VOCABULARY.md (every live token, class tags, <= 8.5k, deterministic);
gate.vocab_detail carries exactly the selected rows + their prose + the family closure + the signature potion; the
design prompt lays out [head + INDEX + pointer] -> [pruned pitches] -> [VOCABULARY DETAIL] (cache-safe: the head is
identical for every forge); `nominate_ops` re-issues the design call ONCE through the front end with the nominated
rows; BTS_BLUEPRINT_VOCAB=full is byte-identical to the pre-BH prompt; the §2.3 rule-0.9 readings (printed, and
asserted against their ceilings); an offline dry run for a normal / orb / hybrid selection; and the BH-1 audit's
exit bar, printed as a checklist when docs/plans/TEST_AUDIT_2026-10.md exists.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import re
import sys
import tempfile

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import bts1, gate, paths  # noqa: E402
from btsgen import class_forge as cf  # noqa: E402
from btsgen.frontend import BlueprintBuilder, load_catalog  # noqa: E402
from btsgen.frontend import catalog as catalog_mod  # noqa: E402
from btsgen.frontend.fakes import _StageFake  # noqa: E402

_PASS = 0
_FAIL = 0
REPO = paths.VOCABULARY.parents[2]
AUDIT_DOC = REPO / "docs" / "plans" / "TEST_AUDIT_2026-10.md"
_ENV_KEYS = ("BTS_HARNESS_V2", "BTS_BLUEPRINT_VOCAB", "BTS_FORGE_LEDGER")


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


class _env:
    """Pin env vars for a block and restore them after (standalone runs have no monkeypatch)."""

    def __init__(self, **kv) -> None:
        self.kv = kv
        self.old: dict = {}

    def __enter__(self):
        for k, v in self.kv.items():
            self.old[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *a):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _vocab() -> str:
    return paths.VOCABULARY.read_text(encoding="utf-8")


def _contract(ops, kind, **kw) -> cf._BlueprintContract:
    return cf._BlueprintContract(mode="dossier", triad=True, seed=1, selected_ops=set(ops), class_kind=kind, **kw)


def _detail_of(prompt: str) -> str:
    at = prompt.rfind(gate.DETAIL_HEADER)
    return prompt[at:] if at >= 0 else ""


def _rows(vocab: str) -> dict:
    """token -> its exact table-row line, for every table row in VOCABULARY.md (first occurrence wins)."""
    out: dict = {}
    for line in vocab.splitlines():
        m = gate._ROW_RE.match(line.strip())
        if m and m.group(1) not in out:
            out[m.group(1)] = line
    return out


# --------------------------------------------------------------------------------------------- version
def test_version() -> None:
    check(bts1.VOCAB_VERSION >= 60, f"vocab >= 60 (BH has NO vocab bump), got {bts1.VOCAB_VERSION}")


# --------------------------------------------------------------------------------------------- 1. the index
def _t_index() -> None:
    print("vocab_index: derived, complete, tagged, within budget:")
    v = _vocab()
    idx = gate.vocab_index(v)
    check(idx == gate.vocab_index(v), "deterministic (same file -> same bytes)")
    check(idx.startswith(gate.INDEX_HEADER) and idx.endswith(gate.INDEX_END), "framed by INDEX_HEADER / INDEX_END")
    check(len(idx) <= gate.INDEX_BUDGET == 11_000, f"index <= 11,000 chars (got {len(idx):,})")
    live = catalog_mod.live_vocab_tokens()
    missing = sorted(t for t in live if f"`{t}`" not in idx)
    check(bool(live) and not missing, f"every live VOCABULARY token is in the index (missing: {missing})")
    lines = idx.splitlines()
    for tok, tag in (("channel_orb", "[orb]"), ("apply_status_custom", "[status]"), ("summon_attack", "[summon]"),
                     ("spend_forge", "[forge]"), ("orbs_match", "[orb]"), ("focus", "[orb]")):
        line = next((ln for ln in lines if ln.startswith(f"`{tok}` — ")), "")
        check(line.endswith(tag), f"`{tok}` has a meaning line tagged {tag} (got {line!r})")
    for tok in ("hp_below_half", "vulnerable", "cost_shift", "cards_retained"):
        line = next((ln for ln in lines if ln.startswith(f"`{tok}` — ")), "")
        check(bool(line) and not line.endswith("]"), f"`{tok}` has an untagged meaning line (got {line!r})")
    for ln in lines:
        if ln.startswith("`") and " — " in ln:
            words = ln.split(" — ", 1)[1].split()
            if words and words[-1].startswith("["):
                words = words[:-1]
            if len(words) > 12:
                check(False, f"a clause is <= 12 words: {ln!r}")
                break
    heads = [ln for ln in lines if ln.startswith("## ")]
    for h in ("## Effect ops", "## Statuses", "## Conditions", "## Triggers", "## Orbs", "## The signature potion"):
        check(h in heads, f"grouped under the file's own heading {h!r}")
    # never hand-kept: a new row in VOCABULARY.md shows up on its own
    grown = v.replace("| `upgrade_card` |", "| `zz_new_op`    | `amount` (int ≥1) | **Zz** — test the tree picks "
                                             "up a new row. |\n| `upgrade_card` |", 1)
    check("`zz_new_op` — test the tree picks up a new row" in gate.vocab_index(grown),
          "a row added to VOCABULARY.md appears in the index with no other edit")
    print(f"  (reading) index {len(idx):,} chars, clause cap {gate.index_clause_cap(v)} chars, "
          f"{len(gate.vocab_tokens(v))} tokens")


# --------------------------------------------------------------------------------------------- 2. the detail
def _t_detail() -> None:
    print("vocab_detail: the selected rows, their prose, the closure, the potion:")
    v = _vocab()
    rows = _rows(v)
    core = set(gate.CORE_OPS)
    normal = gate.vocab_detail(v, core, ())
    orb = gate.vocab_detail(v, core, ("orb",))
    check(normal.startswith(gate.DETAIL_HEADER), "the detail block opens with DETAIL_HEADER")
    check("\n## Orbs" in orb and rows["channel_orb"] in orb, "an orb-kind detail has ## Orbs + the channel_orb row")
    check("\n## Orbs" not in normal and "channel_orb" not in gate.detail_row_tokens(normal)
          and rows["channel_orb"] not in normal, "a normal-kind detail has neither ## Orbs nor the channel_orb row")
    for kinds in ((), ("orb",), ("status",), ("summon",), ("orb", "status"), ("status", "summon")):
        d = gate.vocab_detail(v, core, kinds)
        check("\n## The signature potion" in d, f"the signature potion section is in the detail for kinds {kinds}")
    check("\n## The signature potion" not in gate.vocab_detail(v, core, (), keep_potion=False), "keep_potion=False drops it")
    check(gate.detail_row_tokens(normal) >= core, "every CORE op row is in a normal detail")
    check(not ({"corruption", "balance_step", "hp_below_half"} & gate.detail_row_tokens(normal))
          and "\n## Conditions" not in normal,
          "unselected rows / sections stay index-only")
    # family closure (§2.2 point 2)
    forge = gate.vocab_detail(v, core | {"spend_forge"}, ())
    check({"forge", "forged_ge", "summon_blade", "blade_empower", "spend_forge"} <= gate.detail_row_tokens(forge)
          and "\n## Run-persistent Forge" in forge, "spend_forge pulls the whole forge family + its section")
    check("\n## Run-persistent Forge" not in normal, "... and `forge` alone (a core op) does not")
    check("\n## Triggers" in normal and "`on_poison_damage`" in normal, "add_trigger (core) pulls the trigger kinds")
    check("\n## Structural mechanics" not in normal and "\n## Structural mechanics" in gate.vocab_detail(v, core | {"scale"}, ()),
          "a `scale` selection pulls the scale-source section")
    # BH-3 follow-up: a `status`-field op (apply_status is core) pulls the ## Statuses rows + intro; the class-tagged
    # rows (focus / temp_focus = [orb]) stay with their family.
    check("\n## Statuses" in normal and "Every status takes an `amount`" in normal
          and {"vulnerable", "weak", "strength", "dexterity", "poison"} <= gate.detail_row_tokens(normal),
          "apply_status pulls the ## Statuses rows + intro prose into the detail")
    check(not ({"focus", "temp_focus"} & gate.detail_row_tokens(normal))
          and {"focus", "temp_focus"} <= gate.detail_row_tokens(orb),
          "the [orb] status rows (focus / temp_focus) stay governed by the orb kind")
    no_st = gate.vocab_detail(v, {"damage", "block"}, ())
    check("\n## Statuses" not in no_st and "vulnerable" not in gate.detail_row_tokens(no_st),
          "no `status`-field op selected -> no ## Statuses section")
    th = gate.vocab_detail(v, {"damage", "target_has_status"}, ())
    check({"vulnerable", "weak"} <= gate.detail_row_tokens(th), "target_has_status (a `status` field) pulls them too")
    check({"vulnerable", "weak"} <= gate.tree_selection(v, {"apply_status"})[0],
          "the closure itself carries the status rows (so nominating `vulnerable` is a no-op)")
    with _env(BTS_HARNESS_V2="1", BTS_BLUEPRINT_VOCAB="tree"):
        e = next(x for x in load_catalog().entries if x.class_kind == "normal" and "apply_status" in x.ops)
        d_bp = _detail_of(_contract(e.ops, "normal").system_prompt())
    check(rows["vulnerable"] in d_bp and rows["weak"] in d_bp,
          f"a normal-kind blueprint ({e.id}, lists apply_status) has the vulnerable + weak rows in its detail")
    summ = gate.vocab_detail(v, core | {"buff_summon"}, ())
    check("\n## Forged summons" in summ and rows["summon"] in summ, "any summon op pulls the summon family")
    hyb = gate.vocab_detail(v, core, ("orb", "summon"))
    check("\n## Hybrid classes" in hyb and "\n## Hybrid classes" not in orb, "two pool kinds add ## Hybrid classes")
    cond = gate.vocab_detail(v, core | {"hp_below_half"}, ())
    check(rows["hp_below_half"] in cond and rows.get("no_block", "\x00") not in cond and "One `when` per effect" in cond,
          "a condition selection carries its row + the Conditions intro, not the other condition rows")
    # every archetype's own ops appear IN FULL in its own detail block
    cat = load_catalog()
    bad = []
    for e in cat.entries:
        d = gate.vocab_detail(v, set(e.ops) | core, (e.class_kind,))
        for op in e.ops:
            if op in rows and rows[op] not in d:
                bad.append(f"{e.id}:{op}(row)")
            elif f"`{op}`" not in d:
                bad.append(f"{e.id}:{op}")
    check(not bad, f"every archetype's own ops are in full in its detail block (missing: {bad[:8]})")


# --------------------------------------------------------------------------------------------- 3. the prompt
def _t_prompt_layout() -> None:
    print("the design prompt: layout, cache-safe head, switch, ALSO-AVAILABLE:")
    cat = load_catalog()
    with _env(BTS_HARNESS_V2="1", BTS_BLUEPRINT_VOCAB="tree"):
        a = _contract(cat.by_id["retain_hold"].ops, "normal").system_prompt()
        b = _contract(cat.by_id["orb_channel"].ops, "orb").system_prompt()
        legacy_untrimmed = cf._BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()
    v = _vocab()
    idx = gate.vocab_index(v)
    for name, sp in (("normal", a), ("orb", b)):
        check(sp.count(gate.INDEX_HEADER) == 1 and sp.count(gate.DETAIL_HEADER) == 1,
              f"{name}: the index and the detail block each appear once")
        check(idx in sp and sp.find(idx) < sp.find(gate.DETAIL_HEADER), f"{name}: the index precedes the detail")
        check(gate.TREE_POINTER in sp, f"{name}: the head carries the index/detail/nominate pointer")
        check(sp.endswith(_detail_of(sp)) and "THE BLUEPRINT FORMAT" not in _detail_of(sp),
              f"{name}: the detail block is the end of the system prompt (pitches, format, triad before it)")
        check(len(v) > 0 and v not in sp, f"{name}: VOCABULARY.md is no longer pasted whole")
    head_end = a.find(gate.TREE_POINTER) + len(gate.TREE_POINTER)
    check(a[:head_end] == b[:head_end], "cache-safe: the head through the index + pointer is identical for two forges")
    check(v in legacy_untrimmed and gate.INDEX_HEADER not in legacy_untrimmed,
          "no selection (legacy one-shot paths) -> the whole-file paste, no tree")
    with _env(BTS_HARNESS_V2="1", BTS_BLUEPRINT_VOCAB="full"):
        c = _contract(cat.by_id["retain_hold"].ops, "normal")
        full = c.system_prompt()
        legacy = cf._prune_archetype_sections(c._system_prompt_legacy(), c.selected_ops, "normal", set()) \
            + c._triad_addendum()
    check(full == legacy, "BTS_BLUEPRINT_VOCAB=full is byte-identical to the pre-BH prompt (paste + pitch pruning)")
    check(not c.tree_active(), "full mode: tree_active() is False")
    # BH-3 follow-up: the ORB CLASSES pitch points at the ## Orbs rows where they actually are
    with _env(BTS_HARNESS_V2="1", BTS_BLUEPRINT_VOCAB="full"):
        full_orb = _contract(cat.by_id["orb_channel"].ops, "orb").system_prompt()
    check(cf.ORBS_REF_TREE in b and "section above" not in b and cf.ORBS_REF_FULL not in b,
          "tree: the orb pitch points at the Orbs rows under VOCABULARY DETAIL, never 'section above'")
    check(b.find(cf.ORBS_REF_TREE) < b.find(gate.DETAIL_HEADER) < b.rfind("\n## Orbs"),
          "tree: ... and the ## Orbs rows really are in the detail block after the pitch")
    check(cf.ORBS_REF_FULL in full_orb and cf.ORBS_REF_TREE not in full_orb
          and 0 <= full_orb.find("\n## Orbs") < full_orb.find(cf.ORBS_REF_FULL),
          "full: the orb pitch keeps the pre-BH 'section above' wording (and the section is above)")
    with _env(BTS_HARNESS_V2=None, BTS_BLUEPRINT_VOCAB="tree"):
        check(not _contract({"damage"}, "normal").tree_active(), "harness v1 never gets the tree")
    with _env(BTS_HARNESS_V2="1", BTS_BLUEPRINT_VOCAB="bogus"):
        check(gate.blueprint_mode() == "tree", "an unknown BTS_BLUEPRINT_VOCAB value means tree (the default)")
    also = [p for p in a.split("\n\n") if p.startswith(cf._ALSO_AVAILABLE_HEAD)]
    check(bool(also) and not any(k in also[0] for k in ("summon_pool", "status_pool", "orbs (")),
          "tree: ALSO-AVAILABLE no longer offers the unowned pool kinds (their rows are index-only)")
    check("nominate_ops" in gate.TREE_POINTER and "VOCABULARY DETAIL" in gate.TREE_POINTER,
          "the pointer names the detail block and the nominate_ops rule")


# --------------------------------------------------------------------------------------------- 4. selection
def _t_selection() -> None:
    print("token selection for the design call (§2.2 point 3):")
    with _env(BTS_HARNESS_V2="1", BTS_BLUEPRINT_VOCAB="tree"):
        c = _contract({"discard", "sly"}, "normal", request_ops={"poison"}, nominated_ops={"corruption"},
                      nominated_sections={"rampage", "summon"})
        toks = c.tree_tokens()
        check({"discard", "sly"} <= toks and set(gate.CORE_OPS) <= toks, "selected_ops + CORE_OPS")
        check("poison" in toks and "corruption" in toks, "explicit-request tokens + nominated ops")
        check("grow" in toks and "summon" in c.tree_kinds(), "a nominated section's tokens + its pool kind")
        d = _detail_of(c.system_prompt())
        check({"discard", "sly", "poison", "corruption", "summon", "summon_attack"} <= gate.detail_row_tokens(d),
              "they all reach the detail block (summon via the family closure)")
        check(c.tree_stats.get("detail_rows") and c.tree_stats.get("index_chars"), "tree_stats is populated")
    from btsgen.frontend import request as request_mod
    cat = load_catalog()
    reqs = request_mod.detect_requests("an orb class of storm gamblers", cat)
    rt = request_mod.requested_tokens(reqs, cat)
    check("channel_orb" in rt and "orbs_match" in rt, f"request.requested_tokens names the asked-for rows ({sorted(rt)[:6]})")


# --------------------------------------------------------------------------------------------- 5. nominate
def _t_nominate_round_trip() -> None:
    print("nominate_ops: one re-issue through the front end, with the nominated row in the detail:")
    made: list = []
    picked: list = []

    class _NominatingFake(_StageFake):
        def _emit(self, brief) -> str:
            out = self._contract.fake_output(brief)
            if isinstance(self._contract, cf._BlueprintContract) and not self._contract.nominated_ops:
                have = self._contract.detail_tokens()
                tok = next(t for t in gate.GATED_OP_ORDER if t not in have)
                picked.append(tok)
                out["nominate_ops"] = ["doom", tok, tok]   # doom is not in the vocabulary (yet): sanitized out
            return json.dumps(out)

    def make_gen(contract_mod, *, max_tokens):
        if isinstance(contract_mod, cf._BlueprintContract):
            made.append(contract_mod)
        return _NominatingFake(contract_mod)

    events: list = []
    log_lines: list = []

    class _H(logging.Handler):
        def emit(self, record):
            log_lines.append(record.getMessage())

    h = _H(level=logging.INFO)
    lg = logging.getLogger("btsgen.tree")
    old_level = lg.level
    lg.addHandler(h)
    lg.setLevel(logging.INFO)
    try:
        with tempfile.TemporaryDirectory() as td, \
                _env(BTS_HARNESS_V2="1", BTS_BLUEPRINT_VOCAB="tree", BTS_FORGE_LEDGER=str(pathlib.Path(td) / "l.jsonl")):
            b = BlueprintBuilder(make_gen, catalog=load_catalog(), auto=True, gap_log_append=None, triad=True,
                                 on_event=events.append)
            bp = b.build(cf.ClassBrief(concept="a lighthouse keeper who hoards storms"))
    finally:
        lg.removeHandler(h)
        lg.setLevel(old_level)
    check(len(made) == 2, f"the design call ran twice: the first pass + ONE re-issue (got {len(made)})")
    if len(made) == 2 and picked:
        tok = picked[0]
        first, second = made
        with _env(BTS_HARNESS_V2="1", BTS_BLUEPRINT_VOCAB="tree"):
            d1, d2 = _detail_of(first.system_prompt()), _detail_of(second.system_prompt())
        check(bool(d1) and tok not in gate.detail_row_tokens(d1), f"pass 1 had no `{tok}` row")
        check(second.nominated_ops == {tok}, f"pass 2 carries exactly the sanitized nomination (got {second.nominated_ops})")
        check(tok in gate.detail_row_tokens(d2), f"pass 2's detail has the `{tok}` row")
        check(bp.get("tree_nominated") == [tok] and "nominate_ops" not in bp,
              "the blueprint records tree_nominated and drops nominate_ops")
    check(any("[tree] nominated" in e for e in events), "the forge log names the nomination ([tree] nominated ...)")
    check(sum("[tree] blueprint prompt" in e for e in events) == 2, "a [tree] line per tree-mode prompt build (2)")
    check(any(m.startswith("[tree] nominated") for m in log_lines), "logger btsgen.tree: [tree] nominated ...")
    check(any(m.startswith("[tree] blueprint prompt") for m in log_lines), "logger btsgen.tree: [tree] prompt line")


# --------------------------------------------------------------------------------------------- 6. rule 0.9
def _t_budget() -> None:
    print("rule 0.9 on the real path (§2.3) — readings:")
    from tests.test_harness_v2 import (BP_ARCHETYPE_CEILING, BP_INDEX_CEILING, BP_READING_SCAFFOLD,
                                       BP_SCAFFOLD_BUDGET_PER_ARCHETYPE, BP_TOTAL_TRIPWIRE, BP_TRIAD_BUDGET,
                                       BP_TREE_READING_SCAFFOLD, rule_0_9_readings)
    with _env(BTS_HARNESS_V2="1", BTS_BLUEPRINT_VOCAB="tree"):
        r = rule_0_9_readings()
    print(f"  (reading) index                  {r['index']:>8,}  (ceiling {BP_INDEX_CEILING:,}; clause cap "
          f"{r['index_clause_cap']} chars)")
    print(f"  (reading) per-archetype max      {r['archetype_max']:>8,}  ({r['archetype_max_id']}; ceiling "
          f"{BP_ARCHETYPE_CEILING:,})")
    print(f"  (reading) per-archetype scaffold {r['archetype_scaffold_max']:>8,}  "
          f"({r['archetype_scaffold_max_id']}; budget {BP_SCAFFOLD_BUDGET_PER_ARCHETYPE:,})")
    for name, n in r["triads"].items():
        print(f"  (reading) triad {name:<16} {n:>8,}  (ceiling {BP_TRIAD_BUDGET:,})")
    print(f"  (reading) all-ops path           {r['all_ops']:>8,}  (tripwire {BP_TOTAL_TRIPWIRE:,})")
    print(f"  (reading) scaffold (all-ops)     {r['scaffold']:>8,}  (informational; recorded "
          f"{BP_TREE_READING_SCAFFOLD:,})")
    print(f"  (reading) full path (untrimmed)  {r['untrimmed']:>8,}  (scaffold {r['untrimmed_scaffold']:,}; "
          f"VOCABULARY.md {r['vocabulary']:,})")
    check(r["index"] <= BP_INDEX_CEILING, "(a) index within its ceiling")
    check(r["archetype_max"] <= BP_ARCHETYPE_CEILING, "(b) every archetype alone within its ceiling")
    check(all(n <= BP_TRIAD_BUDGET for n in r["triads"].values()), "(b2) the sample triads within their ceiling")
    check(r["all_ops"] < BP_TOTAL_TRIPWIRE, "(c) the all-ops path under the tripwire")
    check(r["archetype_scaffold_max"] <= BP_SCAFFOLD_BUDGET_PER_ARCHETYPE,
          "(d) every archetype's scaffold within budget")
    check(r["untrimmed_scaffold"] == BP_READING_SCAFFOLD, "(e) the full path's scaffold is the pre-BH snapshot")


# --------------------------------------------------------------------------------------------- 7. dry run
DRY_RUNS = (
    ("normal", ["retain_hold", "poison_attrition", "block_bulwark"], "normal"),
    ("orb", ["orb_channel", "slot_machine", "tempo_draw"], "orb"),
    ("hybrid", ["orb_channel", "status_signature", "debuff_expose"], ["orb", "status"]),
)


def dry_run() -> dict:
    """The offline end-to-end check (BH-3 item 9): build the design prompt exactly as frontend/builder.py does
    for a normal, an orb and a hybrid triad (no model call), and confirm the detail holds exactly the selected
    rows, the index is present once, and the [tree] log line fires. Returns {name: prompt chars}."""
    cat = load_catalog()
    v = _vocab()
    rows = set(_rows(v))
    sizes = {}
    log_lines: list = []

    class _H(logging.Handler):
        def emit(self, record):
            log_lines.append(record.getMessage())

    h = _H(level=logging.INFO)
    lg = logging.getLogger("btsgen.tree")
    old_level = lg.level
    lg.addHandler(h)
    lg.setLevel(logging.INFO)
    try:
        with _env(BTS_HARNESS_V2="1", BTS_BLUEPRINT_VOCAB="tree"):
            for name, ids, kind in DRY_RUNS:
                ops: set = set()
                for aid in ids:
                    ops |= set(cat.by_id[aid].ops)
                before = len(log_lines)
                c = cf._BlueprintContract(mode="dossier", triad=True, seed=1, selected_ops=ops, class_kind=kind,
                                          nominated_sections=None)
                sp = c.system_prompt()
                detail = _detail_of(sp)
                want, _fams = gate.tree_selection(v, c.tree_tokens(), c.tree_kinds())
                got = gate.detail_row_tokens(detail)
                # every selected token that has a table row is in the detail; and no op row beyond the selection
                # (the detail's other rows are the always-on Targeting / potion field tables)
                missing = sorted((want & rows) - got)
                extra = sorted((got - want) & set(_op_rows(v)))
                check(not missing, f"dry run {name}: every selected row is in the detail (missing {missing})")
                check(not extra, f"dry run {name}: no unselected op row in the detail (extra {extra})")
                check(sp.count(gate.INDEX_HEADER) == 1, f"dry run {name}: the index is present once")
                fired = [m for m in log_lines[before:] if m.startswith("[tree] blueprint prompt")]
                check(len(fired) == 1, f"dry run {name}: the [tree] log line fired once")
                sizes[name] = len(sp)
                idx, det = gate.tree_blocks(sp)
                print(f"  (dry run) {name:6s} {'+'.join(ids)} kind={kind}: prompt {len(sp):,} chars "
                      f"(index {idx:,}, detail {det:,}, {len(got)} rows)")
                if fired:
                    print(f"            {fired[0][:150]}...")
    finally:
        lg.removeHandler(h)
        lg.setLevel(old_level)
    return sizes


def _op_rows(v: str) -> list:
    sec = next(s for t, s in gate._sections(v) if t.startswith("## Effect ops"))
    return [t for t, _m in gate._table_rows(sec)]


def _t_dry_run() -> None:
    print("offline dry run — normal / orb / hybrid (BTS_BLUEPRINT_VOCAB=tree):")
    dry_run()


# --------------------------------------------------------------------------------------------- 8. BH-1 hook
def audit_exit_bar() -> list:
    """BH-1's exit bar as a checklist (Phase BH 'Test' line): the bullets under `## Exit bar` in
    docs/plans/TEST_AUDIT_2026-10.md (written by the BH-1 audit), printed; nothing asserted here."""
    print("BH-1 test audit — exit bar:")
    if not AUDIT_DOC.exists():
        print("  audit doc not present")
        return []
    text = AUDIT_DOC.read_text(encoding="utf-8")
    m = re.search(r"^## Exit bar\s*$(.*?)(?=^## |\Z)", text, flags=re.M | re.S)
    bullets = [ln.strip() for ln in (m.group(1) if m else "").splitlines() if re.match(r"\s*[-*] ", ln)]
    if not bullets:
        print("  (the audit doc has no '## Exit bar' bullets yet)")
    for b in bullets:
        print(f"  {b}")
    return bullets


def main() -> int:
    test_version()
    _t_index()
    _t_detail()
    _t_prompt_layout()
    _t_selection()
    _t_nominate_round_trip()
    _t_budget()
    _t_dry_run()
    audit_exit_bar()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


def test_phase_bh_all() -> None:
    global _PASS, _FAIL
    _PASS = _FAIL = 0
    assert main() == 0, f"{_FAIL} Phase BH check(s) failed - see the FAIL lines above"


if __name__ == "__main__":
    sys.exit(main())
