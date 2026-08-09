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
GOOGLE_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=...
ANTHROPIC_API_KEY=sk-ant-...        # powers the hosted "try it" path
BTSWEB_HOSTED_ALLOWLIST=you@example.com   # set to your own admin email; comma-separated. EMPTY = open to any signed-in user.
# --- Stripe donations (pay-what-you-want; key absent = donate UI hidden, daily free token still works) ---
STRIPE_SECRET_KEY=sk_live_...       # sk_test_... while testing; test/live are separate Stripe universes
STRIPE_WEBHOOK_SECRET=whsec_...     # from the DASHBOARD webhook endpoint (https://blankthespire.com/webhook/stripe,
                                    # events: checkout.session.completed + charge.refunded) — NOT the CLI's secret
# BTSWEB_DONATION_PRESETS=300,500,1000   # optional: suggested donation amounts in cents (this is the default)
# (BTSWEB_STRIPE_PACKS is retired — donations use ad-hoc price_data, no Stripe Price objects needed.)
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

## 7. Google OAuth

In Google Cloud Console → Credentials → your OAuth client → **Authorized redirect URIs**, add:
`https://YOURDOMAIN.com/auth/callback`. (Already done for localhost during dev; add the prod one too.)

## 8. Verify

1. Open `https://YOURDOMAIN.com` → **Sign in with Google** (real OAuth, not dev-login).
2. Forge with **Try it free** (hosted key) and with **BYOK** (your own key) — progress should stream live.
3. Confirm a second Google account sees only its own **My Classes**.
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
- "Try it free" is unlimited per user; the only hosted-key guard is a global daily kill-switch
  (`BTSWEB_HOSTED_DAILY_CAP`, default 1000; `0` disables it) plus the optional invite-only allowlist
  (`BTSWEB_HOSTED_ALLOWLIST`). With a single gunicorn process group the counter is process-local, which is
  fine here.
