"""The sign-in code mailed with every magic link (2026-10-29): POST /api/auth/email/code.

Why it exists: a desktop mail client (QQ Mail's embedded Chromium, seen 2026-10-21) opens the link in ITS OWN
browser, so the session cookie lands there and the tab where sign-in started stays signed out. The email
now also carries a 6-digit code bound to the same login_links row, typed into the original tab.

Same harness as test_auth_email.py: no mail leaves the process (`_send_magic_link` / `_send_mail` are capture
stubs, `mail_configured` is forced True). Emails are unique per test (the SQLite DB is session-scoped).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect, text

from conftest import H, login


@pytest.fixture(autouse=True)
def _reset_code_limiter():
    import auth
    auth.code_limiter.reset()
    yield
    auth.code_limiter.reset()


@pytest.fixture()
def mail(monkeypatch):
    """Pretend Resend is configured; collect (email, url, code) instead of sending."""
    import auth
    sent: list[tuple[str, str, str]] = []
    monkeypatch.setattr(auth, "mail_configured", lambda: True)
    monkeypatch.setattr(auth, "_send_magic_link",
                        lambda email, url, lang="en", code="": sent.append((email, url, code)))
    return sent


@pytest.fixture()
def outbox(monkeypatch):
    """One level lower: the real email body, captured at the transport."""
    import auth
    sent: list[dict] = []
    monkeypatch.setattr(auth, "mail_configured", lambda: True)
    monkeypatch.setattr(auth, "_send_mail",
                        lambda to, subject, html, text: sent.append({"to": to, "subject": subject,
                                                                     "html": html, "text": text}))
    return sent


def start(client, email: str, **extra):
    return client.post("/api/auth/email/start", json={"email": email, **extra}, headers=H)


def enter(client, email: str, code: str):
    return client.post("/api/auth/email/code", json={"email": email, "code": code}, headers=H)


def _token_of(url: str) -> str:
    return url.rsplit("/", 1)[-1]


def _wrong(code: str) -> str:
    """A 6-digit code guaranteed not to be `code`."""
    return f"{(int(code) + 1) % 1_000_000:06d}"


def _rows(app_module, email: str) -> list:
    from models import LoginLink
    with app_module.session_scope() as s:
        rows = s.query(LoginLink).filter_by(email=email).order_by(LoginLink.id).all()
        return [(r.used_at, r.code_attempts, r.code_hash) for r in rows]


# --- the email ---------------------------------------------------------------------------------------

def test_the_email_carries_the_link_and_the_code(client, app_module, outbox):
    start(client, "mailcode@example.com")
    msg = outbox[-1]
    assert msg["html"] is None  # still text-only: the magic link has no HTML variant, by design
    text_body = msg["text"]
    assert "http://testserver/auth/email/" in text_body
    m = re.search(r"Or enter this code where you started signing in: (\d{3}) (\d{3})\n", text_body)
    assert m, text_body
    # Only a hash is stored, never the code itself.
    (used, attempts, code_hash), = _rows(app_module, "mailcode@example.com")
    assert used is None and attempts == 0 and code_hash and m.group(1) + m.group(2) not in code_hash
    # ... and the printed code is the one that works.
    r = enter(client, "mailcode@example.com", m.group(1) + " " + m.group(2))
    assert r.get_json() == {"ok": True, "next": "/app"}


def test_the_chinese_email_has_the_chinese_code_sentence(client, outbox):
    start(client, "zhcode@example.com", lang="zh")
    msg = outbox[-1]
    assert msg["subject"] == "你的Blank the Spire登录链接"
    assert re.search(r"或者在你开始登录的页面输入此验证码：\d{3} \d{3}\n", msg["text"]), msg["text"]
    assert "http://testserver/auth/email/" in msg["text"]


def test_each_link_gets_its_own_random_code(client, mail):
    start(client, "twocodes@example.com")
    start(client, "twocodes@example.com")
    (_, _, c1), (_, _, c2) = mail
    assert re.fullmatch(r"\d{6}", c1) and re.fullmatch(r"\d{6}", c2)


# --- signing in with the code -------------------------------------------------------------------------

def test_the_right_code_signs_in_like_the_link_does(client, app_module, mail):
    start(client, "rightcode@example.com")
    _, _, code = mail[0]
    r = enter(client, "RightCode@Example.com ", code)
    assert r.status_code == 200 and r.get_json() == {"ok": True, "next": "/app"}
    assert "session=" in r.headers.get("Set-Cookie", "")
    me = client.get("/api/me").get_json()["user"]
    assert me["email"] == "rightcode@example.com"
    assert me["identities"] == [{"provider": "email", "label": "rightcode@example.com"}]
    assert _rows(app_module, "rightcode@example.com")[0][0] is not None  # spent


@pytest.mark.parametrize("typed", ["{a} {b}", "{a}-{b}", " {a}{b} ", "{fw}"])
def test_the_code_tolerates_spaces_dashes_and_fullwidth_digits(client, mail, typed):
    email = f"typed{abs(hash(typed)) % 10_000}@example.com"
    start(client, email)
    code = mail[0][2]
    fullwidth = "".join(chr(0xFF10 + int(d)) for d in code)  # what a CJK IME may type
    r = enter(client, email, typed.format(a=code[:3], b=code[3:], fw=fullwidth))
    assert r.get_json()["ok"] is True


def test_a_code_from_any_live_email_works(client, mail):
    """Someone who asked three times may type the code from the first email."""
    for _ in range(3):
        start(client, "anyof@example.com")
    first_code = mail[0][2]
    assert enter(client, "anyof@example.com", first_code).get_json()["ok"] is True


def test_the_code_attaches_in_link_mode(client, mail):
    """Signed in already (Account tab -> link another sign-in): the email identity attaches to THIS account
    and the answer points back to the Account tab, exactly like the link's POST."""
    me = login(client, "codelinker@example.com")
    start(client, "codelinker-mail@example.com")
    r = enter(client, "codelinker-mail@example.com", mail[0][2])
    assert r.get_json() == {"ok": True, "next": "/app#account"}
    after = client.get("/api/me").get_json()["user"]
    assert after["id"] == me["id"]
    assert sorted(i["provider"] for i in after["identities"]) == ["dev", "email"]


def test_the_code_endpoint_needs_the_csrf_header(client, mail):
    start(client, "csrfcode@example.com")
    r = client.post("/api/auth/email/code", json={"email": "csrfcode@example.com", "code": mail[0][2]})
    assert r.status_code == 403
    assert client.get("/api/me").get_json()["user"] is None


def test_the_code_endpoint_is_503_when_email_sign_in_is_off(client, monkeypatch):
    import auth
    monkeypatch.setattr(auth, "_dev_auth_enabled", lambda: False)
    assert enter(client, "off@example.com", "123456").status_code == 503


# --- failures -----------------------------------------------------------------------------------------

def test_five_wrong_codes_lock_the_row_and_the_link_with_it(client, app_module, mail):
    start(client, "locked@example.com")
    _, url, code = mail[0]
    bad = _wrong(code)
    for _ in range(4):
        assert enter(client, "locked@example.com", bad).get_json() == {"ok": False, "reason": "wrong"}
    assert enter(client, "locked@example.com", bad).get_json() == {"ok": False, "reason": "too_many"}
    assert _rows(app_module, "locked@example.com")[0][1] == 5
    # Dead: the right code no longer works, and neither does the link.
    assert enter(client, "locked@example.com", code).get_json() == {"ok": False, "reason": "too_many"}
    assert client.get(f"/auth/email/{_token_of(url)}").status_code == 410
    assert client.post(f"/auth/email/{_token_of(url)}").status_code == 410
    assert client.get("/api/me").get_json()["user"] is None


def test_wrong_guesses_count_against_every_live_row_of_the_address(client, app_module, mail):
    """Three links do not buy fifteen guesses: one miss costs one attempt on each live row."""
    for _ in range(3):
        start(client, "budget@example.com")
    codes = {c for _, _, c in mail}
    bad = next(f"{n:06d}" for n in range(1_000_000) if f"{n:06d}" not in codes)
    replies = [enter(client, "budget@example.com", bad).get_json()["reason"] for _ in range(5)]
    assert replies == ["wrong"] * 4 + ["too_many"]
    assert [a for _, a, _ in _rows(app_module, "budget@example.com")] == [5, 5, 5]


def test_an_expired_code_is_refused(client, mail, monkeypatch):
    import auth
    start(client, "stalecode@example.com")
    code = mail[0][2]
    later = datetime.now(timezone.utc) + timedelta(minutes=16)
    monkeypatch.setattr(auth, "_now", lambda: later)
    assert enter(client, "stalecode@example.com", code).get_json() == {"ok": False, "reason": "expired"}
    assert client.get("/api/me").get_json()["user"] is None


def test_a_link_spent_by_its_link_refuses_its_code(client, app_module, mail):
    start(client, "linkfirst@example.com")
    _, url, code = mail[0]
    elsewhere = app_module.app.test_client()  # the mail app's embedded browser
    assert elsewhere.post(f"/auth/email/{_token_of(url)}").status_code == 302
    assert enter(client, "linkfirst@example.com", code).get_json() == {"ok": False, "reason": "expired"}
    assert client.get("/api/me").get_json()["user"] is None


def test_a_link_spent_by_its_code_refuses_its_link(client, app_module, mail):
    start(client, "codefirst@example.com")
    _, url, code = mail[0]
    assert enter(client, "codefirst@example.com", code).get_json()["ok"] is True
    elsewhere = app_module.app.test_client()
    assert elsewhere.get(f"/auth/email/{_token_of(url)}").status_code == 410
    assert elsewhere.post(f"/auth/email/{_token_of(url)}").status_code == 410
    assert elsewhere.get("/api/me").get_json()["user"] is None
    # ... and the code is single-use too.
    assert enter(app_module.app.test_client(), "codefirst@example.com", code).get_json() == \
        {"ok": False, "reason": "expired"}


def test_an_unknown_address_answers_exactly_like_a_bad_code(client, mail):
    """No enumeration: an address nobody asked a link for is indistinguishable from a wrong guess."""
    start(client, "known@example.com")
    bad = _wrong(mail[0][2])
    known = enter(client, "known@example.com", bad)
    unknown = enter(client, "nobody-ever@example.com", bad)
    garbage = enter(client, "not an email", bad)
    assert known.status_code == unknown.status_code == garbage.status_code == 200
    assert known.get_json() == unknown.get_json() == garbage.get_json() == {"ok": False, "reason": "wrong"}


def test_a_malformed_code_is_wrong_and_costs_no_attempt(client, app_module, mail):
    start(client, "short@example.com")
    for junk in ("12345", "1234567", "abcdef", ""):
        assert enter(client, "short@example.com", junk).get_json() == {"ok": False, "reason": "wrong"}
    assert _rows(app_module, "short@example.com")[0][1] == 0


def test_the_code_limiter_caps_attempts_per_address_and_per_ip(client, app_module, mail, monkeypatch):
    """Ten tries per address per 15 minutes (right or wrong), thirty per IP per hour. Over a cap the answer
    is "too_many" — even for the right code — and nothing is spent."""
    import auth
    start(client, "ratelimit@example.com")
    code = mail[0][2]
    for _ in range(10):
        enter(client, "ratelimit@example.com", "")  # malformed: costs a limiter slot, not a row attempt
    assert enter(client, "ratelimit@example.com", code).get_json() == {"ok": False, "reason": "too_many"}
    assert _rows(app_module, "ratelimit@example.com")[0][0] is None  # not spent

    # Per IP: a fresh limiter with a small IP cap, spread over many addresses from one address.
    monkeypatch.setattr(auth, "code_limiter", auth.MagicLinkLimiter(per_email=10, email_window_s=900,
                                                                     per_ip=3, ip_window_s=3600))
    for n in range(3):
        assert enter(client, f"spray{n}@example.com", "123456").get_json()["reason"] == "wrong"
    assert enter(client, "spray9@example.com", "123456").get_json()["reason"] == "too_many"
    other_ip = app_module.app.test_client()
    r = other_ip.post("/api/auth/email/code", json={"email": "spray9@example.com", "code": "123456"},
                      headers=H, environ_base={"REMOTE_ADDR": "10.9.8.7"})
    assert r.get_json()["reason"] == "wrong"


# --- the link's landing page --------------------------------------------------------------------------

def test_the_continue_page_points_back_to_the_code_without_showing_it(client, mail):
    start(client, "handoff@example.com")
    _, url, code = mail[0]
    page = client.get(f"/auth/email/{_token_of(url)}").get_data(as_text=True)
    assert 'data-i18n="signin.continue.code_handoff"' in page and "type the code from the email" in page
    assert code not in page and f"{code[:3]} {code[3:]}" not in page


def test_the_signin_page_has_the_code_box(client):
    page = client.get("/login").get_data(as_text=True)
    assert 'id="code-box" class="signin-code hidden"' in page
    assert 'autocomplete="one-time-code"' in page and 'data-i18n="signin.code.button"' in page


# --- migration ----------------------------------------------------------------------------------------

def test_the_code_columns_migrate_onto_an_old_login_links_table(tmp_path, monkeypatch):
    """A database made before codes: _ensure_login_link_columns adds them (NULL hash, 0 attempts) and is
    idempotent."""
    import db
    old = create_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    with old.begin() as conn:
        conn.execute(text(
            "CREATE TABLE login_links (id INTEGER PRIMARY KEY AUTOINCREMENT, email VARCHAR(320), "
            "token_hash VARCHAR(64) UNIQUE, ip VARCHAR(64), created_at DATETIME, expires_at DATETIME, "
            "used_at DATETIME)"))
        conn.execute(text("INSERT INTO login_links (email, token_hash, ip, created_at, expires_at) "
                          "VALUES ('old@example.com', 'abc', '1.2.3.4', '2026-10-01 00:00:00', "
                          "'2026-10-01 00:15:00')"))
    monkeypatch.setattr(db, "engine", old)
    db._ensure_login_link_columns()
    db._ensure_login_link_columns()  # idempotent
    cols = {c["name"] for c in inspect(old).get_columns("login_links")}
    assert {"code_hash", "code_attempts"} <= cols
    with old.connect() as conn:
        assert conn.execute(text("SELECT code_hash, code_attempts FROM login_links")).fetchall() == [(None, 0)]
    old.dispose()


def test_a_pre_code_link_still_works_and_its_missing_code_never_matches(client, app_module):
    """Rows minted before the deploy have no code_hash: their link keeps working, no code matches them."""
    import auth
    from models import LoginLink
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    token = "legacy-token-" + "x" * 30
    with app_module.session_scope() as s:
        s.add(LoginLink(email="legacy@example.com", token_hash=auth._token_hash(token), ip="1.2.3.4",
                        created_at=now, expires_at=now + timedelta(minutes=15)))
    assert enter(client, "legacy@example.com", "000000").get_json() == {"ok": False, "reason": "expired"}
    assert client.post(f"/auth/email/{token}").status_code == 302
