"""Card-stage vocabulary gate (btsgen/gate.py; docs/plans/JEV_EVALUATION_PLAN.md Phase 1a). Offline: Jev is
stubbed at gate._jev_post, the chat endpoint at OpenAICompatGenerator._complete_once."""
from __future__ import annotations

import json
import re

import pytest

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import contract, gate, paths, pipeline  # noqa: E402
from btsgen.generator import OpenAICompatGenerator  # noqa: E402

SIMPLE = contract.Brief(card_type="attack", rarity="common", target_cost=1,
                        theme="deal 8 damage and apply 2 vulnerable")
TRIGGER = contract.Brief(card_type="power", rarity="uncommon", theme="whenever you retain a card, gain 3 block")


@pytest.fixture(autouse=True)
def _v2_and_clean_memo(monkeypatch):
    monkeypatch.setenv("BTS_HARNESS_V2", "1")
    gate.clear_memo()
    yield
    gate.clear_memo()


def _gen(monkeypatch, sent: list):
    gen = OpenAICompatGenerator("https://fake.test/v1", "sk-x", "m1", contract_mod=contract)

    def fake_once(self, payload):
        sent.append(payload["messages"][0]["content"])
        return json.dumps({"id": "x", "name": "X", "type": "attack", "rarity": "common", "cost": 1,
                           "target": "enemy", "effects": [{"op": "damage", "amount": 6}]})

    monkeypatch.setattr(OpenAICompatGenerator, "_complete_once", fake_once)
    return gen


def _schema_ops() -> set[str]:
    ops: set[str] = set()

    def walk(o):
        if isinstance(o, dict):
            op = o.get("op")
            if isinstance(op, dict):
                if "const" in op:
                    ops.add(op["const"])
                ops.update(op.get("enum", []))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(json.loads(paths.CARD_SCHEMA.read_text(encoding="utf-8")))
    return ops


# ------------------------------------------------------------------------------------------ off = untouched
def test_off_is_byte_identical(monkeypatch):
    monkeypatch.delenv("BTS_VOCAB_GATE", raising=False)
    sent: list = []
    gen = _gen(monkeypatch, sent)
    assert gen._gate is None
    gen.first_attempt(SIMPLE)
    assert sent == [contract.system_prompt()]
    monkeypatch.setenv("BTS_VOCAB_GATE", "bogus")
    assert gate.mode() == "off"


# ------------------------------------------------------------------------------------------ cache-safe layout
def test_heuristic_gate_shares_the_core_and_repairs_use_full(monkeypatch):
    monkeypatch.setenv("BTS_VOCAB_GATE", "heuristic")
    sent: list = []
    gen = _gen(monkeypatch, sent)
    gp = gen._gate
    assert gp is not None and gen._system == gp.full
    _, msgs = gen.first_attempt(SIMPLE)
    gen.first_attempt(TRIGGER)
    gen.repair(msgs, "{}", ["bad"])
    simple, trig, repair = sent
    for s in sent:
        assert s.startswith(gp.core)                    # rule 1: one byte-identical prefix for every call
    assert repair == gp.full                            # rule 3: repairs get core + every add-on
    assert len(simple) < len(trig) < len(repair)
    assert "## Triggers" in trig[len(gp.core):] and "## Triggers" not in simple
    assert gen.last_gate["families"] == ["triggers"]


def test_addons_keep_one_canonical_order():
    gp = gate.GatedPrompt(contract.system_prompt(), kinds=[], gate_mode="heuristic")
    tail = gp.full[len(gp.core):]
    pos = [tail.index(t) for t in ("## Triggers", "## Conditions", "## Structural mechanics",
                                   "## Run-persistent Forge", "## Effect ops (continued)")]
    assert pos == sorted(pos)
    rows = re.findall(r"^\|\s*`([a-z_]+)`", tail.split("## Effect ops (continued)", 1)[1], re.M)
    assert rows == gp.op_order()


@pytest.mark.parametrize("schema", ["whole", "split"])
def test_every_schema_op_has_exactly_one_home(schema):
    """With unknown class kinds nothing is dropped: each op's row is in the core OR in the gateable tail."""
    gp = gate.GatedPrompt(contract.system_prompt(), kinds=None, gate_mode="heuristic", schema=schema)
    core_rows = set(re.findall(r"^\|\s*`([a-z_]+)`\s*\|", gp.core, re.M))
    tail_rows = set(gp.op_rows)
    assert not core_rows & tail_rows
    missing = _schema_ops() - core_rows - tail_rows
    assert not missing, f"schema ops with no vocabulary row in the gated prompt: {sorted(missing)}"
    expect_core = set(gate.CORE_OPS) - ({"add_trigger"} if schema == "split" else set())
    assert expect_core <= core_rows


def _has_section(text: str, title: str) -> bool:
    return re.search(r"^" + re.escape(title), text, re.M) is not None


def _has_row(text: str, op: str) -> bool:
    return re.search(r"^\|\s*`" + op + r"`\s*\|", text, re.M) is not None


def test_class_kinds_move_sections_into_the_core_or_out():
    full = contract.system_prompt()
    normal = gate.GatedPrompt(full, kinds=[], gate_mode="heuristic")
    orb = gate.GatedPrompt(full, kinds=["orb"], gate_mode="heuristic")
    hybrid = gate.GatedPrompt(full, kinds=["orb", "status"], gate_mode="heuristic")
    assert not _has_section(normal.full, "## Orbs") and not _has_row(normal.full, "channel_orb")
    assert _has_section(orb.core, "## Orbs") and _has_row(orb.core, "channel_orb")
    assert not _has_section(orb.full, "## Forged statuses")
    assert _has_section(hybrid.core, "## Forged statuses") and _has_section(hybrid.core, "## Hybrid classes")
    for gp in (normal, orb, hybrid):
        assert not _has_section(gp.full, "## The signature potion")  # a class knob, never a card's business


# ------------------------------------------------------------------------------------------ Jev
def _fake_jev(monkeypatch, *, fail=False, calls=None):
    def post(key, state, questions):
        if calls is not None:
            calls.append(len(questions))
        if fail:
            raise TimeoutError("jev down")
        ans = {}
        for q in questions:
            name = q.split("_", 1)[1]
            ans[q] = {"noul": 0.9 if name in ("triggers", "scry") else 0.01}
        return {"model": "typesafe/jev-x", "answers": ans, "usage": {"input_tokens": 100, "cost": 0.00001}}

    monkeypatch.setattr(gate, "_jev_post", post)
    monkeypatch.setattr(gate, "_jev_key", lambda: "k")


def test_jev_union_and_usage_role(monkeypatch):
    _fake_jev(monkeypatch)
    gp = gate.GatedPrompt(contract.system_prompt(), kinds=[], gate_mode="jev", schema="whole")
    usage: list = []
    text, d = gp.for_brief(SIMPLE.describe(), on_usage=usage.append)
    assert d.jev_ok is True
    assert d.families == {"triggers"}                   # Jev said yes; the heuristic found nothing
    assert d.ops == {"scry"}                            # Jev >= 0.05 only; no forge family -> no forge ops
    assert _has_row(text[len(gp.core):], "scry") and not _has_row(text, "add_card")
    assert [u["_role"] for u in usage] == ["gate", "gate"]
    assert all(u["_model"] == gate.JEV_MODEL for u in usage)


def test_jev_failure_sends_the_full_prompt_and_is_not_memoized(monkeypatch):
    calls: list = []
    _fake_jev(monkeypatch, fail=True, calls=calls)
    gp = gate.GatedPrompt(contract.system_prompt(), kinds=[], gate_mode="jev")
    text, d = gp.for_brief(SIMPLE.describe())
    assert text == gp.full and d.full and d.jev_ok is False and "jev down" in d.error
    gp.for_brief(SIMPLE.describe())
    assert len(calls) == 4                              # asked again (2 requests per card), not cached


def test_decisions_are_memoized_across_failover_tiers(monkeypatch):
    calls: list = []
    _fake_jev(monkeypatch, calls=calls)
    full = contract.system_prompt()
    a = gate.GatedPrompt(full, kinds=[], gate_mode="jev")
    b = gate.GatedPrompt(full, kinds=[], gate_mode="jev")   # a second tier's generator, same forge
    assert a.for_brief(SIMPLE.describe())[0] == b.for_brief(SIMPLE.describe())[0]
    assert len(calls) == 2


# ------------------------------------------------------------------------------------------ pipeline + budget
def test_pipeline_records_the_gate(monkeypatch):
    monkeypatch.setenv("BTS_VOCAB_GATE", "heuristic")
    monkeypatch.setenv("BTSGEN_GENERATED_DIR", str(paths.PACKAGE_DIR / "scratch" / "_test_gate_quarantine"))
    sent: list = []
    gen = _gen(monkeypatch, sent)
    res = pipeline.PipelineResult(ok=False)
    gen.first_attempt(SIMPLE)
    pipeline._note_gate(res, gen)
    assert res.gate["mode"] == "heuristic" and not res.gate["full"]
    assert any(line.startswith("vocab gate [heuristic]") for line in res.log)


# Readings (2026-09-25, v2, mod contract): original 112,542 chars; a normal class's gated core ~64.5k, its full
# cache-safe layout ~96.5k, a plain attack brief ~74.4k under the heuristic. The asserts are loose ceilings:
# they catch a gate that silently stops cutting, not a vocabulary row added next phase.
def test_gated_card_prompt_budget(monkeypatch):
    full = contract.system_prompt()
    gp = gate.GatedPrompt(full, kinds=[], gate_mode="heuristic")
    simple, _ = gp.for_brief(SIMPLE.describe())
    assert len(gp.core) < 0.65 * len(full)
    assert len(gp.full) < len(full)
    assert len(simple) < 0.75 * len(full)


def test_hosted_mix_books_jev_calls_as_the_gate_role(monkeypatch):
    """ollama_mix tags every usage dict with its generator's role; the gate's Jev usage must keep role "gate"."""
    from btsgen import ollama_mix
    monkeypatch.setenv("OLLAMA_TEST_FB_KEY", "sk-test")
    seen: list = []
    role_map = {"roles": {"cards": {"model": "m", "api_key": "k", "base_url": "https://o.example"}},
                "fallbacks": [{"api_key": "${OLLAMA_TEST_FB_KEY}"}]}
    _, card_factory, _, _ = ollama_mix.build_ollama_mix(role_map, on_usage=seen.append)
    gen = card_factory()
    tier_gen = gen.tiers[0].gen
    tier_gen._on_usage({"prompt_tokens": 5})
    tier_gen._on_usage({"_role": "gate", "_model": gate.JEV_MODEL, "input_tokens": 7})
    assert [(u["_role"], u["_model"]) for u in seen] == [("cards", "m"), ("gate", gate.JEV_MODEL)]
    assert gen.last_gate is None


# ------------------------------------------------------------------------------------------ Phase 1b: schema split
FENCE = "```json\n"
CLOSE = "\n```"


def _schema_parts(gp):
    core = json.loads(gp.core.split(gate.SCHEMA_MARK, 1)[1].split(FENCE, 1)[1].split(CLOSE, 1)[0])
    tail = gp.full[gp.full.index(gate.SCHEMA_ADDITIONS_HEADER):]
    add = json.loads(tail.split(FENCE, 1)[1].rsplit(CLOSE, 1)[0])
    return core, add


def test_whole_schema_mode_is_phase_1a(monkeypatch):
    monkeypatch.setenv("BTS_VOCAB_GATE", "heuristic")
    monkeypatch.setenv("BTS_VOCAB_GATE_SCHEMA", "whole")
    gp = gate.build(contract.system_prompt(), {"kinds": []})
    assert gp.schema == "whole" and gate.SCHEMA_ADDITIONS_HEADER not in gp.full
    assert paths.CARD_SCHEMA.read_text(encoding="utf-8").strip() in gp.core


@pytest.mark.parametrize("kinds", [None, [], ["orb"], ["summon", "status"]])
def test_schema_split_loses_nothing(kinds):
    """Core schema + every addition (the full prompt) = card.schema.json, minus only the unowned class kinds."""
    full_schema = json.loads(paths.CARD_SCHEMA.read_text(encoding="utf-8"))
    gp = gate.GatedPrompt(contract.system_prompt(), kinds=kinds, gate_mode="heuristic", schema="split")
    assert gp.schema == "split"
    core, add = _schema_parts(gp)
    eff, orig = core["$defs"]["effect"], full_schema["$defs"]["effect"]
    dropped_fields = {k for k, u in gate.FIELD_UNITS.items() if set(u) <= gp.dropped_ops}
    assert set(orig["properties"]) - dropped_fields == set(eff["properties"]) | set(add["more_effect_fields"])
    assert not set(eff["properties"]) & set(add["more_effect_fields"])
    ops = set(eff["properties"]["op"]["enum"]) | set(add["more_op_values"])
    assert ops == set(orig["properties"]["op"]["enum"]) - gp.dropped_ops
    n_rules = len(eff["allOf"]) + len(add.get("more_effect_rules", []))
    assert n_rules <= len(orig["allOf"]) and (kinds is not None or n_rules == len(orig["allOf"]))
    assert set(core["$defs"]) | set(add["more_defs"]) == set(full_schema["$defs"])
    assert core["properties"] == full_schema["properties"]          # card-level fields always whole
    if not gp.dropped_ops:
        notes = eff["properties"]["op"]["description"] + add["notes_on_those_ops"]
        assert len(notes) >= len(orig["properties"]["op"]["description"]) - 2


def test_schema_split_forge_op_stays_core():
    """Family units are namespaced: the Forge FAMILY being gated must not pull the core `forge` op out."""
    gp = gate.GatedPrompt(contract.system_prompt(), kinds=[], gate_mode="heuristic", schema="split")
    core, _ = _schema_parts(gp)
    assert "forge" in core["$defs"]["effect"]["properties"]["op"]["enum"]


def test_schema_split_additions_follow_the_decision(monkeypatch):
    _fake_jev(monkeypatch)   # triggers + scry only
    gp = gate.GatedPrompt(contract.system_prompt(), kinds=[], gate_mode="jev", schema="split")
    text, d = gp.for_brief(SIMPLE.describe())
    assert d.ops == {"add_trigger", "scry"}                       # add_trigger rides the triggers family under 1b
    add = json.loads(text[text.index(gate.SCHEMA_ADDITIONS_HEADER):].split(FENCE, 1)[1].rsplit(CLOSE, 1)[0])
    assert set(add["more_op_values"]) == {"add_trigger", "scry"}
    assert set(add["more_defs"]) == {"triggerEffect"}
    assert "trigger" in add["more_effect_fields"]
    core, _ = _schema_parts(gp)
    assert "when" in core["$defs"]["effect"]["properties"] and "condition" in core["$defs"]   # always core
    assert text.startswith(gp.core) and len(text) < 0.6 * len(contract.system_prompt())


def test_heuristic_catches_card_latent_triggers():
    assert "triggers" in gate.heuristic("theme: On-discard fuel: grants nothing when played; when this card is "
                                        "discarded, deal 4 damage")
