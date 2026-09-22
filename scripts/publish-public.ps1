param(
    [Parameter(Mandatory = $true)]
    [string]$Version,
    [string]$Notes = "",
    [switch]$SkipRelease
)

# Publishes the current working tree to the PUBLIC repo as a single squashed commit,
# excluding exercises/ and docs/superpowers/.
# Usage: .\scripts\publish-public.ps1 -Version 0.1.0

$ErrorActionPreference = "Stop"
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
foreach ($excluded in @("exercises", "docs\superpowers")) {
    $path = Join-Path $temp $excluded
    if (Test-Path $path) { Remove-Item -Recurse -Force $path }
}

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

Write-Host "Done. Public repo updated to v$Version (exercises/ and docs/superpowers/ excluded)."
