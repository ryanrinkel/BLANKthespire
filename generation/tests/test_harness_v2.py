"""Creative harness v2 (BTS_HARNESS_V2=1) — offline tests for fixes A-D, the temperature bump, and the bench.

Every test toggles the flag with monkeypatch (the flag is read at CALL time, never at import), runs on the
existing fakes (no network, no keys), and asserts the v2 behavior the plan (DEPLOYMENT_PLAN.md §2) prescribes.
The flag-OFF path is covered by the rest of the suite staying green + the explicit off/on contrasts below.
"""
from __future__ import annotations

import json
from collections import Counter

import pytest

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import contract, coverage, harness_v2, ledger  # noqa: E402
from btsgen.class_forge import ClassBrief, _BlueprintContract, _CardFake, _class_context, forge_class  # noqa: E402
from btsgen.frontend import BlueprintBuilder, load_catalog  # noqa: E402
from btsgen.frontend.dossier import Candidate, Dossier, DossierBrief  # noqa: E402
from btsgen.frontend.fakes import _StageFake  # noqa: E402
from btsgen.validator import CardValidator  # noqa: E402


@pytest.fixture
def v2(monkeypatch):
    monkeypatch.setenv("BTS_HARNESS_V2", "1")
    return True


@pytest.fixture
def v1(monkeypatch):
    monkeypatch.delenv("BTS_HARNESS_V2", raising=False)
    return False


def _fake_make_gen(contract_mod, *, max_tokens):
    return _StageFake(contract_mod)


# --------------------------------------------------------------- the flag
def test_flag_read_at_call_time(monkeypatch):
    monkeypatch.delenv("BTS_HARNESS_V2", raising=False)
    assert harness_v2.enabled() is False
    monkeypatch.setenv("BTS_HARNESS_V2", "1")
    assert harness_v2.enabled() is True
    monkeypatch.setenv("BTS_HARNESS_V2", "0")
    assert harness_v2.enabled() is False


# --------------------------------------------------------------- Fix A: the per-card contract
def test_card_system_prompt_v2_drops_ironclad_and_names_real_ops(v2):
    sp = contract.system_prompt()
    assert "Ironclad" not in sp
    clause = harness_v2.compositional_clause()
    assert clause in sp
    live = set(harness_v2.vocabulary_ops()) | set(harness_v2.vocabulary_conditions()) \
        | set(harness_v2.vocabulary_scales()) | set(harness_v2.vocabulary_triggers())
    # every backticked op the clause names exists in the live vocabulary; the prototype-only ops are gone
    import re
    named = set(re.findall(r"`([a-z_]+)`", clause))
    assert named, "clause names ops"
    assert named - {"add_trigger", "scale", "when", "lose_hp", "cost"} <= live, named - live
    for legacy in ("multi", "from_state", "conditional"):
        assert f"`{legacy}`" not in clause
    for real in ("add_trigger", "transform_card", "graft_card", "scry", "balance_step", "purge"):
        assert f"`{real}`" in clause
    # the fixed Strike/Defend/Bash exemplar block is gone from the system prompt
    assert '"id": "strike"' not in sp and '"id": "bash"' not in sp


def test_card_system_prompt_v1_unchanged(v1):
    """ROLLBACK PATH (BTS_HARNESS_V2 unset): production sends the v2 prompt above; this pins the kill-switch."""
    sp = contract.system_prompt()
    assert "Ironclad" in sp and '"id": "strike"' in sp


def test_class_identity_rides_the_system_prompt(v2):
    bp = {"name": "The Tide", "description": "coil then release", "orb_slots": 0,
          "archetypes": [{"id": "retain_hold", "name": "Hold", "description": "keep cards"},
                         {"id": "poison_attrition", "name": "Venom", "description": "stack poison"}],
          "v2_strategy_lines": ["retain_hold + poison_attrition (control): stall then tide -> wins by: poison"]}
    tok = contract.set_class_scope({"identity": harness_v2.identity_block(bp)})
    try:
        sp = contract.system_prompt()
    finally:
        contract.reset_class_scope(tok)
    assert "THE CLASS" in sp and 'Class: "The Tide"' in sp and "retain_hold" in sp
    assert "wins by: poison" in sp
    assert "THE CLASS" not in contract.system_prompt()  # scope reset -> generic v2 prompt


def test_exemplar_pool_is_schema_valid_and_spans_families():
    pool = harness_v2.load_exemplar_pool()
    # W0.8 (VOCAB_GAP_REMEDIATION_PLAN): the pool grew from 46 to ~80 so every archetype has >=2 exemplars and
    # every vocabulary token is demonstrated (tests/test_exemplars.py holds the per-token/per-archetype floors).
    # Wave 5 (v56-v60) added one exemplar per new token -> 127; the ceiling is a sanity bound, not a prompt budget
    # (a brief samples 3), so it moves with the one-exemplar-per-token rule. Wave 6 BL (v64): 150 -> 175 (156 after BL).
    assert 60 <= len(pool) <= 175, len(pool)
    # exemplar_validator() registers every pool id so same-family transform_card/graft_card targets resolve.
    v = harness_v2.exemplar_validator()
    for e in pool:
        r = v.validate(dict(e["card"]))
        assert r.ok, (e["card"]["id"], r.errors)
    cat = load_catalog()
    tagged = {a for e in pool for a in e["archetypes"]}
    assert tagged <= {e.id for e in cat.entries}, tagged - {e.id for e in cat.entries}
    assert len(tagged) >= 28, f"exemplars should span most archetype families, got {len(tagged)}"
    names = [e["card"]["name"] for e in pool]
    assert len(names) == len(set(names))
    metaphors = {m.lower() for e in cat.entries for m in e.metaphors}
    for n in names:
        assert n.lower() not in metaphors


def test_exemplars_rotate_by_archetype_and_never_repeat_a_triple():
    seed = harness_v2.seed_for("a patient duelist")
    dealt: set = set()
    for i in range(8):
        ex = harness_v2.pick_exemplars(["retain_hold", "poison_attrition"], "uncommon", seed, salt=f"card{i}",
                                       avoid_triples=dealt)
        assert len(ex) == 3
        key = frozenset(c["id"] for c in ex)
        assert key not in dealt, "the same three exemplars were dealt twice in one class"
        dealt.add(key)
    # archetype-matched exemplars lead the first deal
    first = harness_v2.pick_exemplars(["retain_hold"], "common", seed)
    assert any("retain_hold" in e["archetypes"] for e in harness_v2.load_exemplar_pool()
               if e["card"]["id"] in {c["id"] for c in first})
    # class-kind exemplars are only dealt to a matching class
    orb_ids = {e["card"]["id"] for e in harness_v2.load_exemplar_pool() if e["needs"] == "orb"}
    normal = harness_v2.pick_exemplars(["orb_channel"], "common", seed, class_kind="normal")
    assert not ({c["id"] for c in normal} & orb_ids)
    orb = harness_v2.pick_exemplars(["orb_channel"], "common", seed, class_kind="orb")
    assert {c["id"] for c in orb} & orb_ids


def test_brief_carries_exemplars_and_used_shapes(v2):
    made = [{"plan": {"role": "pool", "rarity": "common"},
             "card": {"id": "a", "name": "A", "type": "attack", "rarity": "common", "cost": 1, "target": "enemy",
                      "effects": [{"op": "damage", "amount": 6}, {"op": "apply_status", "status": "poison", "amount": 2}]}},
            {"plan": {"role": "basic_attack"}, "card": {"id": "strike", "name": "Strike", "rarity": "basic",
                                                        "effects": [{"op": "damage", "amount": 6}]}}]
    line = harness_v2.used_shapes_line(made)
    assert "apply_status:poison+damage" in line and "SHAPES ALREADY USED" in line
    assert "strike" not in line.lower()
    b = contract.Brief(card_type="attack", rarity="uncommon", theme="t", context="c",
                       exemplars=harness_v2.pick_exemplars(["retain_hold"], "uncommon", 7), used_shapes=line)
    msg = contract.user_brief(b)
    assert "EXEMPLAR CARDS" in msg and "SHAPES ALREADY USED" in msg
    assert "Return only the JSON object." in msg


def test_reprint_gate_downgrades_at_uncommon_under_v2(monkeypatch):
    v = CardValidator()
    inflame_clone = {"id": "hot_blood", "name": "Hot Blood", "type": "power", "rarity": "uncommon", "cost": 1,
                     "target": "self", "source": "llm",
                     "effects": [{"op": "apply_status", "status": "strength", "amount": 2}]}
    # find an authored uncommon/rare skeleton to clone instead if inflame isn't in the mod pool
    corpus = {c["id"]: c for c in v.corpus}
    src = corpus.get("measured_riposte") or next(iter(corpus.values()))
    clone = dict(src)
    clone.update(id="clone_of_it", name="Clone", source="llm", rarity="uncommon")
    clone.pop("character", None)
    monkeypatch.delenv("BTS_HARNESS_V2", raising=False)
    errs_v1, _ = v.reprint_findings(clone)
    assert errs_v1, "v1: an uncommon reprint is a hard error"
    monkeypatch.setenv("BTS_HARNESS_V2", "1")
    errs_v2, warns_v2 = v.reprint_findings(clone)
    assert not errs_v2 and warns_v2 and "harness v2" in warns_v2[0]
    rare = dict(clone, rarity="rare")
    errs_rare, _ = v.reprint_findings(rare)
    assert errs_rare, "rare keeps the hard error under v2"
    del inflame_clone


# --------------------------------------------------------------- Fix B: coverage menus
def test_coverage_menus_shuffle_on_concept_seed_and_drop_generic_head(v2):
    seed_a = harness_v2.seed_for("a plague doctor")
    seed_b = harness_v2.seed_for("a storm gambler")
    ra, wa, xa = coverage._menus(None, seed_a)
    rb, wb, xb = coverage._menus(None, seed_b)
    assert ra == coverage._menus(None, seed_a)[0], "deterministic per seed"
    assert (ra, wa, xa) != (rb, wb, xb), "two concepts get different injection orders"
    for menu in (xa, xb):
        assert menu[0][0] not in ("thorns", "metallicize")
        assert not {k for k, _ in menu} & {"thorns", "metallicize"}
    assert {k for k, _ in ra} == {k for k, _ in coverage.REACTIVE_MENU_V2}


def test_coverage_menus_v1_fixed(v1):
    assert coverage._menus(None, 123) == (coverage.REACTIVE_MENU, coverage.WHEN_MENU, coverage.EXOTIC_MENU)
    assert coverage.EXOTIC_MENU[0][0] == "thorns"  # the v1 head is untouched


def test_coverage_fills_only_from_nominations(v2):
    rep = coverage.PoolReport(pool_size=10, plain_denom=10, plain=0)  # nothing covered: every quota short
    nominated = coverage.sanitize_nominations({"reactive": ["on_exhaust", "bogus", "attacked"],
                                               "when": ["turn_at_least", "no_block"],
                                               "exotic": ["blur", "thorns"]})
    assert nominated == {"reactive": ["on_exhaust", "attacked"], "when": ["turn_at_least", "no_block"],
                         "exotic": ["blur", "thorns"]}
    directives = coverage.plan_repairs(rep, 6, nominated=nominated, seed=1)
    keys = [coverage.directive_key(d) for d in directives]
    allowed = {"on_exhaust", "attacked", "turn_at_least", "no_block", "blur", "thorns", "scale", "nonplain"}
    assert set(keys) <= allowed, keys
    assert keys[:2] == ["on_exhaust", "attacked"]
    assert coverage.sanitize_nominations({"reactive": "nope"}) == {}
    assert coverage.sanitize_nominations(None) == {}


def test_enforce_coverage_records_injections(v2):
    from tests.test_coverage import _pool
    made = _pool()
    log: list[str] = []

    def stub(plan, old, directive):
        return {"id": f"fx_{len(log)}", "name": f"Fx{len(log)}", "type": "skill", "rarity": "common", "cost": 1,
                "target": "self", "effects": [{"op": "add_trigger", "trigger": "on_card_played",
                                               "once_per_turn": True, "effects": [{"op": "block", "amount": 3}]}]}
    summary = coverage.enforce_coverage(made, stub, log.append, seed=harness_v2.seed_for("x"))
    inj = summary["injections"]
    assert inj and all(set(j) >= {"key", "old", "new", "ok"} for j in inj)
    assert all(j["key"] for j in inj)


# --------------------------------------------------------------- Fix C: window, cold set, novelty, metaphors
def test_catalog_window_is_14_to_16_with_four_cold(v2):
    cat = load_catalog()
    usage = Counter()
    hot = [e.id for e in cat.entries][:20]
    for i, aid in enumerate(hot):
        usage[aid] = 20 - i  # the first 20 are "hot"; the rest never used
    clusters = [{"name": "patience", "feeling": "coiled stillness", "concepts": ["held breath", "vigil", "poison"]}]
    seed = harness_v2.seed_for("a patient duelist")
    window, cold_in = cat.window_ids(clusters, seed, usage)
    assert 14 <= len(window) <= 16, len(window)
    assert len(set(window)) == len(window)
    cold = set(cat.cold_set(usage, seed))
    assert not (cold & set(hot[:8])), "the hottest archetypes are never cold"
    assert len([i for i in window if i in cold]) >= 4
    assert set(cold_in) == set(window) & cold
    # cluster matches lead the window
    assert "retain_hold" in window and "poison_attrition" in window
    # deterministic per seed, different across seeds
    assert cat.window_ids(clusters, seed, usage)[0] == window
    assert cat.window_ids(clusters, harness_v2.seed_for("a storm gambler"), usage)[0] != window
    block = cat.prompt_block(window, cold_in)
    assert block.count("COLD:") == len(cold_in) and "\n- " in block


def test_picker_requires_a_cold_archetype_when_fidelity_allows(v2):
    cat = load_catalog()
    b = BlueprintBuilder(_fake_make_gen, catalog=cat, auto=True, gap_log_append=None, triad=True)
    b._cold_ids = {"balance_gauge", "metamorph"}
    hot = Candidate(name="Hot", fantasy="", archetype_ids=["retain_hold", "poison_attrition", "block_bulwark"],
                    archetype_descs=["", "", ""], class_kind="normal", buildable=True)
    cold = Candidate(name="Cold", fantasy="", archetype_ids=["retain_hold", "poison_attrition", "metamorph"],
                     archetype_descs=["", "", ""], class_kind="normal", buildable=True)
    # driver archetypes = retain_hold + poison_attrition + block_bulwark: hot is 100% faithful, cold 67%
    d = Dossier(facets=[{"name": "duel", "role": "driver"}],
                clusters=[{"name": "c1", "facet": "duel"}, {"name": "c2", "facet": "duel"}, {"name": "c3", "facet": "duel"}],
                mappings=[{"cluster": "c1", "archetype_id": "retain_hold"}, {"cluster": "c2", "archetype_id": "poison_attrition"},
                          {"cluster": "c3", "archetype_id": "block_bulwark"}],
                candidates=[hot, cold])
    assert b._pick(d) is cold, "one chosen archetype must come from the cold set when fidelity allows"
    # a cold candidate below the fidelity floor waives the constraint
    far = Candidate(name="Far", fantasy="", archetype_ids=["metamorph", "balance_gauge", "orb_channel"],
                    archetype_descs=["", "", ""], class_kind="normal", buildable=True)
    d2 = Dossier(facets=d.facets, clusters=d.clusters, mappings=d.mappings, candidates=[hot, far])
    assert b._pick(d2) is hot
    # flag off: the cold set is ignored entirely
    import os
    os.environ.pop("BTS_HARNESS_V2", None)
    assert b._pick(d) is hot


def test_novelty_cap_6_under_v2_and_2_otherwise(monkeypatch):
    win = [{"archetype_ids": ["a", "b", "c"]}] * 12
    monkeypatch.delenv("BTS_HARNESS_V2", raising=False)
    assert ledger.novelty_max() == 2.0
    assert abs(ledger.pair_penalty(["a", "b", "c"], win) - 2.0) < 1e-9
    monkeypatch.setenv("BTS_HARNESS_V2", "1")
    assert ledger.novelty_max() == 6.0
    assert abs(ledger.pair_penalty(["a", "b", "c"], win) - 6.0) < 1e-9
    from btsgen.frontend.builder import _FIDELITY_WEIGHT
    assert ledger.novelty_max() < _FIDELITY_WEIGHT


def test_cold_archetypes_rank_by_usage():
    usage = Counter({"a": 5, "b": 3, "c": 0, "d": 0, "e": 1})
    cold = ledger.cold_archetypes(["a", "b", "c", "d", "e"], usage, 3, seed=1)
    assert set(cold) == {"c", "d", "e"}
    assert ledger.archetype_usage([{"archetype_ids": ["a", "a", "b"]}, {"archetype_ids": ["a"]}]) == Counter({"a": 2, "b": 1})


def test_metaphors_stripped_from_blueprint_brief_and_card_context(v2, monkeypatch, tmp_path):
    monkeypatch.setenv("BTS_FORGE_LEDGER", str(tmp_path / "empty.jsonl"))  # no real-ledger recency lines
    cat = load_catalog()
    mets = list(cat.by_id["retain_hold"].metaphors)
    assert "the held breath" in mets
    cand = Candidate(name="The Tide", fantasy="a duelist of the held breath and the drawn bow",
                     archetype_ids=["retain_hold", "poison_attrition"],
                     archetype_descs=["keep cheap cards in hand, coil, then release (patience)", "poison"],
                     core_loop="coiling, then the perfect strike", tension="patience vs venom",
                     strategic_lines=[{"strategy": "control", "line": "hold the held breath", "win_condition": "the drawn bow"},
                                      {"strategy": "aggro", "line": "x", "win_condition": "y"}])
    brief = DossierBrief(candidate=cand, concept="t", metaphors=mets)
    text = _BlueprintContract(mode="dossier", triad=False).user_brief(brief)
    for m in ("held breath", "drawn bow", "perfect strike", "coiling", "patience"):
        assert m not in text.lower(), m
    assert 'Name (use EXACTLY): "The Tide"' in text and "retain_hold" in text
    # flag off: the brief is untouched
    monkeypatch.delenv("BTS_HARNESS_V2", raising=False)
    assert "held breath" in _BlueprintContract(mode="dossier", triad=False).user_brief(brief)
    monkeypatch.setenv("BTS_HARNESS_V2", "1")
    bp = {"name": "The Tide", "description": "the held breath before the strike", "catalog_metaphors": mets,
          "archetypes": [{"id": "retain_hold", "name": "Hold", "description": "coiling until the perfect strike"}]}
    ctx = _class_context(bp)
    assert "held breath" not in ctx.lower() and "coiling" not in ctx.lower() and "perfect strike" not in ctx.lower()
    assert "The Tide" in ctx and "Hold" in ctx
    monkeypatch.delenv("BTS_HARNESS_V2", raising=False)
    assert "held breath" in _class_context(bp).lower()


def test_strip_metaphors_tidies_text():
    out = harness_v2.strip_metaphors("A duelist of the held breath, coiling, then release.", ["the held breath", "coiling"])
    assert out == "A duelist of, then release." or "held breath" not in out
    assert harness_v2.strip_metaphors("keep it", None) == "keep it"


# --------------------------------------------------------------- Fix D: blueprint prompt
# Rule 0.9 (VOCAB_EXPANSION_4_PLAN.md §0) — THE prompt budget, asserted here and nowhere else.
#
# There is ONE prompt, so the ceiling lives in ONE file. A phase test asserts that ITS OWN wording is still in
# the prompt (see test_phase_au / test_phase_av for the idiom); it does NOT pin a size. Phase tests used to keep
# private ceilings measured on their own day, which is the ratchet rule 0.9 exists to stop — test_phase_at and
# test_phase_aw sat red for three phases because the prompt grew past ceilings that had nothing to do with their
# features. Both asserts below bound the WORST CASE, the harness-v2 prompt: v2 is what the droplet runs, and
# Fix D's rotations make it the longer path (by a stable +103 in every commit from Wave 2 through AZ).
#
# REEVALUATED 2026-09-14 at Phase AZ, against the measured growth curve (Wave 2 -> AZ, 15 phases). The single
# 101,000 ceiling was a snapshot, and it hid WHERE the growth comes from:
#
#     v2 prompt   81,126 -> 100,041   +18,915   (+1,261/phase mean, +1,357 median)
#     VOCABULARY  40,256 ->  55,196   +14,940   (+996/phase)  <- 79% of it, pasted verbatim
#     scaffolding 40,870 ->  44,845   + 3,975   (+265/phase, worst single phase +704)
#
# The prompt interpolates VOCABULARY.md whole (one `{vocab}` in `_system_prompt_legacy`), so the total is
# "the vocabulary, plus the scaffolding that frames it". Rule 0.9's "pay for an addition with a removal" can
# only govern the scaffolding — a phase that adds an op MUST document it, and there is nothing to trade the row
# against. Measured against the half it can govern, the discipline is working: +265/phase, several phases at
# zero. So the budget is two terms, both owned here:
BP_SCAFFOLD_BUDGET = 46_000   # HISTORICAL (retired as an assert 2026-10-04): the whole-prompt / all-ops scaffold
                              # ceiling. Replaced by BP_SCAFFOLD_BUDGET_PER_ARCHETYPE on the real (pruned) path.
BP_TOTAL_TRIPWIRE = 140_000   # NOT a per-phase gate — the line at which the shrink conversation is due. Derived
                              # from the actual consumer (below), not from last month's reading: ~35k tokens,
                              # ~25-30% of a 128k context. Raised 120k -> 140k 2026-10-04 (Ryan; 117,639 after BJ):
                              # the real guards are per-archetype <= 80k (b) and the three sample triads <= 90k (b2).
#
# Why the total is a tripwire and not a ceiling: rule 0.9 says the prompt "is tuned for 7B-class local models",
# and that premise is STALE. The blueprint rides the `structure` role, which is glm-5.2 in every shipped mix
# (ollama_roles.example/hybrid/kimi3 + ollama_mix.DEFAULT_ROLE_MAP) and Claude or Kimi K3 on the other paths;
# the small/local model only ever gets `brainstorm`. The blueprint prompt has never gone to a 7B model. What
# survives the premise is real but different: input cost per forge, and attention dilution. Neither justifies a
# hard stop at 100k chars; both justify not letting it double unnoticed.
#
# When the tripwire trips, the answer is a SHRINK, not a raise — and the lever already exists. `_prune_archetype_
# sections` + the W0.5 "ALSO AVAILABLE" one-liner + `coverage.sanitize_nominations({"sections": …})` prune
# class_forge's own archetype sections at blueprint stage and let the model nominate one back. Nothing applies
# that machinery to the VOCABULARY paste, which is the 55k half — until Phase BH-3 built it (below).
#
# REPOINTED 2026-10-01 at Phase BH-3 (VOCAB_EXPANSION_6_PLAN §2.2 / §2.3). The asserts used to measure the
# UNTRIMMED prompt (no selected_ops, no class kind) — a path production never sends. Production (the staged front
# end, harness v2) now sends the VOCABULARY TREE ($BTS_BLUEPRINT_VOCAB=tree, the default): a ~6k INDEX of every
# token in the cached head, plus a per-forge DETAIL block with the full rows of what the chosen archetypes
# selected. So the asserts now run on that real path:
#   (a) the index <= 8,500 chars;                       (b) every archetype alone <= 80,000;
#   (b2) three fixed sample triads (normal / orb / hybrid orb+status) <= 90,000 each;
#   (c) the all-ops path (every archetype's ops, every pool kind, nothing pruned) <= BP_TOTAL_TRIPWIRE;
#   (d) the scaffold = prompt MINUS the index MINUS the detail block (measured from the block markers), for EVERY
#       archetype alone (its pitches pruned as production prunes them) <= BP_SCAFFOLD_BUDGET_PER_ARCHETYPE;
#   (e) the `full` rollback path is byte-identical to the pre-BH prompt (its scaffold half is snapshotted).
# The untrimmed reading survives as an INFORMATIONAL print: it is the `full` rollback path.
#
# DECIDED 2026-10-04 (Ryan): (d) used to be measured on the ALL-OPS path — every archetype's pitch unpruned, a
# prompt no forge sends — so every pitch sentence of every phase was charged to one 46,000 budget (49 chars left
# after BI). Pitches are pruned per forge, so they cost only the forges that select them: (d) now runs on the real
# per-archetype path, the all-ops scaffold is printed (BP_TREE_READING_SCAFFOLD is its recorded reading), and the
# all-ops TOTAL keeps the tripwire (c) as the only synthetic assert. Same day: index 6,000 -> 8,500; tripwire
# 120k -> 140k (the all-ops path is synthetic; (b) and (b2) are the real guards).
# RAISED ONCE for the rest of Wave 6 (Ryan, 2026-10-04, before Phase BL; exhaust_pyre 68,796, hybrid triad 77,647):
# (b) 70,000 -> 80,000 and (b2) 80,000 -> 90,000. Further growth is paid for by shortening, not by raising.
BP_ARCHETYPE_CEILING = 80_000  # (b) the design prompt for ONE archetype's selection
BP_TRIAD_BUDGET = 90_000       # (b2) the design prompt for each of BP_TRIADS (what a real three-archetype forge gets)
BP_SCAFFOLD_BUDGET_PER_ARCHETYPE = 32_000  # (d) 25,345 (exhaust_pyre) at the 2026-10-04 decision
BP_INDEX_CEILING = 8_500       # (a) = gate.INDEX_BUDGET (the index adapts its clause length to stay under it)
# (b2) the fixed sample forges — the same three the Phase BH dry run builds (tests/test_phase_bh.DRY_RUNS).
BP_TRIADS = (
    ("normal", ("retain_hold", "poison_attrition", "block_bulwark"), "normal"),
    ("orb", ("orb_channel", "slot_machine", "tempo_draw"), "orb"),
    ("hybrid", ("orb_channel", "status_signature", "debuff_expose"), ("orb", "status")),
)
BP_READING = 108_282          # the untrimmed v2 path (= the `full` rollback with no selection) — 2026-09-30, Wave 5
BP_READING_V1 = 108_179       # flag-off (informational)
BP_READING_SCAFFOLD = 46_686  # BP_READING minus VOCABULARY.md: the `full` path's scaffold half, snapshotted by (e)
                              # (45,537 at BH-3; +136 Phase BI v61: the TRIGGERS pitch's one-line filter sentence;
                              # +227 Phase BJ v62: the SCALED AMOUNTS history-reads sentence + the two new `when` names
                              # in the conditions pitch; +145 Phase BK v63: the SCALED AMOUNTS hit-count sentence; +340 Phase BL
                              # v64: the PRECISION READS enemy-Strength / Expose / Doom sentence; +301 Phase BM v65: the
                              # PRECISION READS prices / replays sentence)
BP_TREE_READING_SCAFFOLD = 46_323  # INFORMATIONAL reading, not asserted: the scaffold on the all-ops tree path
                                   # (45,789 at BH-3 = 45,537 + the index/detail pointer; 45,951 after BI v61;
                                   # 46,178 after BJ v62; 46,323 after BK v63)


def _tree_prompt(ops, kind, **kw) -> str:
    """The design prompt the staged front end sends under the tree (the caller pins harness v2 + the mode)."""
    return _BlueprintContract(mode="dossier", triad=True, seed=1, selected_ops=set(ops), class_kind=kind,
                              **kw).system_prompt()


def _scaffold_len(bp: str) -> int:
    """The prompt minus the vocabulary it carries — the half rule 0.9 can actually govern. On a tree prompt the
    vocabulary is the INDEX block + the DETAIL block (measured from their markers); on a `full` prompt it is the
    whole VOCABULARY.md paste."""
    from btsgen import gate, paths
    idx, det = gate.tree_blocks(bp)
    if idx or det:
        return len(bp) - idx - det
    return len(bp) - len(paths.VOCABULARY.read_text(encoding="utf-8"))


def _all_ops() -> set:
    ops: set = set()
    for e in load_catalog().entries:
        ops |= set(e.ops)
    return ops


def _triad_prompt(ids, kind) -> str:
    """One of BP_TRIADS' design prompts, built the way the Phase BH dry run (and frontend/builder.py) builds it:
    the union of the three archetypes' ops, the class kind(s), no nominated sections."""
    cat = load_catalog()
    ops: set = set()
    for aid in ids:
        ops |= set(cat.by_id[aid].ops)
    k = kind if isinstance(kind, str) else list(kind)
    return _BlueprintContract(mode="dossier", triad=True, seed=1, selected_ops=ops, class_kind=k,
                              nominated_sections=None).system_prompt()


def rule_0_9_readings() -> dict:
    """Every rule-0.9 reading in one place (the asserts below use the same recipe; tests/test_phase_bh prints
    them). The caller pins BTS_HARNESS_V2=1 and BTS_BLUEPRINT_VOCAB=tree."""
    from btsgen import gate, paths
    vocab = paths.VOCABULARY.read_text(encoding="utf-8")
    per: dict = {}
    per_scaffold: dict = {}
    for e in load_catalog().entries:
        bp = _tree_prompt(e.ops, e.class_kind)
        per[e.id], per_scaffold[e.id] = len(bp), _scaffold_len(bp)
    triads = {name: len(_triad_prompt(ids, kind)) for name, ids, kind in BP_TRIADS}
    allp = _tree_prompt(_all_ops(), ["orb", "status", "summon"])
    untrimmed = _BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()
    worst = max(per, key=per.get)
    worst_sc = max(per_scaffold, key=per_scaffold.get)
    return {"index": len(gate.vocab_index(vocab)), "index_clause_cap": gate.index_clause_cap(vocab),
            "per_archetype": per, "archetype_max": per[worst], "archetype_max_id": worst,
            "per_archetype_scaffold": per_scaffold, "archetype_scaffold_max": per_scaffold[worst_sc],
            "archetype_scaffold_max_id": worst_sc, "triads": triads,
            "all_ops": len(allp), "scaffold": _scaffold_len(allp), "untrimmed": len(untrimmed),
            "untrimmed_scaffold": _scaffold_len(untrimmed), "vocabulary": len(vocab)}


@pytest.fixture
def tree(monkeypatch):
    monkeypatch.setenv("BTS_HARNESS_V2", "1")
    monkeypatch.setenv("BTS_BLUEPRINT_VOCAB", "tree")
    return True


def test_rule_0_9_untrimmed_reading_is_informational(v2):
    """The untrimmed prompt (no selection) is the `full` rollback path now — printed, not asserted."""
    bp = _BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()
    print(f"rule 0.9 (informational): untrimmed v2 blueprint prompt {len(bp):,} chars "
          f"({len(bp) - BP_READING:+,} vs {BP_READING:,}); scaffold {_scaffold_len(bp):,}")


def test_rule_0_9_index_within_budget(tree):
    """(a) the shared index — every forge pays for it, so it has its own ceiling."""
    from btsgen import gate, paths
    idx = gate.vocab_index(paths.VOCABULARY.read_text(encoding="utf-8"))
    assert len(idx) <= BP_INDEX_CEILING, (
        f"the vocabulary index is {len(idx):,} chars, past {BP_INDEX_CEILING:,}: the adaptive clause length hit "
        f"its floor. Shrink the token set or raise the ceiling (and gate.INDEX_BUDGET) on purpose, here.")


def test_rule_0_9_every_archetype_alone_under_the_ceiling(tree):
    """(b) the real path: each archetype's own selection (its ops + its class kind)."""
    over = {}
    for e in load_catalog().entries:
        n = len(_tree_prompt(e.ops, e.class_kind))
        if n > BP_ARCHETYPE_CEILING:
            over[e.id] = n
    assert not over, f"rule 0.9: design prompts past {BP_ARCHETYPE_CEILING:,} chars: {over}"


def test_rule_0_9_sample_triads_under_the_ceiling(tree):
    """(b2) what the model actually receives for a three-archetype forge: a normal, an orb and a hybrid orb+status
    triad (BP_TRIADS, the Phase BH dry-run samples)."""
    sizes = {name: len(_triad_prompt(ids, kind)) for name, ids, kind in BP_TRIADS}
    print("rule 0.9 (b2) triad prompts: " + ", ".join(f"{n} {s:,}" for n, s in sizes.items())
          + f" (ceiling {BP_TRIAD_BUDGET:,})")
    over = {n: s for n, s in sizes.items() if s > BP_TRIAD_BUDGET}
    assert not over, (f"rule 0.9: sample triad design prompts past {BP_TRIAD_BUDGET:,} chars: {over}. Shrink the "
                      f"detail rows or the pitches those archetypes pull; raise the ceiling only on purpose, here.")


def test_rule_0_9_total_prompt_stays_under_the_tripwire(tree):
    """(c) the all-ops path (every archetype selected, every pool kind, nothing pruned) — the only place the
    tripwire (140k since 2026-10-04) survives. Trips long before the model notices, on purpose."""
    bp = _tree_prompt(_all_ops(), ["orb", "status", "summon"])
    assert len(bp) < BP_TOTAL_TRIPWIRE, (
        f"the all-ops blueprint prompt is {len(bp):,} chars, past the {BP_TOTAL_TRIPWIRE:,} tripwire. The answer "
        f"is a SHRINK, not a raise: tighten the tree's selection or the pitches.")


def test_rule_0_9_blueprint_scaffolding_stays_within_budget(tree):
    """(d) the assert with teeth, on the REAL path: for every archetype alone (its ops, its class kind, the pitches
    pruned as production prunes them), everything that is NOT the index or the detail block."""
    per = {}
    for e in load_catalog().entries:
        per[e.id] = _scaffold_len(_tree_prompt(e.ops, e.class_kind))
    worst = max(per, key=per.get)
    print(f"rule 0.9 (d): per-archetype scaffold max {per[worst]:,} ({worst}; "
          f"budget {BP_SCAFFOLD_BUDGET_PER_ARCHETYPE:,})")
    over = {k: n for k, n in per.items() if n > BP_SCAFFOLD_BUDGET_PER_ARCHETYPE}
    assert not over, (
        f"rule 0.9: blueprint scaffolding past the {BP_SCAFFOLD_BUDGET_PER_ARCHETYPE:,} per-archetype ceiling: "
        f"{over}. This is prompt text that is NOT a vocabulary row: keep pitch additions to a sentence, pay for "
        f"shared text with a removal of equal size, or make it a one-line menu pointer. Raise the ceiling only on "
        f"purpose, here.")


def test_rule_0_9_all_ops_scaffold_is_informational(tree):
    """The scaffold on the ALL-OPS path (every pitch unpruned — a prompt no forge sends): printed, not asserted
    (decided 2026-10-04). Its total is still bounded by the 140k tripwire (c)."""
    bp = _tree_prompt(_all_ops(), ["orb", "status", "summon"])
    scaffold = _scaffold_len(bp)
    print(f"rule 0.9 (informational): all-ops scaffold {scaffold:,} chars "
          f"({scaffold - BP_TREE_READING_SCAFFOLD:+,} vs the {BP_TREE_READING_SCAFFOLD:,} recorded reading)")


def test_rule_0_9_full_path_is_byte_identical(v2, monkeypatch):
    """(e) BTS_BLUEPRINT_VOCAB=full is the rollback: exactly the pre-BH prompt (the whole-file paste + the W0.5
    pitch pruning), and its scaffold half is today's snapshot."""
    from btsgen import class_forge as cf
    from btsgen import gate
    monkeypatch.setenv("BTS_BLUEPRINT_VOCAB", "full")
    cat = load_catalog()
    ops = set(cat.by_id["retain_hold"].ops) | set(cat.by_id["orb_channel"].ops)
    c = _BlueprintContract(mode="dossier", triad=True, seed=1, selected_ops=ops, class_kind="orb")
    legacy = cf._prune_archetype_sections(c._system_prompt_legacy(), ops, "orb", set()) + c._triad_addendum()
    assert c.system_prompt() == legacy
    assert gate.tree_blocks(legacy) == (0, 0)
    untrimmed = _BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()
    assert _scaffold_len(untrimmed) == BP_READING_SCAFFOLD, (
        f"the `full` rollback prompt's scaffold is {_scaffold_len(untrimmed):,}, not the {BP_READING_SCAFFOLD:,} "
        f"snapshot: a pitch/rule edit changed it — re-take BP_READING_SCAFFOLD (and BP_TREE_READING_SCAFFOLD) here.")
    # the tree never touches the untrimmed path either (no selected_ops -> the whole-file paste)
    monkeypatch.setenv("BTS_BLUEPRINT_VOCAB", "tree")
    assert _BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt() == untrimmed


def test_rule_0_9_v2_is_the_worst_case(v1):
    """Informational since BH-3: the flag-off prompt never sees the tree (no harness v2, no selection)."""
    from btsgen import gate
    bp_v1 = _BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()
    print(f"rule 0.9 (informational): flag-off blueprint prompt {len(bp_v1):,} chars (v2 untrimmed {BP_READING:,})")
    assert gate.tree_blocks(bp_v1) == (0, 0), "harness v1 must never get the tree"


def test_homage_examples_rotate_per_forge(v2):
    a = _BlueprintContract(mode="dossier", triad=True, seed=harness_v2.seed_for("a plague doctor")).system_prompt()
    b = _BlueprintContract(mode="dossier", triad=True, seed=harness_v2.seed_for("a storm gambler")).system_prompt()
    fixed = "Deflect: 0-cost skill, gain 4 Block; Slice: 0-cost attack, deal 6 damage; Bludgeon"
    assert fixed not in a or fixed not in b
    import re
    pat = r"expresses cleanly in the vocabulary \(e\.g\. (.*?)\) and that flatters"
    ex_a = re.search(pat, a, re.S).group(1)
    ex_b = re.search(pat, b, re.S).group(1)
    assert ex_a != ex_b
    names = {n for n, _ in harness_v2.HOMAGE_POOL}
    assert len(names) == 20
    for ex in (ex_a, ex_b):
        picked = [p.split(":")[0].strip() for p in ex.split("; ")]
        assert len(picked) == 3 and set(picked) <= names
    # same seed -> same examples (deterministic per forge)
    assert _BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt() == \
        _BlueprintContract(mode="dossier", triad=True, seed=1).system_prompt()


def test_blueprint_prompt_prunes_unselected_pitches_and_asks_nominations(v2):
    full = _BlueprintContract(mode="dossier", triad=True).system_prompt()
    cat = load_catalog()
    ops = set(cat.by_id["retain_hold"].ops) | set(cat.by_id["poison_attrition"].ops) | set(cat.by_id["block_bulwark"].ops)
    pruned = _BlueprintContract(mode="dossier", triad=True, seed=1, selected_ops=ops, class_kind="normal").system_prompt()
    assert len(pruned) < len(full) * 0.8, (len(pruned), len(full))
    for heading in ("THE FORGE / SIGNATURE-BLADE ARCHETYPE (", "THE BALANCE ARCHETYPE (", "THE SLOT-MACHINE ARCHETYPE (",
                    "METAMORPH (", "THE SUMMON POOL (", "CORRUPTION ("):
        assert ("\n\n" + heading) not in pruned, heading
        assert ("\n\n" + heading) in full, heading
    for kept in ("TRIGGERS / POWER ENGINES", "SCALED AMOUNTS / RETAIN PAYOFF", "STRATEGIC LINES", "TRIAD OVERRIDE",
                 "CONDITIONAL PAYOFFS", "THE BLUEPRINT FORMAT"):
        assert kept in pruned, kept
    forge_ops = set(cat.by_id["forge_ramp"].ops)
    with_forge = _BlueprintContract(mode="dossier", triad=True, seed=1, selected_ops=forge_ops).system_prompt()
    assert "\n\nTHE FORGE / SIGNATURE-BLADE ARCHETYPE (" in with_forge
    orb = _BlueprintContract(mode="dossier", triad=True, seed=1, selected_ops=set(), class_kind="orb").system_prompt()
    assert "\n\nTHE ORB POOL (" in orb and "\n\nTHE SLOT-MACHINE ARCHETYPE (" in orb
    ask = _BlueprintContract(mode="dossier", triad=True)._pool_ask()
    assert "coverage_nominations" in ask and "on_exhaust" in ask


def test_name_post_pass_rejects_recent_and_top50_names():
    banned = harness_v2.banned_names([{"card_names": ["Septic Wave", "Fine"]}], extra=["Extra One"])
    assert {"septic wave", "fine", "extra one", "held breath", "deflect"} <= banned
    made = [{"plan": {"role": "pool"}, "card": {"id": "a", "name": "Septic Wave", "rarity": "common"}},
            {"plan": {"role": "pool"}, "card": {"id": "b", "name": "Held Breath", "rarity": "uncommon"}},
            {"plan": {"role": "pool"}, "card": {"id": "c", "name": "Fresh Idea", "rarity": "common"}},
            {"plan": {"role": "basic_attack"}, "card": {"id": "s", "name": "Deflect", "rarity": "basic"}}]
    assert harness_v2.name_collisions(made, banned) == [0, 1]
    log: list[str] = []
    calls: list[str] = []

    def rename(card, reason):
        calls.append(card["name"])
        return "Held Breath" if card["name"] == "Septic Wave" else "Second Wind Reborn"  # first answer is banned too
    n = harness_v2.rename_pass(made, set(banned), rename, log.append)
    assert n == 1 and made[1]["card"]["name"] == "Second Wind Reborn" and made[0]["card"]["name"] == "Septic Wave"
    assert calls == ["Septic Wave", "Held Breath"]
    assert any("keeping it" in l for l in log) and any("renamed" in l for l in log)
    # fake-safe: a rename that echoes the same name (the offline fakes) is a logged no-op, never an error
    made2 = [{"plan": {"role": "pool"}, "card": {"id": "a", "name": "Deflect", "rarity": "common"}}]
    assert harness_v2.rename_pass(made2, set(banned), lambda c, r: c["name"], log.append) == 0
    assert harness_v2.rename_pass(made2, set(banned), lambda c, r: (_ for _ in ()).throw(RuntimeError("x")), log.append) == 0


# --------------------------------------------------------------- Fix E (temperature) + end to end + bench
def test_structure_temperature_bump(monkeypatch):
    from btsgen import ollama_mix
    monkeypatch.delenv("BTS_HARNESS_V2", raising=False)
    assert ollama_mix.effective_role_map()["roles"]["structure"]["temperature"] == 0.4
    assert ollama_mix.DEFAULT_ROLE_MAP["roles"]["cards"]["temperature"] == 0.3
    monkeypatch.setenv("BTS_HARNESS_V2", "1")
    rm = ollama_mix.effective_role_map()
    assert rm["roles"]["structure"]["temperature"] == 0.6
    assert rm["roles"]["cards"]["temperature"] == 0.3
    assert ollama_mix.DEFAULT_ROLE_MAP["roles"]["structure"]["temperature"] == 0.4  # never mutated
    custom = {"roles": {"structure": {"model": "m", "temperature": 0.2}}}
    assert ollama_mix.effective_role_map(custom) is custom


def test_forge_class_end_to_end_under_v2(v2, monkeypatch, tmp_path):
    monkeypatch.setenv("BTS_FORGE_LEDGER", str(tmp_path / "ledger.jsonl"))
    cat = load_catalog()
    events: list[str] = []
    b = BlueprintBuilder(_fake_make_gen, catalog=cat, auto=True, gap_log_append=None, triad=True, on_event=events.append)
    res = forge_class(ClassBrief(concept="a plague doctor who trades health for knowledge"), blueprint_gen=None,
                      card_gen_factory=lambda: _CardFake(), relic_gen=None, fake=False, front_end=b)
    assert res.ok and res.bundle is not None, res.log[-3:]
    assert any("catalog window:" in e for e in events), [e for e in events if "window" in e]
    assert any("[creative harness v2]" in l for l in res.log)
    assert any("coverage nominations" in l for l in res.log)
    assert res.stats["cards_attempted"] > 0 and res.stats["cards_first_ok"] == res.stats["cards_attempted"]
    assert isinstance(res.stats["injections"], list)
    assert res.blueprint.get("catalog_metaphors") and "v2_strategy_lines" in res.blueprint
    entries = ledger.read_window()
    assert entries and entries[-1].get("harness") == "v2"
    assert entries[-1].get("card_names") and "injections" in entries[-1]
    # the chosen triad honors the cold rule (or logged why not)
    assert any("cold rule" in e for e in events) or set(res.blueprint["archetype_ids"]) & b._cold_ids


def test_bench_fake_reports_every_metric_row(v2, monkeypatch, tmp_path):
    from btsgen import cli_bench
    with ledger.ledger_scope(tmp_path / "bench.jsonl"):
        report, m = cli_bench.run(cli_bench.CONCEPTS[:2], fake=True)
    for label, _target in cli_bench.METRIC_ROWS:
        assert f"| {label} |" in report, label
    assert m["classes"] == 2 and m["cards"] > 0
    assert "| # | Concept | Class |" in report
    assert "v2 (BTS_HARNESS_V2=1)" in report
    assert len(cli_bench.CONCEPTS) == 12
    out = tmp_path / "HARNESS_BENCH.md"
    # main() re-points the contract, which RELOADS btsgen.paths and resets the quarantine to the real
    # generation/scratch/_class_gen (every run dropped ~20 cards there). conftest already pinned the mod
    # contract + a temp quarantine, so make the re-point a no-op here (BH-1 audit).
    monkeypatch.setattr(cli_bench, "point_btsgen_at_mod_contract", lambda: None)
    rc = cli_bench.main(["--fake", "--concepts", "1", "--quiet", "--out", str(out), "--ledger", str(tmp_path / "l2.jsonl")])
    assert rc == 0 and out.exists() and "| Metric | Value | Target |" in out.read_text(encoding="utf-8")
