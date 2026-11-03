"""The admin Experiments card's API (/api/admin/experiments, docs/plans/AB_TESTING_PLAN.md 3.5): the registry
is the truth (an experiment is listed the moment it deploys, with no exposures), traffic.json's
"experiments" block supplies the numbers, ended experiments drop off after 30 days."""
from __future__ import annotations

import json

import pytest

import ab_report
import experiments
from conftest import login
from experiments import Experiment

ADMIN = "unlimited@example.com"
TODAY = "2026-11-20"


def _exp(**over) -> Experiment:
    base = dict(name="hero", page="/", arms=("a", "b"), weights=(50, 50), salt="s1",
                started="2026-11-03", planned_end="2026-12-15", primary="login",
                hypothesis="Saying the price lifts /login opens.",
                arms_text={"a": "Button says 'Create Your Own Class'", "b": "Button says 'free with your key'"})
    base.update(over)
    return Experiment(**base)


REGISTRY = [
    _exp(),
    _exp(name="pcnote", page="/download", started="2026-09-01", planned_end="2026-09-30",
         ended="2026-10-01", winner="a"),                                      # ended 50 days ago: gone
    _exp(name="recent", page="/help", started="2026-10-01", planned_end="2026-11-01",
         ended="2026-11-02", winner="b"),                                      # ended 18 days ago: kept
]


def _arm(exposures, login_n, **over):
    row = {"exposures": exposures, "clicked": login_n + 3, "browser": 5, "landing_only": 2, "signed_in": 1,
           "login": login_n, "provider": 1, "workshop": 0, "deck": 0, "archive": 0, "download": 0,
           "primary": login_n, "devices": {"desktop": exposures - 4, "phone": 3, "phone_webview": 1}}
    row.update(over)
    return row


def _traffic_block():
    return {"hero": {
        "name": "hero", "page": "/", "arms": ["a", "b"],
        "per_arm": {"a": _arm(120, 6), "b": _arm(118, 14)},
        "daily": [{"day": "2026-11-19", "exposures": {"a": 9, "b": 8}, "primary": {"a": 0, "b": 1}}],
        "exposure_rate_7d": 8.5, "control_rate": 0.05, "days_to_decision": 120.0, "sample_size_per_arm": 1020,
        "decision": {"status": "stale — recomputed by the route"},
    }}


@pytest.fixture
def registry(monkeypatch):
    monkeypatch.setattr(experiments, "EXPERIMENTS", list(REGISTRY))
    monkeypatch.setattr(experiments, "today_utc", lambda: TODAY)
    return REGISTRY


def _traffic_dir(app_module):
    d = app_module.TRAFFIC_DIR
    d.mkdir(parents=True, exist_ok=True)
    for f in d.iterdir():
        f.unlink()
    return d


def test_non_admin_is_forbidden(client, app_module):
    login(client, "nobody@example.com")
    assert client.get("/api/admin/experiments").status_code == 403


def test_signed_out(client):
    client.post("/logout", headers={"X-Requested-With": "fetch"})
    assert client.get("/api/admin/experiments").status_code == 401


def test_listed_from_the_registry_without_a_traffic_summary(client, app_module, registry):
    _traffic_dir(app_module)
    login(client, ADMIN)
    body = client.get("/api/admin/experiments").get_json()
    assert body["available"] is False and "timer" in body["reason"]
    assert body["today"] == TODAY
    assert body["rule"] == {"p_threshold": 0.95, "min_exposures": 200, "min_days": 14}
    names = [e["name"] for e in body["experiments"]]
    assert names == ["hero", "recent"]          # pcnote ended > 30 days ago
    hero = body["experiments"][0]
    assert hero["per_arm"] == {} and hero["accounts"] is None and hero["live"] is True
    assert hero["decision"]["status"] == "running — not yet"
    assert hero["hypothesis"] == "Saying the price lifts /login opens."
    assert "No exposures yet" in hero["readout"]
    assert hero["day"] == 18 and hero["of"] == 42
    assert hero["preview"] == {"a": "/?ab=hero:a", "b": "/?ab=hero:b"}
    recent = body["experiments"][1]
    assert recent["live"] is False and recent["decision"]["status"] == "ended — winner b"
    assert recent["day"] == 32                  # stopped counting at `ended`


def test_merges_the_traffic_numbers(client, app_module, registry):
    d = _traffic_dir(app_module)
    (d / "traffic.json").write_text(json.dumps({"daily": [], "experiments": _traffic_block()}))
    login(client, ADMIN)
    body = client.get("/api/admin/experiments").get_json()
    assert body["available"] is True and body["reason"] is None
    hero = next(e for e in body["experiments"] if e["name"] == "hero")
    assert hero["per_arm"]["b"]["login"] == 14 and hero["per_arm"]["a"]["devices"]["phone"] == 3
    assert hero["exposure_rate_7d"] == 8.5 and hero["sample_size_per_arm"] == 1020
    assert len(hero["daily"]) == 1
    p = hero["decision"]["p_beats_control"]["b"]
    assert 0.9 < p < 1.0                         # 14/118 vs 6/120
    assert hero["decision"]["status"] == "running — not yet"   # < 200 exposures per arm
    assert hero["arms_text"]["b"].startswith("Button says")
    assert "P(b beats a): " in hero["readout"] and "not yet" in hero["readout"]
    assert "~17 weeks" in hero["readout"] and "exposures/week" in hero["readout"]


def test_old_traffic_json_without_experiments_still_lists(client, app_module, registry):
    d = _traffic_dir(app_module)
    (d / "traffic.json").write_text(json.dumps({"daily": [], "windows": {}}))
    login(client, ADMIN)
    body = client.get("/api/admin/experiments").get_json()
    assert body["available"] is True
    assert [e["name"] for e in body["experiments"]] == ["hero", "recent"]
    assert body["experiments"][0]["per_arm"] == {}


def test_traffic_route_unchanged_by_the_shared_reader(client, app_module):
    d = _traffic_dir(app_module)
    login(client, ADMIN)
    r = client.get("/api/admin/traffic")
    assert r.status_code == 200 and r.get_json()["available"] is False
    (d / "traffic.json").write_text("{not json")
    assert client.get("/api/admin/traffic").status_code == 500
    # the experiments card still answers (registry only), flagging the bad file
    body = client.get("/api/admin/experiments").get_json()
    assert body["available"] is False and "unreadable" in body["reason"]


# --- the pure payload builder (shared with the mail) ------------------------------------------------

def test_payload_winner_by_rule_and_control_rate_zero():
    exp = _exp(started="2026-10-01", planned_end="2026-12-15")
    traffic = {"experiments": {"hero": {"per_arm": {"a": _arm(400, 20), "b": _arm(400, 60)},
                                        "exposure_rate_7d": 20, "control_rate": 0.05, "days_to_decision": 40}}}
    [e] = ab_report.build_experiments_payload(traffic, TODAY, experiments=[exp])
    assert e["decision"]["winner_by_rule"] == "b" and e["status_kind"] == "winner"
    assert "winner by the rule: b" in e["readout"]

    traffic["experiments"]["hero"].update(per_arm={"a": _arm(30, 0), "b": _arm(30, 2)}, control_rate=0.0)
    [e] = ab_report.build_experiments_payload(traffic, TODAY, experiments=[exp])
    assert "No /login opened in the control yet" in e["readout"]


def test_payload_lists_a_not_yet_started_experiment():
    [e] = ab_report.build_experiments_payload(None, TODAY, experiments=[_exp(started="2026-12-01",
                                                                              planned_end="2026-12-31")])
    assert e["live"] is False and e["day"] == 0 and e["decision"]["status"] == "not started"
    assert e["status_kind"] == "pending"
