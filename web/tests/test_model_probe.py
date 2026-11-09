"""BYOK model probe (WALK_AWAY_FORGE_PLAN.md 4.2): one timed, streamed call on the user's key projects a
forge's duration as calls x first-token latency + visible x multiplier / speed. Driven against a local SSE
stub that streams visible content at a chosen rate and reports a chosen share of HIDDEN (reasoning) tokens
only in the usage chunk — the Doubao/DeepSeek shape that a speed-only probe would miss."""
from __future__ import annotations

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from conftest import H, login

import forge

KEY = "sk-probe-SECRET-0123456789"


class _Stub(BaseHTTPRequestHandler):
    """POST /v1/chat/completions -> SSE. Behaviour comes from the server's `cfg` dict."""

    def log_message(self, *a):  # keep the test output quiet
        pass

    def do_POST(self):
        srv = self.server
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        srv.requests.append({"auth": self.headers.get("Authorization"), "body": body})
        cfg = srv.cfg
        if cfg.get("status"):
            self.send_response(cfg["status"])
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": {"message": "nope"}}')
            return
        time.sleep(cfg.get("ttft", 0.0))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()

        def send(obj):
            self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
            self.wfile.flush()

        try:
            for _ in range(cfg.get("reasoning_chunks", 0)):  # streamed (visible-to-us) thinking
                send({"choices": [{"delta": {"reasoning_content": "hmmm"}}]})
                time.sleep(cfg.get("delay", 0.0))
            for i in range(cfg["visible"]):
                send({"choices": [{"delta": {"content": "abcd"}}]})  # 4 chars = 1 token
                if i < cfg["visible"] - 1:
                    time.sleep(cfg.get("delay", 0.0))
            send({"choices": [{"delta": {}, "finish_reason": "stop"}]})
            if cfg.get("usage", True) and body.get("stream_options"):
                send({"choices": [], "usage": {"completion_tokens": cfg["visible"] + cfg.get("hidden", 0)}})
            self.wfile.write(b"data: [DONE]\n\n")
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


@pytest.fixture()
def stub(monkeypatch):
    monkeypatch.setenv("BTSWEB_ALLOW_PRIVATE_URLS", "1")  # the stub lives on 127.0.0.1
    forge._probe_cache.clear()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    srv.daemon_threads = True
    srv.requests = []
    srv.cfg = {"visible": 40, "delay": 0.0, "ttft": 0.0, "hidden": 0}
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    srv.base_url = f"http://127.0.0.1:{srv.server_address[1]}/v1"
    yield srv
    srv.shutdown()
    srv.server_close()
    forge._probe_cache.clear()


def test_projection_brackets_the_analytic_value(stub):
    # 50 visible tokens at 0.03 s apart, 200 hidden tokens reported only in usage, 0.3 s to the first token.
    stub.cfg.update(visible=50, delay=0.03, ttft=0.3, hidden=200)
    out = forge.probe_model(stub.base_url, KEY, "deep-thinker")
    stream_s = 49 * 0.03
    completion = 50 + 200
    speed, mult = completion / stream_s, completion / 50
    analytic = forge.PROBE_CALLS * 0.3 + forge.PROBE_VISIBLE * mult / speed
    assert out["timed_out"] is False
    assert out["lo_s"] <= analytic <= out["hi_s"], (out, analytic)
    assert out["multiplier"] == pytest.approx(5.0, abs=0.05)
    assert out["reasoning"] is True
    assert out["lo_s"] == round(out["projected_s"] * 0.7) and out["hi_s"] == round(out["projected_s"] * 1.4)
    # the call was forge-shaped and on the user's key
    req = stub.requests[0]
    assert req["auth"] == f"Bearer {KEY}"
    assert req["body"]["model"] == "deep-thinker" and req["body"]["stream"] is True
    assert req["body"].get("max_tokens", req["body"].get("max_completion_tokens")) == forge.PROBE_MAX_TOKENS


def test_plain_model_is_not_reasoning(stub):
    stub.cfg.update(visible=60, delay=0.01, hidden=0)
    out = forge.probe_model(stub.base_url, KEY, "plain")
    assert out["multiplier"] == 1.0 and out["reasoning"] is False


def test_streamed_reasoning_counts_without_a_usage_chunk(stub):
    # No usage chunk: the streamed reasoning text is what shows the multiplier.
    stub.cfg.update(visible=20, reasoning_chunks=60, delay=0.005, usage=False)
    out = forge.probe_model(stub.base_url, KEY, "shows-its-work")
    assert out["multiplier"] == pytest.approx(4.0, abs=0.05)
    assert out["reasoning"] is True


def test_timeout_is_a_verdict(stub, monkeypatch):
    monkeypatch.setattr(forge, "PROBE_TIMEOUT_S", 0.5)
    stub.cfg.update(ttft=3.0)
    t0 = time.monotonic()
    out = forge.probe_model(stub.base_url, KEY, "glacial")
    assert time.monotonic() - t0 < 2.0
    assert out == {"timed_out": True, "projected_s": None}


def test_cache_hit_does_not_recall_and_never_holds_the_key(stub, caplog):
    caplog.set_level(logging.DEBUG)
    a = forge.probe_model(stub.base_url, KEY, "cached")
    b = forge.probe_model(stub.base_url, "sk-another-key", "cached")  # keyed by (host, model), not the key
    assert a == b
    assert len(stub.requests) == 1
    assert list(forge._probe_cache) == [("127.0.0.1", "cached")]
    assert KEY not in repr(forge._probe_cache)
    assert KEY not in caplog.text and "sk-another-key" not in caplog.text
    forge.probe_model(stub.base_url, KEY, "other-model")
    assert len(stub.requests) == 2


def test_http_error_is_a_probe_failure(stub):
    stub.cfg.update(status=401)
    with pytest.raises(forge.ForgeError) as e:
        forge.probe_model(stub.base_url, KEY, "denied")
    assert str(e.value).startswith("Couldn't measure this model: endpoint returned HTTP 401")
    assert "nope" not in str(e.value)  # never reflect the provider body
    assert not forge._probe_cache


def test_endpoint(client, stub, caplog):
    caplog.set_level(logging.DEBUG)
    assert client.post("/api/model-probe", json={}, headers=H).status_code in (302, 401)  # login required
    login(client)
    stub.cfg.update(visible=40, delay=0.005)
    r = client.post("/api/model-probe", json={"base_url": stub.base_url, "api_key": KEY, "model": "m"}, headers=H)
    assert r.status_code == 200
    d = r.get_json()
    assert set(d) >= {"tps", "multiplier", "first_token_s", "projected_s", "lo_s", "hi_s", "reasoning", "timed_out"}
    assert KEY not in r.get_data(as_text=True) and KEY not in caplog.text

    r = client.post("/api/model-probe", json={"base_url": stub.base_url, "api_key": KEY}, headers=H)
    assert r.status_code == 400
    assert r.get_json()["code"] == "probe.failed"

    stub.cfg.update(status=500)
    r = client.post("/api/model-probe", json={"base_url": stub.base_url, "api_key": KEY, "model": "x"},
                    headers=H)
    assert r.status_code == 400
    assert r.get_json()["code"] == "probe.failed"
    assert r.get_json()["vars"]["detail"].startswith("endpoint returned HTTP 500")
