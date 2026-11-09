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


def test_project_from_timing_formula():
    # The plan's worked examples (WALK_AWAY_FORGE_PLAN.md 0.1): 43 calls x 2 s first token + 25K visible x M / S.
    # Doubao-like: 1000 visible tokens (4000 chars) but 4600 completion tokens (M = 4.6) streamed at 45 tok/s.
    doubao = forge.project_from_timing({"first_token_s": 2.0, "stream_s": 4600 / 45, "content_chars": 4000,
                                        "reasoning_chars": 0, "completion_tokens": 4600})
    expect = forge.PROBE_CALLS * 2.0 + forge.PROBE_VISIBLE * 4.6 / 45
    assert doubao["projected_s"] == round(expect) and 43 <= expect / 60 <= 45  # ≈ 44 min
    assert doubao["multiplier"] == 4.6 and doubao["tps"] == 45 and doubao["reasoning"] is True
    assert doubao["lo_s"] == round(expect * forge.PROBE_LO) and doubao["hi_s"] == round(expect * forge.PROBE_HI)
    # OpenAI-like: same speed and latency, nothing hidden (M = 1).
    plain = forge.project_from_timing({"first_token_s": 2.0, "stream_s": 1000 / 45, "content_chars": 4000,
                                       "reasoning_chars": 0, "completion_tokens": 1000})
    expect = forge.PROBE_CALLS * 2.0 + forge.PROBE_VISIBLE * 1.0 / 45
    assert plain["projected_s"] == round(expect) and 10.5 <= expect / 60 <= 11.5  # ≈ 11 min
    assert plain["multiplier"] == 1.0 and plain["reasoning"] is False and plain["timed_out"] is False
    # No usage chunk: the streamed reasoning text stands in for the hidden tokens.
    shown = forge.project_from_timing({"first_token_s": 2.0, "stream_s": 4600 / 45, "content_chars": 4000,
                                       "reasoning_chars": 14400, "completion_tokens": None})
    assert shown["multiplier"] == 4.6 and shown["projected_s"] == doubao["projected_s"]


def test_projection_brackets_the_analytic_value(stub, monkeypatch):
    # 50 visible tokens at 0.03 s apart, 200 hidden tokens reported only in usage, 0.3 s to the first token.
    stub.cfg.update(visible=50, delay=0.03, ttft=0.3, hidden=200)
    seen: list[dict] = []
    real = forge.project_from_timing
    monkeypatch.setattr(forge, "project_from_timing", lambda t: seen.append(dict(t)) or real(t))
    out = forge.probe_model(stub.base_url, KEY, "deep-thinker")
    assert out["timed_out"] is False
    # Exact: the result IS the formula applied to the probe's own recorded timing (formula itself is pinned by
    # test_project_from_timing_formula), and the count-based facts don't depend on the clock.
    assert len(seen) == 1 and out == real(seen[0])
    assert seen[0]["completion_tokens"] == 250 and seen[0]["content_chars"] == 200
    assert out["multiplier"] == pytest.approx(5.0, abs=0.05)
    assert out["reasoning"] is True
    # lo/hi come from the UNROUNDED seconds (e.g. 771.4 s -> hi 1080, but round(771 * 1.4) = 1079): within 1.
    assert abs(out["lo_s"] - out["projected_s"] * 0.7) <= 1 and abs(out["hi_s"] - out["projected_s"] * 1.4) <= 1
    # Loose: the timing-based projection against the stub's NOMINAL pace. Sleep-based streaming runs slower
    # than 0.03 s/token on a loaded Windows box (full suite), which lowers the measured tok/s and inflates the
    # projection, so only a factor-of-3 sanity bound is asserted here — not the 0.7x-1.4x range.
    stream_s = 49 * 0.03
    completion = 50 + 200
    speed, mult = completion / stream_s, completion / 50
    analytic = forge.PROBE_CALLS * 0.3 + forge.PROBE_VISIBLE * mult / speed
    assert analytic / 3 <= out["projected_s"] <= analytic * 3, (out, analytic)
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
