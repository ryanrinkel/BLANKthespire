<#
.SYNOPSIS
    Package a BLANK the spire release zip (GitHub releases / non-Workshop installs).

.DESCRIPTION
    Produces release\BlankTheSpire-v<Version>.zip containing exactly what a player drops into the
    Slay the Spire 2 `mods\` folder:

        BlankTheSpire\   (BlankTheSpire.dll, .json, .pck  -- .pdb is dropped)

    BaseLib is NOT bundled (GitHub #2, policy 2026-11-05). A local mods\BaseLib makes the game disable
    the Workshop BaseLib for every mod the player owns, and BaseLib is not binary-compatible across
    minor versions, so a frozen bundle breaks things. Players get BaseLib from the Steam Workshop
    (item 3737335127) or, off Steam, from https://github.com/Alchyr/BaseLib-StS2/releases (the
    version in the manifest's "min_version"). See INSTALL.md.

    Source of truth is the *deployed* mods folder (the proven-good artifact a player would install),
    not the raw build output. The BlankTheSpire manifest is version-stamped into the staged copy
    (the working tree manifest is left untouched).

.PARAMETER Version
    Release version, e.g. 0.1.0. Becomes the zip name and the staged manifest "version" field.

.PARAMETER GameMods
    The Slay the Spire 2 mods folder to source the deployed artifacts from.

.PARAMETER OutDir
    Where to write the zip. Defaults to <repo>\release.

.EXAMPLE
    pwsh mod\tools\package_release.ps1 -Version 0.1.0
#>
[CmdletBinding()]
param(
    [string]$Version = "0.1.0",
    [string]$GameMods = "C:\Program Files (x86)\Steam\steamapps\common\Slay the Spire 2\mods",
    [string]$OutDir
)

$ErrorActionPreference = "Stop"

# repo root = two levels up from this script (mod\tools\ -> mod\ -> repo)
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $OutDir) { $OutDir = Join-Path $repoRoot "release" }

$srcBlank = Join-Path $GameMods "BlankTheSpire"
if (-not (Test-Path $srcBlank)) {
    throw "Source mod folder not found: $srcBlank  (build/deploy the mod first, or pass -GameMods)"
}

# Required runtime files (must exist in the deployed folder).
$blankRuntime = @("BlankTheSpire.dll", "BlankTheSpire.json", "BlankTheSpire.pck")
foreach ($f in $blankRuntime) { if (-not (Test-Path (Join-Path $srcBlank $f))) { throw "Missing $f in $srcBlank" } }

# Fresh staging dir.
$stage = Join-Path ([System.IO.Path]::GetTempPath()) "bts-release-$Version"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
$stageBlank = New-Item -ItemType Directory -Force -Path (Join-Path $stage "BlankTheSpire") | ForEach-Object FullName

# Copy runtime files only (drops .pdb and anything else).
foreach ($f in $blankRuntime) { Copy-Item (Join-Path $srcBlank $f) (Join-Path $stageBlank $f) -Force }

# Version-stamp the staged BlankTheSpire manifest (working tree manifest is untouched). A text replace of the
# "version" field only, so the rest (the {id, min_version} dependency objects) is never re-serialized.
$manifestPath = Join-Path $stageBlank "BlankTheSpire.json"
$raw = [System.IO.File]::ReadAllText($manifestPath)
$stamped = ([regex]'("version"\s*:\s*")[^"]*(")').Replace($raw, "`${1}v$Version`${2}", 1)
if ($stamped -notmatch "`"version`"\s*:\s*`"v$([regex]::Escape($Version))`"") {
    throw "Could not stamp the version into $manifestPath"
}
[System.IO.File]::WriteAllText($manifestPath, $stamped, (New-Object System.Text.UTF8Encoding($false)))
$manifest = $stamped | ConvertFrom-Json
$baseLibDep = @($manifest.dependencies) | Where-Object { $_.id -eq "BaseLib" }
if (-not $baseLibDep -or -not $baseLibDep.min_version) {
    throw "Manifest must declare {`"id`": `"BaseLib`", `"min_version`": ...} in dependencies"
}

# Zip it.
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$zipPath = Join-Path $OutDir "BlankTheSpire-v$Version.zip"
if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zipPath -CompressionLevel Optimal

Remove-Item -Recurse -Force $stage

$size = [math]::Round((Get-Item $zipPath).Length / 1KB, 1)
Write-Host ""
Write-Host "Packaged $zipPath ($size KB)" -ForegroundColor Green
Write-Host "  BlankTheSpire/  $($blankRuntime -join ', ')  [version v$Version]"
Write-Host "  (BaseLib not bundled; requires BaseLib >= $($baseLibDep.min_version) from the Workshop or its GitHub releases)"
