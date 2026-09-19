"""Forge admission: token-first dequeue across the two wait lines, and one forge per account at a time."""
from __future__ import annotations

import threading
import time

from conftest import H, login, seed_tokens, sse_events


def _drain_queues(app_module):
    with app_module._forge_admit_lock:
        app_module._forge_waiting_token.clear()
        app_module._forge_waiting_byok.clear()
        app_module._forge_priority.clear()
        app_module._forge_running = 0


def test_token_forges_dequeue_before_byok(app_module, monkeypatch):
    _drain_queues(app_module)
    monkeypatch.setattr(app_module, "FORGE_MAX_CONCURRENT", 1)
    running = app_module._forge_enqueue(priority=False)
    assert running.is_set()
    byok1 = app_module._forge_enqueue(priority=False)
    tok1 = app_module._forge_enqueue(priority=True)
    byok2 = app_module._forge_enqueue(priority=False)
    assert not byok1.is_set() and not tok1.is_set()
    # positions: the token line is served first, so it reports ahead of BYOK forges that arrived earlier
    assert app_module._forge_position(tok1) == 1
    assert app_module._forge_position(byok1) == 2 and app_module._forge_position(byok2) == 3
    app_module._forge_release()                    # slot frees -> token forge runs first
    assert tok1.is_set() and not byok1.is_set()
    app_module._forge_release()
    assert byok1.is_set() and not byok2.is_set()
    assert app_module._forge_abandon(byok2) is True  # leave the line while queued
    app_module._forge_release()                    # nobody waits: running count drops
    with app_module._forge_admit_lock:
        assert app_module._forge_running == 0
    _drain_queues(app_module)


def test_one_forge_per_account_at_a_time(app_module, stub_forge):
    c1 = app_module.app.test_client()
    login(c1, "busy@example.com")
    seed_tokens(app_module, "busy@example.com", 2)
    stub_forge.gate = threading.Event()  # the stubbed forge blocks until we release it
    collected: dict = {}

    def run_first():
        collected["events"] = sse_events(
            c1.post("/api/forge-class", json={"concept": "x", "mode": "token"}, headers=H))

    t = threading.Thread(target=run_first, daemon=True)
    t.start()
    for _ in range(100):  # wait until the first forge is actually in flight
        with app_module._user_active_lock:
            if app_module._user_active:
                break
        time.sleep(0.02)
    c2 = app_module.app.test_client()
    login(c2, "busy@example.com")
    r = c2.post("/api/forge-class", json={"concept": "y", "mode": "token"}, headers=H)
    assert r.status_code == 429 and "in progress" in r.get_json()["error"]
    # a different account is unaffected
    c3 = app_module.app.test_client()
    login(c3, "other@example.com")
    seed_tokens(app_module, "other@example.com", 1)
    stub_forge.gate.set()
    assert sse_events(c3.post("/api/forge-class", json={"concept": "z", "mode": "token"}, headers=H))[-1][0] == "result"
    t.join(timeout=30)
    assert collected["events"][-1][0] == "result"
    # the slot is released once the forge finishes
    with app_module._user_active_lock:
        assert not app_module._user_active
    stub_forge.gate = None


def test_user_slot_is_released_on_early_rejections(client, app_module, stub_forge):
    login(client, "rejected@example.com")            # a fresh account holds nothing to spend
    assert client.post("/api/forge-class", json={"concept": "x", "mode": "token"}, headers=H).status_code == 402
    with app_module._user_active_lock:
        assert not app_module._user_active   # the 402 path gave the per-user slot back
