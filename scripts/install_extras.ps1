# Optional open-source extras, isolated in their own Python 3.12 venv:
#   faster-whisper (speech-to-text, subtitles), rembg (background removal), edge-tts (voice-over), yt-dlp,
#   document libraries for the skills, Node packages (docx, pptxgenjs) and Real-ESRGAN ncnn-vulkan (upscaling).
param([switch]$NoPause)
. "$PSScriptRoot\common.ps1"
RefreshPath

$venv = Join-Path $LocalDir "venv"
$vpy = Join-Path $venv "Scripts\python.exe"

# Python 3.12 (wheels for these packages are reliable on 3.12)
$py312 = $null
if (Have py) { & py -3.12 -c "import sys" 2>$null; if ($LASTEXITCODE -eq 0) { $py312 = "py312" } }
if (-not $py312) {
  Say "Installing Python 3.12 for the extras..."
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements --silent
  RefreshPath
}

if (-not (Test-Path $vpy)) {
  Say "Creating extras environment..."
  New-Item -ItemType Directory -Force -Path $LocalDir | Out-Null
  & py -3.12 -m venv $venv
}
if (-not (Test-Path $vpy)) { Say "Could not create the Python 3.12 environment." Red; if (-not $NoPause) { Read-Host "Press Enter" }; exit 1 }

Say "Installing faster-whisper, rembg, edge-tts, yt-dlp (a few minutes)..."
& $vpy -m pip install --upgrade pip
& $vpy -m pip install --upgrade faster-whisper "rembg[cpu]" pillow edge-tts yt-dlp
Say "Installing CUDA libraries so Whisper runs on your GPU (~1 GB)..."
& $vpy -m pip install --upgrade nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"

Say "Installing document & image libraries used by the skills (Word, PDF, Excel, PowerPoint, GIF)..."
& $vpy -m pip install --upgrade pypdf pdfplumber reportlab openpyxl pandas python-docx python-pptx defusedxml lxml pyyaml imageio numpy "markitdown[pptx,docx,pdf,xlsx]"

# Node.js packages used by the docx / pptx skills
if (-not (Have node)) {
  Say "Installing Node.js (for Word/PowerPoint skills)..."
  winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements --silent
  RefreshPath
}
if (Have npm) {
  $nodeDir = Join-Path $LocalDir "node"
  New-Item -ItemType Directory -Force -Path $nodeDir | Out-Null
  Say "Installing docx + pptxgenjs..."
  & npm install --prefix $nodeDir docx pptxgenjs --no-audit --no-fund
} else { Say "npm not found; Word/PowerPoint creation skills will be limited." Yellow }

# Real-ESRGAN portable (Vulkan: runs on any GPU, no CUDA needed)
$rdir = Join-Path $LocalDir "tools\realesrgan"
if (-not (Get-ChildItem $rdir -Recurse -Filter "realesrgan-ncnn-vulkan.exe" -ErrorAction SilentlyContinue)) {
  Say "Downloading Real-ESRGAN..."
  New-Item -ItemType Directory -Force -Path $rdir | Out-Null
  $zip = Join-Path $rdir "realesrgan.zip"
  if (Download "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip" $zip) {
    Expand-Archive -Force $zip $rdir
    Remove-Item $zip -Force
  } else { Say "Real-ESRGAN download failed; run this file again later." Red }
} else { Say "Real-ESRGAN OK" Green }

Say "Extras ready. Whisper downloads its model (~1.6 GB) the first time you transcribe." Green
if (-not $NoPause) { Read-Host "Press Enter to exit" }
