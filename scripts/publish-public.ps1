param(
    [Parameter(Mandatory = $true)]
    [string]$Version,
    [string]$Notes = "",
    [switch]$SkipRelease
)

# Publishes the current working tree to the PUBLIC repo as a single squashed commit,
# excluding exercises/, docs/superpowers/ and frontend-modern/landing/ (panel-only).
# Usage: .\scripts\publish-public.ps1 -Version 0.1.0

$ErrorActionPreference = "Stop"
# PowerShell 5.1 turns git stderr warnings into terminating errors with Stop;
# route git stderr to stdout (git-only mechanism, harmless elsewhere).
$env:GIT_REDIRECT_STDERR = '2>&1'
$publicUrl = "https://github.com/JJRProDigital/ObsyGPT.git"
$temp = Join-Path $env:TEMP "obsygpt-public-v$Version"

if (Test-Path $temp) { Remove-Item -Recurse -Force $temp }
New-Item -ItemType Directory -Path $temp | Out-Null

Write-Host "Exporting HEAD to $temp..."
$tarPath = Join-Path $env:TEMP "obsygpt-public-v$Version.tar"
git archive --output=$tarPath HEAD
if ($LASTEXITCODE -ne 0) { throw "git archive failed" }
tar -xf $tarPath -C $temp
if ($LASTEXITCODE -ne 0) { throw "tar extract failed" }
Remove-Item $tarPath -Force

Write-Host "Removing excluded paths..."
foreach ($excluded in @("exercises", "docs\superpowers", "frontend-modern\landing")) {
    $path = Join-Path $temp $excluded
    if (Test-Path $path) { Remove-Item -Recurse -Force $path }
}

# Public snapshots get a redirect stub instead of the real landing, so their
# frontend Docker build (COPY landing) keeps working.
$landingStub = @'
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="refresh" content="0; url=/app/" />
  <title>ObsyGPT</title>
</head>
<body>
  <p><a href="/app/">Abrir ObsyGPT</a></p>
</body>
</html>
'@
$landingPath = Join-Path $temp "frontend-modern\landing"
New-Item -ItemType Directory -Path $landingPath -Force | Out-Null
Set-Content -Path (Join-Path $landingPath "index.html") -Value $landingStub -Encoding utf8

Push-Location $temp
try {
    git init --quiet
    git checkout -q -b main
    git add -A
    git -c user.name="JJRProDigital" -c user.email="JJRProDigital@users.noreply.github.com" commit --quiet -m "ObsyGPT v$Version"
    git tag "v$Version"

    Write-Host "Pushing to public repo (force, squash history)..."
    git remote add origin $publicUrl
    git push --force origin main
    git push --force origin "v$Version"

    if (-not $SkipRelease) {
        Write-Host "Creating GitHub release v$Version..."
        if ($Notes -ne "" -and (Test-Path $Notes)) {
            gh release create "v$Version" --repo JJRProDigital/ObsyGPT --title "ObsyGPT v$Version" --notes-file $Notes
        } else {
            gh release create "v$Version" --repo JJRProDigital/ObsyGPT --title "ObsyGPT v$Version" --notes $Notes
        }
    }
} finally {
    Pop-Location
}

Write-Host "Done. Public repo updated to v$Version (exercises/, docs/superpowers/ and frontend-modern/landing/ excluded)."
