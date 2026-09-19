# Pricing v3: no free tokens, key-or-donate onboarding, stepped thank-you tokens

> Status: PLANNED 2026-09-18 (not built). Supersedes the "1 free token per UTC day" rule in
> DEPLOYMENT_PLAN.md Part 3 and the 1-token-per-dollar + %-bonus schedule in `web/billing.py`.

## 1. What changes (Ryan's call, 2026-09-18)

| Area | Today (v2, live since 2026-09-16) | v3 |
|---|---|---|
| Free daily token | 1 per UTC day, every account | **none** |
| Starter tokens | 5 on sign-up (`INITIAL_TOKENS`) | **0** |
| BYOK | free, unlimited | unchanged, and becomes the *promoted* path |
| Donations | $1..$500, 1 token per whole dollar, +10/20/30% from $10/$20/$50 | **$3 = 2, $5 = 4, $10 = 10, above $10 one token per whole dollar** (see 1.1) |
| First-run UX | forge tab opens on "Use a token" with the free token pre-selected | **a chooser: "I have an API key" vs "Let BLANK handle it"** (see 3) |
| Per-IP free-forge cap | 5 free forges / IP / day | dead code, removed; global daily kill-switch stays |

### 1.1 Fixed donation tiers, Stripe fee passed to the donor (Ryan, 2026-09-18)

No custom amounts. The donate UI is a row of fixed buttons; `/api/donate` takes a **tier id**, not cents.
The "one token per dollar above $10" rule becomes two fixed higher tiers ($20, $50) since there is no free
text field. Ryan can drop or change the two high tiers; the first three are his anchors.

| Tier id | You give (net) | Tokens | Stripe fee (2.9% + 30c) | Donor is charged (gross) |
|---|---|---|---|---|
| `t3` | $3.00 | 2 | $0.40 | **$3.40** |
| `t5` | $5.00 | 4 | $0.46 | **$5.46** |
| `t10` | $10.00 | 10 | $0.61 | **$10.61** |
| `t20` | $20.00 | 20 | $0.91 | **$20.91** |
| `t50` | $50.00 | 50 | $1.81 | **$51.81** |

Gross is solved so that `gross - (gross * 2.9% + 30c) = net`, i.e. `gross = ceil((net + 30) / 0.971)` in
cents. The Checkout session carries **two line items**: "Donation: BLANK the spire" at net and "Card
processing fee" at gross minus net, so the Stripe receipt shows the split. Rates live in env
(`STRIPE_FEE_PCT=2.9`, `STRIPE_FEE_FIXED_CENTS=30`) so a rate change is a config edit. Caveats, stated once:
- Stripe's rate is higher for international cards (+1.5%) and currency conversion (+1%); the fixed
  pass-through covers the domestic rate and we eat the difference on the rest. Good enough.
- A few US states restrict card surcharges (MA, CT) and the card networks want surcharges disclosed as
  such. Labelling it "card processing fee" on a donation is the common charity-platform pattern; if that
  ever becomes a concern, the fallback is a pre-checked "cover the processing fee" checkbox, which makes
  it voluntary and dodges surcharge rules entirely. Ryan's call was mandatory pass-through; plan does that.

Unit economics (memory: ~$0.93 metered per hosted forge on the glm-5.3 route): with the fee passed on, the
net is the full $1.50 / $1.25 / $1.00 per token. $10 = 10 tokens is roughly break-even on cost.

### 1.2 Existing balances (decided: keep)

Every existing `token_balance` stays exactly as it is (starter 5s, thank-you tokens). Nothing new is
granted; nothing already granted is clawed back. No data migration.

### 1.3 Policy note (Mega Crit)

With no free hosted path, "tokens only via donation" reads closer to a sale than v2 did. What keeps it in
the donation lane: the mod is free + open source, BYOK forging is free and unlimited (the *default* path in
v3's chooser), classes are usable/shareable regardless of how they were forged, and the Workshop page stays
price-free (workshop/README.md rule). Terms keep "donations are support, tokens are a thank-you".

## 2. Backend

### 2.1 `web/models.py`
- `INITIAL_TOKENS = 0`. Keep the constant (db migration + tests import it). `server_default="0"` follows.
- `free_token_available()`: delete. `spend_token()`: paid only (`if balance > 0: balance -= 1; return "paid"`,
  else `None`). `unspend_token()`: only the `"paid"` branch. Drop `grant_daily_token` (retired stub).
- `User.last_free_token_day`: leave the column in place (prod MySQL, no-Alembic boot migrations cannot drop
  cleanly across engines). Stop reading/writing it. Comment it LEGACY. `db._ensure_user_columns` keeps the
  ALTER for old DBs (harmless).

### 2.2 `web/billing.py`
- Replace `TOKENS_PER_DOLLAR`, `BONUS_TIERS`, `MIN/MAX_DONATION_CENTS`, `PRESETS` and `_parse_presets` with
  one fixed table plus the fee config:
  ```python
  # Fixed donation tiers: id -> (net cents the project receives, thank-you tokens). No custom amounts.
  DONATION_TIERS = {"t3": (300, 2), "t5": (500, 4), "t10": (1000, 10), "t20": (2000, 20), "t50": (5000, 50)}
  STRIPE_FEE_PCT = float(os.environ.get("STRIPE_FEE_PCT", "2.9"))
  STRIPE_FEE_FIXED_CENTS = int(os.environ.get("STRIPE_FEE_FIXED_CENTS", "30"))

  def gross_for(net_cents) -> int:      # smallest charge that nets `net_cents` after Stripe's cut
      return math.ceil((net_cents + STRIPE_FEE_FIXED_CENTS) / (1 - STRIPE_FEE_PCT / 100))
  def fee_for(net_cents) -> int:        # the pass-through line item
      return gross_for(net_cents) - net_cents
  ```
  `BTSWEB_DONATION_PRESETS` env var is retired (delete from the deploy doc).
- `/api/billing` returns `tiers: [{id, net_cents, fee_cents, gross_cents, tokens}]` (+ `enabled`, `currency`).
- `/api/donate` body becomes `{"tier": "t5"}`; unknown id is a 400. Checkout session: `mode=payment`,
  `submit_type=donate`, **two** line items (donation at net, "Card processing fee" at fee), metadata
  `{user_id, tokens, price_id: tier id, net_cents}`. Tokens are still frozen in metadata at checkout, so
  changing the table can't mis-credit an in-flight session. Success URL unchanged; the browser returns to
  the **forge** tab (see 3.4).
- `_credit_purchase`: `Purchase.amount_cents` stays `amount_total` (gross, what the card was charged);
  `price_id` = tier id (history renders "Donated $5.46 (incl. $0.46 card fee)" from `net_cents` metadata
  or by `tier lookup`). Refund clawback unchanged: refund the gross in the dashboard, tokens claw back.
- `Purchase.summary()` (models.py): add `net_cents` if we want the history split; otherwise the UI computes
  fee = gross - tier net from the tier table by `price_id`. Plan: store it (one nullable column,
  `db._ensure_purchase_columns`, same pattern as the others) so history survives a rate change.
- Docstring rewrite (the top-of-file pricing narrative).

### 2.3 `web/app.py` and `web/auth.py`
- `_token_state()` returns `{"token_balance": n}` only. `/api/me` (auth.py:535-538) drops `free_token_available`.
- Forge admission (app.py ~988-1022): drop `would_be_free` / `counted_free` / `free_limiter.check(ip, free=...)`.
  Keep the **global** daily kill-switch: fold `FreeForgeLimiter` down to a `TokenForgeLimiter` with only
  `daily_cap` (rename; the old name would mislead). Delete `BTSWEB_FREE_IP_DAILY_CAP` from env docs.
- 402 messages: see copy row 17.
- `refund_state()` no longer uncounts an IP.
- Module docstring (app.py:10-11) rewrite.

### 2.4 Tests (`web/tests`)
- `test_tokens.py`: delete `free_token_is_spent_before_paid`, `free_token_returns_after_utc_rollover`,
  the `"free"` half of `unspend_restores_the_right_kind`, `per_ip_cap_limits_free_forges_but_not_paid`;
  rewrite `me_reports_free_flag_and_paid_balance` (balance only), `token_forge_spends_free_first_then_paid`
  (spends paid), `402_when_nothing_to_spend` (a fresh account now 402s by default since INITIAL_TOKENS=0).
  Add `test_new_account_has_zero_tokens`. Keep `failed_forge_refunds_a_paid_token`.
- `test_billing.py`: replace `thank_you_tokens_are_one_per_dollar_plus_tier_bonus` and
  `preset_env_parsing_skips_junk_and_falls_back` with: the tier table maps ids to tokens (t3 = 2, t5 = 4,
  t10 = 10, t20 = 20, t50 = 50); `gross_for` nets the tier amount after 2.9% + 30c (340, 546, 1061, 2091,
  5181) and stays correct for a changed fee env; `/api/donate` with an unknown or missing tier is a 400 and
  with `amount_cents` alone is a 400; the created session has two line items whose unit amounts sum to
  gross; credited `Purchase.amount_cents` is gross and `net_cents` is the tier net.
  `pack_era_rows_still_show_in_history` unchanged.
- `conftest.py`: any fixture that assumes a free token or a 5-token starter balance gets an explicit
  `token_balance=` seed.
- `test_admin_stats.py`: the dashboard's free-vs-paid split on `forge_jobs.token_kind` keeps working on
  historical rows; no new "free" rows will appear.

## 3. Frontend (`web/static/index.html`, `app.js`)

### 3.1 Onboarding chooser
When the signed-in user has `token_balance == 0`, is not unlimited, and has no saved BYOK key in
`localStorage.bts_byok`, the forge tab shows a two-card chooser **above** the concept box (replacing the
current "default the radio to BYOK" fallback):

```
How do you want to forge?
+------------------------------+  +------------------------------+
| I have an API key            |  | Let BLANK handle it          |
| Free & unlimited. Paste a    |  | We run it on our models.     |
| key from Anthropic, OpenAI,  |  | Support the forge and get    |
| OpenRouter... it stays in    |  | tokens as a thank-you:       |
| your browser.                |  | $3 = 2 . $5 = 4 . $10 = 10   |
| [Use my key]                 |  | [Support the forge]          |
+------------------------------+  +------------------------------+
```
- "Use my key" selects the BYOK radio, opens Generation settings, focuses the provider select (the
  existing key-prefix auto-detect and "Load available models" stay). Remember `bts_forge_pref = "byok"`.
- "Support the forge" opens the donate panel **inline** (a `<details>` on the forge tab, tier buttons read
  from `/api/billing`), not a tab switch. Remember `bts_forge_pref = "token"`.
- Tier buttons render as e.g. **"$3 = 2 tokens"** with a small line under each: "$3.40 charged incl. $0.40
  card fee". Same component on the Account tab. No custom-amount input anywhere.
- The chooser collapses to a one-line "Forging with your key . change" / "Forging with tokens . change"
  strip once a preference exists. The Generation settings radios remain the source of truth.
- Header chip: `N tokens`; `0 tokens` gets the `.empty` style; drop the "1 free..." variants.

### 3.2 Token-status / forge-button strings
`renderTokens()`, `renderForgeButton()`, the confirm() in `forge()` and the "No tokens to spend" toast lose
their free-token branches. Exact replacement strings in section 5.

### 3.3 Account tab
Balance + "Support the forge" panel stay; the blurb states the fixed tiers and that the card fee is added;
the `donate-custom` input + button are **removed** (`donate()` takes a tier id). "Donation history" rows
show gross with the fee split: "Donated $5.46 ($5.00 + $0.46 card fee) . +4 tokens".

### 3.4 Return from Stripe
`handlePurchaseReturn()`: after crediting, `selectTab("forge")` and select the token radio (the user came
here to forge). Toast: copy row 16.

### 3.5 Existing-user notice
One dismissible banner on `/app` for ~2 weeks (localStorage flag). Copy row 9.

## 4. Docs / env
- `web/DEPLOY-DIGITALOCEAN.md`: remove `BTSWEB_FREE_IP_DAILY_CAP` and `BTSWEB_DONATION_PRESETS`; add
  `STRIPE_FEE_PCT` / `STRIPE_FEE_FIXED_CENTS` (optional, defaults 2.9 / 30); rewrite the "Stripe donations"
  comment and the "Token-path guards" bullet.
- `web/README.md` lines 19-22 + billing row; root `README.md` line 21 (still says "paid token packs", stale
  since 2026-09-16 anyway); `INSTALL.md` section 3 step 2 (also stale: "you can buy more").
- `workshop/DESCRIPTION.bbcode`: one sentence must change, and the Workshop page must stay price-free, so it
  says hosted models are available on the site with no amounts. Requires a Workshop description re-upload
  (mod zip unchanged; no version bump).
- `docs/plans/DEPLOYMENT_PLAN.md` Part 3: add a SUPERSEDED-by-this-file note.
- Memory note `pricing-model-megacrit-permission`: update on ship.

## 5. Copy inventory

**The editable version lives in `docs/plans/PRICING_V3_COPY.md`** (one block per string; Ryan edits the
NEW blocks in VS Code, then they are pasted in verbatim). The table below is the locator index only and
may lag the copy file. Every user-facing string that mentions the free token, starter tokens, custom
amounts, or the old schedule.

| # | File:line | Current | Proposed |
|---|---|---|---|
| 1 | landing.html:57-62 (pricing section) | 3 bullets: BYOK free / One free token a day / Want to help? | **Bring your own API key**: free, unlimited forging. Anthropic, OpenAI, Google, OpenRouter and more; your provider bills you and your key stays in your browser. / **Or let us run it**: support the forge and get tokens as a thank-you. $3 = 2 tokens, $5 = 4, $10 = 10, and one token per dollar above that. One token forges one class on our models. / **The mod is free** and open source. There is nothing to buy; donations keep the hosted forge running. |
| 2 | index.html:19 chip tooltip | "...every account gets a free token each day." | "Tokens are spent by the 'Use a token' forge option. Support the forge on the Account tab to receive more." |
| 3 | index.html:46-47 radios | "Use a token" / "Bring your own key" | keep, or "Use a token (our models)" / "Bring your own key (free)" |
| 4 | index.html:52 token-status default | "Forges on our models: one token per class." | keep |
| 5 | index.html:143-145 Account blurb | "...Every account gets a free token each day... forging never costs money..." | "One token forges one class on our models. Bring your own API key and forging is free and unlimited, no token needed." |
| 6 | index.html:150-152 Support blurb + 153-159 tier buttons (custom input removed) | "...every whole dollar adds a token... $10 = 11, $20 = 24, $50 = 65" | see copy file items 25-27 (fixed tiers, fee line under each button) |
| 7 | index.html:161-162 donate-note | "...your free daily token and BYOK forging both keep working." | "Donations aren't available right now. Bring your own API key to keep forging." |
| 8 | index.html NEW chooser | none | "How do you want to forge?" + card 1 "I have an API key" / "Free and unlimited. Paste a key from Anthropic, OpenAI, OpenRouter and more; it stays in your browser." / button "Use my key" + card 2 "Let BLANK handle it" / "We run it on our models. Support the forge and get tokens as a thank-you: $3 = 2, $5 = 4, $10 = 10." / button "Support the forge" |
| 9 | index.html NEW banner | none | "Heads-up: the daily free token is gone. Bring your own API key to forge free and unlimited, or support the forge for tokens. Tokens you already hold are untouched." |
| 10 | app.js:80 chip | "1 free token" / "1 free + N tokens" | "N tokens" only |
| 11 | app.js:87-97 token-status | 3 free-token variants | paid > 0: "Forges on our models. Uses 1 of your N tokens." / paid == 0: "You have no tokens. Bring your own key below (free, unlimited), or support the forge to get some." |
| 12 | app.js:106-107 acct-free | "Today's free token: available/spent..." | remove the line |
| 13 | app.js:137-139 forge button | "uses today's free token" | "uses 1 of your N tokens" / "no tokens: support the forge or bring a key" |
| 14 | app.js:339 toast | "No tokens to spend: wait for tomorrow's free token, or bring your own key." | "No tokens to spend. Support the forge for some, or bring your own key." |
| 15 | app.js:343-345 confirm | "This will use today's free token..." | "This will use 1 token. You have N. Forge this class?" |
| 16 | app.js:795-796 thank-you toast | "Thank you for supporting the forge: N tokens added!" | "Thank you! N tokens added. You're ready to forge." |
| 17 | app.py:1010,1022 402 error | "...your free daily token arrives tomorrow (UTC), or bring your own API key..." | "you're out of tokens. Support the forge on the Account tab, or bring your own API key to keep forging." |
| 18 | app.py:176-180 limiter | "this network has used its free forges for today..." | delete (IP cap gone); keep the daily-limit line |
| 19 | terms.html:37-39 | "Every account receives one free token per day... New accounts also receive free starter tokens." | "One token = one class generation with the 'Use a token' option, which runs on our models. Tokens are received as a thank-you for donations (below); accounts do not receive free tokens." |
| 20 | terms.html:40-44 + refund bullet 52-53 | "...each whole dollar donated adds one bonus token... (10% from $10, 20% from $20, 30% from $50)." | fixed amounts, fee shown separately and added, tier list, refunds include the fee (copy file items 35, 37) |
| 21 | terms.html:62-63 | "unspent paid tokens on a suspended account are refunded on request" | "unspent thank-you tokens" (wording only) |
| 22 | privacy.html:24 | "...the day you last used your free daily token..." | drop that clause |
| 23 | privacy.html:51-52 | "...track your token balance (including the free daily token)..." | "...track your token balance..." |
| 24 | INSTALL.md:68-70 | "every account gets one free token a day, and you can buy more" | "**Use a token** forges on the site's hosted models (tokens come as a thank-you for supporting the site). Or pick **Bring your own key** (Anthropic, OpenAI, and others) to forge for free with your own API key: unlimited, billed by your provider." |
| 25 | README.md:21 | "one free hosted forge a day otherwise, and paid token packs beyond that" | "Forging is free and unlimited with your own API key; the hosted models run on tokens received as a thank-you for donations (the mod itself is free)." |
| 26 | web/README.md:19-22 | free token per UTC day + starter tokens | rewrite to match |
| 27 | workshop/DESCRIPTION.bbcode, paragraph "Forging happens on the website..." | "...or use the site's hosted models with the free daily forge every account gets." | "Bring your own LLM API key and forge as much as you like, or use the site's hosted models. This Workshop item is free and open source, and contains no purchases." |
| 28 | DEPLOY-DIGITALOCEAN.md:80, 212-214 | env comment + guards bullet | rewrite (operator-facing) |

## 6. Order of work
1. Backend + tests (models, billing, app, auth `/api/me`): one commit, `uv run python -m pytest web/tests`.
2. Frontend strings + chooser + inline donate + return-to-forge: one commit; `web/tools/ui_smoke.mjs` pass.
3. Terms / privacy / landing / READMEs / INSTALL / deploy doc: one commit (Ryan's copy).
4. Deploy (`ssh blankdroplet`, `sudo /opt/btsweb/deploy.sh`); no mod zip change. Drop
   `BTSWEB_FREE_IP_DAILY_CAP` from `/opt/btsweb/web/.env` (ignored if left; tidy).
5. Re-upload the Workshop description (text only, item 3803255976).
6. Update memory `pricing-model-megacrit-permission`; SUPERSEDED note in DEPLOYMENT_PLAN.md Part 3.
