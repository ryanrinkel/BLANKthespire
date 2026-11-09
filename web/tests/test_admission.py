"""Forge admission: two independent pools (token / BYOK), each with its own slots and FIFO line, and one forge
per account at a time."""
from __future__ import annotations

import threading
import time

from conftest import H, login, seed_tokens, sse_events


def _drain_queues(app_module):
    with app_module._forge_admit_lock:
        app_module._forge_waiting_token.clear()
        app_module._forge_waiting_byok.clear()
        app_module._forge_running_token = 0
        app_module._forge_running_byok = 0


def test_token_and_byok_pools_are_independent(app_module, monkeypatch):
    """A full BYOK pool never delays a token forge (and vice versa); each pool admits up to its own limit and
    hands a freed slot to the head of its OWN line."""
    _drain_queues(app_module)
    monkeypatch.setattr(app_module, "FORGE_MAX_CONCURRENT", 1)
    monkeypatch.setattr(app_module, "FORGE_MAX_CONCURRENT_BYOK", 2)
    b1 = app_module._forge_enqueue(token=False)
    b2 = app_module._forge_enqueue(token=False)
    assert b1.is_set() and b2.is_set()             # the BYOK pool admits up to ITS limit (2)
    b3 = app_module._forge_enqueue(token=False)
    b4 = app_module._forge_enqueue(token=False)
    assert not b3.is_set() and not b4.is_set()
    t1 = app_module._forge_enqueue(token=True)
    assert t1.is_set()                             # a queued BYOK line never delays a token forge
    t2 = app_module._forge_enqueue(token=True)
    assert not t2.is_set()                         # ...but the token pool has its own limit (1)
    # positions are per line
    assert app_module._forge_position(b3) == 1 and app_module._forge_position(b4) == 2
    assert app_module._forge_position(t2) == 1
    assert app_module._forge_position(t1) == 0
    with app_module._forge_admit_lock:
        assert app_module._waiting_total() == 3    # the up-front 503 check still sees both lines
        assert (app_module._forge_running_token, app_module._forge_running_byok) == (1, 2)
    app_module._forge_release(token=True)          # a token slot frees -> the token line's head, not BYOK
    assert t2.is_set() and not b3.is_set()
    app_module._forge_release(token=False)         # a BYOK slot frees -> the BYOK line's head
    assert b3.is_set() and not b4.is_set()
    assert app_module._forge_abandon(b4) is True   # leave the line while queued
    assert app_module._forge_abandon(b4) is False
    app_module._forge_release(token=True)          # nobody waits: each pool's running count drops
    app_module._forge_release(token=False)
    app_module._forge_release(token=False)
    with app_module._forge_admit_lock:
        assert (app_module._forge_running_token, app_module._forge_running_byok) == (0, 0)
        assert app_module._waiting_total() == 0
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
