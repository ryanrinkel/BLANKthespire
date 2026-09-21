"""The generic OpenAI-images backend (Gemini + xAI presets) and the chroma key — fully offline.

Every HTTP layer is stubbed: no test here may reach a real API, and no Gemini/xAI key exists anyway.
What is pinned: the request shape per asset kind, PNG normalization from a JPEG reply, the sprite's
green-backdrop prompt + keyed alpha, the price table, key precedence, graceful failure, registration,
and the pack estimate the website's cost summary is built on."""
import base64
import contextlib
import io
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from btsgen.art import ClassArt, ImageRequest, StyleProfile, available_backends, forge_splash, forge_sprite, get_backend
from btsgen.art import keying
from btsgen.art.backends import openai_images as oai
from btsgen.art.backends.openai_images import PRESETS, ImagesPreset, OpenAIImagesBackend, estimate_pack


@pytest.fixture(autouse=True)
def _no_real_keys(monkeypatch):
    """Nothing here may reach a real API or pick up a developer's shell config."""
    for k in ("GEMINI_API_KEY", "XAI_API_KEY", "BTSGEN_IMAGE_BACKEND", "BTSGEN_PROMPT_ENRICH",
              "BTSGEN_GEMINI_MODEL", "BTSGEN_GEMINI_SPRITE_MODEL", "BTSGEN_GEMINI_CARD_MODEL",
              "BTSGEN_XAI_MODEL", "BTSGEN_XAI_SPRITE_MODEL", "BTSGEN_XAI_CARD_MODEL"):
        monkeypatch.delenv(k, raising=False)


# --- fixtures -------------------------------------------------------------------------------------

def _png(w: int, h: int, color=(30, 40, 60)) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg(w: int, h: int, color=(180, 60, 40)) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _green_field_with_square(size=64, square=(20, 20, 44, 44), blur=1.0) -> bytes:
    """A synthetic 'vendor sprite': flat #00FF00 with a red subject in the middle. Blurred so the
    subject's edge is anti-aliased green/red — the fringe the key and the despill exist for."""
    from PIL import Image, ImageDraw, ImageFilter
    im = Image.new("RGB", (size, size), (0, 255, 0))
    ImageDraw.Draw(im).rectangle(square, fill=(220, 30, 30))
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _fake_response(monkeypatch, seen: dict, image: bytes, shape="b64"):
    """Stub urlopen: capture the POST (url/body/headers) and hand back an images response. `shape`
    'url' returns a url item instead, and the follow-up GET returns the bytes."""
    if shape == "b64":
        body = json.dumps({"data": [{"b64_json": base64.b64encode(image).decode()}]}).encode()
    else:
        body = json.dumps({"data": [{"url": "https://example.invalid/i.png"}]}).encode()

    @contextlib.contextmanager
    def fake_urlopen(request, timeout=0):
        if isinstance(request, str):          # the url-item follow-up fetch
            seen["_fetched"] = request
            payload = image
        else:
            seen.clear()
            seen.update(json.loads(request.data.decode()))
            seen["_url"] = request.full_url
            seen["_headers"] = {k.lower(): v for k, v in request.header_items()}
            payload = body

        class R:
            def read(self_inner):
                return payload
        yield R()

    monkeypatch.setattr(oai, "urlopen", fake_urlopen)
    return seen


def _card_request(tmp_path, **kw):
    return ImageRequest(prompt="a gaunt puppet welded into its own armour", kind="card",
                        out_path=tmp_path / "card.png", size=(1536, 1024), **kw)


# --- registration + keys --------------------------------------------------------------------------

def test_both_presets_are_registered_and_inert_without_a_key(monkeypatch):
    for name, env_key, label in (("gemini", "GEMINI_API_KEY", "Google Gemini"), ("xai", "XAI_API_KEY", "xAI")):
        assert name in available_backends()
        be = get_backend(name)
        assert be.name == name and be.preset.env_key == env_key and be.preset.label == label
        assert be.available() is False
        monkeypatch.setenv(env_key, "k-test")
        assert be.available() is True
        monkeypatch.delenv(env_key)


def test_constructor_key_beats_the_env_and_is_what_gets_sent(tmp_path, monkeypatch):
    """The website builds one backend per BYOK forge around the user's own key."""
    monkeypatch.setenv("GEMINI_API_KEY", "k-SERVER")
    be = OpenAIImagesBackend("gemini", api_key="k-USER")
    assert be._key() == "k-USER"
    assert OpenAIImagesBackend("gemini")._key() == "k-SERVER"
    seen = _fake_response(monkeypatch, {}, _png(6, 4))
    res = forge_splash(ClassArt(class_id="u", name="U"), backend=be, out_dir=tmp_path)
    assert res.ok and seen["_headers"]["authorization"] == "Bearer k-USER"
    # a blank ctor key means "not given" and falls back to the env
    monkeypatch.delenv("GEMINI_API_KEY")
    assert OpenAIImagesBackend("gemini", api_key="  ").available() is False


def test_no_key_is_graceful_and_never_touches_the_network(tmp_path, monkeypatch):
    def explode(*a, **kw):
        raise AssertionError("keyless backend must not open a connection")

    monkeypatch.setattr(oai, "urlopen", explode)
    for name, env_key in (("gemini", "GEMINI_API_KEY"), ("xai", "XAI_API_KEY")):
        # the orchestrator gates on available() first, so a keyless preset never even builds a request
        res = forge_splash(ClassArt(class_id="x", name="X"), backend=name, out_dir=tmp_path)
        assert not res.ok and "not available" in (res.error or "")
        # and generate() called directly is just as graceful, naming the env var to set
        direct = get_backend(name).generate(
            ImageRequest(prompt="p", out_path=tmp_path / f"{name}.png", size=(1024, 576)))
        assert not direct.ok and env_key in (direct.error or "")
    assert not list(tmp_path.glob("*.png"))


# --- request shape --------------------------------------------------------------------------------

def test_gemini_splash_request_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k-test")
    seen = _fake_response(monkeypatch, {}, _png(12, 8))
    res = forge_splash(ClassArt(class_id="cryo", name="Cryo"), backend="gemini",
                       style=StyleProfile(name="t", size=(1024, 576)), out_dir=tmp_path)
    assert res.ok and res.backend == "gemini" and res.model == "gemini-2.5-flash-image"
    assert seen["_url"] == "https://generativelanguage.googleapis.com/v1beta/openai/images/generations"
    assert seen["model"] == "gemini-2.5-flash-image" and seen["n"] == 1
    assert seen["response_format"] == "b64_json"
    # the kind map is authoritative: a 16:9 style still asks for the mod's 3:2 splash box
    assert seen["aspect_ratio"] == "3:2"
    assert seen["_headers"]["authorization"] == "Bearer k-test"
    assert seen["_headers"]["content-type"] == "application/json"
    assert "#00FF00" not in seen["prompt"]  # opaque scene: no backdrop instruction
    assert (res.width, res.height) == (12, 8)  # measured from the DECODED image
    assert res.cost_usd == 0.039
    meta = json.loads((tmp_path / "cryo.splash.meta.json").read_text())
    assert meta["backend"] == "gemini" and meta["model"] == "gemini-2.5-flash-image"


def test_xai_card_request_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    seen = _fake_response(monkeypatch, {}, _png(9, 6))
    res = get_backend("xai").generate(_card_request(tmp_path))
    assert res.ok and res.model == "grok-imagine-image" and res.cost_usd == 0.02
    assert seen["_url"] == "https://api.x.ai/v1/images/generations"
    assert seen["aspect_ratio"] == "3:2" and seen["response_format"] == "b64_json"
    assert seen["_headers"]["authorization"] == "Bearer xai-test"


def test_sprite_is_2_3_and_asks_for_the_green_backdrop(tmp_path, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    seen = _fake_response(monkeypatch, {}, _green_field_with_square())
    res = forge_sprite(ClassArt(class_id="cryo", name="Cryo"), backend="xai", out_dir=tmp_path)
    assert res.ok and seen["aspect_ratio"] == "2:3"
    # neither vendor does background=transparent, so the alpha is bought with a prompt + a chroma key
    assert "background" not in seen
    assert "#00FF00" in seen["prompt"] and oai.BACKDROP_PROMPT.strip() in seen["prompt"]


def test_sprite_file_is_rgba_with_transparent_corners(tmp_path, monkeypatch):
    from PIL import Image
    monkeypatch.setenv("GEMINI_API_KEY", "k-test")
    _fake_response(monkeypatch, {}, _green_field_with_square())
    res = forge_sprite(ClassArt(class_id="cryo", name="Cryo"), backend="gemini", out_dir=tmp_path)
    assert res.ok
    with Image.open(res.path) as im:
        assert im.mode == "RGBA" and im.size == (64, 64)
        px = im.load()
        for corner in ((0, 0), (63, 0), (0, 63), (63, 63)):
            assert px[corner][3] == 0, f"backdrop corner {corner} survived the key"
        r, g, b, a = px[32, 32]
        assert a == 255 and r > 150 and g < 80  # the subject is intact


# --- normalization --------------------------------------------------------------------------------

def test_jpeg_reply_is_normalized_to_png_with_decoded_dimensions(tmp_path, monkeypatch):
    """Unlike the openrouter backend (which rejects non-PNG), this one converts — Gemini may return
    either and xAI is likely JPEG. The mod's LoadPngFromBuffer must still get a real PNG."""
    monkeypatch.setenv("GEMINI_API_KEY", "k-test")
    _fake_response(monkeypatch, {}, _jpeg(48, 32))
    out = tmp_path / "s.png"
    res = get_backend("gemini").generate(
        ImageRequest(prompt="p", out_path=out, size=(1536, 1024), kind="splash"))
    assert res.ok and (res.width, res.height) == (48, 32)
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_a_url_only_item_is_fetched_once(tmp_path, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    seen = _fake_response(monkeypatch, {}, _png(5, 5), shape="url")
    res = get_backend("xai").generate(
        ImageRequest(prompt="p", out_path=tmp_path / "u.png", size=(1024, 1024), kind="splash"))
    assert res.ok and (res.width, res.height) == (5, 5)
    assert seen["_fetched"] == "https://example.invalid/i.png"


# --- prices + model resolution --------------------------------------------------------------------

def test_price_per_model_and_env_override_picks_a_different_model_and_price(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k-test")
    be = get_backend("gemini")
    req = _card_request(tmp_path)
    assert be.model_for(req) == "gemini-2.5-flash-image" and be.price_for(req) == 0.039
    monkeypatch.setenv("BTSGEN_GEMINI_CARD_MODEL", "gemini-3-pro-image-preview")
    assert be.model_for(req) == "gemini-3-pro-image-preview" and be.price_for(req) == 0.134
    # a ctor pin still beats the env (the A/B harness path)
    pinned = OpenAIImagesBackend("gemini", api_key="k", card_model="gemini-3.1-flash-lite-image")
    assert pinned.model_for(req) == "gemini-3.1-flash-lite-image" and pinned.price_for(req) == 0.0336
    # an unknown model is unpriced rather than guessed, so the ledger records no cost
    assert PRESETS["gemini"].price_for_model("gemini-whatever-next") is None
    assert PRESETS["xai"].price_for_model("grok-imagine-image-quality") == 0.05


def test_env_overrides_are_per_kind(tmp_path, monkeypatch):
    monkeypatch.setenv("BTSGEN_XAI_MODEL", "grok-imagine-image-quality")
    monkeypatch.setenv("BTSGEN_XAI_SPRITE_MODEL", "grok-imagine-image-2.0")
    preset = PRESETS["xai"]
    assert preset.model_for_kind("splash") == "grok-imagine-image-quality"
    assert preset.model_for_kind("sprite") == "grok-imagine-image-2.0"
    assert preset.model_for_kind("card") == "grok-imagine-image"  # untouched


def test_ratio_falls_back_to_nearest_when_the_vendor_lacks_the_kind_tag():
    square_only = ImagesPreset(name="t", base_url="https://x/v1", models=dict(PRESETS["xai"].models),
                               prices={}, ratios=("1:1", "9:16"), env_prefix="BTSGEN_T",
                               env_key="T_KEY", label="T")
    assert square_only.ratio_for_kind("splash", (1536, 1024)) == "1:1"   # 3:2 unavailable -> nearest
    assert square_only.ratio_for_kind("sprite", (1024, 1536)) == "9:16"
    assert PRESETS["gemini"].ratio_for_kind("sprite", (1024, 1536)) == "2:3"


def test_estimate_pack_is_the_number_the_cost_summary_shows():
    g = estimate_pack("gemini", 34)
    assert g["images"] == 36 and g["total_usd"] == 1.404
    assert g["models"] == {k: "gemini-2.5-flash-image" for k in ("splash", "sprite", "card")}
    assert g["per_image_usd"]["card"] == 0.039
    x = estimate_pack("xai", 34)
    assert x["images"] == 36 and x["total_usd"] == 0.72 and x["per_image_usd"]["splash"] == 0.02


def test_estimate_pack_follows_the_env(monkeypatch):
    monkeypatch.setenv("BTSGEN_GEMINI_CARD_MODEL", "gemini-3-pro-image-preview")
    est = estimate_pack("gemini", 2)
    assert est["models"]["card"] == "gemini-3-pro-image-preview"
    assert est["total_usd"] == round(0.039 * 2 + 0.134 * 2, 6)


# --- failure modes --------------------------------------------------------------------------------

def test_http_error_is_returned_not_raised(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k-test")

    def boom(request, timeout=0):
        raise HTTPError("u", 429, "Too Many Requests", None, io.BytesIO(b'{"error":"quota"}'))

    monkeypatch.setattr(oai, "urlopen", boom)
    res = forge_splash(ClassArt(class_id="e", name="E"), backend="gemini", out_dir=tmp_path)
    assert not res.ok and res.error.startswith("HTTP 429") and "quota" in res.error
    assert not (tmp_path / "e.splash.png").exists()


def test_unexpected_response_shape_is_graceful(tmp_path, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xai-test")

    @contextlib.contextmanager
    def fake(request, timeout=0):
        class R:
            def read(self_inner):
                return b'{"error": {"message": "nope"}}'
        yield R()

    monkeypatch.setattr(oai, "urlopen", fake)
    res = get_backend("xai").generate(_card_request(tmp_path))
    assert not res.ok and "unexpected response shape" in res.error


def test_undecodable_image_is_graceful(tmp_path, monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    _fake_response(monkeypatch, {}, b"not-an-image-at-all")
    res = get_backend("xai").generate(_card_request(tmp_path))
    assert not res.ok and "could not decode image" in res.error
    assert not (tmp_path / "card.png").exists()


# --- the chroma key itself -------------------------------------------------------------------------

def test_chroma_key_hard_edge_square(tmp_path):
    """A hard-edge red square on flat green: the whole backdrop keys to 0, the interior stays fully
    opaque, and every partially transparent edge pixel is despilled (green no higher than the mean of
    red and blue) so the cut-out has no lime halo."""
    src = _green_field_with_square(size=48, square=(14, 14, 33, 33), blur=0)
    img = keying.chroma_key(src)
    assert img.mode == "RGBA" and img.size == (48, 48)
    px = img.load()
    for spot in ((0, 0), (47, 47), (24, 2), (2, 24)):
        assert px[spot][3] == 0, f"backdrop pixel {spot} was not keyed out"
    assert px[24, 24][3] == 255  # well inside the subject
    soft = 0
    for y in range(48):
        for x in range(48):
            r, g, b, a = px[x, y]
            if 0 < a < 255:
                soft += 1
                assert g <= (r + b) // 2 + 1, f"spill left at {(x, y)}: {(r, g, b, a)}"
    assert soft > 0, "the 1px erode + feather must leave a soft edge to despill"


def test_chroma_key_accepts_bytes_paths_and_images(tmp_path):
    from PIL import Image
    raw = _green_field_with_square(size=32, square=(10, 10, 21, 21), blur=0)
    src = tmp_path / "in.png"
    src.write_bytes(raw)
    with Image.open(src) as im:
        im.load()
        from_image = keying.chroma_key(im)
    assert keying.chroma_key(raw).size == from_image.size == (32, 32)
    out = keying.key_file(src, tmp_path / "sub" / "out.png")
    assert Path(out).exists()
    with Image.open(out) as im:
        assert im.mode == "RGBA" and im.load()[0, 0][3] == 0


def test_chroma_key_leaves_a_non_backdrop_image_alone():
    """Tolerance must not eat art that happens to contain green — only the flat key colour."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), (40, 120, 70)).save(buf, format="PNG")  # a muted forest green
    img = keying.chroma_key(buf.getvalue())
    assert img.load()[8, 8][3] == 255
