"""Two-model BYOK: a key names a DESIGN model (brainstorm + structure roles) and an optional CARD model (the
cards role — every card + the relic). forge._key_models is the split; this suite pins that each generator
lands on the right model, that a blank card model is the old one-model forge, that usage is booked per
(role, model), and that /api/forge-estimate hands the browser a design/cards split to price each half.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from conftest import H, login, sse_events

COMPAT_KEY = {"base_url": "https://openrouter.ai/api/v1", "api_key": "sk-or-user",
              "model": "anthropic/claude-opus-4.8", "card_model": "openai/gpt-4o-mini"}
ANTHROPIC_KEY = {"provider": "anthropic", "api_key": "sk-ant-user",
                 "model": "claude-opus-4-8", "card_model": "claude-haiku-4-5"}


@pytest.fixture()
def recording(monkeypatch):
    """Swap both generator classes for recorders: each construction appends {model, contract, on_usage}."""
    import btsgen.generator as gen_mod
    import forge
    seen: list[dict] = []
    monkeypatch.setattr(forge, "_guard_outbound_url", lambda url: None)  # no DNS in tests

    class Compat:
        def __init__(self, base_url, api_key, model, **kw):
            seen.append({"model": model, "contract": type(kw.get("contract_mod")).__name__,
                         "on_usage": kw.get("on_usage")})

    class Anthropic:
        def __init__(self, model, api_key, **kw):
            seen.append({"model": model, "contract": type(kw.get("contract_mod")).__name__,
                         "on_usage": kw.get("on_usage")})

    monkeypatch.setattr(gen_mod, "OpenAICompatGenerator", Compat)
    monkeypatch.setattr(gen_mod, "AnthropicGenerator", Anthropic)
    return seen


def _stage_contracts():
    from btsgen.class_forge import _RelicContract
    from btsgen.frontend.stage_cloud import _CloudClusterContract
    from btsgen.frontend.stage_map import _MapComposeContract
    return [_CloudClusterContract(), _MapComposeContract(True), _RelicContract()]


@pytest.mark.parametrize("key", [COMPAT_KEY, ANTHROPIC_KEY], ids=["openai-compat", "anthropic"])
def test_design_roles_run_the_design_model_and_cards_run_the_card_model(recording, key):
    import forge
    design, cards = key["model"], key["card_model"]

    blueprint_gen, card_factory, relic_gen = forge._build_generators(dict(key), hosted=False, fake=False)
    card_factory()
    assert [r["model"] for r in recording] == [design, cards, cards]   # blueprint, relic, one card

    recording.clear()
    make_gen = forge._make_gen_factory(dict(key), hosted=False, fake=False)
    for c in _stage_contracts():
        make_gen(c, max_tokens=4000)
    # brainstorm (cloud) + structure (map/compose) design the class; the relic is card coding
    assert [r["model"] for r in recording] == [design, design, cards]


@pytest.mark.parametrize("key", [COMPAT_KEY, ANTHROPIC_KEY], ids=["openai-compat", "anthropic"])
def test_a_blank_card_model_is_the_one_model_forge(recording, key):
    import forge
    one = {**key, "card_model": "  "}
    forge._build_generators(dict(one), hosted=False, fake=False)[1]()
    make_gen = forge._make_gen_factory(dict(one), hosted=False, fake=False)
    for c in _stage_contracts():
        make_gen(c, max_tokens=4000)
    assert {r["model"] for r in recording} == {key["model"]}


def test_usage_is_booked_per_role_and_model(recording):
    """Both usage shapes land in the meter tagged with the role + model that produced them — the Anthropic
    SDK's Usage object is flattened to the dict shape (cache reads included)."""
    import forge
    meter = forge.UsageMeter(default_model="ignored", default_role="byok")
    make_gen = forge._make_gen_factory(dict(ANTHROPIC_KEY), hosted=False, fake=False, on_usage=meter)
    for c in _stage_contracts():
        make_gen(c, max_tokens=4000)
    brainstorm, structure, relic = (r["on_usage"] for r in recording)
    brainstorm(SimpleNamespace(input_tokens=100, output_tokens=10, cache_read_input_tokens=40))
    structure({"prompt_tokens": 200, "completion_tokens": 20})
    relic(SimpleNamespace(input_tokens=300, output_tokens=30, cache_read_input_tokens=None))
    rows = {(r["role"], r["model"]): r for r in meter.rows()}
    assert set(rows) == {("brainstorm", "claude-opus-4-8"), ("structure", "claude-opus-4-8"),
                         ("cards", "claude-haiku-4-5")}
    assert rows[("brainstorm", "claude-opus-4-8")]["cached_tokens"] == 40
    assert rows[("cards", "claude-haiku-4-5")]["input_tokens"] == 300


def test_the_route_passes_the_card_model_through(client, app_module, stub_forge):
    login(client, "two-models@example.com")
    for body in ({"concept": "x", "mode": "anthropic",
                  "key": {"api_key": "sk-ant-x", "model": "claude-opus-4-8", "card_model": " claude-haiku-4-5 "}},
                 {"concept": "x", "mode": "byok", "key": {**COMPAT_KEY}}):
        assert sse_events(client.post("/api/forge-class", json=body, headers=H))[-1][0] == "result"
        key = stub_forge.calls[-1]["key"]
        assert key["card_model"].strip() in ("claude-haiku-4-5", "openai/gpt-4o-mini")
    assert stub_forge.calls[0]["key"]["card_model"] == "claude-haiku-4-5"   # trimmed on the Anthropic path


# --- the estimate's design/cards split -------------------------------------------------------------------

def _clear(app_module):
    from models import ForgeJob, ForgeUsage
    with app_module.session_scope() as s:
        s.query(ForgeUsage).delete()
        s.query(ForgeJob).delete()
    app_module._estimate_cache.update(at=0.0, payload=None)


def _estimate(client, app_module):
    app_module._estimate_cache.update(at=0.0, payload=None)
    r = client.get("/api/forge-estimate")
    assert r.status_code == 200
    return r.get_json()


def _halves_add_up(body):
    for f in ("calls", "input_tokens", "cached_tokens", "output_tokens"):
        assert body["slots"]["design"][f] + body["slots"]["cards"][f] == body[f], f


def test_an_empty_ledger_splits_by_the_measured_fallback_share(client, app_module):
    login(client, "split-empty@example.com")
    _clear(app_module)
    body = _estimate(client, app_module)
    _halves_add_up(body)
    share = app_module.FORGE_ESTIMATE_FALLBACK_DESIGN_SHARE
    assert body["slots"]["design"]["input_tokens"] == round(body["input_tokens"] * share["input_tokens"])
    # card coding is the bulk of the input bill — the premise of the two-model split
    assert body["slots"]["cards"]["input_tokens"] > 20 * body["slots"]["design"]["input_tokens"]


def test_role_tagged_rows_set_the_split(client, app_module):
    from models import ForgeUsage, User
    login(client, "split-rows@example.com")
    _clear(app_module)
    with app_module.session_scope() as s:
        uid = s.query(User).filter_by(email="split-rows@example.com").one().id
        for role, calls, inp in (("brainstorm", 2, 100), ("structure", 2, 300), ("cards", 40, 3600)):
            s.add(ForgeUsage(user_id=uid, forge_id="f1", mode="token", provider="hosted", model="m", role=role,
                             calls=calls, input_tokens=inp, output_tokens=calls, cached_tokens=0, ok=1))
        # a legacy one-model BYOK forge: counts toward the totals, says nothing about the split
        s.add(ForgeUsage(user_id=uid, forge_id="f2", mode="byok", provider="api.openai.com", model="gpt",
                         role="byok", calls=44, input_tokens=4000, output_tokens=44, cached_tokens=0, ok=1))
    body = _estimate(client, app_module)
    _halves_add_up(body)
    assert body["input_tokens"] == 4000 and body["calls"] == 44
    assert body["slots"]["design"]["input_tokens"] == 400      # (100 + 300) / 4000 of the average
    assert body["slots"]["design"]["calls"] == 4
