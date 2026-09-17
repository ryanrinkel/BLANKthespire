# /help screenshots

Drop the six PNGs below into this folder and they appear automatically on
[blankthespire.com/help](https://blankthespire.com/help) — one per numbered step. Until a file exists, the
page removes that step's figure and reads as text (see `web/static/help.js`), so partial sets are fine:
add them one at a time.

Keep them wide-ish (≈1200px) and under ~400 KB each; the page scales them to the card width.

| File | The moment to capture |
| --- | --- |
| `step-1.png` | The site's forge **result view**, with the class import code box and the **Copy code** button visible. Crop to the code box plus enough of the result above it to be recognizable. |
| `step-2.png` | The **Slay the Spire 2 main menu**, with the **Mods** / mod-settings entry visible (hovered or highlighted). |
| `step-3.png` | The **installed-mods list**, with **BLANK the spire** selected/highlighted. |
| `step-4.png` | The mod's settings panel showing the **"Import a class code"** field with a `BTSC.…` code pasted in and the **Import** button ready to press. |
| `step-5.png` | The **restart-required confirmation** the mod shows right after a successful import. This is the one people miss — make the restart wording legible. |
| `step-6.png` | The **character select** screen with the freshly imported forged class shown next to the base-game characters. |

If you rename or add steps, update both `web/static/help.html` (the `<figure class="shot">` blocks) and
this table.
