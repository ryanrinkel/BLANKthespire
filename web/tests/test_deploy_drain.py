"""deploy.sh's drain helper (web/deploy/running_forges.py, WALK_AWAY_FORGE_PLAN.md 5.1).

Only the Python helper is tested — never the bash. Each test builds its own throwaway SQLite file from
models.Base (no app import: the helper must work without the app's boot-time reconciliation).
"""
from __future__ import annotations

import importlib.util
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models import Base, ForgeJob, User

_HELPER = Path(__file__).resolve().parents[1] / "deploy" / "running_forges.py"
_spec = importlib.util.spec_from_file_location("running_forges", _HELPER)
rf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rf)

NOW = datetime(2026, 11, 9, 12, 0, 0)


@pytest.fixture()
def db_url(tmp_path):
    url = f"sqlite:///{(tmp_path / 'live.db').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        u = User(email="drain@example.com", google_sub="dev:drain")
        s.add(u)
        s.flush()
        s.add_all([
            ForgeJob(id="a" * 32, user_id=u.id, mode="byok", status="running",
                     concept="a plague doctor\twho\nbrews poison " + "x" * 100,
                     started_at=NOW - timedelta(minutes=47, seconds=30)),
            ForgeJob(id="b" * 32, user_id=u.id, mode="token", status="running", concept="cowboy",
                     started_at=NOW - timedelta(minutes=3)),
            ForgeJob(id="c" * 32, user_id=u.id, mode="token", status="done", concept="finished",
                     started_at=NOW - timedelta(minutes=90)),
            ForgeJob(id="d" * 32, user_id=u.id, mode="byok", status="failed", concept="broken",
                     started_at=NOW - timedelta(minutes=10)),
        ])
        s.commit()
    engine.dispose()
    return url


def test_running_jobs_lists_only_running_oldest_first(db_url):
    jobs = rf.running_jobs(db_url, now=NOW)
    assert [j["id"] for j in jobs] == ["a" * 32, "b" * 32]
    assert [j["age_min"] for j in jobs] == [47, 3]
    assert [j["mode"] for j in jobs] == ["byok", "token"]
    # One line, at most 60 chars: tabs/newlines would break deploy.sh's TAB-separated parse.
    assert jobs[0]["concept"].startswith("a plague doctor who brews poison x")
    assert len(jobs[0]["concept"]) == rf.CONCEPT_CHARS
    assert "\t" not in jobs[0]["concept"] and "\n" not in jobs[0]["concept"]


def test_report_format_is_count_then_tab_lines(db_url):
    out = rf.format_report(rf.running_jobs(db_url, now=NOW)).splitlines()
    assert out[0] == "2"
    assert out[2] == "3\ttoken\tcowboy"
    assert out[1].split("\t")[:2] == ["47", "byok"]
    assert rf.format_report([]) == "0"


def test_helper_is_read_only(db_url):
    """The live DB is opened mode=ro: the helper cannot write even by accident."""
    path = db_url[len("sqlite:///"):]
    before = sqlite3.connect(path).execute("SELECT count(*) FROM forge_jobs").fetchone()
    rf.running_jobs(db_url, now=NOW)
    assert sqlite3.connect(path).execute("SELECT count(*) FROM forge_jobs").fetchone() == before
    ro = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("DELETE FROM forge_jobs")


def test_main_reads_env_file_without_overriding(tmp_path, db_url, monkeypatch, capsys):
    env = tmp_path / ".env"
    env.write_text(f"# comment\n\nBTSWEB_DATABASE_URL='{db_url}'\nBTSWEB_DRAIN_TEST_X=from-file\n",
                   encoding="utf-8")
    monkeypatch.delenv("BTSWEB_DATABASE_URL", raising=False)
    monkeypatch.setenv("BTSWEB_DRAIN_TEST_X", "already-set")
    assert rf.main(["--env-file", str(env)]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "2"
    assert os.environ["BTSWEB_DATABASE_URL"] == db_url
    assert os.environ["BTSWEB_DRAIN_TEST_X"] == "already-set"


def test_unreachable_db_prints_zero_and_exits_0(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BTSWEB_DATABASE_URL", f"sqlite:///{(tmp_path / 'missing.db').as_posix()}")
    assert rf.main(["--env-file", str(tmp_path / "no.env")]) == 0
    cap = capsys.readouterr()
    assert cap.out.strip() == "0"
    assert "assuming 0 running" in cap.err


def test_db_without_forge_jobs_table_prints_zero(tmp_path, monkeypatch, capsys):
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    monkeypatch.setenv("BTSWEB_DATABASE_URL", f"sqlite:///{empty.as_posix()}")
    assert rf.main(["--env-file", str(tmp_path / "no.env")]) == 0
    assert capsys.readouterr().out.strip() == "0"


def test_error_message_never_echoes_the_db_password(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("BTSWEB_DATABASE_URL", "mysql+pymysql://u:s3cretpw@127.0.0.1:1/db")

    def boom(url):
        raise RuntimeError(f"cannot connect to {url}")

    monkeypatch.setattr(rf, "_server_rows", boom)
    assert rf.main(["--env-file", str(tmp_path / "no.env")]) == 0
    err = capsys.readouterr().err
    assert "s3cretpw" not in err and "***" in err
