"""Sign-in (Authlib over Flask sessions) + a dev-login bypass for local verification.

Google, Discord and GitHub each register with Authlib only when their `<PROVIDER>_CLIENT_ID`/`_SECRET` pair is
set, so a box with one provider's credentials offers exactly one button. Every path — the three OAuth
providers, the dev bypass, and whatever comes later — builds a Profile and funnels through _resolve_identity,
which maps one (provider, subject) identity onto a `users` row. Sessions are server-signed cookies; no
passwords.

Local dev: set BTSWEB_DEV_AUTH=1 to expose /dev-login?email=... which logs in a fake user WITHOUT OAuth —
so the per-user library flow is testable with no credentials. Fail-closed: the route is only registered when
the flag is on, and the app refuses to boot if the flag is on while a real sign-in provider is
configured (a production-looking deploy must never carry the bypass).
"""
from __future__ import annotations

import functools
import os
from dataclasses import dataclass

from flask import jsonify, redirect, request, send_from_directory, session, url_for

from db import session_scope
from models import Identity, User, free_token_available

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


# The OAuth providers, in the order the chooser page shows them. A provider is "configured" (and gets a
# button) only when both halves of its env pair are set.
PROVIDERS = ("google", "discord", "github")

# Env vars whose presence means a real sign-in provider is configured — i.e. a production-looking deploy, not
# a keyless local box. Adding a provider (mail, ...) means adding its id here, and every boot guard follows
# automatically.
PROVIDER_ENV_VARS = ("GOOGLE_CLIENT_ID", "DISCORD_CLIENT_ID", "GITHUB_CLIENT_ID")


def is_production() -> bool:
    """True once ANY sign-in provider is configured. The fail-closed boot guards (the session secret key in
    app.py, the dev-login conflict below) key off this rather than one provider's client id, so they keep
    covering every provider as more are added."""
    return any(os.environ.get(v, "").strip() for v in PROVIDER_ENV_VARS)


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


def _identities_of(user_id: int) -> list[dict]:
    """{provider, label} per linked identity, for the Account tab. The label is the identity's email when the
    provider gave one, else its subject — enough to tell two accounts apart."""
    with session_scope() as s:
        rows = s.query(Identity).filter_by(user_id=user_id).all()
        out = [{"provider": i.provider, "label": i.email or i.subject} for i in rows]
    order = {p: n for n, p in enumerate(PROVIDERS)}
    return sorted(out, key=lambda d: (order.get(d["provider"], len(order)), d["label"]))


def require_login(fn):
    """Decorator: 401 JSON for unauthenticated API calls."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            return jsonify({"error": "sign in required"}), 401
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
        """The chooser page: one button per configured provider (signin.js reads /api/me.providers)."""
        if current_user() is not None:
            return redirect("/app")
        return send_from_directory(app.static_folder, "signin.html")

    @app.route("/login/<provider>")
    def login_provider(provider):
        if provider not in PROVIDERS:
            return ("Unknown sign-in provider.", 404)
        client = _client(provider)
        if client is None:
            return (f"{provider.title()} sign-in is not configured on this server.", 503)
        return client.authorize_redirect(
            url_for("auth_provider_callback", provider=provider, _external=True))

    @app.route("/auth/<provider>/callback")
    def auth_provider_callback(provider):
        if provider not in PROVIDERS:
            return ("Unknown sign-in provider.", 404)
        client = _client(provider)
        if client is None:
            return (f"{provider.title()} sign-in is not configured on this server.", 503)
        token = client.authorize_access_token()
        profile = _PROFILE[provider](client, token)
        # current_user_id is Phase 3's "link another provider while signed in" (rule 2) — free here, and it
        # means a signed-in user who runs the flow again attaches rather than splitting into a second account.
        user = _resolve_identity(profile, current_user_id=(current_user() or {}).get("id"))
        _login_session(user)
        return redirect("/app")

    @app.route("/auth/callback")
    def auth_callback():
        """Legacy Google redirect URI — the Google console still points here. Remove once it also lists
        /auth/google/callback (see DEPLOY-DIGITALOCEAN.md §7)."""
        return auth_provider_callback("google")

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
                    "unlimited": is_unlimited(user.get("email", "")),
                    "identities": _identities_of(user["id"])}
        # email_login flips on in Phase 2 (the magic link); signin.js keeps its form hidden until then.
        return jsonify({"user": user, "dev_auth": _dev_auth_enabled(),
                        "providers": configured_providers(), "email_login": False})

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
