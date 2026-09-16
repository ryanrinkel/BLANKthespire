"""Sign-in (Authlib over Flask sessions) + a dev-login bypass for local verification.

Google is the only real provider today, but every path — Google, the dev bypass, and the providers added
later — builds a Profile and funnels through _resolve_identity, which maps one (provider, subject) identity
onto a `users` row. Set GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET to enable Google. Sessions are server-signed
cookies; no passwords.

Local dev: set BTSWEB_DEV_AUTH=1 to expose /dev-login?email=... which logs in a fake user WITHOUT Google —
so the per-user library flow is testable with no credentials. Fail-closed: the route is only registered when
the flag is on, and the app refuses to boot if the flag is on while a real sign-in provider is
configured (a production-looking deploy must never carry the bypass).
"""
from __future__ import annotations

import functools
import os
from dataclasses import dataclass

from flask import jsonify, redirect, request, session, url_for

from db import session_scope
from models import Identity, User, free_token_available

GOOGLE_METADATA = "https://accounts.google.com/.well-known/openid-configuration"
_oauth = None  # set by init_auth when real OAuth is configured

# Master list of accounts that forge on the token path WITHOUT spending tokens (you, testers). Comma-separated
# addresses in BTSWEB_UNLIMITED_EMAILS, matched against users.email (which only ever holds a provider-VERIFIED
# address — see _resolve_identity). Empty/unset ⇒ no one is unlimited (everyone spends their balance).
UNLIMITED_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("BTSWEB_UNLIMITED_EMAILS", "").split(",")
    if e.strip()
}


# Env vars whose presence means a real sign-in provider is configured — i.e. a production-looking deploy, not
# a keyless local box. Adding a provider (Discord, GitHub, mail) means adding its id here, and every boot
# guard follows automatically.
PROVIDER_ENV_VARS = ("GOOGLE_CLIENT_ID",)


def is_production() -> bool:
    """True once ANY sign-in provider is configured. The fail-closed boot guards (the session secret key in
    app.py, the dev-login conflict below) key off this rather than one provider's client id, so they keep
    covering every provider as more are added."""
    return any(os.environ.get(v, "").strip() for v in PROVIDER_ENV_VARS)


def is_unlimited(email: str) -> bool:
    """True if this email is on the unlimited-tokens master list (never decremented on the token path)."""
    return (email or "").strip().lower() in UNLIMITED_EMAILS


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
        elif p.email_verified:
            user.email = email or user.email
            user.name = p.name or user.name
        if ident is None:
            s.add(Identity(user_id=user.id, provider=p.provider, subject=p.subject, email=email))
        elif email and ident.email != email:
            ident.email = email
        return {"id": user.id, "email": user.email, "name": user.name}


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
    session.permanent = True


def require_login(fn):
    """Decorator: 401 JSON for unauthenticated API calls."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            return jsonify({"error": "sign in required"}), 401
        return fn(*args, **kwargs)
    return wrapper


def init_auth(app) -> None:
    """Register auth routes on the Flask app. Real OAuth registers only if client id/secret are present."""
    global _oauth
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")

    if _dev_auth_enabled() and is_production():
        raise RuntimeError(
            "BTSWEB_DEV_AUTH is set while a real sign-in provider is configured — the dev-login bypass must "
            "never be enabled in production. Unset BTSWEB_DEV_AUTH (or the provider credentials for local dev).")

    if client_id and client_secret:
        from authlib.integrations.flask_client import OAuth
        _oauth = OAuth(app)
        _oauth.register(
            name="google",
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url=GOOGLE_METADATA,
            client_kwargs={"scope": "openid email profile"},
        )

    @app.route("/login")
    def login():
        if _oauth is None:
            return ("Google sign-in is not configured (set GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET).", 503)
        return _oauth.google.authorize_redirect(url_for("auth_callback", _external=True))

    @app.route("/auth/callback")
    def auth_callback():
        if _oauth is None:
            return ("Google sign-in is not configured.", 503)
        token = _oauth.google.authorize_access_token()
        info = token.get("userinfo") or _oauth.google.parse_id_token(token, nonce=None)
        user = _resolve_identity(Profile("google", info["sub"], info.get("email", ""),
                                         bool(info.get("email_verified")), info.get("name", "")))
        _login_session(user)
        return redirect("/app")

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
                free = bool(row is not None and free_token_available(row))
            user = {**user, "token_balance": bal, "free_token_available": free,
                    "unlimited": is_unlimited(user.get("email", ""))}
        return jsonify({"user": user, "dev_auth": _dev_auth_enabled()})

    if _dev_auth_enabled():
        @app.route("/dev-login")
        def dev_login():
            """LOCAL ONLY. Logs in a fake user by email so multi-user flows can be tested without Google.
            The route does not exist at all (404) unless BTSWEB_DEV_AUTH is on — and the boot guard above
            ensures that flag can never coexist with real OAuth."""
            email = request.args.get("email", "dev@example.com")
            name = request.args.get("name", email.split("@")[0])
            user = _resolve_identity(Profile("dev", email, email, True, name))
            _login_session(user)
            return redirect("/app")
