# ASSETS TODO — what a full production build needs (running list)

A living inventory of the **art (and a little audio) that BLANK the spire is currently faking, borrowing, or
missing**, and what a shippable version would need. Started 2026-06-17 during Phase I (forged orbs). Add to this
as we hit each gap. Most entries are graphical; SFX/text noted where relevant.

## The framing constraint (read first)

Our content is **generated / data-driven**, not hand-authored: a class, its cards, its orbs, its trigger powers
all come from JSON the player forged. So we can **not** hand-draw one image per card/orb/power — the set is open
and per-user. Every asset need below therefore resolves to one of three production strategies:

- **(P) Procedural / tinted** — one base graphic recolored or composed at runtime from spec data (e.g. an orb
  sprite tinted by the orb's `hue`; a card frame tinted by the class pool color). Cheapest; scales infinitely.
- **(G) Generic-per-category** — a small fixed set of hand-made placeholders chosen by category (card art by
  type/archetype; power icon by "buff vs debuff"; a generic orb glyph). Looks intentional, bounded work.
- **(A) AI-generated at forge time** — the generator also produces an image (orb/card/portrait) and ships it in
  the import bundle / writes it to `user://forged/...`. Most "real", most expensive/risky; a later milestone.

For MVP we lean **P/G**; flag anything that truly needs bespoke art.

---

## 1. Orbs  — **ACTIVE GAP (partially fixed)**
Each custom orb (`ForgedClassKOrbM`, up to 3/class) needs:
- **Orb sprite** — the orb graphic that sits in the HUD slot (`OrbModel.CreateSprite` / `SpritePath`).
  - *Current:* **borrowing the Lightning orb's sprite** (`ForgedOrb.CreateCustomSprite/CustomSpritePath =>
    Lightning.*`). Without this the game threw `NullReferenceException` in `CreateSprite_Patch1` on the missing
    asset and **hung** (Phase I first in-game test, 2026-06-17). Hue is captured in `DarkenedColor` but not yet
    applied to the sprite.
  - *Production:* **(P)** one neutral orb sprite tinted by the spec `hue`, or **(G)** a few elemental glyphs.
- **Orb icon** — small texture used in hover tips (`OrbModel.Icon` / `IconPath`).
  - *Current:* **borrowing Lightning's icon** (`CustomIconPath => Lightning.IconPath`). Missing icon errored on
    hover (`No loader found for res://images/orbs/blankthespire-forged_class02_orb1.png`).
  - *Production:* same tinted/generic approach as the sprite.
- **Orb SFX** (channel / evoke / passive) — `CustomChannelSfx/EvokeSfx/PassiveSfx`, currently null → base default.
  Low priority; base sounds are fine.

## 2. Powers / statuses (the little icons under the HP bar) — **KNOWN GAP**
- **Base-game statuses we reuse have art already** — vulnerable, weak, frail, poison, strength, dexterity, thorns,
  regen, metallicize(Plating), artifact, buffer, intangible, ritual, blur, temp_strength, temp_dexterity,
  barricade, focus all map to real `PowerModel`s, so their icons ship with the game. **No work needed.**
- **Forged TRIGGER powers need their own icon** — each `ForgedTriggerPowerNN` / `ForgedClassKTriggerPowerNN`
  (Phase H3; 40 shared + 96 class = up to 136 shells) looks for `res://BlankTheSpire/images/powers/
  forged_trigger_power{NN}.png` and logs **`Could not find power image path`** (seen 2026-06-17). It still works
  (no crash — just no icon), but production needs one.
  - *Production:* **(G)** a single generic "forged power" buff glyph (one image, reused by all trigger powers),
    maybe tinted buff-gold vs debuff-purple. One asset covers all 136.

## 3. Characters (forged classes) — **PLACEHOLDER**
Each `ForgedCharacterSlotKK` (4 slots) is a `PlaceholderCharacterModel`. Needs, for a real character:
- **Character select portrait / splash** and the **in-combat character sprite** (idle/hit/death frames).
  - *Current:* placeholder (whatever `PlaceholderCharacterModel` provides). Text loc is synthesized in-code.
  - **⚠️ At character select the forged classes currently show the IRONCLAD card + Ironclad splash art**
    (the PlaceholderCharacterModel falls back to a base character's art). Confusing — looks like you're picking
    the Ironclad. **WANT (user, 2026-06-17): a neutral "?" character card + a "?" big splash on the select
    screen for every forged class** until real per-class art exists. So this needs TWO generic assets:
    (a) the small **character-select card/entry** image (the "?" card), and (b) the **big splash art** shown
    when that class is highlighted. One shared "?" pair covers all 4 forged slots.
  - *Production:* **(G)** the shared "?" card + splash above as the MVP; later a generic "forged" silhouette per
    class, or **(A)** a generated portrait. Bespoke animated combat sprites are the most expensive single asset
    — likely **(G)** a shared placeholder long-term.
- **Energy orb icons** — `BigEnergyIconPath` / `TextEnergyIconPath`. *Current:* mod images `charui/big_energy.png`
  / `charui/text_energy.png` (already exist). Verify they look right per class; could be **(P)** tinted by pool color.
- **Character select entry button art / banner**, **name color** (have a default).
- **The Architect intro dialogue** (text loc) — flagged by analyzer STS001 (currently downgraded to warning).

## 4. Cards — **PLACEHOLDER**
Each forged card (40 shared slots + 96 class slots) is a `DataCard` with in-code name/text but **no card art**.
- **Card portrait/art image** per card. *Current:* none → default/blank frame; game supplies the frame, type
  banner, energy cost, rarity gem, and keyword treatment.
  - *Production:* **(G)** a small library of generic art keyed by type (attack/skill/power) × archetype, or **(P)**
    a tinted abstract texture per class, or **(A)** generated per card. Hand-art-per-card is impossible (generated).
- Card **frames / rarity / energy / keyword icons** — **base game provides; no work.**

## 5. Relics — **DEFERRED (no custom relics yet)**
- Starter relic is a **placeholder (base `BurningBlood`)**; generated relics are preview-only/deferred. If/when we
  add forged relics, each needs a **relic icon** (and they'd auto-register like orbs/powers).
  - *Production:* **(G)** generic relic icon, or **(A)** generated.

## 6. Shared UI / misc
- Pool **color** (H/S/V) per class already drives card tint — **(P)**, working.
- Potion pool reuses BLANK's — no new potion art unless we add forged potions (deferred).
- **SFX** generally: orbs/powers fall back to base sounds; acceptable for MVP.

---

## Priority for a first "looks finished" pass
1. **(G) one generic forged-power icon** → kills the `forged_trigger_power*.png` log spam (1 asset, 136 uses).
2. **(P) tinted orb sprite+icon** → replaces the Lightning-borrow so custom orbs read as distinct (2 base
   assets + runtime tint). Removes the last "borrowed art" hack and the hue finally shows.
3. **(G) generic card art** by type/archetype (a handful of images).
4. **(G) "?" character-select card + big splash** (one shared pair) → stops forged classes showing as the
   Ironclad at select (user ask 2026-06-17). Quick win, high visibility.
5. **(G) generic character portrait/select art** (per class or one shared) — the fuller version of #4.
6. Relic art only if/when forged relics ship.

Everything above is cosmetic — the mechanics work with placeholders. The strategic call is **P vs G vs A** per
category (Section "framing constraint"); revisit when we move from "verify mechanics" to "ship-quality".
