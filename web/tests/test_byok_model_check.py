"""BYOK model check at forge start (forge.verify_byok_models): the chosen design/card models must be on the
provider's UNFILTERED /models listing, else the forge route 400s with a plain sentence before anything is
queued. A provider that can't be listed skips the check; BTSWEB_BYOK_VERIFY_MODELS=0 turns it off. Also the
Gemini / OpenRouter refusal wordings explain_provider_error must recognise."""
from __future__ import annotations

import io
import json
import urllib.error
import urllib.request

import pytest
from conftest import H, login

import forge

URL = "https://api.example.com/v1"
LISTING = {"data": [{"id": "gpt-6.1-sol"}, {"id": "text-embedding-3-large"}, {"id": "models/gemini-3.8-flash"},
                    {"id": "google/gemma-4-31b-it:free"}]}


@pytest.fixture()
def listing(monkeypatch):
    """Serve LISTING from a fake urlopen (the SSRF guard's DNS is stubbed out); returns the request log."""
    seen = []

    def fake_urlopen(req, timeout=None):
        seen.append(req.full_url)
        return io.BytesIO(json.dumps(LISTING).encode())

    monkeypatch.setenv("BTSWEB_BYOK_VERIFY_MODELS", "1")
    monkeypatch.setattr(forge, "_guard_outbound_url", lambda u: None)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return seen


def test_listed_models_pass(listing):
    assert forge.verify_byok_models(URL, "k", "gpt-6.1-sol") is None
    assert forge.verify_byok_models(URL, "k", "gpt-6.1-sol", "gpt-6.1-sol") is None
    assert listing == [URL + "/models"] * 2


def test_existence_not_fitness(listing):
    # filter_models hides these from the picker, but they exist: the forge-start check lets them through.
    assert forge.verify_byok_models(URL, "k", "text-embedding-3-large", "google/gemma-4-31b-it:free") is None


def test_a_missing_design_or_card_model_is_named(listing):
    why = forge.verify_byok_models(URL, "k", "gtp-5")
    assert why == ("Your provider doesn't offer a model called “gtp-5” on this key. "
                   "Reload your model list and pick one from it.")
    assert "“claude-opus-5-5”" in forge.verify_byok_models(URL, "k", "gpt-6.1-sol", "claude-opus-5-5")
    assert forge.verify_byok_models(URL, "k", "gpt-6.1-sol", "  ") is None  # blank card = same as design


def test_models_prefix_matches_both_ways(listing, monkeypatch):
    assert forge.verify_byok_models(URL, "k", "gemini-3.8-flash") is None
    assert forge.verify_byok_models(URL, "k", "models/gemini-3.8-flash") is None
    assert forge.verify_byok_models(URL, "k", "models/gpt-6.1-sol") is None
    assert forge.verify_byok_models(URL, "k", "gemini-3.6-flash-lite") is not None


@pytest.mark.parametrize("exc", [
    urllib.error.HTTPError(URL + "/models", 404, "Not Found", {}, None),
    urllib.error.URLError("connection refused"),
])
def test_a_listing_failure_skips_the_check(monkeypatch, exc):
    def boom(req, timeout=None):
        raise exc

    monkeypatch.setenv("BTSWEB_BYOK_VERIFY_MODELS", "1")
    monkeypatch.setattr(forge, "_guard_outbound_url", lambda u: None)
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert forge.verify_byok_models(URL, "k", "anything-at-all") is None


def test_kill_switch(listing, monkeypatch):
    monkeypatch.setenv("BTSWEB_BYOK_VERIFY_MODELS", "0")
    assert forge.verify_byok_models(URL, "k", "gtp-5") is None
    assert listing == []  # not even fetched


def test_forge_route_400s_an_unknown_model_before_queueing(client, stub_forge, listing):
    login(client, "byokcheck@example.com")
    key = {"base_url": URL, "api_key": "k", "model": "gtp-5"}
    r = client.post("/api/forge-class", headers=H, json={"concept": "x", "mode": "byok", "key": key})
    assert r.status_code == 400
    assert r.get_json()["error"].startswith("Your provider doesn't offer a model called “gtp-5”")
    assert stub_forge.calls == []
    # Same account can forge straight away with a listed model (nothing was left registered).
    r = client.post("/api/forge-class", headers=H,
                    json={"concept": "x", "mode": "byok", "key": {**key, "model": "gpt-6.1-sol"}})
    assert r.status_code == 200
    r.get_data()


# --- explain_provider_error wordings ---------------------------------------------------------------------

GEMINI_404 = ('front-end failed: endpoint returned HTTP 404: [{"error": {"code": 404, "message": '
              '"models/gemini-3.6-flash-lite is not found for API version v1main, or is not supported for '
              'generateContent.", "status": "NOT_FOUND"}}]')
OPENROUTER_IGNORED = ('front-end failed: endpoint returned HTTP 404: {"error":{"message":"All providers have been '
                      'ignored. To change your default ignored providers, visit: '
                      'https://openrouter.ai/settings/preferences","code":404}}')
OPENROUTER_PRIVACY = ('front-end failed: endpoint returned HTTP 404: {"error":{"message":"No allowed providers '
                      'are available for the selected model.","code":404}}')


def test_gemini_not_found_wording():
    why = forge.explain_provider_error(GEMINI_404, model="gemini-3.6-flash-lite")
    assert why.startswith("Your provider doesn't offer a model called “gemini-3.6-flash-lite”")


@pytest.mark.parametrize("raw", [OPENROUTER_IGNORED, OPENROUTER_PRIVACY,
                                 "HTTP 403: model is not in your account's allowed-providers list"])
def test_openrouter_routing_wording(raw):
    why = forge.explain_provider_error(raw, model="z-ai/glm-5.3")
    assert why.startswith("OpenRouter has no provider it is allowed to route this model to")
    assert "Settings → Privacy" in why


def test_bundle_result_names_the_requested_model():
    class Res:
        ok = False
        bundle = None
        log = ['endpoint returned HTTP 404: {"code": "model_not_found"}']
    with pytest.raises(forge.ForgeError) as e:
        forge._bundle_result(Res(), model="gpt-7")
    assert "“gpt-7”" in str(e.value)
