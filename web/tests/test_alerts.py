"""The out-of-credit operator email: one mail per endpoint per cooldown, to the alert list (else the admin
list), only when mail is configured; a failed send re-arms; nothing leaves the process (`_send_mail` is a
capture stub and `_dispatch` runs synchronously)."""
from __future__ import annotations

import pytest

import alerts
from btsgen import alerts as bts_alerts


def _event(**over):
    base = {"kind": "credit_exhausted", "source": "chat", "endpoint": "https://openrouter.ai/api/v1",
            "code": 402, "detail": "Insufficient credits. Add more using https://openrouter.ai/settings/credits",
            "model": "z-ai/glm-5.3", "tier": "primary", "ts": 1_800_000_000.0}
    base.update(over)
    return base


@pytest.fixture
def mailbox(monkeypatch, app_module):
    sent: list[tuple[list[str], str, str]] = []
    monkeypatch.setattr(alerts, "_send_mail", lambda to, subject, body: sent.append((to, subject, body)))
    monkeypatch.setattr(alerts, "_dispatch", lambda fn: fn())
    monkeypatch.setattr(alerts, "mail_configured", lambda: True)
    monkeypatch.delenv("BTSWEB_ALERT_EMAILS", raising=False)
    monkeypatch.delenv("BTSWEB_ALERT_COOLDOWN_S", raising=False)
    alerts.reset()
    yield sent
    alerts.reset()


def test_installed_at_app_import(app_module):
    assert alerts._on_credit_exhausted in bts_alerts._listeners


def test_one_email_to_the_admin_list_with_the_facts(mailbox):
    assert alerts._on_credit_exhausted(_event()) is True
    assert len(mailbox) == 1
    to, subject, body = mailbox[0]
    assert to == ["unlimited@example.com"]  # conftest's BTSWEB_ADMIN_EMAILS
    assert "credits exhausted" in subject and "openrouter.ai" in subject
    assert "HTTP 402" in body and "z-ai/glm-5.3" in body and "Insufficient credits" in body
    assert "openrouter.ai/settings/credits" in body


def test_alert_list_overrides_admin_list(mailbox, monkeypatch):
    monkeypatch.setenv("BTSWEB_ALERT_EMAILS", "ops@example.com, Second@Example.com")
    alerts._on_credit_exhausted(_event())
    assert mailbox[0][0] == ["ops@example.com", "second@example.com"]


def test_throttled_per_endpoint_and_source(mailbox):
    assert alerts._on_credit_exhausted(_event()) is True
    assert alerts._on_credit_exhausted(_event(model="google/gemma-4-31b-it")) is False  # same wall
    assert alerts._on_credit_exhausted(_event(endpoint="https://ollama.com/v1")) is True  # other endpoint
    assert alerts._on_credit_exhausted(_event(source="art", endpoint="https://openrouter.ai/api/v1/images",
                                              model="openai/gpt-5-image-mini")) is True  # art is its own
    assert len(mailbox) == 3
    assert "WITHOUT generated art" in mailbox[2][2]


def test_zero_cooldown_sends_every_time(mailbox, monkeypatch):
    monkeypatch.setenv("BTSWEB_ALERT_COOLDOWN_S", "0")
    alerts._on_credit_exhausted(_event())
    alerts._on_credit_exhausted(_event())
    assert len(mailbox) == 2


def test_silent_when_mail_is_not_configured(mailbox, monkeypatch):
    monkeypatch.setattr(alerts, "mail_configured", lambda: False)
    assert alerts._on_credit_exhausted(_event()) is False
    assert mailbox == []


def test_silent_when_nobody_is_listed(mailbox, monkeypatch):
    monkeypatch.setattr(alerts, "ADMIN_EMAILS", set())
    assert alerts._on_credit_exhausted(_event()) is False
    assert mailbox == []


def test_failed_send_rearms_instead_of_waiting_out_the_cooldown(mailbox, monkeypatch):
    calls = {"n": 0}

    def flaky(to, subject, body):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("resend down")
        mailbox.append((to, subject, body))

    monkeypatch.setattr(alerts, "_send_mail", flaky)
    assert alerts._on_credit_exhausted(_event()) is True   # queued, but the send blew up
    assert alerts._on_credit_exhausted(_event()) is True   # re-armed: tries again at once
    assert len(mailbox) == 1


def test_end_to_end_from_the_btsgen_event(mailbox):
    """The library-side hook reaches the mailer: btsgen fires, the web listener mails."""
    bts_alerts.credit_exhausted(source="chat", endpoint="https://openrouter.ai/api/v1", code=402,
                                detail="Insufficient credits", model="z-ai/glm-5.3", tier="primary")
    assert len(mailbox) == 1
