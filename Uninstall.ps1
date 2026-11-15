[CmdletBinding()]
param()
# Removes what Install.ps1 added: the launcher, its user PATH entry and the agent skill copies it recorded.
# Keeps .venv, .mrforge\ (tools, caches, receipts) and projects\.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$state = Join-Path $env:LOCALAPPDATA 'MarvelRivalsForge'
$binDir = Join-Path $state 'bin'
$installJson = Join-Path $state 'install.json'

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath) {
  $parts = $userPath -split ';' | Where-Object { $_ -and ($_ -ne $binDir) }
  [Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User')
}
if (Test-Path $binDir) { Remove-Item -Recurse -Force $binDir }
Write-Host 'launcher and PATH entry removed'

if (Test-Path $installJson) {
  $m = Get-Content $installJson -Raw | ConvertFrom-Json
  foreach ($s in @($m.skills)) {
    if ($s -and (Test-Path (Join-Path $s 'SKILL.md')) -and ((Get-Content (Join-Path $s 'SKILL.md') -Raw) -match 'name: marvelrivals-forge')) {
      Remove-Item -Recurse -Force $s
      Write-Host "agent skill removed: $s"
    }
  }
  Remove-Item -Force $installJson
}
Write-Host "kept: $root\.venv, $root\.mrforge, $root\projects"
