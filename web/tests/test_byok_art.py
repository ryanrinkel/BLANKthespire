"""Art follows the money: a bring-your-own-key forge generates its splash, sprite and card portraits on the
USER's key (OpenRouter / OpenAI) or not at all — the server's image keys (BTSGEN_IMAGE_BACKEND chain) pay
only for token forges.

Network-free: the cloud backends' urlopen is replaced with a fake that records the Authorization header
and answers with a tiny PNG (conftest's safety net otherwise makes every cloud image call fail fast)."""
from __future__ import annotations

import base64
import contextlib
import json

import pytest
from conftest import H, login, sse_events

OR_KEY = {"base_url": "https://openrouter.ai/api/v1", "api_key": "sk-or-user-key", "model": "openai/gpt-4o"}
OAI_KEY = {"base_url": "https://API.OpenAI.com/v1", "api_key": "sk-user-openai", "model": "gpt-4o"}
GROQ_KEY = {"base_url": "https://api.groq.com/openai/v1", "api_key": "gsk_user", "model": "llama"}


def _fake_images(monkeypatch, module, *, cost=0.03):
    """Replace `module.urlopen` with a recorder that returns one 2x2 PNG per call."""
    from btsgen.art.png import encode_rgb
    png = encode_rgb(2, 2, bytes(2 * 2 * 3))
    body = json.dumps({"data": [{"b64_json": base64.b64encode(png).decode(), "media_type": "image/png"}],
                       "usage": {"cost": cost}}).encode()
    seen: list[dict] = []

    @contextlib.contextmanager
    def fake_urlopen(request, timeout=0):
        seen.append({k.lower(): v for k, v in request.header_items()})

        class R:
            def read(self_inner):
                return body
        yield R()

    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    return seen


def _art_rows(app_module, class_id: int) -> dict:
    from models import ForgeUsage
    with app_module.session_scope() as s:
        rows = s.query(ForgeUsage).filter_by(class_id=class_id).all()
        return {r.role: (r.calls, r.mode, r.provider) for r in rows if r.role.startswith("art:")}


# --- the routing decision ----------------------------------------------------------------------------

def test_token_and_fake_forges_use_the_servers_chain(app_module):
    assert app_module._byok_art_backend("token", None) is None
    assert app_module._byok_art_backend("fake", None) is None


def test_an_openrouter_key_builds_an_openrouter_backend_on_that_key(app_module, monkeypatch):
    from btsgen.art.backends.openrouter import OpenRouterImageBackend
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)  # the server's key must not be what's used
    be = app_module._byok_art_backend("byok", OR_KEY)
    assert isinstance(be, OpenRouterImageBackend) and be.available() and be._key() == "sk-or-user-key"


def test_an_openai_key_builds_an_openai_backend_on_that_key(app_module, monkeypatch):
    from btsgen.art.backends.openai import OpenAIImageBackend
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("BTSGEN_IMAGE_API_KEY", raising=False)
    be = app_module._byok_art_backend("byok", OAI_KEY)   # host matching is case-insensitive
    assert isinstance(be, OpenAIImageBackend) and be.available() and be._key() == "sk-user-openai"


def test_providers_without_an_image_api_get_the_fallback_never_the_servers_chain(app_module, monkeypatch):
    monkeypatch.delenv("BTSWEB_BYOK_ART_FALLBACK", raising=False)
    assert app_module._byok_art_backend("byok", GROQ_KEY) == "null"
    assert app_module._byok_art_backend("anthropic", {"provider": "anthropic", "api_key": "sk-ant", "model": "m"}) == "null"
    assert app_module._byok_art_backend("byok", {"base_url": "not a url", "api_key": "k", "model": "m"}) == "null"
    assert app_module._byok_art_backend("byok", {"base_url": OR_KEY["base_url"], "model": "m"}) == "null"  # no key
    monkeypatch.setenv("BTSWEB_BYOK_ART_FALLBACK", "procedural")
    assert app_module._byok_art_backend("byok", GROQ_KEY) == "procedural"


# --- end to end through the forge route ------------------------------------------------------------------

def test_a_byok_openrouter_forge_makes_its_art_on_the_users_key(client, app_module, stub_forge, monkeypatch):
    from btsgen.art.backends import openrouter as orb
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("BTSGEN_IMAGE_BACKEND", "null")      # the server would make NO art on its own
    seen = _fake_images(monkeypatch, orb, cost=0.01)
    login(client, "byokart@example.com")

    ev = sse_events(client.post("/api/forge-class", headers=H, json={"concept": "x", "mode": "byok", "key": OR_KEY}))
    assert ev[-1][0] == "result", ev[-1]
    saved = ev[-1][1]

    n_cards = len(saved["cards"])
    assert seen and all(h["authorization"] == "Bearer sk-or-user-key" for h in seen)
    assert len(seen) == n_cards + 2                            # splash + sprite + one portrait per card
    assert saved.get("splash_url") and saved.get("sprite_url")
    assert saved["usage"]["images"] == n_cards + 2
    assert saved["usage"]["art_cost_usd"] == pytest.approx(0.01 * (n_cards + 2), abs=1e-3)
    rows = _art_rows(app_module, saved["id"])
    assert set(rows) == {"art:splash", "art:sprite", "art:cards"}
    assert all(mode == "byok" and prov == "openrouter.ai" for _, mode, prov in rows.values())


def test_a_byok_forge_on_an_imageless_provider_ships_without_art(client, app_module, stub_forge, monkeypatch):
    """Even with the server's own chain configured, a Groq-key forge must not touch it."""
    from btsgen.art.backends import openai as oaib, openrouter as orb
    monkeypatch.setenv("BTSGEN_IMAGE_BACKEND", "procedural")  # the token path WOULD get placeholder art
    monkeypatch.delenv("BTSWEB_BYOK_ART_FALLBACK", raising=False)
    seen_or = _fake_images(monkeypatch, orb)
    seen_oai = _fake_images(monkeypatch, oaib)
    login(client, "byoknoart@example.com")

    ev = sse_events(client.post("/api/forge-class", headers=H, json={"concept": "x", "mode": "byok", "key": GROQ_KEY}))
    assert ev[-1][0] == "result", ev[-1]
    saved = ev[-1][1]
    assert not seen_or and not seen_oai
    assert not saved.get("splash_url") and not saved.get("sprite_url") and not saved.get("card_art_url")
    assert saved["usage"]["images"] == 0 and saved["usage"]["art_cost_usd"] is None
    assert _art_rows(app_module, saved["id"]) == {}


def test_the_fallback_can_give_imageless_byok_forges_placeholder_art(client, app_module, stub_forge, monkeypatch):
    monkeypatch.setenv("BTSGEN_IMAGE_BACKEND", "null")
    monkeypatch.setenv("BTSWEB_BYOK_ART_FALLBACK", "procedural")
    from btsgen.art.request import StyleProfile
    monkeypatch.setattr("btsgen.art.card.CARD_STYLE", StyleProfile(name="card-test", size=(48, 32), out_format="png"))
    login(client, "byokplaceholder@example.com")

    ev = sse_events(client.post("/api/forge-class", headers=H, json={
        "concept": "x", "mode": "anthropic", "key": {"api_key": "sk-ant-user", "model": "claude-sonnet-4-6"}}))
    assert ev[-1][0] == "result", ev[-1]
    saved = ev[-1][1]
    assert saved.get("splash_url") and saved.get("sprite_url") and saved.get("card_art_url")
    assert saved["usage"]["images"] == len(saved["cards"]) + 2
    assert saved["usage"]["art_cost_usd"] == 0.0                # procedural is really free
