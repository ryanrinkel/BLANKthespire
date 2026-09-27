"""A forge must never cost a token without delivering a class: the worker settles every job exactly once,
regardless of whether the browser is still listening, a restart killed the process, or the forge overran."""
from __future__ import annotations

import threading
import time

from conftest import H, login, seed_tokens, sse_events


def _job(app_module, forge_id):
    from models import ForgeJob
    with app_module.session_scope() as s:
        return s.query(ForgeJob).filter_by(id=forge_id).one()


def _jobs_for(app_module, email):
    from models import ForgeJob, User
    with app_module.session_scope() as s:
        uid = s.query(User).filter_by(email=email).one().id
        return s.query(ForgeJob).filter_by(user_id=uid).order_by(ForgeJob.started_at).all()


def _me(client):
    return client.get("/api/me").get_json()["user"]


def _wait(cond, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return False


def _post_and_disconnect(client, body):
    """Start a forge, read the first SSE chunk, then close the response — what a closed tab looks like to
    the server: the stream generator is shut, the worker thread carries on."""
    resp = client.post("/api/forge-class", json=body, headers=H, buffered=False)
    it = iter(resp.response)
    first = next(it)
    resp.close()
    return first


def test_every_forge_opens_a_job_and_settles_it(client, app_module, stub_forge):
    login(client, "jobs@example.com")
    seed_tokens(app_module, "jobs@example.com", 1)
    ev = sse_events(client.post("/api/forge-class", json={"concept": "x", "mode": "token"}, headers=H))
    assert ev[-1][0] == "result"
    jobs = _jobs_for(app_module, "jobs@example.com")
    assert len(jobs) == 1
    j = jobs[0]
    assert (j.status, j.token_kind, j.class_id, j.refunded) == ("done", "paid", ev[-1][1]["id"], 0)
    assert j.finished_at is not None and j.mode == "token"


def test_disconnect_then_success_still_saves_the_class(client, app_module, stub_forge):
    login(client, "gone@example.com")
    seed_tokens(app_module, "gone@example.com", 1)
    stub_forge.gate = threading.Event()
    _post_and_disconnect(client, {"concept": "closed the tab", "mode": "token"})
    stub_forge.gate.set()
    assert _wait(lambda: _jobs_for(app_module, "gone@example.com")[-1].status != "running")
    j = _jobs_for(app_module, "gone@example.com")[-1]
    assert j.status == "done" and j.class_id
    names = [c["concept"] for c in client.get("/api/classes").get_json()["classes"]]
    assert "closed the tab" in names          # it's in My Classes even though nobody watched the stream
    assert _me(client)["token_balance"] == 0          # the token was rightly spent
    with app_module._user_active_lock:
        assert not app_module._user_active
    stub_forge.gate = None


def test_disconnect_then_failure_refunds_the_token(client, app_module, stub_forge):
    login(client, "gonefail@example.com")
    seed_tokens(app_module, "gonefail@example.com", 2)
    stub_forge.gate = threading.Event()
    stub_forge.error = "provider died"
    _post_and_disconnect(client, {"concept": "x", "mode": "token"})
    assert _me(client)["token_balance"] == 1              # charged up front
    stub_forge.gate.set()
    assert _wait(lambda: _jobs_for(app_module, "gonefail@example.com")[-1].status != "running")
    j = _jobs_for(app_module, "gonefail@example.com")[-1]
    assert j.status == "failed" and j.refunded == 1 and "provider died" in j.error
    assert _me(client)["token_balance"] == 2               # refunded with nobody listening
    stub_forge.gate = None
    stub_forge.error = None


def test_restart_reconciliation_refunds_running_jobs(client, app_module):
    from models import ForgeJob, User
    login(client, "crashed@example.com")
    with app_module.session_scope() as s:
        u = s.query(User).filter_by(email="crashed@example.com").one()
        u.token_balance = 2                                    # a paid token was reserved mid-forge
        s.add(ForgeJob(id="deadbeef" * 4, user_id=u.id, mode="token", token_kind="paid", status="running"))
        s.add(ForgeJob(id="cafef00d" * 4, user_id=u.id, mode="byok", token_kind=None, status="running"))
        s.add(ForgeJob(id="0badf00d" * 4, user_id=u.id, mode="token", token_kind="paid", status="done",
                       class_id=1))
    assert app_module._reconcile_forge_jobs() == 2
    assert app_module._reconcile_forge_jobs() == 0           # idempotent
    j1, j2, j3 = (_job(app_module, i * 4) for i in ("deadbeef", "cafef00d", "0badf00d"))
    assert j1.status == "failed" and j1.refunded == 1 and "restarted" in j1.error
    assert j2.status == "failed" and j2.refunded == 0        # BYOK: nothing to refund
    assert j3.status == "done"                                # finished jobs are untouched
    assert _me(client)["token_balance"] == 3


def test_settle_is_exactly_once(client, app_module):
    from models import ForgeJob, User
    login(client, "once@example.com")
    with app_module.session_scope() as s:
        u = s.query(User).filter_by(email="once@example.com").one()
        u.token_balance = 1
        s.add(ForgeJob(id="feedface" * 4, user_id=u.id, mode="token", token_kind="paid", status="running"))
    assert app_module._settle_forge_job("feedface" * 4, ok=False, error="a")[0] is True
    assert app_module._settle_forge_job("feedface" * 4, ok=False, error="b")[0] is False
    assert app_module._settle_forge_job("feedface" * 4, ok=True)[0] is False
    assert _me(client)["token_balance"] == 2                  # refunded once, not three times


def test_wall_clock_cap_refunds_and_frees_the_slot(client, app_module, stub_forge, monkeypatch):
    login(client, "slow@example.com")
    seed_tokens(app_module, "slow@example.com", 1)
    monkeypatch.setattr(app_module, "FORGE_MAX_SECONDS", 0.3)
    stub_forge.gate = threading.Event()
    ev = sse_events(client.post("/api/forge-class", json={"concept": "slow one", "mode": "token"}, headers=H))
    assert ev[-1][0] == "error" and "abandoned" in ev[-1][1]["error"]
    assert ev[-1][1]["token_balance"] == 1                   # refunded by the watchdog
    j = _jobs_for(app_module, "slow@example.com")[-1]
    assert j.status == "failed" and j.refunded == 1
    with app_module._user_active_lock:
        assert not app_module._user_active                    # they can start another forge right away
    # the overrunning forge eventually succeeds: the class is still saved, the token stays refunded
    stub_forge.gate.set()
    assert _wait(lambda: _jobs_for(app_module, "slow@example.com")[-1].class_id is not None)
    names = [c["concept"] for c in client.get("/api/classes").get_json()["classes"]]
    assert "slow one" in names
    assert _me(client)["token_balance"] == 1
    stub_forge.gate = None


def test_queue_timeout_settles_without_refund_confusion(client, app_module, stub_forge, monkeypatch):
    """A queue-wait timeout is a failed job too: settled once, token refunded, slot released."""
    login(client, "queued@example.com")
    seed_tokens(app_module, "queued@example.com", 1)
    monkeypatch.setattr(app_module, "FORGE_MAX_CONCURRENT", 0)      # nobody may run: everyone queues
    monkeypatch.setattr(app_module, "FORGE_QUEUE_TIMEOUT_S", 0)
    ev = sse_events(client.post("/api/forge-class", json={"concept": "x", "mode": "token"}, headers=H))
    assert ev[-1][0] == "error" and "capacity" in ev[-1][1]["error"]
    j = _jobs_for(app_module, "queued@example.com")[-1]
    assert j.status == "failed" and j.refunded == 1
    assert _me(client)["token_balance"] == 1
    with app_module._user_active_lock:
        assert not app_module._user_active
    with app_module._forge_admit_lock:
        assert app_module._waiting_total() == 0


# --- GET /api/forge-jobs/<id>: the poll a browser falls back to when its stream drops (2026-09-26) ---------

def _first_event(raw: bytes) -> dict:
    import json
    text = raw.decode() if isinstance(raw, bytes) else raw
    return json.loads(text.split("data:", 1)[1].split("\n", 1)[0])


def test_poll_follows_a_dropped_forge_to_its_class(client, app_module, stub_forge):
    login(client, "poll@example.com")
    seed_tokens(app_module, "poll@example.com", 1)
    stub_forge.gate = threading.Event()
    first = _first_event(_post_and_disconnect(client, {"concept": "lost the phone", "mode": "token"}))
    fid = first["forge_id"]                                   # the first event names the job to poll
    run = client.get(f"/api/forge-jobs/{fid}").get_json()
    assert run["status"] == "running" and run["token_balance"] == 0 and run["class_id"] is None
    assert client.get("/api/forge-jobs/latest").get_json()["forge_id"] == fid
    stub_forge.gate.set()
    assert _wait(lambda: client.get(f"/api/forge-jobs/{fid}").get_json()["status"] != "running")
    done = client.get(f"/api/forge-jobs/{fid}").get_json()
    assert done["status"] == "done" and done["class_id"] and not done["refunded"]
    assert client.get(f"/api/classes/{done['class_id']}").status_code == 200
    assert fid not in app_module._forge_progress              # the live line is dropped with the worker
    stub_forge.gate = None


def test_poll_reports_a_failed_forge_and_its_refund(client, app_module, stub_forge):
    login(client, "pollfail@example.com")
    seed_tokens(app_module, "pollfail@example.com", 1)
    stub_forge.error = "provider died"
    fid = _first_event(_post_and_disconnect(client, {"concept": "x", "mode": "token"}))["forge_id"]
    assert _wait(lambda: client.get(f"/api/forge-jobs/{fid}").get_json()["status"] != "running")
    j = client.get(f"/api/forge-jobs/{fid}").get_json()
    assert j["status"] == "failed" and j["refunded"] and "provider died" in j["error"]
    assert j["token_balance"] == 1
    stub_forge.error = None


def test_poll_is_owner_only_and_latest_is_recent_only(client, app_module):
    from models import ForgeJob, User
    login(client, "owner@example.com")
    with app_module.session_scope() as s:
        uid = s.query(User).filter_by(email="owner@example.com").one().id
        s.add(ForgeJob(id="a" * 32, user_id=uid, mode="token", token_kind="paid", status="done", class_id=1))
    assert client.get("/api/forge-jobs/" + "a" * 32).status_code == 200
    login(client, "stranger@example.com")
    assert client.get("/api/forge-jobs/" + "a" * 32).status_code == 404
    assert client.get("/api/forge-jobs/latest").status_code == 404      # stranger has no forges
    login(client, "owner@example.com")
    with app_module.session_scope() as s:  # an old finished forge is not "the one you just started"
        from datetime import datetime, timedelta, timezone
        an_hour_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        s.query(ForgeJob).filter_by(id="a" * 32).update({"started_at": an_hour_ago})
    assert client.get("/api/forge-jobs/latest").status_code == 404


def test_poll_surfaces_a_pending_engine_pick(client, app_module, stub_forge, monkeypatch):
    login(client, "pollpick@example.com")
    seed_tokens(app_module, "pollpick@example.com", 1)
    offered = [{"id": "poison", "name": "Poison"}, {"id": "block", "name": "Block"}]
    picked: list = []

    def forge_with_pick(concept, **kw):
        picked.append(kw["archetype_checkpoint"](offered, {}))
        return dict(stub_forge.result)
    monkeypatch.setattr(app_module, "forge_to_bundle", forge_with_pick)
    fid = _first_event(_post_and_disconnect(
        client, {"concept": "x", "mode": "token", "interactive": True}))["forge_id"]
    assert _wait(lambda: "choice" in client.get(f"/api/forge-jobs/{fid}").get_json())
    ch = client.get(f"/api/forge-jobs/{fid}").get_json()["choice"]
    assert ch["forge_id"] == fid and ch["options"] == offered and 0 < ch["timeout_s"] <= 120
    assert client.post("/api/forge/answer", json={"forge_id": fid, "archetypes": ["poison"]},
                       headers=H).status_code == 200
    assert _wait(lambda: client.get(f"/api/forge-jobs/{fid}").get_json()["status"] == "done")
    assert picked == [["poison"]]
