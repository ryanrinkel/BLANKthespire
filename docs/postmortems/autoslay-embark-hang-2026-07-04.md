# AutoSlay embark hangs on this box — map generation never starts ("Room type not assigned")

Found 2026-07-04 during a forge+autoslay session. **Blocks the entire AutoSlay smoke gate on this
machine right now.** Every run — forged AND base-game — hangs immediately after character-confirm,
before the Act-1 map is generated. Strong evidence this is **environmental (GPU/display or runtime
state), NOT the mod, the forged content, or a code regression.**

## Symptom
AutoSlay drives the menus fine (singleplayer → standard → select character → confirm), logs the
`context=baseline` MemProfile, then **nothing**. The Act-1 map never generates, no first room is
assigned, and after the wait window the runner throws:

```
[ERROR] [AutoSlay] Run failed with seed=<seed>: Room type not assigned
   at MegaCrit.Sts2.Core.AutoSlay.Helpers.WaitHelper.Until(...)
   at MegaCrit.Sts2.Core.AutoSlay.AutoSlayer.PlayRunAsync(String seed, ...)
```

During the stall the game **process is alive but idle** (~10% CPU, sleeping `S` state — NOT a pegged
core), GPU util 0%, and **godot.log dead-ends exactly at the baseline MemProfile line** — zero map
assets load, no errors, no progress. A healthy embark (see below) instead logs a map asset within
seconds and reaches `pre-room:Event:Act1:F1`.

### Healthy vs hung (same slot-01 class)
| | 2026-07-03 PASS (`_bugs/neow-kaleidoscope-crash-*.godot.log`) | 2026-07-04 (every run) |
|---|---|---|
| after `baseline` | `[WARN] Asset not cached: res://animations/map/ceremonial_beast_boss/...tres` → `context=pre-room:Event:Act1:F1` (VRAM +201MB, +6553 objects) → Neow | **nothing** — log ends at `baseline`; times out |

## Scope — ruled OUT
- **Not forged-class-specific:** base-game **Silent** (`CHARACTER.SILENT`, no forged classes staged)
  hangs identically. So it is not our forged content, not a specific class, not the card pool.
- **Not the injected relic:** repro with `--relic off` (no smoke-relic injection, no ethereal edit).
- **Not slow loading:** zero map-asset activity + idle CPU for 180s+ = a *stall*, not a slow preload
  (a preload pegs a core and streams asset logs).
- **Not a stale shader cache:** moved `~/.local/share/SlayTheSpire2/shader_cache` aside (forced
  regen) — no change.
- **Not a mod-code regression:** `mod/**/*.cs` is unchanged since the last PASS (2026-07-03,
  `aa62852`). The newest commit `4a9e5db` touches only forge/web, no mod C#. A fresh `dotnet build`
  this session deploys functionally the same mod.
- **Not a game update:** `sts2.dll` + `SlayTheSpire2` ELF mtime 2026-06-19 (v0.107.1, build 23811903);
  saves unchanged since 2026-06-21. Nothing in game/mod/save changed between the PASS and now.

## Most likely cause — a runtime asset-loader / map-gen stall (environmental)
The stall is at **map generation**: a healthy embark loads a map asset
(`res://animations/map/.../*_skel_data.tres`) within seconds of baseline and reaches
`pre-room:Event:Act1:F1`; the hung runs load **no map asset at all** and sit idle. So it's stuck
before/at map-gen, not in combat.

**GPU-selection is ruled OUT.** This is a hybrid-graphics laptop (Intel i915 iGPU + NVIDIA Quadro
RTX 3000, driver 595.71.05), but `nvidia-smi` during a hung embark shows **`SlayTheSpire2` running on
the NVIDIA GPU** (`C+G`, PID present) — the game is on the correct (dGPU) path, not the flaky i915.
And the clean earlier hangs had Ollama unloaded (full 6GB free), so it's **not VRAM starvation**
either. (There ARE recurring i915 LSPCON probe errors in `journalctl -k`, but they're on the display
connector, not the game's render device.)

That leaves an **async stall in map-gen / the Godot ResourceLoader** (a map-asset load await that
never completes), or an audio(FMOD)/Steam-cloud call at run-start — all share this signature: process
alive, ~10% idle CPU, zero logs, no progress. The last PASS (2026-07-03) implies the box was healthy
then and its runtime state degraded since (a suspend/resume is the usual trigger for a stuck loader
thread). A **reboot** is the cheapest reset and the recommended first step.

## Next steps (need display access — cannot be done blind)
1. **Reboot the box** (or reset the GPU/display path) and retry — the cheapest test of the
   environmental hypothesis.
2. **Watch the actual game window** during embark: is it a black/stuck map, a modal dialog, or frozen?
3. Force the NVIDIA GPU for the game (`__NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia`
   / Vulkan `DRI_PRIME`, or Steam launch options) to bypass the flaky i915 path.
4. Launch a **plain unmodded** base-game run to 100% exonerate the mod (can't be autoslay-driven —
   the hook lives in our mod — so this is a manual watch).
5. Check `dmesg`/`journalctl` for GPU resets/Xid during a hung embark.

## Repro
```sh
cd generation
# forged:
uv run btsgen-autoslay-smoke --seeds HANG1 --character class1 --relic off --timeout 260
# base-game (stage all forged classes out of ~/.local/share/SlayTheSpire2/forged/characters first):
uv run btsgen-autoslay-smoke --seeds HANGBASE --relic off --timeout 260
```

## Mitigation attempted (kept, but did NOT fix this)
`AutoSlaySmokeHook.cs::AutoSlayEmbarkTimeoutPatch.MinRoomWait` widened 90s → 180s. Reasonable for a
genuinely slow *cold* embark, but this is a **hang**, not slowness, so it doesn't help here. Left in
place (harmless; a real slow-preload box would benefit).

## Session logs
`generation/scratch/_session_forges/autoslay_*.log` (driver), and the per-seed AutoSlay logs in
`~/.local/share/SlayTheSpire2/autoslay/autoslay_<seed>.log` (SESSA1, VNEW1, VOFF1, BASEGAME1,
SHCLEAR1). godot.log snapshot at the time: dead-ends at the baseline MemProfile line.
