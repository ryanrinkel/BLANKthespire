# Featured forges + landing conversion plan

Status: Phase 1 BUILT 2026-10-05 (plus phase 2 items 2, 3, 4: landing OG tags + `static/img/og-landing.png`,
sign-in escape hatch, "why sign in" line). Decisions: MOOSE = id 70; GOOSE/MOOSE ship as v55 codes (no
re-forge); primary CTA "Create Your Own Class", secondary "Try a featured class". DEPLOYED 2026-10-05 20:08Z (be77729); live checks: /api/featured returns the 4 classes with art, og-landing.png 200, /login escape hatch present.

Verification: `web/tests` 300 passed; `web/tools/ui_smoke.mjs ... featured` scenario green (boot the server
with `BTSWEB_FEATURED_FILE` pointing at a JSON whose slugs exist in that server's DB; the list is read once
at boot, so editing `web/featured.json` on the droplet needs a restart, a deploy does that anyway).

## 1. What the numbers say (prod, 2026-09-14 .. 2026-10-05)

Source: `/opt/btsweb/traffic/traffic.json` (nginx funnel) and the prod SQLite DB.

| Step | 30 days | Share |
|---|---|---|
| Humans who loaded `/` | 1047 | 100% |
| Reached `/login` | 78 | 7.5% |
| Reached `/app` (signed in) | 18 | 1.7% |
| Opened a `/deck/<slug>` share page | 2 | — |

Accounts: 20 users total, 13 created in the last four weeks. **16 of the 20 have never forged a class.**
Only 4 accounts have ever forged (2 once, 2 more than once) and most of the 77 classes are Ryan's.

So there are two leaks, not one:

1. **Landing → sign-in.** 92% never click anything. The splash shows no class, no art, no gameplay, and
   the only button is "Sign in". Step 1 of "How it works" literally says *sign up first*.
2. **Signed in → first forge.** Even the people who clear the login mostly never forge, because the next
   screen is a paywall (own API key or a donation). They came to see a class, and the site has not shown
   them one yet.

Featured forges fix both: a visitor gets a playable class in two clicks with no account and no spend, and
the share page already exists to show it (`/deck/<slug>`, public, read-only, Open Graph stamped).

## 2. Featured forges (phase 1, the core ask)

### 2.1 Curated list

Ryan curates a small JSON file in the repo; a deploy publishes a change. No admin UI for now.

`web/featured.json`:

```json
[
  {"word": "BRAVE", "slug": "IIZoSCYMf3P9QxA1GFj1bQ", "blurb": "William Wallace, Clan Blade"},
  {"word": "CRAVE", "slug": "8aFsjgJLDpBcbwarwAJ62A", "blurb": "Big Mac, the Layered Tempest"},
  {"word": "GOOSE", "slug": "fPmsNBjRE1T7v1ZJC46gWA", "blurb": "The Unruly Goose"},
  {"word": "MOOSE", "slug": "bZxhY4Qqxqb6By7CUfNp7w", "blurb": "The Bull Moose, Bone Sovereign"}
]
```

The four classes all exist on prod with splash, sprite and card art:

| word | id | name | owner | vocab |
|---|---|---|---|---|
| BRAVE | 76 | William Wallace, Clan Blade | ryan.r.rinkel | v70 |
| CRAVE | 77 | Big Mac, the Layered Tempest | ryan.r.rinkel | v70 |
| GOOSE | 71 | The Unruly Goose | ryan.r.rinkel | v55 |
| MOOSE | 70 | The Bull Moose, Bone Sovereign | ryantheradon | v55 |
| MOOSE alt | 69 | The Blackwater Bull | ryantheradon | v55 |

Notes. The two v55 codes still import on the v0.4.0 mod (the codec only rejects *newer* codes), so no
re-forge is required; re-forging GOOSE and MOOSE at v70 is optional polish. Both moose classes belong to the
`ryantheradon` account, which is fine for a public slug, but a delete from that account would drop the tile.
`word` is the five-letter board word; the "BLANK the spire" tiles should flip to it on hover.

### 2.2 Endpoint: `GET /api/featured`

- Reads `featured.json` once at boot (reload on SIGHUP is overkill; a deploy restarts the app anyway).
- Joins each slug to `classes` and returns the public shape only: `word`, `blurb`, `name`, the character
  description, `card_count`, `splash_url` / `sprite_url` via the existing `/api/deck/<slug>/art/...` thumbs,
  and `share_url`.
- Skips slugs that no longer resolve instead of failing the whole list.
- Public, cacheable (`Cache-Control: public, max-age=300`), no session.
- Add a `featured` boolean to `/api/deck/<slug>` so the share page can change its copy (section 2.4).

### 2.3 Landing page: present the choice

`static/landing.html` + `landing.js` + `style.css`:

- Under the board, replace the single "Sign in" button with two equal CTAs:
  **"Try a featured class"** (scrolls to / reveals the strip) and **"Sign in to forge your own"**.
- A **featured strip** of four tiles directly below: splash art (3:2 thumb), the class name, one-line blurb,
  and a `BRAVE the spire` caption. Click → `/deck/<slug>`. Hovering a tile flips the board to its word
  (reuse `flipTo`), which ties the gimmick to the product.
- Tiles come from `/api/featured`; if the fetch fails the strip hides and the page is exactly today's page.
- Reorder "How it works": 1) Subscribe to the mod on Workshop, 2) Pick a featured class or forge your own,
  3) Paste the code in-game. Sign-in becomes a parenthetical ("sign in to forge and save your own").
- Keep CSP: no inline script, fetch only, same pattern as today.

### 2.4 Share page as a landing for strangers

`static/deck.html` / `deck.js`:

- When `featured` is true, the lede changes from "Someone forged this class" to "A featured class, free to
  play. Copy the code, paste it in-game." and the header nav gains **"More featured classes"** (back to
  `/#featured`).
- Put the **import code and Copy button above the fold**, before the card grid. The code is the product;
  today it is at the bottom of ~34 cards.
- Add an **"Already have the mod?"** mini-checklist beside the code: Subscribe on Workshop → Mods →
  BLANK the spire → Import a class code → Restart. Link to `/help`.
- **"Forge your own twist"** button: stores the concept in `localStorage` (`bts_prefill_concept`) and sends
  the visitor to `/login`; `app.js` reads it once on first load and fills `#concept`. No change to the
  post-login redirect in `auth.py` needed. This is the bridge from "I played the goose" to "I want mine".

### 2.5 Measurement

`web/tools/traffic_report.py`:

- Add `/featured` and `/api/featured` to `ENGAGED_RE`, and a `featured` bucket: a landing visitor who fetched
  `/api/deck/<slug>` for a featured slug that day. Report it in the daily series and the admin card.
- Count `/workshop` (the Steam redirect) as "install intent"; it is the strongest signal we have short of a
  code copy.
- Success criteria for two weeks after launch: `clicked` (anything past the splash) from ~1/day to ≥10/day,
  `/deck` visitors from ~0 to double digits per week, new accounts up from ~3/week, and at least one
  featured-first visitor who later forges (check `classes.created_at` against `users.created_at`).

### 2.6 Work estimate

About one day: endpoint + JSON (1–2 h), landing strip + CSS (3 h), deck page changes + prefill (2 h),
traffic report + tests (1–2 h). Ship as a web-only deploy; no mod or Workshop change, so no release-ordering
concern.

## 3. Landing conversion polish (phase 2, cheap wins)

1. **Show the product before the ask.** Even above the featured strip, the hero should have one piece of
   splash art or the promo loop. The v9 promo video (44 s, 16:9 and 9:16) exists in `promo/`; a muted,
   looping, `playsinline` MP4 under the board needs no music and answers "what is this" in three seconds.
   Serve a ~2 MB 720p cut from `static/img/`, poster = a splash.
2. **Open Graph for `/`.** The landing has no `og:` tags, so Reddit and Discord links unfurl blank. Reddit
   and Steam are two of the top three referers. Add title, description and an `og:image` collage of the four
   featured splashes.
3. **Sign-in page escape hatch.** On `/login`, add a muted line under the providers: "Just want to play one?
   Try a featured class, no account needed." 78 people a month reach this page; today the only exits are
   back or a provider.
4. **Say why sign in.** On both pages: "Sign in to forge and keep your classes. No password, we only see your
   email." The reassurance exists on `/login` but not where the decision is made.
5. **Workshop description.** Add "Try a class right now: blankthespire.com" with one featured link. Workshop
   subscribers already have the mod installed; a code is the shortest path to them playing.
6. **Secondary CTA "Get the mod"** on the landing hero. Everyone needs it regardless of path, and
   `/download` is public.

## 4. The forge wall (phase 3, needs a decision)

16 of 20 accounts never forged. Featured classes soften this, but the wall stays. Options, cheapest first:

- **Remix prefill** (2.4) so the first forge screen is not a blank box.
- **Show the featured strip inside `/app` too**, under the chooser, for people who signed in cold.
- **One free hosted forge per new account.** This reverses the 2026-09-19 "no free tokens" decision, so it
  is Ryan's call, not a recommendation. The cost side: ~13 sign-ups in four weeks at ~$1.05 per hosted forge
  is under $15/month at current volume, with the hosted route's cost gate already in place. The abuse side:
  one per account, Google/GitHub/email identity required, admin panel can revoke. If pricing copy stays as
  is, the landing copy "there is nothing to buy" remains true.

## 5. Open questions for Ryan

1. **MOOSE**: id 70 (Bull Moose, Bone Sovereign) or id 69 (Blackwater Bull)? The plan assumes 70.
2. Re-forge GOOSE and MOOSE at v70 before featuring, or ship the v55 codes as they are?
3. Tile order on the landing. The plan assumes BRAVE, CRAVE, GOOSE, MOOSE.
4. Phase 3 free first forge: yes, no, or later.
5. Promo loop on the landing: yes (phase 2 item 1) or keep the page video-free.

## 6. Files touched (phase 1)

- `web/featured.json` (new)
- `web/app.py`: `/api/featured`, `featured` flag on `/api/deck/<slug>`
- `web/static/landing.html`, `landing.js`, `style.css`
- `web/static/deck.html`, `deck.js`
- `web/static/app.js`: read `bts_prefill_concept` once
- `web/tools/traffic_report.py` + `web/tests/` for the new bucket and endpoint
