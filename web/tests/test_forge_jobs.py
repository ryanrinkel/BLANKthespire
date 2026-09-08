"""A forge must never cost a token without delivering a class: the worker settles every job exactly once,
regardless of whether the browser is still listening, a restart killed the process, or the forge overran."""
from __future__ import annotations

import threading
import time

from conftest import H, login, sse_events


def _today():
    from models import _utc_today
    return _utc_today()


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
    ev = sse_events(client.post("/api/forge-class", json={"concept": "x", "mode": "token"}, headers=H))
    assert ev[-1][0] == "result"
    jobs = _jobs_for(app_module, "jobs@example.com")
    assert len(jobs) == 1
    j = jobs[0]
    assert (j.status, j.token_kind, j.class_id, j.refunded) == ("done", "free", ev[-1][1]["id"], 0)
    assert j.finished_at is not None and j.mode == "token"


def test_disconnect_then_success_still_saves_the_class(client, app_module, stub_forge):
    login(client, "gone@example.com")
    stub_forge.gate = threading.Event()
    _post_and_disconnect(client, {"concept": "closed the tab", "mode": "token"})
    stub_forge.gate.set()
    assert _wait(lambda: _jobs_for(app_module, "gone@example.com")[-1].status != "running")
    j = _jobs_for(app_module, "gone@example.com")[-1]
    assert j.status == "done" and j.class_id
    names = [c["concept"] for c in client.get("/api/classes").get_json()["classes"]]
    assert "closed the tab" in names          # it's in My Classes even though nobody watched the stream
    me = _me(client)
    assert me["free_token_available"] is False and me["token_balance"] == 5   # the token was rightly spent
    with app_module._user_active_lock:
        assert not app_module._user_active
    stub_forge.gate = None


def test_disconnect_then_failure_refunds_the_token(client, app_module, stub_forge):
    login(client, "gonefail@example.com")
    stub_forge.gate = threading.Event()
    stub_forge.error = "provider died"
    _post_and_disconnect(client, {"concept": "x", "mode": "token"})
    assert _me(client)["free_token_available"] is False   # charged up front
    stub_forge.gate.set()
    assert _wait(lambda: _jobs_for(app_module, "gonefail@example.com")[-1].status != "running")
    j = _jobs_for(app_module, "gonefail@example.com")[-1]
    assert j.status == "failed" and j.refunded == 1 and "provider died" in j.error
    assert _me(client)["free_token_available"] is True     # refunded with nobody listening
    stub_forge.gate = None
    stub_forge.error = None


def test_restart_reconciliation_refunds_running_jobs(client, app_module):
    from models import ForgeJob, User
    login(client, "crashed@example.com")
    with app_module.session_scope() as s:
        u = s.query(User).filter_by(email="crashed@example.com").one()
        u.token_balance, u.last_free_token_day = 2, _today()   # a paid token was reserved mid-forge
        s.add(ForgeJob(id="deadbeef" * 4, user_id=u.id, mode="token", token_kind="paid", token_day=_today(),
                       status="running"))
        s.add(ForgeJob(id="cafef00d" * 4, user_id=u.id, mode="byok", token_kind=None, status="running"))
        s.add(ForgeJob(id="0badf00d" * 4, user_id=u.id, mode="token", token_kind="free", status="done",
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
        u.token_balance, u.last_free_token_day = 1, _today()
        s.add(ForgeJob(id="feedface" * 4, user_id=u.id, mode="token", token_kind="paid", token_day=_today(),
                       status="running"))
    assert app_module._settle_forge_job("feedface" * 4, ok=False, error="a")[0] is True
    assert app_module._settle_forge_job("feedface" * 4, ok=False, error="b")[0] is False
    assert app_module._settle_forge_job("feedface" * 4, ok=True)[0] is False
    assert _me(client)["token_balance"] == 2                  # refunded once, not three times


def test_wall_clock_cap_refunds_and_frees_the_slot(client, app_module, stub_forge, monkeypatch):
    login(client, "slow@example.com")
    monkeypatch.setattr(app_module, "FORGE_MAX_SECONDS", 0.3)
    stub_forge.gate = threading.Event()
    ev = sse_events(client.post("/api/forge-class", json={"concept": "slow one", "mode": "token"}, headers=H))
    assert ev[-1][0] == "error" and "abandoned" in ev[-1][1]["error"]
    assert ev[-1][1]["free_token_available"] is True         # refunded by the watchdog
    j = _jobs_for(app_module, "slow@example.com")[-1]
    assert j.status == "failed" and j.refunded == 1
    with app_module._user_active_lock:
        assert not app_module._user_active                    # they can start another forge right away
    # the overrunning forge eventually succeeds: the class is still saved, the token stays refunded
    stub_forge.gate.set()
    assert _wait(lambda: _jobs_for(app_module, "slow@example.com")[-1].class_id is not None)
    names = [c["concept"] for c in client.get("/api/classes").get_json()["classes"]]
    assert "slow one" in names
    assert _me(client)["free_token_available"] is True
    stub_forge.gate = None


def test_queue_timeout_settles_without_refund_confusion(client, app_module, stub_forge, monkeypatch):
    """A queue-wait timeout is a failed job too: settled once, token refunded, slot released."""
    login(client, "queued@example.com")
    monkeypatch.setattr(app_module, "FORGE_MAX_CONCURRENT", 0)      # nobody may run: everyone queues
    monkeypatch.setattr(app_module, "FORGE_QUEUE_TIMEOUT_S", 0)
    ev = sse_events(client.post("/api/forge-class", json={"concept": "x", "mode": "token"}, headers=H))
    assert ev[-1][0] == "error" and "capacity" in ev[-1][1]["error"]
    j = _jobs_for(app_module, "queued@example.com")[-1]
    assert j.status == "failed" and j.refunded == 1
    assert _me(client)["free_token_available"] is True
    with app_module._user_active_lock:
        assert not app_module._user_active
    with app_module._forge_admit_lock:
        assert app_module._waiting_total() == 0
