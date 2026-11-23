# Builds runtime\ for the Windows installer: Python 3.12 (full, with the media/document packages),
# ffmpeg + ffprobe, yt-dlp, Node.js 22 with docx / pptxgenjs / hyperframes / agent-browser,
# llama.cpp (CUDA 12 build + CUDA runtime) and Real-ESRGAN.
# Runs on a GitHub Actions windows runner (needs: internet, gh CLI with GH_TOKEN).
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Root = Split-Path -Parent $PSScriptRoot
$Rt = Join-Path $Root "runtime"
$Tmp = Join-Path $Root "build\tmp"
$PyVersion = "3.12.10"
New-Item -ItemType Directory -Force -Path $Rt, $Tmp, "$Rt\bin" | Out-Null

function Get-File($url, $dest) {
  Write-Host "download $url"
  & curl.exe -L --fail --retry 5 --retry-delay 5 -o $dest $url
  if ($LASTEXITCODE -ne 0) { throw "download failed: $url" }
}

# ---- Python (NuGet package = normal CPython layout: Lib, DLLs, pip; no ._pth isolation) ----
Get-File "https://www.nuget.org/api/v2/package/python/$PyVersion" "$Tmp\python.zip"
Expand-Archive -Force "$Tmp\python.zip" "$Tmp\python"
Move-Item "$Tmp\python\tools" "$Rt\python"
$py = "$Rt\python\python.exe"
& $py -m ensurepip --upgrade
& $py -m pip install --no-warn-script-location --upgrade pip
& $py -m pip install --no-warn-script-location `
  faster-whisper "rembg[cpu]" pillow edge-tts yt-dlp `
  pypdf pdfplumber reportlab openpyxl pandas python-docx python-pptx defusedxml lxml pyyaml imageio numpy `
  "markitdown[pptx,docx,pdf,xlsx]"
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
Get-ChildItem "$Rt\python" -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
if (-not (Test-Path "$Rt\python\pythonw.exe")) { throw "pythonw.exe missing in the Python package" }

# ---- ffmpeg + ffprobe ----
Get-File "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip" "$Tmp\ffmpeg.zip"
Expand-Archive -Force "$Tmp\ffmpeg.zip" "$Tmp\ffmpeg"
Get-ChildItem "$Tmp\ffmpeg" -Recurse -Include "ffmpeg.exe", "ffprobe.exe" | Copy-Item -Destination "$Rt\bin"

# ---- yt-dlp ----
Get-File "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" "$Rt\bin\yt-dlp.exe"

# ---- Node.js 22 + packages used by skills ----
$sums = (Invoke-WebRequest "https://nodejs.org/dist/latest-v22.x/SHASUMS256.txt" -UseBasicParsing).Content
$nodeZip = ([regex]::Match($sums, "node-v22[\d.]+-win-x64\.zip")).Value
if (-not $nodeZip) { throw "node zip not found" }
Get-File "https://nodejs.org/dist/latest-v22.x/$nodeZip" "$Tmp\node.zip"
Expand-Archive -Force "$Tmp\node.zip" "$Tmp\node"
Move-Item (Get-ChildItem "$Tmp\node" -Directory | Select-Object -First 1).FullName "$Rt\node"
$env:Path = "$Rt\node;" + $env:Path
$env:PUPPETEER_SKIP_DOWNLOAD = "1"
$env:HYPERFRAMES_NO_TELEMETRY = "1"
# packages live in their own folder: installing into node\node_modules would prune npm itself
$pk = "$Rt\node-packages"
New-Item -ItemType Directory -Force -Path $pk | Out-Null
Set-Content -Path "$pk\package.json" -Value '{"name":"3zt-agent-runtime","private":true}' -Encoding ascii
& "$Rt\node\npm.cmd" install --prefix $pk --no-audit --no-fund docx pptxgenjs hyperframes agent-browser
if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
if (-not (Test-Path "$pk\node_modules\.bin\hyperframes.cmd")) { throw "hyperframes CLI missing" }
if (-not (Test-Path "$pk\node_modules\.bin\agent-browser.cmd")) { throw "agent-browser CLI missing" }

# ---- llama.cpp (CUDA 12 build + its CUDA runtime DLLs) ----
New-Item -ItemType Directory -Force -Path "$Rt\llama" | Out-Null
# newest release that has the Windows CUDA 12 build (the "latest" one can be a nightly marker)
$rels = gh api "repos/ggml-org/llama.cpp/releases?per_page=15" | ConvertFrom-Json
$main = $null; $cudart = $null; $tag = $null
foreach ($r in $rels) {
  $names = $r.assets.name
  $m = $names | Where-Object { $_ -match "^llama-.*-bin-win-cuda-12[\d.]*-x64\.zip$" } | Sort-Object -Descending | Select-Object -First 1
  $c = $names | Where-Object { $_ -match "^cudart-llama-bin-win-cuda-12[\d.]*-x64\.zip$" } | Sort-Object -Descending | Select-Object -First 1
  if ($m -and $c) { $main = $m; $cudart = $c; $tag = $r.tag_name; break }
}
if (-not $main) {
  $rels | Select-Object -First 3 | ForEach-Object { Write-Host "$($_.tag_name): $($_.assets.name -join ', ')" }
  throw "no llama.cpp release with Windows CUDA 12 assets"
}
Write-Host "llama.cpp $tag : $main + $cudart"
foreach ($n in @($main, $cudart)) {
  gh release download $tag --repo ggml-org/llama.cpp --pattern $n --dir $Tmp --clobber
  Expand-Archive -Force "$Tmp\$n" "$Rt\llama"
}
if (-not (Get-ChildItem "$Rt\llama" -Recurse -Filter "llama-server.exe")) { throw "llama-server.exe missing" }
Get-ChildItem "$Rt\llama" -Recurse -Include "test-*.exe", "llama-bench.exe" | Remove-Item -Force -ErrorAction SilentlyContinue

# ---- Real-ESRGAN (Vulkan, any GPU) ----
Get-File "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip" "$Tmp\resr.zip"
Expand-Archive -Force "$Tmp\resr.zip" "$Rt\realesrgan"

Remove-Item -Recurse -Force $Tmp
$size = (Get-ChildItem $Rt -Recurse -File | Measure-Object Length -Sum).Sum / 1GB
Write-Host ("runtime ready: {0:N2} GB" -f $size)
