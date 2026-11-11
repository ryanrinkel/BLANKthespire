"""The ?look=board share link survives every kind of hop (pages.carried_look / with_look + the Referer net).

A page opened with ?look=board is in look B; board.js carries the parameter on plain links. Everything else
(script navigations, form posts, server redirects, OAuth, the emailed sign-in link, Stripe) is covered here:
the server 302s a page request whose same-origin Referer had the look, and the server-built URLs append it.
Nothing is ever stored on the device: every answer below is checked for Set-Cookie where no sign-in happens.
"""
from __future__ import annotations

import dataclasses
from urllib.parse import parse_qs, urlsplit

import pytest

import experiments as ex
import pages
from conftest import H, login

LIVE_DAY = "2026-11-20"    # inside skin's window
UA = "Mozilla/5.0 test-agent"
SKIN_CSS = '<link rel="stylesheet" href="/static/board.css?v='
HERE = "http://localhost"   # the Flask test client's origin


@pytest.fixture(autouse=True)
def live_day(monkeypatch):
    monkeypatch.setattr(ex, "today_utc", lambda: LIVE_DAY)


def _skin():
    return next(e for e in ex.EXPERIMENTS if e.name == "skin")


def _ip_for_arm(arm: str) -> str:
    for i in range(256):
        ip = f"198.51.100.{i}"
        if ex.arm_for(ip, UA, _skin()) == arm:
            return ip
    raise AssertionError("no ip")


IP_A = None


def _hdr(referer: str | None = None, ip: str | None = None) -> dict:
    global IP_A
    if IP_A is None:
        IP_A = _ip_for_arm("a")   # would draw the classic look: a b page can only come from the look
    h = {"User-Agent": UA, "X-Forwarded-For": ip or IP_A}
    if referer is not None:
        h["Referer"] = referer
    return h


# ----------------------------------------------------------------------------------------- the helpers

@pytest.mark.parametrize("url,want", [
    ("/app", "/app?look=board"),
    ("/app#account", "/app?look=board#account"),
    ("/app?purchase=cancel", "/app?purchase=cancel&look=board"),
    ("https://x.test/app?a=1#h", "https://x.test/app?a=1&look=board#h"),
    ("/app?look=board", "/app?look=board"),
])
def test_with_look(url, want):
    assert pages.with_look(url, "board") == want
    assert pages.with_look(url, None) == url


# ------------------------------------------------------------------------------------- the Referer net

def test_same_origin_referer_redirects_to_the_same_url_plus_look(client):
    r = client.get("/help?x=1&y=two", headers=_hdr(f"{HERE}/deck/abc?look=board"))
    assert r.status_code == 302
    assert r.headers["Location"] == "/help?x=1&y=two&look=board"
    assert r.headers["Cache-Control"] == "private, no-cache"
    assert "Set-Cookie" not in r.headers
    r = client.get("/login", headers=_hdr(f"{HERE}/deck/abc?look=board"))
    assert (r.status_code, r.headers["Location"]) == (302, "/login?look=board")


def test_the_public_url_host_counts_as_same_origin(client):
    """conftest pins BTSWEB_PUBLIC_URL=http://testserver; a proxy that rewrote Host would still match it."""
    r = client.get("/archive", headers=_hdr("http://testserver/?look=board"))
    assert (r.status_code, r.headers["Location"]) == (302, "/archive?look=board")


def test_the_redirect_target_is_served_in_look_b_without_a_loop(client):
    r = client.get("/login?look=board", headers=_hdr(f"{HERE}/deck/abc?look=board"))
    assert r.status_code == 200 and "Set-Cookie" not in r.headers
    assert SKIN_CSS in r.get_data(as_text=True)


@pytest.mark.parametrize("referer", [
    "https://elsewhere.example/?look=board",       # cross-origin
    f"{HERE}/?look=nope",                         # unknown value
    f"{HERE}/?looks=board",                       # not the parameter
    f"{HERE}/",                                   # no look
    "not a url at all",
    None,                                         # no Referer
])
def test_no_redirect_without_a_same_origin_look_referer(client, referer):
    r = client.get("/help", headers=_hdr(referer))
    assert r.status_code == 200 and "Set-Cookie" not in r.headers
    assert SKIN_CSS not in r.get_data(as_text=True)   # IP_A draws look a


def test_hash_assigned_b_visitor_is_untouched(client):
    """A visitor who drew b by hash has no look anywhere: no redirect, no parameter, still b."""
    ip_b = _ip_for_arm("b")
    r = client.get("/help", headers=_hdr(f"{HERE}/archive", ip=ip_b))
    assert r.status_code == 200 and SKIN_CSS in r.get_data(as_text=True)


def test_an_explicit_look_arg_is_never_redirected(client):
    r = client.get("/help?look=nope", headers=_hdr(f"{HERE}/?look=board"))
    assert r.status_code == 200


def test_non_200_page_is_served_with_the_look_instead_of_redirected(client):
    """The expired sign-in page is a 410: no redirect, but the Referer's look still applies."""
    r = client.get("/auth/email/not-a-real-token", headers=_hdr(f"{HERE}/login?look=board"))
    assert r.status_code == 410 and SKIN_CSS in r.get_data(as_text=True)
    assert "Set-Cookie" not in r.headers


def test_no_redirect_once_the_experiment_has_ended(client, monkeypatch):
    monkeypatch.setattr(ex, "EXPERIMENTS", [dataclasses.replace(_skin(), ended="2026-11-15", winner="a")])
    r = client.get("/help", headers=_hdr(f"{HERE}/?look=board"))
    assert r.status_code == 200 and SKIN_CSS not in r.get_data(as_text=True)
    monkeypatch.setattr(ex, "EXPERIMENTS", [])   # gone from the registry entirely
    assert client.get("/help", headers=_hdr(f"{HERE}/?look=board")).status_code == 200


def test_the_net_still_works_before_the_start(client, monkeypatch):
    monkeypatch.setattr(ex, "today_utc", lambda: "2026-11-10")
    assert client.get("/help", headers=_hdr(f"{HERE}/?look=board")).status_code == 302


# ---------------------------------------------------------------------------------- server redirects

def test_app_signed_out_bounces_to_the_splash_with_the_look(client):
    r = client.get("/app?look=board", headers=_hdr())
    assert (r.status_code, r.headers["Location"]) == (302, "/?look=board")
    assert "Set-Cookie" not in r.headers
    r = client.get("/app", headers=_hdr(f"{HERE}/deck/x?look=board"))   # via the Referer
    assert r.headers["Location"] == "/?look=board"
    assert client.get("/app", headers=_hdr()).headers["Location"] == "/"   # no look: unchanged


def test_login_signed_in_bounces_to_the_app_with_the_look(client):
    login(client, "lookbounce@example.com")
    assert client.get("/login?look=board", headers=_hdr()).headers["Location"] == "/app?look=board"
    r = client.get("/login", headers=_hdr(f"{HERE}/deck/x?look=board"))
    assert r.headers["Location"] == "/app?look=board"
    assert client.get("/login", headers=_hdr()).headers["Location"] == "/app"


def test_dev_login_keeps_the_look(client):
    r = client.get("/dev-login?email=lookdev@example.com", headers=_hdr(f"{HERE}/?look=board"))
    assert r.headers["Location"] == "/app?look=board"


# ------------------------------------------------------------------------------------ email sign-in

@pytest.fixture()
def mail(monkeypatch):
    import auth
    sent: list[tuple[str, str, str]] = []
    monkeypatch.setattr(auth, "mail_configured", lambda: True)
    monkeypatch.setattr(auth, "_send_magic_link",
                        lambda email, url, lang="en", code="": sent.append((email, url, code)))
    return sent


def test_emailed_link_carries_the_look_and_lands_on_app_with_it(client, mail):
    r = client.post("/api/auth/email/start", json={"email": "lookmail@example.com"},
                    headers={**H, **_hdr(f"{HERE}/login?look=board")})
    assert r.status_code == 200
    url = mail[-1][1]
    assert url.startswith("http://testserver/auth/email/") and url.endswith("?look=board")
    path = urlsplit(url).path + "?look=board"
    # opened from the inbox: no Referer, the URL alone makes it look b
    page = client.get(path, headers=_hdr())
    assert page.status_code == 200 and SKIN_CSS in page.get_data(as_text=True)
    # the Continue form has no action: it posts back to this same URL, query included
    assert '<form method="post"' in page.get_data(as_text=True)
    r = client.post(path, headers=_hdr(f"http://testserver{path}"))
    assert (r.status_code, r.headers["Location"]) == (302, "/app?look=board")


def test_emailed_link_without_a_look_is_unchanged(client, mail):
    client.post("/api/auth/email/start", json={"email": "plainmail@example.com"},
                headers={**H, **_hdr(f"{HERE}/login")})
    assert "?" not in mail[-1][1]


def test_link_flow_lands_on_the_account_tab_with_the_look(client, mail):
    login(client, "lookacct@example.com")
    client.post("/api/auth/email/start", json={"email": "lookacct@example.com"},
                headers={**H, **_hdr(f"{HERE}/login?link=1&look=board")})
    path = urlsplit(mail[-1][1]).path + "?look=board"
    r = client.post(path, headers=_hdr())
    assert r.headers["Location"] == "/app?look=board#account"


def test_code_sign_in_next_carries_the_look(client, mail):
    hdr = {**H, **_hdr(f"{HERE}/login?look=board")}
    client.post("/api/auth/email/start", json={"email": "lookcode@example.com"}, headers=hdr)
    code = mail[-1][2]
    r = client.post("/api/auth/email/code", json={"email": "lookcode@example.com", "code": code}, headers=hdr)
    assert r.get_json() == {"ok": True, "next": "/app?look=board"}


# ------------------------------------------------------------------------------------------------ OAuth

def test_oauth_state_round_trip_carries_the_look(app_module, monkeypatch):
    """A real Authlib client (no network: the token fetch and the profile call are stubbed): the look rides
    in the state Authlib itself stores and validates, the redirect_uri is untouched, and the callback lands
    on /app?look=board. A forged suffix on a state the session never issued is refused by Authlib."""
    import auth
    from authlib.integrations.flask_client import OAuth
    from test_auth_providers import FakeResp

    # init_app writes app.extensions[...]: claim the key through monkeypatch so teardown removes it again
    monkeypatch.setitem(app_module.app.extensions, "authlib.integrations.flask_client", None)
    oauth = OAuth()
    oauth.init_app(app_module.app)
    oauth.register(name="discord", client_id="cid", client_secret="sec",
                   authorize_url="https://discord.test/authorize",
                   access_token_url="https://discord.test/token",
                   api_base_url="https://discord.test/api/", client_kwargs={"scope": "identify email"})
    client_ = oauth.discord
    monkeypatch.setattr(client_, "fetch_access_token", lambda **kw: {"access_token": "t", "token_type": "bearer"})
    monkeypatch.setattr(client_, "get", lambda path, **kw: FakeResp(
        {"id": 7_700_001, "username": "lk", "email": "lookoauth@example.com", "verified": True}))
    monkeypatch.setattr(auth, "_oauth", oauth)

    c = app_module.app.test_client()
    r = c.get("/login/discord", headers=_hdr(f"{HERE}/login?look=board"))
    assert r.status_code == 302
    q = parse_qs(urlsplit(r.headers["Location"]).query)
    state = q["state"][0]
    assert state.endswith(".board") and len(state) > 30
    assert q["redirect_uri"] == ["http://localhost/auth/discord/callback"]   # unchanged: no look in it

    r = c.get(f"/auth/discord/callback?code=abc&state={state}")
    assert (r.status_code, r.headers["Location"]) == (302, "/app?look=board")

    # without a look: a plain random state, a plain landing
    c2 = app_module.app.test_client()
    state2 = parse_qs(urlsplit(c2.get("/login/discord", headers=_hdr(f"{HERE}/login")).headers["Location"]).query)["state"][0]
    assert "." not in state2
    assert c2.get(f"/auth/discord/callback?code=abc&state={state2}").headers["Location"] == "/app"

    # a state the session never issued (here: someone appending .board) is Authlib's mismatch, not a landing
    c3 = app_module.app.test_client()
    state3 = parse_qs(urlsplit(c3.get("/login/discord").headers["Location"]).query)["state"][0]
    from authlib.integrations.base_client.errors import MismatchingStateError
    with pytest.raises(MismatchingStateError):
        c3.get(f"/auth/discord/callback?code=abc&state={state3}.board")


def test_state_look_ignores_junk_and_ended_experiments(monkeypatch):
    import auth
    assert auth._state_look("abc.board") == "board"
    assert auth._state_look("abc") is None and auth._state_look("abc.nope") is None and auth._state_look(None) is None
    monkeypatch.setattr(ex, "EXPERIMENTS", [dataclasses.replace(_skin(), ended="2026-11-15", winner="b")])
    assert auth._state_look("abc.board") is None
    assert "." not in auth._oauth_state(None)


# ----------------------------------------------------------------------------------------------- Stripe

def test_stripe_return_urls_carry_the_look(client, stripe_stub):
    login(client, "lookgiver@example.com")
    r = client.post("/api/donate", json={"tier": "t5"}, headers={**H, "Referer": f"{HERE}/app?look=board"})
    assert r.status_code == 200
    kw = stripe_stub.sessions[-1]
    assert kw["success_url"] == ("http://testserver/app?purchase=success"
                                 "&session_id={CHECKOUT_SESSION_ID}&look=board")
    assert kw["cancel_url"] == "http://testserver/app?purchase=cancel&look=board"
    client.post("/api/donate", json={"tier": "t5"}, headers={**H, "Referer": f"{HERE}/app"})
    assert stripe_stub.sessions[-1]["cancel_url"] == "http://testserver/app?purchase=cancel"
