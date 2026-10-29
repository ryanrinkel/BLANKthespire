"""Sign-in (Authlib over Flask sessions) + email magic links + a dev-login bypass for local verification.

Google, Discord and GitHub each register with Authlib only when their `<PROVIDER>_CLIENT_ID`/`_SECRET` pair is
set, so a box with one provider's credentials offers exactly one button. The email magic link is ours (no
OAuth): a mailed single-use token, enabled when RESEND_API_KEY + BTSWEB_MAIL_FROM are set. Every path — the
three OAuth providers, the magic link, the dev bypass, and whatever comes later — builds a Profile and
funnels through _resolve_identity, which maps one (provider, subject) identity onto a `users` row. Sessions
are server-signed cookies; no passwords.

Local dev: set BTSWEB_DEV_AUTH=1 to expose /dev-login?email=... which logs in a fake user WITHOUT OAuth —
so the per-user library flow is testable with no credentials. Fail-closed: the route is only registered when
the flag is on, and the app refuses to boot if the flag is on while a real sign-in provider is
configured (a production-looking deploy must never carry the bypass).
"""
from __future__ import annotations

import functools
import hashlib
import hmac
import os
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests
from flask import jsonify, redirect, request, send_from_directory, session, url_for
from sqlalchemy import update

import i18n
import promo
from db import session_scope
from models import Identity, LoginLink, PromoGrant, Promotion, User

GOOGLE_METADATA = "https://accounts.google.com/.well-known/openid-configuration"
_oauth = None  # set by init_auth when at least one provider's credentials are present

# Master list of accounts that forge on the token path WITHOUT spending tokens (you, testers). Comma-separated
# addresses in BTSWEB_UNLIMITED_EMAILS, matched against users.email (which only ever holds a provider-VERIFIED
# address — see _resolve_identity). Empty/unset ⇒ no one is unlimited (everyone spends their balance).
UNLIMITED_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("BTSWEB_UNLIMITED_EMAILS", "").split(",")
    if e.strip()
}

# Accounts that may use the operator cards on the Account tab — the forge-stats dashboard AND the user
# panel that edits token balances and grants unlimited. Comma-separated addresses in BTSWEB_ADMIN_EMAILS,
# matched against users.email exactly like UNLIMITED_EMAILS.
#
# Empty/unset ⇒ NOBODY is an operator. This used to fall back to the unlimited list ("it is already the
# 'this is us' roster"), which was tolerable while the cards were read-only but is not now that they can
# move token balances: adding one tester to BTSWEB_UNLIMITED_EMAILS would silently have made them an
# operator. Fail closed instead — the cost of forgetting the variable is a dashboard that does not render,
# which is obvious and recoverable, rather than a privilege nobody meant to hand out (init_auth warns at
# boot). Granting a tester unlimited no longer needs the env list at all: do it from the panel, which writes
# users.unlimited_tokens and confers nothing else. Admin stays env-only by design, so no route — and no
# operator — can widen who reaches the panel.
ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("BTSWEB_ADMIN_EMAILS", "").split(",")
    if e.strip()
}


# The OAuth providers, in the order the chooser page shows them. A provider is "configured" (and gets a
# button) only when both halves of its env pair are set.
PROVIDERS = ("google", "discord", "github")

# Env vars whose presence means a real sign-in provider is configured — i.e. a production-looking deploy, not
# a keyless local box. Adding a provider (mail, ...) means adding its id here, and every boot guard follows
# automatically.
PROVIDER_ENV_VARS = ("GOOGLE_CLIENT_ID", "DISCORD_CLIENT_ID", "GITHUB_CLIENT_ID")

# Email magic links need BOTH halves: the Resend API key and the From address they are sent as. Either one
# alone cannot send mail, so email sign-in stays off (except under the dev bypass, which logs the link).
MAIL_ENV_VARS = ("RESEND_API_KEY", "BTSWEB_MAIL_FROM")
RESEND_ENDPOINT = "https://api.resend.com/emails"
LINK_TTL = timedelta(minutes=15)      # how long an emailed link stays usable
LINK_SWEEP_AFTER = timedelta(hours=24)  # used or not, a link row is dead weight after a day
# The sign-in code mailed with every link (2026-10-29): 6 digits, same row, same expiry, same single use.
# A desktop mail app (QQ Mail's embedded Chromium, ...) opens the link in ITS browser, so the session lands
# there; the code is typed into the tab where sign-in started instead. CODE_MAX_ATTEMPTS wrong guesses
# against a row kill it — link included — so a guesser gets 5 tries per link, never 10^6.
CODE_DIGITS = 6
CODE_MAX_ATTEMPTS = 5


def mail_configured() -> bool:
    """True when this deploy can actually send a magic link (Resend key + From address)."""
    return all(os.environ.get(v, "").strip() for v in MAIL_ENV_VARS)


def is_production() -> bool:
    """True once ANY sign-in method that real people can use is configured — an OAuth provider or mail. The
    fail-closed boot guards (the session secret key in app.py, the dev-login conflict below) key off this
    rather than one provider's client id, so they keep covering every provider as more are added."""
    return any(os.environ.get(v, "").strip() for v in PROVIDER_ENV_VARS) or mail_configured()


def email_login_enabled() -> bool:
    """True when /login should offer the email form. Without mail the dev bypass still enables it: the link
    is logged and returned in the JSON, so the local loop and the tests need no mail provider at all."""
    return mail_configured() or _dev_auth_enabled()


def _credentials(provider: str) -> tuple[str, str]:
    """(client_id, client_secret) for a provider, "" when unset."""
    up = provider.upper()
    return (os.environ.get(f"{up}_CLIENT_ID", "").strip(),
            os.environ.get(f"{up}_CLIENT_SECRET", "").strip())


def configured_providers() -> list[str]:
    """The providers with a full credential pair, in display order — what /api/me reports and signin.js
    renders buttons for."""
    return [p for p in PROVIDERS if all(_credentials(p))]


def is_unlimited(email: str) -> bool:
    """True if this email is on the unlimited-tokens master list (never decremented on the token path).

    This is the ENV half only. A user can also be granted unlimited from the operator panel, which sets
    users.unlimited_tokens — use user_is_unlimited() when you have the row and want the effective answer."""
    return (email or "").strip().lower() in UNLIMITED_EMAILS


def user_is_unlimited(row) -> bool:
    """The effective answer for a users row: on the env master list OR granted the DB flag from the operator
    panel. Env first and separate on purpose — BTSWEB_UNLIMITED_EMAILS is the break-glass path that no write
    to the database can take away. `row` may be None (deleted mid-request) ⇒ False."""
    if row is None:
        return False
    return is_unlimited(getattr(row, "email", "")) or bool(getattr(row, "unlimited_tokens", 0))


def is_admin(email: str) -> bool:
    """True if this email may read the operator dashboard (see ADMIN_EMAILS). Same matching rule as
    is_unlimited: users.email only ever holds a provider-VERIFIED address."""
    return (email or "").strip().lower() in ADMIN_EMAILS


def _dev_auth_enabled() -> bool:
    return os.environ.get("BTSWEB_DEV_AUTH", "").strip() in ("1", "true", "yes")


@dataclass
class Profile:
    """What a provider told us about the person signing in. email_verified is True ONLY when the provider
    vouches for the address (Google's id_token claim, a clicked magic link, ...) — an unverified address is
    just text the user typed into someone else's form, so it never reaches users.email."""
    provider: str        # "google" | "discord" | "github" | "email" | "dev"
    subject: str         # the provider's stable id (Google sub, a snowflake, the email itself, ...)
    email: str = ""      # "" if the provider gave none
    email_verified: bool = False
    name: str = ""


# --- per-provider profile fetch ----------------------------------------------------------------------
# One pure function per provider: given an Authlib client and its token, return a Profile. Keeping the
# network call in here (and nowhere else) is what lets the tests drive the whole callback with a fake client.

def _profile_google(client, token) -> Profile:
    """Google is OIDC: the ID token already carries everything, so there is no extra API call."""
    info = token.get("userinfo") or client.parse_id_token(token, nonce=None)
    return Profile("google", str(info["sub"]), info.get("email", ""),
                   bool(info.get("email_verified")), info.get("name", ""))


def _profile_discord(client, token) -> Profile:
    """Discord's /users/@me carries `verified`, which is the ONLY thing that makes the address trustworthy —
    an unverified Discord account can claim any address (see _resolve_identity's security note)."""
    me = client.get("users/@me", token=token).json()
    return Profile("discord", str(me["id"]), me.get("email") or "", bool(me.get("verified")),
                   me.get("global_name") or me.get("username") or "")


def _profile_github(client, token) -> Profile:
    """GitHub's /user.email is null for every account with a private email, so the address comes from
    /user/emails (needs the user:email scope) — primary+verified first, else any verified one. No verified
    address ⇒ the account is created without one: it just can't link or be on the unlimited list."""
    me = client.get("user", token=token).json()
    email = ""
    try:
        resp = client.get("user/emails", token=token)
        resp.raise_for_status()
        rows = resp.json()
    except Exception:  # no user:email scope, or GitHub said no — an account without an email is fine
        rows = []
    if isinstance(rows, list):
        verified = [r for r in rows if isinstance(r, dict) and r.get("verified") and r.get("email")]
        primary = [r for r in verified if r.get("primary")]
        if primary or verified:
            email = (primary or verified)[0]["email"]
    return Profile("github", str(me["id"]), email, bool(email),
                   me.get("name") or me.get("login") or "")


_PROFILE = {"google": _profile_google, "discord": _profile_discord, "github": _profile_github}


def _resolve_identity(p: Profile, *, current_user_id: int | None = None) -> dict:
    """Identity -> user: the one door every provider comes through. In order:
    1. identities(provider, subject) exists          -> that user (the normal repeat sign-in)
    2. current_user_id is set (link while signed in) -> attach this identity to the current user
    3. verified email matching exactly one users.email -> attach to THAT user, so someone who signs in with a
       second provider next week keeps their tokens and classes
    4. otherwise                                     -> a new user + identity

    users.email / users.name are refreshed only from a VERIFIED profile: is_unlimited() gates free forging on
    users.email, so an unverified address (some providers let you claim any address) must never land there,
    nor be used for linking. Returns a plain dict detached from the session, like any sign-in."""
    email = (p.email or "").strip().lower()
    with session_scope() as s:
        ident = s.query(Identity).filter_by(provider=p.provider, subject=p.subject).one_or_none()
        user = s.query(User).filter_by(id=ident.user_id).one_or_none() if ident is not None else None
        if user is None and current_user_id is not None:
            user = s.query(User).filter_by(id=current_user_id).one_or_none()
        if user is None and p.email_verified and email:
            matches = s.query(User).filter(User.email == email).all()
            if len(matches) == 1:  # two accounts share the address: ambiguous, so link to neither
                user = matches[0]
        if user is None:
            # google_sub is the legacy NOT NULL UNIQUE column; "provider:subject" keeps it unique forever.
            user = User(google_sub=f"{p.provider}:{p.subject}",
                        email=email if p.email_verified else "", name=p.name or "")
            s.add(user)
            s.flush()
            # Rule 4 is the ONLY place an account is born, so it is the only place a sign-up event pays out
            # (promo.py). Same transaction, inside a savepoint: a promo failure costs the bonus, never the
            # sign-in. Rules 1-3 (repeat sign-in, linking a second provider) never reach this line.
            promo.grant_signup_bonus(s, user)
        elif p.email_verified:
            user.email = email or user.email
            user.name = p.name or user.name
        if ident is None:
            s.add(Identity(user_id=user.id, provider=p.provider, subject=p.subject, email=email))
        elif email and ident.email != email:
            ident.email = email
        return {"id": user.id, "email": user.email, "name": user.name}


def _landing(user: dict, signed_in_as: int | None) -> str:
    """Where a successful sign-in lands. Normally /app — but when the flow ran while already signed in and
    the identity attached to THAT account (rule 2, the "link another sign-in" flow), /app#account puts the
    person back on the Account tab they started from, with the new method listed. An identity owned by
    someone else resolves to that other user (rule 1) — a plain sign-in, so it lands on /app like one."""
    return "/app#account" if signed_in_as is not None and user["id"] == signed_in_as else "/app"


def current_user() -> dict | None:
    """The signed-in user as {id, email, name}, or None."""
    uid = session.get("user_id")
    if uid is None:
        return None
    return {"id": uid, "email": session.get("email", ""), "name": session.get("name", "")}


def _login_session(user: dict) -> None:
    session["user_id"] = user["id"]
    session["email"] = user["email"]
    session["name"] = user["name"]
    # When this sign-in happened. Sessions are permanent (Flask's 31-day default), which is fine for forging
    # but too long for the operator panel's writes: app._admin_or_403 refuses a balance edit from a session
    # older than ADMIN_WRITE_MAX_AGE_S, so a stolen or left-open operator cookie is not a month of free rein.
    session["auth_at"] = int(time.time())
    session.permanent = True


def session_age() -> float | None:
    """Seconds since the current session signed in, or None when the session predates the `auth_at` stamp
    (a cookie issued before it existed) — callers that gate on freshness treat None as "too old"."""
    at = session.get("auth_at")
    if not isinstance(at, (int, float)) or isinstance(at, bool):
        return None
    return max(0.0, time.time() - float(at))


def _identities_of(user_id: int) -> list[dict]:
    """{provider, label} per linked identity, for the Account tab. The label is the identity's email when the
    provider gave one, else its subject — enough to tell two accounts apart."""
    with session_scope() as s:
        rows = s.query(Identity).filter_by(user_id=user_id).all()
        out = [{"provider": i.provider, "label": i.email or i.subject} for i in rows]
    order = {p: n for n, p in enumerate(PROVIDERS)}
    return sorted(out, key=lambda d: (order.get(d["provider"], len(order)), d["label"]))


# --- email magic links -------------------------------------------------------------------------------
# A mailed single-use token instead of a password. The GET of a link only RENDERS a Continue button; the
# POST consumes it (mail scanners prefetch every URL in an email and would burn the token first).

def _now() -> datetime:
    """UTC now, aware. A function so tests can jump time forward to exercise expiry."""
    return datetime.now(timezone.utc)


def _utc_naive(dt: datetime) -> datetime:
    """The one convention for login_links datetimes: store and compare NAIVE UTC. DateTime columns hand back
    naive values on both SQLite and MySQL, and comparing those against an aware datetime raises — so every
    datetime crosses this boundary on its way into a query or a column."""
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _token_hash(token: str) -> str:
    """Only sha256(token) is stored, so a leaked database is not a stack of live sign-in links."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_code() -> str:
    """A fresh sign-in code: CODE_DIGITS uniform random digits (leading zeros kept)."""
    return f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"


def _code_hash(token_hash: str, code: str) -> str:
    """What login_links.code_hash stores: sha256 over the row's token_hash and the code, so the same code on
    two rows never hashes alike. A million codes are cheap to brute-force from a dump, which is fine — the
    row is dead within 15 minutes and the hash never leaves the server."""
    return hashlib.sha256(f"{token_hash}:{code}".encode("utf-8")).hexdigest()


def _normalize_code(raw) -> str:
    """The digits the person typed ("482 913", "482-913", full-width digits from a CJK keyboard), or "" when
    that is not exactly CODE_DIGITS digits."""
    digits = "".join(str(int(c)) for c in str(raw or "")[:64] if c.isdecimal())
    return digits if len(digits) == CODE_DIGITS else ""


def _format_code(code: str) -> str:
    """482913 -> "482 913": easier to read off one screen and type into another."""
    half = len(code) // 2
    return f"{code[:half]} {code[half:]}"


def _normalize_email(raw: str) -> str:
    """strip().lower(), or "" when it is not plausibly an address. Syntax only — no MX lookup and no
    disposable-domain list: throwaway addresses are deliberately allowed (the IP/global forge caps are the
    abuse backstop), and the caller answers identically either way."""
    email = (raw or "").strip().lower()
    if not email or len(email) > 320 or any(c.isspace() for c in email):
        return ""
    local, sep, domain = email.partition("@")
    if not (sep and local and domain) or "@" in domain:
        return ""
    if "." not in domain or domain.startswith(".") or domain.endswith("."):
        return ""
    return email


def _client_ip() -> str:
    """The caller's address, same derivation as app._client_ip (duplicated rather than imported: app imports
    auth, not the other way round). ProxyFix + BTSWEB_BEHIND_PROXY keep this honest behind nginx."""
    return request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()


def _public_url() -> str:
    """Absolute base for the link inside the email — BTSWEB_PUBLIC_URL when set (the same var app.py embeds
    in import codes), else the host this request arrived on."""
    return (os.environ.get("BTSWEB_PUBLIC_URL", "").strip().rstrip("/")
            or request.url_root.rstrip("/"))


def _send_mail(to: str, subject: str, html: str | None, text: str) -> None:
    """Send one message through Resend's HTTPS API (no SDK — requests is already a dependency). The one mail
    transport: the magic link and the "email my class" hand-off both go through here. `html` is optional —
    the magic link is deliberately text-only (HTML mail and redirect-tracking are what put sign-in links in
    the spam folder). Raises on a non-2xx so the caller decides what the user sees."""
    payload = {"from": os.environ.get("BTSWEB_MAIL_FROM", "").strip(), "to": [to],
               "subject": subject, "text": text}
    if html:
        payload["html"] = html
    resp = requests.post(
        RESEND_ENDPOINT,
        headers={"Authorization": f"Bearer {os.environ.get('RESEND_API_KEY', '').strip()}"},
        json=payload,
        timeout=10)
    resp.raise_for_status()


def _send_magic_link(email: str, url: str, lang: str = "en", code: str = "") -> None:
    """Send one sign-in link and its code. Deliberately plain text, one URL, no tracking pixels or
    click-wrapping (there is no HTML variant). Subject and body are COPY.md's email.magic.* in the language
    the sign-in page was showing (per-key English fallback, web/i18n.py). Module-level so tests can swap it
    for a capture stub."""
    if code:
        body = i18n.get_text(lang, "email.magic.body_code", url=url, code=_format_code(code)) + "\n"
    else:  # a caller without a code (none today) still gets the original link-only body
        body = i18n.get_text(lang, "email.magic.body", url=url) + "\n"
    _send_mail(email, i18n.get_text(lang, "email.magic.subject"), None, body)


class MagicLinkLimiter:
    """Abuse backstop for POST /api/auth/email/start: one lock, bucketed windows, process-local — keep
    gunicorn at one worker.

    Two caps: per normalized email, so the endpoint cannot be used to bomb one person's inbox, and per IP, so
    it cannot be used to bomb everyone's. Over either cap the caller still gets the same "Check your inbox."
    200 with nothing stored and nothing sent — a silent drop, so the endpoint also leaks nothing about who
    has an account. Windows are tumbling buckets (like the limiter's UTC day): cheap, and close enough.
    """

    def __init__(self, per_email: int = 3, email_window_s: int = 15 * 60,
                 per_ip: int = 10, ip_window_s: int = 3600) -> None:
        self.per_email, self.email_window_s = per_email, email_window_s
        self.per_ip, self.ip_window_s = per_ip, ip_window_s
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        """Forget every window — boot state, and what the test harness calls between tests."""
        self._email_bucket, self._email_counts = -1, {}
        self._ip_bucket, self._ip_counts = -1, {}

    def _roll(self, now: float) -> None:
        bucket = int(now // self.email_window_s)
        if bucket != self._email_bucket:
            self._email_bucket, self._email_counts = bucket, {}
        bucket = int(now // self.ip_window_s)
        if bucket != self._ip_bucket:
            self._ip_bucket, self._ip_counts = bucket, {}

    def check(self, email: str, ip: str) -> bool:
        """True if this request may send a link (and counts it); False when either cap is already reached."""
        now = time.time()
        with self._lock:
            self._roll(now)
            if self.per_email > 0 and self._email_counts.get(email, 0) >= self.per_email:
                return False
            if self.per_ip > 0 and self._ip_counts.get(ip, 0) >= self.per_ip:
                return False
            self._email_counts[email] = self._email_counts.get(email, 0) + 1
            self._ip_counts[ip] = self._ip_counts.get(ip, 0) + 1
            return True


magic_limiter = MagicLinkLimiter()
# "Email it to me" (POST /api/classes/<id>/email, phone hand-off): keyed by user id (the address is the
# account's own, so a per-address cap is the same thing), 5 per hour; plus a per-IP hourly backstop.
class_mail_limiter = MagicLinkLimiter(per_email=5, email_window_s=3600, per_ip=20, ip_window_s=3600)
# POST /api/auth/email/code: every attempt counts (right or wrong). 10 per address per 15 minutes is two
# rows' worth of CODE_MAX_ATTEMPTS; 30 per IP per hour stops one address spraying guesses across many
# inboxes. Over a cap the answer is "too_many" whatever the address — no account is revealed by it.
code_limiter = MagicLinkLimiter(per_email=10, email_window_s=15 * 60, per_ip=30, ip_window_s=3600)


def _spend(s, row_id: int, now: datetime) -> bool:
    """Stamp used_at on one login_links row IF it is still unspent and not locked out — a conditional
    UPDATE, so of two racing spends (the link's POST and the code, or two tabs) exactly one sees rowcount 1.
    This is the single place a row is consumed; the link and the code both come through it."""
    res = s.execute(update(LoginLink)
                    .where(LoginLink.id == row_id, LoginLink.used_at.is_(None),
                           LoginLink.code_attempts < CODE_MAX_ATTEMPTS)
                    .values(used_at=now)
                    .execution_options(synchronize_session=False))
    return res.rowcount == 1


def _claim_link(token: str, *, consume: bool) -> str | None:
    """The address a live magic link belongs to, or None when it is unknown, expired, already used (by its
    link OR its code — same row) or locked by CODE_MAX_ATTEMPTS wrong codes. consume=True spends the row
    (_spend), so a link can only ever be spent once."""
    now = _utc_naive(_now())
    with session_scope() as s:
        row = s.query(LoginLink).filter_by(token_hash=_token_hash(token)).one_or_none()
        if (row is None or row.used_at is not None or row.expires_at is None or row.expires_at < now
                or (row.code_attempts or 0) >= CODE_MAX_ATTEMPTS):
            return None
        if consume and not _spend(s, row.id, now):
            return None
        return row.email


def _claim_code(email: str, code: str) -> str:
    """Check a typed sign-in code against the address's live rows and spend the one it matches.

    Returns "ok", "wrong", "expired" or "too_many". Every live row is compared (hmac.compare_digest), because
    someone who asked three times may type the code from any of the three emails. A miss counts one attempt
    against EVERY live row of the address, so the guess budget per address is CODE_MAX_ATTEMPTS, not that
    times the number of links. An address with no rows at all answers "wrong", exactly like a bad code for
    an address that has one, so this cannot tell anyone which addresses asked for a link."""
    now = _utc_naive(_now())
    with session_scope() as s:
        rows = s.query(LoginLink).filter_by(email=email).all()
        if not rows or not code:
            return "wrong"
        unspent = [r for r in rows if r.used_at is None and r.expires_at is not None and r.expires_at >= now
                   and r.code_hash]
        live = [r for r in unspent if (r.code_attempts or 0) < CODE_MAX_ATTEMPTS]
        if not live:
            return "too_many" if unspent else "expired"
        match = None
        for r in live:  # no early exit: every live row costs the same compare
            if hmac.compare_digest(r.code_hash, _code_hash(r.token_hash, code)) and match is None:
                match = r
        if match is not None:
            return "ok" if _spend(s, match.id, now) else "expired"
        s.execute(update(LoginLink)
                  .where(LoginLink.id.in_([r.id for r in live]))
                  .values(code_attempts=LoginLink.code_attempts + 1)
                  .execution_options(synchronize_session=False))
        left = [r for r in live if (r.code_attempts or 0) + 1 < CODE_MAX_ATTEMPTS]
        return "wrong" if left else "too_many"


def require_login(fn):
    """Decorator: 401 JSON for unauthenticated API calls."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            return jsonify(i18n.error_body("server.auth.sign_in_required")), 401
        return fn(*args, **kwargs)
    return wrapper


def init_auth(app) -> None:
    """Register auth routes on the Flask app. Each provider registers with Authlib only if its client
    id/secret are present, so /login offers exactly the buttons this deploy can honour."""
    global _oauth

    if _dev_auth_enabled() and is_production():
        raise RuntimeError(
            "BTSWEB_DEV_AUTH is set while a real sign-in provider is configured — the dev-login bypass must "
            "never be enabled in production. Unset BTSWEB_DEV_AUTH (or the provider credentials for local dev).")

    # Loud about the removed fallback: a deploy that predates BTSWEB_ADMIN_EMAILS used to get its operators
    # from the unlimited list, and would otherwise just quietly lose both operator cards after an update.
    if not ADMIN_EMAILS and UNLIMITED_EMAILS:
        app.logger.warning(
            "BTSWEB_ADMIN_EMAILS is unset, so the Account tab's operator cards (forge stats, user "
            "management) are disabled for everyone. Set it to the operator addresses to restore them; it "
            "no longer defaults to BTSWEB_UNLIMITED_EMAILS.")

    registrations = {
        "google": dict(server_metadata_url=GOOGLE_METADATA,
                       client_kwargs={"scope": "openid email profile"}),
        "discord": dict(authorize_url="https://discord.com/oauth2/authorize",
                        access_token_url="https://discord.com/api/oauth2/token",
                        api_base_url="https://discord.com/api/",
                        client_kwargs={"scope": "identify email"}),
        "github": dict(authorize_url="https://github.com/login/oauth/authorize",
                       access_token_url="https://github.com/login/oauth/access_token",
                       api_base_url="https://api.github.com/",
                       client_kwargs={"scope": "read:user user:email"}),
    }
    for provider in configured_providers():
        client_id, client_secret = _credentials(provider)
        if _oauth is None:
            from authlib.integrations.flask_client import OAuth
            _oauth = OAuth(app)
        _oauth.register(name=provider, client_id=client_id, client_secret=client_secret,
                        **registrations[provider])

    def _client(provider: str):
        """The registered Authlib client, or None when this deploy has no credentials for it."""
        return None if _oauth is None else getattr(_oauth, provider, None)

    @app.route("/login")
    def login():
        """The chooser page: one button per configured provider (signin.js reads /api/me.providers).

        A signed-in visitor is bounced to the app UNLESS ?link=1 — that is the Account tab's "link another
        sign-in", where the point is to run a provider flow while signed in so the new identity attaches to
        this account (_resolve_identity rule 2). signin.js renders that case as "Link another sign-in"."""
        if current_user() is not None and request.args.get("link") != "1":
            return redirect("/app")
        return send_from_directory(app.static_folder, "signin.html")

    @app.route("/login/<provider>")
    def login_provider(provider):
        if provider not in PROVIDERS:
            return (i18n.get_text("en", "server.auth.unknown_provider"), 404)
        client = _client(provider)
        if client is None:
            return (i18n.get_text("en", "server.auth.provider_not_configured", provider=provider.title()), 503)
        # Google still returns to the legacy /auth/callback: that is the only URI the Google console lists,
        # and a redirect_uri it does not know is a hard "redirect_uri_mismatch" for every Google sign-in. Point
        # this at auth_provider_callback once the console also lists /auth/google/callback (DEPLOY §7).
        if provider == "google":
            return client.authorize_redirect(url_for("auth_callback", _external=True))
        return client.authorize_redirect(
            url_for("auth_provider_callback", provider=provider, _external=True))

    @app.route("/auth/<provider>/callback")
    def auth_provider_callback(provider):
        if provider not in PROVIDERS:
            return (i18n.get_text("en", "server.auth.unknown_provider"), 404)
        client = _client(provider)
        if client is None:
            return (i18n.get_text("en", "server.auth.provider_not_configured", provider=provider.title()), 503)
        token = client.authorize_access_token()
        profile = _PROFILE[provider](client, token)
        # current_user_id is "link another provider while signed in" (rule 2): a signed-in user who runs the
        # flow attaches the identity rather than splitting into a second account. Deliberate: if the identity
        # already belongs to someone ELSE, rule 1 wins and this signs in as that other user — plain sign-in
        # semantics. We never merge two accounts behind the user's back (that stays a support action).
        signed_in_as = (current_user() or {}).get("id")
        user = _resolve_identity(profile, current_user_id=signed_in_as)
        _login_session(user)
        return redirect(_landing(user, signed_in_as))

    @app.route("/auth/callback")
    def auth_callback():
        """Legacy Google redirect URI — the Google console still points here. Remove once it also lists
        /auth/google/callback (see DEPLOY-DIGITALOCEAN.md §7)."""
        return auth_provider_callback("google")

    @app.route("/api/auth/email/start", methods=["POST"])
    def api_email_start():
        """Ask for a magic link. The answer is ALWAYS the same 200 body — link sent, rate-limited, or
        gibberish in the box — so the endpoint cannot be used to probe who has an account or to confirm a
        send. It lives under /api/ so app.py's X-Requested-With guard already covers it."""
        if not email_login_enabled():
            return jsonify(i18n.error_body("server.auth.email_not_configured")), 503
        answer = {"ok": True, "message": i18n.get_text("en", "server.auth.check_inbox")}
        start_body = request.get_json(silent=True)
        if not isinstance(start_body, dict):
            start_body = {}
        email = _normalize_email(start_body.get("email", ""))
        # The language the sign-in page was showing ("en" | "zh"; anything else is English) picks the email's
        # subject and body. Not stored: the link itself is language-free.
        lang = i18n.normalize_lang(start_body.get("lang"))
        ip = _client_ip()
        if not email or not magic_limiter.check(email, ip):
            return jsonify(answer)

        token = secrets.token_urlsafe(32)
        code = _new_code()
        now = _now()
        with session_scope() as s:
            # Sweep: a day-old row is dead whether it was used or abandoned. Cheap, and it keeps the table
            # from growing forever without a cron job.
            s.query(LoginLink).filter(
                LoginLink.created_at < _utc_naive(now - LINK_SWEEP_AFTER)).delete(synchronize_session=False)
            # created_at is set explicitly (rather than left to server_default) so every row in the table is
            # naive UTC on MySQL too, which is what the sweep and the expiry check compare against.
            s.add(LoginLink(email=email, token_hash=_token_hash(token), ip=ip,
                            code_hash=_code_hash(_token_hash(token), code), code_attempts=0,
                            created_at=_utc_naive(now), expires_at=_utc_naive(now + LINK_TTL)))
        url = f"{_public_url()}/auth/email/{token}"

        if mail_configured():
            try:
                _send_magic_link(email, url, lang=lang, code=code)
            except Exception as exc:  # a dead mail provider must not change the answer (or leak a stacktrace)
                app.logger.warning("magic-link send failed for %s: %s", email, exc)
            return jsonify(answer)
        # No mail configured ⇒ email_login_enabled() only said yes because of the dev bypass: hand the link
        # and its code back (this JSON is the dev "mailbox" — the UI smoke reads the code from it), and log
        # both for the terminal.
        app.logger.info("magic sign-in link for %s: %s (code %s)", email, url, code)
        return jsonify({**answer, "link": url, "code": code})

    @app.route("/api/auth/email/code", methods=["POST"])
    def api_email_code():
        """Sign in with the code from the magic-link email, typed into the tab where sign-in started.

        Body {email, code}. Success: the row is spent (the link dies with it), the session is set exactly as
        the link's POST sets it, and the answer is {ok: true, next: "/app"} (or /app#account in link mode).
        Failure is a 200 {ok: false, reason: "wrong" | "expired" | "too_many"}; an unknown address is
        "wrong", same as a bad code. Under /api/, so app.py's X-Requested-With guard covers it (CSRF)."""
        if not email_login_enabled():
            return jsonify(i18n.error_body("server.auth.email_not_configured")), 503
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            body = {}
        email = _normalize_email(body.get("email", ""))
        code = _normalize_code(body.get("code", ""))
        if not code_limiter.check(email, _client_ip()):
            return jsonify({"ok": False, "reason": "too_many"})
        result = _claim_code(email, code) if email else "wrong"
        if result != "ok":
            return jsonify({"ok": False, "reason": result})
        # The same door as the link's POST below: the code proves the inbox just as the click does.
        signed_in_as = (current_user() or {}).get("id")
        user = _resolve_identity(Profile("email", email, email, True, email.split("@")[0]),
                                 current_user_id=signed_in_as)
        _login_session(user)
        return jsonify({"ok": True, "next": _landing(user, signed_in_as)})

    @app.route("/auth/email/<token>", methods=["GET", "POST"])
    def auth_email(token):
        """GET renders a Continue button; POST consumes the token and signs in.

        The GET must never consume: Gmail's link scanner, Outlook SafeLinks and corporate proxies fetch every
        URL in an email, which would burn a single-use token before the person clicked it.
        The POST is deliberately NOT under /api/, so the X-Requested-With guard does not apply — a cross-site
        form could submit it, but that only signs the ATTACKER's own browser into the account whose owner
        asked for the link, and only if the attacker already holds the token (which only the inbox has)."""
        email = _claim_link(token, consume=request.method == "POST")
        if email is None:
            return send_from_directory(app.static_folder, "signin-expired.html"), 410
        if request.method == "GET":
            return send_from_directory(app.static_folder, "signin-continue.html")
        # A clicked link is proof of the address (that is the whole point), so email_verified=True — which
        # lets rule 3 hand this person their existing Google/Discord account. current_user_id is the
        # "link while signed in" path (rule 2), and lands on the Account tab when it attached there.
        signed_in_as = (current_user() or {}).get("id")
        user = _resolve_identity(Profile("email", email, email, True, email.split("@")[0]),
                                 current_user_id=signed_in_as)
        _login_session(user)
        return redirect(_landing(user, signed_in_as))

    @app.route("/logout", methods=["POST"])
    def logout():
        """POST-only: a GET link on a third-party page must not be able to sign someone out (CSRF)."""
        session.clear()
        return redirect("/")

    @app.route("/api/me")
    def api_me():
        user = current_user()
        if user is not None:
            with session_scope() as s:
                row = s.query(User).filter_by(id=user["id"]).one_or_none()
                bal = int(row.token_balance) if row is not None else 0
                # Effective unlimited (env list or the operator-granted flag) off the SAME row we just read
                # for the balance — one query, and it reflects a grant made seconds ago without a re-login.
                unlimited = user_is_unlimited(row)
                # A sign-up event bonus the browser has not been told about yet: handed out ONCE (seen_at is
                # stamped here), so the welcome notice does not reappear on every page load.
                welcome = None
                g = (s.query(PromoGrant, Promotion.label)
                     .join(Promotion, Promotion.id == PromoGrant.promo_id)
                     .filter(PromoGrant.user_id == user["id"], PromoGrant.seen_at.is_(None))
                     .order_by(PromoGrant.id).first())
                if g is not None:
                    grant, label = g
                    welcome = {"label": label or "", "tokens": int(grant.tokens or 0)}
                    grant.seen_at = _utc_naive(_now())
            user = {**user, "token_balance": bal,
                    "unlimited": unlimited,
                    "welcome_grant": welcome,
                    "admin": is_admin(user.get("email", "")),
                    "identities": _identities_of(user["id"])}
        # email_login gates signin.js's email form: mail configured, or the dev bypass standing in for it.
        # mail: this deploy can send mail (Resend) — gates the "Email it to me" class hand-off button.
        return jsonify({"user": user, "dev_auth": _dev_auth_enabled(),
                        "providers": configured_providers(), "email_login": email_login_enabled(),
                        "mail": mail_configured()})

    if _dev_auth_enabled():
        @app.route("/dev-login")
        def dev_login():
            """LOCAL ONLY. Logs in a fake user by email so multi-user flows can be tested without OAuth.
            The route does not exist at all (404) unless BTSWEB_DEV_AUTH is on — and the boot guard above
            ensures that flag can never coexist with real OAuth."""
            email = request.args.get("email", "dev@example.com")
            name = request.args.get("name", email.split("@")[0])
            user = _resolve_identity(Profile("dev", email, email, True, name))
            _login_session(user)
            return redirect("/app")
