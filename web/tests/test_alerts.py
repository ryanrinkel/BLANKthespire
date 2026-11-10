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


# --- page experiments: Monday digest + planned-end / winner mail (plan 3.10 items 3-4) ------------------

import json  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import ab_report  # noqa: E402
import experiments  # noqa: E402
from experiments import Experiment  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import experiments_mail  # noqa: E402


def _x(**over) -> Experiment:
    base = dict(name="hero", page="/", arms=("a", "b"), weights=(50, 50), salt="s1",
                started="2026-11-03", planned_end="2026-12-15", primary="login",
                hypothesis="Saying the price lifts /login opens.",
                arms_text={"a": "Create Your Own Class", "b": "Forge a class — free with your own API key"})
    base.update(over)
    return Experiment(**base)


def _traffic(a=(120, 6), b=(118, 14)):
    def row(n, hits):
        return {"exposures": n, "login": hits, "primary": hits, "clicked": hits,
                "devices": {"desktop": n - 2, "phone": 1, "phone_webview": 1}}
    return {"experiments": {"hero": {"per_arm": {"a": row(*a), "b": row(*b)}, "exposure_rate_7d": 8.0,
                                     "control_rate": a[1] / a[0], "days_to_decision": 120.0}}}


def _payload(today, traffic=None, reg=None):
    return ab_report.build_experiments_payload(traffic if traffic is not None else _traffic(), today,
                                               experiments=reg or [_x()])


def test_digest_is_none_when_nothing_is_live():
    assert alerts.experiments_digest([], "2026-11-09") is None
    ended = _x(ended="2026-11-08", winner="a")
    assert alerts.experiments_digest(_payload("2026-11-09", reg=[ended]), "2026-11-09") is None


def test_digest_one_block_per_live_experiment(monkeypatch):
    monkeypatch.delenv("BTSWEB_PUBLIC_URL", raising=False)
    reg = [_x(), _x(name="dl", page="/download", hypothesis="A shorter page lifts downloads.", primary="download")]
    subject, body = alerts.experiments_digest(_payload("2026-11-09", reg=reg), "2026-11-09")
    assert subject.startswith("[BLANK the spire] experiments: 2 live — hero P(b beats a)=0.")
    assert "Saying the price lifts /login opens." in body and "A shorter page lifts downloads." in body
    assert body.count("Hypothesis:") == 2
    assert "day 7 of 42" in body and "36 days left" in body
    assert "exposures 118" in body and "/login opened 14 (11.9%)" in body and "P(b beats a) 0." in body
    assert "https://blankthespire.com/?ab=hero:b" in body
    assert "Decision rule:" in body


def test_digest_preview_links_follow_the_public_url(monkeypatch):
    monkeypatch.setenv("BTSWEB_PUBLIC_URL", "https://staging.example.com/")
    _, body = alerts.experiments_digest(_payload("2026-11-09"), "2026-11-09")
    assert "https://staging.example.com/?ab=hero:a" in body


def test_planned_end_mail_fires_once():
    assert alerts.experiments_due(_payload("2026-12-14"), "2026-12-14", {}) == []
    due = alerts.experiments_due(_payload("2026-12-15"), "2026-12-15", {})
    assert [k for k, _, _ in due] == ["end:hero"]
    key, subject, body = due[0]
    assert subject.startswith("[BLANK the spire] hero reached its planned end — P(b beats a) = 0.")
    assert "Decide: set winner or keep control." in body
    assert alerts.experiments_due(_payload("2026-12-16"), "2026-12-16", {key: "2026-12-15"}) == []
    # an ended experiment never asks again
    ended = [_x(ended="2026-12-15", winner="a")]
    assert alerts.experiments_due(_payload("2026-12-16", reg=ended), "2026-12-16", {}) == []


def test_winner_mail_when_the_rule_is_met():
    traffic = _traffic(a=(400, 20), b=(400, 60))
    due = alerts.experiments_due(_payload("2026-11-20", traffic), "2026-11-20", {})
    assert [k for k, _, _ in due] == ["winner:hero"]
    assert due[0][1] == "[BLANK the spire] hero has a winner by the rule: b"
    assert alerts.experiments_due(_payload("2026-11-21", traffic), "2026-11-21", {"winner:hero": "x"}) == []


def test_send_experiments_mail_respects_config(mailbox, monkeypatch):
    assert alerts.send_experiments_mail("s", "b") is True
    assert mailbox == [(["unlimited@example.com"], "s", "b")]
    monkeypatch.setattr(alerts, "mail_configured", lambda: False)
    assert alerts.send_experiments_mail("s", "b") is False
    monkeypatch.setattr(alerts, "mail_configured", lambda: True)
    monkeypatch.setattr(alerts, "ADMIN_EMAILS", set())
    assert alerts.send_experiments_mail("s", "b") is False
    assert len(mailbox) == 1


def test_send_experiments_mail_failure_is_false(mailbox, monkeypatch):
    def boom(to, subject, body):
        raise RuntimeError("resend down")
    monkeypatch.setattr(alerts, "_send_mail", boom)
    assert alerts.send_experiments_mail("s", "b") is False


@pytest.fixture
def mail_cli(tmp_path, monkeypatch):
    monkeypatch.setattr(experiments, "EXPERIMENTS", [_x()])
    (tmp_path / "traffic.json").write_text(json.dumps(_traffic()), encoding="utf-8")
    state = tmp_path / "state.json"

    def run(*args):
        return experiments_mail.main(["--traffic-dir", str(tmp_path), "--state", str(state), *args])
    return run, state


def test_cli_monday_digest_sent_once_and_persisted(mailbox, mail_cli):
    run, state = mail_cli
    assert run("--today", "2026-11-09") == 0          # a Monday
    assert len(mailbox) == 1 and "experiments: 1 live" in mailbox[0][1]
    assert json.loads(state.read_text())["last_digest"] == "2026-11-09"
    assert run("--today", "2026-11-09") == 0          # timer re-run: no second digest
    assert len(mailbox) == 1
    assert run("--today", "2026-11-10") == 0          # Tuesday: nothing due
    assert len(mailbox) == 1


def test_cli_due_mail_persisted_and_not_resent(mailbox, mail_cli):
    run, state = mail_cli
    assert run("--today", "2026-12-15") == 0          # a Tuesday, planned end
    assert [s for _, s, _ in mailbox] == [mailbox[0][1]] and "planned end" in mailbox[0][1]
    assert json.loads(state.read_text())["sent"] == {"end:hero": "2026-12-15"}
    assert run("--today", "2026-12-16") == 0
    assert len(mailbox) == 1


def test_cli_dry_run_prints_and_touches_nothing(mailbox, mail_cli, capsys):
    run, state = mail_cli
    assert run("--today", "2026-11-10", "--digest", "--dry-run") == 0
    out = capsys.readouterr().out
    assert "=== digest" in out and "Subject: [BLANK the spire] experiments: 1 live" in out
    assert mailbox == [] and not state.exists()


def test_cli_failed_send_is_retried(mailbox, mail_cli, monkeypatch):
    run, state = mail_cli
    monkeypatch.setattr(alerts, "mail_configured", lambda: False)
    assert run("--today", "2026-12-15") == 0
    assert mailbox == [] and not state.exists()
    monkeypatch.setattr(alerts, "mail_configured", lambda: True)
    assert run("--today", "2026-12-16") == 0
    assert len(mailbox) == 1 and "planned end" in mailbox[0][1]


def test_cli_without_traffic_json(mailbox, mail_cli, tmp_path):
    run, _ = mail_cli
    (tmp_path / "traffic.json").unlink()
    assert run("--today", "2026-11-09") == 0
    assert len(mailbox) == 1 and "No exposures yet" in mailbox[0][2]


# --- the "ship unless worse" rule (experiments.RULE_SHIP_UNLESS_WORSE): the mails say what the rule says --------

def test_ship_unless_worse_mails():
    suw = _x(rule=experiments.RULE_SHIP_UNLESS_WORSE)
    # B clearly worse after 14+ days and 200+ per arm: one early "stops by the rule" mail, the rule in the footer
    worse = _traffic(a=(400, 40), b=(400, 12))
    due = alerts.experiments_due(_payload("2026-11-20", worse, [suw]), "2026-11-20", {})
    assert [k for k, _s, _b in due] == ["winner:hero"]
    assert "stops by the rule: B is worse — keep the control" in due[0][1]
    assert "Decision rule (ship unless worse)" in due[0][2]
    # not worse: nothing early; at the planned end ONE mail that says the rule ships B (no separate winner mail)
    same = _traffic(a=(400, 30), b=(400, 29))
    assert alerts.experiments_due(_payload("2026-11-20", same, [suw]), "2026-11-20", {}) == []
    due = alerts.experiments_due(_payload("2026-12-15", same, [suw]), "2026-12-15", {})
    assert [k for k, _s, _b in due] == ["end:hero"]
    assert "The rule says ship b: decision due — ship B (not shown to be worse)." in due[0][2]
    # the card readout says the same
    [e] = _payload("2026-12-15", same, [suw])
    assert "the rule says ship B" in e["readout"] and e["status_kind"] == "due"
    assert e["rule"] == "ship_unless_worse" and e["rule_text"].startswith("Decision rule (ship unless worse)")
    # a must_win experiment alone keeps today's single rule sentence
    assert ab_report.rules_text(_payload("2026-11-20")) == ab_report.rule_sentence()
