# Page experiments (A/B testing) plan

Status: PLAN FINAL 2026-11-03, nothing built. Decisions taken the same day (section 7): no new cookies,
operator visibility is a requirement, no ad is scheduled, build order starts with Phase 0 when Ryan says go.
Written against the live droplet numbers of 2026-11-03 (section 1).

## 0. The short version

- The site has ~50-60 real splash visitors a week organically and ~700 in a six-day YouTube ad. At that
  rate an A/B test on the splash can only call a WINNER during an ad burst, or after months for a very
  large effect (section 6). No ad is planned, so the pace is relaxed — but every number below depends on
  Phase 0, which is worth shipping on its own.
- Before anything else, the "clicked past the splash" bucket the traffic card shows is broken (section
  1.2): the landing's Archive strip fetches four art thumbnails under `/api/deck/...`, and `/api/` counts
  as a click-through. The October ad shows 621 of 684 visitors "clicked"; the log says ~50.
- Design: NO new cookie and NO new logging. The arm is a deterministic hash of (client IP, user agent,
  experiment name, salt) — two things nginx already logs — so the report rebuilds every visitor's arm
  from the existing access log. The HTML holds every arm inside comment markers and Flask strips the
  arms the visitor did not draw (no JS, no flicker, no CSP change). `traffic_report.py` buckets the funnel
  per arm with the bot filter and depth logic it already has; sign-up stamps the arms (a label, not an
  id) onto the account so forges and donations attribute too; one admin card reads it all out with a
  plain "probability B beats A".
- You always know what is being tested (section 3.10): a badge on the page itself when you are signed in
  as admin, the Experiments card at the top of the admin area, a Monday email digest, a mail on the day
  an experiment reaches its planned end, the deploy script announcing live experiments, and a written
  log. The registry refuses an experiment that has no one-sentence hypothesis or no planned end.
- Effort: Phase 0 ~1 h, Phase 1 (everything needed to run a splash test, badge and digest included)
  ~1.5 days, Phase 2 (account attribution) ~0.5 day, Phase 3 (inside the signed-in app) later.

## 1. Where we stand

### 1.1 Live numbers (droplet `traffic.json`, generated 2026-11-03)

| Window | humans | signed_in | clicked | browser | landing_only | workshop | devices |
|---|---|---|---|---|---|---|---|
| 7 days | 526 | 15 | 47 | 7 | 457 | 18 | desktop 394, phone 117, webview 15 |
| 30 days | 2666 | 57 | 767 | 42 | 1800 | 71 | desktop 1598, phone 496, webview 572 |
| 90 days (51 logged) | 3453 | 71 | 810 | 86 | 2486 | 71 | desktop 2222, phone 657, webview 574 |

`landing_only` (splash hit, no JS ran) is almost entirely scanners with a spoofed browser UA; the honest
weekly human count is `browser + clicked + signed_in` = ~70, of which ~15 are returning signed-in users.
Call it **50-60 new splash visitors a week organically, ~8 a day, mostly desktop**. The one tagged
campaign in the window is `youtube/promo-oct26` (the 2026-10-07..12 ad): 684 visitors, 95% phone, 0 signed in.

### 1.2 The clicked bucket is inflated (fix first)

`tools/traffic_report.py` counts a landing visitor as `clicked` when the same IP also fetched anything
matching `ENGAGED_RE` (`/login|app|help|download|deck/|archive|terms|privacy|auth/|api/|workshop`) minus
`SPLASH_API_PATHS = {/api/featured, /api/me}`. Since the Archive strip went on the landing
(featured.js, 2026-10-05) every splash load also fetches `/api/deck/<slug>/art/splash` x4, and since the
sign-up events shipped (2026-10-27) `/api/promo/active` too. Both match `^/api/`, so every JS-running
splash visitor is "clicked" and the `browser` bucket is nearly empty.

Measured on the droplet log for the 690 IPs that arrived with `utm_source=youtube&...oct26`:

| Path (200s) | hits |
|---|---|
| `/`, `/api/me`, `/api/featured`, `/api/deck/<4 slugs>/art/splash` | 855 / 832 / 711 / ~2580 |
| `/login` | 19 |
| `/download` | 13 |
| `/deck/<slug>` (any) | ~39 |
| `/help` | 2 |
| `/api/forge-class` | 3 |

So the real click-through from that ad was on the order of 50 of 690 (~7%), and the card says 621. The
memory note "clicked ~10/day is the honest floor" predates the strip and is no longer true either.

Fix (Phase 0): exclude the splash's own fetches by prefix, not by exact path — `/api/deck/<slug>/art/`,
`/api/promo/active`, `/api/featured`, `/api/me` — and keep `GET /api/deck/<slug>` (exactly) as the
`featured` overlay it already is. Add the oct26 case to `tests/test_traffic.py` (a splash visitor whose
only other hits are the four thumbs must land in `browser`, not `clicked`). The hand-built table in
PHONE_FUNNEL_PLAN.md section 1 is unaffected; the campaign row on the card will drop from 621 to ~50 and
that is correct.

## 2. Goal and non-goals

Goal: the operator can put two (or more) versions of a public page live at the same time, visitors see
one version consistently, and the traffic card shows, per version, how far visitors got — click through,
`/login`, signed in, Workshop, sign-ups, first forge, donation — with an honest read on whether the
difference is real yet. Starting, reading and ending an experiment never needs a server-side edit beyond
a deploy. The operator can tell at any moment, from the site, the admin page or their inbox, what is
being tested and what each visitor might be seeing.

Non-goals (for now): a third-party A/B service or analytics script (the site has none and the privacy page
says so); any new cookie or client-side storage for tracking (decision 1, section 7); a visual editor;
multivariate designs; experiments in the mod or the forge pipeline (the jev slots already cover the
generation side); automatic traffic reallocation ("bandits") — with this much traffic a fixed split and a
human decision are simpler and no slower.

## 3. Design

### 3.1 Assignment without a cookie

No visitor id is stored anywhere. The arm is computed from what the request already carries and nginx
already logs:

```python
def arm_for(ip: str, ua: str, exp: Experiment) -> str:
    h = int(hashlib.sha256(f"{ip}|{ua}|{exp.name}|{exp.salt}".encode()).hexdigest()[:8], 16) % 1000
    return pick(h, exp.arms, exp.weights)      # cumulative weights over 0..999
```

- `ip` is `_client_ip()` (X-Forwarded-For, i.e. nginx's `$remote_addr`), `ua` the raw User-Agent string.
  Both are in every access-log line, so `traffic_report.py` imports the same function and rebuilds the
  arm per visitor with no new log field and no nginx change.
- The SAME function in one module (`web/experiments.py`) is used by `app.py` (serve time) and by
  `tools/traffic_report.py` (report time). Change arms or weights -> new salt (or new name): old
  exposures are not comparable and must not be mixed.
- Consistency: a desktop on a home connection keeps its arm for as long as its IP holds (days to weeks —
  the same assumption the existing IP-keyed funnel already makes). A phone that changes IP between visits
  may see the other arm on a later visit; only the experimented page differs, nothing downstream, and at
  this traffic the dilution is noise. Two people behind one NAT with the same browser share an arm; they
  already share a depth bucket today. Accepted (decision 1).
- Override for preview and QA: `/?ab=hero:b` (comma-separated for several) serves that arm for THAT
  request only — nothing is remembered, so the admin badge (3.10) carries the links. The query string is in
  the log, so `traffic_report.py` marks any IP that sent `ab=` that day as an operator and drops it from
  the experiment counts for that day. The smoke harness uses the same door.
- Bots get arms too (server-side assignment cannot tell). The report's UA bot filter runs before arm
  bucketing, exactly as it does for the depth buckets, so they fall out the same way they do today; the
  ones that slip through split evenly across arms and dilute but do not bias.

### 3.2 The registry: `web/experiments.py`

One list, committed with the code — an experiment starts and ends with a deploy, which is also its audit
trail (git log). No admin UI to create experiments: the arms ARE HTML and need a deploy anyway.

```python
EXPERIMENTS = [
    Experiment(
        name="hero",                       # the token used in the HTML markers and the report
        page="/",                          # which page carries the markers ("/" also means /?utm...)
        arms=("a", "b"), weights=(50, 50), # "a" is always the control = today's page
        salt="2026-11-10",
        started="2026-11-10",              # exposures before this day are ignored
        planned_end="2026-12-22",          # REQUIRED: the day the decision is due (3.7, 3.10)
        ended=None, winner=None,           # set both to end it: the winner is served to everyone
        primary="login",                   # the one metric that decides it (3.5)
        hypothesis="Saying 'free with your own API key' on the button lifts /login opens, because the "
                   "cost question stops people before the pricing section far below the fold.",
        arms_text={"a": "Button says 'Create Your Own Class' (today)",
                   "b": "Button says 'Forge a class — free with your own API key'"},
    ),
]
```

Validation (a test, and `app.py` at import, so a bad registry fails the deploy's test step before the
restart): names `[a-z0-9_]+` and unique; arm "a" exists; weights sum to 100; at most ONE live experiment
per page; `ended` implies `winner`; `hypothesis`, `planned_end` and one `arms_text` line per arm are
REQUIRED and non-empty — an experiment that cannot be described in a sentence does not run.

### 3.3 Serving arms: markers in the HTML, stripped by Flask

The static pages are already served through small server-side substitutions (`/download`, `/deck/<slug>`
stamp placeholders). Experiments use the same idea with comment markers, so the HTML holds every arm and
stays valid HTML for the editor, the i18n build and the smoke harness:

```html
<div class="splash-actions">
  <!--ab hero:a-->
  <a id="signin" class="btn primary splash-go" href="/login" data-i18n="landing.hero.cta">Create Your Own Class</a>
  <!--/ab-->
  <!--ab hero:b-->
  <a id="signin" class="btn primary splash-go" href="/login" data-i18n="landing.hero.cta_b">Forge a class — free with your own API key</a>
  <!--/ab-->
</div>
```

`_page(name)` in `app.py` replaces `send_from_directory` for `/`, `/login` (signin.html is served by
auth.py — route it through the same helper), `/download`, `/help`, `/archive` (and `/deck`, which already
templates): read the file (cached by mtime), compute the visitor's arms for the live experiments on that
page, drop every `<!--ab x:y-->...<!--/ab-->` block whose arm was not drawn (regex, DOTALL; markers never
nest), stamp `data-ab="hero:b"` onto the `<html>` tag for CSS-only arms
(`html[data-ab~="hero:b"] .splash-tag { display:none }`), and answer with
`Cache-Control: private, no-cache` + `Vary: User-Agent` so no browser or proxy caches one visitor's arm
for another (nginx has `proxy_cache off` on `/` already). Markers for an experiment that is not live
(ended, or not in the registry) resolve to its `winner`, else to arm `a` — so ending an experiment in the
registry is enough to serve the winner to everyone, and the HTML can be cleaned up in the next commit.

Why not client-side (landing.js swapping the DOM)? It flickers (the scripts load at the end of the body
and the CSP forbids an inline pre-paint script), it would need a beacon or storage to record exposure —
the very thing decision 1 rules out — and it would be a second measurement path next to the log.

i18n: English is the HTML itself, so arm text is just text. A translated page rewrites by key, so an arm
that changes copy needs its own key (`landing.hero.cta_b`) in `docs/copy/COPY.md` + `COPY.zh.md`, or the
zh page shows the control string in both arms. Rule: an experiment on copy gets its own keys; an
experiment on layout/order/visibility needs none. Meta/OG tags and `<title>` are never inside markers (a
crawler's arm must not change the unfurl or the indexed description).

### 3.4 Recording: nothing new — the report recomputes the arm

The access log already has the IP, the user agent, the path and the query string. `traffic_report.py`
adds, per experiment in the registry, for days `>= started` (and `< ended` when set):

- `exposures`: IPs whose non-bot `GET <page>` 200 hit landed that day, arm = `arm_for(ip, ua, exp)` with
  the IP's FIRST non-bot UA of the day (the rule the device class already uses, so one IP sits in one
  arm per day; an IP that shows a second UA later that day and drew the other arm at serve time is the
  rare case accepted in 3.1);
- the same exclusive depth buckets as today per IP (`signed_in > clicked > browser > landing_only`);
- the overlays: `login` (`GET /login` 200), `provider` (`GET /login/<p>` or `/auth/email/start`),
  `workshop`, `deck`, `archive`, `download`;
- the device split per arm (an ad week and an organic week are different populations — section 6);
- IPs that sent `ab=` that day are excluded from that day (the operator previewing).

Output: `traffic.json["experiments"][name] = {arms: {a: {...}, b: {...}}, started, planned_end, ended,
device: {...}, p_beats_control, days_to_decision}` plus a daily series per arm for the chart. Because
the arm is recomputed from the log, a change to the registry's `started` or a fix to the hash is
reflected on the next 15-minute timer tick — there is no stored assignment to migrate.

### 3.5 Reading it: the Experiments card

A new card, placed ABOVE "Site traffic" in the admin area of `/app` (same gate,
`/api/admin/experiments`). Per live or recently ended experiment, first the words, then the numbers:

> **hero** on `/` — day 12 of 42 (started Nov 10, decision due Dec 22) · primary metric: `/login` opened
> *Hypothesis:* Saying 'free with your own API key' on the button lifts /login opens, because …
> **a (control):** Button says 'Create Your Own Class' (today) · [see it]
> **b:** Button says 'Forge a class — free with your own API key' · [see it]

| arm | exposures | clicked | /login | provider | signed in | workshop | new accounts | first forge | donated |
|---|---|---|---|---|---|---|---|---|---|
| a (control) | n | n (%) | n (%) | ... | | | | | |
| b | n | n (%) | n (%) | ... | | | | | |

Under it: "P(b beats a) on `/login`: 0.81 — not yet (needs 0.95, ≥200 exposures per arm, ≥14 days). At
the current ~55 exposures/week, a +50% lift would show in ~37 weeks; during an ad like Oct 7-12 in ~3
weeks." Both numbers are computed, not typed: the first from Beta(1+hits, 1+misses) per arm with
20 000 `random.betavariate` draws (no scipy on the droplet), the second from the two-proportion
sample-size formula in section 6 against the control's own rate and the last 7 days' exposure rate.
"[see it]" links are `/?ab=hero:a` and `/?ab=hero:b` in a new tab.

Decision rule, written on the card so it is not re-litigated per test: call a winner when
`P(beats control) >= 0.95` AND every arm has at least 200 exposures AND the experiment has run at least
14 days (weekday/weekend mix); otherwise, at `planned_end`, keep the control. Secondary metrics are for
understanding, not for deciding. Peeking is fine — the Bayesian read does not inflate with looks the way
a p-value does — but the minimum n and minimum days are what keep a lucky first week from calling it.

New accounts, first forge and donations come from the database (3.6); the rest from the log. The card
is honest when one side is missing ("no traffic summary yet" / "account attribution starts with Phase 2").

#### 3.5.1 Rule variant: "ship unless worse" (added 2026-11-10 for `skin`)

An experiment may set `rule="ship_unless_worse"` in the registry (two arms only; the default stays
`rule="must_win"`, the rule above, unchanged). Used when B is the direction the owner already wants and the
test exists to catch harm, not to prove a gain (first user: the sitewide `skin` experiment):

- Once every arm has `MIN_EXPOSURES` (200) exposures AND the run is `MIN_DAYS` (14) days old, if
  `P(b beats a) <= P_WORSE` (0.10, i.e. at least 90% sure B is worse) the rule stops it: `winner_by_rule = "a"`,
  status "stop: B is worse — keep the control".
- Otherwise it runs to `planned_end`; from then on `winner_by_rule = "b"`, status "decision due — ship B (not
  shown to be worse)", or "decision due — ship B (thin data)" when the minimum exposures / days were never met
  (B still ships: nothing showed it to be worse, and the owner chose this rule knowing the traffic is thin).
- Nothing changes for visitors until someone sets `ended` + `winner` (as with every experiment). The card, the
  Monday digest and the planned-end / early-stop mails print the rule sentence of each experiment shown
  (`ab_report.rule_sentence(rule)`), and `deploy.sh`'s summary line says "rule: ship B unless worse".

A `sitewide=True` experiment (also new for `skin`) draws its arm on every page that goes through
`pages.py` (every HTML page, `/app` included), so a visitor sees one arm everywhere; exposure and the
metrics are still read on its `page` exactly as for any other experiment, and the one-live-experiment-per-page
rule counts it against its `page` only.

### 3.6 Account attribution (Phase 2) — a label, not an identifier

The log can say "signed in" per arm but cannot say "this NEW account came from arm b" or "arm b's
accounts forged and donated more". One stamp at sign-up does: in `auth._resolve_identity` rule 4 (the
brand-new-account branch, next to `promo.grant_signup_bonus`), compute the visitor's arms for the live
experiments from the sign-up request's IP + UA and store the arms string (`"hero:b"`) in one new column
`users.signup_ab VARCHAR(200)` (`db._ensure_*` migration like the others). No visitor id, no IP, no UA
is stored — only which versions of the pages the account's first session was shown. `/api/admin/experiments`
then counts, per arm: accounts whose `signup_ab` names the arm, created on/after `started`; those with a
`done` ForgeJob; those with a paid Purchase; and the hosted cost of those forges — the same joins the
sign-up event stats already do in `promo.py` (`stats` on a promotion), reused rather than rewritten.

Returning users who already had an account before the experiment are in the log buckets ("signed in")
but never in new accounts; that is correct, and the card labels the DB columns "new accounts". Caveat
to keep in mind when reading: the sign-up request may come from a different IP than the splash visit
(phone moved networks, or the OAuth round trip) — then the stamped arm is the arm the sign-up page would
have shown, which for a splash-only experiment is still the right label in the vast majority of cases
(same device, same network minutes later).

### 3.7 Lifecycle and record

1. Write the hypothesis and the primary metric in `docs/experiments/LOG.md` BEFORE it goes live (one
   table row: name, page, arms, primary metric, start, planned end, result, decision). The registry entry
   carries the same hypothesis text (3.2) so the card and the log never disagree.
2. Deploy registry entry + markers. `deploy.sh` prints the live experiments (3.10). Preview each arm with
   `/?ab=name:x` on the live site; run the smoke harness `ab` scenario (3.8).
3. Let it run; read the card; do not touch the arms mid-flight (a copy tweak = a new experiment with a
   new salt).
4. End: set `ended` + `winner` in the registry (deploy). Everyone gets the winner at once. In the same or
   the next commit remove the markers and the losing arm from the HTML and the losing i18n keys from the
   copy docs, so the page never accumulates dead arms. Fill in the LOG row.
5. The card keeps showing ended experiments for 30 days, then they drop off (the LOG is the archive).
6. The `skin` experiment also has a share link, `/?look=board`: a neutral alias of `?ab=skin:b` for that
   request (pages.LOOK_ALIASES), with nothing stored on the visitor's device. board.js appends `look=board` to
   same-origin links on a page that was opened with it, so the look holds while browsing. Other hops are
   caught server-side (pages.carried_look / with_look): a GET page without `look` whose same-origin Referer
   has it is 302'd to itself plus `look=board`; the server redirects (/app, /login), the OAuth state
   (`<random>.board`), the emailed sign-in link and Stripe's return URLs carry it, so it survives sign-in.
   Like `?ab=`, it works from the deploy day and is ignored once the experiment has ended (the winner is
   served, and nothing redirects). The report drops an IP that sent `look=` that day from the experiment
   numbers, like an `?ab=` preview. When `skin` ends, remove `LOOK_ALIASES`' entry, the board.js carrier and
   the report's `has_look_override` with the losing arm.

### 3.8 Verification

- `tests/test_experiments.py`: `arm_for` is deterministic and matches weights over 10 000 (ip, ua) pairs
  within ±2%; the same request gets the same arm twice; `?ab=` forces for that request only (no
  Set-Cookie anywhere — asserted); markers strip correctly incl. several experiments on different pages,
  an ended experiment serving its winner, an unknown name serving arm a; `data-ab` stamped; cache headers
  set; registry validation (duplicate names, weights, two live on one page, missing hypothesis /
  planned_end / arms_text) fails at import.
- `tests/test_traffic.py`: per-arm buckets rebuilt from IP + UA with the shared function; operator IPs
  (`ab=` in the query) excluded for the day; exposures before `started` ignored; `p_beats_control` ≈ 0.5
  for identical arms and → 1 for a clear winner; `days_to_decision` sane; plus the Phase 0 oct26
  regression case.
- `tests/test_alerts.py` additions: the digest composes one block per live experiment and sends nothing
  when none is live; the planned-end mail fires once (throttle key per experiment).
- `tools/ui_smoke.mjs` scenario `ab`: loads `/?ab=<name>:a` and `:b` for every live experiment, asserts
  each arm's marker text is present and the other's absent, that the admin badge appears for the admin
  session and not for a plain user, and that the page still boots (board, Archive strip, sign-in button)
  in both arms.
- Deploy check: `curl -sI https://blankthespire.com/` shows `Vary: User-Agent` and NO `Set-Cookie`;
  `curl -s 'https://blankthespire.com/?ab=hero:b' | grep -c "Forge a class"` is 1; wait one timer tick
  (15 min) and the card shows exposures.

### 3.9 Privacy and the law (decision 1: minimal — nothing new)

- Nothing new is set on the visitor's device: no cookie, no localStorage, no beacon. The existing
  session cookie (sign-in) and the `bts.lang` preference are untouched.
- Nothing new is logged: the access log already holds IP, user agent, path and query string, and the
  privacy page already discloses server logs. The arm is a function of that data, computed on the fly.
- The only new stored datum is `users.signup_ab` (Phase 2): the names of the page versions an account's
  first session saw — a label with no identifier in it, deletable with the account.
- California (CCPA/CPRA): the regime bites on "selling" or "sharing" personal information and on
  cross-context behavioral advertising; first-party, same-site measurement from your own server log,
  shared with no one, is neither, and no opt-out signal (GPC) has anything to act on because no sale or
  share exists. The IP in the log is already there for the reasons the privacy page gives. EU ePrivacy
  (the cookie-banner rule) is about storing or reading from the device, which this design never does.
  Add one honest sentence to `privacy.html` anyway: "We sometimes show two versions of a page to
  different visitors and compare, in aggregate, how far each version's visitors got, using the same
  server logs described above. Nothing is stored on your device for this."
- Google explicitly allows A/B tests that serve different content as long as it is not cloaking; keep
  meta/OG tags and the `<title>` out of markers and never run a test longer than it needs.

### 3.10 Always knowing what is being tested (decision 2)

Six places, all fed from the one registry, so they cannot disagree:

1. **On the page itself, for the admin.** `/api/me` already tells every page who is signed in; for an
   admin it also returns `experiments: [{name, arm_shown, arms, arms_text, hypothesis, day, of}]` for
   the page just served (the server knows the arm it drew). A tiny shared `ab-badge.js` (loaded on the
   experimented pages next to `webview.js`) renders a fixed pill bottom-right, admin only:
   `🧪 hero · you see b · see a · see b · results` — the "see" links are `?ab=` previews, "results" opens
   the admin card. A plain visitor's `/api/me` carries no such field, and no badge exists in the HTML.
2. **The Experiments card at the top of the admin area** (3.5): the hypothesis and the arms in words
   before any number, day N of M, and a status line (`running — not yet`, `decision due`, `winner b
   called`, `ended, control kept`). Reads the registry live, so the moment a deploy adds an experiment
   the card lists it, with "no exposures yet" until the timer ticks.
3. **Monday morning email digest** (via `alerts._send_mail`, same Resend key and recipients as the credit
   alert; a `btsweb-experiments.timer` next to the traffic timer, or the traffic timer's run itself when
   it is Monday's first tick): one block per live experiment — the hypothesis, exposures per arm, the
   primary metric per arm, `P(beats control)`, days left — and nothing at all when nothing is live. The
   digest is the "what am I testing right now" answer for someone who has not opened the admin page in a
   week.
4. **Mail on the day `planned_end` passes** (once per experiment, throttled like the credit alert):
   "hero reached its planned end — P(b beats a) = 0.71. Decide: set winner or keep control." Also one
   when the decision rule is first met before the end date ("hero has a winner by the rule: b").
5. **The deploy script** prints, after the pull, `== live experiments: hero on / (a/b, since 2026-11-10,
   decision due 2026-12-22)` or `== live experiments: none`, and `app.py` logs the same line at boot — so
   every deploy and every restart restates what is running.
6. **`docs/experiments/LOG.md`**: the written record (3.7), one row per experiment, kept forever.

And the guardrail that makes 1-6 meaningful: the registry validation in 3.2 refuses an experiment that
lacks `hypothesis`, `planned_end` or an `arms_text` line per arm, so nothing can run that cannot be read
out in a sentence.

## 4. Phases

### Phase 0 — fix the baseline (~1 h, deploy on its own)

`traffic_report.py`: replace `SPLASH_API_PATHS` with a prefix list (`/api/me`, `/api/featured`,
`/api/promo/active`, `/api/deck/<slug>/art/`), regression test, redeploy, and let the timer rewrite
`traffic.json`. Update the memory note on "clicked". Nothing else depends on it, but every later number
does.

### Phase 1 — a splash experiment end to end (~1.5 days)

`experiments.py` (registry, validation, `arm_for`); `_page()` helper; markers on `landing.html` for the
first experiment (section 5) + its i18n keys; per-arm buckets + `p_beats_control` + `days_to_decision`
in `traffic_report.py`; `/api/admin/experiments` (log side only) and the card above Site traffic;
`/api/me` experiments field + `ab-badge.js`; deploy.sh / boot line; Monday digest + planned-end mail in
`alerts.py`; privacy sentence; `docs/experiments/LOG.md` with the first row; tests + smoke scenario.
No droplet step beyond the ordinary `deploy.sh` (bump `?v=` for `style.css`/`app.js`, and the pages that
gain `ab-badge.js`). Mod release ordering does not apply (no codec change).

### Phase 2 — account attribution (~0.5 day)

`users.signup_ab`, the rule-4 stamp, the "new accounts / first forge / donated" columns on the card and in
the digest, tests on `_resolve_identity` (rules 1-3 never stamp; rule 4 stamps; no live experiment stamps
an empty string).

### Phase 3 — inside the signed-in app (later, when there is a question worth it)

`index.html`/`app.js` experiments on the forge-first screen or the pay step: `window.BTS_AB` reads
`data-ab`, outcomes are already DB events (ForgeJob, Purchase) so no beacon is needed for the metrics that
matter; a UI-only outcome (opened the pay step, picked BYOK) would need a beacon, which decision 1 argues
against — prefer outcomes the database already records. Design when the first such hypothesis exists.

## 5. First experiments (candidates — Phase 1 ships with the first)

All on `/`, primary metric `/login` opened (the highest-rate downstream step that is still a real
decision; "clicked" is too soft, sign-up too rare — section 6). Control is always today's page.

1. **CTA copy.** "Create Your Own Class" vs a variant that says the price up front ("Forge a class — free
   with your own API key"). Hypothesis: the cost question stops people before `/login`; the pricing
   section is far below the fold. Readable organically only if the effect is large; six weeks planned.
2. **Lead with The Archive for phones.** The CTA-above-strip order was Ryan's call on 2026-10-22 after the
   phone reorder; an experiment is the way to settle it with the next ad's traffic rather than by
   argument. Primary metric would be `deck` opened + `/login`, device-split. Only worth running in an ad.
3. **"PC game" note placement.** `splash-pc` above the board vs below the CTA. Hypothesis: on a phone it
   is read as "not for me" before the pitch; moving it below the CTA keeps the ad click but may raise
   bounce-after-login. Device-split read required.
4. **`/login` for webviews**: email form first vs provider buttons first (page `/login`, metric
   `/auth/email/start`). Only readable in an ad (organic webview traffic is ~15/week).

Decision 2: ship Phase 1 with (1). (2)-(4) wait for whenever an ad is next bought (decision 3: none
planned), and that ad should be bought to answer one of them.

## 6. Sample-size reality (why most of this waits for an ad)

Two-proportion test, two-sided α = 0.05, power 0.80, visitors per ARM; "weeks" at ~55 splash exposures a
week organically, "ad days" at the October rate (~115 a day):

| Baseline → target on the primary metric | per arm | total | organic | in an ad |
|---|---|---|---|---|
| 7% → 14% (`/login`, doubling) | ~300 | ~600 | ~11 weeks | ~5 days |
| 7% → 10.5% (+50% relative) | ~1 020 | ~2 040 | ~37 weeks | ~18 days |
| 25% → 32% (a soft metric such as any click) | ~640 | ~1 280 | ~23 weeks | ~11 days |
| 1% → 2% (sign-up) | ~2 300 | ~4 600 | never | ~40 days |

So: organically, only a doubling on `/login` is detectable within a quarter; anything on sign-up or
donation needs an ad-scale burst and a big effect. Two consequences for the design above: the card must
say "not yet" loudly and compute the time-to-decision, and every experiment must be device-split, because
an ad week (95% phone, mostly in-app webview) and an organic week (75% desktop) are different populations
and a winner in one is not a winner in the other.

## 7. Decisions taken 2026-11-03

1. **Minimal tracking, to stay comfortably inside California law:** no new cookie or device storage; the
   arm is derived from the IP + user agent nginx already logs; the only new stored datum is the arms
   label on a new account (3.6, 3.9). The trade-off accepted: a visitor whose IP changes may see the
   other arm on a later visit.
2. **First experiment: CTA copy (section 5, #1).** Operator visibility is a requirement, met by section
   3.10 (page badge, card, Monday digest, end-date mail, deploy line, written log, and a registry that
   refuses an undescribed experiment).
3. **No ad is scheduled.** No deadline on Phases 1-2; when an ad is next considered, Phases 1 and 2 go
   live and get smoke-tested at least a week before it, and the ad is bought to answer a named question.
4. **Plan only for now.** Phase 0 (the clicked-bucket fix) is the first thing to build when work starts.
