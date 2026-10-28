"""Server-side copy (web/i18n.py): the magic-link email, the class email and Stripe's line items read the
same web/static/i18n/<lang>.json the browser does, with per-key English fallback; JSON errors carry a stable
`code` next to the English `error` (docs/plans/I18N_PLAN.md, "Server-side strings the user sees")."""
from __future__ import annotations

import json

import pytest

from conftest import H, login


@pytest.fixture()
def i18n_dir(tmp_path, monkeypatch):
    """A throwaway i18n dir: the real English strings plus a writable zh.json. Returns a writer for zh."""
    import i18n
    i18n.clear_cache()
    en = i18n.get_strings("en")
    assert en.get("email.magic.subject"), "English strings must load (en.json or the in-memory build)"
    (tmp_path / "en.json").write_text(json.dumps({"lang": "en", "strings": en, "console": {}}), encoding="utf-8")
    monkeypatch.setattr(i18n, "I18N_DIR", tmp_path)
    i18n.clear_cache()

    def write_zh(strings: dict) -> None:
        (tmp_path / "zh.json").write_text(json.dumps({"lang": "zh", "strings": strings, "console": {}},
                                                     ensure_ascii=False), encoding="utf-8")
        i18n.clear_cache()

    yield write_zh
    i18n.clear_cache()


# ------------------------------------------------------------------------------------------- module

def test_normalize_lang():
    import i18n
    assert i18n.normalize_lang("zh") == "zh"
    assert i18n.normalize_lang("ZH") == "zh"
    assert i18n.normalize_lang("zh-CN") == "zh"
    for v in (None, "", "en", "fr", "klingon", 7, "../en"):
        assert i18n.normalize_lang(v) == "en"


def test_per_key_english_fallback_and_escaping(i18n_dir):
    import i18n
    i18n_dir({"email.magic.subject": "你的 Blank the Spire 登录链接"})
    assert i18n.get_text("zh", "email.magic.subject") == "你的 Blank the Spire 登录链接"
    # a key zh does not have falls back to English, key by key
    assert i18n.get_text("zh", "email.class.footer") == i18n.get_text("en", "email.class.footer")
    assert i18n.get_strings("zh")["email.class.footer"] == i18n.get_strings("en")["email.class.footer"]
    # unknown language = English; unknown key = the key itself
    assert i18n.get_text("fr", "email.magic.subject") == "Your Blank the Spire sign-in link"
    assert i18n.get_text("en", "no.such.key") == "no.such.key"
    # text strips markup and decodes entities; html escapes the inserted values
    assert "<em>" not in i18n.get_text("en", "email.class.paste_code")
    assert "<em>Import a class code</em>" in i18n.get_html("en", "email.class.paste_code")
    assert i18n.get_html("en", "email.class.subject", name="<b>x</b>").endswith("&lt;b&gt;x&lt;/b&gt;")
    assert i18n.get_text("en", "email.class.subject", name="<b>x</b>").endswith("<b>x</b>")


def test_error_body_and_match_error():
    import i18n
    body = i18n.error_body("server.forge.out_of_tokens")
    assert body["code"] == "forge.out_of_tokens" and body["error"].startswith("you're out of tokens")
    assert "vars" not in body
    ranged = i18n.error_body("server.billing.custom_range", CUSTOM_MIN_DOLLARS=11, CUSTOM_MAX_DOLLARS=500)
    assert ranged["error"] == "custom amounts are whole dollars from $11 to $500."
    assert ranged["vars"] == {"CUSTOM_MIN_DOLLARS": "11", "CUSTOM_MAX_DOLLARS": "500"}
    # a message built elsewhere (forge.py's ForgeError) is mapped back to its code and values
    assert i18n.match_error("could not resolve nowhere.example.") == ("byok.url_resolve",
                                                                      {"parsedhostname": "nowhere.example"})
    assert i18n.match_error("not found") == ("not_found", {})
    assert i18n.match_error("some provider's own words") is None
    assert i18n.with_code({"error": "something else"}) == {"error": "something else"}


# -------------------------------------------------------------------------------------- magic link

@pytest.fixture()
def outbox(monkeypatch):
    import auth
    sent: list[dict] = []
    monkeypatch.setattr(auth, "mail_configured", lambda: True)
    monkeypatch.setattr(auth, "_send_mail",
                        lambda to, subject, html, text: sent.append({"to": to, "subject": subject,
                                                                     "html": html, "text": text}))
    return sent


def _start(client, email, **extra):
    return client.post("/api/auth/email/start", json={"email": email, **extra}, headers=H)


def test_magic_link_email_in_english_by_default(client, outbox):
    r = _start(client, "en-mail@example.com")
    assert r.status_code == 200 and r.get_json() == {"ok": True, "message": "Check your inbox."}
    msg = outbox[-1]
    assert msg["subject"] == "Your Blank the Spire sign-in link" and msg["html"] is None
    assert msg["text"].startswith("Here is your sign-in link for Blank the Spire:\n\nhttp://testserver/auth/email/")
    assert msg["text"].endswith("\n\nThis link expires in 15 minutes. If you didn't ask for it, ignore this "
                                "email.\n")


def test_magic_link_email_picks_the_language_and_falls_back_per_key(client, outbox, i18n_dir):
    i18n_dir({"email.magic.subject": "你的 Blank the Spire 登录链接"})  # body deliberately missing
    _start(client, "zh-mail@example.com", lang="zh")
    msg = outbox[-1]
    assert msg["subject"] == "你的 Blank the Spire 登录链接"
    assert msg["text"].startswith("Here is your sign-in link for Blank the Spire:")  # English fallback
    i18n_dir({"email.magic.subject": "主题", "email.magic.body": "登录链接：\n\n{url}\n\n十五分钟内有效。"})
    _start(client, "zh-mail2@example.com", lang="zh")
    msg = outbox[-1]
    assert msg["subject"] == "主题"
    assert msg["text"].startswith("登录链接：\n\nhttp://testserver/auth/email/") and msg["text"].endswith("十五分钟内有效。\n")


def test_magic_link_unknown_lang_is_english(client, outbox, i18n_dir):
    i18n_dir({"email.magic.subject": "主题"})
    _start(client, "fr-mail@example.com", lang="fr")
    assert outbox[-1]["subject"] == "Your Blank the Spire sign-in link"


# ------------------------------------------------------------------------------------- error codes

def test_error_responses_carry_a_code(client, app_module, stub_forge):
    r = client.get("/api/classes/987654")
    assert r.status_code == 401 and r.get_json() == {"error": "sign in required", "code": "auth.sign_in_required"}
    login(client, "codes@example.com")
    r = client.get("/api/classes/987654")
    assert r.status_code == 404 and r.get_json() == {"error": "not found", "code": "not_found"}
    r = client.post("/api/forge-class", json={"concept": "x", "mode": "token"}, headers=H)
    body = r.get_json()
    assert r.status_code == 402 and body["code"] == "forge.out_of_tokens" and body["token_balance"] == 0
    assert body["error"] == ("you're out of tokens — get a forge token under the Forge button, or bring your own "
                             "API key to keep forging.")
    r = client.post("/api/forge-class", json={"concept": "x", "mode": "token"})  # no CSRF header
    assert r.status_code == 403 and r.get_json()["code"] == "csrf"


# ------------------------------------------------------------------------------------------- stripe

def test_checkout_in_english_sends_no_locale(client, stripe_stub):
    login(client, "en-giver@example.com")
    assert client.post("/api/donate", json={"tier": "t5", "lang": "en"}, headers=H).status_code == 200
    kw = stripe_stub.sessions[-1]
    assert "locale" not in kw
    assert kw["line_items"][0]["price_data"]["product_data"]["name"] == "Donation — Blank the Spire"


def test_checkout_in_chinese_sets_the_locale_and_line_item_names(client, stripe_stub, i18n_dir):
    i18n_dir({"stripe.line_item.donation": "捐赠 — Blank the Spire"})  # fee name falls back to English
    login(client, "zh-giver@example.com")
    assert client.post("/api/donate", json={"tier": "t5", "lang": "zh"}, headers=H).status_code == 200
    kw = stripe_stub.sessions[-1]
    assert kw["locale"] == "zh"
    assert [i["price_data"]["product_data"]["name"] for i in kw["line_items"]] == [
        "捐赠 — Blank the Spire", "Card processing fee"]


def test_checkout_error_carries_a_code(client, stripe_stub):
    login(client, "bad-tier@example.com")
    r = client.post("/api/donate", json={"tier": "t999"}, headers=H)
    assert r.status_code == 400 and r.get_json()["code"] == "billing.pick_tier"


# -------------------------------------------------------------------------------------- class email

def test_class_email_english_and_chinese(app_module, i18n_dir):
    subject, text, html = app_module._class_mail("Plague <Doctor>", "http://x/deck/abc", "BTSC.code")
    assert subject == "Your Slay the Spire 2 class: Plague <Doctor>"
    assert text.startswith('Here is "Plague <Doctor>", the class you forged on Blank the Spire.\n\n')
    assert "(Mods -> Blank the Spire -> Import a class code -> Import, then restart the game):" in text
    assert "<b>Plague &lt;Doctor&gt;</b>" in html and "<em>Import a class code</em>" in html
    assert "BTSC.code" in text and "BTSC.code" in html
    i18n_dir({"email.class.subject": "你的杀戮尖塔 2 职业：{name}"})
    subject, text, _ = app_module._class_mail("Plague", "http://x/deck/abc", "BTSC.code", "zh")
    assert subject == "你的杀戮尖塔 2 职业：Plague"
    assert text.startswith('Here is "Plague"')  # untranslated keys stay English
