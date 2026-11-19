# Emergency stop: unloads models, closes the server, FreeVideo and Ollama.
. "$PSScriptRoot\common.ps1"
try {
  $ps = Invoke-RestMethod "http://127.0.0.1:11434/api/ps" -TimeoutSec 3
  foreach ($m in $ps.models) {
    Invoke-RestMethod "http://127.0.0.1:11434/api/generate" -Method Post -ContentType "application/json" `
      -Body (@{ model = $m.name; keep_alive = 0 } | ConvertTo-Json) -TimeoutSec 20 | Out-Null
  }
} catch {}
Get-CimInstance Win32_Process | Where-Object {
  $_.CommandLine -and ($_.CommandLine -like "*3zT-Agent*server.py*" -or $_.CommandLine -like "*3zt-agent*server.py*")
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Stop-Process -Name "ollama app", "ollama" -Force -ErrorAction SilentlyContinue
$fv = Get-Setting "freevideo_home" (Join-Path $env:LOCALAPPDATA "FreeVideo")
Stop-Process -Name "FreeVideo" -Force -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath -like "$fv*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Write-Host "3zT Agent stopped." -ForegroundColor Green
