# Forge-first signed-in screen + The Archive

Status: PLAN, written 2026-10-26, open questions answered by Ryan the same day (section 9). Nothing built.
Decisions below marked **Ryan 2026-10-26** are his; everything else is a recommendation with the reasoning
attached.

Companion plans: `FEATURED_FORGES_PLAN.md` (the featured strip and `/deck` pages this builds on),
`PRICING_NO_FREE_TOKENS_PLAN.md` + `PRICING_V3_COPY.md` (the copy this plan edits), `PHONE_FUNNEL_PLAN.md`
(phone banner and hand-off block, both touched here).

## 1. What the numbers say (prod SQLite, read 2026-10-26)

| October 1-26 | Users |
|---|---|
| Signed in for the first time | 31 |
| Ever pressed Forge | 7 |
| Got a finished class | 5 |
| Bought tokens | 1 |

- Everyone who has ever forged did so within 35 minutes of signing up, or never. The first signed-in
  screen is the whole decision.
- 6 of the 10 all-time forgers tried their own key first. That path finished 3 of 45 attempts (Gemini
  free-tier quota, OpenAI accounts with no credits, Groq 403, weak models failing the blueprint). Five of
  the seven key users never got a class and none of them later bought tokens.
- Today's first screen asks for three things before showing anything: a five-step tutorial whose first
  step sends people to Steam, a chooser whose primary button says "Support the forge", two payment boxes,
  and a Forge button that is disabled.

The fix is ordering, not features: concept box first, Forge always clickable, payment at the moment of
intent, install instructions after the class exists, and a public showcase ("The Archive") that gives
visitors and new accounts something to play before they spend anything.

## 2. Decisions

| # | Decision | Source |
|---|---|---|
| D1 | The concept textarea is the first thing on the signed-in screen. | Ryan 2026-10-26 |
| D2 | The Forge button is never disabled. Clicking it either forges (if the open pay choice can pay) or reveals the pay step and scrolls to it. | Ryan 2026-10-26 |
| D3 | On an account with 0 tokens and no saved key, the pay step opens on the get-tokens interface (tiers + custom amount), with the key box as the alternative beneath. | Ryan 2026-10-26 |
| D4 | "Subscribe to the mod on Steam Workshop" moves out of the pre-forge tutorial and into the result screen's "Play it" block. | Ryan 2026-10-26 |
| D5 | Every "Support the forge" becomes "Get a forge token" (headings, buttons, comments, copy doc). Donation framing in the blurbs stays; the Stripe product name stays "Donation — BLANK the spire". | Ryan 2026-10-26 |
| D6 | The featured showcase is named **The Archive**, gets its own public page and a nav tab everywhere, and is promoted on the landing page as the no-account way to play. | Ryan 2026-10-26 |
| D7 | A signed-in user can nominate one of their own classes for The Archive. Nominations go to an admin queue; only approved classes appear. | Ryan 2026-10-26 |
| D8 | No free token, and no featured-class showcase inside the signed-in forge screen (Ryan's call: push The Archive and sharing instead). | Ryan 2026-10-26 |
| D9 | The pay step is the two boxes exactly as they are today (Use a token / Bring your own key, radio pair), hidden until the first Forge click, unfolding between the textarea and the one Forge button. No second button. | Ryan 2026-10-26 |
| D10 | The phone banner moves under the Forge button. The Archive lists newest featured first. The share button copies a blurb with the URL. No "needs a paid key" sentence. | Ryan 2026-10-26 |

## 3. The new signed-in screen

### 3.1 Order of the page (desktop and phone)

```
header: Forge · My Classes · The Archive · Account · Get the mod · Help          (3.6)
+- #forge-input -----------------------------------------------------------+
| Describe your class                                                       |
| [textarea, 3 rows, rotating placeholder]                                  |
|                                                                           |
|   +- #pay-step (hidden until the first Forge click, 3.3) --------------+  |
|   | Who provides your compute? Pick one.                               |  |
|   | > Use a token        (you have N / tiers when N = 0)               |  |
|   | > Bring your own key (provider / key / models)                     |  |
|   +--------------------------------------------------------------------+  |
|                      [ Forge the class ]   (always enabled, the only one) |
| Describe -> Forge -> copy the code -> paste it in-game. Full guide  ·  x  |  one-line "how it works" (3.4)
| On a phone? Forge away; play on the PC.                              x    |  phones only (D10)
| > Advanced options                                                        |
+---------------------------------------------------------------------------+
#progress, #result (unchanged, plus the "Play it" block, 3.5)
```

Before the first click the card is just the textarea and the button. The click unfolds the pay boxes
above the button and scrolls so they are in view with the button still on screen; that is the whole
change to the layout (D9).

What disappears from above the fold: the five-step `#v3-banner` and the `#chooser` cards and strip. The
`#phone-banner` moves under the Forge button (D10), dismissable as today.

### 3.2 The Forge button (D2, D9)

`renderForgeButton()` no longer sets `disabled` except while `FORGING`. The label keeps saying what the
click costs once a box can pay ("Forge the class (uses 1 of your 3 tokens)"); before that it is just
"Forge the class". The `forge()` handler becomes:

1. Empty concept: toast "Describe a class first." and focus the textarea (as today).
2. `payable()` is true: the existing confirm dialog, then forge. `payable()` = `currentMode()` is `fake`,
   or `token` with `spendable() > 0`, or `byok` with a key and a model selected. This is the returning
   user's path: no unfold, no extra click.
3. Otherwise: `revealPayStep(reason)`. Un-hide `#pay-step` (the two boxes, 3.3), open the right one,
   `scrollIntoView` on the step with `block: "start"` and a `scroll-margin-top` for the header so the
   boxes and the button both land on screen, move focus to the first actionable control (the first tier
   button, or the key field), and put a one-line reason above the boxes ("Pick how to pay for this
   forge" / "Enter your key and pick a model"). The step stays open for the rest of the visit.

There is one Forge button and it keeps its place under the boxes, as today. Pressing it again while the
step is unsatisfied re-scrolls, re-focuses and repeats the reason as a toast.

### 3.3 The pay step by account state

The two `<details>` boxes (`#forge-token`, `#forge-byok`) are unchanged inside (D9): same radio-pair
behaviour (`onPayBoxToggle`, `onPaySummaryClick`), same `localStorage.bts_forge_pref` memory, same
`restoreForgePref` defaults (token box unless a key is saved), same "Who provides your compute? Pick
one." label. Only their wrapper `#pay-step` is new, and it is hidden until the first Forge click. The
`#chooser` cards and strip are removed; nothing replaces them, the open box is the choice.

| Account | Pay step on load | What Forge does |
|---|---|---|
| a. unlimited | hidden | forges |
| b. tokens > 0, no key | hidden; token box is the armed choice | confirm "uses 1 of your N tokens", forges |
| c. saved key + model | hidden; key box armed | confirm with the cost estimate, forges |
| d. 0 tokens, no key (every new account) | hidden | reveals the step with the token box open on the get-tokens interface (D3): heading "Get a forge token", `#forge-donate-tiers` + custom amount (already built by `renderDonatePanel`), the Stripe-fee line, and under it the key box summary "Have an API key? Forging with it is free." |
| e. key box open but no key/model | hidden | reveals the step with the key box open, focus on the key field |
| f. tokens arrive mid-visit (purchase return, admin grant) | `renderTokens()` re-renders the step: tiers fold, "Use a token — you have N" shows | forges |

Case d is the one that matters. `renderGetTokens()` already opens the tiers when the balance is 0; the
change is that the whole step is hidden until the Forge click, so the first screen is just the box and
the button. A user who wants to read the options first can open the step with a small "how is this paid
for?" link under the Forge button (also handy for the smoke script). Accounts in states b and c never
see the step unless they open it that way.

**Concept draft survives Stripe.** `donate()` / `donateCustom()` navigate to Stripe's hosted checkout
(`location.href = d.url`), which unloads the page. Before that, stash `{concept, interactive, pref}` in
`localStorage.bts_draft`; `boot()` restores it once (after `applyRemixPrefill`, which wins if both exist)
and deletes the key. `handlePurchaseReturn()` then lands on the forge with the token box armed and the
concept intact, and says so in its toast ("2 tokens added. Your class is ready to forge."). The same draft
covers a tab closed mid-checkout.

### 3.4 The tutorial banner shrinks to one line (D4)

`#v3-banner` becomes a single dismissible line under the Forge button:
"Describe, Forge, copy the code, paste it in-game (Mods, BLANK the spire, Import). Full guide."
Dismiss key stays `bts_tutorial_banner_dismissed`. `phoneTutorialOrder()` is deleted (there is no
subscribe step to move). The `#phone-banner` sits directly under it on phones (D10), same dismiss key as
today. The illustrated version on `/help` is unchanged except for 3.5.

### 3.5 Install instructions move to the result (D4)

The result screen's `.codebox` grows a "Play it" block, the same markup `deck.html` already has
(`.play-row` / `.play-how`), placed right under the code:

1. Subscribe on Steam Workshop (once). [link, `target=_blank`]
2. In Slay the Spire 2: Mods, BLANK the spire, Import a class code, paste, Import.
3. Restart the game and pick your class.

On phones the existing hand-off block (`#r-handoff`) stays above the art; the "Play it" block follows the
code as on desktop. `render.js` can own the block so `/deck` and `/app` share one copy.

`/help` step 2 ("Launch Slay the Spire 2 and open Mods") gets a parenthetical: "(the mod must be
subscribed on Steam Workshop first, once)". `test_pages.py` asserts "Steam Workshop" is on `/download`
and `/help`; keep both true.

### 3.6 Header

Add a "The Archive" tab (`<a class="tab" href="/archive">`) to `index.html`, `deck.html`, and `help.html`
/ `download.html` if they carry the nav. The landing page links to it from the strip (5.4). Order on
`/app`: Forge · My Classes · The Archive · Account · Get the mod · Help.

## 4. Wording sweep: "Support the forge" to "Get a forge token" (D5)

Sweep command (run before and after; afterwards only `_REPORT` / history files may match):

```
grep -rniE "support the forge" web/ docs/plans/PRICING_V3_COPY.md docs/plans/FEATURED_FORGES_PLAN.md
```

| Where | Now | New |
|---|---|---|
| `index.html:81` `#choose-token` | Support the forge | retired with the chooser cards (3.3) |
| `index.html:296` Account tab `<h2>` | Support the forge | Get a forge token |
| `index.html` `#forge-get-tokens` | Get tokens / Hide token options | Get a forge token / Hide token options |
| `index.html:22` chip tooltip | "...Account tab to get more." | "...Press Forge to get one." |
| `index.html` pay-step heading when balance is 0 (new) | none | Get a forge token |
| `app.js:205` comment, `style.css:266` comment | support the forge | get a forge token |
| `app.py:1309,1315` 402 text | "get more on the Account tab, or bring your own key" | "get a forge token under the Forge button, or bring your own key" |
| `PRICING_V3_COPY.md` section 11, section 25 heading, line 46 ("Support the forge and get tokens as a thank-you") | Support the forge | Get a forge token (the section 25 blurb body stays: "Your donations cover the cost of our compute.") |
| `landing.html:89` | "Donations cover the cost of tokens..." | unchanged (no "support the forge" there; the no-"buy" sentence stays) |
| `billing.py:278` Stripe product name | Donation — BLANK the spire | unchanged (D5) |

The Mega Crit constraint (never "buy") still holds: "get a forge token" is a request, the money is a
donation, the token is the thank-you. Keep that sentence in the Account blurb.

## 5. The Archive (D6, D7)

### 5.1 What it is

The public, curated showcase, renamed. Today it is four tiles on the landing page fed by
`web/featured.json`. The Archive is the same list with a home of its own (`/archive`), a tab in every
header, a badge on its `/deck` pages, and a way in for players: nominate your class, an admin approves.

### 5.2 Nominations

**Data.** Four nullable columns on `classes` (no new table; the `cards` cascade is untouched):

| column | type | meaning |
|---|---|---|
| `nominated_at` | DateTime | owner pressed Nominate; null = not nominated / withdrawn |
| `nomination_note` | String(200) | optional "why" from the owner, admin-only |
| `featured_at` | DateTime | admin approved; null = not in The Archive |
| `featured_word` | String(5) | the five-letter board word for the tile; admin fills it, default = the first word of the name upper-cased when it is five letters |

`featured.json` is migrated into these columns by a one-off `tools/migrate_featured.py` (sets
`featured_at` to now minus one second per file position, so newest-first keeps BRAVE, CRAVE, GOOSE,
MOOSE in today's order; `featured_word` from `word`). The file stays as the **seed for tests
and a fresh deploy** (`BTSWEB_FEATURED_FILE`): at boot, if no class has `featured_at`, the file is
applied. After that the DB is the source of truth and a deploy no longer edits the showcase. The `blurb`
field in the file maps to the class name (it already was the name for all four).

**Owner side.**
- Result screen `.view-bar` and each `libRow`: "☆ Nominate for The Archive" sends `POST
  /api/classes/<id>/nominate` `{note}` (owner only, via `_owned`). Pressed again: "★ Nominated · withdraw"
  sends `DELETE` on the same route. A featured class shows "★ In The Archive" (not withdrawable by the
  owner; deleting the class still removes it, as today).
- No art requirement before the button enables; the admin sees the art flags in the queue.
- One nomination per class, no limit per user; withdraw-and-renominate is allowed.

**Admin side.** New card on the Account tab under "Users", same `users.admin` gate (`loadAdminUsers`
pattern): "Archive nominations". Rows: name, owner email, concept (truncated), card count, art flags
(splash / sprite / cards), note, link to `/deck/<slug>` in a new tab, and two buttons: **Feature** (asks
for the five-letter word, sets `featured_at`) and **Pass** (clears `nominated_at`, keeps a row in
`admin_actions` so a repeat is visible). A second list under it, "In The Archive", with **Unfeature**.
Ordering is by `featured_at`, newest first (D10); no rank column. Every change writes `admin_actions` like the token
grants do, and writes need the <4h sign-in rule already enforced for the user panel.

**Safety.** Nothing a player writes appears publicly until an admin approves it, so the Archive cannot
be used to publish a slur as a class name. The nomination note is admin-only.

### 5.3 `/api/featured` and the page

- `/api/featured` reads `featured_at IS NOT NULL ORDER BY featured_at DESC` and returns the same shape as
  today (`word`, `slug`, `blurb` = name, `name`, `description`, `card_count`, `share_url`, art thumbs).
  `?limit=4` for the landing strip, unlimited for the page. Cache header unchanged.
- `/api/deck/<slug>` keeps its `featured` flag (now `featured_at IS NOT NULL`), and `deck.js`
  `markFeatured()` says "In The Archive" instead of "a featured class".
- New page `GET /archive` serving `static/archive.html` (+ `archive.js`; `featuredTile()` moves from
  `landing.js` into `render.js` so both pages share it). Header with the nav, `<h1>The Archive</h1>`, one
  line ("Classes forged with BLANK the spire, free to play. Copy a code, paste it in-game, or forge your
  own."), the tile grid, the same footer. OG tags for the page itself (`og-landing.png` is fine). CSP: no
  inline JS, same as `deck.html`.
- `/deck/<slug>` header: "More featured classes" becomes "The Archive".

### 5.4 Landing page

- Section `#featured`: `<h2>The Archive</h2>` with the sub-line "Classes other players forged. Play one
  now, no account needed." and a "Browse The Archive" link after the four tiles (`?limit=4`).
- Meta / splash copy: "Or try a featured class right now — no account needed" becomes "Or play a class
  from The Archive — no account needed."
- Keep the primary CTA "Create Your Own Class" (2026-10-05 decision).

### 5.5 Sharing (D10)

- "🔗 Copy share link" copies a blurb and the link, not just the URL: `"<name>" — <one-line
  description>. Play it: <url>`. One line of code in `renderShareBar` and `libRow`.
- The `/deck` page's `#remix` button and `nav-more` already route visitors into the forge and The
  Archive; nothing else is needed for v1.

### 5.6 Measurement

- `traffic_report.py`: new `archive` bucket (`/archive` page views), alongside `deck` and `featured`.
- Admin "Forge stats" tiles: nominations pending, classes in The Archive.
- The question to answer four weeks after Phase A ships: of new accounts, what share presses Forge, and
  what share of those reaches a purchase or a key forge. Today that is 7/31 and 1/31. Both are readable
  from `forge_jobs` and `purchases` without new logging; the pay-step reveal itself is not logged
  (section 8).

## 6. Work breakdown

Phases A and B are independent; A ships first (it is the conversion fix). Each phase: one Opus agent for
the code and the test runs, review here, deploy per the droplet deploy path (bump every `?v=` in
`index.html`, `landing.html`, `deck.html`, and the new `archive.html`).

### Phase A: forge-first screen (D1-D5)

| # | Item | Files |
|---|---|---|
| A1 | Reorder `index.html`: `#forge-input` first; `#pay-step` (hidden) wraps the two pay boxes as they are; delete `#chooser`; `#v3-banner` becomes the one-liner under the button; `#phone-banner` moves under it | `web/static/index.html` |
| A2 | `app.js`: `payable()`, `revealPayStep()`, forge button never disabled (except `FORGING`), remove `renderChooser` / `chooseToken` / `chooseByok` / `CHOOSER_FORCED`, delete `phoneTutorialOrder`, `bts_draft` stash in `donate()` / `donateCustom()` + restore in `boot()` | `web/static/app.js` |
| A3 | "Play it" block on the result (shared with `/deck` via `render.js`); help step 2 parenthetical | `web/static/index.html`, `render.js`, `deck.html`, `help.html` |
| A4 | Wording sweep (section 4) incl. the `app.py` 402 text and `PRICING_V3_COPY.md` | see section 4 |
| A5 | Share link copies the blurb + URL (5.5) | `web/static/app.js` |
| A6 | CSS: `.pay-step` card, step heading, `scroll-margin-top` for the header offset, phone widths (16px gutter, no horizontal scroll) | `web/static/style.css` |
| A7 | Tests: `ui_smoke.mjs` `forge` + `v3` scenarios rewritten for the new ids (fresh 0-token account: button enabled, step hidden; click: step visible, tiers open, focus on the first tier; saved-key account: click goes straight to confirm); `phone` scenario for the banner decision; `test_pages.py` strings; `test_forge_errors.py` 402 text | `web/tools/ui_smoke.mjs`, `web/tests/` |

Estimate: one working day including the smoke runs.

### Phase B: The Archive (D6, D7)

| # | Item | Files |
|---|---|---|
| B1 | Columns on `classes` + `tools/migrate_featured.py` + boot-time seed from `featured.json` when nothing is featured | `web/models.py`, `web/db.py` (SQLite `ALTER TABLE` on boot like earlier columns), `web/tools/` |
| B2 | `POST` / `DELETE /api/classes/<id>/nominate`; admin `GET /api/admin/nominations`, `POST .../feature`, `.../pass`, `.../unfeature` with `admin_actions` rows | `web/app.py` |
| B3 | `/api/featured` from the DB with `?limit`; `featured` flag on `/api/deck` | `web/app.py` |
| B4 | `/archive` page + `archive.js`; `featuredTile` into `render.js`; nav tab on every page; deck header rename; `markFeatured` copy | `web/static/archive.html` (new), `archive.js` (new), `render.js`, `landing.js`, `deck.js`, `deck.html`, `index.html`, `landing.html`, `help.html`, `download.html` |
| B5 | Nominate button on the result bar and `libRow`; admin "Archive nominations" card | `web/static/index.html`, `app.js` |
| B6 | Landing copy (5.4) | `web/static/landing.html` |
| B7 | `traffic_report.py` `archive` bucket; stats tiles | `web/tools/traffic_report.py`, `app.py`, `app.js` |
| B8 | Tests: `test_featured.py` (DB-backed list, seed-from-file, limit), new `test_nominate.py` (owner-only, admin gate, audit rows, pass / withdraw), `test_pages.py` for `/archive`, smoke `featured` scenario becomes `archive` | `web/tests/`, `web/tools/ui_smoke.mjs` |

Estimate: one and a half working days. B1-B3 can land before B4-B6 without any visible change.

### Deploy notes

- Phase A changes no DB schema; a normal `deploy.sh` with the `?v=` bumps.
- Phase B: run `migrate_featured.py` once on the droplet after the deploy (or rely on the boot seed; the
  seed is idempotent). Verify `/api/featured` still returns the four classes with art, then `/archive`
  200 with four tiles, then nominate a class from a tester account and approve it from the admin card.
- The release-ordering rule (mod zip before web) does not apply: no codec change.

## 7. Verification checklist

- [ ] Fresh account, phone width and desktop: the textarea is the first element under the header; the
      Forge button is enabled; nothing about payment is visible until Forge is pressed.
- [ ] Press Forge with an empty box: toast + focus, no scroll.
- [ ] Press Forge with text, 0 tokens: the page scrolls so the pay step's heading sits under the header,
      the tiers are visible, focus is on the first tier; the top button remains enabled.
- [ ] Donate $3 (Stripe test mode), return: concept text intact, "Use a token — you have 2" armed, press
      Forge, confirm, the forge runs.
- [ ] Account with a saved key: press Forge, confirm dialog directly.
- [ ] Switch boxes inside the step: the button label follows; `bts_forge_pref` remembered; the next visit
      starts with the step hidden and the remembered box armed.
- [ ] Share link on the result and in My Classes pastes as `"<name>" — <description>. Play it: <url>`.
- [ ] Result screen shows the "Play it" block under the code with the Workshop link; phones show the
      hand-off block above the art as before.
- [ ] `grep -rni "support the forge" web/` returns nothing outside `_REPORT` files.
- [ ] `/archive` public, four tiles, no account; header tab on `/app`, `/deck/<slug>`, landing.
- [ ] Nominate, admin card lists it, Feature with a word, tile appears on `/archive` and the landing
      strip within 5 minutes (cache), `/deck/<slug>` says "In The Archive", Unfeature removes it.
- [ ] Non-admin cannot reach the admin routes (403); a user cannot nominate someone else's class (404).
- [ ] `uv run python -m pytest` in `web/` green except the three known stale render.js failures; smoke
      scenarios `forge`, `v3`, `phone`, `archive`, `pages` green.

## 8. Not in this plan

- A free first forge (D8; `FEATURED_FORGES_PLAN.md` section 4 still has the cost math if that changes).
- Featured tiles inside the signed-in forge screen (D8).
- A pre-flight completion call on the key path, and a server-side event log for the pay-step reveal and
  Stripe checkout start. Both deserve a small follow-up plan; the second is the only way to see the step
  this plan creates.
- A re-engagement email to accounts that never forged (magic link is wired; one message, one question).

## 9. Open questions, answered (Ryan 2026-10-26)

1. Nomination queue with admin approval: **yes** (D7).
2. Pay step UI: **the two boxes as they are today, unfolding after the Forge click; one Forge button** (D9).
3. Phone banner: **under the Forge button** (D10).
4. Archive order: **newest featured first** (D10).
5. "Needs a paid key with credits" sentence: **no**. Share link that copies a blurb with the URL: **yes** (D10).
