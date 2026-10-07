"""Site traffic for the operator page: tools/traffic_report.py (the nginx log summariser) and the two
admin routes that serve its output (/api/admin/traffic, /admin/traffic). No analytics script exists —
the access log is the only visitor record, so the parser's bucketing IS the definition of a visitor."""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import pytest

from conftest import H, login

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import traffic_report as tr  # noqa: E402

ADMIN = "unlimited@example.com"
UA_CHROME = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/153.0.0.0 Safari/537.36")
UA_PHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 "
            "Mobile/15E148 Safari/604.1")
GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"


def line(ip, day, path, status=200, ref="-", ua=UA_CHROME, method="GET", time="12:00:00"):
    return f'{ip} - - [{day}:{time} +0000] "{method} {path} HTTP/1.1" {status} 512 "{ref}" "{ua}"\n'


SAMPLE = [
    # 14 Sep: a human who only saw the splash; a human who clicked to /help; a bot; a scanner; no UA
    line("1.1.1.1", "14/Sep/2026", "/", ref="https://www.google.com/"),
    line("2.2.2.2", "14/Sep/2026", "/", ref="https://portfolio.example.net/resume.html"),
    line("2.2.2.2", "14/Sep/2026", "/help"),
    line("9.9.9.9", "14/Sep/2026", "/", ua=GOOGLEBOT),
    line("8.8.8.8", "14/Sep/2026", "/wp-login.php", status=404, ua="python-requests/2.31"),
    line("7.7.7.7", "14/Sep/2026", "/", ua="-"),
    # 15 Sep: a signed-in user straight into the app (no splash), the splash-only human returns and clicks
    line("3.3.3.3", "15/Sep/2026", "/app?utm_source=Reddit&utm_campaign=sts2"),  # a tracked post link
    line("3.3.3.3", "15/Sep/2026", "/api/me"),
    line("3.3.3.3", "15/Sep/2026", "/api/classes"),
    line("1.1.1.1", "15/Sep/2026", "/", ref="android-app://com.reddit.frontpage/"),
    line("1.1.1.1", "15/Sep/2026", "/download", ua=UA_PHONE),
    line("4.4.4.4", "15/Sep/2026", "/deck/sherman-52", ref="https://steamcommunity.com/"),
    line("4.4.4.4", "15/Sep/2026", "/deck/sherman-52", ref="https://steamcommunity.com/"),  # same IP twice
    # noise that must never count as a source: the OAuth bounce, an IP-shaped scanner host, our own site
    line("5.5.5.5", "15/Sep/2026", "/app", ref="https://accounts.google.com/"),
    line("5.5.5.5", "15/Sep/2026", "/", ref="https://condescending-wing.161-35-235-245.plesk.page/wp-admin/"),
    line("5.5.5.5", "15/Sep/2026", "/help", ref="https://www.blankthespire.com/"),
    line("6.6.6.6", "15/Sep/2026", "/", status=302),  # not a 200 splash
    line("5.5.5.5", "15/Sep/2026", "/css/style.css"),  # a probe that got 200: never a "page"
    line("5.5.5.5", "15/Sep/2026", "/.well-known/acme-challenge/abc"),  # certbot, not a page
    # featured strip: the deck page's JSON counts, its art thumbs do not
    line("4.4.4.4", "15/Sep/2026", "/api/deck/abc"),
    line("4.4.4.4", "15/Sep/2026", "/api/deck/abc"),  # same IP twice
    line("11.11.11.11", "15/Sep/2026", "/api/deck/abc/art/splash"),
    line("12.12.12.12", "15/Sep/2026", "/api/featured"),  # the splash fetches this: never "featured"
    # a splash visitor who clicked through to Steam: the 302 counts as workshop AND as clicked. They came
    # in from a tagged ad link (twice: a double click), so they are also the youtube/promo-oct26 tag's visitor
    line("10.10.10.10", "15/Sep/2026", "/?utm_source=youtube&utm_medium=video-ad&utm_campaign=promo-oct26"),
    line("10.10.10.10", "15/Sep/2026", "/?utm_source=youtube&utm_medium=video-ad&utm_campaign=promo-oct26"),
    line("10.10.10.10", "15/Sep/2026", "/workshop", status=302),
    # an ad network's verification crawler opening the same tagged link: a bot, never a click
    line("14.14.14.14", "15/Sep/2026", "/?utm_source=youtube&utm_campaign=promo-oct26", ua=GOOGLEBOT),
    # a gclid alone (no utm_source) says nothing about the source: not a tag
    line("1.1.1.1", "15/Sep/2026", "/download?gclid=abc123", ua=UA_PHONE),
    line("13.13.13.13", "15/Sep/2026", "/workshop", status=404),  # not a redirect: does not count
    # imports: the mod (no user agent through v0.4.0) pulling class 78's four assets in one burst ...
    line("20.20.20.20", "15/Sep/2026", "/static/forged/78/splash.png?v=97c9b086", ua="-", time="04:12:00"),
    line("20.20.20.20", "15/Sep/2026", "/static/forged/78/sprite.png?v=82719e6b", ua="-", time="04:12:01"),
    line("20.20.20.20", "15/Sep/2026", "/static/forged/78/relic.png", ua="-", time="04:12:02"),
    line("20.20.20.20", "15/Sep/2026", "/static/forged/78/cards.zip?v=1c3e", ua="-", time="04:12:03"),
    # ... a later build, from another player, same class (a second import session)
    line("21.21.21.21", "15/Sep/2026", "/static/forged/78/splash.png", ua="BlankTheSpire/0.5.0", time="18:30:00"),
    # never imports: a 404 (class deleted), a browser opening the URL, a sub-path the mod never fetches
    line("20.20.20.20", "15/Sep/2026", "/static/forged/79/splash.png", status=404, ua="-"),
    line("22.22.22.22", "15/Sep/2026", "/static/forged/80/splash.png", ref="https://blankthespire.com/deck/x"),
    line("20.20.20.20", "15/Sep/2026", "/static/forged/78/cards/strike.png", ua="-"),
]


@pytest.fixture()
def logs(tmp_path):
    """Two rotations: the older one gzipped, like /var/log/nginx after logrotate."""
    (tmp_path / "access.log.1.gz").write_bytes(gzip.compress("".join(SAMPLE[:6]).encode()))
    (tmp_path / "access.log").write_text("".join(SAMPLE[6:]), encoding="utf-8")
    return tmp_path


# --- the parser ---------------------------------------------------------------------------------------

def test_bot_detection():
    assert tr.is_bot("-") and tr.is_bot("") and tr.is_bot("Mozilla/5.0")
    assert tr.is_bot(GOOGLEBOT)
    assert tr.is_bot("python-requests/2.31") and tr.is_bot("Mozilla/5.0 zgrab/0.x")
    assert not tr.is_bot(UA_CHROME) and not tr.is_bot(UA_PHONE)


def test_referer_sources():
    ours = {"blankthespire.com"}
    assert tr.referer_source("https://www.google.com/", ours) == "google.com"
    assert tr.referer_source("android-app://com.reddit.frontpage/", ours) == "com.reddit.frontpage (android app)"
    assert tr.referer_source("https://accounts.google.com/", ours) is None
    assert tr.referer_source("https://www.blankthespire.com/app", ours) is None
    assert tr.referer_source("https://161.35.235.245/", ours) is None
    assert tr.referer_source("https://x.161-35-235-245.plesk.page/wp-admin/", ours) is None
    assert tr.referer_source("-", ours) is None and tr.referer_source("", ours) is None


def test_daily_buckets_are_exclusive_and_bots_are_dropped(logs):
    paths = tr._sorted_logs(str(logs / "access.log*"))
    assert [Path(p).name for p in paths] == ["access.log.1.gz", "access.log"]  # oldest first
    data = tr.build(paths, {"blankthespire.com"}, today="2026-09-15")
    by_day = {r["day"]: r for r in data["daily"]}
    d14, d15 = by_day["2026-09-14"], by_day["2026-09-15"]
    # 14th: 1.1.1.1 splash only, 2.2.2.2 clicked; 9.9.9.9 / 8.8.8.8 / 7.7.7.7 are bots and never appear
    assert (d14["landing_only"], d14["clicked"], d14["app"], d14["humans"]) == (1, 1, 0, 2)
    assert d14["requests"] == 6 and d14["bot_requests"] == 3
    # 15th: 3.3.3.3 in the app (no splash needed), 1.1.1.1 / 5.5.5.5 / 10.10.10.10 (via /workshop 302)
    # clicked, 4.4.4.4 deck only
    assert (d15["landing_only"], d15["clicked"], d15["app"], d15["humans"]) == (0, 3, 1, 4)
    assert d15["deck"] == 1 and d15["landing"] == 3  # the 302 from 6.6.6.6 is not a splash view
    # overlays: 4.4.4.4's /api/deck/abc (not 11.11.11.11's art thumb, not /api/featured); 10.10.10.10's 302
    assert d15["featured"] == 1 and d15["workshop"] == 1
    assert d14["featured"] == 0 and d14["workshop"] == 0


def test_windows_count_each_ip_once_at_its_deepest(logs):
    paths = tr._sorted_logs(str(logs / "access.log*"))
    data = tr.build(paths, {"blankthespire.com"}, today="2026-09-15")
    w = data["windows"]["0"]
    # 1.1.1.1 was splash-only on the 14th and clicked on the 15th: one visitor, counted as clicked.
    assert (w["humans"], w["app"], w["clicked"], w["landing_only"]) == (5, 1, 4, 0)
    assert w["featured"] == 1 and w["workshop"] == 1
    assert w["deck"] == 1 and w["day_count"] == 2 and w["since"] == "2026-09-14"
    refs = {r["source"]: r["visitors"] for r in w["referers"]}
    assert refs == {"google.com": 1, "portfolio.example.net": 1, "com.reddit.frontpage (android app)": 1,
                    "steamcommunity.com": 1}
    pages = {r["path"]: r["visitors"] for r in w["pages"]}
    assert pages["/"] == 4 and pages["/deck/sherman-52"] == 1 and "/api/me" not in pages and "/css/style.css" not in pages
    assert not any(p.startswith("/.well-known") for p in pages)
    assert data["windows"]["7"]["day_count"] == 2
    # A window anchored past the log sees nothing, and reports so rather than crashing.
    empty = tr.Tally({"x"}).window(7, "2026-09-15")
    assert empty["humans"] == 0 and empty["since"] is None and empty["referers"] == []


def test_campaign_key():
    assert tr.campaign_key("/?utm_source=youtube&utm_medium=video-ad&utm_campaign=promo-oct26") == "youtube/promo-oct26"
    assert tr.campaign_key("/app?utm_source=Reddit&utm_campaign=sts2") == "reddit/sts2"
    assert tr.campaign_key("/?utm_source=youtube") == "youtube"
    assert tr.campaign_key("/?utm_campaign=promo") is None   # no source, no attribution
    assert tr.campaign_key("/?gclid=abc") is None and tr.campaign_key("/") is None
    assert tr.campaign_key("/?utm_source=") is None


def test_tagged_links_show_clicks_visitors_and_depth(logs):
    paths = tr._sorted_logs(str(logs / "access.log*"))
    data = tr.build(paths, {"blankthespire.com"}, today="2026-09-15")
    by_day = {r["day"]: r for r in data["daily"]}
    assert by_day["2026-09-15"]["tagged_clicks"] == 3 and by_day["2026-09-14"]["tagged_clicks"] == 0
    camps = {c["campaign"]: c for c in data["windows"]["0"]["campaigns"]}
    # 10.10.10.10 clicked the ad link twice (2 clicks, 1 visitor), got past the splash to /workshop, never
    # signed in; the crawler's hit and the bare gclid never appear
    assert camps["youtube/promo-oct26"] == {"campaign": "youtube/promo-oct26", "clicks": 2, "visitors": 1,
                                            "clicked": 1, "app": 0, "workshop": 1}
    # 3.3.3.3 came in on a tagged /app link and ran the app
    assert camps["reddit/sts2"] == {"campaign": "reddit/sts2", "clicks": 1, "visitors": 1,
                                    "clicked": 1, "app": 1, "workshop": 0}
    assert set(camps) == {"youtube/promo-oct26", "reddit/sts2"}
    # the tag never changes the depth buckets themselves: the tagged splash view is still a splash view
    assert by_day["2026-09-15"]["landing"] == 3
    assert tr.Tally({"x"}).window(7, "2026-09-15")["campaigns"] == []


def test_imports_are_the_mods_art_fetches(logs):
    """A forged code counts as imported when THE MOD fetched the class's art from /static/forged/<id>/:
    the UA-less builds and the "BlankTheSpire/<v>" ones alike, 200s only, the four import assets only.
    A browser on the same URL, a 404, or a per-card PNG is not an import."""
    paths = tr._sorted_logs(str(logs / "access.log*"))
    data = tr.build(paths, {"blankthespire.com"}, today="2026-09-15")
    assert set(data["imports"]) == {"78"}
    rec = data["imports"]["78"]
    assert rec["first"] == "2026-09-15T04:12:00Z" and rec["last"] == "2026-09-15T18:30:00Z"
    assert rec["fetches"] == 5 and rec["imports"] == 2 and rec["players"] == 2
    assert rec["assets"] == ["cards.zip", "relic.png", "splash.png", "sprite.png"]
    assert rec["versions"] == ["0.5.0"]   # the UA-less build contributes no version
    by_day = {r["day"]: r for r in data["daily"]}
    assert (by_day["2026-09-15"]["imports"], by_day["2026-09-15"]["import_fetches"]) == (1, 5)
    assert (by_day["2026-09-14"]["imports"], by_day["2026-09-14"]["import_fetches"]) == (0, 0)
    w = data["windows"]["0"]
    assert w["imports"] == 1 and w["import_fetches"] == 5
    # the mod's fetches stay out of the visitor numbers: no UA is a bot, and /static/ is never a page
    assert w["humans"] == 5 and all(not p["path"].startswith("/static/") for p in w["pages"])


def test_mod_version_from_user_agent():
    assert tr.mod_version("-") == "" and tr.mod_version("") == ""
    assert tr.mod_version("BlankTheSpire/0.5.0") == "0.5.0"
    assert tr.mod_version("BlankTheSpire/0.5.0 (Godot)") == "0.5.0"
    assert tr.mod_version(UA_CHROME) is None and tr.mod_version("python-requests/2.31") is None


def test_cli_writes_json_and_skips_goaccess(logs, tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["traffic_report.py", "--log-glob", str(logs / "access.log*"),
                                      "--out-dir", str(out), "--no-goaccess"])
    assert tr.main() == 0
    data = json.loads((out / "traffic.json").read_text())
    assert data["goaccess"] is False and data["first_day"] == "2026-09-14" and len(data["daily"]) == 2
    assert not list(out.glob(".traffic.*"))  # the temp file was renamed away
    assert "traffic.json: 2 days" in capsys.readouterr().out


def test_cli_no_logs_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["traffic_report.py", "--log-glob", str(tmp_path / "nope*"),
                                      "--out-dir", str(tmp_path / "o"), "--no-goaccess"])
    assert tr.main() == 1


def test_goaccess_missing_is_a_soft_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(tr.shutil, "which", lambda _: None)
    assert tr.run_goaccess([], tmp_path / "g.html", "t") is False
    assert not (tmp_path / "g.html").exists()


# --- the routes ----------------------------------------------------------------------------------------

def _traffic_dir(app_module) -> Path:
    d = app_module.TRAFFIC_DIR
    d.mkdir(parents=True, exist_ok=True)
    for f in d.iterdir():
        f.unlink()
    return d


def test_non_admin_is_forbidden(client, app_module):
    _traffic_dir(app_module)
    login(client, "nobody@example.com")
    assert client.get("/api/admin/traffic").status_code == 403
    assert client.get("/admin/traffic").status_code == 403


def test_signed_out(client):
    client.post("/logout", headers=H)
    assert client.get("/api/admin/traffic").status_code == 401
    r = client.get("/admin/traffic")
    assert r.status_code == 302 and r.headers["Location"].endswith("/")


def test_no_summary_yet_is_not_an_error(client, app_module):
    _traffic_dir(app_module)
    login(client, ADMIN)
    r = client.get("/api/admin/traffic")
    assert r.status_code == 200 and r.get_json()["available"] is False
    assert "timer" in r.get_json()["reason"]
    assert client.get("/admin/traffic").status_code == 404


def test_summary_and_report_are_served_to_admin(client, app_module):
    d = _traffic_dir(app_module)
    (d / "traffic.json").write_text(json.dumps({"daily": [], "windows": {"7": {"humans": 3}}}))
    login(client, ADMIN)
    body = client.get("/api/admin/traffic").get_json()
    assert body["available"] is True and body["report"] is False and body["windows"]["7"]["humans"] == 3

    (d / "goaccess.html").write_text("<html><script>var x=1</script>report</html>")
    assert client.get("/api/admin/traffic").get_json()["report"] is True
    r = client.get("/admin/traffic")
    assert r.status_code == 200 and b"report" in r.data
    csp = r.headers["Content-Security-Policy"]
    # GoAccess's inline script must run, but nothing may leave the page.
    assert "script-src 'unsafe-inline'" in csp and "connect-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert r.headers["Cache-Control"] == "no-store"
    # The site-wide policy still applies everywhere else.
    assert "script-src 'self'" in client.get("/").headers["Content-Security-Policy"]


def test_unreadable_summary_is_a_500(client, app_module):
    d = _traffic_dir(app_module)
    (d / "traffic.json").write_text("{not json")
    login(client, ADMIN)
    r = client.get("/api/admin/traffic")
    assert r.status_code == 500 and r.get_json()["available"] is False
