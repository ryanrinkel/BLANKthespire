"""Past-forge timings for the BYOK picker (WALK_AWAY_FORGE_PLAN.md 4.1) and the projection a BYOK forge stores
for calibration (4.6). History counts forges whose CARDS ran on the provider host + model, any account; a
job settled by the wall-clock cap that landed anyway is measured to its class row, not to the watchdog."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from conftest import H, login, sse_events

HOST = "api.histtest.example"
URL = f"https://{HOST}/v1"
T0 = datetime(2026, 11, 8, 12, 0, 0)


def _seed(app_module, uid, fid, *, status, wall=None, out=1000, model="slowthink-1", role="cards",
          host=HOST, class_after=None):
    """One forge_jobs row (+ its forge_usage row, + a class row when class_after is given)."""
    from models import ForgedClass, ForgeJob, ForgeUsage
    with app_module.session_scope() as s:
        class_id = None
        if class_after is not None:
            c = ForgedClass(user_id=uid, name="Late", concept="c", code="BTSC.x", bundle_json="{}",
                            created_at=T0 + timedelta(seconds=class_after))
            s.add(c)
            s.flush()
            class_id = c.id
        s.add(ForgeJob(id=fid, user_id=uid, mode="byok", concept="secret concept", status=status,
                       class_id=class_id, started_at=T0,
                       finished_at=(T0 + timedelta(seconds=wall)) if wall is not None else None))
        s.add(ForgeUsage(user_id=uid, forge_id=fid, mode="byok", role=role, model=model, provider=host,
                         calls=40, output_tokens=out))


def _reset(app_module):
    from models import ForgeJob, ForgeUsage
    with app_module.session_scope() as s:
        s.query(ForgeUsage).filter(ForgeUsage.provider.in_([HOST, "api.other.example"])).delete(
            synchronize_session=False)
        s.query(ForgeJob).filter(ForgeJob.id.like("hist%")).delete(synchronize_session=False)
    app_module._model_history_cache.clear()


def test_history_median_p90_and_late_finish(client, app_module):
    uid = login(client)["id"]
    _reset(app_module)
    _seed(app_module, uid, "hist-a", status="done", wall=600, out=20000)
    _seed(app_module, uid, "hist-b", status="done", wall=1200, out=30000)
    # cap-settled at 1200 s (the watchdog's finished_at) but the class landed at 3000 s: wall is 3000
    _seed(app_module, uid, "hist-c", status="failed", wall=1200, out=40000, class_after=3000)
    _seed(app_module, uid, "hist-d", status="failed", wall=50)                        # failed, no class
    _seed(app_module, uid, "hist-e", status="running")                                # still running
    _seed(app_module, uid, "hist-f", status="done", wall=9999, model="other-model")   # other model
    _seed(app_module, uid, "hist-g", status="done", wall=9999, role="structure")      # design role only
    _seed(app_module, uid, "hist-h", status="done", wall=9999, host="api.other.example")  # other host

    r = client.get("/api/model-history", query_string={"base_url": URL, "model": "slowthink-1"})
    assert r.status_code == 200
    assert r.get_json() == {"n": 3, "median_s": 1200, "p90_s": 3000, "median_output_tokens": 30000}
    assert "secret concept" not in r.get_data(as_text=True)

    # unknown pair / missing params
    assert client.get("/api/model-history", query_string={"base_url": URL, "model": "nope"}).get_json() == {"n": 0}
    assert client.get("/api/model-history").get_json() == {"n": 0}


def test_history_is_cached(client, app_module):
    uid = login(client)["id"]
    _reset(app_module)
    _seed(app_module, uid, "hist-1", status="done", wall=300)
    q = {"base_url": URL, "model": "slowthink-1"}
    assert client.get("/api/model-history", query_string=q).get_json()["n"] == 1
    _seed(app_module, uid, "hist-2", status="done", wall=400)
    assert client.get("/api/model-history", query_string=q).get_json()["n"] == 1   # 10-min cache
    app_module._model_history_cache.clear()
    assert client.get("/api/model-history", query_string=q).get_json()["n"] == 2


def test_history_needs_login(client):
    r = client.get("/api/model-history", query_string={"base_url": URL, "model": "m"})
    assert r.status_code in (302, 401)


def test_forge_stores_the_projection_without_the_key(client, app_module, stub_forge):
    from models import ForgeJob
    login(client)
    key = {"base_url": "https://api.example.com/v1", "api_key": "sk-NEVER-STORED", "model": "m"}
    body = {"concept": "x", "mode": "byok", "key": key,
            "projection": {"projected_s": 3300, "tps": 45, "multiplier": 5.0, "first_token_s": 1.2,
                           "api_key": "sk-NEVER-STORED", "junk": "x"}}
    ev = sse_events(client.post("/api/forge-class", json=body, headers=H))
    assert ev[-1][0] == "result"
    fid = next(d["forge_id"] for _, d in ev if isinstance(d, dict) and d.get("forge_id"))
    with app_module.session_scope() as s:
        job = s.query(ForgeJob).filter_by(id=fid).one()
        assert job.projected_s == 3300
        assert json.loads(job.probe_json) == {"projected_s": 3300, "tps": 45, "multiplier": 5.0,
                                              "first_token_s": 1.2}
        assert "sk-NEVER" not in (job.probe_json or "")

    # no projection sent -> both columns stay NULL
    ev = sse_events(client.post("/api/forge-class", json={"concept": "y", "mode": "byok", "key": key}, headers=H))
    fid = next(d["forge_id"] for _, d in ev if isinstance(d, dict) and d.get("forge_id"))
    with app_module.session_scope() as s:
        job = s.query(ForgeJob).filter_by(id=fid).one()
        assert job.projected_s is None and job.probe_json is None
