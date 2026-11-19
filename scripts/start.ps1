# Starts 3zT Agent: Ollama + the local server. The server opens the app window itself and
# shuts everything down when that window is closed.
. "$PSScriptRoot\common.ps1"
RefreshPath
Set-OllamaEnv
$url = "http://127.0.0.1:$Port"

# Already running? server.py itself asks the running copy to show its window, or replaces it when
# that copy runs older code (after an update).

# Ollama
if (-not (Up "http://127.0.0.1:11434/api/version")) {
  $o = OllamaExe
  if ($o) { Start-Process $o -ArgumentList "serve" -WindowStyle Hidden }
}

# Server (it opens the window)
$py = PythonW
if (-not $py) {
  Add-Type -AssemblyName PresentationFramework
  [System.Windows.MessageBox]::Show("Python was not found. Run install.bat first.", "3zT Agent") | Out-Null
  exit 1
}
$pyArgs = @("`"$Root\app\server.py`"")
if ((Split-Path $py -Leaf) -eq "pyw.exe") { $pyArgs = @("-3") + $pyArgs }
Start-Process $py -ArgumentList $pyArgs -WorkingDirectory "$Root\app" -WindowStyle Hidden
