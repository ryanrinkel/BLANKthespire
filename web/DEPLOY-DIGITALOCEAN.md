# Deploy "Forge a Class" to DigitalOcean (Droplet + gunicorn/nginx + Managed MySQL)

Chosen setup: a small **Droplet** running the Flask app under **gunicorn** behind **nginx**, with a **DO
Managed MySQL** database. The Droplet keeps the multi-minute SSE forge working with no request-timeout
refactor (App Platform would need that — see the plan's Phase E notes).

Paths below assume the repo lives at `/opt/btsweb` (so the app is `/opt/btsweb/web`). Adjust to taste.

## 1. Provision

- **Droplet:** Ubuntu LTS, the $6–12/mo basic tier is plenty for early traffic. Add your SSH key.
- **Managed MySQL:** Databases → Create → MySQL, same region as the Droplet. When it's up:
  - Add the Droplet to the DB's **Trusted Sources** (firewall) so only it can connect.
  - Create a database (e.g. `btsweb`) and note the **connection string** and **port (25060)**.
  - Download the **CA certificate** (`ca-certificate.crt`) — DO Managed MySQL requires TLS.

> **Sizing:** the `s-1vcpu-1gb-35gb-intel` (1 vCPU / 1 GB) Droplet is enough — MySQL is managed (off-box) and
> the forge is I/O-bound (generation happens on the LLM provider). Keep gunicorn at **1 worker** (the default
> in `deploy/gunicorn.conf.py`) and add swap (below). Bump to 2 workers only on a ≥2 GB box.

## 2. System packages + swap

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip nginx git
sudo adduser --system --group btsweb        # service account
sudo mkdir -p /opt/btsweb && sudo chown btsweb:btsweb /opt/btsweb

# 2 GB swap — insurance against OOM on a 1 GB box (pip installs, traffic spikes).
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 3. Code + virtualenv

```bash
sudo -u btsweb git clone <your-repo-url> /opt/btsweb
cd /opt/btsweb
sudo -u btsweb python3 -m venv .venv
sudo -u btsweb .venv/bin/pip install -r web/requirements.txt
sudo -u btsweb .venv/bin/pip install -e ./generation  # EDITABLE install of the btsgen package
```

> **Why `-e` (editable):** btsgen locates the mod contract (`mod/contract/`) relative to its own file. A
> plain `pip install ./generation` COPIES btsgen into the venv's site-packages, so its repo-root guess
> lands *inside* the venv (`…/.venv/lib/pythonX/mod/contract` → `FileNotFoundError: VOCABULARY.md`).
> Editable keeps btsgen rooted at `/opt/btsweb/generation`, so it resolves `/opt/btsweb/mod/contract`
> correctly — and future `git pull`s of generation code take effect without re-installing. (The app also
> hands btsgen the real repo root via `BTS_REPO_ROOT`, so a non-editable install works too; `-e` is just
> the cleaner default.)

Put the CA cert somewhere readable, e.g. `/opt/btsweb/web/do-mysql-ca.crt`.

## 4. Environment (`/opt/btsweb/web/.env`)

```ini
BTSWEB_SECRET_KEY=<long-random-string>
BTSWEB_BEHIND_PROXY=1
BTSWEB_DATABASE_URL=mysql+pymysql://USER:PASSWORD@DBHOST:25060/btsweb
BTSWEB_DB_SSL_CA=/opt/btsweb/web/do-mysql-ca.crt
# --- sign-in providers: set any subset; each provider's button appears only when its pair is present ---
GOOGLE_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=...
DISCORD_CLIENT_ID=...                # Discord Developer Portal → your application → OAuth2
DISCORD_CLIENT_SECRET=...
GITHUB_CLIENT_ID=...                 # the PROD GitHub OAuth App (the local one is a second app — see §7)
GITHUB_CLIENT_SECRET=...
RESEND_API_KEY=re_...                # email magic links; BOTH mail vars must be set or email sign-in is off
BTSWEB_MAIL_FROM=sign-in@blankthespire.com   # must be a Resend-verified domain (SPF+DKIM — see §7)
OLLAMA_API_KEY=...                  # powers the "Use a token" path (our hosted Ollama mix; see btsgen/ollama_mix.py)
# (ANTHROPIC_API_KEY / BTSWEB_HOSTED_ALLOWLIST are retired: `mode=hosted` is rejected outright — the public
#  paths are the token forge and bring-your-own-key.)
BTSWEB_UNLIMITED_EMAILS=you@example.com   # accounts that forge on the token path without spending tokens
#                                     # (break-glass only: unlimited is also grantable per account from the
#                                     #  operator panel, and this list is what no DB write can take away)
BTSWEB_ADMIN_EMAILS=you@example.com   # REQUIRED for the Account tab's OPERATOR CARDS: forge stats AND the
#                                     # user panel that edits token balances / grants unlimited. Unset ⇒ both
#                                     # cards are off for everyone (it does NOT fall back to the unlimited
#                                     # list any more — a tester on that list must not inherit the ability to
#                                     # edit balances). Admin is env-only by design: no route can grant it,
#                                     # so the panel can never widen who reaches the panel.
# BTSWEB_WORKSHOP_URL=https://steamcommunity.com/sharedfiles/filedetails/?id=...   # the mod's Workshop item; the
#                                     # /download page links the STS2 Workshop hub until this is set
# BTSWEB_MODEL_PRICES='{"glm-5.2": [in, out, cached]}'  # $/1M tokens for the hosted mix — feeds the dashboard's spend estimate
BTSWEB_TOKEN_DAILY_CAP=1000         # global kill-switch on all token-path forges per day; 0 = off
# --- Stripe donations (key absent = donate UI hidden; BYOK still works; hosted forges need tokens) ---
STRIPE_SECRET_KEY=sk_live_...       # sk_test_... while testing; test/live are separate Stripe universes
STRIPE_WEBHOOK_SECRET=whsec_...     # from the DASHBOARD webhook endpoint (https://blankthespire.com/webhook/stripe,
                                    # events: checkout.session.completed + charge.refunded) — NOT the CLI's secret
# STRIPE_FEE_PCT=2.9                # Stripe's card fee, passed to the donor as a "Card processing fee"
# STRIPE_FEE_FIXED_CENTS=30         # line item (defaults shown)
# SENTRY_DSN=https://...             # optional: error reporting (pip install sentry-sdk[flask])
# Do NOT set BTSWEB_DEV_AUTH in prod.
```

`chmod 600 web/.env` and `chown btsweb:btsweb web/.env`. Tables auto-create on first boot (`init_db`).
After editing `.env`, `sudo systemctl restart btsweb` to pick up new vars.

### Release zip (download page)

The `/download` page serves `web/static/releases/BlankTheSpire-v<N>.zip`, which is **gitignored** (not in
the repo). Build it locally with `mod\tools\package_release.ps1` and copy it to the droplet on each release:

```bash
scp release/BlankTheSpire-vX.Y.Z.zip your-droplet:/opt/btsweb/web/static/releases/
```

## 5. gunicorn under systemd

```bash
sudo cp /opt/btsweb/web/deploy/btsweb.service /etc/systemd/system/btsweb.service
sudo systemctl daemon-reload && sudo systemctl enable --now btsweb
sudo systemctl status btsweb        # should be active; logs: journalctl -u btsweb -f
```

### Forged-art rotation (disk safety valve)

Generated art (`web/static/forged/`, ~3MB/class) grows forever. Install the daily prune timer —
it no-ops until free disk drops under 5GB, then deletes the oldest idle classes' splash/sprite
(clearing their DB hashes; the game shows its "?" placeholder for late imports of those codes):

```bash
sudo cp /opt/btsweb/web/deploy/btsweb-prune.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now btsweb-prune.timer
# preview what a low-disk day would do:  cd /opt/btsweb/web &&
#   sudo -u btsweb ../.venv/bin/python tools/prune_forged_art.py --dry-run --target-free-gb 999
```

## 6. nginx + TLS

```bash
sudo cp /opt/btsweb/web/deploy/nginx-btsweb.conf /etc/nginx/sites-available/btsweb
# edit it: set server_name to your domain
sudo ln -s /etc/nginx/sites-available/btsweb /etc/nginx/sites-enabled/btsweb
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
# point your domain's A record at the droplet IP, then:
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d YOURDOMAIN.com      # adds https; OAuth needs https
```

## 7. Sign-in providers

Each provider is optional: the `/login` chooser renders a button only for providers whose
`<PROVIDER>_CLIENT_ID` **and** `_SECRET` are both set. The callback URL is always
`/auth/<provider>/callback`.

**Discord** — [Developer Portal](https://discord.com/developers/applications) → New Application → OAuth2 →
Redirects. Add **both**:

```
https://YOURDOMAIN.com/auth/discord/callback
http://localhost:5000/auth/discord/callback
```

Scopes: `identify email`. Copy the **Client ID** and **Client Secret** into `.env`.

**GitHub** — Settings → Developer settings → **OAuth Apps**. A GitHub OAuth App allows **exactly one**
callback URL, so create **two apps**:

| app | Authorization callback URL | where its id/secret go |
|-----|---------------------------|------------------------|
| BLANK the spire | `https://YOURDOMAIN.com/auth/github/callback` | the droplet's `/opt/btsweb/web/.env` |
| BLANK the spire (local) | `http://localhost:5000/auth/github/callback` | your local `web/.env` |

Scope `read:user user:email` is requested by the app itself (nothing to configure). `user:email` is what
makes `/user/emails` readable — without a verified address there, the account is created with no email
(it just can't link to another provider or be on `BTSWEB_UNLIMITED_EMAILS`).

**Email (Resend)** — the magic link is ours, not OAuth: no redirect URI, but it needs DNS, which is the
slow part (propagation + Resend's verification can take hours — start it before you need it).

1. Create the account at [resend.com](https://resend.com) → **Domains** → **Add domain** →
   `blankthespire.com`. Resend shows a set of records.
2. At **DigitalOcean → Networking → Domains → blankthespire.com**, add exactly what Resend listed — an SPF
   TXT record and the DKIM records (a CNAME/TXT pair on a `resend._domainkey`-style host) — plus a DMARC
   record of your own:

   | type | hostname | value |
   |------|----------|-------|
   | TXT | `_dmarc` | `v=DMARC1; p=none` |

   `p=none` is monitor-only: it never bounces mail while you are still watching deliverability. Tighten to
   `quarantine` later if you care to. **Without DKIM the links land in spam** — this is not optional.
3. Wait for the domain to read **verified** in Resend (refresh; minutes to hours).
4. Create an API key (**sending access** is enough), put `RESEND_API_KEY` and
   `BTSWEB_MAIL_FROM=sign-in@blankthespire.com` in `.env`, `sudo systemctl restart btsweb`.
5. Test before announcing: request a link from `/login` **to a Gmail address and to an Outlook/Hotmail
   address**, and check the spam folder in both. Outlook SafeLinks will prefetch the URL — that is exactly
   why the GET only renders a Continue button and the POST is what consumes the token.

Note both mail vars count as "a sign-in provider is configured" for the boot guards: with them set, the app
refuses to boot without `BTSWEB_SECRET_KEY`, or with `BTSWEB_DEV_AUTH` on.

**Google** — nothing to do for this release: `/login/google` still sends Google back to the legacy
`https://YOURDOMAIN.com/auth/callback`, the one URI the Cloud Console already lists, so Google sign-in keeps
working through the deploy. To retire the alias later: Cloud Console → Credentials → your OAuth client →
**Authorized redirect URIs** → add `https://YOURDOMAIN.com/auth/google/callback`, then switch the Google
branch in `auth.py`'s `login_provider` to `auth_provider_callback` and drop the `/auth/callback` route.

## 8. Verify

1. Open `https://YOURDOMAIN.com` → **Sign in** → one button per configured provider (real OAuth, not
   dev-login), plus the email form when the two mail vars are set.
2. Forge with **Use a token** (our hosted models) and with **Bring your own key** — progress should stream live.
3. Confirm a second account sees only its own **My Classes**.
4. Copy a class code, import it in-game, restart, play it.

## Notes

- `passenger_wsgi.py` is for cPanel only — unused on DO; ignore or delete it.
- Updating: `git pull`, `pip install -r web/requirements.txt` (if changed), `sudo systemctl restart btsweb`.
  If generation/ was installed non-editable (plain `pip install ./generation`), also re-run the install so
  the new btsgen lands in site-packages; an **editable** (`-e`) install skips that — `git pull` is enough.
- Forge admission: at most `BTSWEB_FORGE_MAX_CONCURRENT` (3) forges run at once; the next
  `BTSWEB_FORGE_MAX_QUEUE` (12) wait in a FIFO line with live queue-position progress in the stream;
  beyond that `/api/forge-class` answers 503 up front (no token spent). Process-local — keep
  gunicorn at 1 worker or the limits silently double and the line splits.
- Token-path guards: there is no free token — accounts start with 0 tokens, and tokens only ever arrive as
  a thank-you for a donation. All token forges are capped by a global daily kill-switch
  (`BTSWEB_TOKEN_DAILY_CAP`, default 1000; `0` disables). One forge per account at a time, across all modes;
  token forges dequeue ahead of BYOK forges. All of it is process-local — keep gunicorn at one worker.
- A forge can never cost a token without delivering a class: every attempt is a `forge_jobs` row settled
  exactly once by the worker thread (not the browser stream), so a closed tab still gets its class saved or
  its token refunded; jobs left running by a restart are refunded at boot; a forge running past
  `BTSWEB_FORGE_MAX_SECONDS` (default 1200) is abandoned and refunded, and if it finishes late the class
  still lands in the library.
- `mode=hosted` (our Anthropic key) is retired and answers 410 — nothing can spend that key any more.
- Deploy with `web/deploy/deploy.sh` (pull, install if requirements changed, run web tests, restart, curl
  `/healthz`). `/healthz` returns 503 when the DB is unreachable — point the uptime monitor at it.
- Nightly backups of the un-versioned server data (forged art, feedback + gap logs): `web/deploy/backup.sh`
  + `btsweb-backup.timer` sync them to a DO Space via rclone. Managed MySQL keeps its own daily backups —
  verify the retention setting in the DO console.
