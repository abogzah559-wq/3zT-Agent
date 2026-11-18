# Shared helpers for the 3zT Agent scripts (ASCII only: Windows PowerShell 5.1 safe)
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
$Root = Split-Path -Parent $PSScriptRoot
$Port = 7272
$LocalDir = Join-Path $env:LOCALAPPDATA "3zT-Agent"
$DataDir = Join-Path $env:APPDATA "3zT-Agent"

function Say($t, $c = "Cyan") { Write-Host "`n>> $t" -ForegroundColor $c }
function Have($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function RefreshPath {
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
function Up($u) { try { Invoke-WebRequest $u -UseBasicParsing -TimeoutSec 2 | Out-Null; $true } catch { $false } }

function OllamaExe {
  $c = Get-Command ollama -ErrorAction SilentlyContinue
  if ($c) { return $c.Source }
  $p = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
  if (Test-Path $p) { return $p }
  return $null
}

function PythonW {
  # windowless python for the server (any Python 3.9+ works: the server uses only the standard library)
  foreach ($n in "pyw", "pythonw") {
    $c = Get-Command $n -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
  }
  $cands = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\pythonw.exe", "$env:ProgramFiles\Python3*\pythonw.exe" -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending
  if ($cands) { return $cands[0].FullName }
  return $null
}

function Set-OllamaEnv {
  foreach ($kv in @(@("OLLAMA_MAX_LOADED_MODELS", "1"), @("OLLAMA_FLASH_ATTENTION", "1"), @("OLLAMA_KV_CACHE_TYPE", "q8_0"))) {
    $v = [Environment]::GetEnvironmentVariable($kv[0], "User")
    if (-not $v) { $v = $kv[1] }
    Set-Item "env:$($kv[0])" $v
  }
}

function Get-Setting($name, $default) {
  $f = Join-Path $DataDir "settings.json"
  if (Test-Path $f) {
    try { $j = Get-Content $f -Raw -Encoding UTF8 | ConvertFrom-Json; if ($j.$name) { return $j.$name } } catch {}
  }
  return $default
}

function Download($url, $dest) {
  # resumable download with curl.exe (ships with Windows 10+)
  $part = "$dest.part"
  & curl.exe -L --fail --retry 5 --retry-delay 3 -C - -o $part $url
  if ($LASTEXITCODE -ne 0) { return $false }
  Move-Item -Force $part $dest
  return $true
}
