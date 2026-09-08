# Steam Workshop packaging

Everything needed to publish BLANK the spire to the [STS2 Steam Workshop](https://steamcommunity.com/app/2868840/workshop/)
via Mega Crit's official [sts2-mod-uploader](https://github.com/megacrit/sts2-mod-uploader).

```
workshop/
  build_workspace.ps1     stages workspace\content\ from the deployed game mods folder
  DESCRIPTION.bbcode      canonical Workshop page text (Steam descriptions are BBCode) — edit THIS,
                          build_workspace.ps1 injects it into workshop.json
  workspace/              what ModUploader.exe consumes (-w workshop\workspace)
    workshop.json         metadata: title, visibility, tags, dependencies (BaseLib = 3737335127)
    image.png             required thumbnail, MUST be < 1MB          (not created yet)
    previews/             optional extra screenshots, each < 1MB
    content/              the shipped mod files — gitignored, staged by the script
    mod_id.txt            written by the FIRST upload; identifies the listing forever — COMMIT IT
```

Unlike the release zip (`mod\tools\package_release.ps1`), **BaseLib is not bundled** — it's a
Workshop dependency, so subscribers get [Alchyr's listing](https://steamcommunity.com/sharedfiles/filedetails/?id=3737335127)
automatically.

## Publishing a release

1. Build + deploy the mod to the game's `mods\` folder as usual (that deployed copy is the source of truth).
2. `pwsh workshop\build_workspace.ps1 -Version X.Y.Z -ChangeNote "what changed"`
3. With Steam running (the account that owns STS2): `ModUploader.exe upload -w workshop\workspace`
   (get the uploader from the [sts2-mod-uploader releases](https://github.com/megacrit/sts2-mod-uploader/releases)).
4. First upload only: accept the **Steam Workshop legal agreement** when prompted on the item page
   (the item stays invisible until you do), then commit the generated `mod_id.txt`.
5. Check `mod-uploader.log` if anything fails (it's gitignored).

## First-upload checklist (verify against reality, then delete this section)

- [ ] **content layout** — double-click `ModUploader.exe` once to generate its template workspace and
      confirm whether mod files sit at `content\` root (what `build_workspace.ps1` assumes, per the
      template README) or in a nested subfolder. Fix the script if nested.
- [ ] **dependencies field type** — `workshop.json` lists BaseLib's item ID as a string
      (`"3737335127"`); if the uploader complains, try it as a bare number.
- [ ] **tags** — browse the [STS2 Workshop](https://steamcommunity.com/app/2868840/workshop/) sidebar
      for the valid tag list and fill in `tags` (`"Tools & APIs"` is reserved for utility mods — not us).
- [ ] **thumbnail** — create `workspace\image.png` (< 1MB).
- [ ] **smoke test while private** — DELETE the manual `mods\BlankTheSpire` + `mods\BaseLib` copies
      first (avoid double-load), subscribe to the hidden item, confirm BaseLib auto-installs, launch,
      import a class code, play a hand.
- [ ] **go public** — add `previews\` screenshots, flip `"visibility": "public"`, re-upload, and update
      the root README/INSTALL to make Workshop the headline install path (zip stays as manual fallback).

## Compliance notes (Mega Crit content policy + Steam)

- The Workshop page must (and does, via `DESCRIPTION.bbcode`) state the mod is **unofficial and not
  affiliated with Mega Crit**, and be transparent that forged content is **AI-generated on the website**.
- **No donation links on the Workshop page.** Donations live on blankthespire.com only. Mega Crit's
  policy allows donations for modding work but forbids any other monetization, including paywalling
  mod content in or out of game.
- The package ships only our MIT-licensed runtime — no game assets, no BaseLib binaries, no
  AI-generated art.
