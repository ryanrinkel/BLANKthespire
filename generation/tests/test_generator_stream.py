"""Offline tests for OpenAICompatGenerator's streamed transport — no API key, no network.

Run:  uv run python -m tests.test_generator_stream     (from generation/)
Exits nonzero on any failure. Covers: SSE chunk reassembly (+ usage chunk -> on_usage), the plain-JSON
fallback when an endpoint ignores `stream`, the one-retry-on-transient-failure policy (read timeout /
dropped connection), the friendly translation of a double timeout, the max_tokens -> max_completion_tokens
400 swap surviving the restructure, and dropping `stream_options` for endpoints that reject it.
"""
from __future__ import annotations

import io
import json
import sys
import urllib.error
import urllib.request

from btsgen.generator import OpenAICompatGenerator

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


class _Contract:
    def system_prompt(self) -> str:
        return "SYS"

    def user_brief(self, brief) -> str:
        return f"BRIEF:{brief}"

    def repair_message(self, prev_text, errors) -> str:
        return "REPAIR"


class _FakeResp:
    """Duck-typed urlopen response: headers.get, iteration (SSE), read (JSON fallback), context manager."""

    def __init__(self, lines: list[bytes], ctype: str = "text/event-stream") -> None:
        self._lines = lines
        self.headers = {"Content-Type": ctype}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter(self._lines)

    def read(self) -> bytes:
        return b"".join(self._lines)


def _sse(events: list[dict | str]) -> list[bytes]:
    out = []
    for e in events:
        data = e if isinstance(e, str) else json.dumps(e)
        out.append(f"data: {data}\n".encode())
        out.append(b"\n")
    return out


def _gen(on_usage=None, timeout: int = 7) -> OpenAICompatGenerator:
    OpenAICompatGenerator._completion_token_models.clear()
    OpenAICompatGenerator._no_stream_options_models.clear()
    return OpenAICompatGenerator("https://fake.test/v1", "sk-x", "m1", contract_mod=_Contract(),
                                 max_tokens=100, timeout=timeout, on_usage=on_usage)


def _with_urlopen(fn, run):
    """Run `run()` with urllib.request.urlopen swapped for `fn`; always restore."""
    real = urllib.request.urlopen
    urllib.request.urlopen = fn
    try:
        return run()
    finally:
        urllib.request.urlopen = real


def _http_error(code: int, body: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://fake.test/v1/chat/completions", code, "Bad Request",
                                  {}, io.BytesIO(body.encode()))


def test_sse_reassembly_and_usage() -> None:
    print("sse reassembly + usage chunk...")
    seen_usage: list[dict] = []
    captured: list[dict] = []

    def fake(req, timeout=None):
        captured.append(json.loads(req.data.decode()))
        return _FakeResp(_sse([
            {"choices": [{"delta": {"role": "assistant", "content": ""}}]},
            {"choices": [{"delta": {"content": '{"a"'}}]},
            "not-json keep-alive",  # must be ignored, not fatal
            {"choices": [{"delta": {"content": ": 1}"}}]},
            {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 4}},
            "[DONE]",
        ]))

    gen = _gen(on_usage=seen_usage.append)
    text, messages = _with_urlopen(fake, lambda: gen.first_attempt("x"))
    check(text == '{"a": 1}', f"streamed chunks must reassemble in order (got {text!r})")
    check(seen_usage == [{"prompt_tokens": 10, "completion_tokens": 4}], "usage chunk must reach on_usage")
    check(captured[0].get("stream") is True, "request must ask for a stream")
    check(captured[0].get("stream_options") == {"include_usage": True},
          "usage opt-in must be sent when on_usage is set")
    check(messages[-1] == {"role": "assistant", "content": text}, "history must carry the assembled text")

    # Without on_usage there must be no OpenAI-only stream_options in the request.
    captured.clear()
    gen2 = _gen(on_usage=None)
    _with_urlopen(fake, lambda: gen2.first_attempt("x"))
    check("stream_options" not in captured[0], "no on_usage -> no stream_options in the payload")


def test_plain_json_fallback() -> None:
    print("plain-JSON fallback (endpoint ignored `stream`)...")
    body = json.dumps({"choices": [{"message": {"content": "hello"}}],
                       "usage": {"prompt_tokens": 1}}).encode()

    def fake(req, timeout=None):
        return _FakeResp([body], ctype="application/json")

    text, _ = _with_urlopen(fake, lambda: _gen().first_attempt("x"))
    check(text == "hello", f"a buffered JSON body must parse as-is (got {text!r})")


def test_transient_retry() -> None:
    print("one retry on a transient transport failure...")
    calls = {"n": 0}
    ok = _FakeResp(_sse([{"choices": [{"delta": {"content": "recovered"}}]}, "[DONE]"]))

    def flaky(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("The read operation timed out")
        return ok

    text, _ = _with_urlopen(flaky, lambda: _gen().first_attempt("x"))
    check(text == "recovered" and calls["n"] == 2, "a single read timeout must retry once and succeed")

    def always_times_out(req, timeout=None):
        raise TimeoutError("The read operation timed out")

    try:
        _with_urlopen(always_times_out, lambda: _gen(timeout=7).first_attempt("x"))
        check(False, "a double timeout must raise")
    except RuntimeError as e:
        check("7s" in str(e) and "tried twice" in str(e),
              f"double timeout must translate to an actionable message (got {e})")

    def unreachable(req, timeout=None):
        raise urllib.error.URLError("nope")

    try:
        _with_urlopen(unreachable, lambda: _gen().first_attempt("x"))
        check(False, "a double URLError must raise")
    except RuntimeError as e:
        check("could not reach endpoint" in str(e), f"URLError must keep its friendly message (got {e})")


def test_max_completion_tokens_swap() -> None:
    print("max_tokens -> max_completion_tokens 400 swap...")
    captured: list[dict] = []

    def fake(req, timeout=None):
        payload = json.loads(req.data.decode())
        captured.append(payload)
        if "max_tokens" in payload:
            raise _http_error(400, "Use 'max_completion_tokens' instead of 'max_tokens'.")
        return _FakeResp(_sse([{"choices": [{"delta": {"content": "ok"}}]}, "[DONE]"]))

    text, _ = _with_urlopen(fake, lambda: _gen().first_attempt("x"))
    check(text == "ok", "the swapped retry must succeed")
    check(captured[-1].get("max_completion_tokens") == 100 and "max_tokens" not in captured[-1],
          "retry must carry the newer parameter name only")
    check("m1" in OpenAICompatGenerator._completion_token_models, "the swap must be remembered per-model")

    # HTTP status errors must NOT get the transient retry: exactly one call per attempt.
    calls = {"n": 0}

    def hard_400(req, timeout=None):
        calls["n"] += 1
        raise _http_error(400, "some other validation error")

    try:
        _with_urlopen(hard_400, lambda: _gen().first_attempt("x"))
        check(False, "an unrecognized 400 must raise")
    except RuntimeError as e:
        check("HTTP 400" in str(e), f"unrecognized 400 must surface code+detail (got {e})")
    check(calls["n"] == 1, f"an unrecognized 400 must not be retried (got {calls['n']} calls)")


def test_stream_options_dropped_on_400() -> None:
    print("stream_options dropped for endpoints that reject it...")
    captured: list[dict] = []

    def fake(req, timeout=None):
        payload = json.loads(req.data.decode())
        captured.append(payload)
        if "stream_options" in payload:
            raise _http_error(400, "Unknown parameter: 'stream_options'.")
        return _FakeResp(_sse([{"choices": [{"delta": {"content": "ok"}}]}, "[DONE]"]))

    gen = _gen(on_usage=lambda u: None)
    text, _ = _with_urlopen(fake, lambda: gen.first_attempt("x"))
    check(text == "ok", "the retry without stream_options must succeed")
    check("stream_options" not in captured[-1], "retry must drop stream_options")
    check("m1" in OpenAICompatGenerator._no_stream_options_models, "the rejection must be remembered per-model")
    # A later call on the same model must not probe again.
    captured.clear()
    gen2 = OpenAICompatGenerator("https://fake.test/v1", "sk-x", "m1", contract_mod=_Contract(),
                                 max_tokens=100, on_usage=lambda u: None)
    _with_urlopen(fake, lambda: gen2.first_attempt("x"))
    check(len(captured) == 1 and "stream_options" not in captured[0],
          "a remembered model must skip stream_options on the first try")


def main() -> int:
    test_sse_reassembly_and_usage()
    test_plain_json_fallback()
    test_transient_retry()
    test_max_completion_tokens_swap()
    test_stream_options_dropped_on_400()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
