# Image + video generation: downloads the FreeVideo launcher (github.com/FlashML-org/FreeVideo, Apache-2.0)
# and opens it once so it can install ComfyUI, its environment and the MiniMax H3 / H3 Image models.
# After that 3zT Agent starts FreeVideo by itself whenever a picture or video is requested.
. "$PSScriptRoot\common.ps1"

$tools = Join-Path $LocalDir "tools"
New-Item -ItemType Directory -Force -Path $tools | Out-Null
$exe = Join-Path $tools "FreeVideo.exe"
$url = "https://github.com/FlashML-org/FreeVideo/releases/latest/download/FreeVideo.exe"

Say "FreeVideo: local MiniMax H3 video (with sound) + H3 Image / Qwen-Image 2.1 pictures"
Write-Host "Needs an NVIDIA card with 8 GB+ VRAM, 16 GB+ RAM and about 40-60 GB of free disk for the models."

if (Test-Path $exe) {
  $a = Read-Host "FreeVideo.exe is already here. Download the latest version again? (y/n)"
  if ($a -match '^[yY]') { Remove-Item -Force $exe -ErrorAction SilentlyContinue }
}
if (-not (Test-Path $exe)) {
  Say "Downloading FreeVideo.exe ..."
  if (-not (Download $url $exe)) {
    Say "Download failed. Check the internet connection and run install-freevideo.bat again." Red
    Read-Host "Press Enter to close"
    exit 1
  }
}

# Stop the chat models first so the installer has the whole graphics card.
if (Up "http://127.0.0.1:11434/api/tags") {
  try {
    $ps = (Invoke-RestMethod "http://127.0.0.1:11434/api/ps" -TimeoutSec 5).models
    foreach ($m in $ps) {
      $body = @{ model = $m.name; keep_alive = 0 } | ConvertTo-Json
      Invoke-RestMethod "http://127.0.0.1:11434/api/generate" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 30 | Out-Null
    }
  } catch {}
}

Say "Opening the FreeVideo launcher" Green
Write-Host ""
Write-Host "  1. Choose 'Install a new ComfyUI' (recommended)."
Write-Host "  2. Keep 'Automatic download' for the models and accept the model license."
Write-Host "  3. Press 'Install & launch' and wait until ComfyUI opens in the browser."
Write-Host "  4. Optional: on the picture page install H3 Image (best quality pictures)."
Write-Host ""
Write-Host "When it finishes you can close the browser tab. 3zT Agent will start FreeVideo on its own"
Write-Host "every time you ask for a picture or a video."
Start-Process -FilePath $exe -WorkingDirectory $tools
Read-Host "`nPress Enter to close this window"
