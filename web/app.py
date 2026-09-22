"""The "Forge a Class" website — Flask app reusing btsgen, OAuth sign-in, per-user class library.

Run locally:
    cd web
    BTSWEB_DEV_AUTH=1 uv run --project ../generation python app.py
    # open http://localhost:5000 , click "Dev sign-in", forge with the offline FAKE generator (no key)

Deploy: gunicorn + nginx on a plain Linux host (see DEPLOY-DIGITALOCEAN.md); set the env secrets
({GOOGLE,DISCORD,GITHUB}_CLIENT_ID/SECRET, OLLAMA_API_KEY, BTSWEB_DATABASE_URL, BTSWEB_SECRET_KEY, STRIPE_* — see
DEPLOY-DIGITALOCEAN.md). Pricing: forging is free and unlimited with your own API key; a forge on OUR models
spends one token, and tokens arrive only as a thank-you for a fixed-amount donation (billing.DONATION_TIERS).
Nothing is sold, and there are no free tokens of any kind — not a starter grant, not one per day.
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

from auth import (current_user, init_auth, is_admin, is_production, is_unlimited,  # noqa: E402
                  require_login, user_is_unlimited)
from billing import init_billing  # noqa: E402
from db import db_ping, init_db, session_scope  # noqa: E402
from forge import (ELEMENT_KINDS, VALID_FEEDBACK_CATEGORIES, ForgeError, UsageMeter,  # noqa: E402
                   append_card_feedback, append_element_feedback, forge_to_bundle, list_models)
from models import (AdminAction, ForgeJob, ForgeUsage, ForgedCard, ForgedClass, Identity,  # noqa: E402
                    Purchase, User, new_slug, spend_token, unspend_token)

# Generated art (Track 2/3): the class splash, the combat sprite, the relic icon and the per-card portrait
# pack (cards.zip) are all made at persist time, written to static/forged/<id>/, served by nginx, and their
# URLs embedded in the import code so the mod can fetch them. Backend is chosen by BTSGEN_IMAGE_BACKEND
# (unset -> 'null' = no art; 'procedural' = a free placeholder; a comma list is a fallback chain). Image gen
# never blocks a forge, and btsgen.art is imported LAZILY (inside each _generate_* helper) so a missing or
# broken art module can't stop app boot.

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


# --- hosted-path guardrail: a global daily kill-switch on token forges --------------------------------

class TokenForgeLimiter:
    """Budget backstop for the token path, which spends OUR provider budget.

    One cap, `daily_cap`: the most token-path forges this process will admit in a UTC day, so a runaway day
    (a bug, a spike, a donor with a script) can't run up an unbounded bill while nobody is watching. 0
    disables it. BYOK forges are never counted — they cost us nothing. The old per-IP cap on the FREE daily
    token went away with the free token itself (pricing v3): every hosted forge is now paid for with a token
    someone donated for, so throttling by address only punished households. Process-local, like forge
    admission — keep gunicorn at one worker.
    """

    def __init__(self, daily_cap: int = 1000) -> None:
        self.daily_cap = daily_cap
        self._day = -1
        self._day_count = 0
        self._lock = threading.Lock()

    def _roll(self, now: float) -> None:
        day = int(now // 86400)
        if day != self._day:
            self._day, self._day_count = day, 0

    def check(self, ip: str) -> str | None:
        """Admit one token-path forge, counting it. Returns an error string if the day's cap is hit (nothing
        counted), else None. `ip` is accepted for logging symmetry and is not rate-limited on."""
        with self._lock:
            self._roll(time.time())
            if self.daily_cap > 0 and self._day_count >= self.daily_cap:
                return "the hosted forge has hit its daily limit — bring your own API key to keep forging today."
            self._day_count += 1
            return None

    def uncount(self, ip: str) -> None:
        """Undo a check() that admitted a forge which never ran (e.g. the token reserve failed after it)."""
        with self._lock:
            self._roll(time.time())
            self._day_count = max(0, self._day_count - 1)


# Renamed from `free_limiter` with the free token: the old name would now name the wrong thing entirely.
token_limiter = TokenForgeLimiter(
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
# key). The public paths are the token forge (our Ollama mix, OpenRouter failover) and BYOK.
#
# Belt AND braces (2026-09-18): the website holds NO Anthropic credential of its own. BYOK-Anthropic users
# pass their key per request (used once, never stored); token forges never touch Anthropic as primary OR
# fallback. btsgen's AnthropicGenerator falls back to $ANTHROPIC_API_KEY when given no explicit key, so blank
# it in this process — a stray construction then fails loudly instead of billing our account. (load_env()
# only setdefault()s, so a generation/.env can't re-inject it either.)
os.environ["ANTHROPIC_API_KEY"] = ""

# --- pages --------------------------------------------------------------------------------------

@app.route("/")
def index():
    """Public splash (the split-flap landing). Continue → /login → the app."""
    return send_from_directory(app.static_folder, "landing.html")


@app.route("/favicon.ico")
def favicon():
    """Browsers ask for /favicon.ico at the site root regardless of the <link> tags, so serve the real
    multi-size .ico from static/img rather than letting it 404."""
    return send_from_directory(str(WEB_DIR / "static" / "img"), "favicon.ico")


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


# Art kinds whose file is not <kind>.png. 'cards' is the per-card portrait PACK: one zip per class (~34
# PNGs) so the mod's import does ONE download instead of ~34 synchronous ones on its UI thread.
_ART_FILENAMES = {"cards": "cards.zip"}


def _art_url(class_id: int, kind: str, digest: str | None = None) -> str:
    """Absolute, public URL of a class's generated art file — kind is 'splash', 'sprite', 'relic' (a PNG
    each) or 'cards' (the cards.zip pack); nginx serves the whole static/forged tree straight from disk.
    The hash rides as a cache-bust query so a regenerated file isn't served stale."""
    url = f"{PUBLIC_BASE_URL}/static/forged/{class_id}/{_ART_FILENAMES.get(kind, f'{kind}.png')}"
    return f"{url}?v={digest[:8]}" if digest else url


def _splash_url(class_id: int, splash_hash: str | None = None) -> str:
    return _art_url(class_id, "splash", splash_hash)


def _sprite_url(class_id: int, sprite_hash: str | None = None) -> str:
    return _art_url(class_id, "sprite", sprite_hash)


# Image-capable BYOK providers, by the hostname of the base_url the user chose: the art backend that can
# take THEIR key. Everything else (Anthropic, Groq, DeepSeek, Together, Ollama Cloud, a custom endpoint)
# has no image API we drive, so a BYOK forge there ships with BTSWEB_BYOK_ART_FALLBACK art ('null' = none;
# 'procedural' = the free placeholder) — never with art billed to the server's keys.
#
# Gemini's OpenAI shim and xAI joined on 2026-09-20: both answer an OpenAI-shaped POST /images/generations,
# so ONE generic backend (btsgen.art.backends.openai_images.OpenAIImagesBackend) drives both from a preset
# table. Neither meters a cost in the response, so their ledger rows carry the preset's LIST price estimate.
_BYOK_ART_HOSTS = {"openrouter.ai": "openrouter", "api.openai.com": "openai",
                   "generativelanguage.googleapis.com": "gemini", "api.x.ai": "xai"}


def _byok_art_backend(mode: str, key: dict | None):
    """The image backend a forge's art runs on, or None to use the server's own BTSGEN_IMAGE_BACKEND chain.

    Token (and dev-only fake) forges return None: the server pays for the text, so it pays for the art.
    A bring-your-own-key forge NEVER returns None — the user's key pays for everything or the art is
    skipped: an OpenRouter, OpenAI, Google Gemini or xAI key gets that vendor's backend built around the
    user's key (used for this forge only, held in memory, never persisted — same contract as the text
    calls); any other provider gets the fallback name. The returned instance/name goes straight to
    forge_splash & co as `backend=`, so the server's env chain is never consulted for a BYOK forge."""
    if mode not in ("byok", "anthropic"):
        return None
    fallback = (os.environ.get("BTSWEB_BYOK_ART_FALLBACK", "null").strip() or "null").lower()
    if mode != "byok" or not isinstance(key, dict):
        return fallback  # Anthropic has no image API
    api_key = (key.get("api_key") or "").strip()
    try:
        host = (urllib.parse.urlsplit((key.get("base_url") or "").strip()).hostname or "").lower()
    except ValueError:
        host = ""
    vendor = _BYOK_ART_HOSTS.get(host)
    if not (vendor and api_key):
        return fallback
    if vendor in ("gemini", "xai"):  # the generic OpenAI-images shape, one preset row per vendor
        from btsgen.art.backends.openai_images import PRESETS, OpenAIImagesBackend  # lazy: never block boot
        return OpenAIImagesBackend(PRESETS[vendor], api_key=api_key)
    from btsgen.art.backends.openai import OpenAIImageBackend          # lazy: never block app boot
    from btsgen.art.backends.openrouter import OpenRouterImageBackend
    cls = OpenRouterImageBackend if vendor == "openrouter" else OpenAIImageBackend
    return cls(api_key=api_key)


def _generate_art(kind: str, class_id: int, out: dict, bundle: dict, meter=None, backend=None) -> str | None:
    """Best-effort: render one art asset ('splash' = select-screen background, 'sprite' = the standing
    combat model) to static/forged/<id>/<kind>.png and return its content digest (or None if no backend
    is configured / generation failed). Mutates `bundle` in place to carry `<kind>_url` so the
    re-encoded import code delivers it to the mod. `meter` (a forge.UsageMeter) gets the image's model and
    metered cost for the ledger. `backend` (None = the server's BTSGEN_IMAGE_BACKEND chain) is a BYOK
    forge's own backend instance/name from _byok_art_backend. NEVER raises — a forge must succeed even if
    image generation doesn't."""
    try:
        from btsgen.art import class_art_from_bundle, forge_splash, forge_sprite  # lazy: never block app boot
        forge = forge_sprite if kind == "sprite" else forge_splash
        dest = STATIC_FORGED_DIR / str(class_id) / f"{kind}.png"
        res = forge(class_art_from_bundle(out), out_path=dest, backend=backend)
        if not (res.ok and res.path):
            app.logger.warning("%s not produced for class %s: %s", kind, class_id, res.error or "no backend")
            return None
        if meter is not None:  # one image, priced by whichever backend actually answered
            meter.add_art(kind, res.model or res.backend, res.cost_usd)
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


# --- per-card portrait pack ----------------------------------------------------------------------
# One illustration per card, delivered as ONE zip (static/forged/<id>/cards.zip) rather than ~34 URLs:
# the mod fetches it once at import and unpacks it, instead of making ~34 synchronous HTTP calls on the
# game's UI thread. Entry names are FLAT (`<card_id>.png`, no directories) because the mod flattens them
# to the leaf anyway.
#
# The guardrails exist because this is the one step whose cost and wall-clock scale with the class: ~34
# images at ~10 s and ~$0.004 each. Whichever of the two caps trips first stops the run and ships a
# PARTIAL zip — the mod falls back to its per-type doodle for every card the pack is missing, so a
# half-finished pack is a strictly better outcome than none, and far better than a forge that hangs.
CARD_ART_WORKERS = 6            # IO-bound (the backends are HTTP); the 1-vCPU droplet is fine with six
CARD_ART_BUDGET_S = 150.0       # wall clock for the whole pack (BTSWEB_CARD_ART_BUDGET_S)
CARD_ART_MAX_USD = 0.40         # spend cap for the whole pack, OUR money only (BTSWEB_CARD_ART_MAX_USD);
                                # a BYOK pack is uncapped — see _generate_card_art / BTSWEB_BYOK_CARD_ART_MAX_USD
CARD_ART_PROGRESS_EVERY = 4     # SSE lines: one per N cards, so the page never looks hung


def _env_float(name: str, default: float) -> float:
    try:
        raw = os.environ.get(name, "").strip()
        return float(raw) if raw else float(default)
    except (TypeError, ValueError):
        return float(default)


def _card_art_enabled() -> bool:
    """BTSWEB_CARD_ART=0 turns the whole step off (kill-switch for a bad image vendor day)."""
    return os.environ.get("BTSWEB_CARD_ART", "1").strip().lower() not in ("0", "false", "no", "off")


def _card_art_id(card: dict, index: int) -> str:
    """The zip entry stem for one card: its own id (that is what the mod looks a portrait up by), reduced
    to filesystem-safe characters. Falls back to the ordinal so a card with no id still gets a file."""
    raw = str((card or {}).get("id") or "").strip()
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in raw)[:64].strip("_")
    return safe or f"card_{index}"


def _generate_card_art(class_id: int, out: dict, bundle: dict, on_event=None, meter=None,
                       backend=None) -> str | None:
    """Best-effort: render one portrait per card into static/forged/<id>/cards/<card_id>.png, zip the
    successes into static/forged/<id>/cards.zip, stamp `bundle["card_art_url"]` and return the zip's
    content digest (None = nothing was produced — no backend, disabled, or every card failed).

    Runs the cards on a CARD_ART_WORKERS-wide pool and stops early when either guardrail trips:
    BTSWEB_CARD_ART_BUDGET_S wall clock or BTSWEB_CARD_ART_MAX_USD metered spend. "Stops" means the
    not-yet-started cards are cancelled (in-flight ones are left to finish — killing them would waste
    an image that is already paid for) and whatever succeeded is zipped and shipped.

    `backend` (None = the server's BTSGEN_IMAGE_BACKEND chain) is a BYOK forge's own image backend, so
    the pack bills the user's key — see _byok_art_backend. The COST cap is then off by default (the user
    was quoted the whole pack up front and asked for a complete class); the wall-clock budget is not.

    `on_event(str)` receives "card art n/N" progress for the SSE stream; `meter` (a forge.UsageMeter)
    collects the pack's model + metered cost for the forge_usage ledger. NEVER raises: identical contract
    to _generate_art — a forge must succeed even when its art does not."""
    from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed

    def note(msg: str) -> None:
        if on_event is not None:
            try:
                on_event(msg)
            except Exception:  # noqa: BLE001 — a broken progress sink must never break a forge
                pass

    try:
        if not _card_art_enabled():
            return None
        cards = [c for c in (out.get("cards") or []) if isinstance(c, dict)]
        if not cards:
            return None
        from btsgen.art import class_art_from_bundle, forge_card_art  # lazy: never block app boot

        art = class_art_from_bundle(out)  # built ONCE and shared: read-only, thread-safe
        cards_dir = STATIC_FORGED_DIR / str(class_id) / "cards"
        shutil.rmtree(cards_dir, ignore_errors=True)  # a re-run must never zip a previous run's art
        cards_dir.mkdir(parents=True, exist_ok=True)

        budget_s = _env_float("BTSWEB_CARD_ART_BUDGET_S", CARD_ART_BUDGET_S)
        # The spend cap guards OUR money. A BYOK forge's art is billed to the user's own key and the panel
        # showed them the whole per-forge figure before they pushed go (/api/forge-estimate), so BYOK is
        # UNCAPPED by decision (BYOK_ART_GEMINI_XAI_PLAN.md, 2026-09-19): at Gemini's flat $0.039 an image
        # the $0.40 ceiling would truncate every single pack at 11 of ~34 cards and quietly make the quote
        # a lie. BTSWEB_BYOK_CARD_ART_MAX_USD > 0 re-arms one if a vendor ever misbehaves. The wall-clock
        # budget still applies to both — that one guards against a hang, not against a bill.
        byok_key = backend is not None and not isinstance(backend, str)
        max_usd = (_env_float("BTSWEB_BYOK_CARD_ART_MAX_USD", 0.0) if byok_key
                   else _env_float("BTSWEB_CARD_ART_MAX_USD", CARD_ART_MAX_USD))
        deadline = time.monotonic() + budget_s if budget_s > 0 else None
        stop = threading.Event()
        total = len(cards)

        def render(card: dict, card_id: str):
            if stop.is_set():   # a cap tripped while this one sat in the queue
                return None
            return forge_card_art(art, card, out_path=cards_dir / f"{card_id}.png", backend=backend)

        made: dict[str, Path] = {}
        spent = 0.0
        done = 0
        note(f"card art: {total} cards…")
        pool = ThreadPoolExecutor(max_workers=max(1, CARD_ART_WORKERS))
        try:
            futures = {}
            for i, card in enumerate(cards):
                cid = _card_art_id(card, i)
                futures[pool.submit(render, card, cid)] = cid
            for fut in as_completed(futures):
                cid = futures[fut]
                try:
                    res = fut.result()
                except CancelledError:
                    continue
                except Exception as e:  # noqa: BLE001 — one bad card is not a failed forge
                    app.logger.warning("card art %s failed for class %s: %s", cid, class_id, e)
                    res = None
                done += 1
                if res is not None and not res.ok:
                    why = str(res.error or "no backend")[:160]
                    app.logger.warning("card art %s not produced for class %s: %s", cid, class_id, why)
                    note(f"card art: {cid} not produced ({why})")
                if res is not None and res.ok and res.path:
                    made[cid] = Path(res.path)
                    if res.cost_usd:
                        spent += float(res.cost_usd)
                    if meter is not None:
                        # model, else the backend name: the local backends report no model, and a ledger
                        # row that names neither is unattributable a month later.
                        meter.add_art("cards", res.model or res.backend, res.cost_usd)
                if not stop.is_set():
                    over_time = deadline is not None and time.monotonic() >= deadline
                    over_cost = max_usd > 0 and spent >= max_usd
                    if over_time or over_cost:
                        stop.set()
                        for f in futures:
                            f.cancel()
                        why = f"time budget ({int(budget_s)}s)" if over_time else f"cost cap (${max_usd:.2f})"
                        note(f"card art: {why} reached at {len(made)}/{total} — shipping a partial pack")
                        app.logger.warning("card art for class %s stopped early: %s (%d/%d done)",
                                           class_id, why, len(made), total)
                if done % CARD_ART_PROGRESS_EVERY == 0 or done == total:
                    note(f"card art {done}/{total}…")
        finally:
            pool.shutdown(wait=True)

        if not made:
            shutil.rmtree(cards_dir, ignore_errors=True)  # don't leave an empty cards/ per class
            note("card art: none produced")
            return None

        import hashlib
        import io
        import zipfile
        buf = io.BytesIO()
        # STORED, not deflated: PNG is already compressed, so deflating burns droplet CPU per class for
        # ~0 bytes. Flat entry names, sorted, so the pack is reproducible for a given set of renders.
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
            for cid in sorted(made):
                z.write(made[cid], arcname=f"{cid}.png")
        blob = buf.getvalue()
        (STATIC_FORGED_DIR / str(class_id) / "cards.zip").write_bytes(blob)
        digest = hashlib.sha256(blob).hexdigest()[:16]
        bundle["card_art_url"] = _art_url(class_id, "cards", digest)
        note(f"card art: packed {len(made)}/{total} portraits")
        return digest
    except Exception as e:  # logged, swallowed — art is cosmetic, the class still ships
        app.logger.warning("card art failed for class %s: %s", class_id, e)
        return None


def _persist_class(user_id: int, concept: str, out: dict, forge_meta: dict | None = None, art_backend=None,
                   on_event=None, meter=None) -> dict:
    """Save a forged class (+ denormalized card rows) for the user; return the detail shape. After the
    row gets its id, generate the art (best-effort) and re-encode the import code so it carries the
    splash_url/sprite_url/card_art_url — the harness/forge_to_bundle is never touched. Splash, sprite,
    relic icon and the per-card portrait pack are independent cloud work, so they run concurrently (each
    writes a distinct bundle key).

    `on_event(str)` (the forge route's SSE sink) carries the card-art step's progress to the browser — it
    is the long one (~34 images) and an unnarrated minute looks like a hang. `meter` (forge.UsageMeter)
    collects every image's model + metered cost, which the route's _record_usage then writes as the
    forge's `art:*` ledger rows.

    `forge_meta` (interactive forge mode) stamps how the class was made — offered/picked archetypes — into
    bundle_json for the guided-vs-unguided fun experiment. Analysis-only: stripped before encoding the
    import code, so the mod payload is byte-identical to an autonomous forge's.

    `art_backend` (None = the server's BTSGEN_IMAGE_BACKEND chain, i.e. the token path) is the image
    backend every asset here runs on — a BYOK forge passes its own (the user's key) or 'null'."""
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
    with ThreadPoolExecutor(max_workers=4) as pool:
        f_splash = pool.submit(_generate_art, "splash", class_id, out, bundle, meter, art_backend)
        f_sprite = pool.submit(_generate_art, "sprite", class_id, out, bundle, meter, art_backend)
        f_relic = pool.submit(_generate_relic_icon, class_id, out, bundle)  # emoji fetch: free either way
        # The card pack runs INSIDE this pool (it owns a nested worker pool of its own) so the code
        # returned below already carries every URL — the mod gets one code, not a code plus a promise.
        f_cards = pool.submit(_generate_card_art, class_id, out, bundle, on_event, meter, art_backend)
        splash_digest, sprite_digest = f_splash.result(), f_sprite.result()
        relic_digest = f_relic.result()
        cards_digest = f_cards.result()

    with session_scope() as s:
        cls = s.query(ForgedClass).filter_by(id=class_id).one_or_none()
        if cls is None:  # deleted mid-art-generation (rare): don't strand the fresh art on disk
            shutil.rmtree(STATIC_FORGED_DIR / str(class_id), ignore_errors=True)
            raise RuntimeError("this class was deleted while its art was still generating")
        cls.splash_hash = splash_digest or cls.splash_hash
        cls.sprite_hash = sprite_digest or cls.sprite_hash
        cls.card_art_hash = cards_digest or cls.card_art_hash
        if splash_digest or sprite_digest or relic_digest or cards_digest:  # re-encode so the code delivers the URLs
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
        if cards_digest:
            detail["card_art_url"] = _art_url(cls.id, "cards", cards_digest)
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
    """What the browser shows: the spendable balance, and nothing else — there is no free token to report."""
    return {"token_balance": int(u.token_balance)}


def _reserve_token(user_id: int) -> tuple[str, dict] | None:
    """Atomically spend one token for a hosted forge and return (kind, token_state). None = nothing to spend
    (caller 402s). The read + write happen in one transaction so two concurrent forges can't both spend the
    last token."""
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
            # "paid" is the only refundable kind. Rows stamped "free" predate pricing v3 (the token came out
            # of a day stamp, not the balance) and crediting one would mint a token that never existed.
            if job.token_kind == "paid":
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


# Estimated provider prices in USD per MILLION tokens: (input, output, cache-read). This is the FALLBACK
# estimate only: when a call reports what it actually billed (OpenRouter's usage.cost) the ledger records that
# in metered_cost_micros and every money reader prefers it — the table under-counted a real forge by 30-45% in
# the 2026-09-18 A/B, which is why it is a fallback and not the number.
#
# Bare slugs (`gemma4:31b`, `glm-5.2`) are OLLAMA CLOUD, the last-resort tier: they were priced at 0 for the
# flat plan, which Ollama retired for per-token billing on 2026-08-31 — a 0 there silently reported our most
# expensive tier as free. Namespaced slugs are OpenRouter, fetched live from GET /api/v1/models on 2026-09-18.
# Override/extend with BTSWEB_MODEL_PRICES='{"model": [in, out, cached], ...}'. Unknown model => est_cost NULL
# (recorded, not priced).
MODEL_PRICES: dict[str, tuple[float, float, float]] = {
    "gemma4:31b": (0.14, 0.40, 0.05),          # Ollama Cloud per-token list
    "glm-5.2": (1.40, 4.40, 0.26),             # Ollama Cloud per-token list
    "z-ai/glm-5.3": (0.91, 2.86, 0.169),       # OpenRouter, the hosted primary since Step 1
    "z-ai/glm-5.2": (0.5544, 1.7424, 0.10296),  # OpenRouter, the middle fallback tier
    "google/gemma-4-31b-it": (0.09, 0.34, 0.05),  # OpenRouter, brainstorm at every tier
}

# Every model the BYOK panel SUGGESTS (static/app.js PROVIDERS), so /api/forge-estimate can quote a dollar
# figure on the user's own key before they push go. Same unit as MODEL_PRICES: $ per MILLION tokens,
# (input, output, cache-read). These are the vendors' published LIST prices — advisory, never a bill.
# A suggested model with no row here is a test failure (web/tests/test_forge_estimate.py), which is how the
# table stays complete as the suggestion lists change. Checked 2026-09-20 unless a comment says otherwise.
BYOK_TEXT_PRICES: dict[str, tuple[float, float, float]] = {
    # Anthropic (the list the browser used to carry as CLAUDE_PRICES, now server-side like everything else)
    "claude-sonnet-4-6": (3.00, 15.00, 0.30),
    "claude-haiku-4-5": (1.00, 5.00, 0.10),
    "claude-opus-4-8": (5.00, 25.00, 0.50),
    "claude-opus-5": (5.00, 25.00, 0.50),    # not suggested, but the old browser table priced them and
    "claude-sonnet-5": (2.00, 10.00, 0.20),  # people type them — keep the quote working
    # OpenAI — developers.openai.com/api/docs/pricing, short-context standard tier
    "gpt-4o": (2.50, 10.00, 1.25),
    "gpt-4o-mini": (0.15, 0.60, 0.075),
    "gpt-4.1": (2.00, 8.00, 0.50),
    "o4-mini": (1.10, 4.40, 0.275),
    # Google Gemini, paid tier (ai.google.dev pricing). flash-lite first in the dropdown: cheapest text on
    # the shim, and the art bill is the same whichever text model is picked.
    "gemini-2.5-flash-lite": (0.10, 0.40, 0.01),
    "gemini-2.5-flash": (0.30, 2.50, 0.03),
    "gemini-3-flash-preview": (0.50, 3.00, 0.05),
    "gemini-2.5-pro": (1.25, 10.00, 0.125),
    # xAI — docs.x.ai models page, <200k context tier. grok-4-fast is GONE (retired before 2026-09-20);
    # grok-4.20-0309-non-reasoning is the only explicitly non-reasoning pick and so the first suggestion.
    "grok-4.20-0309-non-reasoning": (1.25, 2.50, 0.20),
    "grok-4.3": (1.25, 2.50, 0.20),
    "grok-4.5": (2.00, 6.00, 0.30),
    "grok-4.6": (2.00, 6.00, 0.50),
    # OpenRouter passes vendor list prices through (the hosted slugs live in MODEL_PRICES above)
    "anthropic/claude-sonnet-4.6": (3.00, 15.00, 0.30),
    "openai/gpt-4o": (2.50, 10.00, 1.25),
    "google/gemini-2.5-pro": (1.25, 10.00, 0.125),
    # Groq — UNVERIFIED 2026-09-20: groq.com/pricing and console.groq.com/docs/models no longer publish
    # per-token rates for these ("contact sales"), so these are the last rates Groq did publish.
    "llama-3.3-70b-versatile": (0.59, 0.79, 0.59),
    "moonshotai/kimi-k2-instruct": (1.00, 3.00, 1.00),
    # Ollama Cloud — ollama.com/pricing, OFF-PEAK rates (12:00-18:00 UTC Mon-Fri costs double). Cache-read
    # rates are not published per model there: UNVERIFIED 2026-09-20, estimated low.
    "gpt-oss:120b": (0.15, 0.60, 0.05),
    "qwen3.5:397b": (0.60, 3.60, 0.05),
    "deepseek-v4-pro": (0.66, 1.98, 0.022),
    # DeepSeek — api-docs.deepseek.com now lists deepseek-flash / deepseek-v4-pro; the API aliases
    # deepseek-chat / deepseek-reasoner are UNVERIFIED 2026-09-20 mappings onto those two rows (peak rates,
    # the pessimistic half of the off-peak/peak pair).
    "deepseek-chat": (0.30, 1.20, 0.006),
    "deepseek-reasoner": (1.32, 3.96, 0.044),
    # Together — together.ai/pricing lists "Llama 3.3 70B" at $1.04 flat; the -Turbo slug and DeepSeek-V3
    # are no longer on the page: UNVERIFIED 2026-09-20.
    "meta-llama/Llama-3.3-70B-Instruct-Turbo": (1.04, 1.04, 1.04),
    "deepseek-ai/DeepSeek-V3": (1.25, 1.25, 1.25),
}
MODEL_PRICES.update(BYOK_TEXT_PRICES)  # one table; BTSWEB_MODEL_PRICES below overrides either half
try:
    MODEL_PRICES.update({k: tuple(float(x) for x in v)  # type: ignore[misc]
                         for k, v in json.loads(os.environ.get("BTSWEB_MODEL_PRICES", "{}")).items()})
except (ValueError, TypeError, AttributeError):
    pass


def _record_usage(meter: UsageMeter, *, user_id: int, forge_id: str, mode: str, token_kind: str | None,
                  class_id: int | None, ok: bool, provider: str = "") -> None:
    """Write one forge_usage row per (role, model) the forge touched — LLM calls AND the art the persist step
    generated (role 'art:splash' / 'art:sprite' / 'art:cards', token columns 0). `provider` is WHERE the calls
    went ("hosted" / "anthropic" / a BYOK hostname — never the key).

    Two money columns per row: `est_cost_micros` is the MODEL_PRICES guess from the token counts (token path
    only — a BYOK forge is billed to the user's own provider), `metered_cost_micros` is what the provider said
    it actually charged (OpenRouter's usage.cost / ImageResult.cost_usd), NULL when nothing metered the row.

    Best-effort: never raises (telemetry must not break a forge that already succeeded)."""
    try:
        rows, art = meter.rows(), meter.art_rows()
        if not (rows or art):
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
                                 cached_tokens=r["cached_tokens"], est_cost_micros=cost,
                                 metered_cost_micros=_micros(r.get("cost_usd")), ok=1 if ok else 0))
            for r in art:
                # No est_cost for art: an image bills per image, not per token, and MODEL_PRICES is a
                # per-token table. The metered number from the backend is the only price there is.
                s.add(ForgeUsage(user_id=user_id, class_id=class_id, forge_id=forge_id, mode=mode,
                                 provider=provider or "",
                                 token_kind=token_kind, role=r["role"], model=r["model"], calls=r["calls"],
                                 input_tokens=0, output_tokens=0, cached_tokens=0, est_cost_micros=None,
                                 metered_cost_micros=_micros(r.get("cost_usd")), ok=1 if ok else 0))
    except Exception as e:  # noqa: BLE001
        app.logger.warning("forge_usage write failed (forge %s): %s", forge_id, e)


def _micros(usd) -> int | None:
    """USD float -> micro-dollars (the integer ledger unit), or None when nothing reported a cost."""
    if usd is None:
        return None
    try:
        return int(round(float(usd) * 1_000_000))
    except (TypeError, ValueError):
        return None


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
    # Art follows the money: a BYOK forge's splash/sprite/card pack run on the USER's key (OpenRouter or
    # OpenAI) or not at all — the server's image keys only ever pay for token forges.
    art_backend = _byok_art_backend(mode, key)

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

    # The "Use a token" path forges on our server-side Ollama mixture and spends one of the user's tokens,
    # unless the account is unlimited. Reserve it up front so we can 402 BEFORE streaming; a
    # forge that then fails is refunded by the worker (see finish_failed).
    ollama_mix = mode == "token"
    # Unlimited is env list OR the operator-granted users.unlimited_tokens flag, so it needs the row — read
    # it together with the balance pre-check below rather than in a query of its own.
    unlimited = False
    reserved = False
    token_kind: str | None = None
    token_day = time.strftime("%Y-%m-%d", time.gmtime())
    token_state: dict | None = None
    ip = _client_ip()
    if ollama_mix:
        # Cheap pre-check so an empty balance 402s without touching the day's budget counter; the reserve
        # below is the authoritative one (it's the transaction two concurrent forges race in).
        with session_scope() as s:
            u = s.query(User).filter_by(id=user["id"]).one_or_none()
            unlimited = user_is_unlimited(u)
            has_any = bool(u is not None and u.token_balance > 0)
        token_kind = "unlimited" if unlimited else None
    if ollama_mix and not unlimited:
        if not has_any:
            _user_end(user["id"])
            return jsonify({"error": "you're out of tokens — get more on the Account tab, or bring your own "
                                     "API key to keep forging.",
                            "token_balance": 0}), 402
        denied = token_limiter.check(ip)
        if denied:
            _user_end(user["id"])
            return jsonify({"error": denied}), 429
        res = _reserve_token(user["id"])
        if res is None:  # lost a race for the last token: give the day's budget slot back
            token_limiter.uncount(ip)
            _user_end(user["id"])
            return jsonify({"error": "you're out of tokens — get more on the Account tab, or bring your own "
                                     "API key to keep forging.",
                            "token_balance": 0}), 402
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
        """The balance fields the browser needs after a refund. The day's budget counter is deliberately NOT
        given back: the forge did reach our providers before it died, and the cap exists to bound spend."""
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
            # on_event: the card-art step narrates itself over the same SSE stream the forge used.
            # meter: its image costs join this forge's ledger rows (written by _record_usage below).
            saved = _persist_class(user["id"], concept, out, forge_meta=forge_meta,
                                   on_event=on_event, meter=meter, art_backend=art_backend)
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
            # The art rows are on the user's key too (BYOK): images made, and the metered USD where the
            # vendor reported one (OpenRouter does; OpenAI's is advisory, None means unknown).
            art = meter.art_rows()
            saved["usage"]["images"] = sum(int(r.get("calls") or 0) for r in art)
            priced = [float(r["cost_usd"]) for r in art if r.get("cost_usd") is not None]
            saved["usage"]["art_cost_usd"] = round(sum(priced), 4) if priced else None
            # Is that dollar figure a BILL or a TABLE? OpenRouter meters every image (and a token forge's
            # art runs on our OpenRouter key), so those are real. OpenAI, Gemini and xAI report no cost at
            # all, so their backends hand back a list-price estimate — the browser labels it "est.".
            saved["usage"]["art_cost_metered"] = provider in ("openrouter.ai", "hosted")
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
# A complete pack is splash + sprite + one portrait per card; a triad class runs ~34 cards. Used when the
# ledger has no art rows to average yet.
FORGE_ESTIMATE_FALLBACK_IMAGES = 36
# List-price-per-image fallback for the two METERED art vendors, used only until the ledger has real rows.
# Derived from the 2026-09-18 A/B defaults: splash $0.044 + sprite $0.015 + 34 cards @ $0.0038 = $0.19 for
# 36 images ≈ $0.0055 each. OpenRouter meters every image, so in practice this is replaced by the measured
# average within a few forges; OpenAI's backend only ever reports its own advisory table.
ART_LIST_PRICE_USD = {"openrouter": 0.0055, "openai": 0.0055}
# A vendor's art line switches from the preset/list price to the ledger's MEASURED average once this many
# distinct sampled forges made art on that host — the plan's open question, answered: list until there is
# enough history to beat it, then the real number (which is also what the Gemini/xAI comparison sentence
# quotes for OpenRouter).
ART_MEASURED_MIN_FORGES = 3
# 60 s of caching: the payload now costs three queries plus the preset math, and it changes about as often
# as a forge finishes. Tests (and anything that seeds the ledger) reset it by clearing `at`.
FORGE_ESTIMATE_CACHE_S = 60
_estimate_cache: dict = {"at": 0.0, "payload": None}


def _art_price_blocks(images_per_forge: int, measured: dict) -> dict:
    """The `art` block of /api/forge-estimate: one entry per vendor in _BYOK_ART_HOSTS, each answering
    "what does a complete pack cost on a key of this kind". Gemini and xAI have no metered cost in their
    API responses at all, so their number is the preset table (btsgen.art.backends.openai_images); the
    OpenRouter/OpenAI entries start at ART_LIST_PRICE_USD and are replaced by the ledger's measured average
    per image once ART_MEASURED_MIN_FORGES forges have made art there. `measured` is
    {vendor: {"per_image_usd": float, "forges": int}} from _sampled_art_stats."""
    out: dict[str, dict] = {}
    n_cards = max(0, int(images_per_forge) - 2)  # splash + sprite are not portraits
    for vendor in set(_BYOK_ART_HOSTS.values()):
        entry: dict = {"source": "list"}
        if vendor in ("gemini", "xai"):
            try:
                from btsgen.art.backends.openai_images import estimate_pack  # lazy: never block app boot
                pack = estimate_pack(vendor, n_cards)
                entry.update(model=pack["models"].get("card"), models=pack["models"],
                             per_image_usd=pack["per_image_usd"].get("card"),
                             per_image_by_kind=pack["per_image_usd"],
                             images=pack["images"], pack_usd=round(float(pack["total_usd"]), 4))
            except Exception as e:  # noqa: BLE001 — a quote must never 500 the panel
                app.logger.warning("art estimate for %s unavailable: %s", vendor, e)
                continue
        else:
            per = ART_LIST_PRICE_USD.get(vendor)
            entry.update(model=None, models={}, per_image_usd=per, images=images_per_forge,
                         pack_usd=round((per or 0.0) * images_per_forge, 4))
        m = measured.get(vendor) or {}
        if m.get("forges", 0) >= ART_MEASURED_MIN_FORGES and m.get("per_image_usd") is not None:
            entry.update(source="measured", per_image_usd=round(m["per_image_usd"], 6),
                         pack_usd=round(m["per_image_usd"] * images_per_forge, 4),
                         forges_measured=m["forges"])
        out[vendor] = entry
    return out


def _sampled_art_stats(s, forge_ids: list[str]) -> tuple[int | None, dict]:
    """Art rows of the sampled forges, reduced to (images per forge, per-vendor measured price).

    Returns (images_per_forge or None when no forge in the sample made art, {vendor: {"per_image_usd",
    "forges"}}). `provider` on an art row is the BYOK hostname ("openrouter.ai") or "hosted" for a token
    forge; a token forge's art runs on OUR OpenRouter key, so those rows back the openrouter average when
    no BYOK ones exist — the hosted pack is the same pack."""
    from sqlalchemy import func as sa_func
    if not forge_ids:
        return None, {}
    rows = (s.query(ForgeUsage.forge_id, ForgeUsage.provider, ForgeUsage.calls,
                    ForgeUsage.metered_cost_micros)
            .filter(ForgeUsage.ok == 1, ForgeUsage.forge_id.in_(forge_ids),
                    sa_func.coalesce(ForgeUsage.role, "").like("art:%"))
            .all())
    if not rows:
        return None, {}
    host_vendor = dict(_BYOK_ART_HOSTS)
    per_forge_images: dict[str, int] = {}
    # vendor -> {"usd": float, "images": int, "forges": set} for BYOK rows, plus "hosted" kept apart so it
    # only stands in for OpenRouter when no BYOK OpenRouter forge is in the window.
    acc: dict[str, dict] = {}
    for r in rows:
        calls = int(r.calls or 0)
        per_forge_images[r.forge_id] = per_forge_images.get(r.forge_id, 0) + calls
        vendor = host_vendor.get((r.provider or "").strip().lower())
        if vendor is None and (r.provider or "").strip().lower() == "hosted":
            vendor = "hosted"
        if vendor is None or r.metered_cost_micros is None or calls <= 0:
            continue
        a = acc.setdefault(vendor, {"usd": 0.0, "images": 0, "forges": set()})
        a["usd"] += int(r.metered_cost_micros) / 1_000_000
        a["images"] += calls
        a["forges"].add(r.forge_id)
    hosted = acc.pop("hosted", None)
    if hosted and "openrouter" not in acc:
        acc["openrouter"] = hosted
    measured = {v: {"per_image_usd": a["usd"] / a["images"], "forges": len(a["forges"])}
                for v, a in acc.items() if a["images"] > 0}
    images = int(round(sum(per_forge_images.values()) / len(per_forge_images))) if per_forge_images else None
    return images, measured


def _forge_estimate_payload() -> dict:
    """Build (uncached) the whole pre-go quote. Split out of the route so tests can call it directly."""
    from sqlalchemy import func as sa_func
    with session_scope() as s:
        rows = (s.query(ForgeUsage.forge_id, ForgeUsage.calls, ForgeUsage.input_tokens,
                        ForgeUsage.cached_tokens, ForgeUsage.output_tokens)
                .filter(ForgeUsage.ok == 1,
                        sa_func.coalesce(ForgeUsage.role, "").notlike("art:%"))
                .order_by(ForgeUsage.created_at.desc(), ForgeUsage.id.desc())
                .all())
        # One query, grouped in Python: rows arrive newest-first, so the first FORGE_ESTIMATE_SAMPLE
        # distinct forge_ids are the newest forges — and every row of those forges is summed wherever it
        # turns up.
        per_forge: dict[str, dict] = {}
        for r in rows:
            acc = per_forge.get(r.forge_id)
            if acc is None:
                if len(per_forge) >= FORGE_ESTIMATE_SAMPLE:
                    continue
                acc = per_forge[r.forge_id] = dict.fromkeys(_ESTIMATE_FIELDS, 0)
            for f in _ESTIMATE_FIELDS:
                acc[f] += int(getattr(r, f) or 0)
        images, measured = _sampled_art_stats(s, list(per_forge))
    n = len(per_forge)
    tokens = ({**FORGE_ESTIMATE_FALLBACK, "forges_sampled": 0, "fallback": True} if not n else
              {**{f: int(round(sum(a[f] for a in per_forge.values()) / n)) for f in _ESTIMATE_FIELDS},
               "forges_sampled": n, "fallback": False})
    images_per_forge = images or FORGE_ESTIMATE_FALLBACK_IMAGES
    return {**tokens,
            "images_per_forge": images_per_forge,
            "images_fallback": images is None,
            "art": _art_price_blocks(images_per_forge, measured),
            "text_prices": {m: list(p) for m, p in MODEL_PRICES.items()}}


@app.route("/api/forge-estimate")
@require_login
def forge_estimate():
    """What one forge will cost the user, before they push go. Three parts:

    * the average LLM consumption of one forge (calls + tokens), from the last FORGE_ESTIMATE_SAMPLE
      successful forges in the usage ledger (any mode — the staged front-end does the same work whoever
      pays for it), falling back to measured constants on an empty ledger. `art:*` rows are excluded here:
      folding ~36 image "calls" and their zero token counts into a TOKEN average would be wrong in both
      directions — they get their own numbers below;
    * `images_per_forge` + `art`: how many images a pack is and what one costs on each art-capable BYOK
      vendor — preset list price for Gemini/xAI (neither meters a cost), the ledger's measured average for
      OpenRouter/OpenAI once there is enough of it (see ART_MEASURED_MIN_FORGES);
    * `text_prices`: {model: [in, out, cached]} $/M for every model the panel suggests, so the browser
      multiplies but never owns a price table. Override any row with BTSWEB_MODEL_PRICES.

    Cached FORGE_ESTIMATE_CACHE_S seconds process-wide — it is the same answer for every user."""
    now = time.time()
    if _estimate_cache["payload"] is None or now - _estimate_cache["at"] > FORGE_ESTIMATE_CACHE_S:
        _estimate_cache["payload"], _estimate_cache["at"] = _forge_estimate_payload(), now
    return jsonify(_estimate_cache["payload"])


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
        if cls.card_art_hash:
            detail["card_art_url"] = _art_url(cls.id, "cards", cls.card_art_hash)
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
                     ForgeUsage.role, ForgeUsage.calls, ForgeUsage.input_tokens, ForgeUsage.output_tokens,
                     ForgeUsage.cached_tokens, ForgeUsage.est_cost_micros,
                     ForgeUsage.metered_cost_micros)
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
    # Per row we prefer the METERED cost (what the provider actually billed) and fall back to the rate-table
    # estimate — mixing is deliberate: a forge's glm rows are metered by OpenRouter while an Ollama-tier row
    # never is, and half a real number beats a whole guess. The token/call counters skip `art:*` rows: an
    # image call has no tokens, and counting it as a "call" would corrupt the per-forge LLM averages. Its
    # COST is still ours and is counted.
    hosted = {"forges": 0, "calls": 0, "input_tokens": 0, "cached_tokens": 0, "output_tokens": 0,
              "est_cost_usd": None}
    hosted_forge_ids: set[str] = set()
    cost_micros, priced = 0, False
    models: dict[tuple, dict] = {}
    providers: dict[str, set] = {}
    for r in usage:
        is_art = str(r.role or "").startswith("art:")
        if r.mode == "token":
            hosted_forge_ids.add(r.forge_id)
            if not is_art:
                for f in ("calls", "input_tokens", "cached_tokens", "output_tokens"):
                    hosted[f] += int(getattr(r, f) or 0)
            billed = r.metered_cost_micros if r.metered_cost_micros is not None else r.est_cost_micros
            if billed is not None:
                cost_micros += int(billed)
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


# --- operator dashboard: user management --------------------------------------------------------
# Adjust an account's token balance, or grant it unlimited hosted forging, without a redeploy. Same gate as
# the stats card (auth.ADMIN_EMAILS) — and notably admin itself is NOT editable here: it comes from
# BTSWEB_ADMIN_EMAILS only, so the panel can never widen who reaches the panel. Every write is recorded in
# admin_actions, because a token balance is money-adjacent and "who moved it" has to stay answerable.

ADMIN_USERS_LIMIT = 200        # rows one listing may return (the UI also shows the unfiltered total)
ADMIN_TOKENS_MAX = 100_000     # sanity ceiling on a balance set by hand; a typo shouldn't mint a fortune
ADMIN_ACTIONS_LIMIT = 50


def _admin_or_403():
    """None when the caller may use these routes, else the (body, status) to return. @require_login has
    already handled "not signed in" (401) by the time this runs."""
    if not is_admin((current_user() or {}).get("email", "")):
        return jsonify({"error": "forbidden"}), 403
    return None


def _log_admin_action(s, actor, target, action: str, old_value: int, new_value: int, note: str = "") -> None:
    """Append one audit row inside the caller's transaction, so the edit and its record commit together."""
    s.add(AdminAction(
        actor_user_id=actor.get("id"), actor_email=(actor.get("email") or "").strip().lower(),
        target_user_id=target.id, target_email=(target.email or "").strip().lower(),
        action=action, old_value=int(old_value), new_value=int(new_value), note=note[:200]))


@app.route("/api/admin/users")
@require_login
def admin_users():
    """The user list behind the Account tab's management panel: one row per account with the context needed
    to judge a token edit (how many forges, how much donated, when they joined, how they sign in).

    ?q= filters on email or name (case-insensitive substring, trimmed); ?limit= caps rows (<= 200). Ordering
    is newest account first, which is what you want when someone just donated or just wrote in. `total` is
    the number of accounts MATCHING the filter, so the UI can say "showing 200 of 412".

    Read-only. No API key has ever existed in this database (see models' module docstring) and nothing here
    exposes concept text or class contents."""
    denied = _admin_or_403()
    if denied:
        return denied
    q = (request.args.get("q") or "").strip()
    try:
        limit = int(request.args.get("limit", ADMIN_USERS_LIMIT))
    except (TypeError, ValueError):
        limit = ADMIN_USERS_LIMIT
    limit = max(1, min(limit, ADMIN_USERS_LIMIT))

    from sqlalchemy import func as sa_func, or_

    with session_scope() as s:
        uq = s.query(User)
        if q:
            like = f"%{q.lower()}%"
            uq = uq.filter(or_(sa_func.lower(User.email).like(like), sa_func.lower(User.name).like(like)))
        total = uq.count()
        rows = uq.order_by(User.id.desc()).limit(limit).all()
        ids = [u.id for u in rows]

        # Three grouped queries for the whole page rather than three per row.
        forges: dict[int, int] = {}
        donated: dict[int, int] = {}
        idents: dict[int, list[str]] = {}
        if ids:
            for uid, n in (s.query(ForgeJob.user_id, sa_func.count(ForgeJob.id))
                           .filter(ForgeJob.user_id.in_(ids)).group_by(ForgeJob.user_id).all()):
                forges[uid] = int(n or 0)
            for uid, cents in (s.query(Purchase.user_id, sa_func.sum(Purchase.amount_cents))
                               .filter(Purchase.user_id.in_(ids), Purchase.status == "paid")
                               .group_by(Purchase.user_id).all()):
                donated[uid] = int(cents or 0)
            for uid, provider in (s.query(Identity.user_id, Identity.provider)
                                  .filter(Identity.user_id.in_(ids)).all()):
                idents.setdefault(uid, []).append(provider)

        users = [{
            "id": u.id,
            "email": u.email or "",
            "name": u.name or "",
            "providers": sorted(set(idents.get(u.id, []))),
            "token_balance": int(u.token_balance or 0),
            "unlimited": bool(u.unlimited_tokens),
            # On the env master list ⇒ unlimited no matter what the flag says, and the UI locks the toggle:
            # only an edit to BTSWEB_UNLIMITED_EMAILS + a redeploy can change it.
            "unlimited_env": is_unlimited(u.email or ""),
            "admin": is_admin(u.email or ""),
            "forges": forges.get(u.id, 0),
            "donated_cents": donated.get(u.id, 0),
            "created_at": u.created_at.isoformat() if u.created_at else None,
        } for u in rows]

    return jsonify({"users": users, "total": total, "limit": limit, "q": q})


@app.route("/api/admin/users/<int:user_id>/tokens", methods=["POST"])
@require_login
def admin_set_tokens(user_id: int):
    """Set an account's token balance to `balance`, or move it by `delta`. Exactly one of the two.

    The read-modify-write happens in ONE transaction so it cannot interleave with a forge spending the last
    token (SQLite takes the write lock at BEGIN — see db._sqlite_begin — and MySQL's row lock does the same).
    A delta is clamped into [0, ADMIN_TOKENS_MAX] rather than rejected: "take 5 away" from a balance of 3
    should leave 0, not an error."""
    denied = _admin_or_403()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    has_balance, has_delta = "balance" in body, "delta" in body
    if has_balance == has_delta:
        return jsonify({"error": "send exactly one of balance or delta"}), 400
    raw = body["balance"] if has_balance else body["delta"]
    if isinstance(raw, bool) or not isinstance(raw, (int, str, float)):
        return jsonify({"error": "balance/delta must be a whole number"}), 400
    try:
        amount = int(str(raw).strip())
    except (TypeError, ValueError):
        return jsonify({"error": "balance/delta must be a whole number"}), 400
    if has_balance and not (0 <= amount <= ADMIN_TOKENS_MAX):
        return jsonify({"error": f"balance must be between 0 and {ADMIN_TOKENS_MAX}"}), 400

    actor = current_user() or {}
    with session_scope() as s:
        target = s.query(User).filter_by(id=user_id).one_or_none()
        if target is None:
            return jsonify({"error": "no such user"}), 404
        old = int(target.token_balance or 0)
        new = amount if has_balance else old + amount
        new = max(0, min(int(new), ADMIN_TOKENS_MAX))
        target.token_balance = new
        if new != old:
            _log_admin_action(s, actor, target, "set_tokens", old, new,
                              note=str(body.get("note") or "").strip())
    return jsonify({"id": user_id, "token_balance": new, "previous": old})


@app.route("/api/admin/users/<int:user_id>/unlimited", methods=["POST"])
@require_login
def admin_set_unlimited(user_id: int):
    """Turn users.unlimited_tokens on or off for an account: {"unlimited": true|false}.

    Turning it OFF does not touch the env master list — an account on BTSWEB_UNLIMITED_EMAILS keeps forging
    free, and the response says so in `unlimited_env` so the UI can explain why the toggle looks stuck."""
    denied = _admin_or_403()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    if not isinstance(body.get("unlimited"), bool):
        return jsonify({"error": "unlimited must be true or false"}), 400
    want = 1 if body["unlimited"] else 0

    actor = current_user() or {}
    with session_scope() as s:
        target = s.query(User).filter_by(id=user_id).one_or_none()
        if target is None:
            return jsonify({"error": "no such user"}), 404
        old = 1 if target.unlimited_tokens else 0
        target.unlimited_tokens = want
        env = is_unlimited(target.email or "")
        if old != want:
            _log_admin_action(s, actor, target, "set_unlimited", old, want,
                              note=str(body.get("note") or "").strip())
    return jsonify({"id": user_id, "unlimited": bool(want), "unlimited_env": env})


@app.route("/api/admin/actions")
@require_login
def admin_actions():
    """The audit trail, newest first: what was changed, for whom, by whom. Append-only; nothing edits it."""
    denied = _admin_or_403()
    if denied:
        return denied
    try:
        limit = int(request.args.get("limit", 10))
    except (TypeError, ValueError):
        limit = 10
    limit = max(1, min(limit, ADMIN_ACTIONS_LIMIT))
    with session_scope() as s:
        rows = s.query(AdminAction).order_by(AdminAction.id.desc()).limit(limit).all()
        actions = [r.summary() for r in rows]
    return jsonify({"actions": actions})


# Refund the tokens of any forge the previous process took down with it (deploy restarts).
_reconcile_forge_jobs()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), threaded=True, debug=True)
