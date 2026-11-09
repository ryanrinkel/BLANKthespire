"""A forge must never cost a token without delivering a class: the worker settles every job exactly once,
regardless of whether the browser is still listening, a restart killed the process, or the forge overran."""
from __future__ import annotations

import json
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


# --- BYOK: slow is a wait, not a failure (WALK_AWAY_FORGE_PLAN section 1) --------------------------------
# A provider with no art backend of ours, so a BYOK forge in these tests never builds an image client.
BYOK_BODY = {"mode": "byok", "key": {"base_url": "https://api.deepseek.com/v1", "api_key": "k", "model": "m"}}


def _release_after(gate: threading.Event, seconds: float) -> None:
    t = threading.Timer(seconds, gate.set)
    t.daemon = True
    t.start()


def test_byok_ceiling_is_separate(client, app_module, stub_forge, monkeypatch):
    """The 20-minute cap is the TOKEN forge's; a BYOK forge running past it is just slow and still finishes."""
    login(client, "byokslow@example.com")
    seed_tokens(app_module, "byokslow@example.com", 1)
    monkeypatch.setattr(app_module, "FORGE_MAX_SECONDS", 0.3)
    monkeypatch.setattr(app_module, "FORGE_MAX_SECONDS_BYOK", 5)
    stub_forge.gate = threading.Event()
    _release_after(stub_forge.gate, 1.0)
    ev = sse_events(client.post("/api/forge-class", json={"concept": "slow byok", **BYOK_BODY}, headers=H))
    assert ev[-1][0] == "result"
    assert not any(e == "error" for e, _ in ev)
    j = _jobs_for(app_module, "byokslow@example.com")[-1]
    assert (j.mode, j.status, j.class_id) == ("byok", "done", ev[-1][1]["id"])
    # the same one-second stall on a token forge still trips the 0.3 s token cap
    stub_forge.gate = threading.Event()
    _release_after(stub_forge.gate, 1.0)
    ev = sse_events(client.post("/api/forge-class", json={"concept": "slow token", "mode": "token"}, headers=H))
    assert ev[-1][0] == "error" and ev[-1][1]["code"] == "forge.too_long"
    assert _wait(lambda: _jobs_for(app_module, "byokslow@example.com")[-1].class_id is not None)
    stub_forge.gate = None


def test_byok_ceiling_copy(client, app_module, stub_forge, monkeypatch):
    """A BYOK forge that does hit its (hours-long) ceiling gets BYOK wording: nothing refunded, no balance."""
    login(client, "byokstuck@example.com")
    monkeypatch.setattr(app_module, "FORGE_MAX_SECONDS_BYOK", 0.3)
    stub_forge.gate = threading.Event()
    ev = sse_events(client.post("/api/forge-class", json={"concept": "stuck byok", **BYOK_BODY}, headers=H))
    assert ev[-1][0] == "error"
    data = ev[-1][1]
    assert data["code"] == "forge.too_long_byok" and "token" not in data["error"]
    assert "token_balance" not in data
    j = _jobs_for(app_module, "byokstuck@example.com")[-1]
    assert j.status == "failed" and j.refunded == 0
    with app_module._user_active_lock:
        assert not app_module._user_active                    # the page stopped waiting: the account is free
    # the provider does finish in the end: the class is still saved
    stub_forge.gate.set()
    assert _wait(lambda: _jobs_for(app_module, "byokstuck@example.com")[-1].class_id is not None)
    names = [c["concept"] for c in client.get("/api/classes").get_json()["classes"]]
    assert "stuck byok" in names
    stub_forge.gate = None


def test_byok_pool_does_not_block_token(app_module, stub_forge, monkeypatch):
    """BYOK forges have their own slots: a full BYOK pool queues the next BYOK forge (with a position line)
    while a token forge runs straight away."""
    monkeypatch.setattr(app_module, "FORGE_MAX_CONCURRENT_BYOK", 1)
    gate = threading.Event()
    stub_forge.gate = gate
    out: dict = {}

    def byok(name):
        c = app_module.app.test_client()
        login(c, f"{name}@example.com")
        out[name] = sse_events(c.post("/api/forge-class", json={"concept": name, **BYOK_BODY}, headers=H))

    t1 = threading.Thread(target=byok, args=("pool-b1",), daemon=True)
    t1.start()
    assert _wait(lambda: len(stub_forge.calls) == 1)          # b1 holds the only BYOK slot, blocked in the forge
    t2 = threading.Thread(target=byok, args=("pool-b2",), daemon=True)
    t2.start()
    assert _wait(lambda: len(app_module._forge_waiting_byok) == 1)   # b2 waits in the BYOK line
    stub_forge.gate = None                                    # forges that START from now on don't block
    c3 = app_module.app.test_client()
    login(c3, "pool-tok@example.com")
    seed_tokens(app_module, "pool-tok@example.com", 1)
    ev = sse_events(c3.post("/api/forge-class", json={"concept": "tok", "mode": "token"}, headers=H))
    assert ev[-1][0] == "result"                              # never waited on the BYOK pool
    assert not any("console.queue" in json.dumps(d) or "in line" in json.dumps(d) for _, d in ev)
    assert len(app_module._forge_waiting_byok) == 1 and t2.is_alive()
    gate.set()                                                # b1 finishes -> its slot goes to b2
    t1.join(timeout=30)
    t2.join(timeout=30)
    assert out["pool-b1"][-1][0] == "result" and out["pool-b2"][-1][0] == "result"
    # the second BYOK forge narrated its wait. (i18n.get_text has no console.* table on the server, so today the
    # line goes out as the bare key; accept that or the rendered English text.)
    b2_lines = [str(d.get("message")) for e, d in out["pool-b2"] if e == "progress"]
    assert any(m.startswith("console.queue.busy") or "in line at position 1" in m for m in b2_lines)
    with app_module._forge_admit_lock:
        assert app_module._waiting_total() == 0
        assert (app_module._forge_running_token, app_module._forge_running_byok) == (0, 0)


def test_user_lock_outlives_cap(client, app_module, stub_forge, monkeypatch):
    """With the watchdog no longer freeing a BYOK forge at 20 min, the per-account lock has to hold for as long
    as the forge may legitimately run — past the OLD stale horizon (queue timeout + 15 min)."""
    assert app_module.USER_ACTIVE_STALE_S > app_module.FORGE_MAX_SECONDS_BYOK
    assert app_module.USER_ACTIVE_STALE_S > app_module.FORGE_QUEUE_TIMEOUT_S
    me = login(client, "longbyok@example.com")
    monkeypatch.setattr(app_module, "FORGE_MAX_SECONDS_BYOK", 5)
    stub_forge.gate = threading.Event()
    collected: dict = {}

    def run_first():
        collected["events"] = sse_events(
            client.post("/api/forge-class", json={"concept": "long one", **BYOK_BODY}, headers=H))

    t = threading.Thread(target=run_first, daemon=True)
    t.start()
    assert _wait(lambda: len(stub_forge.calls) == 1)
    # pretend the forge has been running for longer than the old 45-minute horizon
    with app_module._user_active_lock:
        app_module._user_active[me["id"]] -= app_module.FORGE_QUEUE_TIMEOUT_S + 900 + 60
    c2 = app_module.app.test_client()
    login(c2, "longbyok@example.com")
    r = c2.post("/api/forge-class", json={"concept": "second", **BYOK_BODY}, headers=H)
    assert r.status_code == 429 and r.get_json()["code"] == "forge.already_running"
    stub_forge.gate.set()
    t.join(timeout=30)
    assert collected["events"][-1][0] == "result"
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


# --- walk-away fields (WALK_AWAY_FORGE_PLAN.md 2.1, 2.2, 3.3) -----------------------------------------------

def test_status_carries_concept_started_at_and_pace_eta(client, app_module, stub_forge, monkeypatch):
    """A `pace:` progress line from the card pass becomes eta_s on the status endpoint (and is dropped with the
    worker); the status also carries the concept (120 chars), started_at and late=False while running."""
    login(client, "pace@example.com")
    gate = threading.Event()

    def forge_with_pace(concept, **kw):
        kw["on_event"]("card 3/35: Plague Lance ready…")
        kw["on_event"]("pace: 75s/card, ~40 min to go (32 cards left)")
        gate.wait(timeout=30)
        return dict(stub_forge.result)
    monkeypatch.setattr(app_module, "forge_to_bundle", forge_with_pace)
    concept = "a very slow provider " * 10
    fid = _first_event(_post_and_disconnect(client, {"concept": concept, **BYOK_BODY}))["forge_id"]
    assert _wait(lambda: client.get(f"/api/forge-jobs/{fid}").get_json().get("eta_s") is not None)
    j = client.get(f"/api/forge-jobs/{fid}").get_json()
    assert j["status"] == "running" and j["late"] is False and j["still_running"] is True
    assert 39 * 60 <= j["eta_s"] <= 40 * 60
    assert j["message"].startswith("pace: 75s/card")
    assert j["concept"] == concept[:120] and len(j["concept"]) == 120
    assert j["started_at"] and j["started_at"].endswith("+00:00")
    # the same forge is the library's in-progress row
    running = client.get("/api/classes").get_json()["running"]
    assert [r["forge_id"] for r in running] == [fid]
    assert running[0]["concept"] == concept[:120] and running[0]["message"].startswith("pace:")
    assert 39 * 60 <= running[0]["eta_s"] <= 40 * 60 and running[0]["age_s"] >= 0 and running[0]["started_at"]
    gate.set()
    assert _wait(lambda: client.get(f"/api/forge-jobs/{fid}").get_json()["status"] == "done")
    done = client.get(f"/api/forge-jobs/{fid}").get_json()
    assert done["eta_s"] is None and done["late"] is False and done["still_running"] is False
    assert fid not in app_module._forge_eta
    assert client.get("/api/classes").get_json()["running"] == []


def test_capped_job_is_followable_and_lands_late(client, app_module, stub_forge, monkeypatch):
    """After the ceiling settles a job (no class yet), `latest` still returns it past FORGE_LATEST_WINDOW_S
    while its worker runs; once the class is saved the status says late=True with the class id."""
    login(client, "capfollow@example.com")
    monkeypatch.setattr(app_module, "FORGE_MAX_SECONDS_BYOK", 0.3)
    monkeypatch.setattr(app_module, "FORGE_LATEST_WINDOW_S", -1)   # "recent" never applies: only the cap rule
    stub_forge.gate = threading.Event()
    ev = sse_events(client.post("/api/forge-class", json={"concept": "capped one", **BYOK_BODY}, headers=H))
    assert ev[-1][0] == "error" and ev[-1][1]["code"] == "forge.too_long_byok"
    j = client.get("/api/forge-jobs/latest").get_json()
    assert j["status"] == "failed" and j["class_id"] is None and j["late"] is False
    assert j["code"] == "forge.too_long_job" and "abandoned" in j["error"]
    assert j["still_running"] is True and "message" in j
    assert client.get("/api/classes").get_json()["running"] == []     # settled: no longer a running row
    stub_forge.gate.set()
    assert _wait(lambda: client.get(f"/api/forge-jobs/{j['forge_id']}").get_json()["class_id"] is not None)
    late = client.get(f"/api/forge-jobs/{j['forge_id']}").get_json()
    assert late["late"] is True and late["status"] == "failed" and late["still_running"] is False
    assert client.get(f"/api/classes/{late['class_id']}").status_code == 200
    # the worker is gone and the job has its class: past the window `latest` no longer offers it
    assert client.get("/api/forge-jobs/latest").status_code == 404
    stub_forge.gate = None


def test_capped_job_whose_worker_died_is_not_offered(client, app_module):
    """A cap-settled job with no live worker (a restart, or a forge that failed after the cap) is not
    'the forge still running': `latest` keeps its recent-only rule for it and still_running is False."""
    from datetime import datetime, timedelta, timezone
    import i18n
    from models import ForgeJob, User
    login(client, "capdead@example.com")
    err = i18n.get_text("en", "server.forge.too_long_job", max_seconds=14400)
    with app_module.session_scope() as s:
        uid = s.query(User).filter_by(email="capdead@example.com").one().id
        s.add(ForgeJob(id="c" * 32, user_id=uid, mode="byok", status="failed", error=err,
                       started_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=5)))
    assert client.get("/api/forge-jobs/latest").status_code == 404
    assert client.get("/api/forge-jobs/latest?quiet=1").status_code == 204   # the page-load probe: no console 404
    j = client.get("/api/forge-jobs/" + "c" * 32).get_json()
    assert j["code"] == "forge.too_long_job" and j["still_running"] is False and j["late"] is False


def test_classes_running_is_own_running_jobs_only(client, app_module):
    from models import ForgeJob, User
    login(client, "runrows@example.com")
    with app_module.session_scope() as s:
        uid = s.query(User).filter_by(email="runrows@example.com").one().id
        s.add(ForgeJob(id="r" * 32, user_id=uid, mode="byok", status="running", concept="a goose knight"))
        s.add(ForgeJob(id="d" * 32, user_id=uid, mode="byok", status="done", concept="done one", class_id=7))
    login(client, "otherrun@example.com")
    with app_module.session_scope() as s:
        oid = s.query(User).filter_by(email="otherrun@example.com").one().id
        s.add(ForgeJob(id="o" * 32, user_id=oid, mode="token", status="running", concept="not yours"))
    login(client, "runrows@example.com")
    body = client.get("/api/classes").get_json()
    assert body["classes"] == []
    assert [(r["forge_id"], r["concept"], r["message"], r["eta_s"]) for r in body["running"]] == [
        ("r" * 32, "a goose knight", "", None)]
