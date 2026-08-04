"""Track 2 art skeleton — end-to-end, offline (no API, no Godot project needed)."""
import json
from pathlib import Path

from btsgen.art import (ClassArt, StyleProfile, class_art_from_bundle,
                        class_art_from_disk, forge_splash)


def _is_png(p: Path) -> bool:
    return p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_null_is_default_and_noops(tmp_path):
    res = forge_splash(ClassArt(class_id="x", name="X"), out_dir=tmp_path)  # no backend -> null
    assert res.backend == "null" and not res.ok and res.error
    assert not list(tmp_path.glob("*.png"))


def test_procedural_writes_real_png_and_sidecar(tmp_path):
    art = ClassArt(class_id="cryo", name="The Cryomancer", description="frost", archetypes=["deep_freeze"])
    res = forge_splash(art, backend="procedural", style=StyleProfile(name="t", size=(48, 27)), out_dir=tmp_path)
    assert res.ok and res.cost_usd == 0.0 and (res.width, res.height) == (48, 27)
    out = tmp_path / "cryo.splash.png"
    assert out.exists() and _is_png(out)
    meta = json.loads((tmp_path / "cryo.splash.meta.json").read_text())
    assert meta["class_id"] == "cryo" and meta["backend"] == "procedural" and meta["file"] == "cryo.splash.png"


def test_hue_deterministic_and_distinct():
    a = class_art_from_bundle({"character": {"id": "a", "name": "A"}})
    a2 = class_art_from_bundle({"character": {"id": "a", "name": "A"}})
    b = class_art_from_bundle({"character": {"id": "b", "name": "B"}})
    assert a.hue == a2.hue and a.hue != b.hue


def test_extract_prefers_blueprint_archetypes():
    art = class_art_from_bundle({
        "character": {"id": "c", "name": "C", "description": "d"},
        "blueprint": {"archetypes": [{"id": "x", "name": "Frost"}, "raw"]},
        "concept": "a frost mage",
    })
    assert art.archetypes == ["Frost", "raw"] and art.concept == "a frost mage"


def test_unknown_backend_is_graceful():
    res = forge_splash(ClassArt(class_id="x", name="X"), backend="nope")
    assert not res.ok and "unknown image backend" in (res.error or "")


def test_from_disk_roundtrip(tmp_path):
    (tmp_path / "cryo.json").write_text(json.dumps({"id": "cryo", "name": "The Cryomancer", "description": "frost"}))
    (tmp_path / "cryo.meta.json").write_text(json.dumps({"concept": "freeze", "archetypes": ["deep_freeze"]}))
    art = class_art_from_disk("cryo", characters_dir=tmp_path)
    assert art.name == "The Cryomancer" and art.concept == "freeze" and art.archetypes == ["deep_freeze"]


# --- openai cloud backend (no real API calls) --------------------------------------------------
import base64  # noqa: E402
import contextlib  # noqa: E402

from btsgen.art import available_backends, get_backend  # noqa: E402
from btsgen.art.backends import openai as openai_backend  # noqa: E402
from btsgen.art.png import encode_rgb  # noqa: E402


def test_openai_registered_and_key_gated(monkeypatch):
    assert "openai" in available_backends()
    be = get_backend("openai")
    monkeypatch.delenv("BTSGEN_IMAGE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert be.available() is False
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert be.available() is True


def test_openai_nearest_size():
    assert openai_backend._nearest_size((1024, 576)) == "1536x1024"   # landscape
    assert openai_backend._nearest_size((576, 1024)) == "1024x1536"   # portrait
    assert openai_backend._nearest_size((512, 512)) == "1024x1024"    # square


def test_openai_no_key_is_graceful(tmp_path, monkeypatch):
    monkeypatch.delenv("BTSGEN_IMAGE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    res = forge_splash(ClassArt(class_id="x", name="X"), backend="openai", out_dir=tmp_path)
    # forge_splash gates on available() first, so the message is the orchestrator's — either way: graceful.
    assert not res.ok and "key" in (res.error or "").lower()
    assert not list(tmp_path.glob("*.png"))


def test_openai_generate_writes_png_when_mocked(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    fake_png = encode_rgb(2, 2, bytes(2 * 2 * 3))
    body = json.dumps({"data": [{"b64_json": base64.b64encode(fake_png).decode()}]}).encode()

    @contextlib.contextmanager
    def fake_urlopen(request, timeout=0):
        class R:
            def read(self_inner):
                return body
        yield R()

    monkeypatch.setattr(openai_backend, "urlopen", fake_urlopen)
    res = forge_splash(ClassArt(class_id="cryo", name="Cryo"), backend="openai",
                       style=StyleProfile(name="t", size=(1024, 576)), out_dir=tmp_path)
    assert res.ok and res.backend == "openai" and res.width == 1536 and res.height == 1024
    out = tmp_path / "cryo.splash.png"
    assert out.exists() and _is_png(out)


# --- combat-model sprite (forge_sprite) ---------------------------------------------------------
from btsgen.art import SPRITE_STYLE, forge_sprite, sprite_prompt  # noqa: E402


def test_sprite_style_is_transparent_portrait():
    assert SPRITE_STYLE.transparent is True
    w, h = SPRITE_STYLE.size
    assert h > w  # portrait: a standing figure


def test_sprite_prompt_demands_cutout_full_body():
    art = ClassArt(class_id="cryo", name="The Cryomancer", flavor=["glacier worship"], imagery=["ice staff"])
    p = sprite_prompt(art, SPRITE_STYLE)
    assert "transparent background" in p and "facing right" in p and "whole body" in p
    assert "ice staff" in p  # flavor/imagery carry over like the splash prompt


def test_procedural_sprite_is_rgba_figure(tmp_path):
    art = ClassArt(class_id="cryo", name="The Cryomancer")
    res = forge_sprite(art, backend="procedural", out_dir=tmp_path)
    assert res.ok and res.cost_usd == 0.0
    out = tmp_path / "cryo.sprite.png"
    assert out.exists() and _is_png(out)
    data = out.read_bytes()
    assert data[25] == 6  # IHDR colour type 6 = truecolour with alpha (a real cut-out)
    meta = json.loads((tmp_path / "cryo.sprite.meta.json").read_text())
    assert meta["file"] == "cryo.sprite.png" and meta["backend"] == "procedural"


def test_procedural_sprite_hue_distinct(tmp_path):
    a = forge_sprite(ClassArt(class_id="a", name="A", hue=0.1), backend="procedural", out_dir=tmp_path)
    b = forge_sprite(ClassArt(class_id="b", name="B", hue=0.6), backend="procedural", out_dir=tmp_path)
    assert a.ok and b.ok
    assert (tmp_path / "a.sprite.png").read_bytes() != (tmp_path / "b.sprite.png").read_bytes()


def test_openai_sprite_requests_transparent_background(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    fake_png = encode_rgb(2, 2, bytes(2 * 2 * 3))
    body = json.dumps({"data": [{"b64_json": base64.b64encode(fake_png).decode()}]}).encode()
    seen = {}

    @contextlib.contextmanager
    def fake_urlopen(request, timeout=0):
        seen.update(json.loads(request.data.decode()))

        class R:
            def read(self_inner):
                return body
        yield R()

    monkeypatch.setattr(openai_backend, "urlopen", fake_urlopen)
    res = forge_sprite(ClassArt(class_id="cryo", name="Cryo"), backend="openai", out_dir=tmp_path)
    assert res.ok and seen.get("background") == "transparent" and seen.get("size") == "1024x1536"
    # transparent requests must NOT go to gpt-image-2 — it 400s on background=transparent (live-verified)
    assert seen.get("model") == "gpt-image-1.5"
    assert (tmp_path / "cryo.sprite.png").exists()
    # and the splash path must NOT ask for transparency — and DOES use the flagship model
    seen.clear()
    res2 = forge_splash(ClassArt(class_id="cryo", name="Cryo"), backend="openai", out_dir=tmp_path)
    assert res2.ok and "background" not in seen
    assert seen.get("model") == "gpt-image-2"  # gpt-image-1 retires 2026-10; default must be the successor


# --- optional cheap-LLM prompt enrichment (enrich.py; no real API calls) ------------------------
from btsgen.art import enrich as enrich_mod  # noqa: E402
from btsgen.art.prompt import splash_prompt  # noqa: E402
from btsgen.art.styles import DEFAULT_STYLE  # noqa: E402


def test_enrich_off_by_default_even_with_key(monkeypatch):
    monkeypatch.delenv("BTSGEN_PROMPT_ENRICH", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert enrich_mod.enrich_body(ClassArt(class_id="x", name="X"), "splash") is None


def test_enrich_on_but_keyless_is_none(monkeypatch):
    monkeypatch.setenv("BTSGEN_PROMPT_ENRICH", "1")
    monkeypatch.delenv("BTSGEN_IMAGE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert enrich_mod.enrich_body(ClassArt(class_id="x", name="X"), "splash") is None


def test_enriched_body_replaces_theme_but_keeps_constraints():
    art = ClassArt(class_id="cryo", name="The Cryomancer", description="frost", imagery=["ice staff"])
    p = splash_prompt(art, DEFAULT_STYLE, enriched_body="A hooded glacier priest wreathed in rime.")
    assert "glacier priest" in p and '"The Cryomancer"' in p
    assert "RIGHT" in p and "menu UI" in p          # the layout contract survives enrichment
    assert "ice staff" not in p and "frost" not in p  # raw theme lines are replaced, not doubled


def test_enrich_flows_into_forge_and_sidecar(tmp_path, monkeypatch):
    monkeypatch.setenv("BTSGEN_PROMPT_ENRICH", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    body = json.dumps({"choices": [{"message": {"content": "A hooded glacier priest."}}]}).encode()

    @contextlib.contextmanager
    def fake_urlopen(request, timeout=0):
        class R:
            def read(self_inner):
                return body
        yield R()

    monkeypatch.setattr(enrich_mod, "urlopen", fake_urlopen)
    res = forge_splash(ClassArt(class_id="cryo", name="Cryo"), backend="procedural", out_dir=tmp_path)
    assert res.ok
    meta = json.loads((tmp_path / "cryo.splash.meta.json").read_text())
    assert meta["enriched"] is True and "glacier priest" in meta["prompt"]


def test_enrich_failure_falls_back_to_template(tmp_path, monkeypatch):
    monkeypatch.setenv("BTSGEN_PROMPT_ENRICH", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    @contextlib.contextmanager
    def fake_urlopen(request, timeout=0):
        raise TimeoutError("slow")
        yield  # pragma: no cover

    monkeypatch.setattr(enrich_mod, "urlopen", fake_urlopen)
    res = forge_splash(ClassArt(class_id="cryo", name="Cryo", description="frost"),
                       backend="procedural", out_dir=tmp_path)
    assert res.ok  # enrichment failing must never fail the forge
    meta = json.loads((tmp_path / "cryo.splash.meta.json").read_text())
    assert meta["enriched"] is False and "frost" in meta["prompt"]
