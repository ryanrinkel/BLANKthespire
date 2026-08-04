# Pull website-collected per-card feedback off the droplet and merge it into the generator's
# tracked feedback file (generation/feedback/card_feedback.jsonl), which the card prompt reads
# back as emulate-examples / anti-examples. Safe to run repeatedly: identical lines are de-duped,
# so re-pulling the (append-only) server log never creates duplicates.
#
$ErrorActionPreference = 'Stop'

# --- config (edit for your own server SSH alias / remote path) -------------------------------
$RemoteHost = 'your-droplet'                        # set to the alias in your ~/.ssh/config
$RemotePath = '/opt/btsweb/web/card_feedback.jsonl' # default BTSWEB_CARD_FEEDBACK_LOG on the droplet
# ---------------------------------------------------------------------------------------------

# repo root = two levels up from this script (web\tools\ -> repo)
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Local    = Join-Path $RepoRoot 'generation\feedback\card_feedback.jsonl'
$Tmp      = Join-Path $env:TEMP ('card_feedback_remote_{0}.jsonl' -f $PID)

Write-Host "Pulling feedback from ${RemoteHost}:${RemotePath} ..." -ForegroundColor Cyan
& scp "${RemoteHost}:${RemotePath}" $Tmp
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "scp failed (exit $LASTEXITCODE)." -ForegroundColor Red
    Write-Host "  - If the droplet has no feedback yet, the file just doesn't exist remotely (nothing to pull)." -ForegroundColor Red
    Write-Host "  - Otherwise check the '$RemoteHost' SSH alias and that the droplet is reachable." -ForegroundColor Red
    exit 1
}

function Read-Lines($path) {
    if (Test-Path $path) { Get-Content -LiteralPath $path -Encoding UTF8 | Where-Object { $_.Trim() -ne '' } }
    else { @() }
}

$existing = @(Read-Lines $Local)
$remote   = @(Read-Lines $Tmp)

# union, preserving existing order then appending genuinely-new remote lines (exact-line de-dup)
$seen   = [System.Collections.Generic.HashSet[string]]::new()
$merged = [System.Collections.Generic.List[string]]::new()
foreach ($l in $existing) { if ($seen.Add($l)) { $merged.Add($l) } }
$newLines = [System.Collections.Generic.List[string]]::new()
foreach ($l in $remote) { if ($seen.Add($l)) { $merged.Add($l); $newLines.Add($l) } }

# write back as UTF-8 (no BOM), LF line endings, single trailing newline
New-Item -ItemType Directory -Force -Path (Split-Path $Local) | Out-Null
$text = ($merged -join "`n") + "`n"
[System.IO.File]::WriteAllText($Local, $text, (New-Object System.Text.UTF8Encoding($false)))
Remove-Item $Tmp -ErrorAction SilentlyContinue

$added = $newLines.Count
Write-Host ""
Write-Host ("Done. {0} new entr{1} merged ({2} total in card_feedback.jsonl)." -f `
    $added, $(if ($added -eq 1) { 'y' } else { 'ies' }), $merged.Count) -ForegroundColor Green

if ($added -gt 0) {
    Write-Host ""
    Write-Host "New entries:" -ForegroundColor Yellow
    foreach ($l in ($newLines | Select-Object -Last 15)) {
        try {
            $o = $l | ConvertFrom-Json
            $note = if ($o.note) { " -- `"$($o.note)`"" } else { '' }
            Write-Host ("  [{0}] {1} ({2}){3}" -f $o.category, $o.name, $o.character, $note)
        } catch { Write-Host "  $l" }
    }
    Write-Host ""
    Write-Host "Review the new lines, then commit them so the next generation run picks them up:" -ForegroundColor Cyan
    Write-Host "  git add generation/feedback/card_feedback.jsonl" -ForegroundColor Cyan
    Write-Host "  git commit -m `"feedback: pull latest website card ratings`"" -ForegroundColor Cyan
}
