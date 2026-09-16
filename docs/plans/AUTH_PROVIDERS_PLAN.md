# Sign-in providers — Discord, GitHub, email magic link — PLAN

Status: **BUILT 2026-09-16** on branch `auth-providers` (Phases 0-3, 100 web tests green), not yet merged or
deployed. Still manual: Discord app + two GitHub OAuth apps (Phase 1 portal setup), Resend account + DNS (Phase 2).
Deviation: `/login/google` keeps returning to the legacy `/auth/callback` until the Google console lists
`/auth/google/callback` (see DEPLOY-DIGITALOCEAN.md §7). Originally: PLANNED 2026-09-16, nothing built. Written against `web/auth.py`, `web/models.py`,
`web/db.py`, `web/app.py`, `web/static/{landing,index}.html` as of v0.2.0 (the live droplet).

## Why

Today the only way in is "Sign in with Google" (Authlib OIDC, `web/auth.py`). Users keyed by the Google
`sub`, signed-cookie sessions, no passwords. That is the right shape — we keep it — but a modding community
lives on Discord and GitHub, and some people have neither account, or would rather use a throwaway. The
decision (Ryan, 2026-09-16): **support all of Discord, GitHub and email magic links. Throwaway email
accounts are explicitly fine; if someone cares enough to farm the free daily token, let them.** The existing
`FreeForgeLimiter` (5 free forges per IP per UTC day, global `BTSWEB_TOKEN_DAILY_CAP`) stays as the bill
backstop and nothing stricter is added.

No hosted auth vendor (Auth0/Clerk/Supabase/Firebase) and no passwords. Authlib is already a dependency and
does Discord and GitHub in ~15 lines each; the magic link is ~150 lines of our own.

## Shape after the change

```
/login                       chooser page: [Discord] [GitHub] [Google] + email form   (static/signin.html)
/login/<provider>            start OAuth (google|discord|github)
/auth/<provider>/callback    OAuth return          (/auth/callback stays as the Google alias — see risks)
POST /api/auth/email/start   {email} -> sends a magic link (always 200, "check your inbox")
GET  /auth/email/<token>     renders a "Continue" button (mail scanners prefetch GETs — never consume on GET)
POST /auth/email/<token>     consumes the token, signs in, -> /app
POST /logout                 unchanged
GET  /api/me                 gains "providers": [...configured...] and "identities": [{provider, label}]
```

Data model: one `users` row can own many `identities` rows. `(provider, subject)` is unique. Sign-in resolves
an identity to a user; the user is what tokens and classes hang off, exactly as today.

## The one rule that matters: `_resolve_identity`

Every provider (Google, Discord, GitHub, email, dev) funnels into ONE function in `auth.py`:

```python
@dataclass
class Profile:
    provider: str          # "google" | "discord" | "github" | "email" | "dev"
    subject: str           # provider's stable id (Google sub, Discord snowflake, GitHub numeric id, the email itself)
    email: str             # "" if the provider gave none
    email_verified: bool   # ONLY True when the provider vouches for it
    name: str

def _resolve_identity(p: Profile, *, current_user_id: int | None) -> dict:
    """Identity -> user. In order:
    1. identities(provider, subject) exists            -> that user  (normal repeat sign-in)
    2. current_user_id is set (link-while-signed-in)   -> attach identity to the current user
    3. p.email_verified and exactly one users.email == lower(p.email) -> attach identity to THAT user
       (a Google user who picks Discord next week keeps their tokens and classes)
    4. otherwise                                       -> new user + identity
    users.email / users.name are refreshed from the profile ONLY when email_verified (see security note)."""
```

**Security note (found while reading the code):** `is_unlimited(email)` and `BTSWEB_UNLIMITED_EMAILS` gate
unlimited forging on `users.email`. If an UNVERIFIED provider email were ever written into `users.email`, a
Discord account claiming `you@example.com` (Discord lets you set any address until you verify it) would forge
for free forever. So: unverified emails are never stored and never used for linking. Discord's `/users/@me`
returns `verified`; GitHub's `/user/emails` returns `verified` per address; Google's ID token has
`email_verified`; the magic link is verified by construction (they clicked it). Add a unit test that pins this.

## Phases

Each phase is independently deployable (`ssh blankdroplet`, `sudo /opt/btsweb/deploy.sh` — it runs
`web/tests` before restarting). Ship 0 alone first: it changes the schema on prod MySQL with no visible
behavior change, so a migration problem surfaces without a UI change tangled in.

### Phase 0 — identities table + resolver (Google keeps working, nothing visible changes)

- `models.py`: `class Identity(Base)`: `id`, `user_id` (FK users, CASCADE, index), `provider` VARCHAR(16),
  `subject` VARCHAR(255), `email` VARCHAR(320) default "", `created_at`; `UniqueConstraint(provider, subject)`.
  `User.identities` relationship. Keep `users.google_sub` (NOT NULL UNIQUE on prod MySQL; SQLite cannot relax
  nullability with ALTER and we have no Alembic) — it becomes a legacy column: new rows get
  `f"{provider}:{subject}"` (the dev bypass already writes `dev:<email>`), legacy rows keep the raw Google sub,
  and **nothing reads it after this phase except the backfill**.
- `db.py`: `_ensure_identities()` next to `_ensure_user_columns`: after `create_all`, for every user with no
  identity row, insert one from `google_sub` (`dev:x` -> provider `dev`, subject `x`; anything else ->
  provider `google`, subject as-is). Idempotent, runs every boot, SQLite + MySQL.
- `auth.py`: `Profile`, `_resolve_identity`; `_login_session` unchanged. Google callback builds a Profile from
  the ID token (`sub`, `email`, `email_verified`, `name`). `/dev-login` builds `Profile("dev", email, email,
  True, name)`. Delete `_upsert_user`.
- Boot guards in `app.py` + `auth.py` generalize from "is GOOGLE_CLIENT_ID set" to `auth.is_production()` =
  any OAuth client id set OR mail configured. Both the secret-key check and the dev-auth conflict use it.
- Tests (`web/tests/test_auth.py`, new): resolver cases 1-4 above; verified-only email write; backfill on a
  users table seeded with a legacy `google_sub` and a `dev:` row; existing dev-login tests still pass.
  `test_tokens.py` constructs `User(google_sub="x")` directly — still valid.

### Phase 1 — Discord + GitHub

- Portal setup (manual, ~15 min):
  - Discord Developer Portal -> New Application -> OAuth2: redirects `https://blankthespire.com/auth/discord/callback`
    and `http://localhost:5000/auth/discord/callback`. Scopes `identify email`.
  - GitHub -> Settings -> Developer settings -> OAuth Apps. **A GitHub OAuth App allows exactly one callback URL**,
    so make two apps ("BLANK the spire" and "BLANK the spire (local)") and put the local pair in `web/.env`.
    Scope `read:user user:email`.
  - Google Cloud console: add `https://blankthespire.com/auth/google/callback` as a second authorized redirect
    (keep the old one until the alias is removed).
- `auth.py`: register with Authlib when the env pair is present:
  ```
  DISCORD: authorize_url https://discord.com/oauth2/authorize
           access_token_url https://discord.com/api/oauth2/token
           api_base_url https://discord.com/api/   scope "identify email"
           profile: GET users/@me -> Profile("discord", id, email, verified, global_name or username)
  GITHUB:  authorize_url https://github.com/login/oauth/authorize
           access_token_url https://github.com/login/oauth/access_token
           api_base_url https://api.github.com/   scope "read:user user:email"
           profile: GET user -> id, name/login; GET user/emails -> the primary+verified address (email on
           /user is null for private-email accounts) -> Profile("github", str(id), email, True-if-found, name)
  ```
  One `_profile_<provider>(client, token) -> Profile` per provider, so tests feed fake token/JSON and never
  touch the network. Generic routes `/login/<provider>` (404 for unknown, 503 for unconfigured) and
  `/auth/<provider>/callback`; `/login` now serves the chooser; `/auth/callback` stays as a Google alias.
- `/api/me` gains `providers` (configured list, in display order) and `email_login: bool`.
- Frontend: new `static/signin.html` + `static/signin.js` (CSP forbids inline script). Buttons render only for
  providers `/api/me` reports. `landing.js` keeps its already-signed-in / dev shortcut and otherwise points at
  `/login`. `index.html` gate: the single Google button becomes "Sign in" -> `/login`; drop the
  "Sign in with Google" copy. Style: reuse `.btn.primary` / `.btn.ghost`, one column, provider name only, no
  brand icons needed for v1.
- `privacy.html`: "Account" bullet becomes provider-neutral; subprocessor list gains Discord and GitHub.
- `.env.example`, `DEPLOY-DIGITALOCEAN.md` §4, `README.md`: `DISCORD_CLIENT_ID/SECRET`, `GITHUB_CLIENT_ID/SECRET`.
- Tests: monkeypatch `authorize_access_token` + the profile fetch per provider; callback with a new Discord
  user creates user+identity; callback with a verified email matching an existing Google user links (same
  `user_id`, tokens intact); unverified Discord email does NOT link and does NOT populate `users.email`;
  `/login/steam` -> 404; `/login/discord` -> 503 when unconfigured.

### Phase 2 — email magic link

- Mail provider: **Resend** over plain HTTPS with `requests` (already a dep, no SDK). Free tier covers this
  scale. Env: `RESEND_API_KEY`, `BTSWEB_MAIL_FROM=sign-in@blankthespire.com`. Unset -> email login is
  disabled (button hidden, `/api/auth/email/start` -> 503) **except** under `BTSWEB_DEV_AUTH`, where the link
  is logged and also returned in the JSON so local dev and tests need no mail at all.
- DNS (manual, the slow part — start it first, propagation can take hours): add Resend's SPF, DKIM and a
  `p=none` DMARC record for `blankthespire.com` (DigitalOcean DNS). Without DKIM the links land in spam.
- `models.py`: `class LoginLink(Base)`: `id`, `email` (normalized, index), `token_hash` CHAR(64) unique,
  `ip` VARCHAR(64), `created_at`, `expires_at`, `used_at` nullable. The raw token (32 bytes,
  `secrets.token_urlsafe`) exists only inside the email; we store `sha256(token)`.
- `auth.py`:
  - `POST /api/auth/email/start` (under `/api/` so the existing `X-Requested-With` CSRF guard covers it):
    normalize `strip().lower()`, syntax check (one `@`, a dot after it, <= 320 chars — no MX lookup, no
    disposable-domain list, per the decision above), rate limit, insert row (15 min expiry), send, and
    **always** return `{"ok": true, "message": "Check your inbox."}` so the response is uniform.
  - Rate limit: a process-local `MagicLinkLimiter` shaped like `FreeForgeLimiter`: 3 per email per 15 min,
    10 per IP per hour; over -> same 200 message, nothing sent (silent, so the endpoint cannot be used to
    spam someone's inbox or to probe). One gunicorn worker, as everything else here assumes.
  - `GET /auth/email/<token>`: look up by hash; expired/used/unknown -> a friendly "link expired, request a
    new one" page. Valid -> `static/signin-continue.html` with a single "Continue to BLANK the spire" form
    button (`form-action 'self'` is already in the CSP). **The GET never consumes the token**: Outlook
    SafeLinks, Gmail's link scanner and some corporate proxies fetch every link in an email, which would
    burn a single-use token before the person clicks.
  - `POST /auth/email/<token>`: re-check, set `used_at`, `_resolve_identity(Profile("email", email, email,
    True, email.split("@")[0]))`, `_login_session`, redirect `/app`. Single-use; a second POST -> expired page.
  - Sweep: on each start-request, delete rows older than 24 h (cheap, keeps the table from growing forever).
  - Email body: plain text, subject "Your BLANK the spire sign-in link", one URL, "expires in 15 minutes, ignore
    if you didn't ask". From `BTSWEB_MAIL_FROM`. Keep it plain — HTML mail and tracking hurt deliverability.
- `signin.html`: email input + "Email me a link" button; on success swap to "Check your inbox" copy. Under
  dev auth show the returned link inline (so the local loop is one click).
- Free daily token: email accounts get it like everyone else. Per the decision, no extra gating; the IP cap and
  global cap already exist. Note for later if it ever matters: `FreeForgeLimiter` could be told the identity
  provider and cap `email` accounts harder without touching anything else.
- `privacy.html`: add Resend as a subprocessor (email address, for sign-in mail only) and mention the sign-in
  email is the account's address for deletion requests.
- Tests: start -> row created, mail stub captured a URL, response uniform; GET does not consume; POST signs
  in, second POST fails; expiry honored (monkeypatch time); rate limiter drops silently; email with a
  verified Google user links to it; bad syntax -> still 200, no row; under dev auth the link is in the JSON.

### Phase 3 — link another provider while signed in + Account tab

- `/login/<provider>` when already signed in: the callback's `_resolve_identity(..., current_user_id=uid)`
  attaches the new identity to the current user (rule 2). If the identity already belongs to someone else,
  sign in as that user — plain sign-in semantics, no merging of two accounts (that is a support action, and
  the honest answer today is "email us"). Same for a magic link consumed while signed in.
- Account tab (`index.html` / `app.js`): "Signed in with: Google (r…@gmail.com), Discord (ryan)" from
  `/api/me.identities`, plus "Link another: [Discord] [GitHub] [Email]". No unlinking in v1 (a user with one
  identity could lock themselves out; add it only with a "must keep at least one" rule later).
- Tests: link while signed in -> two identities, one user; sign in with the second provider later -> same user.

## Rollout order

1. Phase 0, deploy, watch `/healthz` and one Google sign-in on prod (identity row appears, tokens unchanged).
2. Start the Resend DNS records now (Phase 2 dependency with the longest wall-clock).
3. Phase 1, deploy. Announce Discord/GitHub sign-in.
4. Phase 2 once DKIM verifies. Send a test link to a Gmail and an Outlook address and check the spam folder
   before announcing.
5. Phase 3 whenever.

Rough effort: Phase 0 ~2 h, Phase 1 ~3 h + portal clicks, Phase 2 ~4 h + DNS wait, Phase 3 ~1 h.

## Risks and gotchas

- **`users.google_sub` NOT NULL UNIQUE on MySQL.** We keep writing it (`provider:subject`) rather than
  altering it. Cross-engine nullability changes are the one thing our no-Alembic boot migrations cannot do.
- **Backfill must run before the first request** and must be idempotent — `init_db()` already runs at import,
  before `init_auth`, so it is. SQLite locally is not enough: exercise the MySQL path once on the droplet
  (the deploy script's test run, or a manual `python -c "import db"` in the venv) before trusting Phase 0.
- **Google redirect URI**: keeping `/auth/callback` as an alias means the console needs no change for Phase 0
  and the new URI can be added at leisure. Remove the alias only after the console has the new one.
- **GitHub email privacy**: `email` on `/user` is null for many accounts; `/user/emails` needs the
  `user:email` scope. If neither yields a verified address the account is created without one (no linking,
  no `users.email`), which is fine — it just cannot be on the unlimited list.
- **Discord unverified emails**: handled by the verified-only rule; do not "fix" it by trusting `email`.
- **Magic-link prefetch**: covered by the GET-renders / POST-consumes split. Do not shortcut this.
- **Deliverability**: DKIM or nothing. Plain-text mail. `p=none` DMARC first; tighten later.
- **Process-local limiters** (three of them after this): documented assumption of one gunicorn worker.
- **Open redirect**: none of the flows take a `next` parameter; every success lands on `/app`.
- **Privacy page + `BTSWEB_UNLIMITED_EMAILS`** both assume "the Google email". After Phase 0 that reads
  "the account's verified email", whichever provider supplied it — the env var keeps working unchanged.

## Out of scope (deliberately)

Steam (OpenID 2.0, not Authlib, no email — revisit on demand), passwords, account merging, unlinking,
disposable-email blocking, captcha on the email form, hosted auth vendors.
