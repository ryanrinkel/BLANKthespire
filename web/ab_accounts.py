"""Page experiments, Phase 2: what the NEW accounts of each arm went on to do (docs/plans/AB_TESTING_PLAN.md 3.6).

``users.signup_ab`` carries the arms label (``"hero:b"``, or several space-separated ``name:arm`` tokens) that
auth._resolve_identity stamped when the account was born. Per arm of an experiment this counts:

* ``accounts`` — users whose label has the token ``f"{exp.name}:{arm}"`` and who were created on/after
  ``exp.started`` (and before ``exp.ended`` when it is set). Returning users are never here: they had an
  account before, so no stamp.
* ``forged`` — of those, the ones with at least one ``done`` ForgeJob.
* ``donated`` — of those, the ones with at least one ``paid`` Purchase.
* ``hosted_cost_usd`` — what their "Use a token" forges cost us: ForgeUsage rows with ``mode == "token"``,
  metered cost falling back to the rate-table estimate per row (models.billed_micros), exactly as
  app.admin_stats and app._promo_stats (the sign-up event stats) do.

Imports db / models / experiments and the standard library only — never app — so the mail CLI can use it.
Every public function swallows a DB problem and returns ``{}``: an Experiments card or a digest without the
account columns is better than none.
"""
from __future__ import annotations

import logging
from datetime import datetime

import experiments as _exp
from db import session_scope
from models import ForgeJob, ForgeUsage, Purchase, User, billed_micros

log = logging.getLogger(__name__)


def _day_start(day: str) -> datetime:
    """'YYYY-MM-DD' -> naive UTC midnight (the convention of every DateTime column here)."""
    return datetime.fromisoformat(day)


def _tokens(label: str | None) -> set[str]:
    return set((label or "").split())


def _empty() -> dict:
    return {"accounts": 0, "forged": 0, "donated": 0, "hosted_cost_usd": 0.0}


def _per_arm(s, exp) -> dict[str, dict]:
    out = {arm: _empty() for arm in exp.arms}
    q = (s.query(User.id, User.signup_ab)
         .filter(User.signup_ab.isnot(None), User.signup_ab.like(f"%{exp.name}:%"),
                 User.created_at >= _day_start(exp.started)))
    if exp.ended is not None:
        q = q.filter(User.created_at < _day_start(exp.ended))
    arm_of: dict[int, str] = {}
    for uid, label in q.all():
        toks = _tokens(label)
        for arm in exp.arms:
            if f"{exp.name}:{arm}" in toks:
                arm_of[uid] = arm
                break
    if not arm_of:
        return out
    uids = list(arm_of)
    for arm in arm_of.values():
        out[arm]["accounts"] += 1
    forged = {uid for (uid,) in (s.query(ForgeJob.user_id)
                                 .filter(ForgeJob.user_id.in_(uids), ForgeJob.status == "done").distinct())}
    donors = {uid for (uid,) in (s.query(Purchase.user_id)
                                 .filter(Purchase.user_id.in_(uids), Purchase.status == "paid").distinct())}
    for uid in forged:
        out[arm_of[uid]]["forged"] += 1
    for uid in donors:
        out[arm_of[uid]]["donated"] += 1
    micros: dict[str, int] = {}
    for uid, metered, est in (s.query(ForgeUsage.user_id, ForgeUsage.metered_cost_micros,
                                      ForgeUsage.est_cost_micros)
                              .filter(ForgeUsage.user_id.in_(uids), ForgeUsage.mode == "token").all()):
        billed = billed_micros(metered, est)
        if billed is not None:
            arm = arm_of[uid]
            micros[arm] = micros.get(arm, 0) + int(billed)
    for arm, m in micros.items():
        out[arm]["hosted_cost_usd"] = round(m / 1_000_000, 6)
    return out


def accounts_per_arm(exp, today: str | None = None) -> dict[str, dict]:
    """``{arm: {"accounts", "forged", "donated", "hosted_cost_usd"}}`` for one experiment, or ``{}`` when the
    database could not be read. ``today`` is accepted for symmetry with the other read-outs; the window is
    the registry's own [started, ended)."""
    try:
        with session_scope() as s:
            return _per_arm(s, exp)
    except Exception as e:  # noqa: BLE001 — never let the account side break the card or the mail
        log.warning("experiment %s: account attribution lookup failed: %s", getattr(exp, "name", "?"), e)
        return {}


def accounts_payload(experiments_list, today: str | None = None) -> dict[str, dict[str, dict]]:
    """``{experiment name: accounts_per_arm(...)}`` for every experiment given (the ones the card shows), in
    one session; ``{}`` when the database could not be read."""
    today = today or _exp.today_utc()
    try:
        with session_scope() as s:
            return {exp.name: _per_arm(s, exp) for exp in experiments_list}
    except Exception as e:  # noqa: BLE001
        log.warning("experiments: account attribution lookup failed: %s", e)
        return {}
