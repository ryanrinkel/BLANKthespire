"""/api/forge-estimate — the pre-go cost quote (BYOK_ART_GEMINI_XAI_PLAN.md step 3).

The browser owns NO price table any more: it multiplies the numbers this endpoint hands it. So the
contract tested here is that the endpoint can always answer three questions for whatever key the user is
about to paste — what the text costs, what the art costs, and how many images a pack is — and that the
price table stays in step with the suggestions static/app.js actually offers.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from conftest import login

APP_JS = Path(__file__).resolve().parents[1] / "static" / "app.js"


def _naive_utc(offset_days: float = 0.0) -> datetime:
    return (datetime.now(timezone.utc) - timedelta(days=offset_days)).replace(tzinfo=None)


def _user_id(app_module, email: str) -> int:
    from models import User
    with app_module.session_scope() as s:
        return s.query(User).filter_by(email=email).one().id


def _clear(app_module):
    from models import ForgeJob, ForgeUsage
    with app_module.session_scope() as s:
        s.query(ForgeUsage).delete()
        s.query(ForgeJob).delete()
    app_module._estimate_cache.update(at=0.0, payload=None)


def _seed_forge(app_module, user_id: int, forge_id: str, *, provider="openrouter.ai", images=36,
                art_micros: int | None = 360_000, mode="byok", age_days=0.0):
    """One sampled forge: a text row (that is what puts it in the window) plus its art row."""
    from models import ForgeUsage
    when = _naive_utc(age_days)
    with app_module.session_scope() as s:
        s.add(ForgeUsage(user_id=user_id, forge_id=forge_id, mode=mode, provider=provider,
                         model="z-ai/glm-5.3", role="cards", calls=40, input_tokens=1000,
                         output_tokens=100, cached_tokens=500, ok=1, created_at=when))
        if images:
            s.add(ForgeUsage(user_id=user_id, forge_id=forge_id, mode=mode, provider=provider,
                             model="an-image-model", role="art:cards", calls=images, input_tokens=0,
                             output_tokens=0, cached_tokens=0, metered_cost_micros=art_micros, ok=1,
                             created_at=when))


def _estimate(client, app_module):
    app_module._estimate_cache.update(at=0.0, payload=None)  # never answer from a previous call's cache
    r = client.get("/api/forge-estimate")
    assert r.status_code == 200
    return r.get_json()


def suggested_models() -> dict[str, list[str]]:
    """Every model id static/app.js suggests, parsed out of the PROVIDERS literal by provider id.

    A regex on purpose: the point is that ADDING a suggestion to app.js without pricing it server-side
    fails this suite, so the parser must see the real file, not a copy kept in the test."""
    src = APP_JS.read_text(encoding="utf-8")
    block = src.split("const PROVIDERS = {", 1)[1].split("\n};", 1)[0]
    out: dict[str, list[str]] = {}
    for m in re.finditer(r"(?m)^  (\w+):\s*\{", block):
        pid = m.group(1)
        nxt = re.search(r"(?m)^  \w+:\s*\{", block[m.end():])
        body = block[m.end():m.end() + (nxt.start() if nxt else len(block))]
        models = re.search(r"models:\s*\[(.*?)\]", body, re.S)
        out[pid] = re.findall(r'"([^"]+)"', models.group(1)) if models else []
    return out


# --- the parser itself (a silently-empty parse would make the price test vacuous) ------------------------

def test_the_app_js_parser_sees_every_provider():
    found = suggested_models()
    assert set(found) >= {"anthropic", "openai", "ollama", "openrouter", "groq", "google", "xai",
                          "deepseek", "together", "custom"}
    assert found["xai"][0] == "grok-4.20-0309-non-reasoning"   # non-reasoning suggested first
    assert found["google"][0] == "gemini-2.5-flash-lite"       # cheap first
    assert sum(len(v) for v in found.values()) >= 25


# --- the price table -------------------------------------------------------------------------------------

def test_every_suggested_model_carries_a_text_price(client, app_module):
    """A suggestion with no price would render a blank quote — that is a test failure, not a UI shrug."""
    login(client, "estimate-prices@example.com")
    prices = _estimate(client, app_module)["text_prices"]
    missing = {pid: [m for m in models if m not in prices]
               for pid, models in suggested_models().items()}
    assert not any(missing.values()), f"suggested models with no price: {missing}"
    for model, row in prices.items():
        assert len(row) == 3 and all(isinstance(x, (int, float)) and x >= 0 for x in row), model


def test_the_env_override_table_flows_into_the_quote(client, app_module, monkeypatch):
    """BTSWEB_MODEL_PRICES edits MODEL_PRICES at import; the payload must read that same live table."""
    login(client, "estimate-override@example.com")
    monkeypatch.setitem(app_module.MODEL_PRICES, "gpt-4o", (9.0, 99.0, 0.9))
    assert _estimate(client, app_module)["text_prices"]["gpt-4o"] == [9.0, 99.0, 0.9]


# --- the art block ---------------------------------------------------------------------------------------

def test_the_art_block_answers_for_every_art_capable_host(client, app_module):
    login(client, "estimate-art@example.com")
    _clear(app_module)
    body = _estimate(client, app_module)
    assert set(body["art"]) == set(app_module._BYOK_ART_HOSTS.values())
    for vendor, entry in body["art"].items():
        assert entry["per_image_usd"] is not None and entry["pack_usd"] > 0, vendor
        assert entry["source"] in ("list", "measured")
    gem, xai = body["art"]["gemini"], body["art"]["xai"]
    assert gem["model"] == "gemini-2.5-flash-image" and gem["per_image_usd"] == pytest.approx(0.039)
    assert xai["model"] == "grok-imagine-image" and xai["per_image_usd"] == pytest.approx(0.02)
    assert set(gem["models"]) == {"splash", "sprite", "card"}
    # 36 images on an empty ledger, and the preset totals the plan quotes
    assert body["images_per_forge"] == 36 and body["images_fallback"] is True
    assert gem["pack_usd"] == pytest.approx(1.404) and xai["pack_usd"] == pytest.approx(0.72)
    assert body["art"]["openrouter"]["source"] == "list"


def test_images_per_forge_is_the_rolling_average_of_the_sampled_forges(client, app_module):
    login(client, "estimate-images@example.com")
    _clear(app_module)
    uid = _user_id(app_module, "estimate-images@example.com")
    _seed_forge(app_module, uid, "a" * 32, images=30)
    _seed_forge(app_module, uid, "b" * 32, images=40)
    body = _estimate(client, app_module)
    assert body["images_per_forge"] == 35 and body["images_fallback"] is False
    # the art line scales with it: 35 images x $0.039
    assert body["art"]["gemini"]["pack_usd"] == pytest.approx(0.039 * 35, abs=1e-4)
    _clear(app_module)


# --- measured vs list (the plan's open question, answered) ------------------------------------------------

def test_two_measured_forges_are_not_enough_to_beat_the_list_price(client, app_module):
    login(client, "estimate-two@example.com")
    _clear(app_module)
    uid = _user_id(app_module, "estimate-two@example.com")
    for fid in ("1" * 32, "2" * 32):
        _seed_forge(app_module, uid, fid, provider="openrouter.ai", art_micros=360_000)
    entry = _estimate(client, app_module)["art"]["openrouter"]
    assert entry["source"] == "list" and entry["per_image_usd"] == pytest.approx(0.0055)
    _clear(app_module)


def test_three_measured_forges_replace_the_list_price(client, app_module):
    login(client, "estimate-three@example.com")
    _clear(app_module)
    uid = _user_id(app_module, "estimate-three@example.com")
    for fid in ("1" * 32, "2" * 32, "3" * 32):
        _seed_forge(app_module, uid, fid, provider="openrouter.ai", art_micros=360_000)  # $0.01/image
    entry = _estimate(client, app_module)["art"]["openrouter"]
    assert entry["source"] == "measured" and entry["forges_measured"] == 3
    assert entry["per_image_usd"] == pytest.approx(0.01)
    assert entry["pack_usd"] == pytest.approx(0.36)
    _clear(app_module)


def test_token_forges_back_the_openrouter_average_when_no_byok_ones_exist(client, app_module):
    """A token forge's art runs on OUR OpenRouter key, so 'hosted' rows are the same measured pack."""
    login(client, "estimate-hosted@example.com")
    _clear(app_module)
    uid = _user_id(app_module, "estimate-hosted@example.com")
    for fid in ("1" * 32, "2" * 32, "3" * 32):
        _seed_forge(app_module, uid, fid, provider="hosted", mode="token", art_micros=180_000)
    entry = _estimate(client, app_module)["art"]["openrouter"]
    assert entry["source"] == "measured" and entry["per_image_usd"] == pytest.approx(0.005)
    _clear(app_module)


def test_a_measured_gemini_history_overrides_the_preset_price(client, app_module):
    login(client, "estimate-gem@example.com")
    _clear(app_module)
    uid = _user_id(app_module, "estimate-gem@example.com")
    for fid in ("1" * 32, "2" * 32, "3" * 32):
        _seed_forge(app_module, uid, fid, provider="generativelanguage.googleapis.com",
                    art_micros=36 * 45_000)  # the vendor actually billed $0.045 an image
    art = _estimate(client, app_module)["art"]
    assert art["gemini"]["source"] == "measured"
    assert art["gemini"]["per_image_usd"] == pytest.approx(0.045)
    assert art["gemini"]["model"] == "gemini-2.5-flash-image"   # the model is still the preset's
    assert art["xai"]["source"] == "list"                       # untouched by another vendor's history
    _clear(app_module)


def test_art_rows_without_a_metered_cost_never_become_a_measured_price(client, app_module):
    """Gemini/xAI rows carry a list-price estimate; a row with no cost at all (an unpriced model) must
    not drag the average to zero."""
    login(client, "estimate-nocost@example.com")
    _clear(app_module)
    uid = _user_id(app_module, "estimate-nocost@example.com")
    for fid in ("1" * 32, "2" * 32, "3" * 32):
        _seed_forge(app_module, uid, fid, provider="api.openai.com", art_micros=None)
    entry = _estimate(client, app_module)["art"]["openai"]
    assert entry["source"] == "list" and entry["per_image_usd"] == pytest.approx(0.0055)
    _clear(app_module)


# --- caching ---------------------------------------------------------------------------------------------

def test_the_payload_is_cached_for_a_minute(client, app_module):
    login(client, "estimate-cache@example.com")
    _clear(app_module)
    uid = _user_id(app_module, "estimate-cache@example.com")
    first = client.get("/api/forge-estimate").get_json()
    _seed_forge(app_module, uid, "9" * 32, images=12)
    assert client.get("/api/forge-estimate").get_json() == first   # same minute, same answer
    app_module._estimate_cache.update(at=0.0, payload=None)
    assert client.get("/api/forge-estimate").get_json()["images_per_forge"] == 12
    _clear(app_module)
