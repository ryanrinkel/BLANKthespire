"""Summarise the nginx access log into the traffic numbers the operator dashboard shows.

There is no analytics script on blankthespire.com; the only visitor record is nginx's access log
(/var/log/nginx/access.log, rotated daily, kept ~400 days — see deploy/README + logrotate). This tool
reads every rotation (plain + .gz), classifies each request, and writes:

    <out-dir>/traffic.json     the numbers /api/admin/traffic serves (tiles, daily series, referers, pages)
    <out-dir>/goaccess.html    the full GoAccess report, served admin-only at /admin/traffic (optional)

Run by deploy/btsweb-traffic.timer every 15 minutes as root (the log is www-data:adm 0640). Manual:

    sudo python3 web/tools/traffic_report.py --out-dir /opt/btsweb/traffic
    python3 web/tools/traffic_report.py --log-glob 'sample/access.log*' --out-dir /tmp/t --no-goaccess

How a visitor is counted (all per UTC day, by client IP, so every number here is a FLOOR):
  * bot          — user agent names a crawler/scanner/HTTP library, is empty, or is a bare "Mozilla/5.0".
                   Everything below skips bots. Scanners that spoof a real browser string still slip
                   through, which is why "landing" alone over-counts and "clicked through" is the honest
                   floor for humans.
  * landing      — GET / answered 200: the public splash.
  * clicked      — a landing visitor who ALSO fetched a page past the splash that day (/login, /app,
                   /help, /download, /deck/…, /terms, /privacy, /auth/…, /api/…).
  * app          — GET /api/me answered 200: only index.html's JS calls it, so this is a real browser
                   running the signed-in app.
  Each (day, ip) lands in exactly ONE depth bucket — app > clicked > landing — so the daily bars stack
  to "humans seen that day" without double counting.
  * deck         — GET /deck/<slug> 200: a shared class page opened (unique IPs).
  * referers     — the referring HOST of a non-bot page hit, minus ourselves, raw IPs / IP-shaped hosts
                   (the droplet's Plesk-era names are scanner noise), and the OAuth return
                   (accounts.google.com is a sign-in bounce, not a source). android-app:// referers keep
                   the package name so the Reddit app shows up as itself.
"""
from __future__ import annotations

import argparse
import glob
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

WINDOWS = (7, 30, 90, 0)   # days; 0 = everything the logs hold. Mirrors ADMIN_STATS_WINDOWS in app.py.
TOP_N = 12

# nginx "combined": ip - user [time] "request" status bytes "referer" "user-agent"
LINE_RE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<day>[^:\]]+):(?P<time>[^\]]+)\] "(?P<req>[^"]*)" (?P<status>\d{3}) \S+ '
    r'"(?P<ref>[^"]*)" "(?P<ua>[^"]*)"')
MONTHS = {m: i for i, m in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}

BOT_UA_RE = re.compile(
    r"bot|crawl|spider|slurp|python|curl|wget|go-http|zgrab|censys|masscan|nmap|headless|nomorevibe|"
    r"scan|httpx|libwww|java/|okhttp|ahrefs|semrush|mj12|dataprovider|facebookexternalhit|"
    r"preview|monitor|uptime|feedfetcher|fetch|http-client|axios|node|dart|ruby|perl|php",
    re.IGNORECASE)
# Pages past the splash. /api covers the app's own calls (a real browser on /app), /auth the OAuth hops.
ENGAGED_RE = re.compile(r"^/(login|app|help|download|deck/|terms|privacy|auth/|api/)")
DECK_RE = re.compile(r"^/deck/[^/?]+$")
# Not pages: our own API/static/auth hops, and anything with a file extension (scanners probing
# /css/style.css, /wp-login.php, /.env… that happened to answer 200 via the SPA fallback).
PAGE_SKIP_RE = re.compile(r"^/(static/|api/|favicon\.ico|healthz|auth/|\.well-known/)|^.*\.[A-Za-z0-9]{1,5}$")
IPISH_HOST_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}(:\d+)?$|\d{1,3}-\d{1,3}-\d{1,3}-\d{1,3}")
REFERER_SKIP_HOSTS = {"accounts.google.com", "localhost"}


def is_bot(ua: str) -> bool:
    ua = ua.strip()
    return not ua or ua == "-" or ua == "Mozilla/5.0" or bool(BOT_UA_RE.search(ua))


def referer_source(ref: str, self_hosts: set[str]) -> str | None:
    """The host (or app package) a page hit came from, or None when it isn't a real outside source."""
    ref = (ref or "").strip()
    if not ref or ref == "-":
        return None
    if ref.startswith("android-app://"):
        pkg = ref[len("android-app://"):].split("/", 1)[0].strip().lower()
        return f"{pkg} (android app)" if pkg else None
    try:
        parts = urlsplit(ref)
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if not host or host in REFERER_SKIP_HOSTS or IPISH_HOST_RE.search(host):
        return None
    if "wp-admin" in parts.path:   # WordPress probes carry a fake referer per target path
        return None
    if host.startswith("www."):
        host = host[4:]
    if host in self_hosts or any(host.endswith("." + h) for h in self_hosts):
        return None
    return host


def _open(path: str):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, "r", encoding="utf-8", errors="replace")


def _day_key(day: str) -> str | None:
    """'28/Sep/2026' -> '2026-09-28'."""
    try:
        d, m, y = day.split("/")
        return f"{int(y):04d}-{MONTHS[m]:02d}-{int(d):02d}"
    except (ValueError, KeyError):
        return None


class Tally:
    """Everything we keep per day while streaming the log; the JSON is derived at the end."""

    def __init__(self, self_hosts: set[str]):
        self.self_hosts = self_hosts
        self.requests: dict[str, int] = defaultdict(int)
        self.bot_requests: dict[str, int] = defaultdict(int)
        self.landing: dict[str, set] = defaultdict(set)
        self.engaged: dict[str, set] = defaultdict(set)
        self.app: dict[str, set] = defaultdict(set)
        self.deck: dict[str, set] = defaultdict(set)
        self.referers: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
        self.pages: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))

    def add(self, line: str) -> None:
        m = LINE_RE.match(line)
        if not m:
            return
        day = _day_key(m.group("day"))
        if day is None:
            return
        ip, status, ua = m.group("ip"), m.group("status"), m.group("ua")
        self.requests[day] += 1
        if is_bot(ua):
            self.bot_requests[day] += 1
            return
        req = m.group("req").split(" ")
        if len(req) < 2:
            return
        method, target = req[0], req[1]
        path = target.split("?", 1)[0]
        if method != "GET" or status != "200":
            return
        if path == "/":
            self.landing[day].add(ip)
        if ENGAGED_RE.match(path):
            self.engaged[day].add(ip)
        if path == "/api/me":
            self.app[day].add(ip)
        if DECK_RE.match(path):
            self.deck[day].add(ip)
        if not PAGE_SKIP_RE.match(path):
            self.pages[day][path].add(ip)
            src = referer_source(m.group("ref"), self.self_hosts)
            if src:
                self.referers[day][src].add(ip)

    # -- output -------------------------------------------------------------------------------------

    def days(self) -> list[str]:
        return sorted(self.requests)

    def _depth(self, day: str) -> tuple[set, set, set]:
        """Exclusive buckets for one day: (app, clicked-but-not-app, landing-only)."""
        app = set(self.app[day])
        clicked = (self.landing[day] & self.engaged[day]) - app
        landing_only = self.landing[day] - self.engaged[day] - app
        return app, clicked, landing_only

    def daily(self) -> list[dict]:
        out = []
        for day in self.days():
            app, clicked, landing_only = self._depth(day)
            out.append({
                "day": day,
                "landing_only": len(landing_only), "clicked": len(clicked), "app": len(app),
                "humans": len(landing_only) + len(clicked) + len(app),
                "landing": len(self.landing[day]),
                "deck": len(self.deck[day]),
                "requests": self.requests[day], "bot_requests": self.bot_requests[day],
            })
        return out

    def window(self, days: int, today: str) -> dict:
        """Unique-IP totals across the last `days` days (0 = all). 'today' anchors the window so a stale
        log still reports the right span."""
        keys = self.days()
        if days:
            cutoff = _shift_day(today, -(days - 1))
            keys = [k for k in keys if k >= cutoff]
        app: set = set(); clicked: set = set(); landing_only: set = set(); deck: set = set()
        refs: dict[str, set] = defaultdict(set)
        pages: dict[str, set] = defaultdict(set)
        requests = bots = 0
        for day in keys:
            a, c, l = self._depth(day)
            app |= a; clicked |= c; landing_only |= l
            deck |= self.deck[day]
            requests += self.requests[day]; bots += self.bot_requests[day]
            for src, ips in self.referers[day].items():
                refs[src] |= ips
            for path, ips in self.pages[day].items():
                pages[path] |= ips
        # An IP that was landing-only on Monday and in the app on Friday counts once, at its deepest.
        clicked -= app
        landing_only -= app | clicked
        return {
            "days": days, "day_count": len(keys),
            "since": keys[0] if keys else None,
            "humans": len(app) + len(clicked) + len(landing_only),
            "app": len(app), "clicked": len(clicked), "landing_only": len(landing_only),
            "deck": len(deck),
            "requests": requests, "bot_requests": bots,
            "referers": [{"source": s, "visitors": len(ips)} for s, ips in
                         sorted(refs.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:TOP_N]],
            "pages": [{"path": p, "visitors": len(ips)} for p, ips in
                      sorted(pages.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:TOP_N]],
        }


def _shift_day(day: str, delta: int) -> str:
    from datetime import date, timedelta
    y, m, d = (int(x) for x in day.split("-"))
    return (date(y, m, d) + timedelta(days=delta)).isoformat()


def build(paths: list[str], self_hosts: set[str], today: str | None = None) -> dict:
    tally = Tally(self_hosts)
    for p in paths:
        with _open(p) as fh:
            for line in fh:
                tally.add(line)
    days = tally.days()
    today = today or (days[-1] if days else datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "log_files": len(paths),
        "first_day": days[0] if days else None,
        "last_day": days[-1] if days else None,
        "daily": tally.daily(),
        "windows": {str(w): tally.window(w, today) for w in WINDOWS},
    }


def run_goaccess(paths: list[str], out_html: Path, title: str) -> bool:
    """Stream every rotation through goaccess into one self-contained HTML report. False when goaccess is
    not installed or fails — the JSON still gets written either way."""
    exe = shutil.which("goaccess")
    if not exe:
        print("goaccess not installed; skipping the HTML report", file=sys.stderr)
        return False
    tmp = out_html.with_suffix(".tmp.html")
    cmd = [exe, "-", "--log-format=COMBINED", "--ignore-crawlers", "--unknowns-as-crawlers",
           "--ignore-status=400", "--ignore-status=404", "--no-query-string",
           "--html-report-title", title, "-o", str(tmp)]
    try:
        with tmp.open("wb"):
            pass
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE)
        assert proc.stdin is not None
        for p in paths:
            with _open(p) as fh:
                for line in fh:
                    proc.stdin.write(line.encode("utf-8", "replace"))
        proc.stdin.close()
        err = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
        if proc.wait() != 0:
            print(f"goaccess failed: {err.strip()[:400]}", file=sys.stderr)
            tmp.unlink(missing_ok=True)
            return False
        os.replace(tmp, out_html)
        return True
    except OSError as e:
        print(f"goaccess failed: {e}", file=sys.stderr)
        tmp.unlink(missing_ok=True)
        return False


def _sorted_logs(pattern: str) -> list[str]:
    """Oldest rotation first (access.log.14.gz … access.log.1, access.log) so goaccess sees time in order."""
    def key(p: str):
        m = re.search(r"\.(\d+)(\.gz)?$", p)
        return -(int(m.group(1)) if m else 0)
    return sorted(glob.glob(pattern), key=key)


def main() -> int:
    ap = argparse.ArgumentParser(description="summarise nginx access logs for the operator dashboard")
    ap.add_argument("--log-glob", default="/var/log/nginx/access.log*")
    ap.add_argument("--out-dir", default="/opt/btsweb/traffic")
    ap.add_argument("--self-host", action="append", default=None,
                    help="our own hostname(s), dropped from referers (default: blankthespire.com)")
    ap.add_argument("--no-goaccess", action="store_true", help="only write traffic.json")
    ap.add_argument("--title", default="blankthespire.com traffic")
    args = ap.parse_args()

    paths = _sorted_logs(args.log_glob)
    if not paths:
        print(f"no log files match {args.log_glob}", file=sys.stderr)
        return 1
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    self_hosts = {h.lower().removeprefix("www.") for h in (args.self_host or ["blankthespire.com"])}

    data = build(paths, self_hosts)
    data["goaccess"] = False if args.no_goaccess else run_goaccess(paths, out_dir / "goaccess.html", args.title)

    # Atomic write: the app may read traffic.json at any moment.
    fd, tmp = tempfile.mkstemp(dir=out_dir, prefix=".traffic.", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))
    os.chmod(tmp, 0o644)
    os.replace(tmp, out_dir / "traffic.json")
    w7 = data["windows"]["7"]
    print(f"traffic.json: {len(data['daily'])} days ({data['first_day']}..{data['last_day']}), "
          f"last 7d humans={w7['humans']} app={w7['app']}; goaccess={data['goaccess']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
