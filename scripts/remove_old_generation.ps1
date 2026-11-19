# Removes the OLD image/video generation setup of 3zT Agent v1.0-1.1 (a separate ComfyUI with SDXL + Wan 2.1
# models and the 3zT-*.bat helper files). v1.2+ generates through FreeVideo instead.
# Nothing is removed without your confirmation. FreeVideo's own folders are never touched.
. "$PSScriptRoot\common.ps1"

function SizeOf($p) {
  try { (Get-ChildItem -LiteralPath $p -Recurse -Force -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum } catch { 0 }
}
function Gb($b) { "{0:N1} GB" -f ($b / 1GB) }

$fvHome = Get-Setting "freevideo_home" (Join-Path $env:LOCALAPPDATA "FreeVideo")
$protect = @($fvHome, (Join-Path $env:LOCALAPPDATA "FreeVideo"), (Join-Path $env:LOCALAPPDATA "FreeVideo-launcher")) |
  ForEach-Object { try { [IO.Path]::GetFullPath($_).TrimEnd('\') } catch { $_ } }

$cands = @((Get-Setting "comfy_dir" ""), (Join-Path $env:USERPROFILE "ComfyUI"), (Join-Path $env:USERPROFILE "Desktop\ComfyUI"),
           "C:\ComfyUI") | Where-Object { $_ } | Select-Object -Unique
$markers = "3zT-2-start.bat", "_3zt_fast_download.py", "3zt_comfy_log.txt", "3zT-1-download-models.bat", "3zT-video-outpaint.json"
$oldModels = "Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors", "animagine-xl-4.0-opt.safetensors", "wan2.1_vace_1.3B_fp16.safetensors"

$targets = @()
foreach ($c in $cands) {
  if (-not (Test-Path -LiteralPath $c)) { continue }
  $full = [IO.Path]::GetFullPath($c).TrimEnd('\')
  if ($protect | Where-Object { $full -like "$_*" -or $_ -like "$full*" }) { continue }
  $ours = $markers | Where-Object { Test-Path -LiteralPath (Join-Path $full $_) }
  if (-not $ours) {
    $ours = Get-ChildItem -LiteralPath $full -Recurse -Force -File -Depth 3 -ErrorAction SilentlyContinue |
      Where-Object { $oldModels -contains $_.Name } | Select-Object -First 1
  }
  if ($ours -and -not ($targets -contains $full)) { $targets += $full }
}

Say "Old generation setup (separate ComfyUI + SDXL / Wan 2.1)"
if (-not $targets) {
  Write-Host "Nothing found. The old setup is already gone." -ForegroundColor Green
  Read-Host "`nPress Enter to close"
  exit 0
}
$total = 0
foreach ($t in $targets) {
  $s = SizeOf $t; $total += $s
  Write-Host ("  {0}   ({1})" -f $t, (Gb $s)) -ForegroundColor Yellow
  foreach ($d in "models\checkpoints", "models\diffusion_models", "models\text_encoders", "models\vae", "venv", "output") {
    $p = Join-Path $t $d
    if (Test-Path -LiteralPath $p) { Write-Host ("      {0,-26} {1}" -f $d, (Gb (SizeOf $p))) }
  }
}
Write-Host ("`nTotal: {0}" -f (Gb $total)) -ForegroundColor Cyan
Write-Host "Your own files in the agent workspace and FreeVideo are NOT touched."
Write-Host ""
Write-Host "  [R] Move to the Recycle Bin (can be restored; very large folders may not fit in the bin)"
Write-Host "  [D] Delete permanently (frees the disk space right away)"
Write-Host "  [N] Cancel"
$a = Read-Host "Choose R / D / N"
if ($a -notmatch '^[rRdD]') { Say "Cancelled. Nothing was removed." Green; Read-Host "Press Enter to close"; exit 0 }

# stop anything still running from these folders (an old ComfyUI)
foreach ($t in $targets) {
  Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { ($_.ExecutablePath -and $_.ExecutablePath -like "$t*") -or ($_.CommandLine -and $_.CommandLine -like "*$t*") } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}
Start-Sleep -Seconds 1

Add-Type -AssemblyName Microsoft.VisualBasic
$failed = @()
foreach ($t in $targets) {
  Say "Removing $t"
  try {
    if ($a -match '^[rR]') {
      [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory($t, 'OnlyErrorDialogs', 'SendToRecycleBin')
    } else {
      Remove-Item -LiteralPath $t -Recurse -Force -ErrorAction Stop
    }
  } catch { $failed += $t; Write-Host "  Could not remove: $($_.Exception.Message)" -ForegroundColor Red }
}

if ($failed) { Say "Some folders are still there (a file may be open). Close other programs and run this again." Red }
else { Say "Done. The old generation setup is removed. Use install-freevideo.bat for the new one." Green }
Read-Host "Press Enter to close"
