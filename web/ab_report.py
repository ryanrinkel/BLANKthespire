"""The per-experiment read-out shared by the admin Experiments card, the Monday digest and the
planned-end / winner mail (docs/plans/AB_TESTING_PLAN.md 3.5, 3.10 items 2-4).

``build_experiments_payload(traffic_data, today)`` merges the registry (``experiments.EXPERIMENTS``, the
truth: a deploy that adds an experiment lists it at once, "no exposures yet") with the per-arm numbers
``tools/traffic_report.py`` writes to ``traffic.json["experiments"]`` (absent on an old file, or before the
first timer tick). The decision is re-applied here with today's date, so the status line never lags the
15-minute timer by a day.

Imports only ``experiments`` and the standard library, so app.py's route, alerts.py and the mail CLI all
share it without importing app.py.
"""
from __future__ import annotations

import experiments as _exp

KEEP_ENDED_DAYS = 30   # the card keeps an ended experiment this long, then the LOG is the archive (plan 3.7)

# What each primary metric means, in the words the card and the mail print.
PRIMARY_LABELS = {
    "clicked": "clicked past the splash",
    "login": "/login opened",
    "provider": "picked a sign-in provider",
    "signed_in": "signed in",
    "workshop": "Workshop link opened",
    "deck": "a deck page opened",
    "archive": "/archive opened",
    "download": "/download opened",
}

# The registry fields copied onto every entry (the card and the mail print them in words first).
_REG_FIELDS = ("name", "page", "started", "planned_end", "ended", "winner", "primary", "hypothesis")
# What the traffic summary contributes when it has the experiment.
_TRAFFIC_FIELDS = ("daily", "exposure_rate_7d", "control_rate", "days_to_decision", "sample_size_per_arm")


def rule() -> dict:
    return {"p_threshold": _exp.P_THRESHOLD, "min_exposures": _exp.MIN_EXPOSURES, "min_days": _exp.MIN_DAYS}


def rule_sentence() -> str:
    """The decision rule, printed once under the card and in every mail so it is not re-litigated."""
    return (f"Decision rule: call a winner when P(beats control) >= {_exp.P_THRESHOLD} AND every arm has at "
            f"least {_exp.MIN_EXPOSURES} exposures AND the experiment has run at least {_exp.MIN_DAYS} days; "
            "otherwise, at the planned end, keep the control. Secondary metrics are for understanding, not "
            "for deciding. Peeking is fine; the minimum n and days are what stop a lucky first week.")


def _shown(exp, today: str) -> bool:
    """Live today, not started yet (so a fresh deploy is visible), or ended within KEEP_ENDED_DAYS."""
    if exp.ended is None or today < exp.ended:
        return True
    return 0 <= _exp._days_between(exp.ended, today) <= KEEP_ENDED_DAYS


def status_kind(status: str) -> str:
    """A class for the card's status pill: running / due / winner / ended / pending."""
    s = status or ""
    if s.startswith("ended"):
        return "ended"
    if s.startswith("winner"):
        return "winner"
    if s.startswith("decision due"):
        return "due"
    if s.startswith("not started"):
        return "pending"
    return "running"


def _fmt_p(p) -> str:
    return "—" if p is None else f"{p:.2f}"


def p_phrase(entry: dict, sep: str = "=") -> str:
    """'P(b beats a)=0.81' (one per non-control arm, comma-joined)."""
    ps = (entry.get("decision") or {}).get("p_beats_control") or {}
    arms = entry.get("arms") or []
    return ", ".join(f"P({a} beats {arms[0]}){sep}{_fmt_p(ps.get(a))}" for a in arms[1:]) if arms else ""


def _span(days: float) -> str:
    if days < 14:
        return f"~{max(1, round(days))} days"
    return f"~{round(days / 7)} weeks"


def readout(entry: dict) -> str:
    """The sentence under the table: the P read, whether the rule is met, and the time to a decision."""
    per_arm = entry.get("per_arm") or {}
    if not any(int((r or {}).get("exposures") or 0) for r in per_arm.values()):
        return "No exposures yet — the traffic timer refreshes every 15 min."
    d = entry.get("decision") or {}
    label = entry.get("primary_label") or entry.get("primary") or "?"
    parts = [f"{p_phrase(entry, ': ')} on {label}"]
    ended = entry.get("status_kind") == "ended"
    if ended:
        verdict = f"ended {entry['ended']}, winner {entry.get('winner')}."
    elif d.get("winner_by_rule"):
        verdict = f"winner by the rule: {d['winner_by_rule']}."
    elif entry.get("status_kind") == "due":
        verdict = (f"the rule was not met by the planned end (needs ≥{_exp.P_THRESHOLD}, ≥{_exp.MIN_EXPOSURES} "
                   f"exposures per arm, ≥{_exp.MIN_DAYS} days), so the rule says keep the control.")
    else:
        verdict = (f"not yet (needs ≥{_exp.P_THRESHOLD}, ≥{_exp.MIN_EXPOSURES} exposures per arm, "
                   f"≥{_exp.MIN_DAYS} days).")
    text = parts[0] + " — " + verdict
    if ended:
        return text
    cr = entry.get("control_rate")
    rate = float(entry.get("exposure_rate_7d") or 0)
    arms = entry.get("arms") or []
    if not cr:
        return text + f" No {label} in the control yet, so no time-to-decision."
    if rate <= 0:
        return text + " No exposures in the last 7 days, so no time-to-decision."
    weekly = rate * 7 * max(1, len(arms))
    text += f" At ~{round(weekly)} exposures/week ({rate * 7:.0f} per arm)"
    dtd = entry.get("days_to_decision")
    if dtd:
        text += f", a +50% lift over the control's {cr:.1%} would show in {_span(float(dtd))}."
    else:
        text += "."
    return text


def shown_experiments(today: str | None = None, experiments: list | None = None) -> list:
    """The registry experiments the card / mail show today (what ab_accounts.accounts_payload is asked for)."""
    today = today or _exp.today_utc()
    reg = _exp.EXPERIMENTS if experiments is None else experiments
    return [exp for exp in reg if _shown(exp, today)]


ACCOUNTS_UNAVAILABLE = "account attribution lookup failed (database unreadable)"


def build_experiments_payload(traffic_data: dict | None, today: str | None = None,
                              experiments: list | None = None,
                              accounts: dict | None = None) -> list[dict]:
    """One entry per registry experiment shown on the card (live, not started yet, or ended within 30 days).
    ``experiments`` overrides the registry (tests). ``accounts`` is ab_accounts.accounts_payload's
    ``{name: {arm: {accounts, forged, donated, hosted_cost_usd}}}`` (Phase 2, from the database — passed in so
    this module stays DB-free); an experiment missing from it gets ``accounts: None`` + ``accounts_reason``."""
    today = today or _exp.today_utc()
    block = (traffic_data or {}).get("experiments") if isinstance(traffic_data, dict) else None
    block = block if isinstance(block, dict) else {}
    out = []
    for exp in shown_experiments(today, experiments):
        entry = {k: getattr(exp, k) for k in _REG_FIELDS}
        entry.update(arms=list(exp.arms), weights=list(exp.weights), arms_text=dict(exp.arms_text),
                     describe=_exp.describe(exp, today),
                     primary_label=PRIMARY_LABELS.get(exp.primary, exp.primary))
        t = block.get(exp.name)
        t = t if isinstance(t, dict) else {}
        per_arm = t.get("per_arm") if isinstance(t.get("per_arm"), dict) else {}
        entry["per_arm"] = per_arm
        entry["in_traffic"] = bool(t)
        for k in _TRAFFIC_FIELDS:
            entry[k] = t.get(k)
        if entry["daily"] is None:
            entry["daily"] = []
        # Re-applied with today's date and the registry's ended/winner (the summary may be a tick old).
        entry["decision"] = _exp.decide(exp, {a: {"exposures": (r or {}).get("exposures"),
                                                  "primary": (r or {}).get("primary")}
                                              for a, r in per_arm.items()}, today)
        entry["status_kind"] = status_kind(entry["decision"]["status"])
        entry["live"] = _exp.is_live(exp, today)
        # 1-based "day N": the start day is day 1; an ended run stops counting on `ended` (exclusive).
        if exp.ended is not None and exp.ended <= today:
            entry["day"] = max(0, _exp._days_between(exp.started, exp.ended))
        elif today >= exp.started:
            entry["day"] = _exp._days_between(exp.started, today) + 1
        else:
            entry["day"] = 0
        entry["of"] = _exp._days_between(exp.started, exp.planned_end)
        entry["preview"] = {a: f"{exp.page}?ab={exp.name}:{a}" for a in exp.arms}
        # Phase 2 (users.signup_ab): new accounts / first forge / donated per arm, from the database.
        acc = (accounts or {}).get(exp.name) if isinstance(accounts, dict) else None
        if isinstance(acc, dict) and acc:
            entry["accounts"] = {a: dict(acc.get(a) or {"accounts": 0, "forged": 0, "donated": 0,
                                                       "hosted_cost_usd": 0.0}) for a in exp.arms}
        else:
            entry["accounts"] = None
            if accounts is not None:   # asked for and missing = the lookup failed (None = not asked)
                entry["accounts_reason"] = ACCOUNTS_UNAVAILABLE
        entry["readout"] = readout(entry)
        out.append(entry)
    return out
