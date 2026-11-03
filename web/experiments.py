"""Page experiments (A/B tests): the one registry plus the pure functions every consumer shares.

No cookie, no storage, no beacon. A visitor's arm is never stored anywhere: it is
``sha256(ip|ua|name|salt)`` folded onto the experiment's weights, computed from what the request already
carries and nginx already logs. ``app.py`` calls :func:`arm_for` at serve time to pick which
``<!--ab name:arm-->`` blocks of a page survive, and ``tools/traffic_report.py`` imports this same module
(under the droplet's plain ``/usr/bin/python3``, outside the app venv — so this file imports ONLY the
standard library) and recomputes the arm per visitor from the access log. Because both sides run the same
function, there is nothing to record and nothing to migrate. Consequence: changing an experiment's arms or
weights changes who sees what, so it needs a NEW salt (or a new name) — old exposures are not comparable
and must not be mixed.

Lifecycle (docs/plans/AB_TESTING_PLAN.md 3.7):

1. Write the row in ``docs/experiments/LOG.md`` first (name, page, arms, primary metric, start, planned
   end) — the registry entry carries the same hypothesis text so the card and the log never disagree.
2. Deploy the registry entry + the HTML markers. Preview each arm with ``/?ab=name:x``.
3. Let it run. Never touch the arms mid-flight: a copy tweak is a new experiment with a new salt.
4. End it by setting ``ended`` + ``winner`` here and deploying: everyone gets the winner at once
   (:func:`served_arms`). In the same or the next commit remove the markers, the losing arm and its
   i18n keys from the HTML / copy docs, and fill in the LOG row.

Decision rule (plan 3.5), applied by :func:`decide`: call a winner when ``P(arm beats control) >=
P_THRESHOLD`` AND every arm has at least ``MIN_EXPOSURES`` exposures AND the experiment has run at least
``MIN_DAYS`` days; otherwise, at ``planned_end``, keep the control. Secondary metrics are for understanding,
not for deciding.

Importing this module never raises; :func:`validate` is an explicit call (app.py runs it at import so a
bad registry fails the deploy's test step).
"""
from __future__ import annotations

import datetime
import hashlib
import math
import random
import re
from dataclasses import dataclass

MIN_EXPOSURES = 200     # per arm, decision rule (plan 3.5)
MIN_DAYS = 14
P_THRESHOLD = 0.95
NAME_RE = re.compile(r"^[a-z0-9_]+$")   # experiment names AND arm names
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

PRIMARY_METRICS = ("clicked", "login", "provider", "signed_in", "workshop", "deck", "archive", "download")

MAX_OVERRIDE_ITEMS = 20

Z_ALPHA_2 = 1.959964   # two-sided 0.05
Z_POWER = 0.841621     # power 0.80


@dataclass(frozen=True)
class Experiment:
    name: str
    page: str                 # route path, no query: "/", "/login", "/download", "/help", "/archive"
    arms: tuple[str, ...]     # arms[0] must be "a" = control = today's page
    weights: tuple[int, ...]  # same length as arms, sum to 100
    salt: str
    started: str              # "YYYY-MM-DD" UTC; exposures before this day are ignored
    planned_end: str          # REQUIRED "YYYY-MM-DD": the day the decision is due
    primary: str              # the one metric that decides it, one of PRIMARY_METRICS
    hypothesis: str           # REQUIRED non-empty, one sentence
    arms_text: dict[str, str] # REQUIRED: one non-empty line per arm
    ended: str | None = None  # "YYYY-MM-DD"; set together with winner
    winner: str | None = None

    # dict fields make the generated __hash__ fail; experiments are identified by name.
    def __hash__(self) -> int:
        return hash(self.name)


EXPERIMENTS: list[Experiment] = [
    # control is always arm a = today's page
    Experiment(
        name="hero", page="/", arms=("a", "b"), weights=(50, 50),
        salt="2026-11-03", started="2026-11-03", planned_end="2026-12-15",
        primary="login",
        hypothesis=("Saying 'free with your own API key' on the button lifts /login opens, because the cost "
                    "question stops people before the pricing section far below the fold."),
        arms_text={"a": "Button says 'Create Your Own Class' (today's page)",
                   "b": "Button says 'Forge a class — free with your own API key'"},
    ),
]


# ---------------------------------------------------------------------------------------------- dates

def today_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


def _parse_day(s) -> datetime.date | None:
    if not isinstance(s, str) or not DATE_RE.match(s):
        return None
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None


def _reg(experiments):
    return EXPERIMENTS if experiments is None else experiments


# ------------------------------------------------------------------------------------------ validation

def _validate_one(exp: Experiment) -> None:
    n = exp.name
    if not isinstance(n, str) or not NAME_RE.match(n):
        raise ValueError(f"experiment name {n!r} must match [a-z0-9_]+")
    where = f"experiment {n!r}"
    if not isinstance(exp.page, str) or not exp.page.startswith("/"):
        raise ValueError(f"{where}: page {exp.page!r} must start with '/'")
    arms = tuple(exp.arms) if isinstance(exp.arms, (tuple, list)) else ()
    if not arms:
        raise ValueError(f"{where}: arms must be a non-empty tuple")
    if arms[0] != "a":
        raise ValueError(f"{where}: arms[0] must be 'a' (the control = today's page), got {arms[0]!r}")
    seen = set()
    for a in arms:
        if not isinstance(a, str) or not NAME_RE.match(a):
            raise ValueError(f"{where}: arm {a!r} must match [a-z0-9_]+")
        if a in seen:
            raise ValueError(f"{where}: arm {a!r} is listed twice")
        seen.add(a)
    weights = tuple(exp.weights) if isinstance(exp.weights, (tuple, list)) else None
    if weights is None or len(weights) != len(arms):
        raise ValueError(f"{where}: weights {exp.weights!r} must have one entry per arm ({len(arms)})")
    for w in weights:
        if isinstance(w, bool) or not isinstance(w, int) or w < 0:
            raise ValueError(f"{where}: weights must be ints >= 0, got {w!r}")
    if sum(weights) != 100:
        raise ValueError(f"{where}: weights must sum to 100, got {sum(weights)}")
    if not isinstance(exp.salt, str) or not exp.salt.strip():
        raise ValueError(f"{where}: salt is required")
    started = _parse_day(exp.started)
    if started is None:
        raise ValueError(f"{where}: started {exp.started!r} must be YYYY-MM-DD")
    planned_end = _parse_day(exp.planned_end)
    if planned_end is None:
        raise ValueError(f"{where}: planned_end {exp.planned_end!r} must be YYYY-MM-DD (it is required)")
    if planned_end <= started:
        raise ValueError(f"{where}: planned_end {exp.planned_end} must be after started {exp.started}")
    if exp.ended is not None and _parse_day(exp.ended) is None:
        raise ValueError(f"{where}: ended {exp.ended!r} must be YYYY-MM-DD")
    if exp.ended is not None and exp.winner is None:
        raise ValueError(f"{where}: ended is set without a winner (set both to end it)")
    if exp.winner is not None and exp.ended is None:
        raise ValueError(f"{where}: winner is set without ended (set both to end it)")
    if exp.winner is not None and exp.winner not in arms:
        raise ValueError(f"{where}: winner {exp.winner!r} is not one of its arms {arms}")
    if exp.primary not in PRIMARY_METRICS:
        raise ValueError(f"{where}: primary {exp.primary!r} must be one of {PRIMARY_METRICS}")
    if not isinstance(exp.hypothesis, str) or not exp.hypothesis.strip():
        raise ValueError(f"{where}: hypothesis is required (one sentence)")
    text = exp.arms_text if isinstance(exp.arms_text, dict) else {}
    for a in arms:
        line = text.get(a)
        if not isinstance(line, str) or not line.strip():
            raise ValueError(f"{where}: arms_text needs a non-empty line for arm {a!r}")


def validate(experiments: list[Experiment] | None = None) -> None:
    """Raise ValueError with a readable message when the registry is unusable."""
    exps = _reg(experiments)
    names = set()
    live_pages: dict[str, str] = {}
    for exp in exps:
        _validate_one(exp)
        if exp.name in names:
            raise ValueError(f"experiment name {exp.name!r} is used twice")
        names.add(exp.name)
        if exp.ended is None:
            if exp.page in live_pages:
                raise ValueError(f"page {exp.page!r} has two live experiments: {live_pages[exp.page]!r} and "
                                 f"{exp.name!r} (at most one per page)")
            live_pages[exp.page] = exp.name


# ------------------------------------------------------------------------------------------ assignment

def is_live(exp: Experiment, day: str | None = None) -> bool:
    day = day or today_utc()
    return exp.started <= day and (exp.ended is None or day < exp.ended)


def live_experiments(page: str | None = None, day: str | None = None, experiments=None) -> list[Experiment]:
    day = day or today_utc()
    return [e for e in _reg(experiments) if is_live(e, day) and (page is None or e.page == page)]


def arm_for(ip: str, ua: str, exp: Experiment) -> str:
    h = int(hashlib.sha256(f"{ip}|{ua}|{exp.name}|{exp.salt}".encode()).hexdigest()[:8], 16) % 1000
    cum = 0
    for arm, w in zip(exp.arms, exp.weights):
        cum += w
        if h < 10 * cum:
            return arm
    return exp.arms[0]   # unreachable for a valid registry (weights sum to 100)


def parse_override(raw: str | None, experiments=None) -> dict[str, str]:
    """``"hero:b,other:a"`` -> ``{"hero": "b", "other": "a"}``; silently drops anything not usable."""
    if not raw or not isinstance(raw, str):
        return {}
    by_name = {e.name: e for e in _reg(experiments)}
    out: dict[str, str] = {}
    for item in raw.split(",")[:MAX_OVERRIDE_ITEMS]:
        name, sep, arm = item.partition(":")
        if not sep:
            continue
        name, arm = name.strip(), arm.strip()
        exp = by_name.get(name)
        if exp is None or arm not in exp.arms:
            continue
        out[name] = arm
    return out


def served_arms(ip: str, ua: str, page: str, override: dict[str, str] | None = None,
                day: str | None = None, experiments=None) -> dict[str, str]:
    """Arm per registry experiment on ``page``: live -> override or hash; ended -> winner; future -> a."""
    day = day or today_utc()
    override = override or {}
    out: dict[str, str] = {}
    for exp in _reg(experiments):
        if exp.page != page:
            continue
        if day < exp.started:
            out[exp.name] = "a"
        elif is_live(exp, day):
            forced = override.get(exp.name)
            out[exp.name] = forced if forced in exp.arms else arm_for(ip, ua, exp)
        else:
            out[exp.name] = exp.winner or "a"
    return out


# ------------------------------------------------------------------------------------------------ HTML

AB_BLOCK_RE = re.compile(
    r"<!--\s*ab\s+([a-z0-9_]+)\s*:\s*([a-z0-9_]+)\s*-->(.*?)<!--\s*/ab\s*-->",
    re.DOTALL,
)


def strip_arms(html: str, arms: dict[str, str]) -> str:
    """Keep the drawn arm's block contents, drop the rest; marker comments always go."""
    def repl(m: re.Match) -> str:
        name, arm, inner = m.group(1), m.group(2), m.group(3)
        return inner if arm == arms.get(name, "a") else ""
    return AB_BLOCK_RE.sub(repl, html)


def data_ab(arms: dict[str, str]) -> str:
    return " ".join(f"{k}:{v}" for k, v in arms.items())


# ---------------------------------------------------------------------------------------------- reading

def p_beats_control(control_hits: int, control_n: int, arm_hits: int, arm_n: int,
                    draws: int = 20000, seed: int = 0) -> float | None:
    """Share of Beta posterior draws where the arm's rate exceeds the control's (uniform prior)."""
    if not control_n or not arm_n or draws <= 0:
        return None
    rng = random.Random(seed)
    ca, cb = 1 + control_hits, 1 + max(0, control_n - control_hits)
    aa, ab = 1 + arm_hits, 1 + max(0, arm_n - arm_hits)
    wins = 0
    for _ in range(draws):
        if rng.betavariate(aa, ab) > rng.betavariate(ca, cb):
            wins += 1
    return wins / draws


def sample_size_per_arm(p_control: float, rel_lift: float = 0.5, alpha_z: float = Z_ALPHA_2,
                        power_z: float = Z_POWER) -> int | None:
    """Two-proportion sample size per arm to detect p_control -> p_control * (1 + rel_lift)."""
    if p_control is None or not (0 < p_control < 1) or not rel_lift:
        return None
    p1 = p_control
    p2 = min(p1 * (1 + rel_lift), 0.999)
    if p2 == p1:
        return None
    pbar = (p1 + p2) / 2
    num = (alpha_z * math.sqrt(2 * pbar * (1 - pbar)) + power_z * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    return math.ceil(num / (p2 - p1) ** 2)


def days_to_decision(p_control: float, exposures_per_day_per_arm: float, rel_lift: float = 0.5) -> float | None:
    if not p_control or not exposures_per_day_per_arm or exposures_per_day_per_arm <= 0:
        return None
    n = sample_size_per_arm(p_control, rel_lift)
    if n is None:
        return None
    return n / exposures_per_day_per_arm


def _days_between(a: str, b: str) -> int:
    da, db = _parse_day(a), _parse_day(b)
    if da is None or db is None:
        return 0
    return (db - da).days


def decide(exp: Experiment, per_arm: dict[str, dict], today: str | None = None) -> dict:
    """Apply the decision rule (plan 3.5) to per-arm ``{"exposures", "primary"}`` counts."""
    today = today or today_utc()
    stop = exp.ended if exp.ended is not None and exp.ended < today else today
    days_running = max(0, _days_between(exp.started, stop))

    def counts(arm: str) -> tuple[int, int]:
        row = per_arm.get(arm) or {}
        return int(row.get("exposures") or 0), int(row.get("primary") or 0)

    cn, ch = counts("a")
    p: dict[str, float | None] = {}
    for arm in exp.arms[1:]:
        an, ah = counts(arm)
        p[arm] = p_beats_control(ch, cn, ah, an)
    min_exposures_met = all(counts(a)[0] >= MIN_EXPOSURES for a in exp.arms)
    min_days_met = days_running >= MIN_DAYS
    winner_by_rule = None
    if min_exposures_met and min_days_met:
        best = None
        for arm, val in p.items():
            if val is not None and val >= P_THRESHOLD and (best is None or val > p[best]):
                best = arm
        winner_by_rule = best

    if exp.ended is not None and exp.ended <= today:
        status = "ended — control kept" if exp.winner == "a" else f"ended — winner {exp.winner}"
    elif today < exp.started:
        status = "not started"
    elif winner_by_rule is not None:
        status = f"winner by rule: {winner_by_rule}"
    elif today >= exp.planned_end:
        status = "decision due"
    else:
        status = "running — not yet"

    return {
        "p_beats_control": p,
        "days_running": days_running,
        "min_exposures_met": min_exposures_met,
        "min_days_met": min_days_met,
        "winner_by_rule": winner_by_rule,
        "status": status,
        "days_left": _days_between(today, exp.planned_end),
    }


def describe(exp: Experiment, today: str | None = None) -> str:
    if exp.ended is not None:
        return f"{exp.name} on {exp.page} (ended {exp.ended}, winner {exp.winner})"
    return (f"{exp.name} on {exp.page} ({'/'.join(exp.arms)}, since {exp.started}, "
            f"decision due {exp.planned_end})")


def summary_line(today: str | None = None, experiments=None) -> str:
    live = live_experiments(day=today or today_utc(), experiments=experiments)
    if not live:
        return "live experiments: none"
    return "live experiments: " + "; ".join(describe(e, today) for e in live)
