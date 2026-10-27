# Sign-up events (free tokens for new accounts, time-boxed)

Status: BACKEND + FRONTEND BUILT 2026-10-26, not committed and not deployed. The web suite passes (410 = 374
existing + 34 in `web/tests/test_promos.py` + 2 page tests). The `events` scenario of `web/tools/ui_smoke.mjs`
passes end to end. What is left is the deploy (see "What is left" below).

## What it is

An event is a window of time chosen by the operator. Every NEW account created inside that window starts
with `tokens_per_signup` hosted-forge tokens, until `max_grants` accounts have received them. This is a
deliberate, temporary exception to pricing v3, under which accounts start with 0 tokens
(`models.INITIAL_TOKENS = 0`). The most an event can cost is `max_grants x tokens_per_signup` hosted forges
(about $1 each, see the hosted-forge unit cost notes).

## Design decisions

- **Who qualifies:** any brand-new signup, from any provider, created while an event is active. That means
  rule 4 of `auth._resolve_identity`. These get nothing:
  - existing accounts,
  - repeat sign-ins (rule 1),
  - linking another sign-in method while signed in (rule 2),
  - a second provider that matches by verified email (rule 3).
- **Cost guard:** a hard `max_grants` cap, counted in granted accounts. Once the cap is reached, new
  signups still get an account but receive no tokens.
- **One event at a time:** creating or editing an event is refused (409) if its window overlaps another
  event that has not ended. Ended events (ended early with End now, or with a window that has run out)
  never block. Windows are half-open `[starts_at, ends_at)`, so back-to-back events are allowed.
- **Atomicity:** the grant runs in the same transaction as the account insert, inside a SAVEPOINT
  (`begin_nested`). If it fails, only the grant rolls back. The account is still created, with no tokens,
  no PromoGrant row and no stray balance change, and the error is logged.
- **Cap race:** "count then insert" is race-free on SQLite, because every transaction takes the write
  lock at BEGIN (`db._sqlite_begin`, BEGIN IMMEDIATE). On MySQL, two signups at the same moment could
  overshoot the cap by one. Prod is SQLite, so this is accepted.
- **Datetimes:** stored as naive UTC (the same convention as `auth._utc_naive`). The API returns them with
  an explicit `+00:00` and requires input to carry an offset; naive input gets a 400.

## What was built (backend)

| file | change |
|------|--------|
| `web/models.py` | `Promotion` (`promotions`) and `PromoGrant` (`promo_grants`, UNIQUE(promo_id, user_id), `seen_at`). Both are new tables, so `create_all` creates them and no `_ensure_*` migration is needed. |
| `web/promo.py` | `active_promotion(s, now)`, `grant_signup_bonus(s, user, now)`, `status_of`, input parsing and validation, `overlapping`. `_now()` can be monkeypatched in tests. |
| `web/auth.py` | The rule-4 branch calls `promo.grant_signup_bonus(s, user)` after `s.flush()`. `/api/me` adds `user.welcome_grant` and stamps `seen_at`. |
| `web/app.py` | Admin routes, the public `/api/promo/active`, `promo_label`/`promo_tokens` on `/api/admin/users`, and `_log_admin_action` now accepts `target=None`. |
| `web/tests/test_promos.py` | 34 tests. |

### Endpoints

Admin reads need an address in `BTSWEB_ADMIN_EMAILS`. Admin writes also need a sign-in less than 4 h old
(`ADMIN_WRITE_MAX_AGE_S`) and the `X-Requested-With: fetch` header. Every write adds an `admin_actions` row:

| action | old -> new | note |
|--------|------------|------|
| `promo_create` | 0 -> cap | `event #<id> <label> · N/signup` |
| `promo_edit` | old cap -> new cap | the names of the changed fields |
| `promo_end` | 1 -> 0 | the event |

These rows have no target account.

- `GET /api/admin/promos` returns `{promos: [row...], now}`, newest first.
  - Each row has: `{id, label, tokens_per_signup, starts_at, ends_at, max_grants, ended_at,
    created_by_email, created_at, status, stats}`.
  - `status` is one of `scheduled | live | capped | ended`.
  - `stats` is `{granted, tokens_granted, forged_after, hosted_cost_usd, donated_after,
    donated_cents_after}`. Each of these counts only activity by granted users after their grant:
    - `forged_after` counts users with at least one ForgeJob whose status is `done`.
    - `hosted_cost_usd` sums their `mode=token` ForgeUsage, using the metered cost and falling back to
      the estimate for each row. It is null when no row has a price.
    - `donated_*` counts paid Purchases.
- `POST /api/admin/promos` creates an event and returns 201 with the row.
  - Body: `{label, tokens_per_signup?, starts_at, ends_at, max_grants}`.
    - `label`: 1..120 characters.
    - `tokens_per_signup`: 1..10, default 1.
    - `max_grants`: 0..10000, required.
    - `starts_at` / `ends_at`: ISO 8601 with an offset. `ends_at` must be after `starts_at` and in the
      future.
  - Returns 400 `{error}` for invalid input, or 409 `{error, conflict_id}` when the window overlaps another
    event.
- `POST /api/admin/promos/<id>` edits an event. It takes the same full body and rules as create, and works
  while the event is scheduled, live or capped. For example, raising the cap reopens a capped event.
  - Returns 404 if the event does not exist, 409 if it has ended, 400 or 409 as for create, or 200 with the
    row.
- `POST /api/admin/promos/<id>/end` sets `ended_at = now` and returns 200 with the row. It is idempotent:
  calling it again keeps the first `ended_at` and adds no second audit row.
- `GET /api/promo/active` is public. It returns `{active: {label, tokens_per_signup, ends_at}}` or
  `{active: null}`.
  - A capped event reads as null.
  - The remaining count is never exposed.
  - Responses carry `Cache-Control: public, max-age=60`.
- `GET /api/me` adds `user.welcome_grant`: `{label, tokens}` for the user's first PromoGrant that has not
  been seen yet, otherwise null. It is shown once (`seen_at` is stamped on read).
- `GET /api/admin/users`: each row gains `promo_label` (null if the account had no grant) and
  `promo_tokens`.

## What was built (frontend, 2026-10-26)

Every visitor-facing piece is invisible unless an event is live: no element, no gap, no flash.

| file | change |
|------|--------|
| `web/static/signup-event.js` (new) | `BTS_EVENT.ribbon(me, place)` and `BTS_EVENT.keepWelcome(me)`, loaded by `landing.html` and `signin.html` before their page scripts. The ribbon element is CREATED only after `/api/promo/active` names an event AND `/api/me` says the visitor is signed out. On any fetch error nothing is added. Its copy is "{label}: sign up before {ends_at in the viewer's local day/time} and your first forge is on us" ("your first N forges are on us" when N > 1). It never shows a remaining count. |
| `web/static/landing.js` | The ribbon goes right above "Create Your Own Class". |
| `web/static/signin.js` | The ribbon goes under the lede. It is never shown in link mode (signed in). A welcome this read consumed is parked before the `/app` bounce. |
| `web/static/index.html` + `app.js` | `#welcome-banner` (hidden) at the top of the forge tab. `renderWelcome()` shows "Welcome! {label} gave you N free forge token(s)..." from `ME.welcome_grant` (`boot()`, or `loadAccount()`'s `/api/me` read), or from `bts_welcome_grant` in localStorage. The splash and `/login` park a grant they consumed there, tagged with the user id and cleared once read. The x only hides it, since the server has already marked it seen. |
| `web/static/index.html` + `app.js` | The admin **Sign-up events** card (`#admin-events`, after the Archive card, same gate):<br>- a table with label, status pill, local-time window ("ended early" when End now was used), granted/cap, forged, our cost, donated.<br>- **New event** / **Edit** open one form: label, tokens per signup, start/end `datetime-local` sent with the browser's UTC offset for that date, cap.<br>- **End now** asks for `confirm()` first.<br>- 400/409/403-reauth messages show inline. A 409's UTC times are rewritten to local time. |
| `web/static/app.js` | The user panel row shows "🎁 {promo_label} (+N)". The Recent changes log renders `promo_create` / `promo_edit` / `promo_end`. |
| `web/static/style.css` | `.event-ribbon`, `.banner.welcome`, `.ev-pill.*`, the admin event form. Dark theme only, existing tokens. |
| `?v=` | `style.css` → `20261026d` on all 7 pages. In `index.html`, `render.js` + `app.js` → `20261026d`. `landing.js`, `signin.js` and the new `signup-event.js` → `20261026d`. |
| `web/tests/test_pages.py` | Two tests:<br>- no page ships ribbon markup, and `signup-event.js` loads before `landing.js` / `signin.js`.<br>- the welcome banner and the Events card are hidden by default, and every page uses one `style.css` version. |
| `web/tools/ui_smoke.mjs` | The `events` scenario covers (a)-(e): no event, live, welcome once and parked, the admin card, End now. It needs `BTSWEB_ADMIN_EMAILS=unlimited@example.com` and a fresh DB. It turns off the browser cache, so the 60 s `Cache-Control` on `/api/promo/active` does not mask End now. |

## What is left

1. Deploy with `ssh blankdroplet`, `sudo /opt/btsweb/deploy.sh`. The tables are created on boot. After
   deploying, check `GET /api/promo/active` returns `{"active": null}`, and that the splash looks exactly as it did.
2. The first write from the card needs a sign-in less than 4 h old, as the user panel does.
3. After End now, real visitors can still see the ribbon for up to 60 s, because of the `/api/promo/active` cache
   header. The card's note says so.

## Running an event from the command line (the card does the same)

Writes need a session cookie from a sign-in less than 4 h old. Sign in on https://blankthespire.com, copy
the `session` cookie from devtools, and keep it out of shell history:

```sh
read -rs BTS_COOKIE   # paste the session cookie value
BASE=https://blankthespire.com
H=(-H "X-Requested-With: fetch" -H "Content-Type: application/json" -b "session=$BTS_COOKIE")

# Create: 1 token per new account, at most 50 accounts, Friday 18:00 US Eastern to Monday 06:00 Eastern.
curl -s "${H[@]}" -X POST "$BASE/api/admin/promos" -d '{
  "label": "Launch weekend", "tokens_per_signup": 1, "max_grants": 50,
  "starts_at": "2026-10-30T18:00:00-04:00", "ends_at": "2026-11-02T06:00:00-05:00"}'

# List with stats
curl -s "${H[@]}" "$BASE/api/admin/promos"

# Raise the cap mid-event (send the full body again)
curl -s "${H[@]}" -X POST "$BASE/api/admin/promos/1" -d '{
  "label": "Launch weekend", "tokens_per_signup": 1, "max_grants": 100,
  "starts_at": "2026-10-30T18:00:00-04:00", "ends_at": "2026-11-02T06:00:00-05:00"}'

# End it now
curl -s "${H[@]}" -X POST "$BASE/api/admin/promos/1/end"

# What the landing page will see
curl -s "$BASE/api/promo/active"
```

A 403 with `"reauth": true` means the sign-in is more than 4 h old. Sign out, sign back in, and copy the
new cookie.
