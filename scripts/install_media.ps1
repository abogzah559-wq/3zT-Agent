# Image + video generation models for ComfyUI (resumable; run again to continue a stopped download)
. "$PSScriptRoot\common.ps1"
$comfy = Get-Setting "comfy_dir" "$env:USERPROFILE\ComfyUI"
$models = Join-Path $comfy "models"
if (-not (Test-Path (Join-Path $comfy "main.py"))) {
  if (Test-Path (Join-Path $comfy "ComfyUI\main.py")) { $models = Join-Path $comfy "ComfyUI\models" }
  else {
    Say "ComfyUI not found in $comfy. Install ComfyUI (github.com/comfyanonymous/ComfyUI) or set its folder in the app settings." Red
    Read-Host "Press Enter"; exit 1
  }
}

function Resolve-HF($repo, $pattern) {
  try {
    $info = Invoke-RestMethod "https://huggingface.co/api/models/$repo" -TimeoutSec 30
    return ($info.siblings.rfilename | Where-Object { $_ -notmatch "/" -and $_ -match $pattern } | Select-Object -First 1)
  } catch { return $null }
}
function Get-Model($name, $repo, $file, $sub, $saveAs) {
  $dir = Join-Path $models $sub
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  if (-not $saveAs) { $saveAs = Split-Path $file -Leaf }
  $dest = Join-Path $dir $saveAs
  if ((Test-Path $dest) -and -not (Test-Path "$dest.part")) { Say "$name already downloaded" Green; return }
  Say "Downloading $name ..."
  if (Download "https://huggingface.co/$repo/resolve/main/$file" $dest) { Say "$name ready" Green }
  else { Say "$name failed. Run this file again to continue." Red }
}

Write-Host "3zT Agent - image & video models (about 20 GB total, once only)" -ForegroundColor Magenta
Get-Model "Realistic images: Juggernaut XL v9" "RunDiffusion/Juggernaut-XL-v9" "Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors" "checkpoints"
$an = Resolve-HF "cagliostrolab/animagine-xl-4.0" "opt\.safetensors$"
if (-not $an) { $an = Resolve-HF "cagliostrolab/animagine-xl-4.0" "\.safetensors$" }
if ($an) { Get-Model "Anime images: Animagine XL 4.0" "cagliostrolab/animagine-xl-4.0" $an "checkpoints" }
else { Say "Could not find the anime model on Hugging Face" Red }

$a = Read-Host "Also download the video model Wan 2.1 VACE 1.3B (~8 GB)? (y/n)"
if ($a -match "^[yY]") {
  $w = "Comfy-Org/Wan_2.1_ComfyUI_repackaged"
  Get-Model "Wan 2.1 VACE 1.3B" $w "split_files/diffusion_models/wan2.1_vace_1.3B_fp16.safetensors" "diffusion_models"
  Get-Model "UMT5 text encoder" $w "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" "text_encoders"
  Get-Model "Wan VAE" $w "split_files/vae/wan_2.1_vae.safetensors" "vae"
}
Say "Done." Green
Read-Host "Press Enter to exit"
