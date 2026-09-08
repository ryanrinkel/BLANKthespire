# BLANK the spire: Production Deployment Plan

> **Decisions taken when execution started (2026-09-08):** the free daily token is tracked separately from the
> paid balance (`users.last_free_token_day` = the day it was last *spent*), so buyers never lose it. No
> single-token pack; packs are 5/$5, 11/$10, 24/$20, 65/$50 (`web/billing.py`). "Connect your account"
> (OpenRouter OAuth) is dropped — bring-your-own-key stays the free path, with Anthropic and OpenAI keys
> first-class. Per-IP daily cap applies to *free-token* forges only, never to paid tokens. `mode=hosted`
> answers 410. Web tests live in `web/tests` (Flask test client, SQLite, no network).

Status: DRAFT, compiled 2026-09-08 from a code read of `generation/`, `web/`, `workshop/`, the July 12 go-to-public plan, and the forge logs and ledger in `generation/scratch/`.

**Bottom line.** Three workstreams stand between the current build and a public launch:

1. **Creative harness.** The "same cards every time" feeling has concrete, measurable causes. The harness is a funnel: a hot brainstorm stage feeds a fixed 34-archetype catalog that 19 archetypes never escape, then a per-card prompt that still says "Ironclad-like Strength/Block character" with three Ironclad basics as its only exemplars, run cold (temperature 0.3), and finally a coverage repair pass that injects the same three mechanics (`attacked`, `thorns`, `metallicize`) into most classes. Each cause has a targeted fix, and a benchmark is defined below so the fix is measured, not felt.
2. **Pricing.** The code already has a token economy, a daily free token, and idempotent Stripe crediting. Moving from donations to sales is mostly a restore of the token-pack code you retired on July 13 (private repo commit `d6f5592` / `d734492`), plus a fix to the daily-token rule, a "Connect with OpenRouter" button, and coordinated copy, terms, and tax changes. One reality check: no major provider lets a third-party app spend a user's subscription, so "connect your account" means OpenRouter OAuth plus paste-your-key for everyone else.
3. **Production hardening and Workshop.** Most of the July P0 list is done. What remains is small but real: one SSRF gap, enumerable deck ids, an unversioned deploy script, no CI, no backups of forged art or feedback logs, no health endpoint, and a Workshop listing that has never been uploaded and lacks its required thumbnail.

Suggested order: instrument and test first (Phase 0), fix the harness behind a flag and measure it (Phase 1), ship pricing (Phase 2), then publish the Workshop item and announce (Phase 3). Roughly three to four working weeks at a solo pace.

---

## Part 1. Where things stand today

| Area | State | Evidence |
|---|---|---|
| Site | Live at blankthespire.com, HTTP 200, download page serving v0.1.7 | curl on 2026-09-08 |
| Generator tests | 316 pass offline in this checkout | `uv run pytest` in `generation/` |
| Web tests | None exist | no `web/tests/`, no Flask test client usage anywhere |
| Git | Clean except uncommitted `workshop/` and a `.gitignore` edit | `git status` |
| Hosted forge path | `token` mode on Ollama Cloud: gemma4:31b brainstorm, glm-5.2 structure and cards; OpenRouter failover | `btsgen/ollama_mix.py:62-101` |
| Cost tracking | None. `on_usage` hooks exist in btsgen but `web/forge.py` never passes them | `web/forge.py:365`, `btsgen/generator.py:99` |
| Billing | Pay-what-you-want donations, 1 thank-you token per dollar; daily free token only when balance is 0 | `web/billing.py:39-41`, `web/models.py:28-38` |
| Workshop | Staged, private, never uploaded; `tags` empty, no `image.png`, no `mod_id.txt` | `workshop/workspace/` |
| Deploy | Droplet + gunicorn (1 worker, load-bearing) + nginx + DO Managed MySQL; `/opt/btsweb/deploy.sh` not in repo | `web/deploy/gunicorn.conf.py:9` |
| Monitoring, backups, CI | None | `.github/` has only an issue template |

A note on repo copies: `C:\Users\ryanr\Desktop\NOVOGODOT\BLANKthespire` (private, full history) and `...\BLANKthespire-prod\BLANKthespire` (public, fresh history) both exist locally. The first `uv run pytest` in the prod checkout imported btsgen from the sibling `public-repo` checkout. Run tests with `PYTHONPATH` set to the checkout under test, and consider deleting stale sibling checkouts before launch to avoid deploying the wrong tree.

---

## Part 2. Creative harness: why the output converges, and the fix

### 2.1 Diagnosis, ranked by impact

The forge pipeline in production is: cloud/cluster (hot, gemma) -> map/compose against the archetype catalog (cold, glm) -> relic intent (hot) -> blueprint (cold, 387-line prompt) -> ~33 per-card calls (cold) -> validate/repair/balance -> coverage repair -> keystone relic -> assemble. Sameness enters at five points.

**Cause 1. The coverage repair pass injects the same mechanics into every class.**
`btsgen/coverage.py:31-51` holds three ordered menus (reactive triggers, "when" conditions, exotic statuses). Quotas at lines 20-26 fire on nearly every forge, and the walker takes the first missing entry every time (lines 238-258). In three consecutive real forge logs the injected mechanics were `attacked`, then `thorns`, then `metallicize`: the literal head of each menu. Across the 14 forges in `generation/scratch/forge_ledger.jsonl`, `attacked` appears in 6, `thorns` in 5, `metallicize` in 5, regardless of theme. This pass was built to raise breadth per class; it guarantees the same breadth in every class.

**Cause 2. The per-card prompt describes a different game and anchors on three Ironclad basics.**
`btsgen/contract.py:199-201` opens every card call with "for a single Ironclad-like Strength/Block character." The exemplar list at lines 54-57 names 10 cards, but 7 do not exist in `mod/content/cards` and are silently dropped (lines 95-98). What ships is Strike, Defend, and Bash under the header "match this style and balance" (line 212). Measured over 526 quarantined cards in `generation/scratch/_class_gen/`: the most common effect skeleton is `{damage, apply_status}` at 27%, and 142 of those 144 apply poison. The one compositional-design instruction (lines 241-245) names ops (`multi`, `from_state`, `conditional`, `add_card recursion`) that are not in `mod/contract/VOCABULARY.md`, so the validator rejects them and the model falls back to the flat stat line it was told to avoid.

**Cause 3. Identity is a draw of 3 from a fixed 34-item catalog, and the selection math prefers repeats.**
`btsgen/data/archetypes.json` has 34 archetypes; the map prompt forbids inventing new ones (`frontend/stage_map.py:184-185`) and "STRONGLY prefers" the BUILDABLE-tagged ones (lines 169-173). The candidate score is `10 x fidelity + distinctiveness - novelty`, with novelty capped at 2.0 by design (`frontend/builder.py:31,565-567`, `ledger.py:27`). A faithful repeat always beats a slightly-less-faithful novel pick. Result: 19 of 34 archetypes have never been chosen in 14 forges, including the entire Forge/signature-blade, slot-machine, metamorph, and tag-synergy systems that hundreds of prompt lines describe. The three kingmakers (`retain_hold`, `poison_attrition`, `ascetic_purge`) appear in 4 of 14 each.

**Cause 4. Catalog metaphors and in-prompt examples leak verbatim into card names and designs.**
`retain_hold.metaphors` ("the held breath", "coiling", "patience", "vigil") reach the model in the map prompt, the blueprint brief, and every card call. Across five triad runs the card name "Held Breath" appears in two different classes; "Held" leads 5 names, "Coiled" 4, "Patient/Patience" 7, "Vigil" 4. The blueprint prompt's homage example "Deflect: 0-cost skill, gain 4 Block" (`class_forge.py:586-592`) becomes a card named Deflect in 2 of 5 runs.

**Cause 5. The only hot stage is forbidden from touching mechanics; everything that decides mechanics is cold.**
`ollama_mix.py:72-86`: brainstorm at 0.9 but told "do NOT talk about game mechanics, cards, damage, or numbers" (`stage_cloud.py:27-29`); structure at 0.4 and cards at 0.3 with `reasoning_effort: none`. The premise in the code comment ("the creative divergence already happened upstream") is only true if the catalog can carry that divergence, and Cause 3 shows it cannot. The Anthropic BYOK path sends no temperature at all and runs adaptive thinking, so BYOK users on Claude get materially more varied output than token users.

Secondary contributors: the reprint gate hard-errors at uncommon/rare when a skeleton matches any earlier card in the same class within +/-1 (`validator.py:1028-1033`), so late cards in a class are pushed into gimmicks or dropped; a single repair attempt with no diversity guidance (`pipeline.py:73`, `contract.py:268-277`); and structural quotas (Strike/Defend, 3 strategies fixed to aggro/control/combo, 4 bridges, 1 homage, 10-card starter) that pre-commit roughly 20 of 35 slots by shape before theme gets a vote.

Your own Phase N plan already recorded the key lesson: "the local model ignores prose adjectives." The anti-convergence instructions that exist are all prose. The fixes below are structural.

### 2.2 The fix, in order of impact per effort

Ship all of this behind one flag (`BTS_HARNESS_V2=1`) so production can A/B via the ledger and roll back by env var.

**Fix A. Rewrite the per-card contract (contract.py). Half a day.**
- Replace the "Ironclad-like Strength/Block character" framing with the class identity block (name, fantasy, three archetypes, pair lines) in the system prompt itself, not only in the trailing context.
- Replace the three Ironclad exemplars. Exemplars should be class-appropriate and rotate: pick 3 from a curated pool of 30 to 40 hand-approved forged cards spanning every archetype family, chosen by the card's archetype and rarity, and never the same three twice in a class. Keep Strike/Defend/Bash out of the exemplar block entirely (they are synthesized by rule anyway).
- Rewrite the compositional-design clause to name ops that exist in `VOCABULARY.md` (for example `add_trigger`, `transform_card`, `graft_card`, `scry`, `balance_step`, `purge`, `grow`, state-scaled amounts, X-cost). Generate this list from the vocabulary file at build time so it cannot drift again.
- Add a per-class "already used shapes" line: the effect skeletons and status keywords already present in this class, with the instruction that this card must differ in at least one op. This replaces the reprint gate's hard error with guidance up front, and lets the gate downgrade to a warning at uncommon.

**Fix B. Make the coverage pass theme-driven and shuffled (coverage.py). Half a day.**
- Ask the blueprint stage to nominate, per class, which 3 reactive triggers, 4 "when" kinds, and 3 exotic statuses fit the theme (cheap: one JSON field on an existing call). The coverage pass may only fill from the nominated set.
- If no nomination exists, shuffle each menu with a seed derived from the concept hash, so two classes never receive the same injection order.
- Remove `thorns` and `metallicize` from the default head of the exotic menu; they are the most generic entries in the vocabulary.
- Log every injection to the ledger so the benchmark below can count them.

**Fix C. Rotate the catalog window and force one cold archetype (builder.py, stage_map.py, ledger.py). One day.**
- Do not show all 34 archetypes on every forge. Show a window of 14 to 16: the ones whose tags match the cloud stage's clusters, plus a seeded random fill, plus at least 4 from the "coldest" set (lowest global usage in the ledger). Fewer options with rotation beats a long list with a "prefer buildable" instruction.
- Require that at least one of the three chosen archetypes comes from the cold set unless fidelity to the concept would drop below a threshold. Implement as a hard constraint on the candidate filter, not as prompt prose.
- Raise the novelty cap from 2.0 to 6.0 for global recency (keep the per-user ledger as is). A 10x fidelity weight with a 2.0 cap means novelty never wins; with 6.0 it wins when fidelity is within 0.6 of the best candidate.
- Keep archetype `metaphors` in the cloud stage only. Strip them from the blueprint brief and from `_class_context` in card calls (Cause 4). The card model should get the class's own fantasy line, not the catalog's stock phrases.

**Fix D. De-anchor the blueprint prompt (class_forge.py). One day.**
- Replace the fixed homage examples (Deflect/Slice/Bludgeon) with a rotating draw of 3 from a pool of 20, seeded per forge.
- Include the long archetype "sales pitch" sections (slot machine, forge/blade, balance) only for archetypes that were actually selected. This shrinks the prompt by roughly a third and removes examples the model is not supposed to use.
- Add a name-diversity rule with teeth: a post-pass that rejects any card name used in the user's last 12 forges or in the global top-50 name list, and asks for a rename (one cheap call, names only).

**Fix E. Split "design" from "encode" for cards, and warm up the temperatures (ollama_mix.py, pipeline.py). Two days.**
- Today one cold call both invents the card and writes strict JSON. Split it: a hot design call (temperature 0.8, prose, 2 to 3 sentences per card, batched 8 cards per call so it is cheap) followed by the existing cold encode call that turns one design into schema-valid JSON. Divergence happens where it is allowed to, and the validator still gates the encoding.
- Raise `structure` to 0.6. Keep `cards` (now encode) at 0.3.
- Route the two decision calls (map/compose and blueprint) to a stronger model on the token path. At Sonnet 5 rates ($2 in / $10 out per million) two calls of roughly 15K input and 3K output cost about $0.12 per forge; with prompt caching on the shared vocabulary prefix it is under $0.05. That is the highest-leverage place to spend, because those two calls make every decision the 33 card calls then execute. Keep glm-5.2 for cards.

**Fix F. Structural quotas (optional, after measuring A to E). One day.**
- Let the three strategies be chosen from a set of six (aggro, control, combo, tempo, attrition, ramp) rather than fixed to three.
- Reduce mandatory bridges from 4 to 3.

### 2.3 The benchmark: how we know it worked

Add `btsgen-bench` (CLI only, no web wiring):
- A fixed set of 12 concept sentences, chosen to span tone and mechanics (already have several in `generation/scratch/triad_run_*`).
- Forge all 12 on the token path, then compute from `census.py`:

| Metric | Today (from ledger and scratch) | Target |
|---|---|---|
| Distinct archetypes used across 12 forges | roughly 15 of 34 | >= 22 |
| Any archetype in more than 4 of 12 classes | yes (3 of them) | none |
| Share of cards with the `{damage, apply_status}` skeleton | 27% | <= 15% |
| Single status as share of all `apply_status` uses | poison 59% | no status above 25% |
| Card names repeated verbatim across classes (excluding Strike/Defend) | yes | zero |
| First-word name collisions across classes (top word count) | "Held" 5 | no word above 2 |
| Coverage-pass injections per class | 1 to 5 | <= 1 average, and never the same mechanic in more than 3 of 12 |
| Validator pass rate on first attempt | current baseline (record it) | not more than 5 points lower |

Run it once before touching anything to lock the baseline, then after each fix. Cost per run is cents on glm-5.2. Gate: harness v2 becomes the default only when every target is met and a blind side-by-side of three v1 and three v2 classes reads as more distinct to you.

---

## Part 3. Pricing: free with your own key, one free token a day otherwise, $1 a token

### 3.1 The rules, stated precisely

| Who | Forging cost | Notes |
|---|---|---|
| Signed-in user who brings a key or connects OpenRouter | Free, unlimited | Their provider bills them. Site still applies queue admission and a per-user concurrency cap of 1. |
| Signed-in user on the hosted models | 1 token per forge | 1 free token per UTC day, whether or not they hold paid tokens. Paid tokens never expire. Free token is consumed before paid tokens. |
| Anyone | Buy tokens | $1 each. Packs: 10 for $8. Recommended additional packs: 3 for $3 (minimum checkout) and 25 for $18. |
| Existing accounts | Keep current balance | Today's `INITIAL_TOKENS = 5` starter grant continues for new accounts (your call; it is a good onboarding hook). |
| Unlimited allowlist (`BTSWEB_UNLIMITED_EMAILS`) | Free | Unchanged. |

Two decisions worth making explicitly:
- **Daily token semantics.** The current rule (`models.grant_daily_token`) only tops up when the balance is zero. Under paid tokens that is wrong: a user holding 9 purchased tokens would never receive the free daily one, which reads as punishment for paying. The fix is to track the free token separately (see 3.3).
- **The $1 single purchase.** Stripe takes $0.30 + 2.9%, so a $1 checkout nets $0.67. Either accept that as the price of simplicity, or set a $3 minimum checkout (3 tokens for $3) and keep "$1 per token" as the headline. The plan assumes the $3 minimum; delete the 3-pack if you prefer true singles.

### 3.2 "Connect your account": what is actually possible

As of September 2026:
- **Anthropic** prohibits using consumer OAuth tokens (Free, Pro, Max) in any third-party product; enforcement has been active since April 2026. Third-party apps must use API keys.
- **OpenAI** "Sign in with ChatGPT" is an identity flow only; it does not let a third-party app bill the user's ChatGPT plan.
- **Google** has no third-party flow that spends a consumer's Gemini quota.
- **OpenRouter** has a documented OAuth PKCE flow that mints a user-controlled API key and redirects back to the app. The user funds OpenRouter credits and can reach Anthropic, OpenAI, Google, and open models through one key.

So the product is: a **"Connect with OpenRouter"** button (one click, no key copying) plus the existing 9-provider paste-your-key BYOK. Do the PKCE code exchange in the browser and keep the resulting key in `localStorage` exactly like today's BYOK keys, so the "keys are never stored server-side" promise in the privacy policy stays true. The site only needs a callback route that serves the SPA; no server-side token storage, no new table.

Marketing copy should say "bring your own key or connect OpenRouter" and not promise Anthropic or OpenAI account linking.

### 3.3 Implementation

**Data model (`web/models.py`, `web/db.py`).** No Alembic exists; every new column needs a hand-written `_ensure_*` ALTER or prod will not get it.
- Add `users.free_token_day VARCHAR(10)`: the UTC day the free token was last spent (not granted). A forge in token mode first checks `free_token_day != today` and, if so, uses the free token and stamps the day; otherwise decrements `token_balance` (paid). Drop the "only when empty" branch. Keep `last_free_token_day` for the migration window, then remove.
- Add `forge_usage` table: `user_id`, `class_id`, `mode`, `model`, `role`, `input_tokens`, `output_tokens`, `cached_tokens`, `cost_cents_est`, `created_at`. Populated from btsgen's `on_usage` callback via `build_ollama_mix(on_usage=...)` in `web/forge.py`. This is the prerequisite for knowing your margin; today marginal cost is near zero while the Ollama flat plan holds and unknown on OpenRouter overflow.

**Billing (`web/billing.py`).** Restore the pack shape from private-repo commit `d6f5592`, simplified:
- Define packs in code: `PACKS = [("3", 3, 300), ("10", 10, 800), ("25", 25, 1800)]` and use `price_data` (as the donation code does) rather than Stripe Price objects, so test and live modes need no separate ids. Re-pricing is a deploy, which is fine.
- `POST /api/checkout {pack}` creates a Checkout Session with `mode="payment"`, no `submit_type="donate"`, product name "Forge tokens x10", `metadata.tokens` frozen at checkout time (the existing idempotent `_credit_purchase` path stays untouched).
- Enable Stripe Tax: `automatic_tax={"enabled": True}` on the session and register in the Stripe dashboard. You are now selling a digital good; Stripe Tax handles the registration thresholds and rates.
- Keep the donate endpoint if you like, but stop granting thank-you tokens for donations (or the Workshop compliance framing gets muddy). Recommendation: remove donations; tokens are the product.
- Refund policy: keep the 14-day window for unspent tokens; `charge.refunded` should now claw back unspent tokens (`max(0, balance - refunded_tokens)`), since these are purchases, not gifts.

**Access control and abuse (`web/app.py`).**
- Per-IP daily cap on token-mode forges (say 5) using the existing `HostedLimiter`, whose `check(ip)` currently ignores its argument. Free daily tokens on Google-account farms are the obvious abuse; an IP cap is the cheap first line.
- Per-user concurrency cap of 1 across all modes (an authenticated BYOK user pointed at a slow endpoint can hold 3 of the 3 forge slots today).
- Queue priority: paid and daily-token forges ahead of BYOK forges in the FIFO. BYOK is free to you but occupies the same three slots; paying users should not wait behind it. Two queues with token-first dequeue is a 30-line change to `_forge_enqueue`.
- Reject `mode=hosted` outright (it is retired from the UI and reachable by hand-crafted POST on your Anthropic key).

**BYOK "Connect with OpenRouter" (`web/static/app.js`, `web/static/index.html`, `web/app.py`).**
- Button next to the provider dropdown. Generates `code_verifier`, stores it in `sessionStorage`, redirects to `https://openrouter.ai/auth?callback_url=https://blankthespire.com/app&code_challenge=...&code_challenge_method=S256`.
- On return with `?code=`, the browser POSTs to `https://openrouter.ai/api/v1/auth/keys` with the verifier, receives the key, stores it in `localStorage` under the existing BYOK slot with provider `openrouter`, and clears the query string.
- Register the callback URL in the OpenRouter app settings. Add OpenRouter's domain to the CSP `connect-src` once security headers exist (Part 4).

**Copy and legal, all in one change so nothing contradicts anything.**
- `web/static/index.html:132-139`: replace "forging never costs money" and the donation paragraph with the three-tier rules.
- `web/static/app.js:44-49`: the header chip currently leaks backend model names ("gemma + glm-5.2"). Say "our hosted models."
- `web/static/terms.html:33-51`: tokens are prepaid credits for generation compute on the site; they are not a purchase of mod content; the mod is free and open source; refunds for unspent tokens within 14 days; no cash value, non-transferable.
- `web/static/privacy.html`: add OpenRouter as a processor when the user chooses to connect it; restate that keys stay in the browser.
- Add a `/pricing` route or a pricing section on the landing page.
- `INSTALL.md:68` and `README.md` "Play it" section: update the pricing sentence and the BYOK label names (the old "Anthropic (your key)" and "My API key" labels no longer exist).
- `workshop/DESCRIPTION.bbcode` line 17: keep it accurate but price-free ("Forging is free with your own API key, and every account gets a daily free forge on our hosted models"). No prices, no purchase links on the Workshop page.
- Put "Unofficial fan project, not affiliated with or endorsed by Mega Crit" in the shared site footer (landing, app, download). Today it appears only in the terms page and the Workshop description.
- Keep Mega Crit's written permission for this pricing model on file (a dated message or email), since their published content policy allows donations only. Phrase everything as paying for generation compute, never for mod content.

**Tests (`web/tests/`, new).** Flask test client against SQLite; no network.
- Daily token: first forge of the day is free even with paid balance; second decrements paid; UTC rollover.
- Reserve/refund: forge error refunds the right kind of token (free day-stamp reverted vs paid balance restored).
- Webhook idempotency: same session id delivered twice credits once; `charge.refunded` claws back at most the unspent amount.
- Pack math: each pack's `metadata.tokens` and `unit_amount` match the table.
- BYOK never persists: after a BYOK forge, no table contains the key string.
- Admission: per-user concurrency 1; token forges dequeue ahead of BYOK.
- SSRF guard: private and link-local `base_url` rejected on both the staged and one-shot paths.

### 3.4 Margin check

At $0.80 per token (the 10-pack) and roughly $0.72 net after Stripe fees, the hosted forge must cost well under that. Current estimate on OpenRouter overflow: about 35 calls with a 15K-token cached prefix and 1K to 3K output each, at glm-5.2's $0.49 in / $1.56 out per million and $0.09 cache read, lands in the $0.05 to $0.15 range per forge, plus art. On the Ollama flat plan the marginal cost is zero until the plan's credit ceiling. Adding Sonnet 5 for the two decision calls (Fix E) adds $0.05 to $0.12. Margin holds either way, but the `forge_usage` table is what turns that into a fact.

---

## Part 4. Production hardening before launch

Status of the July 12 plan's P0/P1 items, from the current code:

| Item | Status |
|---|---|
| dev-login fail-closed | Done (`web/auth.py:86-89`) |
| Insecure default secret key | Done, boot refuses (`web/app.py:50-56`) |
| SSRF guard on BYOK base_url | Done for the staged path; **missing on the one-shot path** (`web/forge.py:110-122` never calls `_guard_outbound_url`) |
| Hosted-mode Opus burn | Allowlist is fail-closed in code (`app.py:180-182`), but the deploy doc says the opposite; reject `mode=hosted` and fix the doc |
| STS2 card DB removed, LICENSE, README rewrite, fresh history | Done |
| `/api/deck/<id>` enumeration | **Open**; comment at `app.py:681-683` defers it "before launch" |
| Security headers, CSP, body limit, CSRF, POST-only logout | **Open** |
| Per-user forge concurrency | **Open** (covered in Part 3) |
| Feedback free text into prompts | Wired live; add a length cap and a rate limit, and keep it as anti-examples only |

Must-do before the pricing launch (about two days):
1. Guard the one-shot BYOK path; make both paths share one factory so the guard cannot be skipped.
2. Switch shared deck links to an unguessable slug (`classes.share_slug`, 16 random chars, add via `_ensure_class_columns`); keep numeric ids internal.
3. Security headers via an `after_request` hook (CSP with the CDN/OpenRouter allowances you need, `X-Frame-Options`, `nosniff`), `MAX_CONTENT_LENGTH` of 256 KB, `/logout` POST-only, a CSRF header check on mutating JSON routes. Keys live in `localStorage`, so DOM XSS is key theft; CSP is the mitigation.
4. Commit `/opt/btsweb/deploy.sh` into `web/deploy/` and make it the only deploy path (pull, pip install if requirements changed, run web tests, restart, curl `/healthz`).
5. Add `/healthz` (DB ping plus queue depth) and point an external uptime monitor at it. Add Sentry or equivalent for the Flask app; forge failures currently vanish into journald.
6. Backups: DO Managed MySQL has automatic backups; verify retention in the dashboard. `web/static/forged/`, `web/card_feedback.jsonl`, and `web/captured_gaps.jsonl` are unbacked; add a nightly rclone or `s3cmd` sync to DO Spaces from the prune timer's sibling unit.
7. CI: one GitHub Actions workflow running `generation` pytest and the new `web/tests` on push. Neither needs a key or the game.
8. Fix `pyproject.toml`'s `web` extra to include `stripe` and `gunicorn`, matching `web/requirements.txt`.
9. Commit `workshop/` (except the gitignored content dir) and the `.gitignore` change.

Known scaling ceiling, not a launch blocker: the forge queue, the daily cap, and the interactive-choice registry are process-local, so gunicorn stays at 1 worker. When demand exceeds 3 concurrent forges, the path is to move admission state into MySQL (or Redis) and run forges in a worker process; budget a week for that when the ledger shows queue waits.

---

## Part 5. Steam Workshop publication

The listing is drafted but has never been uploaded. Complete `workshop/README.md`'s checklist in this order:
1. Rewrite `DESCRIPTION.bbcode` line 17 per Part 3 (accurate, no prices). Rebuild `workshop.json` with `build_workspace.ps1`.
2. Create `workspace/image.png` under 1 MB, and two or three `previews/` screenshots (forge site, class select, a forged hand).
3. Fill `tags` from the STS2 Workshop sidebar (not "Tools & APIs").
4. Run `ModUploader.exe` once to confirm the content layout the uploader expects; fix the script if nested.
5. Upload private, accept the Workshop legal agreement, commit `mod_id.txt`.
6. Smoke test as a subscriber: remove manual `mods\BlankTheSpire` and `mods\BaseLib`, subscribe, confirm BaseLib auto-installs, import a code, play a hand.
7. Flip to public only after the site's pricing and terms are live, so the first wave of subscribers sees consistent copy.
8. Update `README.md` and `INSTALL.md` so Workshop is the headline install path and the zip is the fallback; make `download.html` read the version from the manifest instead of a hardcoded string.

---

## Part 6. Sequenced rollout

**Phase 0: measure and protect (3 to 4 days).**
- Wire `on_usage` into `forge_usage`. Record the harness baseline with `btsgen-bench` on the 12 fixed concepts.
- Add `web/tests` for the money paths as they exist today, so the pricing change starts from green.
- Hardening items 1, 4, 5, 7, 8, 9 from Part 4.
- Gate: CI green, baseline numbers recorded in `docs/plans/HARNESS_BENCH.md`.

**Phase 1: harness v2 (5 to 7 days).**
- Fixes A through E behind `BTS_HARNESS_V2`. Re-run the bench after each fix; keep only fixes that move a metric.
- Deploy with the flag on for `BTSWEB_UNLIMITED_EMAILS` accounts first, then for everyone once the bench targets hold and you prefer the blind side-by-side.
- Rollback: unset the flag; no data migration involved.

**Phase 2: pricing (4 to 5 days).**
- Schema, billing, admission, copy, terms, OpenRouter connect, tests, Stripe Tax registration.
- Deploy with `STRIPE_SECRET_KEY` on the test key first and buy a pack end to end; then flip to live and buy one real 3-pack yourself.
- Existing users: announce the change on the app page for a week ("tokens are now purchasable; daily free token continues; your balance is unchanged").
- Rollback: the pack endpoints are additive; the old donate code can stay dormant behind a flag for one release.

**Phase 3: launch (2 to 3 days).**
- Workshop public, README/INSTALL updated, hardening items 2, 3, 6.
- Launch-day checklist: `/healthz` green, uptime monitor armed, Sentry receiving, one real purchase verified, one BYOK forge and one token forge completed from a fresh Google account, `journalctl -u btsweb -f` open, Ollama plan credits checked, OpenRouter failover key funded.

**Phase 4: first month after launch.**
- Watch `forge_usage` for cost per forge and the bench metrics on real traffic (a weekly census over the last 50 forges).
- Watch queue waits; if median wait exceeds a minute at peak, start the worker-process refactor.
- Turn player card ratings into the exemplar pool (Fix A gets better as `card_feedback.jsonl` grows; it has 2 lines today).

---

## Appendix: file map for the work above

| Workstream | Files |
|---|---|
| Harness A | `generation/btsgen/contract.py`, `generation/btsgen/validator.py:1028-1033` |
| Harness B | `generation/btsgen/coverage.py`, `generation/btsgen/class_forge.py` (blueprint nomination field) |
| Harness C | `generation/btsgen/frontend/builder.py`, `frontend/stage_map.py`, `frontend/catalog.py`, `ledger.py`, `data/archetypes.json` |
| Harness D | `generation/btsgen/class_forge.py:219-660` |
| Harness E | `generation/btsgen/ollama_mix.py`, `pipeline.py`, `generator.py` |
| Bench | new `generation/btsgen/cli_bench.py`, `census.py` |
| Pricing | `web/models.py`, `web/db.py`, `web/billing.py`, `web/app.py`, `web/forge.py`, `web/static/{index.html,app.js,terms.html,privacy.html,landing.html}`, `INSTALL.md`, `README.md` |
| Hardening | `web/forge.py`, `web/app.py`, `web/deploy/`, `.github/workflows/ci.yml`, `generation/pyproject.toml` |
| Workshop | `workshop/DESCRIPTION.bbcode`, `workshop/workspace/`, `web/static/download.html` |
