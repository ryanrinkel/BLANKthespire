# Phone + in-app-browser funnel plan ("Safari users")

Status: BUILT 2026-10-13 (phases 0-3; 5.4 completion email deferred; 4.3 hand-off scheme and 5.2 share sheet unverified on a real phone). Written after the YouTube ad post-mortem (below).

## 1. What the YouTube ad showed (prod nginx log, 2026-10-07 .. 2026-10-12)

| Step | Count |
|---|---|
| Landing hits carrying `utm_source=youtube` | 850 |
| Unique visitors | 686 |
| ...on a phone (iPhone 77%, Android 20%) | ~95% |
| ...iPhone hits from a WKWebView (UA has no `Safari/` token = the YouTube app's in-app browser) | 635 of 661 |
| Opened `/login` | 13 |
| Tapped a provider button (2 Google, 1 GitHub; all iPhone webview) | 3 |
| Came back through `/auth/callback` | 0 |
| Forged / purchased / reached `/app` / opened `/download` | 0 / 0 / 1 / 1 |

Three new accounts were created that week; all three signed in from Windows desktops on IPs that never
touched the ad link. Attribution to the ad: zero.

Why it died, in order of where people fell off:

1. **Google OAuth refuses embedded webviews** (`403 disallowed_useragent`, policy since 2016). The YouTube
   iOS app opens links in a WKWebView, so "Continue with Google" cannot work there, and that is the first
   button on `/login`. Nothing on the page says so; the visitor sees a Google error and leaves.
2. **The product lives on a PC.** Even in real Safari a phone visitor cannot subscribe on Steam, paste a
   code into the mod, or play. Every page assumes "you are at the machine the game is on". There is no
   "forge now, play later on your PC" story anywhere, and no way to send a class to that PC.
3. **Nobody told them it is a PC game.** The splash says "forge your own Slay the Spire 2 class"; a phone
   viewer of a video ad can reasonably think it is a mobile thing. Those who would never qualify still
   cost a click.

"Safari users" below means both cases: a real Safari/Chrome-on-iPhone visitor (OAuth works, hand-off is
the problem) and the in-app webview visitor (OAuth is broken too).

## 2. Goal

A phone visitor arriving from an ad or a share link can, without leaving the phone:

1. understand in one screen that this makes classes for Slay the Spire 2 on Steam (PC), and that forging
   on the phone is fine because the class waits in their library;
2. sign in, including from inside the YouTube / Reddit / Discord in-app browsers;
3. forge a class, lock the phone, come back, and find the result;
4. get the class onto their PC later with one tap (email it, share-sheet it, or just open My Classes on
   the PC).

Nothing here changes the PC experience.

## 3. Phase 0 - measure the right thing first (~2 h)

The admin card's campaign row said 635 ad visitors "reached the app". That bucket is `GET /api/me 200`,
and `landing.js` calls `/api/me` on every splash load to point the sign-in button
(`web/static/landing.js` ~line 220). So "app" really means "a real browser ran our JS" - useful as a bot
filter, but not signed-in use. The docstring in `web/tools/traffic_report.py` (line ~24, "only
index.html's JS calls it") is wrong.

- Rename the bucket honestly (`browser` or `js_ran`) and add a real `signed_in` bucket keyed on a path
  only the signed-in app fetches on boot (candidate: the library load in `app.js`; confirm the exact path
  before coding - the fetch URLs there are built dynamically so grep does not list them). Keep the
  stacked-bar invariant (one bucket per IP per day).
- Add a `device` split to each campaign row: `desktop` / `phone` / `phone-webview`, from the UA
  (iOS: `iPhone|iPad` without `Safari/` and without `CriOS|FxiOS` -> webview; Android: `; wv)` -> webview).
  Same split on the 7/30-day humans line so the next ad can be read at a glance.
- Card copy: "reached the app" -> "signed in"; add the device chips.

Files: `web/tools/traffic_report.py`, the traffic card in `web/static/app.js` (~line 1513),
`web/tests` for the report.

## 4. Phase 1 - sign-in that works inside a webview (~half a day)

**4.1 Detect the webview** in one tiny helper shared by `signin.js` and `landing.js`:

```js
const UA = navigator.userAgent;
const IOS_WEBVIEW = /iPhone|iPad|iPod/.test(UA) && !/Safari\//.test(UA) && !/CriOS|FxiOS/.test(UA);
const ANDROID_WEBVIEW = /Android/.test(UA) && /; wv\)/.test(UA);
```

Nothing server-side needs to change for this phase; `/api/me` already tells the page which providers
exist.

**4.2 Reorder `/login` for webviews.** Today: Google, GitHub, then "or" + the email form. In a webview:

- Put the **email magic link first**, with its own heading: *"You're in the YouTube app's browser -
  Google can't sign you in here. Enter your email and we'll send a link; it opens in Safari and you're in."*
- **Hide the Google button** (it will fail). Keep GitHub below the form (GitHub does not block webviews;
  the one GitHub tap in the ad never returned, but that is one data point).
- Keep "Just want to play one? Try a featured class" as the no-account path.

The magic link is already the natural escape hatch: Mail opens the link in Safari, so the session and
everything after it lives in a real browser. `signin-continue.html`'s "One more click" POST stays as is
(the mail-scanner reason still holds).

**4.3 "Open in Safari / Chrome" button** above the form, user-gesture only:

- iOS: try the `x-safari-https://blankthespire.com/login` scheme (reported to work from WKWebViews on
  iOS 17+; **verify on a real iPhone before shipping**, and keep the fallback text: *"or tap the ... menu
  at the top right and choose Open in Safari"*).
- Android: `intent://blankthespire.com/login#Intent;scheme=https;end` reliably hands off to Chrome.
  Low priority - only 3 of 169 Android hits were webviews; the YouTube Android app uses Custom Tabs.

**4.4 Landing page in a webview** (`landing.js`): keep the single CTA, but swap the note under it to
*"Sign in by email - the YouTube browser can't do Google sign-in. Or tap ... -> Open in Safari."* so the
first screen already sets expectations.

**4.5 Smoke**: add a `ui_smoke.mjs` scenario that boots headless Chrome with the iPhone-webview UA and
asserts the email form is first and the Google button is absent; a second run with the Safari UA asserts
the old order. (The harness can set the UA through CDP `Emulation.setUserAgentOverride`.)

Files: `web/static/signin.js`, `web/static/signin.html`, `web/static/landing.js`,
`web/static/style.css` (bump every `?v=` in the HTML), `web/tools/ui_smoke.mjs`.

## 5. Phase 2 - "forge on your phone, play on your PC" (~1.5 days)

**5.1 The phone banner in the app.** When `matchMedia("(pointer: coarse)")` or a phone UA: a one-line
banner above the forge box, dismissible like the tutorial banner: *"On a phone? Forge away - the class is
saved to My Classes. Open blankthespire.com on the PC that runs Slay the Spire 2 to grab the code, or send
it to yourself below."* The five-step tutorial banner's step 1 ("Subscribe to the mod on Steam Workshop")
reads as a blocker on a phone; on phones put it last and label it "later, on your PC".

**5.2 "Send to my PC."** Two cheap hand-offs on the result page and in each library row:

- **Share sheet** (`navigator.share` with the `/deck/<slug>` URL + the class name): on iPhone this is
  AirDrop-to-Mac, Messages-to-self, Notes, Mail - zero server work, ~10 lines next to the existing
  Share link button (`app.js` ~line 1010 / 845). Fall back to the copy button where unsupported.
- **Email it to me**: `POST /api/class/<id>/email` sends the share link + the import code to the
  account's email (Resend is already wired for magic links; reuse `_send_magic_link`'s transport, new
  template). Rate-limit like `magic_limiter`. Requires an email on the account - Google/GitHub/email
  identities all provide one.

**5.3 The result page on a phone.** The code box and the copy button already exist. Make the code box
`readonly` + select-on-tap, and put the **two hand-off buttons above the fold**, before the card
gallery. Check `/deck/<slug>` at 390 px (it is the page strangers hit from shares and the featured strip).

**5.4 The wait.** A forge is several minutes; phones lock the screen. The server-side job already
survives, and `app.js` (~lines 720-800) reconnects on `visibilitychange`. Keep that, and add a
"Your class is ready" email on job completion (the same mailer, triggered where `forge_jobs.status`
flips to done) **only for jobs started from a phone** (a flag on the job from the client). Optional;
decide after 5.2 ships.

**5.5 Payment on a phone.** Stripe Checkout works in Safari and in webviews, and Apple Pay appears
automatically on iPhone Safari (a real advantage: no card typing). Verify the return URL lands on
`/app#account` on a phone and that the token balance refreshes without a reload. Likely no code change.

Files: `web/static/index.html`, `web/static/app.js`, `web/static/deck.html`, `web/static/deck.js`,
`web/static/style.css`, `web/auth.py` (mailer reuse), `web/app.py` (new endpoint), `web/tests`.

## 6. Phase 3 - the first screen for a phone coming from an ad (~half a day)

- **Say "PC" early.** Under the board: *"A free mod for Slay the Spire 2 on Steam. Forge on any device;
  play on your PC."* One line; it also stops people who do not own the game before they cost a sign-in.
- **Phone hero order**: featured classes first (something to look at in 2 seconds), the CTA second. On
  desktop keep the current order. *Reverted 2026-10-22: on a real phone it read as a layout mistake (the
  "How will you fill in the Blank?" question with its button pushed under the strip), so phones now keep
  the document order too: board, tagline, CTA, then the strip.*
- **Ad-side lever, no code**: in Google Ads set the mobile device bid adjustment to -100% (or run a
  desktop-only campaign) for the next test, or if the point IS phones, make the ad's own story "forge on
  your phone, play tonight on PC" so the landing page and the ad agree. Either way phase 1 is still worth
  shipping: shares on Discord/Reddit/Telegram open in in-app browsers every day.

Files: `web/static/landing.html`, `web/static/landing.js`, `web/static/style.css`.

## 7. Measurement and success criteria (after phases 0-2)

Read from the campaign rows with the new device split, per tagged link:

| Funnel step (phone-webview + phone) | Today | Target for the next ad |
|---|---|---|
| landed -> opened `/login` | 2% | 5% |
| opened `/login` -> started a magic link (`POST /api/auth/email/start`) | 0 | 50% |
| magic link started -> signed in (`/auth/email/<token>` POST 302) | 0 | 60% |
| signed in -> forged | 0 | 25% |
| forged -> imported on a PC (mod fetch of that class's art, `imports` in traffic.json) | 0 | 1 in 3 |

The last row is the only one that proves the hand-off worked; it is visible since 2026-10-06 and keyed by
class, so it does not need the phone and the PC to share an IP.

## 8. Work estimate

| Phase | Effort | Ship on its own? |
|---|---|---|
| 0 measure | 2 h | yes |
| 1 webview sign-in | 0.5 d | yes, first |
| 2 phone->PC hand-off | 1.5 d | yes |
| 3 phone landing | 0.5 d | yes |

Order: 1 -> 0 -> 2 -> 3. Phase 1 is the fix for the actual break; phase 0 makes the next test readable;
phase 2 is the product story; phase 3 is copy.

## 9. Open questions for Ryan

1. Run the next ad desktop-only, or lean into "forge on your phone, play on PC" and keep phones? (Decides
   whether phase 3 copy is defensive or the headline.)
2. OK to email import codes to account owners (5.2)? It is their own content; cost is Resend volume.
3. Keep the GitHub button in webviews, or email-only there? (Data says 1 tap, 0 returns; GitHub itself
   allows webviews.)
4. Is the completion email (5.4) wanted at all, or is the share sheet enough?
5. Do you have an iPhone handy to verify `x-safari-https://` (4.3)? Without that check it ships as
   instructions only.
