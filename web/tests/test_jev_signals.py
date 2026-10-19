"""forge._append_jev_signals: the Jev quality signals (card qa / relic form / vocab gate) persist server-side as
ONE JSONL line per forge, so they can be compared against the validator later. Never breaks a forge."""
from __future__ import annotations

import json
from types import SimpleNamespace

import forge


def _res(**over):
    base = dict(
        stats={"jev_qa": [{"name": "Ember Jab", "name_fits": True, "reads_like_sts": True, "power": 3,
                           "validator_score": 4.5}],
               "jev_relic": {"form": "engine", "p": 0.81, "guess": "engine", "agree": True},
               "vocab_gate": {"mode": "heuristic", "cards": 12, "full_prompt": 2, "first_try_ok": 10}},
        skipped=["Broken Card"],
        log=["card 1 qa (jev): name_fits=True reads_like_sts=True power=3/5 (validator score 4.5)",
             "card 2/12: Ash Ward ready"],
        bundle={"character": {"name": "Cinderwright"}, "cards": [{}, {}, {}]},
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_writes_one_line_with_the_jev_fields(tmp_path, monkeypatch):
    path = tmp_path / "jev.jsonl"
    monkeypatch.setattr(forge, "JEV_LOG", path)
    assert forge._append_jev_signals(_res(), user_id=7, concept="a smith who forges with embers — " + "x" * 300)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["user_id"] == 7
    assert row["class"] == "Cinderwright"
    assert row["concept"].startswith("a smith who forges with embers — ") and len(row["concept"]) == 200
    assert "—" in lines[0]  # ensure_ascii=False
    assert row["cards"] == 3
    assert row["skipped"] == ["Broken Card"]
    assert row["vocab_gate"]["first_try_ok"] == 10
    assert row["jev_qa"][0]["name"] == "Ember Jab"
    assert row["jev_relic"] == {"form": "engine", "p": 0.81, "guess": "engine", "agree": True}
    assert row["jev_lines"] == ["card 1 qa (jev): name_fits=True reads_like_sts=True power=3/5 (validator score 4.5)"]
    assert row["ts"].endswith("+00:00")


def test_skips_when_nothing_jev_related(tmp_path, monkeypatch):
    path = tmp_path / "jev.jsonl"
    monkeypatch.setattr(forge, "JEV_LOG", path)
    res = _res(stats={"vocab_gate": {"cards": 12}}, log=["card 2/12: Ash Ward ready", "relic OK: Anvil"])
    assert forge._append_jev_signals(res, user_id=1, concept="x") is False
    assert not path.exists()


def test_triage_and_snapped_lines_count_as_jev(tmp_path, monkeypatch):
    path = tmp_path / "jev.jsonl"
    monkeypatch.setattr(forge, "JEV_LOG", path)
    res = _res(stats={}, log=["gap X [triage: typo]", "snapped nomination Foo -> Bar", "unrelated"])
    assert forge._append_jev_signals(res)
    row = json.loads(path.read_text(encoding="utf-8"))
    assert row["jev_lines"] == ["gap X [triage: typo]", "snapped nomination Foo -> Bar"]
    assert row["jev_qa"] is None and row["user_id"] is None


def test_unwritable_path_returns_false_without_raising(tmp_path, monkeypatch):
    blocker = tmp_path / "a_file"
    blocker.write_text("not a dir", encoding="utf-8")
    monkeypatch.setattr(forge, "JEV_LOG", blocker / "sub" / "jev.jsonl")
    assert forge._append_jev_signals(_res(), user_id=1, concept="x") is False


def test_odd_result_shape_never_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(forge, "JEV_LOG", tmp_path / "jev.jsonl")
    assert forge._append_jev_signals(SimpleNamespace(stats=None, log=None)) is False
    assert forge._append_jev_signals(object()) is False
