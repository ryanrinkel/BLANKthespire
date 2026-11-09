r"""Walk-away forge, section 3 (docs/plans/WALK_AWAY_FORGE_PLAN.md) — the forge announces its own pace. Offline.

Run:  uv run python -m pytest tests/test_forge_pace.py -q       (from generation/)

The card loop times each LLM-designed card (synthesized basics + the Sovereign Blade excluded) and, after the 3rd
timed card and every 10th after it, emits `pace: Ns/card, ~M min to go (K cards left)` when the projected remainder
exceeds PACE_WARN_MIN. web/app.py parses `~(\d+) min to go` out of that line, so its shape is pinned here.
"""
from __future__ import annotations

import re
import time

from btsgen.class_forge import point_btsgen_at_mod_contract

point_btsgen_at_mod_contract()

from btsgen import class_forge as cf  # noqa: E402
from btsgen.class_forge import ClassBrief, _CardFake, forge_class  # noqa: E402

_PACE_RE = re.compile(r"^pace: (\d+)s/card, ~(\d+) min to go \((\d+) cards left\)$")
_WEB_RE = re.compile(r"^pace: .*~(\d+) min to go")  # the web/app.py side of the contract
_DESIGNING = re.compile(r"^card \d+/\d+: designing ")


class _SlowCardFake(_CardFake):
    """The offline card fake, ~0.05 s per designed card."""

    def first_attempt(self, brief):
        time.sleep(0.05)
        return super().first_attempt(brief)


def _forge(monkeypatch, tmp_path, warn_min: str | None):
    monkeypatch.setenv("BTS_FORGE_LEDGER", str(tmp_path / "ledger.jsonl"))
    if warn_min is None:
        monkeypatch.delenv("BTSGEN_PACE_WARN_MIN", raising=False)
    else:
        monkeypatch.setenv("BTSGEN_PACE_WARN_MIN", warn_min)
    # a FORGE class: its blueprint carries the basics AND the synthesized signature blade, both excluded from timing
    return forge_class(ClassBrief(concept="a molten forge sovereign"), blueprint_gen=None,
                       card_gen_factory=lambda: _SlowCardFake(), relic_gen=None, fake=True, triad=False)


def test_pace_line_math():
    assert cf._pace_line(75, 32) == "pace: 75s/card, ~40 min to go (32 cards left)"
    assert cf._pace_line(0.05, 20) == "pace: 0s/card, ~1 min to go (20 cards left)"  # floor of 1 minute
    assert cf._pace_line(61, 1) == "pace: 61s/card, ~2 min to go (1 cards left)"  # ceil


def test_pace_warn_min_env(monkeypatch):
    monkeypatch.delenv("BTSGEN_PACE_WARN_MIN", raising=False)
    assert cf._pace_warn_min() == 10 == cf.PACE_WARN_MIN
    monkeypatch.setenv("BTSGEN_PACE_WARN_MIN", "0")
    assert cf._pace_warn_min() == 0
    monkeypatch.setenv("BTSGEN_PACE_WARN_MIN", "junk")
    assert cf._pace_warn_min() == 10


def test_pace_line_emitted_after_third_designed_card(monkeypatch, tmp_path):
    res = _forge(monkeypatch, tmp_path, "0")
    assert res.ok
    log = res.log
    designing = [i for i, m in enumerate(log) if _DESIGNING.match(m)]
    assert len(designing) > 3, f"fake blueprint too small for the pace check: {len(designing)} designed cards"
    pace = [i for i, m in enumerate(log) if m.startswith("pace:")]
    assert pace, "no pace line with PACE_WARN_MIN=0"
    for i in pace:
        m = _PACE_RE.match(log[i])
        assert m, f"pace line shape: {log[i]!r}"
        assert _WEB_RE.match(log[i]) and int(_WEB_RE.match(log[i]).group(1)) >= 1
        secs, mins, left = map(int, m.groups())
        # cards_left is exact: the designed cards whose "designing" line comes after this pace line
        assert left == sum(1 for d in designing if d > i), log[i]
        # 0.05 s/card -> 0s mean, and the 1-minute floor (real remainder is ~1-2 s; ceil can't project less)
        assert secs <= 1 and mins == 1
    # cadence: after the 3rd timed card, then the 13th, 23rd, ... (while cards remain)
    done_at = [sum(1 for d in designing if d < i) for i in pace]
    expected = [n for n in range(3, len(designing), 10)]
    assert done_at == expected, (done_at, expected)
    # the first one lands right after card 3's design and before card 4's
    assert designing[2] < pace[0] < designing[3]


def test_no_pace_line_for_a_fast_forge_at_default_threshold(monkeypatch, tmp_path):
    res = _forge(monkeypatch, tmp_path, None)
    assert res.ok
    assert not [m for m in res.log if m.startswith("pace:")]
