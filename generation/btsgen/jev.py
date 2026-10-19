"""The shared Jev client (docs/plans/JEV_EVALUATION_PLAN.md, sections 1 + 3b, Phase 2).

Jev is TypeSafe's typed-decision model, reached through OpenRouter's Decisions API on OPENROUTER_API_KEY:
`POST https://openrouter.ai/api/alpha/decisions`, body `{model, state, questions}`. Every question is answered
INDEPENDENTLY against the same state, so batching questions into one request is free; any cross-question
constraint is the caller's job.

Two layers:
  * the raw transport (`post`, `request` with one backoff on 429/529, `key`, `report_usage`) - the card-stage
    vocab gate (gate.py, Phases 1a/1b) uses these directly and books its usage as role "gate";
  * the Phase 2 QUALITY SLOTS (`ask` / `choice` / `choices` / `nouls`), each switched on by name in
    $BTS_JEV_SLOTS ("" / unset / "off" = none, "all" = every slot, else a comma list of SLOTS). A slot call never
    raises: disabled, no key, HTTP error, bad shape all return None and the caller keeps today's behaviour.
    Usage is booked as role "jev:<slot>".

Choice answers (docs.typesafe.ai/api, read 2026-10-18): a question
    {"type": "choice", "instructions": "...", "criteria": {"opt": "description", ...}}
answers as
    {"type": "choice", "choice": "opt", "probabilities": {"opt": 0.88, ...}, "confidence": 0.81}
The parser also accepts a bare {opt: prob} map (see _parse_choice).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict

_log = logging.getLogger("btsgen.jev")

JEV_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
JEV_MODEL = "typesafe/jev-1.13"
JEV_TIMEOUT_S = 15
MAX_OPTIONS = 255          # Jev's documented cap on choice options (the none option included)

SLOTS_ENV = "BTS_JEV_SLOTS"
SLOTS = ("nominate", "relic", "vocab", "qa", "stub")


# ------------------------------------------------------------------------------------------------ transport
def post(key: str, state, questions: dict) -> dict:
    body = json.dumps({"model": JEV_MODEL, "state": state, "questions": questions}).encode()
    req = urllib.request.Request(JEV_ENDPOINT, data=body, method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=JEV_TIMEOUT_S) as r:
        return json.load(r)


def request(key: str, state, questions: dict) -> dict:
    """One Decisions request with a single short backoff on 429/529. Raises on anything else."""
    try:
        return post(key, state, questions)
    except urllib.error.HTTPError as e:
        if e.code not in (429, 529):
            raise
        time.sleep(1.5)
        return post(key, state, questions)


def key() -> str:
    from .generator import load_env
    load_env()
    return (os.environ.get("OPENROUTER_API_KEY") or "").strip()


def report_usage(on_usage, resp: dict, role: str = "gate") -> float:
    """Book one response's usage on `on_usage` (never raises) and return its cost in USD (0.0 if unknown)."""
    u = resp.get("usage") or {}
    cost = u.get("cost")
    try:
        cost_f = float(cost) if cost is not None and not isinstance(cost, bool) else 0.0
    except (TypeError, ValueError):
        cost_f = 0.0
    if on_usage is not None:
        try:
            # the stable slug, not resp["model"] (a dated build id), so the ledger keeps ONE row per role
            on_usage({"_role": role, "_model": JEV_MODEL,
                      "input_tokens": int(u.get("input_tokens", 0) or 0), "output_tokens": 0,
                      **({"cost": cost} if cost is not None else {})})
        except Exception:  # noqa: BLE001 — a telemetry sink must never break a forge
            pass
    return cost_f


# ------------------------------------------------------------------------------------------------ slots
def slots_enabled() -> frozenset:
    """The quality slots switched on by $BTS_JEV_SLOTS (read at call time, .env included). Unknown names are
    ignored, so a typo means "off", never a surprise call."""
    try:
        from .generator import load_env
        load_env()
    except Exception:  # noqa: BLE001
        pass
    raw = (os.environ.get(SLOTS_ENV) or "").strip().lower()
    if not raw or raw == "off":
        return frozenset()
    if raw == "all":
        return frozenset(SLOTS)
    return frozenset(s.strip() for s in raw.split(",") if s.strip() in SLOTS)


def enabled(slot: str) -> bool:
    return slot in slots_enabled()


_memo: "OrderedDict[str, dict]" = OrderedDict()
_memo_lock = threading.Lock()
_MEMO_MAX = 512


def clear_memo() -> None:
    with _memo_lock:
        _memo.clear()


def _warn(slot: str, msg: str) -> None:
    _log.warning(f"jev[{slot}]: {msg}"[:200])


def ask(slot: str, state, questions: dict, *, on_usage=None) -> dict | None:
    """The `answers` map for one request, or None when the slot is off, the key is missing, or ANYTHING goes
    wrong (logged). Never raises. Identical asks in one process are memoized (and not re-billed)."""
    try:
        if not enabled(slot) or not questions:
            return None
        mkey = slot + "\0" + json.dumps({"state": state, "questions": questions}, sort_keys=True, default=str)
        with _memo_lock:
            hit = _memo.get(mkey)
            if hit is not None:
                _memo.move_to_end(mkey)
                return hit
        k = key()
        if not k:
            _warn(slot, "OPENROUTER_API_KEY is not set; slot skipped")
            return None
        resp = request(k, state, questions)
        if not isinstance(resp, dict):
            raise RuntimeError(f"non-object response: {str(resp)[:120]}")
        report_usage(on_usage, resp, role=f"jev:{slot}")
        ans = resp.get("answers")
        if not isinstance(ans, dict):
            raise RuntimeError(f"no answers map: {str(resp)[:120]}")
        with _memo_lock:
            _memo[mkey] = ans
            _memo.move_to_end(mkey)
            while len(_memo) > _MEMO_MAX:
                _memo.popitem(last=False)
        return ans
    except Exception as e:  # noqa: BLE001 — a quality slot must never break a forge
        _warn(slot, f"{type(e).__name__}: {e}")
        return None


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _parse_choice(a, options) -> tuple[str, float] | None:
    """(best option, its probability) from one choice answer, or None if the shape is unusable.

    Documented shape (docs.typesafe.ai/api): {"type": "choice", "choice": opt, "probabilities": {opt: p},
    "confidence": c}. Also accepted: a bare {opt: p} map.
    TODO(live probe, tools/jev_slots_probe.py): confirm OpenRouter's /alpha/decisions returns the documented
    shape for `choice` (only `noul` is verified live so far), and whether `confidence` or probabilities[choice]
    is the better gate number. This uses probabilities[choice] when present, else `confidence`."""
    if not isinstance(a, dict):
        return None
    opts = set(options)
    probs = a.get("probabilities")
    if not isinstance(probs, dict):
        probs = {k: v for k, v in a.items() if k in opts}
    best = a.get("choice") if isinstance(a.get("choice"), str) else None
    clean = {str(k): p for k, v in probs.items() if (p := _num(v)) is not None and str(k) in opts}
    if clean:
        if best not in clean:
            best = max(clean, key=lambda k: clean[k])
        return best, clean[best]
    if best in opts:
        c = _num(a.get("confidence"))
        if c is not None:
            return best, c
    return None


def _choice_q(options, instructions: str, none_label: str | None) -> dict | None:
    crit = ({str(k): str(v) for k, v in options.items()} if isinstance(options, dict)
            else {str(o): str(o).replace("_", " ") for o in options})
    if none_label:
        crit[none_label] = "nothing listed here matches"
    if len(crit) < 2 or len(crit) > MAX_OPTIONS:
        return None
    return {"type": "choice", "instructions": instructions, "criteria": crit}


def choices(slot: str, state, asks: dict, *, on_usage=None,
            none_label: str | None = "none_of_these") -> dict | None:
    """Several choice questions in ONE request: {qname: (options, instructions)} -> {qname: (best, prob)}.
    `options` is a list of ids or an {id: description} dict; `none_label` (None = no escape option) is appended
    to every question. A question that can't be asked (too many options) or answers in an unusable shape is
    left out of the result; None = the request did not happen or failed."""
    if not enabled(slot):
        return None
    qs: dict = {}
    for name, (opts, instr) in (asks or {}).items():
        q = _choice_q(opts, instr, none_label)
        if q is None:
            _warn(slot, f"question {name} skipped ({len(opts)} options)")
            continue
        qs[str(name)] = q
    if not qs:
        return None
    ans = ask(slot, state, qs, on_usage=on_usage)
    if ans is None:
        return None
    out: dict = {}
    for name, q in qs.items():
        got = _parse_choice(ans.get(name), list(q["criteria"]))
        if got is not None:
            out[name] = got
    return out


def choice(slot: str, state, options, instructions: str, *, on_usage=None,
           none_label: str | None = "none_of_these") -> tuple[str, float] | None:
    """One choice question over `options` + [none_label]: (best option, its probability) or None."""
    got = choices(slot, state, {"q": (options, instructions)}, on_usage=on_usage, none_label=none_label)
    return (got or {}).get("q")


def nouls(slot: str, state, asks: dict, *, on_usage=None) -> dict | None:
    """Yes/no questions in one request: {name: instructions} -> {name: P(yes)}; None on any failure."""
    qs = {str(n): {"type": "noul", "instructions": str(i)} for n, i in (asks or {}).items()}
    ans = ask(slot, state, qs, on_usage=on_usage)
    if ans is None:
        return None
    out: dict = {}
    for n in qs:
        v = parse_noul(ans.get(n))
        if v is not None:
            out[n] = v
    return out


def parse_noul(a) -> float | None:
    """P(yes) from one noul answer (live-verified shape {"noul": p}; a bare number is accepted too)."""
    return _num(a.get("noul")) if isinstance(a, dict) else _num(a)


def score_q(instructions: str, levels) -> dict:
    """A `score` question: `levels` is the ORDERED list of level descriptions, lowest first (2-10 of them)."""
    return {"type": "score", "instructions": str(instructions), "criteria": [str(x) for x in levels]}


def parse_score(a, n_levels: int) -> tuple[float, int] | None:
    """(expected level, most likely level) from one score answer, both 1-BASED (level 1 = the first criterion),
    or None if the shape is unusable.

    Documented shape (docs.typesafe.ai/api, read 2026-10-18): {"type": "score", "score": 1.05 (probability-
    weighted, 0-based level index), "legend": {"0": desc, ...}, "probabilities": {"0": p, ...}, "confidence": c}.
    Also accepted: a bare probability map over the level indices.
    TODO(live probe, tools/jev_slots_probe.py [qa]): confirm OpenRouter's /alpha/decisions returns `score` as a
    0-BASED weighted index (so 1-based = score + 1) and `probabilities` keyed by "0".."n-1"; if it is 1-based,
    drop the +1 here."""
    if isinstance(a, dict):
        probs = a.get("probabilities") if isinstance(a.get("probabilities"), dict) else             {k: v for k, v in a.items() if str(k).isdigit()}
    else:
        return None
    clean: dict[int, float] = {}
    for k, v in (probs or {}).items():
        p = _num(v)
        try:
            i = int(k)
        except (TypeError, ValueError):
            continue
        if p is not None and 0 <= i < n_levels:
            clean[i] = p
    top = max(clean, key=lambda i: clean[i]) if clean else None
    sc = _num(a.get("score"))
    if sc is not None and 0 <= sc <= n_levels - 1:
        expected = sc + 1
    elif clean and sum(clean.values()) > 0:
        expected = sum((i + 1) * p for i, p in clean.items()) / sum(clean.values())
    else:
        return None
    return round(expected, 2), (top + 1 if top is not None else int(round(expected)))
