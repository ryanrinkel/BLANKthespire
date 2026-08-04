# Contributing to BLANK the spire

Thanks for your interest! This is a hobby project — an unofficial *Slay the Spire 2* mod plus the generator and website that power it. Contributions of all sizes are welcome.

## Ground rules

- **You must own Slay the Spire 2** to build or test the mod itself; it builds against the game's assemblies (discovered from your Steam install).
- No Mega Crit game code, binaries, or copyrighted game data in PRs. The mod uses the game's public modding surface + Harmony; it does not redistribute game content. Don't commit decompiled game source or extracted card databases.
- Be kind. No plagiarized or offensive content (also required by Mega Crit's mod content policy).

## What can be worked on without the game

The **generator** (`generation/btsgen`) and its tests run with no API key and no game install:

```bash
cd generation
uv sync            # or: python -m venv .venv && .venv/bin/pip install -e .
uv run pytest -q
```

Good first contributions: generator vocabulary/validation fixes, website UX, docs, new tests. The card/relic/status vocabulary the generator targets lives in `mod/contract/`.

## Building the mod

```bash
cd mod
dotnet build
```
Requires the .NET 9 SDK and a Steam install of STS2 (see `mod/Sts2PathDiscovery.props` — no paths are hardcoded to a specific machine; override via `local.props` if auto-discovery misses).

## The website

```bash
cd web
pip install -r requirements.txt
cp .env.example .env   # your own secrets — never commit a real .env
python app.py
```

## Pull requests

- Keep PRs focused; describe what and why.
- Run the generator tests before submitting.
- For mod behavior changes, describe how you verified in-game (attach `godot.log` snippets for bug reports).

## Reporting bugs

Open a GitHub Issue using the bug-report template. For mod crashes/hangs, include your `godot.log` and the class import code that triggered it.
