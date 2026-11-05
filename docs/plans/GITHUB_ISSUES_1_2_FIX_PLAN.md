# GitHub issues #1 and #2 - evaluation and fix plan (2026-11-04)

Repo: https://github.com/ryanrinkel/BLANKthespire  (open issues #1, #2; both labelled bug)
Mod shipped to reporters: v0.5.0 (Workshop item 3803255976, uploaded 2026-10-28; byte-identical to
`workshop/workspace/content/` and to the local `mods/BlankTheSpire/`).

Verdict: both need a fix. Three defects, one cosmetic warning, one release-process gap. All fixes are
mod-side; the web/forge side needs nothing to unblock users (one optional validator symmetry tweak).

---

## Issue #1 - "Characters not being able to be imported" (Mrpickaxe, 2026-10-17)

### What happens
Two of the four codes fail the mod's import validator:
`Import rejected ... card 11: at most one 'transform_card' effect per card`
(code 1 = "Hero of Kvatch", card 11 = Oblivion Spark; code 2 = "Rich Uncle Pennybags", card 21 =
Corporate Ladder). Both codes decode fine on the generation side (`tools/show_cards.py`).

### Root cause (confirmed by reading both validators)
`mod/BlankTheSpireCode/Engine/ForgedCards.cs:2200`

```csharp
if ((effects.Concat(upgrade ?? [])).Count(e => e.Op == "transform_card") > 1)
    return "at most one 'transform_card' effect per card ...";
```

counts base + upgrade TOGETHER. The upgrade list is a full replacement list, so every transform card
whose upgrade repeats the transform (which is the normal shape the forge emits) has exactly two and is
rejected. The generation validator (`generation/btsgen/validator.py:1461`) counts the base list only,
and the mod's own `graft_card` rule a few lines later already counts the two lists independently with a
comment saying it matches validator.py. `transform_card` was simply never given the same treatment.

Blast radius: every forged class that contains a transform card has been un-importable in the game
since Phase AH shipped the op. Nobody noticed because the Phase AH smoke testers had no upgrade list
repeating the op.

### Fix
1. `ForgedCards.cs` ~2200: count base and upgrade independently (same pattern as the graft_card rule):
   `effects.Count(transform) > 1 || (upgrade ?? []).Count(transform) > 1`.
   Keep the transform-vs-purge rule as-is (an `Any` across both lists is correct there).
2. `generation/btsgen/validator.py` ~1461: add the symmetric upgrade-list check so the two validators
   stay byte-lockstep (no behaviour change for well-formed cards).
3. Regression: a generation test with transform_card in base+upgrade must pass the validator; after
   the mod rebuild, queue the reporter's "Hero of Kvatch" code through `forged/import_code.txt` and
   confirm `[IMPORT] queued code ... imported` in godot.log.

Effort: ~20 minutes plus the shared release below.

---

## Issue #2 - "missing thorns/poison totals, cards hover and don't apply" (JAViL197, 2026-11-01)

Reporter: Workshop install, game v0.107.1 (2026-06-18 build, identical to the local one), also sees the
game's "Mod Manifest should be migrated" notice. Same symptoms on an Archive class (The Unruly Goose,
a v55 code), so it is not class-specific. Three separate things are going on.

### 2a. CRITICAL - cards hover and the status is never applied (BaseLib binary incompatibility)

Root cause: the mod is compiled against NuGet `Alchyr.Sts2.BaseLib 3.2.1`
(`mod/BlankTheSpire.csproj:35`). The Steam Workshop BaseLib (item 3737335127) has been **v3.4.7 since
2026-09-11**. Between 3.2.1 and 3.4.7 BaseLib changed the overload the mod uses for every base status:

```
3.2.1: Task<IReadOnlyList<T>> Apply<T>(PlayerChoiceContext ctx, CardModel card, CardPlay? cardPlay)
3.4.7: Task<IReadOnlyList<T>> Apply<T>(PlayerChoiceContext ctx, CardModel card, CardPlay? cardPlay, bool silent = false)
```

`EffectRunner.cs:2042` calls `CommonActions.Apply<T>(ctx, card, play)`. C# binds optional parameters at
compile time, so the shipped DLL references the 3-parameter method, which no longer exists in 3.4.7.
The first debuff play JITs `ApplyPower<T>` -> `MissingMethodException` -> the card's play task faults ->
the card stays hovering and every effect after the status is skipped. Exactly the report
("hover in the air and don't apply all the effects"; Red Silk Snare = block then temp_thorns).
Self-buffs go through `ApplySelf<T>(ctx, card)` whose compiled form `(ctx, card, false)` still matches,
but thorns/poison/vulnerable etc. on an enemy or via the shared wrapper hit the broken overload.
`CardAttack`, `CardBlock`, `Draw` signatures are unchanged (only a `CardPlay?` nullability annotation).

Why no smoke ever caught it: the local game has a hand-copied `mods/BaseLib` (v3.2.1, dated June 9).
godot.log on every local run says
`Mod with ID BaseLib is loaded both via Steam and local mods directory. Disabling the Steam workshop version.`
So every AutoSlay smoke since September ran against 3.2.1 while every Workshop player ran 3.4.7.
The GitHub release zip also bundles BaseLib 3.2.1 (INSTALL.md), so zip users work and Workshop users
have been broken since BaseLib auto-updated in September. Workshop subscribers: 4.

Fix:
1. `BlankTheSpire.csproj`: `Alchyr.Sts2.BaseLib` 3.2.1 -> 3.4.7 (on nuget.org; 3.4.0 is already in the
   local cache, 3.4.7 is not). Rebuild with `~/.dotnet/dotnet.exe build mod/BlankTheSpire.csproj -c Debug`;
   compile errors will surface any SOURCE-level breaks (none expected from the API diff: the only
   touched members are `CommonActions.Apply/CardAttack` overloads and `CustomTemporaryPowerModel.Type`,
   which the mod does not override).
2. Make the local environment match players: delete `mods/BaseLib` from the game folder (a copy of the
   3.2.1 files goes under `_modref/baselib-3.2.1-local/` for reference) so the game loads the Workshop
   3.4.7 copy. Record this in the smoke notes so it is never re-shadowed.
3. Reproduce before / verify after: drop the reporter's Umbreon code into
   `%APPDATA%/SlayTheSpire2/forged/import_code.txt` (`slot=4`), run
   `uv run btsgen-autoslay-smoke --seeds <SEED> --character class4 --relic off --timeout 600` from
   `generation/`, then `grep -a -A15 Exception godot.log | grep -a BlankTheSpire` and
   `grep -a MissingMethodException godot.log`. Expect the exception with the 3.2.1 DLL under 3.4.7 and
   zero mod frames after the rebuild. Also confirm `[AX]`/apply lines show the poison/thorns stacks.
4. Declare the dependency properly in `mod/BlankTheSpire.json` and the Workshop manifest copy
   (new-style object form):
   `"dependencies": [{"id": "BaseLib", "min_version": "3.4.7"}]`, add `"min_game_version": "0.107.1"`.
   The game will then refuse to load the mod on an older BaseLib instead of failing mid-combat.
   (The "v0.5.0" version string is fine: the game's SemanticVersion parser accepts a leading `v`.)
5. Stop bundling BaseLib in the GitHub release zip (decision 2026-11-05, see the policy section below).
   The zip ships `mods/BlankTheSpire/` only. INSTALL.md: "Subscribe to BaseLib on the Workshop
   (item 3737335127). Non-Steam / Linux: download the same version from
   https://github.com/Alchyr/BaseLib-StS2/releases. If you installed an earlier zip, DELETE
   `mods/BaseLib/` first - a leftover local copy overrides the Workshop one for every mod you own."
6. Shrink the churn-prone surface while in this code: replace the three `CommonActions.Apply` /
   `ApplySelf` call sites (`EffectRunner.ApplyPower`, ~2042) with direct base-game `PowerCmd.Apply`
   calls that read the card's `PowerVar<T>` (the base-game API the game's own cards use, and the
   same mechanics BaseLib wraps). `CardAttack` / `CardBlock` / `Draw` stay on BaseLib for now (their
   signatures were stable across 3.2 -> 3.4); list them in the policy section as the remaining
   binary-compat exposure. The inherited bases (`ConstructedCardModel`, `Custom*Model`, the `*Loc`
   records) changed nothing the mod overrides in two minor versions and are kept.
7. Guards for the future: log BaseLib's loaded assembly version and the mod's compiled-against version
   at mod init (one `[BOOT]` line), and make the smoke harness FAIL its pre-check when godot.log shows
   `Disabling the Steam workshop version` for BaseLib (the local-copy shadowing that hid this bug).

Effort: 2-3 hours including two smoke seeds (the PowerCmd rewrite adds ~1 hour; it is covered by the
same status smoke).

### BaseLib dependency policy (decided 2026-11-05)

One supported configuration: the Workshop BaseLib, whatever version it currently is.

Why not pin or bundle:
- Steam auto-updates BaseLib for every subscriber; the mod cannot pin it for Workshop players at all.
- A bundled local `mods/BaseLib` makes the game disable the Workshop copy for EVERY mod on the player's
  machine ("Disabling the Steam workshop version"), so a frozen bundle breaks other mods instead of ours.
- BaseLib updates track game patches; freezing BaseLib does not freeze the game, so the next STS2 patch
  forces a rebuild anyway.
- BaseLib's semver is source-compatible, not binary-compatible (3.2 -> 3.4 added an optional parameter
  and broke us). Any minor can break a stale DLL silently; only recompiling fixes that.

What "unstable" costs: the hours between a BaseLib update and our rebuilt release. Keep that under a day:
1. Build against EXACTLY the version the Workshop serves (3.4.7 today; it is on nuget.org). If NuGet
   ever lags the Workshop, reference the Workshop DLL by path
   (`steamapps/workshop/content/2868840/3737335127/BaseLib/BaseLib.dll`) via a `Reference` HintPath.
2. Declare `{"id":"BaseLib","min_version":"<built-against>"}` in `BlankTheSpire.json` so an older
   BaseLib fails at load with the game's own dependency error instead of mid-combat.
3. Test only on the Workshop copy: the local `mods/BaseLib` is deleted (a copy stays in `_modref/`
   for source reference only) and the smoke pre-check refuses to run if it comes back.
4. Watch for updates: a weekly check of Steam's `time_updated` for item 3737335127
   (`ISteamRemoteStorage/GetPublishedFileDetails`, no key needed) from the droplet timer that already
   produces the Monday digest; a change = bump the package, rebuild, one smoke seed, release.
   Also watch the game build (release_info.json / Steam buildid 23811903 today) since a game patch
   usually lands with or before a BaseLib release.
5. Remaining binary-compat exposure after 2a.6, to re-check on every BaseLib bump:
   `CommonActions.CardAttack(card, play, hits)`, `CommonActions.CardBlock(card, play)`,
   `CommonActions.Draw(card, ctx)`, the `ConstructedCardModel.With*` helpers, `ModConfig`,
   `BaseLib.Utils.NodeFactories`, the `*Loc` records. Diff those signatures between the old and new tag
   (`git -C _modref/BaseLib-StS2 diff vOLD..vNEW -- Utils/CommonActions.cs Abstracts/`) before rebuilding.

Migration note for existing zip users (the October zips bundled BaseLib 3.2.1): their local copy will
shadow the Workshop one and v0.5.1 will refuse to load with a BaseLib-too-old error. The release note and
INSTALL.md must say "delete mods/BaseLib and subscribe to BaseLib on the Workshop".

### 2b. Card text never shows status amounts ("Apply Poison.", "Gain Thorns.")

This is NOT a v0.5.0 regression. `ForgedCards.Describe` has emitted `Gain {name}.` / `Apply {name}.`
with the bare status word since the first public commit (3a125fc), and the i18n describe dump from the
Oct 27 smoke (`logs/bts_describe_zhs.txt`, `[fmt]` section = after the game's SmartFormat pass) shows
even the baked Bash card renders "Deal 8 damage. Apply Vulnerable." with no number. The DataCard
declares the `PowerVar<T>` (so the amount is applied correctly and the hover tip exists) but the text
never references it. The website preview (cardgen.py) prints literal numbers, which is why the reporter
noticed the difference between the site and the game.

How the game resolves placeholders (LocManager.cs:230): `DictionarySource` over the card's
`DynamicVarSet` (keys = the var name; an unnamed `PowerVar<T>` is keyed `typeof(T).Name`, e.g.
`PoisonPower`, `ThornsPower`, `ForgedTempThornsPower`; a named one keeps its name, e.g. `Weak2`) plus
`ReflectionSource` (only the six convenience properties Poison/Vulnerable/Weak/Strength/Dexterity/Doom).
Using the dictionary key works for every status, so emit that.

Fix:
1. `ForgedCards.cs`: add `StatusVarRef(effects, i)` returning `"{" + key + "}"` where key is
   `StatusVarName(effects, i)` for a suffixed second copy, else the power type name for the status
   (lift the status -> power-type switch out of `DataCard.cs:340-370` and `EffectRunner.ApplyStatus`
   into one shared map in ForgedCards so the three stay in lockstep). Statuses that declare no var
   (`strength_down` uses `StrengthLoss`, the Blight-Strike doom form, the BM self-status sentences)
   keep their current text.
2. Describe: `Gain {amount} {status}.` / `Apply {amount} {status}{to}.` with `("amount", StatusVarRef)`.
   Match the damage form the mod already uses for English (plain `{Damage}`), and in
   `ForgedText.zhs.cs` update `card.status.gain` / `card.status.apply` to carry `{amount}{unit}`
   (the `frag.apply_status` trigger template already has an `{amount}` slot, copy its wording).
3. Keep cardgen.py's literal-number sentences as they are (site preview); only the placeholder differs,
   the sentence shape is identical, so the lockstep tests still hold.
4. Verify with the describe dump: launch once with `BTS_DESCRIBE_DUMP=1` (or any smoke) in English and
   check `[fmt] CARD.* desc` lines for status cards contain the number and godot.log has zero
   "Localization formatting error" lines (memory: card-text-localization-errors). Repeat in zhs.

Effort: 2-3 hours.

### 2c. "Mod Manifest should be migrated" (cosmetic)

The game's `ModManifest.ReadFromStream` logs this (loc key MOD_ERROR.MIGRATION_REQUIRED) when
`dependencies` is a list of strings instead of `{id, min_version}` objects. Harmless today ("It works
for now but this will be removed in a future release"); fixed for free by step 2a.4.

---

## Release (one mod release covers everything)

1. Branch, apply #1 fix + 2a (incl. the PowerCmd rewrite and the manifest) + 2b, bump to v0.5.1,
   change note:
   "v0.5.1 - fixes classes with a transforming card failing to import; fixes cards hovering / statuses
   not applying with the current Workshop BaseLib (3.4.7, now required); card text shows status
   amounts; manifest migrated. Zip users: delete mods/BaseLib and subscribe to BaseLib on the Workshop."
2. Delete the local `mods/BaseLib`, build against BaseLib 3.4.7, run two AutoSlay seeds with the
   Workshop BaseLib loaded (Umbreon in slot 4, a transform class such as Hero of Kvatch imported via
   the queue), gate on: `[BOOT]` line shows BaseLib 3.4.7 from the workshop path, zero BlankTheSpire
   exception frames, zero Localization formatting errors, `[IMPORT] ... imported` for both codes,
   describe dump `[fmt]` lines show the status amounts. Unstage slot 4 afterwards.
3. Ship in the standing order (memory: release ordering): zip + GitHub release (mod only, no BaseLib;
   INSTALL.md rewritten per 2a.5) -> Workshop upload (previews dir must stay non-empty, PNGs only;
   workshop.json already lists BaseLib's item id as the dependency) -> no droplet deploy needed
   (vocab version unchanged at v70). The validator.py symmetry tweak can ride the next web deploy.
4. Add the weekly BaseLib / game-build update check to the droplet digest timer (policy step 4) and
   the smoke pre-check (2a.7). These can land in the same branch or the web deploy that follows.
5. Reply on #1 and #2 with the cause and "update to v0.5.1; BaseLib comes from the Workshop", ask
   JAViL197 for a godot.log only if the hover persists after updating. Close #1 once Mrpickaxe
   confirms or after the import check in step 2 passes with their exact codes.

## Decisions taken (2026-11-05)
- BaseLib is NOT bundled any more; the Workshop BaseLib is the only supported configuration (policy
  section above). Non-Steam users fetch the same version from BaseLib's GitHub releases.
- The local `mods/BaseLib` (3.2.1) is deleted so every smoke runs on the Workshop copy.
- `CommonActions.Apply` / `ApplySelf` are replaced with direct base-game `PowerCmd` calls to cut the
  most churn-prone BaseLib dependency; the rest of the BaseLib surface stays and is diffed on each bump.
