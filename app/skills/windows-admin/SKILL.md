---
name: windows-admin
description: Windows system tasks - installed apps, install/uninstall with winget, startup programs, processes, disk space, network/IP/Wi-Fi, drivers/GPU info, services, scheduled tasks, environment variables, fixing common problems. Arabic triggers - ثبت برنامج، حذف برنامج، بدء التشغيل، المساحة، الشبكة، الواي فاي، العمليات، تسريع الجهاز، مشكلة في ويندوز.
---
# Windows admin (PowerShell via run_command)

- Find/install apps: `winget search NAME` → `winget install -e --id ID --accept-package-agreements --accept-source-agreements`
- Installed apps: `winget list` ; uninstall needs user approval: `winget uninstall -e --id ID`
- Startup apps: `Get-CimInstance Win32_StartupCommand | Select Name,Command,Location`
- Heavy processes: `system_info` tool, or `Get-Process | Sort CPU -Desc | Select -First 15 Name,Id,CPU,@{n='MB';e={[int]($_.WS/1MB)}}`
- Disk space: `system_info` tool; cleanup temp: `Remove-Item "$env:TEMP\*" -Recurse -Force -ErrorAction SilentlyContinue` (ask first)
- Network: `Get-NetIPConfiguration`, `Test-NetConnection google.com`, Wi-Fi password: `netsh wlan show profile name="NAME" key=clear`
- GPU/driver: `nvidia-smi`, `Get-CimInstance Win32_VideoController | Select Name,DriverVersion`
- Services: `Get-Service | Where Status -eq Running`
- Env vars (user): `[Environment]::SetEnvironmentVariable("NAME","VALUE","User")`
- Always explain what a command will change before running anything that modifies the system.
