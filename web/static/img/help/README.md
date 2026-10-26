# /help screenshots

The six PNGs below (captured 2026-10-26: steps 2-6 are the real game on a 1920x1080 display, step 1 is the
result view dressed as the featured "Big Mac" forge) appear automatically on
[blankthespire.com/help](https://blankthespire.com/help) — one per numbered step. Until a file exists, the
page removes that step's figure and reads as text (see `web/static/help.js`), so partial sets are fine:
add them one at a time.

Keep them wide-ish (≈1200px) and under ~400 KB each; the page scales them to the card width.

| File | The moment to capture |
| --- | --- |
| `step-1.png` | The site's forge **result view**, with the class import code box and the **Copy code** button visible. Crop to the code box plus enough of the result above it to be recognizable. |
| `step-2.png` | The **Slay the Spire 2 main menu**, with the **Mod Configuration** entry hovered. |
| `step-3.png` | The **Mod Configuration** screen: the installed-mods list on the left with **BlankTheSpire** selected and its settings open. |
| `step-4.png` | The mod's settings panel with a `BTSC.…` code pasted into the **Class code** field (under "Import a class code") and the **Import** button hovered. |
| `step-5.png` | The **"Class imported"** dialog the mod shows right after a successful import ("Press \"Restart game\" below…"). This is the one people miss — keep the restart wording legible. |
| `step-6.png` | The **character select** screen with the freshly imported forged class shown next to the base-game characters. |

If you rename or add steps, update both `web/static/help.html` (the `<figure class="shot">` blocks) and
this table.
