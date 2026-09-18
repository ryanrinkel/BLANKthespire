"""Card art (art/card.py) — style, prompt, per-kind model/quality, the two fallback ladders, the
portrait crop, and one end-to-end run on the keyless procedural backend. Fully offline: every HTTP
layer is stubbed and no test may reach a real API."""
import base64
import contextlib
import io
import json
from urllib.error import HTTPError

import pytest

from btsgen.art import (CARD_PORTRAIT_SIZE, CARD_STYLE, DEFAULT_STYLE, ClassArt, ImageRequest,
                        ImageResult, StyleProfile, card_prompt, forge_card_art, get_backend,
                        portrait_crop_box, resolve_backends)
from btsgen.art import card as card_mod
from btsgen.art.backends import openai as openai_backend
from btsgen.art.backends import openrouter as orb
from btsgen.art.png import encode_rgb

_CARD = {"id": "jack_in_iron", "name": "Jack in Iron", "type": "attack", "rarity": "rare",
         "flavor": "A gaunt puppet welded into its own armour."}


@pytest.fixture(autouse=True)
def _no_real_keys(monkeypatch):
    """Nothing here may ever reach a real API, whatever the developer's shell holds."""
    for k in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "BTSGEN_IMAGE_API_KEY", "BTSGEN_IMAGE_BACKEND",
              "BTSGEN_IMAGE_MODEL", "BTSGEN_IMAGE_SPRITE_MODEL", "BTSGEN_IMAGE_CARD_MODEL",
              "BTSGEN_IMAGE_QUALITY", "BTSGEN_IMAGE_SPRITE_QUALITY", "BTSGEN_IMAGE_CARD_QUALITY",
              "BTSGEN_OPENROUTER_MODEL", "BTSGEN_OPENROUTER_SPRITE_MODEL",
              "BTSGEN_OPENROUTER_CARD_MODEL", "BTSGEN_OPENROUTER_CARD_MODELS",
              "BTSGEN_OPENROUTER_RESOLUTION", "BTSGEN_PROMPT_ENRICH", "BTSGEN_CARD_ART_COLORS"):
        monkeypatch.delenv(k, raising=False)


# --- 3a. style + prompt ---------------------------------------------------------------------------

def test_card_style_is_3_2_png_sharing_the_house_look():
    assert CARD_STYLE.size == (1536, 1024) and CARD_STYLE.out_format == "png"
    # the SAME descriptive STS ink/cel sentence as the splash: one class, one artwork
    assert CARD_STYLE.prompt_suffix == DEFAULT_STYLE.prompt_suffix
    for word in ("text", "lettering", "watermark", "ui", "card frame", "border", "logo"):
        assert word in CARD_STYLE.negative
    assert CARD_STYLE.transparent is False


def test_card_prompt_leads_with_name_and_type_and_ends_with_style():
    art = ClassArt(class_id="pyre", name="The Sixgun Pyre")
    p = card_prompt(art, _CARD, CARD_STYLE)
    head = p[:120]
    assert "Jack in Iron" in head and "attack card" in head   # the card IS the subject
    assert head.index("Jack in Iron") < head.index("attack card")
    assert p.endswith(CARD_STYLE.prompt_suffix)               # style suffix is always last
    assert "Single focal subject filling the frame" in p
    assert "no character text" in p


@pytest.mark.parametrize("ctype,word", [("skill", "a skill card"), ("power", "a power card"),
                                        ("attack", "an attack card"), ("", "a card"),
                                        ("curse", "a card")])
def test_card_prompt_names_every_type(ctype, word):
    p = card_prompt(ClassArt(class_id="x", name="X"), {"name": "Ward", "type": ctype}, CARD_STYLE)
    assert f'"Ward", {word} in a dark-fantasy deckbuilder' in p


def test_card_prompt_carries_card_prose_and_class_look():
    art = ClassArt(class_id="pyre", name="The Sixgun Pyre", concept="a cowboy who burns his own ghosts",
                   flavor=["frontier funeral rites"], imagery=["brass revolver", "ash-grey duster"])
    p = card_prompt(art, dict(_CARD, description="Deal 12 damage."), CARD_STYLE)
    assert "Deal 12 damage." in p and "gaunt puppet" in p            # the card's own prose
    assert 'The player asked for: "a cowboy who burns his own ghosts"' in p  # verbatim concept
    assert "frontier funeral rites" in p and "brass revolver" in p   # class flavor/imagery motifs
    assert p.index("Jack in Iron") < p.index("player asked for")     # the CARD leads, the class dresses


def test_card_prompt_survives_a_bare_card():
    p = card_prompt(ClassArt(class_id="x", name="X"), {"id": "ember_jab"}, CARD_STYLE)
    assert "ember_jab" in p and p.endswith(CARD_STYLE.prompt_suffix)


def test_nearest_ratio_snaps_card_size_to_3_2():
    # 4:3 is rejected by the OpenAI image family on OpenRouter; 1536x1024 must land on 3:2
    assert orb.nearest_ratio((1536, 1024)) == "3:2"
    assert orb.nearest_ratio(CARD_STYLE.size) == "3:2"


# --- 3b. per-kind model + quality -----------------------------------------------------------------

def _req(kind: str, tmp_path, transparent=False) -> ImageRequest:
    return ImageRequest(prompt="p", out_path=tmp_path / "o.png", size=CARD_STYLE.size,
                        transparent=transparent, kind=kind)


def test_openrouter_models_and_quality_per_kind(tmp_path):
    be = orb.OpenRouterImageBackend()
    assert be.model_for(_req("splash", tmp_path)) == "openai/gpt-5-image-mini"  # was qwen before 2026-09-18
    assert be.model_for(_req("sprite", tmp_path, transparent=True)) == orb.DEFAULT_SPRITE_MODEL
    assert be.model_for(_req("card", tmp_path)) == "openai/gpt-5-image-mini"
    assert be.quality_for(_req("splash", tmp_path)) == "low"
    assert be.quality_for(_req("card", tmp_path)) == "low"
    assert be.quality_for(_req("sprite", tmp_path, transparent=True)) == "low"  # falls back to splash


def test_openrouter_kind_envs_are_independent(tmp_path, monkeypatch):
    monkeypatch.setenv("BTSGEN_OPENROUTER_MODEL", "qwen/qwen-image-3")
    monkeypatch.setenv("BTSGEN_OPENROUTER_SPRITE_MODEL", "sprite/model")
    monkeypatch.setenv("BTSGEN_OPENROUTER_CARD_MODEL", "card/model")
    monkeypatch.setenv("BTSGEN_IMAGE_QUALITY", "high")
    monkeypatch.setenv("BTSGEN_IMAGE_SPRITE_QUALITY", "medium")
    monkeypatch.setenv("BTSGEN_IMAGE_CARD_QUALITY", "low")
    be = orb.OpenRouterImageBackend()
    assert be.model_for(_req("splash", tmp_path)) == "qwen/qwen-image-3"
    assert be.model_for(_req("sprite", tmp_path, transparent=True)) == "sprite/model"
    assert be.model_for(_req("card", tmp_path)) == "card/model"
    assert be.quality_for(_req("splash", tmp_path)) == "high"
    assert be.quality_for(_req("sprite", tmp_path, transparent=True)) == "medium"
    assert be.quality_for(_req("card", tmp_path)) == "low"


def test_openai_models_and_quality_per_kind(tmp_path, monkeypatch):
    assert openai_backend.model_for(_req("splash", tmp_path)) == "gpt-image-2"
    assert openai_backend.model_for(_req("sprite", tmp_path, transparent=True)) == "gpt-image-1.5"
    assert openai_backend.model_for(_req("card", tmp_path)) == "gpt-image-1-mini"
    assert openai_backend.quality_for(_req("splash", tmp_path)) == "medium"
    assert openai_backend.quality_for(_req("card", tmp_path)) == "low"
    monkeypatch.setenv("BTSGEN_IMAGE_CARD_MODEL", "gpt-image-1.5")
    monkeypatch.setenv("BTSGEN_IMAGE_CARD_QUALITY", "medium")
    assert openai_backend.model_for(_req("card", tmp_path)) == "gpt-image-1.5"
    assert openai_backend.quality_for(_req("card", tmp_path)) == "medium"
    assert openai_backend.model_for(_req("splash", tmp_path)) == "gpt-image-2"  # untouched


def test_openai_card_request_is_priced_and_landscape(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    seen: dict = {}
    body = json.dumps({"data": [{"b64_json": base64.b64encode(encode_rgb(2, 2, bytes(12))).decode()}]}).encode()

    @contextlib.contextmanager
    def fake_urlopen(request, timeout=0):
        seen.update(json.loads(request.data.decode()))

        class R:
            def read(self_inner):
                return body
        yield R()

    monkeypatch.setattr(openai_backend, "urlopen", fake_urlopen)
    res = forge_card_art(ClassArt(class_id="pyre", name="Pyre"), _CARD, backend="openai",
                         out_dir=tmp_path, portrait_size=None)
    assert res.ok and seen["model"] == "gpt-image-1-mini" and seen["quality"] == "low"
    assert seen["size"] == "1536x1024" and "background" not in seen
    assert res.cost_usd == 0.004  # advisory rate-table estimate (openrouter meters the real number)


# --- 3c. the two fallback ladders -----------------------------------------------------------------

class _FakeBackend:
    """A registered-shape backend that records the requests it is handed."""

    def __init__(self, name, ok=True, available=True, error="boom"):
        self.name, self._ok, self._available, self._error = name, ok, available, error
        self.seen: list[ImageRequest] = []

    def available(self) -> bool:
        return self._available

    def generate(self, req: ImageRequest) -> ImageResult:
        self.seen.append(req)
        if not self._ok:
            return ImageResult(ok=False, backend=self.name, error=self._error)
        req.out_path.parent.mkdir(parents=True, exist_ok=True)
        req.out_path.write_bytes(encode_rgb(6, 4, bytes(6 * 4 * 3)))
        return ImageResult(ok=True, backend=self.name, model=f"{self.name}/m", path=req.out_path,
                           cost_usd=0.004, width=6, height=4)


def test_env_backend_list_resolves_in_order(monkeypatch):
    monkeypatch.setenv("BTSGEN_IMAGE_BACKEND", "openrouter,openai")
    assert [b.name for b in resolve_backends(None)] == ["openrouter", "openai"]
    assert get_backend(None).name == "openrouter"          # the single-backend API still works
    monkeypatch.setenv("BTSGEN_IMAGE_BACKEND", " procedural , null ")
    assert [b.name for b in resolve_backends(None)] == ["procedural", "null"]


def test_backend_chain_falls_through_to_the_first_ok(tmp_path):
    down = _FakeBackend("down", ok=False, error="HTTP 503: upstream")
    keyless = _FakeBackend("keyless", available=False)
    good = _FakeBackend("good")
    res = forge_card_art(ClassArt(class_id="pyre", name="Pyre"), _CARD,
                         backend=[down, keyless, good], out_dir=tmp_path, portrait_size=None)
    assert res.ok and res.backend == "good" and res.model == "good/m"
    assert len(down.seen) == 1 and len(good.seen) == 1 and keyless.seen == []  # unavailable = never called
    assert res.path.name == "pyre.card.jack_in_iron.png"


def test_backend_chain_reports_every_tier_when_all_fail(tmp_path):
    a = _FakeBackend("a", ok=False, error="HTTP 500")
    b = _FakeBackend("b", ok=False, error="non-PNG")
    res = forge_card_art(ClassArt(class_id="pyre", name="Pyre"), _CARD, backend=[a, b],
                         out_dir=tmp_path)
    assert not res.ok and "a: HTTP 500" in res.error and "b: non-PNG" in res.error
    assert not list(tmp_path.glob("*.png"))


def test_unknown_backend_in_a_list_is_loud_but_graceful(tmp_path):
    res = forge_card_art(ClassArt(class_id="pyre", name="Pyre"), _CARD,
                         backend="procedural,nope", out_dir=tmp_path)
    assert not res.ok and "unknown image backend 'nope'" in (res.error or "")


def test_request_carries_the_card_kind(tmp_path):
    be = _FakeBackend("probe")
    forge_card_art(ClassArt(class_id="pyre", name="Pyre"), _CARD, backend=be, out_dir=tmp_path,
                   portrait_size=None)
    assert be.seen[0].kind == "card" and be.seen[0].transparent is False
    assert be.seen[0].size == CARD_STYLE.size


def _ok_body(cost=0.0038, png=None):
    png = png or encode_rgb(6, 4, bytes(6 * 4 * 3))
    return json.dumps({"data": [{"b64_json": base64.b64encode(png).decode(), "media_type": "image/png"}],
                       "usage": {"cost": cost}}).encode()


def _script(monkeypatch, steps, seen):
    """Stub OpenRouter's HTTP layer with an ordered script of responses/exceptions."""
    it = iter(steps)

    @contextlib.contextmanager
    def fake_urlopen(request, timeout=0):
        body = json.loads(request.data.decode())
        seen.append((body["model"], body["quality"]))
        try:
            step = next(it)
        except StopIteration:
            raise AssertionError(f"unscripted OpenRouter call #{len(seen)} for {body['model']}") from None
        if isinstance(step, Exception):
            raise step

        class R:
            def read(self_inner):
                return step
        yield R()

    monkeypatch.setattr(orb, "urlopen", fake_urlopen)


def _http(code: int) -> HTTPError:
    return HTTPError("https://openrouter.ai/api/v1/images", code, "err", {}, io.BytesIO(b"upstream"))


def test_card_model_ladder_retries_once_then_falls_to_flux(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    seen: list = []
    _script(monkeypatch, [_http(502), _http(502), _ok_body()], seen)
    res = forge_card_art(ClassArt(class_id="pyre", name="Pyre"), _CARD, backend="openrouter",
                         out_dir=tmp_path, portrait_size=None)
    assert res.ok and res.model == "black-forest-labs/flux.2-klein-4b"
    assert [m for m, _ in seen] == ["openai/gpt-5-image-mini", "openai/gpt-5-image-mini",
                                    "black-forest-labs/flux.2-klein-4b"]
    assert seen[0][1] == "low"  # the '@low' suffix on the ladder entry
    assert res.cost_usd == 0.0038  # metered, straight off the response


def test_card_kind_asks_the_openai_family_for_an_opaque_scene(tmp_path, monkeypatch):
    """gpt-5-image-mini returned half-transparent cut-outs when nothing was asked (2026-09-18); a card
    portrait is an opaque scene like shipped STS art. FLUX (the fallback rung) does not know the param."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.delenv("BTSGEN_IMAGE_CARD_BACKGROUND", raising=False)
    bodies: list = []
    real = orb.OpenRouterImageBackend.build_payload

    def spy(self, req, **kw):
        body = real(self, req, **kw)
        bodies.append(body)
        return body
    monkeypatch.setattr(orb.OpenRouterImageBackend, "build_payload", spy)
    seen: list = []
    _script(monkeypatch, [_http(502), _http(502), _ok_body()], seen)
    res = forge_card_art(ClassArt(class_id="pyre", name="Pyre"), _CARD, backend="openrouter",
                         out_dir=tmp_path, portrait_size=None)
    assert res.ok
    by_model = {b["model"]: b for b in bodies}
    assert by_model["openai/gpt-5-image-mini"]["background"] == "opaque"
    assert "background" not in by_model["black-forest-labs/flux.2-klein-4b"]
    # env "auto" (or empty) = let the model decide, as before
    monkeypatch.setenv("BTSGEN_IMAGE_CARD_BACKGROUND", "auto")
    body = real(orb.OpenRouterImageBackend(), ImageRequest(prompt="x", out_path=tmp_path / "x.png", size=(1536, 1024), kind="card"),
                model="openai/gpt-5-image-mini")
    assert "background" not in body


def test_card_ladder_skips_the_retry_on_a_hard_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    seen: list = []
    _script(monkeypatch, [_http(400), _ok_body()], seen)  # 400 fails identically twice — don't pay twice
    res = forge_card_art(ClassArt(class_id="pyre", name="Pyre"), _CARD, backend="openrouter",
                         out_dir=tmp_path, portrait_size=None)
    assert res.ok and [m for m, _ in seen] == ["openai/gpt-5-image-mini",
                                               "black-forest-labs/flux.2-klein-4b"]


def test_card_ladder_env_override_and_per_entry_quality(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("BTSGEN_OPENROUTER_CARD_MODELS", "a/one@medium,b/two")
    monkeypatch.setenv("BTSGEN_IMAGE_CARD_QUALITY", "high")
    seen: list = []
    _script(monkeypatch, [_http(500), _http(500), _ok_body()], seen)
    res = forge_card_art(ClassArt(class_id="pyre", name="Pyre"), _CARD, backend="openrouter",
                         out_dir=tmp_path, portrait_size=None)
    assert res.ok and seen == [("a/one", "medium"), ("a/one", "medium"), ("b/two", "high")]


def test_single_card_model_env_keeps_the_safety_net(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("BTSGEN_OPENROUTER_CARD_MODEL", "pinned/model")  # the droplet's .env shape
    seen: list = []
    _script(monkeypatch, [_http(429), _http(429), _ok_body()], seen)
    res = forge_card_art(ClassArt(class_id="pyre", name="Pyre"), _CARD, backend="openrouter",
                         out_dir=tmp_path, portrait_size=None)
    assert res.ok
    assert [m for m, _ in seen] == ["pinned/model", "pinned/model", "black-forest-labs/flux.2-klein-4b"]


def test_card_ladder_is_bounded_and_then_hands_off(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("BTSGEN_OPENROUTER_CARD_MODELS", "a/1,b/2,c/3,d/4,e/5,f/6")
    seen: list = []
    _script(monkeypatch, [_http(500)] * orb._MAX_CARD_ATTEMPTS, seen)
    res = forge_card_art(ClassArt(class_id="pyre", name="Pyre"), _CARD, backend="openrouter",
                         out_dir=tmp_path, portrait_size=None)
    assert not res.ok and len(seen) == orb._MAX_CARD_ATTEMPTS  # never loops the whole catalog


def test_splash_and_sprite_never_use_the_card_ladder(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    from btsgen.art import forge_splash
    seen: list = []
    _script(monkeypatch, [_http(500)], seen)  # exactly ONE call is scripted; a second would assert
    res = forge_splash(ClassArt(class_id="pyre", name="Pyre"), backend="openrouter", out_dir=tmp_path)
    assert not res.ok and len(seen) == 1


def test_metered_cost_shapes():
    assert orb.metered_cost({"usage": {"cost": 0.0038}}) == 0.0038
    assert orb.metered_cost({"usage": {"total_cost": 0.02}}) == 0.02
    assert orb.metered_cost({"cost": 0.01}) == 0.01
    assert orb.metered_cost({"usage": {"cost_details": {"upstream_inference_cost": 0.004}}}) == 0.004
    assert orb.metered_cost({"usage": {"prompt_tokens": 12}}) is None
    assert orb.metered_cost(None) is None


# --- 3d. the portrait crop ------------------------------------------------------------------------

def test_crop_box_3_2_to_the_portrait_box():
    # 1536x1024 (1.5) is wider than 1000x760 (~1.3158): trim a sliver off each side, keep full height
    assert portrait_crop_box((1536, 1024)) == (94, 0, 1441, 1024)
    left, top, right, bottom = portrait_crop_box((1536, 1024))
    assert (right - left) / (bottom - top) == pytest.approx(1000 / 760, abs=0.002)


def test_crop_box_non_3_2_inputs():
    assert portrait_crop_box((1024, 1024)) == (0, 123, 1024, 901)        # square -> trim top/bottom
    assert portrait_crop_box((2048, 1024)) == (350, 0, 1697, 1024)       # 2:1 -> trim the sides
    l, t, r, b = portrait_crop_box((800, 1200))                          # portrait input
    assert (l, r) == (0, 800) and (b - t) == 608 and t == 296
    assert portrait_crop_box((1000, 760)) == (0, 0, 1000, 760)           # already exact: no crop
    with pytest.raises(ValueError):
        portrait_crop_box((0, 10))


def _half_transparent_png(w, h) -> bytes:
    """Left half fully transparent, right half opaque red — a stand-in for the cut-outs
    gpt-5-image-mini returns for card art even when nothing asked for transparency."""
    from btsgen.art.png import encode_rgba
    row = bytes((0, 0, 0, 0)) * (w // 2) + bytes((200, 30, 30, 255)) * (w - w // 2)
    return encode_rgba(w, h, row * h)


def test_colour_cap_zero_keeps_lossless_rgba(tmp_path, monkeypatch):
    from PIL import Image
    monkeypatch.setenv("BTSGEN_CARD_ART_COLORS", "0")
    p = tmp_path / "raw.png"
    p.write_bytes(_half_transparent_png(160, 100))
    assert card_mod.fit_to_portrait(p) is True
    with Image.open(p) as im:
        assert im.mode == "RGBA"  # nothing silently flattens the cut-out onto black
        rgba = im.convert("RGBA")
    assert rgba.getpixel((0, 0))[3] == 0 and rgba.getpixel((999, 379))[3] == 255


def test_colour_cap_is_on_by_default_and_keeps_alpha(tmp_path, monkeypatch):
    """256 colours by default: 34 lossless portraits are ~26 MB per class and the mod pulls cards.zip
    on the game's UI thread at import. The reserved transparent index must survive the save."""
    from PIL import Image
    big, small = tmp_path / "big.png", tmp_path / "small.png"
    for f in (big, small):
        f.write_bytes(_half_transparent_png(160, 100))
    monkeypatch.setenv("BTSGEN_CARD_ART_COLORS", "0")
    card_mod.fit_to_portrait(big)
    monkeypatch.delenv("BTSGEN_CARD_ART_COLORS", raising=False)
    assert card_mod.fit_to_portrait(small) is True
    with Image.open(small) as im:
        assert im.mode == "P"                       # a palette PNG: ~2.7x smaller on real card art
        rgba = im.convert("RGBA")
    assert rgba.getpixel((0, 0))[3] == 0            # the reserved transparent index survived the save
    assert rgba.getpixel((999, 379))[3] == 255
    assert small.stat().st_size < big.stat().st_size
    assert card_mod.image_size(small) == CARD_PORTRAIT_SIZE


@pytest.mark.parametrize("value,expected", [("", 256), ("0", 0), ("1", 256), ("999", 256), ("nonsense", 256), ("64", 64)])
def test_colour_cap_defaults_to_256_and_zero_disables(value, expected, monkeypatch):
    monkeypatch.setenv("BTSGEN_CARD_ART_COLORS", value)
    assert card_mod._colour_cap() == expected


def test_fit_to_portrait_resizes_in_place(tmp_path):
    p = tmp_path / "raw.png"
    p.write_bytes(encode_rgb(1536, 8, bytes(1536 * 8 * 3)))  # tiny stand-in for a 3:2 render
    assert card_mod.fit_to_portrait(p) is True
    assert card_mod.image_size(p) == CARD_PORTRAIT_SIZE
    assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


# --- end to end, no key, no network ---------------------------------------------------------------

def test_procedural_card_art_end_to_end(tmp_path):
    art = ClassArt(class_id="pyre", name="The Sixgun Pyre", concept="a cowboy", imagery=["revolver"])
    small = StyleProfile(name="card-test", prompt_suffix=CARD_STYLE.prompt_suffix,
                         negative=CARD_STYLE.negative, size=(96, 64), out_format="png")
    res = forge_card_art(art, _CARD, backend="procedural", style=small, out_dir=tmp_path)
    out = tmp_path / "pyre.card.jack_in_iron.png"
    assert res.ok and res.path == out and res.error is None
    assert out.exists() and out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert (res.width, res.height) == CARD_PORTRAIT_SIZE   # cropped + resized to the mod's box
    assert card_mod.image_size(out) == CARD_PORTRAIT_SIZE
    assert res.cost_usd == 0.0 and res.backend == "procedural"
    meta = json.loads((tmp_path / "pyre.card.jack_in_iron.meta.json").read_text())
    assert meta["class_id"] == "pyre" and meta["size"] == [1000, 760] and meta["enriched"] is False
    assert "Jack in Iron" in meta["prompt"]


def test_card_art_never_enriches(tmp_path, monkeypatch):
    """34 cards must not become 34 extra LLM calls — enrichment is off for this kind, key or not."""
    monkeypatch.setenv("BTSGEN_PROMPT_ENRICH", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from btsgen.art import enrich as enrich_mod

    def boom(*a, **k):
        raise AssertionError("card art must never call the enrichment LLM")

    monkeypatch.setattr(enrich_mod, "urlopen", boom)
    small = StyleProfile(name="t", size=(48, 32), out_format="png")
    res = forge_card_art(ClassArt(class_id="pyre", name="Pyre"), _CARD, backend="procedural",
                         style=small, out_dir=tmp_path)
    assert res.ok
    meta = json.loads((tmp_path / "pyre.card.jack_in_iron.meta.json").read_text())
    assert meta["enriched"] is False


def test_no_backend_is_still_graceful(tmp_path):
    res = forge_card_art(ClassArt(class_id="pyre", name="Pyre"), _CARD, out_dir=tmp_path)  # -> null
    assert not res.ok and res.backend == "null" and res.error
    assert not list(tmp_path.glob("*.png"))


def test_result_carries_the_ledger_fields(tmp_path):
    """The web orchestrator records one forge_usage row per art kind off exactly these fields."""
    res = forge_card_art(ClassArt(class_id="pyre", name="Pyre"), _CARD, backend=_FakeBackend("x"),
                         out_dir=tmp_path, portrait_size=None)
    for field in ("ok", "path", "error", "cost_usd", "model", "backend", "width", "height"):
        assert hasattr(res, field)
    assert res.cost_usd == 0.004 and res.model == "x/m" and res.backend == "x"
