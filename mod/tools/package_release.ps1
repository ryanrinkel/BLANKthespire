<#
.SYNOPSIS
    Package a BLANK the spire soft-launch release zip for friends-as-testers.

.DESCRIPTION
    Produces release\BlankTheSpire-v<Version>.zip containing exactly what a friend drops into the
    Slay the Spire 2 `mods\` folder:

        BlankTheSpire\   (BlankTheSpire.dll, .json, .pck  -- .pdb is dropped)
        BaseLib\         (BaseLib.dll, .json, .pck         -- bundled; private use only)

    Source of truth is the *deployed* mods folder (the proven-good artifact a friend would install),
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

$srcBlank   = Join-Path $GameMods "BlankTheSpire"
$srcBaseLib = Join-Path $GameMods "BaseLib"

foreach ($p in @($srcBlank, $srcBaseLib)) {
    if (-not (Test-Path $p)) {
        throw "Source mod folder not found: $p  (build/deploy the mod and install BaseLib first, or pass -GameMods)"
    }
}

# Required runtime files (must exist in the deployed folder).
$blankRuntime   = @("BlankTheSpire.dll", "BlankTheSpire.json", "BlankTheSpire.pck")
$baseLibRuntime = @("BaseLib.dll", "BaseLib.json", "BaseLib.pck")
foreach ($f in $blankRuntime)   { if (-not (Test-Path (Join-Path $srcBlank $f)))   { throw "Missing $f in $srcBlank" } }
foreach ($f in $baseLibRuntime) { if (-not (Test-Path (Join-Path $srcBaseLib $f))) { throw "Missing $f in $srcBaseLib" } }

# Fresh staging dir.
$stage = Join-Path ([System.IO.Path]::GetTempPath()) "bts-release-$Version"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
$stageBlank   = New-Item -ItemType Directory -Force -Path (Join-Path $stage "BlankTheSpire")   | ForEach-Object FullName
$stageBaseLib = New-Item -ItemType Directory -Force -Path (Join-Path $stage "BaseLib")         | ForEach-Object FullName

# Copy runtime files only (drops .pdb and anything else).
foreach ($f in $blankRuntime)   { Copy-Item (Join-Path $srcBlank $f)   (Join-Path $stageBlank $f)   -Force }
foreach ($f in $baseLibRuntime) { Copy-Item (Join-Path $srcBaseLib $f) (Join-Path $stageBaseLib $f) -Force }

# Version-stamp the staged BlankTheSpire manifest (working tree manifest is untouched).
$manifestPath = Join-Path $stageBlank "BlankTheSpire.json"
$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
$manifest.version = "v$Version"
$manifest | ConvertTo-Json -Depth 10 | Set-Content $manifestPath -Encoding utf8

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
Write-Host "  BaseLib/        $($baseLibRuntime -join ', ')"
