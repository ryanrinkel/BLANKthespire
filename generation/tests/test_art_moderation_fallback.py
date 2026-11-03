"""Moderation fallback for splash + sprite (art/moderation.py, splash._forge_asset).

2026-11-01, class 97 "Umbreon, the Red Cloaked": openrouter,openai both refused the same prompt on
OpenAI's safety system and the class shipped with no splash. Rung 1 = the same prompt on FLUX.2 Klein
via OpenRouter (server chain only), rung 2 = a neutral prompt on the forge's own chain. Fully offline:
OpenRouter's HTTP layer is scripted and no test may reach a real API."""
import base64
import contextlib
import io
import json
from urllib.error import HTTPError

import pytest

from btsgen.art import (DEFAULT_STYLE, SPRITE_STYLE, ClassArt, ImageRequest, ImageResult, forge_card_art,
                        forge_splash, forge_sprite, splash_prompt, sprite_prompt)
from btsgen.art import moderation
from btsgen.art import registry
from btsgen.art.backends import openrouter as orb
from btsgen.art.png import encode_rgb

FLUX = "black-forest-labs/flux.2-klein-4b"
_BLOCK = 'HTTP 400: {"error":{"message":"Your request was rejected by the safety system."}}'

_ART = ClassArt(class_id="umbreon", name="Umbreon, the Red Cloaked",
                description="Umbreon turns the strength of his foes against them.",
                concept="A dark-magic sorcerer who focuses on using the strength of his enemies against them",
                archetypes=["Poison", "Evasion"], flavor=["a red-cloaked hexer"],
                imagery=["crimson cloak", "venom-green sigils"])


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "BTSGEN_IMAGE_BACKEND", "BTSGEN_PROMPT_ENRICH",
              "BTSGEN_OPENROUTER_MODEL", "BTSGEN_OPENROUTER_SPRITE_MODEL", "BTSGEN_OPENROUTER_RESOLUTION",
              "BTSGEN_IMAGE_QUALITY", "BTSGEN_IMAGE_SPRITE_QUALITY", "BTSGEN_OPENROUTER_CARD_MODELS",
              "BTSGEN_OPENROUTER_CARD_MODEL", moderation.FALLBACK_MODEL_ENV):
        monkeypatch.delenv(k, raising=False)


class _Fake:
    """A chain tier. `refuse(prompt) -> error | None` decides per call; records every prompt it saw."""

    def __init__(self, name, refuse=lambda p: _BLOCK, available=True):
        self.name, self._refuse, self._available = name, refuse, available
        self.prompts: list[str] = []

    def available(self):
        return self._available

    def generate(self, req: ImageRequest) -> ImageResult:
        self.prompts.append(req.prompt)
        err = self._refuse(req.prompt)
        if err:
            return ImageResult(ok=False, backend=self.name, model=f"{self.name}/m", error=err)
        req.out_path.parent.mkdir(parents=True, exist_ok=True)
        req.out_path.write_bytes(encode_rgb(6, 4, bytes(6 * 4 * 3)))
        return ImageResult(ok=True, backend=self.name, model=f"{self.name}/m", path=req.out_path,
                           cost_usd=0.044, width=6, height=4)


@pytest.fixture
def server_chain(monkeypatch):
    """Register two fake tiers and point $BTSGEN_IMAGE_BACKEND at them — the backend=None (server) path."""
    made = []

    def make(*tiers):
        for t in tiers:
            registry._ensure_builtins()
            registry.register(t)
            made.append(t.name)
        monkeypatch.setenv("BTSGEN_IMAGE_BACKEND", ",".join(t.name for t in tiers))
        return tiers
    yield make
    for n in made:
        registry._BACKENDS.pop(n, None)


def _script(monkeypatch, steps, seen):
    """Stub OpenRouter's HTTP layer with an ordered script; an unscripted call fails the test."""
    it = iter(steps)

    @contextlib.contextmanager
    def fake_urlopen(request, timeout=0):
        body = json.loads(request.data.decode())
        seen.append(body)
        try:
            step = next(it)
        except StopIteration:
            raise AssertionError(f"unscripted OpenRouter call for {body['model']}") from None
        if isinstance(step, Exception):
            raise step

        class R:
            def read(self_inner):
                return step
        yield R()

    monkeypatch.setattr(orb, "urlopen", fake_urlopen)


def _ok_body(png=None, cost=0.015):
    png = png or encode_rgb(6, 4, bytes(6 * 4 * 3))
    return json.dumps({"data": [{"b64_json": base64.b64encode(png).decode(), "media_type": "image/png"}],
                       "usage": {"cost": cost}}).encode()


def _blocked():
    return HTTPError("https://openrouter.ai/api/v1/images", 400, "err", {},
                     io.BytesIO(b'{"error":{"message":"Black Forest Labs blocked this request: flagged."}}'))


# --- rung 1: FLUX on the original prompt ----------------------------------------------------------

def test_moderation_on_every_tier_falls_back_to_flux_with_the_same_prompt(tmp_path, monkeypatch, server_chain):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-SERVER")
    a, b = server_chain(_Fake("modtier_a"), _Fake("modtier_b"))
    seen: list = []
    _script(monkeypatch, [_ok_body(cost=0.015)], seen)
    events: list = []
    res = forge_splash(_ART, out_dir=tmp_path, on_event=events.append)
    assert res.ok and res.backend == "openrouter" and res.model == FLUX and res.cost_usd == 0.015
    assert len(a.prompts) == 1 and len(b.prompts) == 1
    assert len(seen) == 1 and seen[0]["model"] == FLUX
    assert seen[0]["prompt"] == a.prompts[0]               # the concept survives intact
    assert "Umbreon" in seen[0]["prompt"] and "dark-magic sorcerer" in seen[0]["prompt"]
    assert seen[0]["aspect_ratio"] == "16:9" and "background" not in seen[0]  # FLUX takes any ratio
    assert any("moderation blocked every tier" in e and FLUX in e for e in events)
    meta = json.loads((tmp_path / "umbreon.splash.meta.json").read_text())
    assert meta["model"] == FLUX and meta["moderation_fallback"] == "model"
    assert meta["prompt"] == a.prompts[0]


def test_flux_already_refused_in_the_chain_is_not_retried(tmp_path, monkeypatch, server_chain):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-SERVER")
    flux_tier = _Fake("fluxtier")
    flux_tier.generate = lambda req: (flux_tier.prompts.append(req.prompt) or
                                      ImageResult(ok=False, backend="fluxtier", model=FLUX, error=_BLOCK))
    server_chain(flux_tier)
    _script(monkeypatch, [], [])                           # any OpenRouter call fails the test
    events: list = []
    res = forge_splash(_ART, out_dir=tmp_path, on_event=events.append)
    assert not res.ok and any("already refused" in e for e in events)
    assert len(flux_tier.prompts) == 2                     # the original + the neutral rung, no FLUX rung


# --- rung 2: the neutral prompt on the normal chain -----------------------------------------------

def test_flux_also_blocked_then_the_neutral_prompt_succeeds(tmp_path, monkeypatch, server_chain):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-SERVER")
    picky = lambda p: _BLOCK if "Umbreon" in p else None   # noqa: E731 — refuses only the named prompt
    a, = server_chain(_Fake("modtier_a", refuse=picky))
    seen: list = []
    _script(monkeypatch, [_blocked()], seen)
    events: list = []
    res = forge_splash(_ART, out_dir=tmp_path, on_event=events.append)
    assert res.ok and res.backend == "modtier_a" and res.model == "modtier_a/m" and res.cost_usd == 0.044
    assert [s["model"] for s in seen] == [FLUX]
    assert len(a.prompts) == 2
    neutral = a.prompts[1]
    for gone in ("Umbreon", "dark-magic sorcerer", "strength of his foes", "player asked for"):
        assert gone not in neutral
    assert "crimson cloak" in neutral and "red-cloaked hexer" in neutral
    assert neutral.endswith(DEFAULT_STYLE.prompt_suffix) and "RIGHT third" in neutral
    assert any("neutral prompt" in e for e in events)
    meta = json.loads((tmp_path / "umbreon.splash.meta.json").read_text())
    assert meta["prompt"] == neutral and meta["moderation_fallback"] == "neutral" and meta["enriched"] is False


def test_every_rung_fails_reports_every_refusal(tmp_path, monkeypatch, server_chain):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-SERVER")
    server_chain(_Fake("modtier_a"))
    _script(monkeypatch, [_blocked()], [])
    res = forge_splash(_ART, out_dir=tmp_path)
    assert not res.ok
    assert res.error.count("modtier_a:") == 2 and "openrouter:" in res.error
    assert not list(tmp_path.glob("*.png"))


def test_neutral_prompts_drop_name_concept_and_description():
    for build, style in ((splash_prompt, DEFAULT_STYLE), (sprite_prompt, SPRITE_STYLE)):
        full, neutral = build(_ART, style), build(_ART, style, neutral=True)
        assert "Umbreon" in full and "Umbreon" not in neutral
        assert _ART.concept not in neutral and _ART.description not in neutral
        assert "venom-green sigils" in neutral and neutral.endswith(style.prompt_suffix)
        # enrichment is written FROM the concept: a neutral prompt ignores it
        assert "ENRICHED" not in build(_ART, style, enriched_body="ENRICHED", neutral=True)
    bare = ClassArt(class_id="x", name="X", archetypes=["Poison"])
    assert "Themes: Poison." in splash_prompt(bare, DEFAULT_STYLE, neutral=True)


# --- what must NOT change -------------------------------------------------------------------------

@pytest.mark.parametrize("err", ["HTTP 429: rate limited", "HTTP 503: upstream", "network error: timed out"])
def test_non_moderation_failure_makes_no_extra_calls(tmp_path, monkeypatch, server_chain, err):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-SERVER")
    a, b = server_chain(_Fake("modtier_a", refuse=lambda p: err), _Fake("modtier_b", refuse=lambda p: err))
    _script(monkeypatch, [], [])                           # any OpenRouter call fails the test
    events: list = []
    res = forge_splash(_ART, out_dir=tmp_path, on_event=events.append)
    assert not res.ok and len(a.prompts) == 1 and len(b.prompts) == 1
    assert not any("moderation" in e or "neutral" in e for e in events)
    assert res.error == f"modtier_a: {err} | modtier_b: {err}"


def test_missing_keys_make_no_extra_calls(tmp_path, monkeypatch, server_chain):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-SERVER")
    a, = server_chain(_Fake("modtier_a", available=False))
    _script(monkeypatch, [], [])
    res = forge_sprite(_ART, out_dir=tmp_path)
    assert not res.ok and a.prompts == []


def test_byok_backend_never_uses_the_server_flux(tmp_path, monkeypatch):
    """A BYOK forge passes its own backend instance: rung 1 (server key) is skipped, rung 2 reuses theirs."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-SERVER")
    _script(monkeypatch, [], [])                           # the server key must never be used
    user = _Fake("user_openai", refuse=lambda p: _BLOCK if "Umbreon" in p else None)
    events: list = []
    res = forge_splash(_ART, backend=user, out_dir=tmp_path, on_event=events.append)
    assert res.ok and res.backend == "user_openai" and len(user.prompts) == 2
    assert "Umbreon" not in user.prompts[1]
    assert any("forge's own backend" in e for e in events)


def test_byok_openrouter_key_never_falls_back_to_the_server_key(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-SERVER")
    auths: list = []

    @contextlib.contextmanager
    def fake_urlopen(request, timeout=0):
        auths.append((dict(request.header_items()).get("Authorization"), json.loads(request.data)["model"]))
        raise _blocked()
    monkeypatch.setattr(orb, "urlopen", fake_urlopen)
    res = forge_splash(_ART, backend=orb.OpenRouterImageBackend(api_key="sk-or-USER"), out_dir=tmp_path)
    assert not res.ok
    assert auths and all(a == "Bearer sk-or-USER" for a, _ in auths)
    assert FLUX not in [m for _, m in auths] and len(auths) == 2  # original + neutral, both on their key


@pytest.mark.parametrize("off", ["off", "", "none"])
def test_env_disables_the_flux_rung(tmp_path, monkeypatch, server_chain, off):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-SERVER")
    monkeypatch.setenv(moderation.FALLBACK_MODEL_ENV, off)
    a, = server_chain(_Fake("modtier_a"))
    _script(monkeypatch, [], [])
    events: list = []
    res = forge_splash(_ART, out_dir=tmp_path, on_event=events.append)
    assert not res.ok and len(a.prompts) == 2              # the neutral rung still runs
    assert any("model fallback is off" in e for e in events)
    assert moderation.fallback_backend() is None


def test_env_overrides_the_fallback_model(tmp_path, monkeypatch, server_chain):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-SERVER")
    monkeypatch.setenv(moderation.FALLBACK_MODEL_ENV, "bytedance-seed/seedream-4.5")
    server_chain(_Fake("modtier_a"))
    seen: list = []
    _script(monkeypatch, [_ok_body()], seen)
    res = forge_splash(_ART, out_dir=tmp_path)
    assert res.ok and res.model == "bytedance-seed/seedream-4.5" and seen[0]["model"] == res.model


def test_no_server_openrouter_key_skips_flux_and_goes_neutral(tmp_path, monkeypatch, server_chain):
    a, = server_chain(_Fake("modtier_a", refuse=lambda p: _BLOCK if "Umbreon" in p else None))
    _script(monkeypatch, [], [])
    res = forge_splash(_ART, out_dir=tmp_path)
    assert res.ok and len(a.prompts) == 2


def test_card_art_does_not_climb_the_shared_rungs(tmp_path, monkeypatch, server_chain):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-SERVER")
    a, = server_chain(_Fake("modtier_a"))
    _script(monkeypatch, [], [])
    res = forge_card_art(_ART, {"id": "c", "name": "Hex", "type": "skill"}, out_dir=tmp_path, portrait_size=None)
    assert not res.ok and len(a.prompts) == 1              # no prose -> card.py's own retry is a no-op too


# --- the FLUX sprite: no alpha from the model, so it is chroma-keyed ------------------------------

def _green_png_with_subject() -> bytes:
    from PIL import Image
    im = Image.new("RGB", (40, 60), (0, 255, 0))
    for x in range(12, 28):
        for y in range(15, 50):
            im.putpixel((x, y), (180, 20, 30))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_flux_sprite_is_chroma_keyed_to_a_cutout(tmp_path, monkeypatch, server_chain):
    from PIL import Image
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-SERVER")
    server_chain(_Fake("modtier_a"))
    seen: list = []
    _script(monkeypatch, [_ok_body(png=_green_png_with_subject())], seen)
    res = forge_sprite(_ART, out_dir=tmp_path)
    assert res.ok and res.model == FLUX and (res.width, res.height) == (40, 60)
    body = seen[0]
    assert "background" not in body and "#00FF00" in body["prompt"] and body["aspect_ratio"] == "2:3"
    with Image.open(res.path) as im:
        assert im.mode == "RGBA"
        assert im.getpixel((1, 1))[3] == 0                 # the green field is gone
        assert im.getpixel((20, 30))[3] == 255             # the subject is kept
    meta = json.loads((tmp_path / "umbreon.sprite.meta.json").read_text())
    assert meta["moderation_fallback"] == "model" and "#00FF00" not in meta["prompt"]


def test_alpha_capable_sprite_models_still_ask_for_transparency():
    req = ImageRequest(prompt="p", out_path="x.png", size=(1024, 1536), transparent=True, kind="sprite")
    be = orb.OpenRouterImageBackend()
    body = be.build_payload(req, model=orb.DEFAULT_SPRITE_MODEL)
    assert body["background"] == "transparent" and body["prompt"] == "p"
    body = be.build_payload(req, model=FLUX)
    assert "background" not in body and "#00FF00" in body["prompt"]
    assert orb.supports_alpha("sourceful/riverflow-v2") and not orb.supports_alpha(FLUX)
