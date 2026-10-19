"""Jev Phase 2 quality slots (docs/plans/JEV_EVALUATION_PLAN.md 3b): the shared client (btsgen/jev.py), the
"nominate" slot (coverage.sanitize_nominations + BlueprintBuilder._snap_featured) and the "vocab" slot
(class_forge.triage_vocab_misses). Offline: the Decisions endpoint is stubbed at jev.post."""
from __future__ import annotations

import re

import pytest

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import class_forge, coverage, featured, jev  # noqa: E402
from btsgen.frontend.builder import BlueprintBuilder  # noqa: E402
from btsgen.frontend.dossier import Dossier  # noqa: E402

_TICK = re.compile(r"`([^`]+)`")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    jev.clear_memo()
    monkeypatch.setenv("BTS_JEV_SLOTS", "all")
    monkeypatch.setattr(jev, "key", lambda: "k")
    yield
    jev.clear_memo()


def _fake(monkeypatch, table: dict, *, calls=None, fail=False, shape="documented"):
    """Answer each choice question from `table`: backticked token in the instructions -> (best, p)."""
    def post(key, state, questions):
        if calls is not None:
            calls.append({"state": state, "questions": questions})
        if fail:
            raise TimeoutError("jev down")
        ans = {}
        for name, q in questions.items():
            tok = _TICK.search(q["instructions"]).group(1)
            opts = list(q["criteria"])
            best, p = table.get(tok, (opts[-1], 0.95))
            probs = {o: (p if o == best else (1 - p) / (len(opts) - 1)) for o in opts}
            ans[name] = ({"type": "choice", "choice": best, "probabilities": probs, "confidence": p}
                         if shape == "documented" else probs)
        return {"answers": ans, "usage": {"input_tokens": 50, "cost": 0.000002}}
    monkeypatch.setattr(jev, "post", post)


# ------------------------------------------------------------------------------------------ the client
def test_slots_env(monkeypatch):
    monkeypatch.setenv("BTS_JEV_SLOTS", "off")
    assert jev.slots_enabled() == frozenset()
    monkeypatch.setenv("BTS_JEV_SLOTS", "all")
    assert jev.slots_enabled() == frozenset(jev.SLOTS)
    monkeypatch.setenv("BTS_JEV_SLOTS", " nominate , bogus,VOCAB")
    assert jev.slots_enabled() == {"nominate", "vocab"}
    assert jev.enabled("vocab") and not jev.enabled("qa")


def test_choice_usage_role_and_memo(monkeypatch):
    calls, usage = [], []
    _fake(monkeypatch, {"x": ("b", 0.7)}, calls=calls)
    got = jev.choice("relic", {"s": 1}, ["a", "b"], "pick for `x`", on_usage=usage.append)
    assert got == ("b", 0.7)
    assert calls[0]["questions"]["q"]["criteria"].keys() == {"a", "b", "none_of_these"}
    assert usage == [{"_role": "jev:relic", "_model": jev.JEV_MODEL, "input_tokens": 50, "output_tokens": 0,
                      "cost": 0.000002}]
    assert jev.choice("relic", {"s": 1}, ["a", "b"], "pick for `x`", on_usage=usage.append) == ("b", 0.7)
    assert len(calls) == 1 and len(usage) == 1          # memoized: not re-asked, not re-billed


def test_choice_parses_a_bare_probability_map(monkeypatch):
    _fake(monkeypatch, {"x": ("a", 0.66)}, shape="bare")
    best, p = jev.choice("relic", "s", ["a", "b"], "pick for `x`")
    assert best == "a" and p == pytest.approx(0.66)


def test_failures_return_none(monkeypatch):
    _fake(monkeypatch, {}, fail=True)
    assert jev.choice("relic", "s", ["a", "b"], "`x`") is None
    assert jev.nouls("qa", "s", {"n": "`x`?"}) is None
    monkeypatch.setattr(jev, "key", lambda: "")
    assert jev.ask("qa", "s", {"n": {"type": "noul", "instructions": "?"}}) is None
    monkeypatch.setenv("BTS_JEV_SLOTS", "vocab")
    assert jev.ask("qa", "s", {"n": {"type": "noul", "instructions": "?"}}) is None


def test_too_many_options_is_not_asked(monkeypatch):
    calls = []
    _fake(monkeypatch, {}, calls=calls)
    assert jev.choice("relic", "s", [f"o{i}" for i in range(255)], "`x`") is None
    assert calls == []


# ------------------------------------------------------------------------------------------ slot: nominate
RAW = {"reactive": ["on_exhasut", "attacked", "zzz_nonsense", "on_hp_lsot"], "keyword": ["retian", "innate"]}
PLAIN = {"reactive": ["attacked"], "keyword": ["innate"]}


def test_nominations_snap_at_threshold(monkeypatch):
    calls, lines, usage = [], [], []
    _fake(monkeypatch, {"on_exhasut": ("on_exhaust", 0.81), "zzz_nonsense": ("none_of_these", 0.9),
                        "on_hp_lsot": ("on_hp_lost", 0.5), "retian": ("retain", 0.95)}, calls=calls)
    out = coverage.sanitize_nominations(RAW, on_usage=usage.append, log=lines.append)
    assert out == {"reactive": ["on_exhaust", "attacked"], "keyword": ["retain", "innate"]}
    assert len(calls) == 1 and len(calls[0]["questions"]) == 4      # ONE batched request
    assert "coverage: snapped nomination `on_exhasut` -> `on_exhaust` (reactive, p=0.81)" in lines
    assert len(lines) == 2 and usage[0]["_role"] == "jev:nominate"


def test_nominations_dedupe_and_cap(monkeypatch):
    _fake(monkeypatch, {"atacked": ("attacked", 0.9), "on_blok": ("on_block_gained", 0.9),
                        "on_drawn": ("on_card_drawn", 0.9)})
    raw = {"reactive": ["attacked", "atacked", "on_blok", "on_exhaust", "on_drawn"]}
    assert coverage.sanitize_nominations(raw) == {"reactive": ["attacked", "on_block_gained", "on_exhaust"]}


@pytest.mark.parametrize("mode", ["off", "error"])
def test_nominations_unchanged_without_jev(monkeypatch, mode):
    if mode == "off":
        monkeypatch.setenv("BTS_JEV_SLOTS", "off")
        _fake(monkeypatch, {"on_exhasut": ("on_exhaust", 0.99)})
    else:
        _fake(monkeypatch, {}, fail=True)
    assert coverage.sanitize_nominations(RAW, log=print) == PLAIN


def test_known_nominations_never_call_jev(monkeypatch):
    calls = []
    _fake(monkeypatch, {}, calls=calls)
    assert coverage.sanitize_nominations(PLAIN) == PLAIN and calls == []


class _Brief:
    featured: list = []


def test_builder_snaps_featured_resonance(monkeypatch):
    real = featured.FEATURED_MENU[0].id
    _fake(monkeypatch, {"reactive_playd": (real, 0.88), "nonsense_mech": ("none_of_these", 0.9)})
    lines = []
    b = BlueprintBuilder(lambda *a, **k: None, catalog=None, on_event=lines.append, triad=False)
    brief, d = _Brief(), Dossier(theme="a pirate who loves cards")
    cloud = {"featured_resonance": [{"id": "reactive_playd", "why": "plays a lot"}, {"id": "nonsense_mech"}]}
    b._reroll_featured(brief, cloud, d)
    assert d.featured_resonance == [{"id": real, "why": "plays a lot"}]
    assert any(f"snapped nomination `reactive_playd` -> `{real}` (p=0.88)" in ln for ln in lines)
    assert brief.featured                                # the lottery still ran


def test_builder_unchanged_when_jev_fails(monkeypatch):
    _fake(monkeypatch, {}, fail=True)
    b = BlueprintBuilder(lambda *a, **k: None, catalog=None, triad=False)
    d = Dossier(theme="t")
    b._reroll_featured(_Brief(), {"featured_resonance": [{"id": "reactive_playd"}]}, d)
    assert d.featured_resonance == []


# ------------------------------------------------------------------------------------------ slot: vocab
def test_vocab_triage_near_and_new(monkeypatch):
    calls, usage = [], []
    _fake(monkeypatch, {"apply_posion": ("apply_status", 0.83), "time_warp": ("genuinely_new", 0.7),
                        "on_retian": ("on_exhaust", 0.6)}, calls=calls)
    misses = [("op", "apply_posion"), ("op", "time_warp"), ("trigger", "on_retian"), ("bogus_kind", "x_y")]
    t = class_forge.triage_vocab_misses(misses, "a poison card", on_usage=usage.append)
    assert t[("op", "apply_posion")] == {"verdict": "near:apply_status", "nearest": "apply_status", "p": 0.83}
    assert t[("op", "time_warp")]["verdict"] == "new"
    assert t[("trigger", "on_retian")]["verdict"] == "new"      # p < 0.8 is never "near"
    assert ("bogus_kind", "x_y") not in t
    q = calls[0]["questions"]
    assert len(calls) == 1 and len(q) == 3 and "genuinely_new" in q["m0"]["criteria"]
    assert "apply_status" in q["m0"]["criteria"] and usage[0]["_role"] == "jev:vocab"
    assert class_forge._triage_suffix(t[("op", "apply_posion")]) == " [triage: near `apply_status` p=0.83]"
    assert class_forge._triage_suffix(t[("op", "time_warp")]) == " [triage: new]"
    assert class_forge._triage_suffix(None) == ""


def test_vocab_triage_off_or_failing_is_empty(monkeypatch):
    _fake(monkeypatch, {}, fail=True)
    assert class_forge.triage_vocab_misses([("op", "apply_posion")]) == {}
    monkeypatch.setenv("BTS_JEV_SLOTS", "nominate")
    assert class_forge.triage_vocab_misses([("op", "apply_posion")]) == {}


def test_usage_sink_finds_a_failover_tier():
    class G:
        _on_usage = staticmethod(lambda u: None)

    class F:
        tiers = [type("T", (), {"gen": G()})()]
    assert class_forge.usage_sink(G()) is not None and class_forge.usage_sink(F()) is not None
    assert class_forge.usage_sink(object()) is None


# ------------------------------------------------------------------- relic / qa / stub slots (Phase 2 second half)
_COUNTER_RELIC = {"id": "tally_stone", "name": "Tally Stone", "icon_emoji": "*",
                  "description": "Every 3rd Attack you play, gain 4 Block.",
                  "hooks": [{"trigger": "on_card_played", "card_type": "attack", "every_n": 3,
                             "effects": [{"op": "block", "amount": 4}]}]}


def _typed_fake(monkeypatch, *, calls=None, choice_pick="Counter relic", noul=0.8, score=2.4, stub_p=None):
    """Answer every question by its type: noul -> {"noul": p}; score -> the documented score shape; choice ->
    `choice_pick` when offered (else the last option)."""
    def post(key, state, questions):
        if calls is not None:
            calls.append({"state": state, "questions": questions})
        ans = {}
        for name, q in questions.items():
            if q["type"] == "noul":
                ans[name] = {"noul": stub_p if (stub_p is not None and name == "stub") else noul}
            elif q["type"] == "score":
                n = len(q["criteria"])
                ans[name] = {"type": "score", "score": score,
                             "legend": {str(i): c for i, c in enumerate(q["criteria"])},
                             "probabilities": {str(i): (0.6 if i == round(score) else 0.4 / (n - 1))
                                               for i in range(n)},
                             "confidence": 0.6}
            else:
                opts = list(q["criteria"])
                best = choice_pick if choice_pick in opts else opts[-1]
                ans[name] = {"type": "choice", "choice": best, "confidence": 0.88,
                             "probabilities": {o: (0.88 if o == best else 0.01) for o in opts}}
        return {"answers": ans, "usage": {"input_tokens": 40, "cost": 0.000001}}
    monkeypatch.setattr(jev, "post", post)


def test_relic_form_names_come_from_the_heuristic():
    names = class_forge.relic_form_names()
    assert names[:3] == ["Combat-start boon", "Per-turn drip", "Reactive counter"]
    assert len(names) == 10 and "Counter relic" in names and "Class-kind boon" in names
    assert class_forge.relic_form_names("no bullets here") == []


@pytest.mark.parametrize("relic, form", [
    (_COUNTER_RELIC, "Counter relic"),
    ({"hooks": [{"trigger": "combat_end", "effects": [{"op": "heal", "amount": 4}]}]}, "Victory heal"),
    ({"hooks": [{"trigger": "attacked", "target": "attacker", "effects": [{"op": "damage", "amount": 2}]}]},
     "Reactive counter"),
    ({"hooks": [{"trigger": "turn_start", "once_per_combat": True, "effects": [{"op": "forge", "amount": 2}]}]},
     "Class-kind boon"),
    ({"hooks": [{"trigger": "turn_start", "once_per_combat": True,
                 "effects": [{"op": "apply_status", "status": "strength", "amount": 1}]}]}, "Combat-start boon"),
    ({"hooks": [{"trigger": "turn_start", "effects": [{"op": "block", "amount": 2}]}]}, "Per-turn drip"),
    ({"hooks": [{"trigger": "on_exhaust", "effects": [{"op": "draw", "amount": 1}]}]}, "Do-what-you-do payoff"),
    ({"hooks": [{"trigger": "on_hp_lost", "effects": [{"op": "block", "amount": 2}]}]}, "Bleed payoff"),
    ({"modifiers": [{"stat": "first_attack", "amount": 8}]}, "Passive modifier"),
    ({"modifiers": [{"stat": "max_energy", "amount": 1}, {"stat": "max_hp", "amount": -10}]}, "Boon with a price"),
    ({"hooks": [{"trigger": "turn_end", "effects": [{"op": "block", "amount": 3}]}]}, None),
    ("not a relic", None),
])
def test_guess_relic_form(relic, form):
    assert class_forge.guess_relic_form(relic) == form


def test_jev_relic_form_records_form_and_agreement(monkeypatch):
    calls, usage = [], []
    _typed_fake(monkeypatch, calls=calls)
    got = class_forge.jev_relic_form(_COUNTER_RELIC, on_usage=usage.append)
    assert got == {"form": "Counter relic", "p": 0.88, "guess": "Counter relic", "agree": True}
    q = calls[0]["questions"]["q"]
    assert set(q["criteria"]) == set(class_forge.relic_form_names()) | {"none_of_these"}
    assert calls[0]["state"]["relic"] == _COUNTER_RELIC and "RELIC FORMS" in calls[0]["state"]["forms"]
    assert usage[0]["_role"] == "jev:relic"
    jev.clear_memo()
    _typed_fake(monkeypatch, choice_pick="Per-turn drip")
    assert class_forge.jev_relic_form(_COUNTER_RELIC)["agree"] is False


def test_jev_relic_form_off_or_failing_is_none(monkeypatch):
    _typed_fake(monkeypatch)
    monkeypatch.setenv("BTS_JEV_SLOTS", "qa")
    assert class_forge.jev_relic_form(_COUNTER_RELIC) is None
    monkeypatch.setenv("BTS_JEV_SLOTS", "relic")
    _fake(monkeypatch, {}, fail=True)
    assert class_forge.jev_relic_form(_COUNTER_RELIC) is None


def test_parse_score_shapes():
    assert jev.parse_score({"type": "score", "score": 1.05, "probabilities": {"0": 0.0, "1": 0.95, "2": 0.05}}, 3) \
        == (2.05, 2)
    assert jev.parse_score({"0": 0.1, "1": 0.1, "2": 0.8}, 3) == (2.7, 3)       # bare map: weighted, 1-based
    assert jev.parse_score({"score": 99}, 5) is None
    assert jev.parse_score("nope", 5) is None


def test_jev_card_qa_one_request_three_questions(monkeypatch):
    calls, usage = [], []
    _typed_fake(monkeypatch, calls=calls, noul=0.81, score=3.0)
    card = {"id": "x", "name": "Iron Hail", "type": "attack", "rarity": "common", "cost": 1, "target": "enemy",
            "effects": [{"op": "damage", "amount": 6}]}
    got = class_forge.jev_card_qa(card, "a hail of iron", on_usage=usage.append)
    assert got == {"name_fits": 0.81, "reads_like_sts": 0.81, "power": 4.0, "power_level": 4}
    assert len(calls) == 1 and set(calls[0]["questions"]) == {"name_fits", "reads_like_sts", "power"}
    assert calls[0]["questions"]["power"]["criteria"] == list(class_forge.QA_POWER_LEVELS)
    st = calls[0]["state"]
    assert st["name"] == "Iron Hail" and "6" in st["text"] and st["brief"] == "a hail of iron"
    assert usage[0]["_role"] == "jev:qa"
    monkeypatch.setenv("BTS_JEV_SLOTS", "off")
    assert class_forge.jev_card_qa(card) is None


def test_forge_records_qa_per_card(monkeypatch, tmp_path):
    from btsgen.class_forge import ClassBrief, _CardFake, forge_class
    monkeypatch.setenv("BTS_FORGE_LEDGER", str(tmp_path / "ledger.jsonl"))
    monkeypatch.setenv("BTS_JEV_SLOTS", "qa")
    _typed_fake(monkeypatch)
    res = forge_class(ClassBrief(concept="a molten forge sovereign"), blueprint_gen=None,
                      card_gen_factory=lambda: _CardFake(), relic_gen=None, fake=True, triad=False)
    assert res.ok
    qa = res.stats.get("jev_qa") or []
    assert qa and all(set(r) == {"name", "name_fits", "reads_like_sts", "power", "validator_score"} for r in qa)
    assert any("qa (jev): name_fits=0.8" in line for line in res.log)


def _or_gen(monkeypatch, replies):
    """An OpenAICompatGenerator on the OpenRouter host whose transport replays canned replies."""
    from btsgen import generator as g
    gen = g.OpenAICompatGenerator(base_url="https://openrouter.ai/api/v1", api_key="k", model="m")
    seq = list(replies)

    def once(payload):
        gen.last_meta = {"provider": f"p{len(seq)}"}
        return seq.pop(0)
    monkeypatch.setattr(gen, "_complete_once", once)
    monkeypatch.setattr(g, "ignore_provider", lambda p: None)
    return gen


def test_stub_slot_logs_agreement_without_changing_retries(monkeypatch):
    calls = []
    _typed_fake(monkeypatch, calls=calls, stub_p=0.97)
    monkeypatch.setenv("BTS_JEV_SLOTS", "stub")
    gen = _or_gen(monkeypatch, ['{"name": "", "effects": []}', '{"name": "Real", "effects": [{"op": "block"}]}'])
    text = gen._complete([{"role": "user", "content": "x"}])
    assert "Real" in text                                   # the string detector still drove the one retry
    assert len(calls) == 2 and calls[0]["state"] == {"reply": '{"name": "", "effects": []}'}
    assert gen.last_meta["jev_stub"] == {"p": 0.97, "string_stub": False}
    assert gen.last_meta["jev_stub_all"][0] == {"p": 0.97, "string_stub": True}
    assert gen.last_meta["stubs"]


def test_stub_slot_off_makes_no_call(monkeypatch):
    calls = []
    _typed_fake(monkeypatch, calls=calls)
    monkeypatch.setenv("BTS_JEV_SLOTS", "qa")
    gen = _or_gen(monkeypatch, ['{"name": "Real", "effects": [{"op": "block"}]}'])
    gen._complete([{"role": "user", "content": "x"}])
    assert calls == [] and "jev_stub" not in gen.last_meta


def test_stub_slot_failure_never_raises(monkeypatch):
    _fake(monkeypatch, {}, fail=True)
    monkeypatch.setenv("BTS_JEV_SLOTS", "stub")
    gen = _or_gen(monkeypatch, ['{"name": "Real", "effects": [{"op": "block"}]}'])
    assert "Real" in gen._complete([{"role": "user", "content": "x"}])
    assert gen.last_meta["jev_stub"] == {"p": None, "string_stub": False}


class _RelicStub:
    model = "relic-stub"

    def first_attempt(self, bp):
        import json as _j
        t = _j.dumps(_COUNTER_RELIC)
        return t, [{"role": "user", "content": "bp"}, {"role": "assistant", "content": t}]

    def repair(self, messages, prev_text, errors):
        return prev_text, messages


def test_forge_records_relic_form(monkeypatch, tmp_path):
    from btsgen.class_forge import ClassBrief, _CardFake, forge_class
    from btsgen.frontend import load_catalog
    from btsgen.frontend.fakes import _StageFake
    monkeypatch.setenv("BTS_FORGE_LEDGER", str(tmp_path / "ledger.jsonl"))
    monkeypatch.setenv("BTS_HARNESS_V2", "1")
    monkeypatch.setenv("BTS_JEV_SLOTS", "relic")
    _typed_fake(monkeypatch)
    b = BlueprintBuilder(lambda c, *, max_tokens: _StageFake(c), catalog=load_catalog(), auto=True,
                         gap_log_append=None, triad=True, on_event=lambda m: None)
    res = forge_class(ClassBrief(concept="a plague doctor who trades health for knowledge"), blueprint_gen=None,
                      card_gen_factory=lambda: _CardFake(), relic_gen=_RelicStub(), fake=False, front_end=b)
    assert res.ok, res.log[-3:]
    relic_lines = [line for line in res.log if "relic" in line.lower()]
    if res.stats.get("jev_relic") is None:  # the stub relic must have passed the deck-aware gate to be asked about
        pytest.fail(f"no jev_relic: {relic_lines[-3:]}")
    assert res.stats["jev_relic"]["form"] == "Counter relic" and res.stats["jev_relic"]["agree"] is True
    assert any("relic form (jev): Counter relic p=0.88" in line for line in res.log)
