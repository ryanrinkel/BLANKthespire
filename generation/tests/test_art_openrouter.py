"""OpenRouter image backend — offline (urlopen is mocked; no real API calls)."""
import base64
import contextlib
import json

from btsgen.art import ClassArt, StyleProfile, available_backends, forge_splash, forge_sprite, get_backend
from btsgen.art.backends import openrouter as orb
from btsgen.art.png import encode_rgb


def _fake_response(monkeypatch, seen: dict, png: bytes, cost=0.03):
    body = json.dumps({"data": [{"b64_json": base64.b64encode(png).decode(), "media_type": "image/png"}],
                       "usage": {"cost": cost}}).encode()

    @contextlib.contextmanager
    def fake_urlopen(request, timeout=0):
        seen.clear()
        seen.update(json.loads(request.data.decode()))
        seen["_headers"] = {k.lower(): v for k, v in request.header_items()}

        class R:
            def read(self_inner):
                return body
        yield R()

    monkeypatch.setattr(orb, "urlopen", fake_urlopen)


def test_registered_and_key_gated(monkeypatch):
    assert "openrouter" in available_backends()
    be = get_backend("openrouter")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert be.available() is False
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    assert be.available() is True


def test_no_key_is_graceful(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    res = forge_splash(ClassArt(class_id="x", name="X"), backend="openrouter", out_dir=tmp_path)
    assert not res.ok and "key" in (res.error or "").lower()
    assert not list(tmp_path.glob("*.png"))


def test_nearest_ratio():
    assert orb.nearest_ratio((1024, 576)) == "16:9"
    assert orb.nearest_ratio((1536, 1024)) == "3:2"
    assert orb.nearest_ratio((1024, 1536)) == "2:3"
    assert orb.nearest_ratio((1000, 1000)) == "1:1"


def test_splash_payload_and_result(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.delenv("BTSGEN_OPENROUTER_MODEL", raising=False)
    monkeypatch.delenv("BTSGEN_OPENROUTER_RESOLUTION", raising=False)
    monkeypatch.delenv("BTSGEN_IMAGE_QUALITY", raising=False)
    seen: dict = {}
    _fake_response(monkeypatch, seen, encode_rgb(4, 2, bytes(4 * 2 * 3)), cost=0.03)
    res = forge_splash(ClassArt(class_id="cryo", name="Cryo"), backend="openrouter",
                       style=StyleProfile(name="t", size=(1024, 576)), out_dir=tmp_path)
    assert res.ok and res.backend == "openrouter" and res.model == orb.DEFAULT_MODEL
    assert (res.width, res.height) == (4, 2)  # measured from the returned PNG, not assumed
    assert res.cost_usd == 0.03  # metered cost from the response
    # 2026-09-18: the splash default moved off qwen/qwen-image-3 to the A/B winner (Qwen is one env flip away)
    assert orb.DEFAULT_MODEL == "openai/gpt-5-image-mini" and seen["quality"] == "low"
    assert seen["model"] == orb.DEFAULT_MODEL and seen["aspect_ratio"] == "16:9"
    assert seen["output_format"] == "png" and "background" not in seen and "resolution" not in seen
    assert "input_references" not in seen
    assert seen["_headers"]["authorization"] == "Bearer sk-or-test"
    meta = json.loads((tmp_path / "cryo.splash.meta.json").read_text())
    assert meta["model"] == orb.DEFAULT_MODEL and meta["backend"] == "openrouter"


def test_sprite_uses_transparent_capable_model(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.delenv("BTSGEN_OPENROUTER_SPRITE_MODEL", raising=False)
    seen: dict = {}
    _fake_response(monkeypatch, seen, encode_rgb(2, 2, bytes(2 * 2 * 3)))
    res = forge_sprite(ClassArt(class_id="cryo", name="Cryo"), backend="openrouter", out_dir=tmp_path)
    assert res.ok and seen["background"] == "transparent" and seen["aspect_ratio"] == "2:3"
    assert seen["model"] == orb.DEFAULT_SPRITE_MODEL  # the splash model has no alpha output; sprites route elsewhere


def test_env_and_ctor_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("BTSGEN_OPENROUTER_MODEL", "bytedance-seed/seedream-4.5")
    monkeypatch.setenv("BTSGEN_OPENROUTER_RESOLUTION", "2K")
    seen: dict = {}
    _fake_response(monkeypatch, seen, encode_rgb(2, 2, bytes(2 * 2 * 3)))
    forge_splash(ClassArt(class_id="a", name="A"), backend="openrouter", out_dir=tmp_path)
    assert seen["model"] == "bytedance-seed/seedream-4.5" and seen["resolution"] == "2K"
    # an instance pins the model regardless of env (the A/B harness path)
    be = orb.OpenRouterImageBackend(model="black-forest-labs/flux.2-pro", resolution="1K", quality="high")
    forge_splash(ClassArt(class_id="b", name="B"), backend=be, out_dir=tmp_path)
    assert seen["model"] == "black-forest-labs/flux.2-pro" and seen["resolution"] == "1K"
    assert seen["quality"] == "high"


def test_reference_images_become_data_urls(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    ref = tmp_path / "ref.png"
    ref.write_bytes(encode_rgb(1, 1, b"\xff\x00\x00"))
    seen: dict = {}
    _fake_response(monkeypatch, seen, encode_rgb(2, 2, bytes(2 * 2 * 3)))
    style = StyleProfile(name="sts", size=(1024, 576), ref_images=[ref, tmp_path / "missing.png"])
    res = forge_splash(ClassArt(class_id="r", name="R"), backend="openrouter", style=style, out_dir=tmp_path)
    assert res.ok
    refs = seen["input_references"]
    assert len(refs) == 1  # the missing file is skipped, not sent as garbage
    assert refs[0]["type"] == "image_url" and refs[0]["image_url"]["url"].startswith("data:image/png;base64,")


def test_non_png_response_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    seen: dict = {}
    _fake_response(monkeypatch, seen, b"\xff\xd8\xff\xe0not-a-png")
    res = forge_splash(ClassArt(class_id="j", name="J"), backend="openrouter", out_dir=tmp_path)
    assert not res.ok and "non-PNG" in (res.error or "")
    assert not (tmp_path / "j.splash.png").exists()  # never write a mislabeled file the mod can't load
