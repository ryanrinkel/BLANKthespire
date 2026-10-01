"""The BYOK "Load models" filter (forge.filter_models): unfit ids are dropped, tested ones come first."""
import pytest

from conftest import H, login


def _ids(listing):
    return listing["models"]


@pytest.mark.parametrize("mid", [
    "text-embedding-3-large", "gemini-embedding-001", "tts-1-hd", "whisper-1", "gpt-4o-transcribe",
    "gpt-4o-realtime-preview", "gpt-4o-audio-preview", "omni-moderation-latest", "dall-e-3", "gpt-image-1",
    "imagen-4.0-generate-001", "veo-3.0-generate-001", "gemini-2.5-flash-image", "meta-llama/llama-guard-4-12b",
    "gpt-4o-search-preview", "perplexity/sonar-deep-research", "gemini-live-2.5-flash", "babbage-002", "gemini-2.5-flash-native-audio-latest",
    "google/gemma-4-31b-it:free", "llama-3.1-8b-instant", "qwen3:4b", "models/gemma-3-12b-it",
])
def test_unfit_models_are_hidden(mid):
    import forge
    out = forge.filter_models([{"id": mid}])
    assert _ids(out) == [] and out["hidden"] == 1


@pytest.mark.parametrize("mid", [
    "gpt-4o-mini", "gpt-4.1", "claude-sonnet-4-6", "models/gemini-2.5-flash", "gemini-3.7-flash",
    "llama-3.3-70b-versatile", "qwen3.5:397b", "gpt-oss:120b", "mistralai/mixtral-8x7b-instruct",
    "deepseek-chat", "grok-4.3", "glm-5.3", "nousresearch/hermes-4-405b",
])
def test_capable_models_are_kept(mid):
    import forge
    assert _ids(forge.filter_models([{"id": mid}])) == [mid]


def test_openrouter_metadata_is_used():
    import forge
    items = [
        {"id": "a/short", "context_length": 8192},
        {"id": "a/pics", "context_length": 200000, "architecture": {"output_modalities": ["image"]}},
        {"id": "a/fine", "context_length": 200000, "architecture": {"output_modalities": ["text"]}},
    ]
    out = forge.filter_models(items)
    assert _ids(out) == ["a/fine"] and out["hidden"] == 2


def test_tested_models_lead_and_dupes_collapse():
    import forge
    items = [{"id": "zeta-chat"}, {"id": "glm-5.3"}, {"name": "alpha-chat"}, {"id": "glm-5.3"}, "junk", {}]
    out = forge.filter_models(items)
    assert _ids(out) == ["glm-5.3", "alpha-chat", "zeta-chat"]
    assert out["recommended"] == ["glm-5.3"] and out["hidden"] == 0


def test_api_models_returns_filtered_listing(client, app_module, monkeypatch):
    import forge
    monkeypatch.setattr(app_module, "list_models",
                        lambda u, k: forge.filter_models([{"id": "glm-5.3"}, {"id": "tts-1"}]))
    login(client, "models@example.com")
    r = client.post("/api/models", json={"base_url": "https://api.example.com/v1", "api_key": "k"},
                    headers=H)
    assert r.status_code == 200
    assert r.get_json() == {"models": ["glm-5.3"], "recommended": ["glm-5.3"], "hidden": 1}
