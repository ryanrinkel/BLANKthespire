"""Dependency watch (dep_watch.py): Workshop BaseLib + the game's public build in the Monday digest
(docs/plans/GITHUB_ISSUES_1_2_FIX_PLAN.md, BaseLib dependency policy step 4). Fake fetchers only, no network."""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import pytest

import alerts
import dep_watch
import experiments
from experiments import Experiment

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import experiments_mail  # noqa: E402

SEP_11 = 1789149503          # 2026-09-11, BaseLib 3.4.7
NOV_06 = 1793923200          # 2026-11-06 00:00 UTC
MONDAY = datetime.date(2026, 11, 9)


def _item(tu=SEP_11):
    return lambda item_id: {"item_id": item_id, "title": "BaseLib", "time_updated": tu}


def _build(buildid="23811903"):
    return lambda: {"buildid": buildid, "timeupdated": 1781829256}


def _boom(*a, **k):
    raise OSError("network down")


def test_first_run_records_baseline(tmp_path):
    st = tmp_path / "dep.json"
    r = dep_watch.check(now=MONDAY, state_path=st, fetch_item=_item(), fetch_build=_build())
    assert r["baselib"]["first_run"] and not r["baselib"]["changed"]
    assert r["game"]["first_run"] and not r["game"]["changed"]
    assert not dep_watch.any_changed(r)
    saved = json.loads(st.read_text())
    assert saved["baselib_time_updated"] == SEP_11 and saved["game_buildid"] == "23811903"
    assert saved["baselib_first_seen"] == "2026-11-09" and saved["game_first_seen"] == "2026-11-09"
    text = dep_watch.digest_section(r)
    assert "first run, baseline recorded" in text and "!!" not in text
    assert "2026-09-11" in text


def test_unchanged_run(tmp_path):
    st = tmp_path / "dep.json"
    dep_watch.check(now=MONDAY, state_path=st, fetch_item=_item(), fetch_build=_build())
    r = dep_watch.check(now=MONDAY + datetime.timedelta(days=7), state_path=st, fetch_item=_item(),
                        fetch_build=_build())
    assert not dep_watch.any_changed(r)
    assert r["baselib"]["previous"] == SEP_11 and r["baselib"]["current"] == SEP_11
    assert json.loads(st.read_text())["baselib_first_seen"] == "2026-11-09"   # first seen is not bumped
    assert dep_watch.digest_section(r) == ("BaseLib (Workshop 3737335127): unchanged, last updated 2026-09-11. "
                                           "Game build: 23811903, unchanged.")


def test_baselib_update_is_loud(tmp_path):
    st = tmp_path / "dep.json"
    dep_watch.check(now=MONDAY, state_path=st, fetch_item=_item(), fetch_build=_build())
    r = dep_watch.check(now=MONDAY + datetime.timedelta(days=7), state_path=st, fetch_item=_item(NOV_06),
                        fetch_build=_build())
    assert r["baselib"]["changed"] and not r["game"]["changed"] and dep_watch.any_changed(r)
    text = dep_watch.digest_section(r)
    assert text.startswith("!! BaseLib UPDATED 2026-11-06")
    assert "bump Alchyr.Sts2.BaseLib in mod/BlankTheSpire.csproj, rebuild, one AutoSlay smoke, release" in text
    assert "Game build: 23811903, unchanged." in text
    assert json.loads(st.read_text())["baselib_time_updated"] == NOV_06


def test_game_build_change_is_loud(tmp_path):
    st = tmp_path / "dep.json"
    dep_watch.check(now=MONDAY, state_path=st, fetch_item=_item(), fetch_build=_build())
    r = dep_watch.check(now=MONDAY, state_path=st, fetch_item=_item(), fetch_build=_build("24000000"))
    assert r["game"]["changed"] and not r["baselib"]["changed"]
    assert ("!! Game build changed 23811903 -> 24000000: expect a BaseLib release; re-check the Workshop item"
            in dep_watch.digest_section(r))


def test_fetch_failure_is_unavailable_and_keeps_state(tmp_path):
    st = tmp_path / "dep.json"
    dep_watch.check(now=MONDAY, state_path=st, fetch_item=_item(), fetch_build=_build())
    r = dep_watch.check(now=MONDAY, state_path=st, fetch_item=_boom, fetch_build=lambda: None)
    text = dep_watch.digest_section(r)
    assert text.startswith("dep watch: unavailable (") and "network down" in text
    assert not dep_watch.any_changed(r)
    assert json.loads(st.read_text())["baselib_time_updated"] == SEP_11
    # one side down: the other still reports
    r = dep_watch.check(now=MONDAY, state_path=st, fetch_item=_item(), fetch_build=_boom)
    text = dep_watch.digest_section(r)
    assert "unchanged, last updated 2026-09-11" in text and "Game build: unavailable (OSError: network down)" in text


def test_write_false_leaves_state_until_commit(tmp_path):
    st = tmp_path / "dep.json"
    r = dep_watch.check(now=MONDAY, state_path=st, fetch_item=_item(), fetch_build=_build(), write=False)
    assert not st.exists()
    assert dep_watch.commit(r) and json.loads(st.read_text())["game_buildid"] == "23811903"


# --- the Monday digest -------------------------------------------------------------------------------------

@pytest.fixture
def mailbox(monkeypatch, app_module):
    sent: list[tuple[list[str], str, str]] = []
    monkeypatch.setattr(alerts, "_send_mail", lambda to, subject, body: sent.append((to, subject, body)))
    monkeypatch.setattr(alerts, "mail_configured", lambda: True)
    monkeypatch.delenv("BTSWEB_ALERT_EMAILS", raising=False)
    return sent


@pytest.fixture
def digest_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("BTSWEB_DEP_WATCH", "1")
    monkeypatch.delenv("BTSWEB_DEP_WATCH_STATE", raising=False)
    monkeypatch.setattr(dep_watch, "fetch_workshop_item", _item())
    monkeypatch.setattr(dep_watch, "fetch_game_build", _build())
    monkeypatch.setattr(experiments, "EXPERIMENTS", [Experiment(
        name="hero", page="/", arms=("a", "b"), weights=(50, 50), salt="s1", started="2026-11-03",
        planned_end="2026-12-15", primary="login", hypothesis="Saying the price lifts /login opens.",
        arms_text={"a": "Create Your Own Class", "b": "Forge a class"})])
    state = tmp_path / "state.json"

    def run(*args):
        return experiments_mail.main(["--traffic-dir", str(tmp_path), "--state", str(state), *args])
    return run, tmp_path / "dep_watch.json"


def test_digest_carries_the_dep_section(mailbox, digest_cli):
    run, dep_state = digest_cli
    assert run("--today", "2026-11-09") == 0
    assert len(mailbox) == 1
    _, subject, body = mailbox[0]
    assert not subject.startswith("[DEP]")
    assert "Dependency watch:\nBaseLib (Workshop 3737335127): first run, baseline recorded" in body
    assert json.loads(dep_state.read_text())["baselib_time_updated"] == SEP_11


def test_digest_subject_flags_a_change(mailbox, digest_cli, monkeypatch):
    run, dep_state = digest_cli
    run("--today", "2026-11-09")
    monkeypatch.setattr(dep_watch, "fetch_workshop_item", _item(NOV_06))
    assert run("--today", "2026-11-16") == 0
    _, subject, body = mailbox[-1]
    assert subject.startswith("[DEP] [BLANK the spire] experiments:")
    assert "!! BaseLib UPDATED 2026-11-06" in body


def test_digest_survives_fetch_failure(mailbox, digest_cli, monkeypatch):
    run, dep_state = digest_cli
    monkeypatch.setattr(dep_watch, "fetch_workshop_item", _boom)
    monkeypatch.setattr(dep_watch, "fetch_game_build", lambda: None)
    assert run("--today", "2026-11-09") == 0
    _, subject, body = mailbox[0]
    assert "experiments: 1 live" in subject and "dep watch: unavailable (OSError: network down" in body


def test_dry_run_does_not_record(mailbox, digest_cli, capsys):
    run, dep_state = digest_cli
    assert run("--today", "2026-11-10", "--digest", "--dry-run") == 0
    assert "Dependency watch:" in capsys.readouterr().out
    assert mailbox == [] and not dep_state.exists()


def test_failed_send_does_not_record(mailbox, digest_cli, monkeypatch):
    run, dep_state = digest_cli
    monkeypatch.setattr(alerts, "mail_configured", lambda: False)
    assert run("--today", "2026-11-09") == 0
    assert not dep_state.exists()


def test_dep_only_digest_when_nothing_is_live(mailbox, digest_cli, monkeypatch):
    run, _ = digest_cli
    monkeypatch.setattr(experiments, "EXPERIMENTS", [])
    assert run("--today", "2026-11-09") == 0
    assert len(mailbox) == 1 and "no experiment live" in mailbox[0][1]
    assert "Dependency watch:" in mailbox[0][2]


def test_disabled_leaves_digest_alone(mailbox, digest_cli, monkeypatch):
    run, dep_state = digest_cli
    monkeypatch.setenv("BTSWEB_DEP_WATCH", "0")
    assert run("--today", "2026-11-09") == 0
    assert "Dependency watch" not in mailbox[0][2] and not dep_state.exists()
