"""Module-level tests for web/experiments.py (registry, assignment, HTML markers, the decision math)."""
from __future__ import annotations

import dataclasses

import pytest

import experiments as ex


def mk(**kw) -> ex.Experiment:
    base = dict(
        name="t", page="/", arms=("a", "b"), weights=(50, 50), salt="s1",
        started="2026-11-03", planned_end="2026-12-15", primary="login",
        hypothesis="B lifts /login opens.", arms_text={"a": "control", "b": "variant"},
    )
    base.update(kw)
    return ex.Experiment(**base)


def pairs(n=10_000):
    return [(f"10.{i // 65536}.{(i // 256) % 256}.{i % 256}", f"Mozilla/5.0 test-{i % 7}") for i in range(n)]


# ------------------------------------------------------------------------------------------- arm_for

def test_arm_for_deterministic_and_salted():
    e = mk()
    assert ex.arm_for("1.2.3.4", "UA", e) == ex.arm_for("1.2.3.4", "UA", e)
    e2 = dataclasses.replace(e, salt="s2")
    diff = sum(ex.arm_for(ip, ua, e) != ex.arm_for(ip, ua, e2) for ip, ua in pairs(1000))
    assert 350 < diff < 650   # an independent re-split, not identical


def test_arm_for_matches_hash_formula():
    import hashlib
    e = mk()
    h = int(hashlib.sha256(b"1.2.3.4|UA|t|s1").hexdigest()[:8], 16) % 1000
    assert ex.arm_for("1.2.3.4", "UA", e) == ("a" if h < 500 else "b")


@pytest.mark.parametrize("weights", [(50, 50), (90, 10)])
def test_arm_for_weights(weights):
    e = mk(weights=weights)
    ps = pairs()
    share_a = sum(ex.arm_for(ip, ua, e) == "a" for ip, ua in ps) / len(ps) * 100
    assert abs(share_a - weights[0]) <= 2


def test_arm_for_three_arms():
    e = mk(arms=("a", "b", "c"), weights=(34, 33, 33), arms_text={"a": "x", "b": "y", "c": "z"})
    counts = {"a": 0, "b": 0, "c": 0}
    for ip, ua in pairs():
        counts[ex.arm_for(ip, ua, e)] += 1
    assert all(abs(v / 100 - 33.3) <= 2.5 for v in counts.values())


def test_arm_for_zero_weight_arm_never_drawn():
    e = mk(weights=(100, 0))
    assert {ex.arm_for(ip, ua, e) for ip, ua in pairs(2000)} == {"a"}


# ----------------------------------------------------------------------------------- parse_override

REG = [mk(name="hero"), mk(name="other", page="/login", arms=("a", "b", "c"), weights=(40, 30, 30),
                            arms_text={"a": "x", "b": "y", "c": "z"})]


def test_parse_override_valid():
    assert ex.parse_override("hero:b,other:c", REG) == {"hero": "b", "other": "c"}
    assert ex.parse_override(" hero : b , other:a ", REG) == {"hero": "b", "other": "a"}


@pytest.mark.parametrize("raw", [None, "", ",,", "hero", "hero:", ":b", "nope:b", "hero:z", "HERO:b", "hero:B",
                                 "hero=b"])
def test_parse_override_rejects(raw):
    assert ex.parse_override(raw, REG) == {}


def test_parse_override_mixed():
    assert ex.parse_override("junk,hero:b,nope:a,other:q", REG) == {"hero": "b"}


def test_parse_override_cap():
    raw = ",".join(["junk"] * 20 + ["hero:b"])
    assert ex.parse_override(raw, REG) == {}
    raw = ",".join(["junk"] * 19 + ["hero:b"])
    assert ex.parse_override(raw, REG) == {"hero": "b"}


def test_parse_override_default_registry():
    assert ex.parse_override("hero:b") == {"hero": "b"}


# -------------------------------------------------------------------------------------- served_arms

def test_served_arms_live_override_else_hash():
    reg = [mk(name="hero")]
    want = ex.arm_for("1.1.1.1", "UA", reg[0])
    assert ex.served_arms("1.1.1.1", "UA", "/", day="2026-11-10", experiments=reg) == {"hero": want}
    other = "b" if want == "a" else "a"
    got = ex.served_arms("1.1.1.1", "UA", "/", {"hero": other}, day="2026-11-10", experiments=reg)
    assert got == {"hero": other}


def test_served_arms_ended_returns_winner_ignores_override():
    reg = [mk(name="hero", ended="2026-12-01", winner="b")]
    for ip, ua in pairs(50):
        assert ex.served_arms(ip, ua, "/", {"hero": "a"}, day="2026-12-02", experiments=reg) == {"hero": "b"}


def test_served_arms_not_started_is_control_unless_previewed():
    """Before the start day every visitor gets the control — but ?ab= still previews an arm, so the
    operator can check both arms between the deploy and the start (2026-11-03: the 'see it' links showed
    the control at both arms for the rest of the deploy day)."""
    reg = [mk(name="hero", started="2026-12-01", planned_end="2026-12-31")]
    for ip, ua in pairs(50):
        assert ex.served_arms(ip, ua, "/", None, day="2026-11-30", experiments=reg) == {"hero": "a"}
        assert ex.served_arms(ip, ua, "/", {"hero": "b"}, day="2026-11-30", experiments=reg) == {"hero": "b"}
        assert ex.served_arms(ip, ua, "/", {"hero": "zz"}, day="2026-11-30", experiments=reg) == {"hero": "a"}


def test_served_arms_only_that_page_registry_order():
    reg = [mk(name="zed"), mk(name="login_x", page="/login"), mk(name="alpha", ended="2026-11-05", winner="a")]
    got = ex.served_arms("1.1.1.1", "UA", "/", day="2026-11-10", experiments=reg)
    assert list(got) == ["zed", "alpha"]
    assert got["alpha"] == "a"
    assert list(ex.served_arms("1.1.1.1", "UA", "/login", day="2026-11-10", experiments=reg)) == ["login_x"]
    assert ex.served_arms("1.1.1.1", "UA", "/help", day="2026-11-10", experiments=reg) == {}


# --------------------------------------------------------------------------------------- strip_arms

PAGE = """<html><body>
<p>before</p>
<!--ab hero:a-->
<a id="signin">Create Your Own Class</a>
<!--/ab-->
<!--ab hero:b-->
<a id="signin">Forge a class</a>
<!--/ab-->
<p>after</p>
</body></html>"""


def test_strip_arms_keeps_chosen_drops_other():
    out = ex.strip_arms(PAGE, {"hero": "b"})
    assert "Forge a class" in out and "Create Your Own Class" not in out
    assert "<!--" not in out
    assert "<p>before</p>" in out and "<p>after</p>" in out
    out = ex.strip_arms(PAGE, {"hero": "a"})
    assert "Create Your Own Class" in out and "Forge a class" not in out


def test_strip_arms_unknown_name_keeps_a():
    out = ex.strip_arms(PAGE, {})
    assert "Create Your Own Class" in out and "Forge a class" not in out and "<!--" not in out


def test_strip_arms_several_experiments():
    html = "<!--ab x:a-->XA<!--/ab--><!--ab x:b-->XB<!--/ab-->|<!--ab y:a-->YA<!--/ab--><!--ab y:c-->YC<!--/ab-->"
    assert ex.strip_arms(html, {"x": "b", "y": "c"}) == "XB|YC"
    assert ex.strip_arms(html, {"x": "a", "y": "b"}) == "XA|"


def test_strip_arms_whitespace_tolerant_markers():
    html = "1<!-- ab hero:b -->B<!-- /ab -->2<!--ab  hero : a  -->A<!--/ab-->3"
    assert ex.strip_arms(html, {"hero": "b"}) == "1B23"


def test_strip_arms_untouched_without_markers():
    html = "<html><!-- a normal comment --><p>x</p></html>"
    assert ex.strip_arms(html, {"hero": "b"}) == html


def test_strip_arms_dotall_multiline():
    html = "<!--ab hero:b-->\nline1\nline2\n<!--/ab-->"
    assert ex.strip_arms(html, {"hero": "b"}) == "\nline1\nline2\n"
    assert ex.strip_arms(html, {"hero": "a"}) == ""


def test_ab_block_re_groups():
    m = ex.AB_BLOCK_RE.search("<!-- ab hero_2:b1 -->in<!--/ab-->")
    assert m and m.group(1) == "hero_2" and m.group(2) == "b1" and m.group(3) == "in"


# ------------------------------------------------------------------------------------------- data_ab

def test_data_ab():
    assert ex.data_ab({}) == ""
    assert ex.data_ab({"hero": "b"}) == "hero:b"
    assert ex.data_ab({"hero": "b", "other": "a"}) == "hero:b other:a"


# ------------------------------------------------------------------------------------------ validate

def test_real_registry_validates():
    ex.validate()
    ex.validate(ex.EXPERIMENTS)
    assert [e.name for e in ex.EXPERIMENTS] == ["hero"]


def test_validate_empty_ok():
    ex.validate([])


BAD = {
    "bad name": dict(name="Hero"),
    "bad name dash": dict(name="he-ro"),
    "arms empty": dict(arms=(), weights=(), arms_text={}),
    "arms0 not a": dict(arms=("b", "a")),
    "bad arm name": dict(arms=("a", "B"), arms_text={"a": "x", "B": "y"}),
    "dup arm": dict(arms=("a", "a"), arms_text={"a": "x"}),
    "weights len": dict(weights=(100,)),
    "weights sum": dict(weights=(50, 40)),
    "weights negative": dict(weights=(110, -10)),
    "weights float": dict(weights=(50.0, 50.0)),
    "salt empty": dict(salt=""),
    "started bad": dict(started="2026-13-01"),
    "started format": dict(started="2026/11/03"),
    "planned_end missing": dict(planned_end=""),
    "planned_end bad": dict(planned_end="soon"),
    "planned_end before": dict(planned_end="2026-11-03"),
    "ended bad": dict(ended="nope", winner="b"),
    "ended no winner": dict(ended="2026-12-01"),
    "winner no ended": dict(winner="b"),
    "winner not arm": dict(ended="2026-12-01", winner="c"),
    "primary bad": dict(primary="sales"),
    "hypothesis empty": dict(hypothesis=""),
    "hypothesis blank": dict(hypothesis="   "),
    "arms_text missing": dict(arms_text={"a": "x"}),
    "arms_text empty line": dict(arms_text={"a": "x", "b": " "}),
    "page no slash": dict(page="login"),
}


@pytest.mark.parametrize("kw", list(BAD.values()), ids=list(BAD))
def test_validate_rejects(kw):
    with pytest.raises(ValueError):
        ex.validate([mk(**kw)])


def test_validate_rejects_duplicate_names():
    with pytest.raises(ValueError, match="twice"):
        ex.validate([mk(), mk(page="/login")])


def test_validate_rejects_two_live_on_one_page():
    with pytest.raises(ValueError, match="two live"):
        ex.validate([mk(name="one"), mk(name="two")])


def test_validate_allows_ended_next_to_live_on_same_page():
    ex.validate([mk(name="old", ended="2026-11-20", winner="b"), mk(name="new")])
    ex.validate([mk(name="one"), mk(name="two", page="/login")])


# ---------------------------------------------------------------------------------- p_beats_control

def test_p_identical_arms_half():
    p = ex.p_beats_control(70, 1000, 70, 1000, draws=20000)
    assert abs(p - 0.5) <= 0.05


def test_p_clear_winner_and_loser():
    assert ex.p_beats_control(50, 1000, 100, 1000) > 0.99
    assert ex.p_beats_control(100, 1000, 50, 1000) < 0.01


def test_p_none_on_zero_n():
    assert ex.p_beats_control(0, 0, 5, 100) is None
    assert ex.p_beats_control(5, 100, 0, 0) is None


def test_p_seed_reproducible():
    a = ex.p_beats_control(10, 100, 14, 100, draws=5000, seed=7)
    assert a == ex.p_beats_control(10, 100, 14, 100, draws=5000, seed=7)
    assert 0 < a < 1


# ------------------------------------------------------------------------------- sample size / days

@pytest.mark.parametrize("p,lift,want", [(0.07, 0.5, 1020), (0.07, 1.0, 300), (0.25, 0.28, 640)])
def test_sample_size_sanity(p, lift, want):
    n = ex.sample_size_per_arm(p, lift)
    assert isinstance(n, int)
    assert abs(n - want) <= want * 0.10


@pytest.mark.parametrize("p", [0, 1, -0.1, 1.5])
def test_sample_size_none(p):
    assert ex.sample_size_per_arm(p) is None


def test_days_to_decision():
    n = ex.sample_size_per_arm(0.07, 0.5)
    assert ex.days_to_decision(0.07, 10) == pytest.approx(n / 10)
    assert ex.days_to_decision(0.07, 0) is None
    assert ex.days_to_decision(0, 10) is None
    assert ex.days_to_decision(None, 10) is None
    assert ex.days_to_decision(0.07, None) is None


# --------------------------------------------------------------------------------------------- decide

BIG = {"a": {"exposures": 1000, "primary": 50}, "b": {"exposures": 1000, "primary": 100}}
SMALL = {"a": {"exposures": 50, "primary": 3}, "b": {"exposures": 50, "primary": 4}}


def test_decide_not_started():
    d = ex.decide(mk(started="2026-12-01", planned_end="2026-12-31"), {}, today="2026-11-20")
    assert d["status"] == "not started" and d["days_running"] == 0 and d["p_beats_control"] == {"b": None}


def test_decide_running_not_yet():
    d = ex.decide(mk(), SMALL, today="2026-11-10")
    assert d["status"] == "running — not yet"
    assert d["days_running"] == 7 and not d["min_days_met"] and not d["min_exposures_met"]
    assert d["winner_by_rule"] is None and d["days_left"] == 35
    assert 0 < d["p_beats_control"]["b"] < 1


def test_decide_big_but_too_early_is_not_a_winner():
    d = ex.decide(mk(), BIG, today="2026-11-10")
    assert d["min_exposures_met"] and not d["min_days_met"]
    assert d["winner_by_rule"] is None and d["status"] == "running — not yet"


def test_decide_winner_by_rule():
    d = ex.decide(mk(), BIG, today="2026-11-20")
    assert d["min_days_met"] and d["min_exposures_met"]
    assert d["winner_by_rule"] == "b" and d["status"] == "winner by rule: b"


def test_decide_picks_highest_p_among_arms():
    e = mk(arms=("a", "b", "c"), weights=(34, 33, 33), arms_text={"a": "x", "b": "y", "c": "z"})
    per = {"a": {"exposures": 1000, "primary": 50}, "b": {"exposures": 1000, "primary": 90},
           "c": {"exposures": 1000, "primary": 120}}
    assert ex.decide(e, per, today="2026-11-30")["winner_by_rule"] == "c"


def test_decide_decision_due():
    d = ex.decide(mk(), SMALL, today="2026-12-15")
    assert d["status"] == "decision due" and d["days_left"] == 0
    d = ex.decide(mk(), SMALL, today="2026-12-20")
    assert d["status"] == "decision due" and d["days_left"] == -5


def test_decide_ended_variants():
    d = ex.decide(mk(ended="2026-12-01", winner="b"), BIG, today="2026-12-05")
    assert d["status"] == "ended — winner b"
    assert d["days_running"] == 28   # stops counting at the end date
    d = ex.decide(mk(ended="2026-12-01", winner="a"), SMALL, today="2026-12-05")
    assert d["status"] == "ended — control kept"


# ------------------------------------------------------------------------------- describe / summary

def test_describe():
    assert ex.describe(mk(name="hero")) == "hero on / (a/b, since 2026-11-03, decision due 2026-12-15)"
    assert ex.describe(mk(name="hero", ended="2026-12-01", winner="b")) == "hero on / (ended 2026-12-01, winner b)"


def test_summary_line_none():
    assert ex.summary_line(today="2026-11-01", experiments=[mk(name="hero")]) == "live experiments: none"
    assert ex.summary_line(experiments=[]) == "live experiments: none"
    ended = [mk(name="hero", ended="2026-11-20", winner="b")]
    assert ex.summary_line(today="2026-11-25", experiments=ended) == "live experiments: none"


def test_summary_line_live():
    reg = [mk(name="hero"), mk(name="other", page="/login")]
    assert ex.summary_line(today="2026-11-10", experiments=reg) == (
        "live experiments: hero on / (a/b, since 2026-11-03, decision due 2026-12-15); "
        "other on /login (a/b, since 2026-11-03, decision due 2026-12-15)")


def test_summary_line_default_registry():
    assert ex.summary_line(today="2026-11-10").startswith("live experiments: hero on / (a/b")


# ---------------------------------------------------------------------------------------------- is_live

def test_is_live_boundaries():
    e = mk(ended="2026-12-01", winner="b")
    assert not ex.is_live(e, "2026-11-02")
    assert ex.is_live(e, "2026-11-03")
    assert ex.is_live(e, "2026-11-30")
    assert not ex.is_live(e, "2026-12-01")
    assert ex.is_live(mk(), "2027-06-01")   # no ended: live past planned_end until someone ends it


def test_live_experiments_filter():
    reg = [mk(name="one"), mk(name="two", page="/login"), mk(name="old", ended="2026-11-05", winner="a")]
    assert [e.name for e in ex.live_experiments(day="2026-11-10", experiments=reg)] == ["one", "two"]
    assert [e.name for e in ex.live_experiments("/login", day="2026-11-10", experiments=reg)] == ["two"]
    assert [e.name for e in ex.live_experiments(day="2026-11-04", experiments=reg)] == ["one", "two", "old"]


def test_today_utc_format():
    assert ex.DATE_RE.match(ex.today_utc())


def test_module_is_stdlib_only():
    import ast
    import pathlib
    src = pathlib.Path(ex.__file__).read_text(encoding="utf-8")
    mods = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            mods.add((node.module or "").split(".")[0])
    assert mods <= {"__future__", "dataclasses", "hashlib", "re", "random", "math", "datetime"}


# ================================================================================ route level (pages.py)
# The splash and the other public pages are served through pages.serve_page / finish_page: arms drawn from
# IP + UA, markers stripped, data-ab stamped, no shared caching, and never a cookie.

import re as _re  # noqa: E402

from conftest import login  # noqa: E402

ADMIN = "unlimited@example.com"
UA = "Mozilla/5.0 test-agent"
ARM_TEXT = {"a": "Create Your Own Class", "b": "Forge a class — free with your own API key"}
PRIVACY_SENTENCE = ("We sometimes show two versions of a page to different visitors and compare, in aggregate, "
                    "how far each version's visitors got, using the same server logs described above. Nothing "
                    "is stored on your device for this.")


@pytest.fixture()
def day(monkeypatch):
    """Pin 'today' inside the hero experiment's window so the route tests do not drift with the calendar."""
    monkeypatch.setattr(ex, "today_utc", lambda: "2026-11-10")
    return "2026-11-10"


def _hero():
    return next(e for e in ex.EXPERIMENTS if e.name == "hero")


def _get(client, path, ip="203.0.113.7", ua=UA):
    return client.get(path, headers={"User-Agent": ua, "X-Forwarded-For": ip})


def _arm_in(body: str) -> str:
    has_a, has_b = ARM_TEXT["a"] in body, ARM_TEXT["b"] in body
    assert has_a != has_b, "exactly one hero arm must be in the page"
    return "a" if has_a else "b"


def _assert_page_headers(r):
    assert r.headers["Content-Type"] == "text/html; charset=utf-8"
    assert r.headers["Cache-Control"] == "private, no-cache"
    assert "User-Agent" in r.headers.get("Vary", "")
    assert "Set-Cookie" not in r.headers


def _ip_for_arm(arm: str) -> str:
    for i in range(256):
        ip = f"198.51.100.{i}"
        if ex.arm_for(ip, UA, _hero()) == arm:
            return ip
    raise AssertionError(f"no ip drew arm {arm}")


def test_splash_serves_one_arm_matching_the_hash(client, day):
    ip = "203.0.113.7"
    r = _get(client, "/", ip)
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert body.count('id="signin"') == 1
    assert "<!--ab" not in body and "<!--/ab" not in body
    want = ex.arm_for(ip, UA, _hero())
    assert _arm_in(body) == want
    assert _re.search(r'<html[^>]*\sdata-ab="hero:%s"' % want, body)
    _assert_page_headers(r)
    assert _get(client, "/", ip).get_data(as_text=True) == body   # same visitor, same page


def test_splash_both_arms_reachable_by_ip(client, day):
    for arm in ("a", "b"):
        body = _get(client, "/", _ip_for_arm(arm)).get_data(as_text=True)
        assert _arm_in(body) == arm
        assert f'data-ab="hero:{arm}"' in body


def test_override_is_for_that_request_only(client, day):
    ip = _ip_for_arm("a")
    body = _get(client, "/?ab=hero:b", ip).get_data(as_text=True)
    assert _arm_in(body) == "b"
    assert 'data-ab="hero:b"' in body
    _assert_page_headers(_get(client, "/?ab=hero:b", ip))
    assert _arm_in(_get(client, "/", ip).get_data(as_text=True)) == "a"   # nothing remembered
    ip_b = _ip_for_arm("b")
    assert _arm_in(_get(client, "/?ab=hero:a", ip_b).get_data(as_text=True)) == "a"
    assert _arm_in(_get(client, "/?ab=hero:zzz", ip_b).get_data(as_text=True)) == "b"   # junk ignored


def test_no_set_cookie_on_public_pages(client, day):
    for path in ("/", "/?ab=hero:b", "/login", "/help"):
        r = _get(client, path)
        assert r.status_code == 200, path
        assert "Set-Cookie" not in r.headers, path


def test_ended_experiment_serves_winner_to_everyone(client, day, monkeypatch):
    ended = dataclasses.replace(_hero(), ended="2026-11-05", winner="b")
    ips = (_ip_for_arm("a"), _ip_for_arm("b"))
    monkeypatch.setattr(ex, "EXPERIMENTS", [ended])
    for ip in ips:
        assert _arm_in(_get(client, "/", ip).get_data(as_text=True)) == "b"
    body = _get(client, "/?ab=hero:a").get_data(as_text=True)
    assert _arm_in(body) == "b"
    assert 'data-ab="hero:b"' in body


def test_empty_registry_serves_control_without_data_ab(client, day, monkeypatch):
    monkeypatch.setattr(ex, "EXPERIMENTS", [])
    r = _get(client, "/?ab=hero:b")
    body = r.get_data(as_text=True)
    assert _arm_in(body) == "a"
    assert "data-ab" not in body
    assert "<!--ab" not in body and "<!--/ab" not in body
    assert body.count('id="signin"') == 1
    _assert_page_headers(r)


def test_other_public_pages_go_through_the_helper(client, app_module, day):
    from test_pages import _make_class
    for path in ("/login", "/help", "/download", "/archive", "/terms", "/privacy"):
        r = client.get(path, headers={"User-Agent": UA})
        assert r.status_code == 200, path
        _assert_page_headers(r)
        assert "data-ab" not in r.get_data(as_text=True), path   # no experiment on these pages
    body = client.get("/download").get_data(as_text=True)
    assert app_module.WORKSHOP_URL in body
    assert app_module.mod_version() in body and "{{VERSION}}" not in body
    slug = _make_class(app_module, client)
    r = client.get(f"/deck/{slug}", headers={"User-Agent": UA})
    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "private, no-cache"
    assert "User-Agent" in r.headers.get("Vary", "")
    assert "The Tempest" in r.get_data(as_text=True)


def test_login_page_experiment_arms_strip(client, day, monkeypatch):
    """A /login experiment works through auth.py's route the same way (markers injected via read_static)."""
    import pages
    login_exp = dataclasses.replace(_hero(), name="signin_t", page="/login")
    monkeypatch.setattr(ex, "EXPERIMENTS", [login_exp])
    real = pages.read_static
    extra = "<!--ab signin_t:a-->ARM-A<!--/ab--><!--ab signin_t:b-->ARM-B<!--/ab-->"
    monkeypatch.setattr(pages, "read_static", lambda name: real(name) + (extra if name == "signin.html" else ""))
    body = _get(client, "/login?ab=signin_t:b").get_data(as_text=True)
    assert "ARM-B" in body and "ARM-A" not in body
    assert 'data-ab="signin_t:b"' in body


def test_api_me_admin_carries_experiments(client, day):
    user = login(client, ADMIN)
    assert user["admin"] is True
    hero = next(e for e in user["experiments"] if e["name"] == "hero")
    h = _hero()
    assert hero["page"] == "/"
    assert hero["arms"] == list(h.arms)
    assert hero["arms_text"] == h.arms_text
    assert hero["hypothesis"] == h.hypothesis
    assert hero["started"] == h.started and hero["planned_end"] == h.planned_end
    assert hero["day"] == ex._days_between(h.started, "2026-11-10") + 1
    assert hero["of"] == ex._days_between(h.started, h.planned_end)
    assert hero["arm"] in h.arms
    me = client.get("/api/me", headers={"User-Agent": UA, "X-Forwarded-For": "203.0.113.7"}).get_json()
    hero = next(e for e in me["user"]["experiments"] if e["name"] == "hero")
    assert hero["arm"] == ex.arm_for("203.0.113.7", UA, h)


def test_api_me_plain_user_and_signed_out_have_no_experiments(app_module, day):
    c = app_module.app.test_client()
    assert c.get("/api/me").get_json()["user"] is None
    user = login(c, "plain-ab@example.com")
    assert user["admin"] is False
    assert "experiments" not in user


def test_privacy_sentence_and_badge_script(client):
    body = client.get("/privacy").get_data(as_text=True)
    assert PRIVACY_SENTENCE in " ".join(body.split())
    r = client.get("/static/ab-badge.js")
    assert r.status_code == 200
    assert "experiments" in r.get_data(as_text=True)
    r.close()
    for path in ("/", "/login"):
        assert "/static/ab-badge.js?v=" in client.get(path).get_data(as_text=True), path


def test_boot_wiring(app_module):
    import pages
    assert app_module.experiments is ex
    assert app_module.pages is pages
    ex.validate()   # the registry app.py validated at import is still valid
    assert ex.summary_line().startswith("live experiments:")
