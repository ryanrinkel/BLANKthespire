# generation/reference

This directory holds **calibration reference data** the forge prompts can optionally embed to teach the LLM the Slay the Spire 2 power/complexity ladder per rarity.

## The data is NOT committed (on purpose)

The actual card data — `sts2_cards.json` and the derived `sts2_rarity_examples.md` digest — is **Slay the Spire 2 game content, © Mega Crit Games**, and is not redistributed in this repository. Both files are `.gitignore`d.

They are sourced from the public community extraction at
[github.com/ptrlrd/spire-codex](https://github.com/ptrlrd/spire-codex) and are used here as a **noncommercial community design reference only**.

## Regenerate locally

Run the distiller to fetch/build the files into this directory:

```bash
cd generation
python reference/distill_sts2.py   # writes reference/sts2_cards.json + sts2_rarity_examples.md locally
```

The forge degrades gracefully if these files are absent — `paths.STS2_EXAMPLES` is optional and prompts simply skip the rarity digest when it isn't present. So you can run the generator without them; they just improve rarity calibration.
