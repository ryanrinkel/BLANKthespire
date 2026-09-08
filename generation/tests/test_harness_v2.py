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
    assert 30 <= len(pool) <= 50, len(pool)
    v = CardValidator(extra_statuses={"Razor Focus"}, extra_summons={"Bone Thrall"})
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
    rc = cli_bench.main(["--fake", "--concepts", "1", "--quiet", "--out", str(out), "--ledger", str(tmp_path / "l2.jsonl")])
    assert rc == 0 and out.exists() and "| Metric | Value | Target |" in out.read_text(encoding="utf-8")
