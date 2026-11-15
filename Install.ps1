[CmdletBinding()]
param(
  [switch]$SkipTests,
  [switch]$DryRun,
  [switch]$Skills
)
# Installs MarvelRivals-Forge for the current user: .venv + editable install, one launcher on the user PATH,
# optional agent skill copy (-Skills). A second run converges; Uninstall.ps1 removes only what this adds.
# .mrforge\ (tools, caches) and projects\ are never touched.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }
$state = Join-Path $env:LOCALAPPDATA 'MarvelRivalsForge'
$binDir = Join-Path $state 'bin'
$launcher = Join-Path $binDir 'mrforge.cmd'
$skillSrc = Join-Path $root 'skills\marvelrivals-forge'
$skillTargets = @(
  (Join-Path $env:USERPROFILE '.claude\skills'),
  (Join-Path $env:USERPROFILE '.agents\skills')
) | Where-Object { Test-Path $_ }

Write-Host '== MarvelRivals-Forge install =='
Write-Host "root: $root"
if ($DryRun) {
  Write-Host 'Dry run: nothing will be changed.'
  Write-Host "  venv:     $root\.venv (pip install -e this folder)"
  Write-Host "  launcher: $launcher (added once to the user PATH)"
  if ($Skills) { foreach ($t in $skillTargets) { Write-Host "  agent skill: $t\marvelrivals-forge" } }
  return
}

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { throw 'Python 3.10+ was not found on PATH. Install it from python.org and run this again.' }
& $py.Source -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) { throw 'Python 3.10 or newer is required.' }

$venv = Join-Path $root '.venv'
$vpy = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $vpy)) {
  & $py.Source -m venv $venv
  if ($LASTEXITCODE -ne 0) { throw "venv creation failed ($LASTEXITCODE)" }
}
& $vpy -m pip install --disable-pip-version-check --quiet -e $root
if ($LASTEXITCODE -ne 0) { throw "pip install failed ($LASTEXITCODE)" }

if (-not $SkipTests) {
  & $vpy (Join-Path $root 'tests\run_tests.py')
  if ($LASTEXITCODE -ne 0) { throw "tests failed ($LASTEXITCODE)" }
}

# Launcher so 'mrforge' works from any folder; it names this checkout's venv and forge root.
New-Item -ItemType Directory -Force -Path $binDir | Out-Null
$lines = @(
  '@echo off',
  'setlocal EnableExtensions DisableDelayedExpansion',
  ('if not exist "{0}" (' -f $vpy),
  '  echo MarvelRivals-Forge is no longer in the folder this launcher points to. 1>&2',
  '  echo Run Install.ps1 from its current folder to repair the launcher. 1>&2',
  '  exit /b 3',
  ')',
  ('"{0}" -m mrforge %*' -f $vpy),
  'exit /b %ERRORLEVEL%'
)
[IO.File]::WriteAllText($launcher, (($lines -join "`r`n") + "`r`n"), (New-Object Text.UTF8Encoding($false)))
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not $userPath) { $userPath = '' }
if (($userPath -split ';') -notcontains $binDir) {
  [Environment]::SetEnvironmentVariable('Path', ($userPath.TrimEnd(';') + ';' + $binDir), 'User')
  Write-Host "added $binDir to the user PATH; open a new terminal to use 'mrforge'"
}
$manifest = @{ root = $root; launcher = $launcher; bin = $binDir; skills = @() }

if ($Skills) {
  foreach ($t in $skillTargets) {
    $dest = Join-Path $t 'marvelrivals-forge'
    if (Test-Path $dest) {
      $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
      $backup = Join-Path $state ("skill-backup\" + (Split-Path $t -Parent | Split-Path -Leaf) + "-$stamp")
      New-Item -ItemType Directory -Force -Path $backup | Out-Null
      Copy-Item -Recurse -Force $dest $backup
      Remove-Item -Recurse -Force $dest
    }
    Copy-Item -Recurse $skillSrc $dest
    $manifest.skills += $dest
    Write-Host "agent skill installed: $dest"
  }
}
$manifest | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $state 'install.json')

& $vpy -m mrforge version | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'mrforge did not start after install' }
Write-Host ''
Write-Host 'Done. Next: mrforge doctor, mrforge setup, mrforge sync, mrforge index'
