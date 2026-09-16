# Forge a Class — the BLANK the spire website

A small Flask app that reuses the `btsgen` generator to forge a whole **BLANK the spire** class from a
sentence, hands back a `BTSC` import code, and saves it to a per-user library. Sign in with Google, Discord,
GitHub or an emailed magic link; classes in MySQL (prod) / SQLite (dev). **BYOK API keys are never persisted** — only generated content is.

This is the app behind [blankthespire.com](https://blankthespire.com).

## Run locally (no OAuth, no MySQL)

```bash
cd web
# editable btsgen + web deps already installed via:  uv sync --extra web   (run in ../generation)
BTSWEB_DEV_AUTH=1 uv run --project ../generation python app.py
# open http://localhost:5000  → "Dev sign-in"  → pick "Offline demo"  → Forge
```

- **Offline demo** mode needs no API key (placeholder cards, exercises the whole pipeline + code + library).
- **Use a token** forges on the server's hosted Ollama mix behind a token economy: every account gets one
  free token per UTC day (tracked separately from the balance, so donors never lose it) plus a few starter
  tokens. Nothing is sold: optional Stripe donations grant a thank-you token per whole dollar (`billing.py`).
  Free-token forges are capped per IP per day; one forge per account at a time; token forges dequeue before BYOK.
- **BYOK** posts your `base_url`/`api_key`/`model` once; the key lives only in your browser's localStorage.
  An SSRF guard rejects private/loopback endpoints — to point BYOK at a localhost Ollama in local dev, set
  `BTSWEB_ALLOW_PRIVATE_URLS=1` (never in prod).

## Files

| file | role |
|------|------|
| `app.py` | Flask routes: `POST /api/forge-class` (SSE), `GET/PATCH/DELETE /api/classes[/:id]`, static |
| `forge.py` | wraps `btsgen.class_forge.forge_class` + `bts1.encode_class` (hosted / BYOK / fake) |
| `auth.py` | sign-in: OAuth (Authlib: Google / Discord / GitHub) + email magic links (Resend; 15-min single-use token, GET renders / POST consumes) + `/dev-login` bypass (env-gated, fails closed in prod) |
| `billing.py` | Stripe pay-what-you-want donations (Checkout + webhook, thank-you tokens, refund clawback) |
| `db.py`, `models.py` | SQLAlchemy engine + `users` / `classes` / `cards` / `purchases` / `forge_usage` |
| `static/` | split-flap landing page (`/`), sign-in chooser (`/login`) + single-page Forge app (`/app`) |
| `deploy/` | gunicorn + nginx + systemd units, `deploy.sh` (the only deploy path), `backup.sh` |
| `tests/` | Flask-test-client suite (SQLite, no network): `PYTHONPATH=generation python -m pytest web/tests` |

## Deploy

Production runs on a plain Linux VM (DigitalOcean droplet) behind nginx + gunicorn + systemd — the
full walkthrough, including TLS and the environment secrets, is in
**[DEPLOY-DIGITALOCEAN.md](DEPLOY-DIGITALOCEAN.md)**. Copy `.env.example` to `.env` and fill in your
own values; tables auto-create on first boot (`init_db`).
