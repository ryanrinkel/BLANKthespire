"""Google OAuth sign-in (Authlib over Flask sessions) + a dev-login bypass for local verification.

Production: real Google OAuth. Set GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET (cPanel env secrets). On first
login we upsert a `users` row keyed by the Google `sub`. Sessions are server-signed cookies; no passwords.

Local dev: set BTSWEB_DEV_AUTH=1 to expose /dev-login?email=... which logs in a fake user WITHOUT Google —
so the per-user library flow is testable with no credentials. Fail-closed: the route is only registered when
the flag is on, and the app refuses to boot if the flag is on while Google OAuth is configured (a
production-looking deploy must never carry the bypass).
"""
from __future__ import annotations

import functools
import os

from flask import jsonify, redirect, request, session, url_for

from db import session_scope
from models import User, grant_daily_token

GOOGLE_METADATA = "https://accounts.google.com/.well-known/openid-configuration"
_oauth = None  # set by init_auth when real OAuth is configured

# Master list of accounts that forge on the token path WITHOUT spending tokens (you, testers). Comma-separated
# Google emails in BTSWEB_UNLIMITED_EMAILS. Empty/unset ⇒ no one is unlimited (everyone spends their balance).
UNLIMITED_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("BTSWEB_UNLIMITED_EMAILS", "").split(",")
    if e.strip()
}


def is_unlimited(email: str) -> bool:
    """True if this email is on the unlimited-tokens master list (never decremented on the token path)."""
    return (email or "").strip().lower() in UNLIMITED_EMAILS


def _dev_auth_enabled() -> bool:
    return os.environ.get("BTSWEB_DEV_AUTH", "").strip() in ("1", "true", "yes")


def _upsert_user(google_sub: str, email: str, name: str) -> dict:
    """Find-or-create a user by Google sub; return a plain dict (detached from the session)."""
    with session_scope() as s:
        user = s.query(User).filter_by(google_sub=google_sub).one_or_none()
        if user is None:
            user = User(google_sub=google_sub, email=email or "", name=name or "")
            s.add(user)
            s.flush()
        else:  # keep email/name fresh
            user.email, user.name = email or user.email, name or user.name
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

    if _dev_auth_enabled() and client_id:
        raise RuntimeError(
            "BTSWEB_DEV_AUTH is set while Google OAuth is configured — the dev-login bypass must never be "
            "enabled in production. Unset BTSWEB_DEV_AUTH (or GOOGLE_CLIENT_ID/SECRET for local dev).")

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
        user = _upsert_user(info["sub"], info.get("email", ""), info.get("name", ""))
        _login_session(user)
        return redirect("/app")

    @app.route("/logout", methods=["POST", "GET"])
    def logout():
        session.clear()
        return redirect("/")

    @app.route("/api/me")
    def api_me():
        user = current_user()
        if user is not None:
            with session_scope() as s:
                row = s.query(User).filter_by(id=user["id"]).one_or_none()
                if row is not None:
                    grant_daily_token(row)  # donation model: refill an empty balance once per day
                bal = int(row.token_balance) if row is not None else 0
            user = {**user, "token_balance": bal, "unlimited": is_unlimited(user.get("email", ""))}
        return jsonify({"user": user, "dev_auth": _dev_auth_enabled()})

    if _dev_auth_enabled():
        @app.route("/dev-login")
        def dev_login():
            """LOCAL ONLY. Logs in a fake user by email so multi-user flows can be tested without Google.
            The route does not exist at all (404) unless BTSWEB_DEV_AUTH is on — and the boot guard above
            ensures that flag can never coexist with real OAuth."""
            email = request.args.get("email", "dev@example.com")
            name = request.args.get("name", email.split("@")[0])
            user = _upsert_user(f"dev:{email}", email, name)
            _login_session(user)
            return redirect("/app")
