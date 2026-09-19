"""Web test harness: the Flask app against a throwaway SQLite file, dev-login auth, no network.

app.py builds its state at import (engine, limiters, queues), so the environment is pinned HERE before the
first `import app`, and the app module is imported once per session. Run from the repo root:

    PYTHONPATH=generation uv run --project generation pytest web/tests -q

Set BTSWEB_* env in this file only; individual tests monkeypatch module attributes instead.
"""
from __future__ import annotations

import os
import sys
import tempfile
import types
from pathlib import Path

import pytest

WEB_DIR = Path(__file__).resolve().parents[1]
REPO = WEB_DIR.parent
for p in (str(WEB_DIR), str(REPO / "generation")):
    if p not in sys.path:
        sys.path.insert(0, p)

_TMP = Path(tempfile.mkdtemp(prefix="btsweb-tests-"))
DB_PATH = _TMP / "test.db"

os.environ["BTSWEB_NO_DOTENV"] = "1"  # never load a real web/.env (the droplet has one)
os.environ["BTSWEB_DATABASE_URL"] = f"sqlite:///{DB_PATH.as_posix()}"
os.environ["BTSWEB_DEV_AUTH"] = "1"
os.environ.pop("GOOGLE_CLIENT_ID", None)
os.environ.pop("GOOGLE_CLIENT_SECRET", None)
os.environ.pop("STRIPE_SECRET_KEY", None)          # billing disabled: routes 503, event handler still testable
os.environ.pop("BTSWEB_ALLOW_PRIVATE_URLS", None)  # the SSRF guard must be live
os.environ["BTSWEB_TOKEN_DAILY_CAP"] = "0"   # global kill-switch off by default; tests that want it set it
os.environ["BTSWEB_UNLIMITED_EMAILS"] = "unlimited@example.com"
os.environ["BTSWEB_PUBLIC_URL"] = "http://testserver"
os.environ["BTSWEB_GAP_LOG"] = str(_TMP / "gaps.jsonl")
os.environ["BTSWEB_CARD_FEEDBACK_LOG"] = str(_TMP / "feedback.jsonl")
os.environ.setdefault("BTSGEN_IMAGE_BACKEND", "null")

# The CSRF header every mutating /api call must carry.
H = {"X-Requested-With": "fetch"}


@pytest.fixture(scope="session")
def app_module():
    import app as app_mod  # noqa: WPS433 — deliberate late import after the env is pinned
    app_mod.app.config["TESTING"] = True
    # Art is cosmetic and the relic icon would hit the Twemoji CDN — never in tests.
    app_mod._generate_relic_icon = lambda *a, **k: None
    # Generated art (splash/sprite/cards.zip) goes to the throwaway temp tree: a test run must never
    # litter the real web/static/forged/ with classes the repo's own deploy then serves.
    app_mod.STATIC_FORGED_DIR = _TMP / "forged"
    return app_mod


@pytest.fixture(scope="session")
def fake_bundle(app_module):
    """One real offline forge result (the fake generators), reused as the stubbed forge output."""
    import forge
    return forge.forge_to_bundle("a venomous plague doctor", fake=True, staged=True)


@pytest.fixture()
def client(app_module):
    return app_module.app.test_client()


@pytest.fixture(autouse=True)
def _no_cloud_image_calls(monkeypatch):
    """Safety net: a BYOK forge builds a REAL OpenRouter/OpenAI image backend around the posted key (see
    app._byok_art_backend), so any test that posts such a key would otherwise dial the vendor. Make those
    calls fail fast instead (art is best-effort: the forge still succeeds, just without images). Tests that
    want to see the request replace urlopen again with their own fake."""
    from urllib.error import URLError
    from btsgen.art.backends import openai as oaib, openrouter as orb

    def refuse(request, timeout=0):
        raise URLError("network disabled in tests")

    monkeypatch.setattr(orb, "urlopen", refuse)
    monkeypatch.setattr(oaib, "urlopen", refuse)


def login(client, email: str = "dev@example.com") -> dict:
    """Dev sign-in; returns the /api/me user dict."""
    r = client.get(f"/dev-login?email={email}")
    assert r.status_code == 302
    return client.get("/api/me").get_json()["user"]


def seed_tokens(app_module, email: str, n: int) -> None:
    """Give an account `n` tokens. Accounts start at zero (pricing v3 grants nothing), so every test that
    drives the hosted "Use a token" path has to say out loud how it got them."""
    from models import User
    with app_module.session_scope() as s:
        s.query(User).filter_by(email=email).one().token_balance = n


def sse_events(resp) -> list[tuple[str, dict]]:
    """Drain a text/event-stream response into [(event, data), ...]."""
    import json
    raw = resp.get_data(as_text=True)
    out = []
    for chunk in raw.split("\n\n"):
        event, data = "message", ""
        for line in chunk.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data += line[5:].strip()
        if data:
            out.append((event, json.loads(data)))
    return out


@pytest.fixture()
def stub_forge(app_module, fake_bundle, monkeypatch):
    """Replace the real forge with a stub. Returns a controller: .result (dict to return) / .error (message to
    raise as ForgeError) / .calls (kwargs seen)."""
    import forge

    class Ctl:
        result = fake_bundle
        error: str | None = None
        calls: list[dict] = []
        gate = None  # threading.Event: when set, the stub blocks until it is set

    def fake_forge(concept, **kw):
        Ctl.calls.append(kw)
        if kw.get("on_usage") is not None:
            kw["on_usage"]({"prompt_tokens": 1000, "completion_tokens": 200,
                            "prompt_tokens_details": {"cached_tokens": 300}, "_role": "cards",
                            "_model": "glm-5.2"})
            kw["on_usage"]({"prompt_tokens": 500, "completion_tokens": 100, "_role": "structure",
                            "_model": "z-ai/glm-5.2"})
        if Ctl.gate is not None:
            Ctl.gate.wait(timeout=30)
        if Ctl.error:
            raise forge.ForgeError(Ctl.error)
        return dict(Ctl.result)

    monkeypatch.setattr(app_module, "forge_to_bundle", fake_forge)
    Ctl.calls = []
    return Ctl


@pytest.fixture()
def stripe_stub(app_module, monkeypatch):
    """Turn billing ON with no key and no network: billing_enabled() reads the module constant, and the
    routes resolve `billing._stripe` at call time, so both can be stood in for. Returns a controller whose
    .sessions is the list of kwargs each Checkout create was called with."""
    import billing

    class Ctl:
        sessions: list[dict] = []

    class _Session:
        @staticmethod
        def create(**kw):
            Ctl.sessions.append(kw)
            return types.SimpleNamespace(url=f"https://stripe.test/c/cs_stub{len(Ctl.sessions)}")

    class _Checkout:
        Session = _Session

    Ctl.sessions = []
    monkeypatch.setattr(billing, "STRIPE_SECRET_KEY", "sk_test_stub")
    monkeypatch.setattr(billing, "_stripe", types.SimpleNamespace(checkout=_Checkout))
    return Ctl


@pytest.fixture(autouse=True)
def _reset_process_state(app_module):
    """Limiters, queues and per-user locks are process-local singletons — start every test clean."""
    import auth

    lim = app_module.token_limiter
    with lim._lock:
        lim._day, lim._day_count = -1, 0
    auth.magic_limiter.reset()
    with app_module._user_active_lock:
        app_module._user_active.clear()
    with app_module._feedback_lock:
        app_module._feedback_hits.clear()
    yield
