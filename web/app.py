"""The "Forge a Class" website — Flask app reusing btsgen, OAuth sign-in, per-user class library.

Run locally:
    cd web
    BTSWEB_DEV_AUTH=1 uv run --project ../generation python app.py
    # open http://localhost:5000 , click "Dev sign-in", forge with the offline FAKE generator (no key)

Deploy: gunicorn + nginx on a plain Linux host (see DEPLOY-DIGITALOCEAN.md); set the env secrets
({GOOGLE,DISCORD,GITHUB}_CLIENT_ID/SECRET, OLLAMA_API_KEY, BTSWEB_DATABASE_URL, BTSWEB_SECRET_KEY, STRIPE_* — see
DEPLOY-DIGITALOCEAN.md). Pricing: free with your own key; one free token per UTC day; optional donations
(a thank-you token per dollar) — nothing is sold.
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import threading
import time
import urllib.parse
import uuid
from html import escape as html_escape
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, redirect, request, send_from_directory

WEB_DIR = Path(__file__).resolve().parent
if os.environ.get("BTSWEB_NO_DOTENV", "").strip() not in ("1", "true", "yes"):
    load_dotenv(WEB_DIR / ".env")  # local secrets; in prod these come from the service environment
# (BTSWEB_NO_DOTENV=1 keeps the test suite hermetic on a box whose web/.env holds real credentials.)

from auth import current_user, init_auth, is_admin, is_production, is_unlimited, require_login  # noqa: E402
from billing import init_billing  # noqa: E402
from db import db_ping, init_db, session_scope  # noqa: E402
from forge import (ELEMENT_KINDS, VALID_FEEDBACK_CATEGORIES, ForgeError, UsageMeter,  # noqa: E402
                   append_card_feedback, append_element_feedback, forge_to_bundle, list_models)
from models import (ForgeJob, ForgeUsage, ForgedCard, ForgedClass, Purchase, User,  # noqa: E402
                    free_token_available, new_slug, spend_token, unspend_token)

# Splash art (Track 2/3): generated at persist time, written to static/forged/<id>/, served by nginx,
# its URL embedded in the import code so the mod can fetch it. Backend is chosen by BTSGEN_IMAGE_BACKEND
# (unset -> 'null' = no splash; 'procedural' = a free placeholder). Image gen never blocks a forge, and
# btsgen.art is imported LAZILY (in _generate_splash) so a missing/broken art module can't stop app boot.

# Absolute base for asset URLs that travel OUTSIDE a request (embedded in the import code, read by the
# mod). nginx serves /static/forged/ straight from disk; override per env (local: http://localhost:5000).
PUBLIC_BASE_URL = os.environ.get("BTSWEB_PUBLIC_URL", "https://blankthespire.com").rstrip("/")
STATIC_FORGED_DIR = WEB_DIR / "static" / "forged"  # gitignored (like static/releases); survives git-pull deploys

app = Flask(__name__, static_folder=str(WEB_DIR / "static"), static_url_path="/static")

# Session-signing key. Fail closed: when a sign-in provider is configured (a production-looking deploy), a
# missing key means anyone could forge session cookies with the public default — refuse to boot instead. The
# insecure default survives only for keyless local dev (dev-login + fake forges, no real accounts).
_secret_key = os.environ.get("BTSWEB_SECRET_KEY", "").strip()
if not _secret_key:
    if is_production():
        raise RuntimeError("BTSWEB_SECRET_KEY must be set when sign-in is configured — refusing to "
                           "boot with the insecure default session key.")
    _secret_key = "dev-insecure-change-me"
app.secret_key = _secret_key
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Behind nginx (prod): honor X-Forwarded-Proto/Host so OAuth builds the correct https callback URL.
# No-op locally (the headers aren't present without a proxy).
if os.environ.get("BTSWEB_BEHIND_PROXY", "").strip() in ("1", "true", "yes"):
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Mark the session cookie Secure ONLY once HTTPS is actually serving (set this after certbot). Over plain
# HTTP — e.g. IP-only before a domain/TLS — a Secure cookie is never sent, so sessions would silently break.
SECURE_COOKIES = os.environ.get("BTSWEB_SECURE_COOKIES", "").strip() in ("1", "true", "yes")
if SECURE_COOKIES:
    app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True

# Request bodies are small JSON (a concept sentence, a BYOK key, a feedback note) — 256 KB is generous.
# Anything bigger is a mistake or an attack; werkzeug answers 413 before the view runs.
app.config["MAX_CONTENT_LENGTH"] = 256 * 1024

# BYOK keys live in the browser's localStorage, so a DOM XSS here is API-key theft. The CSP allows only our own
# scripts/styles (style attributes need 'unsafe-inline'; there are no inline <script>s). Art is same-origin
# (data: for any inlined placeholder). No framing, no form posts elsewhere.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; "
    "font-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; "
    "form-action 'self'")


@app.after_request
def _security_headers(resp):
    h = resp.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
    h.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
    if SECURE_COOKIES:  # only once TLS is really serving, or an http-only staging box locks itself out
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return resp


# CSRF: every mutating /api/* call must carry `X-Requested-With: fetch`. A cross-site HTML form can't set a
# custom header, and cross-origin fetch() would need a CORS preflight we never answer — so the header proves
# the request came from our own page's JS (app.js patches fetch() to add it). SameSite=Lax on the session
# cookie is the first line; this is the second. The Stripe webhook isn't under /api/ (its signature IS its auth).
CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "fetch"


@app.before_request
def _csrf_guard():
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.path.startswith("/api/"):
        if request.headers.get(CSRF_HEADER, "") != CSRF_VALUE:
            return jsonify({"error": "missing X-Requested-With header (cross-site request blocked)"}), 403
    return None


# Error reporting: forge failures used to vanish into journald. With SENTRY_DSN set (and sentry-sdk installed),
# unhandled exceptions and the worker threads' logged warnings/errors reach Sentry; without it, nothing changes.
_sentry_dsn = os.environ.get("SENTRY_DSN", "").strip()
if _sentry_dsn:
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=_sentry_dsn, traces_sample_rate=0.0, send_default_pii=False,
                        environment=os.environ.get("BTSWEB_ENV", "production"))
    except ImportError:
        app.logger.warning("SENTRY_DSN is set but sentry-sdk is not installed (pip install 'sentry-sdk[flask]')")

init_db()
init_auth(app)
init_billing(app)
# (forge-job reconciliation runs below, once the settle helpers are defined — see _reconcile_forge_jobs.)


# --- hosted-path guardrails: per-IP daily cap on FREE forges + a global daily kill-switch -------------

class FreeForgeLimiter:
    """Abuse backstop for the token path, which spends OUR provider budget.

    Per IP, per UTC day, at most `ip_daily_cap` forges may be paid for with the FREE daily token — the obvious
    abuse is a farm of throwaway Google accounts behind one address, each claiming its free forge. Paid tokens
    (starter + thank-you) are not IP-capped (a household of donors should never hit it). On top, `daily_cap` is a global
    kill-switch on ALL token-path forges (free or paid) so a runaway day can't run up the bill; 0 disables
    either limit. Process-local, like forge admission — keep gunicorn at one worker.
    """

    def __init__(self, ip_daily_cap: int = 5, daily_cap: int = 1000) -> None:
        self.ip_daily_cap = ip_daily_cap
        self.daily_cap = daily_cap
        self._day = -1
        self._day_count = 0
        self._ip_counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def _roll(self, now: float) -> None:
        day = int(now // 86400)
        if day != self._day:
            self._day, self._day_count, self._ip_counts = day, 0, {}

    def check(self, ip: str, *, free: bool) -> str | None:
        """Admit one token-path forge from `ip` (`free` = paid with the daily free token), counting it. Returns
        an error string if a cap is hit (nothing counted), else None."""
        now = time.time()
        with self._lock:
            self._roll(now)
            if self.daily_cap > 0 and self._day_count >= self.daily_cap:
                return "the hosted forge has hit its daily limit — bring your own API key to keep forging today."
            if free and self.ip_daily_cap > 0 and self._ip_counts.get(ip, 0) >= self.ip_daily_cap:
                return ("this network has used its free forges for today — bring your own API "
                        "key to keep forging.")
            self._day_count += 1
            if free:
                self._ip_counts[ip] = self._ip_counts.get(ip, 0) + 1
            return None

    def uncount(self, ip: str, *, free: bool) -> None:
        """Undo a check() that admitted a forge which never ran (e.g. the token reserve failed after it)."""
        with self._lock:
            self._roll(time.time())
            self._day_count = max(0, self._day_count - 1)
            if free and ip in self._ip_counts:
                self._ip_counts[ip] = max(0, self._ip_counts[ip] - 1)


free_limiter = FreeForgeLimiter(
    ip_daily_cap=int(os.environ.get("BTSWEB_FREE_IP_DAILY_CAP", "5")),
    daily_cap=int(os.environ.get("BTSWEB_TOKEN_DAILY_CAP", os.environ.get("BTSWEB_HOSTED_DAILY_CAP", "1000"))),
)


def _client_ip() -> str:
    return request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()


# --- forge admission control: bounded concurrency + a FIFO wait line -----------------------------
# Each in-flight forge holds one gunicorn thread (its SSE stream) plus a daemon worker thread, and
# burns provider capacity — unbounded simultaneous forges would starve page loads and trip provider
# rate limits in a traffic spike. Admission is process-local (like HostedLimiter — revisit both
# before going multi-worker): at most FORGE_MAX_CONCURRENT forges run at once, the next
# FORGE_MAX_QUEUE wait in line (their SSE stream shows live queue position), and beyond that
# /api/forge-class turns the forge away up front, BEFORE any token is reserved.
FORGE_MAX_CONCURRENT = int(os.environ.get("BTSWEB_FORGE_MAX_CONCURRENT", "3"))
FORGE_MAX_QUEUE = int(os.environ.get("BTSWEB_FORGE_MAX_QUEUE", "12"))
FORGE_QUEUE_TIMEOUT_S = int(os.environ.get("BTSWEB_FORGE_QUEUE_TIMEOUT_S", "1800"))
# Wall-clock cap on a RUNNING forge. Past it the job is settled as failed (token refunded, user slot freed)
# and the stream told; the worker thread finishes on its own and, if it succeeds late, still saves the class.
FORGE_MAX_SECONDS = float(os.environ.get("BTSWEB_FORGE_MAX_SECONDS", "1200"))

_forge_admit_lock = threading.Lock()
_forge_running = 0
# Two FIFO lines, served token-first: paying (token-path) forges never wait behind free BYOK forges. Each entry
# is one queued forge's turn signal.
_forge_waiting_token: list[threading.Event] = []
_forge_waiting_byok: list[threading.Event] = []
_forge_priority: dict[int, bool] = {}  # id(ticket) -> in the token line?


def _waiting_total() -> int:
    return len(_forge_waiting_token) + len(_forge_waiting_byok)


def _forge_enqueue(priority: bool = False) -> threading.Event:
    """Join the forge line (`priority` = the token line, dequeued first). The returned Event is set once this
    forge may run (immediately when a slot is free and nobody is ahead). Once it IS set, the holder owes
    exactly one _forge_release()."""
    global _forge_running
    ticket = threading.Event()
    with _forge_admit_lock:
        if _forge_running < FORGE_MAX_CONCURRENT and not _waiting_total():
            _forge_running += 1
            ticket.set()
        else:
            (_forge_waiting_token if priority else _forge_waiting_byok).append(ticket)
            _forge_priority[id(ticket)] = priority
    return ticket


def _forge_abandon(ticket: threading.Event) -> bool:
    """Leave the line (queue-wait timeout). True = removed while still queued (no release owed);
    False = a slot was granted concurrently, so the caller now owes a _forge_release()."""
    with _forge_admit_lock:
        for line in (_forge_waiting_token, _forge_waiting_byok):
            if ticket in line:
                line.remove(ticket)
                _forge_priority.pop(id(ticket), None)
                return True
    return False


def _forge_release() -> None:
    """Free a slot: hand it straight to the head of the token line, else the BYOK line (running count
    unchanged), or if nobody waits, decrement the running count."""
    global _forge_running
    with _forge_admit_lock:
        if _forge_waiting_token:
            t = _forge_waiting_token.pop(0)
        elif _forge_waiting_byok:
            t = _forge_waiting_byok.pop(0)
        else:
            _forge_running -= 1
            return
        _forge_priority.pop(id(t), None)
        t.set()


def _forge_position(ticket: threading.Event) -> int:
    """1-based place in the overall wait line (token line first); 0 = not queued (running/granted)."""
    with _forge_admit_lock:
        if ticket in _forge_waiting_token:
            return _forge_waiting_token.index(ticket) + 1
        if ticket in _forge_waiting_byok:
            return len(_forge_waiting_token) + _forge_waiting_byok.index(ticket) + 1
        return 0


# Per-user concurrency: ONE forge (running or queued) per account across all modes. Without it, one BYOK user
# on a slow endpoint can hold every forge slot. Entries carry their start time so a forge whose worker never
# ran (client vanished before the stream started) can't lock the account forever.
_user_active: dict[int, float] = {}
_user_active_lock = threading.Lock()
USER_ACTIVE_STALE_S = FORGE_QUEUE_TIMEOUT_S + 900


def _user_begin(user_id: int) -> bool:
    """Claim the user's single forge slot. False if they already have a forge in flight."""
    now = time.time()
    with _user_active_lock:
        started = _user_active.get(user_id)
        if started is not None and now - started < USER_ACTIVE_STALE_S:
            return False
        _user_active[user_id] = now
        return True


def _user_end(user_id: int) -> None:
    with _user_active_lock:
        _user_active.pop(user_id, None)


# The hosted path on our ANTHROPIC key (`mode=hosted`) is retired: it is no longer reachable by any request
# (it used to be an allowlisted invite path, but a hand-crafted POST could still aim Opus-class spend at our
# key). The public paths are the token forge (our Ollama mix) and BYOK.

# --- pages --------------------------------------------------------------------------------------

@app.route("/")
def index():
    """Public splash (the split-flap landing). Continue → /login → the app."""
    return send_from_directory(app.static_folder, "landing.html")


@app.route("/app")
def app_view():
    """The Forge a Class single-page app. Auth-gated server-side: unauthenticated users are bounced
    back to the splash to sign in, so the forge screen is never served without a session."""
    if current_user() is None:
        return redirect("/")
    return send_from_directory(app.static_folder, "index.html")


# Where the mod actually comes from. The Workshop listing is the headline install path (subscribers get
# BaseLib automatically as a Workshop dependency); until the item itself is uploaded this points at the
# game's Workshop hub, so override it with the item URL the first upload mints.
WORKSHOP_URL = os.environ.get(
    "BTSWEB_WORKSHOP_URL", "https://steamcommunity.com/app/2868840/workshop/").strip()
GITHUB_URL = "https://github.com/ryanrinkel/BLANKthespire"


def mod_version() -> str:
    """The current mod version, read from the mod manifest (mod/BlankTheSpire.json) so the download page and
    the release zip name can't drift from what was actually built. Falls back to the newest release zip on disk,
    then to a placeholder."""
    try:
        with open(_REPO_ROOT / "mod" / "BlankTheSpire.json", encoding="utf-8-sig") as f:
            v = str(json.load(f).get("version") or "").strip()
        if v:
            return v if v.startswith("v") else f"v{v}"
    except (OSError, ValueError):
        pass
    zips = sorted((WEB_DIR / "static" / "releases").glob("BlankTheSpire-v*.zip"))
    if zips:
        return zips[-1].stem.split("-", 1)[1]
    return "v0.0.0"


_REPO_ROOT = WEB_DIR.parent


@app.route("/download")
def download():
    """Public install + download page (no login). The release zip lives under static/releases/; the version
    is stamped from the mod manifest at request time (the page is a tiny template with one placeholder)."""
    page = (WEB_DIR / "static" / "download.html").read_text(encoding="utf-8")
    page = (page.replace("{{VERSION}}", mod_version())
                .replace("{{WORKSHOP_URL}}", WORKSHOP_URL)
                .replace("{{GITHUB_URL}}", GITHUB_URL))
    return Response(page, mimetype="text/html")


@app.route("/help")
def help_page():
    """Public "where do I paste my code?" walkthrough (no login) — the page every in-game step links to."""
    return send_from_directory(app.static_folder, "help.html")


@app.route("/terms")
def terms():
    """Public Terms of Service (incl. the refund policy Stripe Checkout links to)."""
    return send_from_directory(app.static_folder, "terms.html")


@app.route("/privacy")
def privacy():
    """Public privacy policy — what we store (and what we deliberately don't, e.g. BYOK keys)."""
    return send_from_directory(app.static_folder, "privacy.html")


# A forged class can only be played by importing its code, so a shared link has to SHOW the code. /deck/<slug>
# is that link: the public, read-only twin of the result view, rendered client-side by render.js off
# /api/deck/<slug>, with the Open Graph tags stamped in server-side so the unfurl on Discord/X/Reddit shows
# the class name, blurb and splash art. No login, no owner data — only what /api/deck already exposes.

_DECK_404_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Class not found — BLANK the spire</title>
<link rel="stylesheet" href="/static/style.css" /></head>
<body><main><section class="card"><h1>Class not found</h1>
<p class="muted">This class link is no longer valid — it may have been deleted, or the link was mistyped.</p>
<p><a class="btn primary" href="/app">Forge your own</a> <a class="btn" href="/download">Get the mod</a></p>
</section></main></body></html>"""

DECK_DESC_MAX = 200  # og:description is truncated by every crawler anyway; keep the unfurl tight


@app.route("/deck/<slug>")
def deck_page(slug: str):
    """Public share page for one forged class: its identity, cards and — the whole point — its import code.
    Same slug validation as /api/deck/<slug> (the JSON this page fetches); a miss renders a small 404 page
    instead of JSON because a human (or a crawler) is on the other end."""
    slug = (slug or "").strip()
    if not slug or len(slug) > 32:
        return Response(_DECK_404_HTML, mimetype="text/html", status=404)
    with session_scope() as s:
        cls = s.query(ForgedClass).filter_by(slug=slug).one_or_none()
        if cls is None:
            return Response(_DECK_404_HTML, mimetype="text/html", status=404)
        character = cls.detail().get("character") or {}
        title = str(character.get("name") or cls.name or "A forged class").strip()
        desc = str(character.get("description") or cls.concept or "").strip()
        image = _splash_url(cls.id, cls.splash_hash) if cls.splash_hash else ""
    if len(desc) > DECK_DESC_MAX:
        desc = desc[:DECK_DESC_MAX - 1].rstrip() + "…"
    page = (WEB_DIR / "static" / "deck.html").read_text(encoding="utf-8")
    # Every value lands inside an HTML attribute (og:*/twitter:*) or text node — escape with quote=True so a
    # class named `" onload=` can't break out of the meta tag it is stamped into.
    for key, value in (("{{TITLE}}", title), ("{{DESC}}", desc), ("{{IMAGE}}", image),
                       ("{{URL}}", f"{PUBLIC_BASE_URL}/deck/{slug}"), ("{{SLUG}}", slug)):
        page = page.replace(key, html_escape(value, quote=True))
    return Response(page, mimetype="text/html")


@app.route("/healthz")
def healthz():
    """Liveness + readiness for the uptime monitor and deploy.sh: a DB round-trip plus forge queue depth.
    503 when the database is unreachable (nginx keeps serving static, but forging and sign-in are down)."""
    ok = db_ping()
    with _forge_admit_lock:
        running, waiting = _forge_running, _waiting_total()
    body = {"ok": ok, "db": ok, "forge_running": running, "forge_waiting": waiting,
            "forge_max_concurrent": FORGE_MAX_CONCURRENT}
    return jsonify(body), (200 if ok else 503)


# --- forge (SSE stream over POST; BYOK key stays in the body, never a URL) -----------------------

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# --- interactive forge mode: the mid-forge archetype-pick round-trip ------------------------------
# SSE is one-way, so the player's answer arrives on a SECOND request (/api/forge/answer) and meets the
# blocked forge worker here: an in-process registry of pending choices keyed by forge id. Safe because
# gunicorn runs ONE gthread worker (deploy/gunicorn.conf.py) — both requests land in the same process;
# if workers ever goes >1 this needs a shared store or sticky routing.
# The wait ALWAYS resolves: answer -> the player's picks; timeout -> [] (the forge decides). A charged
# token can never hang on a player who walked away.
CHOICE_TIMEOUT_S = int(os.environ.get("BTSWEB_CHOICE_TIMEOUT_S", "120"))
_pending_choices: dict[str, dict] = {}
_choices_lock = threading.Lock()


def _art_url(class_id: int, kind: str, digest: str | None = None) -> str:
    """Absolute, public URL of a class's generated art file — kind is 'splash' or 'sprite' (nginx
    serves it directly). The hash rides as a cache-bust query so a regenerated file isn't served stale."""
    url = f"{PUBLIC_BASE_URL}/static/forged/{class_id}/{kind}.png"
    return f"{url}?v={digest[:8]}" if digest else url


def _splash_url(class_id: int, splash_hash: str | None = None) -> str:
    return _art_url(class_id, "splash", splash_hash)


def _sprite_url(class_id: int, sprite_hash: str | None = None) -> str:
    return _art_url(class_id, "sprite", sprite_hash)


def _generate_art(kind: str, class_id: int, out: dict, bundle: dict) -> str | None:
    """Best-effort: render one art asset ('splash' = select-screen background, 'sprite' = the standing
    combat model) to static/forged/<id>/<kind>.png and return its content digest (or None if no backend
    is configured / generation failed). Mutates `bundle` in place to carry `<kind>_url` so the
    re-encoded import code delivers it to the mod. NEVER raises — a forge must succeed even if image
    generation doesn't."""
    try:
        from btsgen.art import class_art_from_bundle, forge_splash, forge_sprite  # lazy: never block app boot
        forge = forge_sprite if kind == "sprite" else forge_splash
        dest = STATIC_FORGED_DIR / str(class_id) / f"{kind}.png"
        res = forge(class_art_from_bundle(out), out_path=dest)  # backend from BTSGEN_IMAGE_BACKEND
        if not (res.ok and res.path):
            return None
        import hashlib
        digest = hashlib.sha256(res.path.read_bytes()).hexdigest()[:16]
        bundle[f"{kind}_url"] = _art_url(class_id, kind, digest)
        return digest
    except Exception as e:  # logged, swallowed — art is cosmetic, the class still ships
        app.logger.warning("%s generation failed for class %s: %s", kind, class_id, e)
        return None


def _generate_relic_icon(class_id: int, out: dict, bundle: dict) -> str | None:
    """Best-effort: the relic call picks an `icon_emoji`; fetch the matching Twemoji asset (no
    image-generation tokens) to static/forged/<id>/relic.png and carry `relic_icon_url` in the bundle
    so the import code delivers it to the mod. NEVER raises."""
    try:
        emoji = str((out.get("relic") or {}).get("icon_emoji") or "").strip()
        if not emoji:
            return None
        from btsgen.art.emoji_icon import fetch_emoji_png  # lazy: never block app boot
        dest = STATIC_FORGED_DIR / str(class_id) / "relic.png"
        if fetch_emoji_png(emoji, dest) is None:
            app.logger.warning("relic icon: no twemoji asset for %r (class %s)", emoji, class_id)
            return None
        import hashlib
        digest = hashlib.sha256(dest.read_bytes()).hexdigest()[:16]
        bundle["relic_icon_url"] = _art_url(class_id, "relic", digest)
        return digest
    except Exception as e:  # logged, swallowed — the icon is cosmetic, the class still ships
        app.logger.warning("relic icon failed for class %s: %s", class_id, e)
        return None


def _persist_class(user_id: int, concept: str, out: dict, forge_meta: dict | None = None) -> dict:
    """Save a forged class (+ denormalized card rows) for the user; return the detail shape. After the
    row gets its id, generate the art (best-effort) and re-encode the import code so it carries the
    splash_url/sprite_url — the harness/forge_to_bundle is never touched. Splash + sprite are two
    independent ~20s cloud calls, so they run concurrently (each writes a distinct bundle key).

    `forge_meta` (interactive forge mode) stamps how the class was made — offered/picked archetypes — into
    bundle_json for the guided-vs-unguided fun experiment. Analysis-only: stripped before encoding the
    import code, so the mod payload is byte-identical to an autonomous forge's."""
    from btsgen.bts1 import VOCAB_VERSION, encode_class
    bundle = {"kind": "class", "character": out["character"], "cards": out["cards"]}
    if out.get("relic"):  # keep the stored bundle in lockstep with the encoded code (which carries the relic)
        bundle["relic"] = out["relic"]
    if forge_meta:
        bundle["forge_meta"] = forge_meta
    if out.get("archetypes"):  # report-only: the archetype cards the class was built around
        bundle["archetypes"] = out["archetypes"]
    # Three short transactions with the art OUTSIDE them: the ~20s art calls used to run inside the
    # insert's open transaction, holding SQLite's ONE write lock the whole time — concurrent forges
    # then died "database is locked" the moment saves overlapped (caught by the 4-forge queue test).
    with session_scope() as s:
        cls = ForgedClass(
            user_id=user_id,
            name=out["character"].get("name", "Forged Class"),
            concept=concept,
            vocab_version=VOCAB_VERSION,
            bundle_json=json.dumps(bundle, separators=(",", ":")),
            code=out["code"],
            slug=new_slug(),
        )
        for i, card in enumerate(out["cards"]):
            cls.cards.append(ForgedCard(card_json=json.dumps(card, separators=(",", ":")), ordinal=i))
        s.add(cls)
        s.flush()  # assigns cls.id, which keys the art paths/URLs
        class_id = cls.id

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_splash = pool.submit(_generate_art, "splash", class_id, out, bundle)
        f_sprite = pool.submit(_generate_art, "sprite", class_id, out, bundle)
        f_relic = pool.submit(_generate_relic_icon, class_id, out, bundle)
        splash_digest, sprite_digest = f_splash.result(), f_sprite.result()
        relic_digest = f_relic.result()

    with session_scope() as s:
        cls = s.query(ForgedClass).filter_by(id=class_id).one_or_none()
        if cls is None:  # deleted mid-art-generation (rare): don't strand the fresh art on disk
            shutil.rmtree(STATIC_FORGED_DIR / str(class_id), ignore_errors=True)
            raise RuntimeError("this class was deleted while its art was still generating")
        cls.splash_hash = splash_digest or cls.splash_hash
        cls.sprite_hash = sprite_digest or cls.sprite_hash
        if splash_digest or sprite_digest or relic_digest:  # art made: re-encode the code so it delivers the URLs
            cls.bundle_json = json.dumps(bundle, separators=(",", ":"))
            # the import code never carries forge_meta/archetypes — the mod payload stays identical to an
            # auto forge's (both are report/analysis data, not game content)
            wire = {k: v for k, v in bundle.items() if k not in ("forge_meta", "archetypes")}
            cls.code = encode_class(json.dumps(wire, separators=(",", ":")))

        detail = cls.detail()
        if splash_digest:
            detail["splash_url"] = _splash_url(cls.id, splash_digest)
        if sprite_digest:
            detail["sprite_url"] = _sprite_url(cls.id, sprite_digest)
        if relic_digest:
            detail["relic_icon_url"] = _art_url(cls.id, "relic", relic_digest)
        return detail


@app.route("/api/models", methods=["POST"])
@require_login
def api_models():
    """Proxy GET {base_url}/models for a BYOK user (browsers can't call OpenAI directly — CORS). The posted
    key is used once here and never stored."""
    body = request.get_json(silent=True) or {}
    try:
        ids = list_models((body.get("base_url") or "").strip(), (body.get("api_key") or "").strip())
    except ForgeError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"models": ids})


def _token_state(u: User) -> dict:
    """What the browser shows: the PAID balance plus whether today's free token is still unspent."""
    return {"token_balance": int(u.token_balance), "free_token_available": free_token_available(u)}


def _reserve_token(user_id: int) -> tuple[str, dict] | None:
    """Atomically spend one token for a hosted forge — the free daily token first, else one paid token — and
    return (kind, token_state). None = nothing to spend (caller 402s). The read + write happen in one
    transaction so two concurrent forges can't both spend the last token."""
    with session_scope() as s:
        u = s.query(User).filter_by(id=user_id).one_or_none()
        if u is None:
            return None
        kind = spend_token(u)
        if kind is None:
            return None
        s.flush()
        return kind, _token_state(u)


def _open_forge_job(forge_id: str, user_id: int, *, mode: str, token_kind: str | None, token_day: str,
                    concept: str) -> None:
    with session_scope() as s:
        s.add(ForgeJob(id=forge_id, user_id=user_id, mode=mode, token_kind=token_kind, token_day=token_day,
                       concept=concept[:2000], status="running"))


def _settle_forge_job(forge_id: str, *, ok: bool, class_id: int | None = None,
                      error: str = "") -> tuple[bool, dict | None]:
    """Move a job from running to done/failed EXACTLY ONCE, and on failure refund the reserved token in the
    same transaction. The guarded UPDATE (status='running') is what makes the worker, the wall-clock watchdog
    and boot reconciliation safe to race: only the caller whose UPDATE hit a row owns the transition.
    Returns (transitioned, token_state-after-refund or None)."""
    from datetime import datetime, timezone
    with session_scope() as s:
        n = (s.query(ForgeJob)
             .filter(ForgeJob.id == forge_id, ForgeJob.status == "running")
             .update({"status": "done" if ok else "failed", "class_id": class_id, "error": (error or "")[:500],
                      "finished_at": datetime.now(timezone.utc).replace(tzinfo=None)},
                     synchronize_session=False))
        if not n:
            return False, None
        state = None
        if not ok:
            job = s.query(ForgeJob).filter_by(id=forge_id).one()
            if job.token_kind in ("free", "paid"):
                u = s.query(User).filter_by(id=job.user_id).one_or_none()
                if u is not None:
                    unspend_token(u, job.token_kind, job.token_day or "")
                    job.refunded = 1
                    s.flush()
                    state = _token_state(u)
        return True, state


def _reconcile_forge_jobs() -> int:
    """Boot-time sweep: any job still 'running' died with the previous process (a deploy restart mid-forge).
    Settle each as failed, which refunds its token. Returns the number reconciled."""
    with session_scope() as s:
        ids = [j.id for j in s.query(ForgeJob).filter_by(status="running").all()]
    n = 0
    for fid in ids:
        done, _ = _settle_forge_job(fid, ok=False, error="the server restarted mid-forge — token refunded")
        n += int(done)
    if n:
        app.logger.warning("reconciled %d forge job(s) left running by a restart (tokens refunded)", n)
    return n


# Estimated provider prices in USD per MILLION tokens: (input, output, cache-read). Only the token path is our
# cost; models on the Ollama flat plan are 0 until the plan's ceiling, OpenRouter overflow slugs carry the plan's
# glm-5.2 rates. Override/extend with BTSWEB_MODEL_PRICES='{"model": [in, out, cached], ...}'. Unknown model
# => est_cost NULL (recorded, not priced).
MODEL_PRICES: dict[str, tuple[float, float, float]] = {
    "gemma4:31b": (0.0, 0.0, 0.0),
    "glm-5.2": (0.0, 0.0, 0.0),
    "z-ai/glm-5.2": (0.49, 1.56, 0.09),
    "google/gemma-4-31b-it": (0.10, 0.30, 0.0),
}
try:
    MODEL_PRICES.update({k: tuple(float(x) for x in v)  # type: ignore[misc]
                         for k, v in json.loads(os.environ.get("BTSWEB_MODEL_PRICES", "{}")).items()})
except (ValueError, TypeError, AttributeError):
    pass


def _record_usage(meter: UsageMeter, *, user_id: int, forge_id: str, mode: str, token_kind: str | None,
                  class_id: int | None, ok: bool, provider: str = "") -> None:
    """Write one forge_usage row per (role, model) the forge touched. `provider` is WHERE the calls went
    ("hosted" / "anthropic" / a BYOK hostname — never the key). Best-effort: never raises (telemetry must
    not break a forge that already succeeded)."""
    try:
        rows = meter.rows()
        if not rows:
            return
        with session_scope() as s:
            for r in rows:
                cost = None
                if mode == "token":
                    price = MODEL_PRICES.get(r["model"])
                    if price is not None:
                        uncached = max(0, r["input_tokens"] - r["cached_tokens"])
                        usd = (uncached * price[0] + r["output_tokens"] * price[1]
                               + r["cached_tokens"] * price[2]) / 1_000_000
                        cost = int(round(usd * 1_000_000))
                s.add(ForgeUsage(user_id=user_id, class_id=class_id, forge_id=forge_id, mode=mode,
                                 provider=provider or "",
                                 token_kind=token_kind, role=r["role"], model=r["model"], calls=r["calls"],
                                 input_tokens=r["input_tokens"], output_tokens=r["output_tokens"],
                                 cached_tokens=r["cached_tokens"], est_cost_micros=cost, ok=1 if ok else 0))
    except Exception as e:  # noqa: BLE001
        app.logger.warning("forge_usage write failed (forge %s): %s", forge_id, e)


@app.route("/api/forge-class", methods=["POST"])
@require_login
def forge_class_route():
    user = current_user()
    body = request.get_json(silent=True) or {}
    concept = (body.get("concept") or "").strip()
    mode = body.get("mode", "byok")  # 'byok' (OpenAI-compat) | 'anthropic' (BYOK) | 'hosted' | 'fake'
    pool_per = int(body.get("pool_per_archetype", 4) or 4)
    # Interactive forge mode: pause mid-forge for the player's archetype pick. Off = the autonomous
    # behavior, untouched.
    interactive = bool(body.get("interactive", False))
    # Triad (the DEFAULT since 2026-08-17): forge a three-archetype class (tension triangle). The UI sends
    # triad=false for the "Classic pair" opt-out.
    triad = bool(body.get("triad", True))
    # The web forge ALWAYS runs the staged creative front-end (cloud -> cluster -> map -> compose ->
    # relic-intent). The one-shot blueprint path lives on only in the CLI: it has no triad prompt and no
    # interactive checkpoint, so there is nothing for the site to opt out to — the request body is not
    # consulted for `staged` at all.
    staged = True

    # BYOK keys (OpenAI-compat or Anthropic) ride in the body, used once, never persisted.
    key = None
    if mode == "byok":
        key = body.get("key")
    elif mode == "anthropic":
        k = body.get("key") or {}
        key = {"provider": "anthropic",
               "api_key": (k.get("api_key") or "").strip(),
               "model": (k.get("model") or "").strip()}

    if not concept:
        return jsonify({"error": "describe a class first."}), 400

    if mode == "hosted":  # retired: never spend our Anthropic key on a hand-crafted POST
        return jsonify({"error": "the hosted Anthropic path is retired — use a token or bring your own "
                                 "API key."}), 410
    if mode not in ("token", "byok", "anthropic", "fake"):
        return jsonify({"error": "unknown forge mode."}), 400
    if mode == "fake" and not os.environ.get("BTSWEB_DEV_AUTH", "").strip() in ("1", "true", "yes"):
        return jsonify({"error": "the offline demo forge is dev-only."}), 403

    fake = mode == "fake"
    hosted = False
    model = None

    # Full line ⇒ turn the forge away NOW, before a token is reserved (soft cap: a race past it just
    # means one extra spot in line, never a lost token).
    with _forge_admit_lock:
        line_len = _waiting_total()
    if line_len >= FORGE_MAX_QUEUE:
        return jsonify({"error": "the forge is at full capacity right now — please try again in a few "
                                 "minutes."}), 503

    # One forge per account at a time, across every mode.
    if not _user_begin(user["id"]):
        return jsonify({"error": "you already have a forge in progress — wait for it to finish."}), 429

    # The "Use a token" path forges on our server-side Ollama mixture and spends one of the user's tokens —
    # today's free token first, else a paid one — unless they're on the unlimited master list. Reserve it up
    # front so we can 402 BEFORE streaming; a forge that then fails is refunded by the worker (see finish_failed).
    ollama_mix = mode == "token"
    unlimited = ollama_mix and is_unlimited(user.get("email", ""))
    reserved = False
    token_kind: str | None = "unlimited" if unlimited else None
    token_day = time.strftime("%Y-%m-%d", time.gmtime())
    token_state: dict | None = None
    ip = _client_ip()
    counted_free = False
    if ollama_mix and not unlimited:
        # Would this forge be paid with the free token? Decide the IP cap on that BEFORE spending anything.
        with session_scope() as s:
            u = s.query(User).filter_by(id=user["id"]).one_or_none()
            would_be_free = bool(u is not None and free_token_available(u))
            has_any = bool(u is not None and (would_be_free or u.token_balance > 0))
        if not has_any:
            _user_end(user["id"])
            return jsonify({"error": "you're out of tokens — your free daily token arrives tomorrow (UTC), "
                                     "or bring your own API key to keep forging.",
                            "token_balance": 0, "free_token_available": False}), 402
        denied = free_limiter.check(ip, free=would_be_free)
        if denied:
            _user_end(user["id"])
            return jsonify({"error": denied}), 429
        counted_free = would_be_free
        res = _reserve_token(user["id"])
        if res is None:  # lost a race for the last token
            free_limiter.uncount(ip, free=would_be_free)
            _user_end(user["id"])
            return jsonify({"error": "you're out of tokens — your free daily token arrives tomorrow (UTC), "
                                     "or bring your own API key to keep forging.",
                            "token_balance": 0, "free_token_available": False}), 402
        token_kind, token_state = res
        reserved = True

    forge_id = uuid.uuid4().hex
    meter = UsageMeter(default_model=(key or {}).get("model", "") if key else "", default_role=mode)
    usage_mode = "byok" if mode in ("byok", "anthropic") else mode
    # WHERE this forge's calls go, for the usage ledger — never WHAT authenticates them (the key is used
    # once, in the worker, and stored nowhere). Our own Ollama mixture is "hosted"; a BYOK OpenAI-compatible
    # endpoint is recorded as the bare hostname of its base_url ("api.openai.com", "openrouter.ai", ...).
    if ollama_mix:
        provider = "hosted"
    elif mode == "anthropic":
        provider = "anthropic"
    elif mode == "byok":
        try:  # a malformed base_url is the worker's ForgeError to raise, not a 500 out of telemetry
            provider = (urllib.parse.urlsplit((key or {}).get("base_url") or "").hostname or "").lower()
        except ValueError:
            provider = ""
    else:
        provider = "fake"
    _open_forge_job(forge_id, user["id"], mode=usage_mode, token_kind=token_kind, token_day=token_day,
                    concept=concept)

    # Everything that MUST happen (save the class, refund the token, record usage) happens on the worker
    # thread via settle()/finish_*(), never in the SSE generator: the generator only runs while the browser is
    # still reading, and a closed tab must not cost anyone a class or a token.
    q: queue.Queue = queue.Queue()
    choice_meta: dict = {}  # what was offered / picked — stamped into the bundle for the fun experiment

    def refund_state(state: dict | None) -> dict:
        """After a refund: un-count the free-forge IP cap and return the balance fields for the browser."""
        if counted_free:
            free_limiter.uncount(ip, free=True)
        return dict(state or {})

    def finish_failed(message: str) -> None:
        """Settle the job as failed (refunding the token if this is the first settlement) and tell the stream."""
        transitioned, state = _settle_forge_job(forge_id, ok=False, error=message)
        data = {"error": message}
        if transitioned and reserved:
            data.update(refund_state(state))
        _record_usage(meter, user_id=user["id"], forge_id=forge_id, mode=usage_mode,
                      token_kind=token_kind, class_id=None, ok=False, provider=provider)
        q.put(("error", data))

    def finish_done(out: dict) -> None:
        """Persist the class, then settle the job as done. A save failure is a failed forge (refund). If the
        job was already settled (wall-clock cap fired), the class is still saved — it's theirs — but nothing
        about tokens changes and the stream has already been told."""
        try:
            forge_meta = None
            if interactive:
                forge_meta = {"interactive": True,
                              "offered_archetypes": choice_meta.get("offered", []),
                              "picked_archetypes": choice_meta.get("picked", []),
                              "answered": choice_meta.get("answered", False)}
            saved = _persist_class(user["id"], concept, out, forge_meta=forge_meta)
        except Exception as e:
            finish_failed(f"forged, but saving failed: {e}")
            return
        transitioned, _ = _settle_forge_job(forge_id, ok=True, class_id=saved.get("id"))
        _record_usage(meter, user_id=user["id"], forge_id=forge_id, mode=usage_mode,
                      token_kind=token_kind, class_id=saved.get("id"), ok=True, provider=provider)
        if not transitioned:
            app.logger.info("forge %s finished after its job was settled — class %s saved late",
                            forge_id, saved.get("id"))
            with session_scope() as s:  # keep the audit trail honest
                s.query(ForgeJob).filter_by(id=forge_id).update({"class_id": saved.get("id")})
        if reserved and token_state:  # tell the browser the new balance so the header updates now
            saved.update(token_state)
        if saved.get("slug"):
            saved["share_url"] = f"{PUBLIC_BASE_URL}/deck/{saved['slug']}"  # the public share page
        # What this one forge consumed, summed across every (role, model). The browser shows it to BYOK
        # users ("this forge used …") so the bill that lands on their own provider is never a surprise.
        # Best-effort like the ledger write: telemetry must never sink a forge that already succeeded.
        try:
            rows = meter.rows()
            saved["usage"] = {k: sum(int(r.get(k) or 0) for r in rows)
                              for k in ("calls", "input_tokens", "cached_tokens", "output_tokens")}
        except Exception as e:  # noqa: BLE001
            app.logger.warning("usage summary failed (forge %s): %s", forge_id, e)
        q.put(("result", saved))

    def on_wall_clock() -> None:
        """Watchdog: the forge has run past FORGE_MAX_SECONDS. Refund now and free the user's slot; the worker
        keeps going and a late success still lands in the library."""
        transitioned, state = _settle_forge_job(
            forge_id, ok=False, error=f"the forge ran past {int(FORGE_MAX_SECONDS)}s and was abandoned")
        if transitioned:
            data = {"error": "this forge is taking far too long — it's been abandoned and your token "
                             "refunded. If it does finish, the class will appear in My Classes."}
            if reserved:
                data.update(refund_state(state))
            _user_end(user["id"])
            q.put(("error", data))

    def archetype_checkpoint(options, dossier) -> list:
        """Runs on the forge worker thread: surface the options as a 'choice' SSE event, then block
        until /api/forge/answer sets the event or the timeout fires (empty picks = the forge decides)."""
        entry = {"event": threading.Event(), "answer": None, "user_id": user["id"]}
        with _choices_lock:
            _pending_choices[forge_id] = entry
        q.put(("choice", {"forge_id": forge_id, "options": options, "timeout_s": CHOICE_TIMEOUT_S}))
        answered = entry["event"].wait(timeout=CHOICE_TIMEOUT_S)
        with _choices_lock:
            _pending_choices.pop(forge_id, None)
        picks = [str(p) for p in (entry["answer"] or [])][:2] if answered else []
        choice_meta.update({"offered": [o.get("id") for o in options], "picked": picks,
                            "answered": bool(answered)})
        return picks

    def on_event(msg: str) -> None:
        q.put(("progress", msg))

    def worker() -> None:
        # Admission: wait for a forge slot, narrating queue position over SSE. (If the player closes the tab
        # while queued, this thread still waits its turn and the forge runs to completion unseen — the class
        # is saved to their library regardless — bounded by the queue timeout.)
        ticket = _forge_enqueue(priority=ollama_mix)
        if not ticket.is_set():
            last_pos = _forge_position(ticket)
            q.put(("progress", f"the forge is busy — you're in line at position {last_pos} "
                               f"(your spot is held, hang tight)…"))
            deadline = time.time() + FORGE_QUEUE_TIMEOUT_S
            while not ticket.wait(timeout=5):
                if time.time() >= deadline:
                    if _forge_abandon(ticket):
                        finish_failed("the forge stayed at capacity too long — nothing was forged (and "
                                      "no token was spent); please try again later.")
                        _user_end(user["id"])
                        return
                    break  # a slot arrived in the same instant — we own it now, proceed
                pos = _forge_position(ticket)
                if pos and pos != last_pos:
                    last_pos = pos
                    q.put(("progress", f"in line: position {pos}…"))
            q.put(("progress", "it's your turn — forging now…"))
        watchdog = threading.Timer(FORGE_MAX_SECONDS, on_wall_clock)
        watchdog.daemon = True
        watchdog.start()
        try:
            out = forge_to_bundle(
                concept, key=key, hosted=hosted, fake=fake, model=model,
                pool_per_archetype=pool_per, staged=staged, ollama_mix=ollama_mix, on_event=on_event,
                archetype_checkpoint=archetype_checkpoint if interactive else None,
                user_id=user["id"], triad=triad, on_usage=meter)
        except ForgeError as e:
            watchdog.cancel()
            finish_failed(str(e))
        except Exception as e:  # never leak a stack trace to the browser
            watchdog.cancel()
            finish_failed(f"unexpected error: {e}")
        else:
            watchdog.cancel()
            finish_done(out)
        finally:
            _forge_release()
            _user_end(user["id"])

    threading.Thread(target=worker, daemon=True).start()

    def stream():
        """Pure observer: relays the worker's events to the browser. Closing the tab closes this generator and
        nothing else — the worker settles the job either way."""

        # Carry the post-reserve balance on the FIRST event so the header chip ticks down the moment the
        # forge starts (the token is already spent server-side); an error event refunds it back visibly.
        first = {"message": "starting… (interactive forge: you'll pick the engines after the map stage)"
                            if interactive else "starting…"}
        if reserved and token_state:
            first.update(token_state)
        yield _sse("progress", first)
        while True:
            try:
                # Timed get + SSE keepalive comments: while the forge waits on the player's pick no progress
                # flows, and an idle stream would otherwise hit nginx's proxy read timeout mid-choice.
                kind, payload = q.get(timeout=15)
            except queue.Empty:
                yield ": keepalive\n\n"
                continue
            if kind == "progress":
                yield _sse("progress", {"message": payload})
            elif kind == "choice":
                yield _sse("choice", payload)
            elif kind == "error":
                yield _sse("error", payload)
                return
            elif kind == "result":
                yield _sse("result", payload)
                return

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return Response(stream(), mimetype="text/event-stream", headers=headers)


@app.route("/api/forge/answer", methods=["POST"])
@require_login
def forge_answer():
    """The return leg of the interactive forge's choice round-trip: the browser posts the player's archetype
    picks (or [] for 'let the forge decide') against the forge_id it got in the 'choice' SSE event, and the
    blocked forge worker wakes up. 404 = nothing pending (already answered, timed out, or bogus id)."""
    user = current_user()
    body = request.get_json(silent=True) or {}
    forge_id = str(body.get("forge_id") or "")
    raw = body.get("archetypes")
    picks = [str(p) for p in raw][:2] if isinstance(raw, list) else []
    with _choices_lock:
        entry = _pending_choices.get(forge_id)
    if entry is None:
        return jsonify({"error": "no pending choice for this forge — it may have already timed out."}), 404
    if entry["user_id"] != user["id"]:
        return jsonify({"error": "this isn't your forge."}), 403
    entry["answer"] = picks
    entry["event"].set()
    return jsonify({"ok": True, "picked": picks})


# --- "what will this cost me?" ------------------------------------------------------------------

# How many recent successful forges the estimate averages over, and what to answer before the ledger has
# any: measured numbers from the staged triad front-end (2026-09), so a brand-new deploy still tells a BYOK
# user roughly what one forge will put on their provider bill.
FORGE_ESTIMATE_SAMPLE = 30
FORGE_ESTIMATE_FALLBACK = {"calls": 53, "input_tokens": 1_370_000,
                           "cached_tokens": 720_000, "output_tokens": 28_000}
_ESTIMATE_FIELDS = ("calls", "input_tokens", "cached_tokens", "output_tokens")


@app.route("/api/forge-estimate")
@require_login
def forge_estimate():
    """Average LLM consumption of one forge, from the last FORGE_ESTIMATE_SAMPLE successful forges in the
    usage ledger (any mode — the staged front-end does the same work whoever pays for it). The BYOK panel
    shows it before the user hands over a key. Falls back to measured constants on an empty ledger."""
    with session_scope() as s:
        rows = (s.query(ForgeUsage.forge_id, ForgeUsage.calls, ForgeUsage.input_tokens,
                        ForgeUsage.cached_tokens, ForgeUsage.output_tokens)
                .filter(ForgeUsage.ok == 1)
                .order_by(ForgeUsage.created_at.desc(), ForgeUsage.id.desc())
                .all())
    # One query, grouped in Python: rows arrive newest-first, so the first FORGE_ESTIMATE_SAMPLE distinct
    # forge_ids are the newest forges — and every row of those forges is summed wherever it turns up.
    per_forge: dict[str, dict] = {}
    for r in rows:
        acc = per_forge.get(r.forge_id)
        if acc is None:
            if len(per_forge) >= FORGE_ESTIMATE_SAMPLE:
                continue
            acc = per_forge[r.forge_id] = dict.fromkeys(_ESTIMATE_FIELDS, 0)
        for f in _ESTIMATE_FIELDS:
            acc[f] += int(getattr(r, f) or 0)
    n = len(per_forge)
    if not n:
        return jsonify({"forges_sampled": 0, **FORGE_ESTIMATE_FALLBACK, "fallback": True})
    avg = {f: int(round(sum(a[f] for a in per_forge.values()) / n)) for f in _ESTIMATE_FIELDS}
    return jsonify({"forges_sampled": n, **avg, "fallback": False})


# --- library CRUD ------------------------------------------------------------------------------

def _owned(s, user_id: int, class_id: int) -> ForgedClass | None:
    return s.query(ForgedClass).filter_by(id=class_id, user_id=user_id).one_or_none()


@app.route("/api/classes")
@require_login
def list_classes():
    user = current_user()
    with session_scope() as s:
        rows = (s.query(ForgedClass)
                .filter_by(user_id=user["id"])
                .order_by(ForgedClass.updated_at.desc())
                .all())
        return jsonify({"classes": [c.summary() for c in rows]})


@app.route("/api/classes/<int:class_id>")
@require_login
def get_class(class_id: int):
    user = current_user()
    with session_scope() as s:
        cls = _owned(s, user["id"], class_id)
        if cls is None:
            return jsonify({"error": "not found"}), 404
        return jsonify(cls.detail())


@app.route("/api/classes/<int:class_id>", methods=["PATCH"])
@require_login
def rename_class(class_id: int):
    user = current_user()
    name = ((request.get_json(silent=True) or {}).get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    with session_scope() as s:
        cls = _owned(s, user["id"], class_id)
        if cls is None:
            return jsonify({"error": "not found"}), 404
        cls.name = name[:255]
        return jsonify(cls.summary())


@app.route("/api/classes/<int:class_id>", methods=["DELETE"])
@require_login
def delete_class(class_id: int):
    user = current_user()
    with session_scope() as s:
        cls = _owned(s, user["id"], class_id)
        if cls is None:
            return jsonify({"error": "not found"}), 404
        s.delete(cls)
    # Row is committed gone — remove the class's generated art (splash/sprite/relic) too, or deleted
    # classes leak ~3MB each forever. After the DB delete so a failed delete never strands a live
    # class without its art; ignore_errors because the dir may never have existed (no image backend).
    shutil.rmtree(STATIC_FORGED_DIR / str(class_id), ignore_errors=True)
    return jsonify({"ok": True})


# --- share resolver (public) -------------------------------------------------------------------------
# Resolve a shared class by its unguessable slug — the foundation for blankthespire.com/deck/<slug> sharing
# and the mod fetching a class's package by key. PUBLIC by design (friends import without an account), so it
# exposes only the playable bundle + art. The numeric id is enumerable and stays internal.

@app.route("/api/deck/<slug>")
def deck_resolve(slug: str):
    slug = (slug or "").strip()
    if not slug or len(slug) > 32:
        return jsonify({"error": "not found"}), 404
    with session_scope() as s:
        cls = s.query(ForgedClass).filter_by(slug=slug).one_or_none()
        if cls is None:
            return jsonify({"error": "not found"}), 404
        detail = cls.detail()
        detail.pop("id", None)  # public shape: never leak the internal enumerable id
        if cls.splash_hash:
            detail["splash_url"] = _splash_url(cls.id, cls.splash_hash)
        if cls.sprite_hash:
            detail["sprite_url"] = _sprite_url(cls.id, cls.sprite_hash)
        return jsonify(detail)


# --- feedback rate limit (free text reaches the generator's prompts) ----------------------------------
FEEDBACK_HOURLY_CAP = int(os.environ.get("BTSWEB_FEEDBACK_HOURLY_CAP", "60"))
_feedback_hits: dict[int, list[float]] = {}
_feedback_lock = threading.Lock()


def _feedback_allowed(user_id: int) -> bool:
    """Sliding one-hour window per user. Notes are capped at 500 chars by the routes below; this caps volume."""
    if FEEDBACK_HOURLY_CAP <= 0:
        return True
    now = time.time()
    with _feedback_lock:
        hits = [t for t in _feedback_hits.get(user_id, []) if now - t < 3600]
        if len(hits) >= FEEDBACK_HOURLY_CAP:
            _feedback_hits[user_id] = hits
            return False
        hits.append(now)
        _feedback_hits[user_id] = hits
        return True


# --- per-card feedback -------------------------------------------------------------------------

@app.route("/api/card-feedback", methods=["POST"])
@require_login
def card_feedback_route():
    """Record one player rating on a forged card. The card is resolved server-side from the user's owned
    class (we never trust the client's card blob), then appended to the JSONL feedback log in the exact
    shape the generator reads back. Best-effort: a logging failure returns an error but never 500s."""
    user = current_user()
    body = request.get_json(silent=True) or {}
    category = (body.get("category") or "").strip()
    card_id = (body.get("card_id") or "").strip()
    note = (body.get("note") or "").strip()[:500]
    try:
        class_id = int(body.get("class_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "class_id is required"}), 400

    if category not in VALID_FEEDBACK_CATEGORIES:
        return jsonify({"error": "unknown feedback category"}), 400
    if not card_id:
        return jsonify({"error": "card_id is required"}), 400
    if not _feedback_allowed(user["id"]):
        return jsonify({"error": "too much feedback too fast — try again in a while."}), 429

    with session_scope() as s:
        cls = _owned(s, user["id"], class_id)
        if cls is None:
            return jsonify({"error": "not found"}), 404
        bundle = json.loads(cls.bundle_json)
        card = next((c for c in bundle.get("cards", []) if c.get("id") == card_id), None)
    if card is None:
        return jsonify({"error": "card not found in class"}), 404

    character = card.get("character") or (bundle.get("character") or {}).get("id", "")
    ok = append_card_feedback(category=category, card=card, character=character, note=note)
    if not ok:
        return jsonify({"error": "could not record feedback"}), 503
    return jsonify({"ok": True})


def _find_element(bundle: dict, kind: str, element_id: str) -> dict | None:
    """Resolve a forged non-card element from a stored bundle (server-side; we never trust the client's blob).
    `kind` is orb|status|summon|relic|potion; `element_id` is the element's name (matched case-insensitively). The
    relic is singular (one per class) so its id is ignored."""
    if kind == "relic":
        relic = bundle.get("relic")
        return relic if isinstance(relic, dict) else None
    character = bundle.get("character") or {}
    pool = character.get({"orb": "orb_pool", "status": "status_pool", "summon": "summon_pool",
                          "potion": "potion_pool"}[kind]) or []
    want = (element_id or "").strip().lower()
    for entry in pool:
        if isinstance(entry, dict) and str(entry.get("name", "")).strip().lower() == want:
            return entry
    return None  # base-orb name strings carry no custom definition, so they're never rateable elements


@app.route("/api/element-feedback", methods=["POST"])
@require_login
def element_feedback_route():
    """Record one player rating on a forged non-card element (custom orb/status/summon/keystone relic). Like
    card feedback, the element is resolved server-side from the user's owned class, then appended to the same
    JSONL log in the shape the generator reads back."""
    user = current_user()
    body = request.get_json(silent=True) or {}
    category = (body.get("category") or "").strip()
    kind = (body.get("element_kind") or "").strip()
    element_id = (body.get("element_id") or "").strip()
    note = (body.get("note") or "").strip()[:500]
    try:
        class_id = int(body.get("class_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "class_id is required"}), 400

    if category not in VALID_FEEDBACK_CATEGORIES:
        return jsonify({"error": "unknown feedback category"}), 400
    if kind not in ELEMENT_KINDS:
        return jsonify({"error": "unknown element kind"}), 400
    if not _feedback_allowed(user["id"]):
        return jsonify({"error": "too much feedback too fast — try again in a while."}), 429

    with session_scope() as s:
        cls = _owned(s, user["id"], class_id)
        if cls is None:
            return jsonify({"error": "not found"}), 404
        bundle = json.loads(cls.bundle_json)
        element = _find_element(bundle, kind, element_id)
    if element is None:
        return jsonify({"error": "element not found in class"}), 404

    character = (bundle.get("character") or {}).get("id", "")
    ok = append_element_feedback(category=category, element_kind=kind, element=element,
                                 character=character, note=note)
    if not ok:
        return jsonify({"error": "could not record feedback"}), 503
    return jsonify({"ok": True})


# --- operator dashboard -------------------------------------------------------------------------

ADMIN_STATS_WINDOWS = (7, 30, 90, 0)   # ?days=...; 0 means all time
ADMIN_STATS_TOP_MODELS = 20


@app.route("/api/admin/stats")
@require_login
def admin_stats():
    """Everything the operator page shows, in one call: forge counts by outcome/mode/token kind, a daily
    series, who forged, what our hosted path consumed (and cost), which models and providers did the work,
    and donations — all over ?days=7|30|90|0 (0 = all time; anything else falls back to 30).

    Windowing is by row CREATION: forge_jobs.started_at (its creation column — a job is inserted the moment
    the token is reserved) and created_at on forge_usage / purchases. `users.accounts` is deliberately NOT
    windowed: it is the size of the whole account table, not a signup count.

    Read-only and admin-gated (auth.ADMIN_EMAILS); no key, address or concept text ever leaves here."""
    user = current_user()
    if not is_admin(user.get("email", "")):
        return jsonify({"error": "forbidden"}), 403
    from datetime import datetime, timedelta, timezone
    try:
        days = int(request.args.get("days", 30))
    except (TypeError, ValueError):
        days = 30
    if days not in ADMIN_STATS_WINDOWS:
        days = 30
    now = datetime.now(timezone.utc).replace(tzinfo=None)   # naive UTC, the one convention for DateTime cols
    since = now - timedelta(days=days) if days else None

    with session_scope() as s:
        jq = s.query(ForgeJob.user_id, ForgeJob.mode, ForgeJob.token_kind, ForgeJob.status,
                     ForgeJob.refunded, ForgeJob.started_at)
        uq = s.query(ForgeUsage.forge_id, ForgeUsage.mode, ForgeUsage.provider, ForgeUsage.model,
                     ForgeUsage.calls, ForgeUsage.input_tokens, ForgeUsage.output_tokens,
                     ForgeUsage.cached_tokens, ForgeUsage.est_cost_micros)
        pq = s.query(Purchase.tokens, Purchase.amount_cents).filter(Purchase.status == "paid")
        if since is not None:
            jq = jq.filter(ForgeJob.started_at >= since)
            uq = uq.filter(ForgeUsage.created_at >= since)
            pq = pq.filter(Purchase.created_at >= since)
        jobs, usage, purchases = jq.all(), uq.all(), pq.all()
        accounts = s.query(User).count()

    by_mode = {"token": 0, "byok": 0, "fake": 0}
    by_token_kind = {"free": 0, "paid": 0, "unlimited": 0}
    daily: dict[str, dict] = {}
    forgers: set[int] = set()
    ok_n = failed_n = refunded_n = 0
    for j in jobs:
        if j.mode in by_mode:
            by_mode[j.mode] += 1
        if j.token_kind in by_token_kind:
            by_token_kind[j.token_kind] += 1
        ok_n += int(j.status == "done")
        failed_n += int(j.status == "failed")
        refunded_n += int(bool(j.refunded))
        forgers.add(j.user_id)
        if j.started_at is not None:
            day = daily.setdefault(j.started_at.strftime("%Y-%m-%d"),
                                   {"day": j.started_at.strftime("%Y-%m-%d"), "token": 0, "byok": 0, "fake": 0})
            if j.mode in day:
                day[j.mode] += 1

    # Hosted = the "Use a token" path: the only rows whose bill is ours. est_cost_usd stays null (rather
    # than 0.0) when NO row carried a price, so "free on the flat plan" and "unpriced model" stay distinct.
    hosted = {"forges": 0, "calls": 0, "input_tokens": 0, "cached_tokens": 0, "output_tokens": 0,
              "est_cost_usd": None}
    hosted_forge_ids: set[str] = set()
    cost_micros, priced = 0, False
    models: dict[tuple, dict] = {}
    providers: dict[str, set] = {}
    for r in usage:
        if r.mode == "token":
            hosted_forge_ids.add(r.forge_id)
            for f in ("calls", "input_tokens", "cached_tokens", "output_tokens"):
                hosted[f] += int(getattr(r, f) or 0)
            if r.est_cost_micros is not None:
                cost_micros += int(r.est_cost_micros)
                priced = True
        key = (r.model or "", r.provider or "", r.mode or "")
        m = models.setdefault(key, {"model": key[0], "provider": key[1], "mode": key[2], "forges": set(),
                                    "calls": 0, "input_tokens": 0, "output_tokens": 0})
        m["forges"].add(r.forge_id)
        for f in ("calls", "input_tokens", "output_tokens"):
            m[f] += int(getattr(r, f) or 0)
        if r.provider:  # rows written before the provider column existed carry "" — nothing to attribute
            providers.setdefault(r.provider, set()).add(r.forge_id)
    hosted["forges"] = len(hosted_forge_ids)
    if priced:
        hosted["est_cost_usd"] = round(cost_micros / 1_000_000, 6)

    model_rows = sorted(({**m, "forges": len(m["forges"])} for m in models.values()),
                        key=lambda d: (-d["forges"], -d["calls"], d["model"]))[:ADMIN_STATS_TOP_MODELS]
    provider_rows = sorted(({"provider": p, "forges": len(ids)} for p, ids in providers.items()),
                           key=lambda d: (-d["forges"], d["provider"]))

    return jsonify({
        "days": days,
        "since": since.strftime("%Y-%m-%d") if since is not None else None,
        "forges": {"total": len(jobs), "ok": ok_n, "failed": failed_n, "refunded": refunded_n,
                   "by_mode": by_mode, "by_token_kind": by_token_kind},
        "users": {"forgers": len(forgers), "accounts": accounts},
        "daily": [daily[k] for k in sorted(daily)],
        "hosted": hosted,
        "models": model_rows,
        "providers": provider_rows,
        "donations": {"count": len(purchases),
                      "amount_cents": sum(int(p.amount_cents or 0) for p in purchases),
                      "tokens": sum(int(p.tokens or 0) for p in purchases)},
    })


# Refund the tokens of any forge the previous process took down with it (deploy restarts).
_reconcile_forge_jobs()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), threaded=True, debug=True)
