# BLANK the spire

> Forge a custom *Slay the Spire 2* character class from a single sentence.

**BLANK the spire** is an unofficial mod for [Slay the Spire 2](https://store.steampowered.com/app/2868840/) that adds AI-forged playable classes — each with its own cards, relic, mechanics, and identity — generated from a plain-English concept. Describe a class in a sentence at **[blankthespire.com](https://blankthespire.com)**, and the forge turns it into a real, playable STS2 character you import into the game.

> ⚠️ Unofficial fan project. Not affiliated with or endorsed by Mega Crit. Requires owning Slay the Spire 2. See [License & game IP](#license).

<!-- <<PLACEHOLDER: add 2-3 screenshots here — a forged class in-game, the forge website, a generated card. Put images in docs/img/ and reference them.>> -->

---

## What's in this repo

This project has three parts:

| Directory | What it is |
|-----------|-----------|
| **`mod/`** | The Slay the Spire 2 mod itself — a C# assembly (built with the community modding SDK + [BaseLib-StS2](https://github.com/Alchyr/BaseLib-StS2) + Harmony) that adds a data-driven runtime so a forged class defined as pure data becomes a playable character. The card/relic/status "vocabulary" the generator is allowed to use lives in `mod/contract/`. |
| **`generation/`** | `btsgen`, the Python LLM harness that turns a concept sentence into a validated class blueprint (cards, relic, starter deck) that conforms to the mod's contract. Multi-stage creative pipeline with schema validation so generated content is guaranteed playable. |
| **`web/`** | The Flask website behind [blankthespire.com](https://blankthespire.com): sign in, forge a class (hosted, or bring your own API key), share results at `/deck/<id>`, and download the mod. |

## Play it (no building required)

The fastest path is the live site + the released mod:

1. Own **Slay the Spire 2** on Steam.
2. Install the mod — via the **Steam Workshop** listing, or grab the latest release zip and follow **[INSTALL.md](INSTALL.md)** (Windows + Linux/Proton instructions included).
3. Forge a class at **[blankthespire.com](https://blankthespire.com)** and import its code in-game.

Three starter class codes to try are listed in [INSTALL.md](INSTALL.md).

## Build it yourself

**Prerequisites**
- A legitimate copy of **Slay the Spire 2** installed via Steam (the mod builds against the game's assemblies, discovered automatically from your Steam install — see `mod/Sts2PathDiscovery.props`).
- **.NET 9 SDK** (and the `Godot.NET.Sdk` referenced by the csproj).
- **Python 3.10+** and [uv](https://github.com/astral-sh/uv) (or plain `venv`/`pip`) for the generator and website.

**The mod**
```bash
cd mod
dotnet build            # outputs BlankTheSpire.{dll,json,pck}; package with mod/tools/package_release.ps1
```

**The generator**
```bash
cd generation
uv sync
uv run pytest           # test suite runs without any API key
```
The generator reads the card/relic/status contract from `mod/contract/`. Provide an LLM key via `generation/.env` (see `.env.example`) to actually forge.

**The website**
```bash
cd web
pip install -r requirements.txt
cp .env.example .env    # fill in your own secrets
python app.py
```
See `web/DEPLOY-DIGITALOCEAN.md` for the production (gunicorn + nginx) setup.

## How a forge works (high level)

A concept sentence → a staged LLM pipeline (`generation/btsgen`) that brainstorms an identity, maps it onto the mechanics the mod can actually execute (the `mod/contract/` vocabulary), and emits a schema-validated blueprint → the site hands you an import code → the mod's data-driven runtime instantiates the class in-game. Because generation is constrained to the mod's real vocabulary and validated against a JSON schema, forged classes are guaranteed to load and play.

## Contributing

Issues and PRs welcome — see **[CONTRIBUTING.md](CONTRIBUTING.md)**. The generator's tests run without any API key or the game installed, so most contributions can be validated in CI.

## License

Code and original content in this repo are **MIT** licensed (see [LICENSE](LICENSE)). **Slay the Spire 2**, its assets, names, characters, and card content are © **Mega Crit Games**; this is an unofficial fan mod and includes no game code, binaries, or copyrighted game data. You need to own the game to use it.

*This project began life as a data-driven prototype in Godot before becoming an STS2 mod; some contract schemas carry that lineage.*
