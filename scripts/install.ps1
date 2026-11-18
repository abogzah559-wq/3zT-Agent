# 3zT Agent installer: everything the app needs, once.
. "$PSScriptRoot\common.ps1"

Write-Host "==================================" -ForegroundColor Magenta
Write-Host "        3zT Agent - Setup" -ForegroundColor Magenta
Write-Host "==================================" -ForegroundColor Magenta

if (-not (Have winget)) {
  Say "winget not found. Install 'App Installer' from the Microsoft Store, then run this again." Red
  Read-Host "Press Enter to exit"; exit 1
}
function WingetInstall($id, $name) {
  Say "Installing $name..."
  winget install -e --id $id --accept-source-agreements --accept-package-agreements --silent
  RefreshPath
}

# 1) Core tools
if (-not (OllamaExe)) { WingetInstall "Ollama.Ollama" "Ollama" } else { Say "Ollama OK" Green }
if (-not (PythonW)) { WingetInstall "Python.Python.3.12" "Python 3.12" } else { Say "Python OK" Green }
if (-not (Have ffmpeg)) { WingetInstall "Gyan.FFmpeg" "ffmpeg" } else { Say "ffmpeg OK" Green }
if (-not (Have yt-dlp)) { WingetInstall "yt-dlp.yt-dlp" "yt-dlp (video downloader)" } else { Say "yt-dlp OK" Green }

# 2) Ollama tuning for a 12 GB GPU: one model at a time, flash attention, 8-bit KV cache
Say "Tuning Ollama..."
[Environment]::SetEnvironmentVariable("OLLAMA_MAX_LOADED_MODELS", "1", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_FLASH_ATTENTION", "1", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_KV_CACHE_TYPE", "q8_0", "User")
Set-OllamaEnv
Get-Process "ollama app", "ollama" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep 2
$ollama = OllamaExe
if (-not $ollama) { Say "Ollama install failed. Install it from ollama.com and run this again." Red; Read-Host "Press Enter"; exit 1 }
Start-Process $ollama -ArgumentList "serve" -WindowStyle Hidden
for ($i = 0; $i -lt 30 -and -not (Up "http://127.0.0.1:11434/api/version"); $i++) { Start-Sleep 1 }

# 3) Local models (the app can also download them later on first use)
$exec = Get-Setting "executor_model" "qwen3.5:9b"
$free = Get-Setting "free_model" "huihui_ai/qwen3.5-abliterated:9b"
Say "Downloading executor model: $exec (~6.6 GB)..."
& $ollama pull $exec
Say "Downloading uncensored model: $free (~6.6 GB)..."
& $ollama pull $free

# 4) Workspace + Desktop shortcut
New-Item -ItemType Directory -Force -Path (Get-Setting "workspace" "$HOME\agent-workspace") | Out-Null
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut("$([Environment]::GetFolderPath('Desktop'))\3zT Agent.lnk")
$lnk.TargetPath = "wscript.exe"
$lnk.Arguments = "`"$Root\3zT-Agent.vbs`""
$lnk.WorkingDirectory = $Root
$lnk.IconLocation = "$Root\assets\3zT.ico,0"
$lnk.Description = "3zT Agent"
$lnk.Save()

Say "Core setup done!" Green
Write-Host "Optional extras (subtitles with Whisper, background removal, voice-over, 4x upscaling):"
$a = Read-Host "Install extras now? (y/n)"
if ($a -match "^[yY]") { & "$PSScriptRoot\install_extras.ps1" -NoPause }
Say "All done. Open the app from the '3zT Agent' shortcut on your Desktop." Green
Read-Host "Press Enter to exit"
