; 3zT Agent installer (Inno Setup 6). Built by .github/workflows/build.yml after build-runtime.ps1.
; Per-user install: no admin rights needed. The app, Python and every tool are inside the install folder;
; models are downloaded by the app itself on first use (Settings -> Setup & downloads).

#ifndef AppVersion
  #define AppVersion "2.0.0"
#endif

[Setup]
AppId={{8C6F2D4A-3A7B-4E15-9C1E-7A1B2C3D4E5F}
AppName=3zT Agent
AppVersion={#AppVersion}
AppPublisher=3zT
DefaultDirName={localappdata}\Programs\3zT Agent
DefaultGroupName=3zT Agent
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=3zT-Agent-Setup-{#AppVersion}
SetupIconFile=..\assets\3zT.ico
UninstallDisplayIcon={app}\assets\3zT.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\app\*"; DestDir: "{app}\app"; Excludes: "__pycache__,*.pyc"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs
Source: "..\runtime\*"; DestDir: "{app}\runtime"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[InstallDelete]
; old app code is replaced as a whole (removed modules must not linger)
Type: filesandordirs; Name: "{app}\app"

[Icons]
Name: "{autoprograms}\3zT Agent"; Filename: "{app}\runtime\python\pythonw.exe"; Parameters: """{app}\app\server.py"""; WorkingDir: "{app}\app"; IconFilename: "{app}\assets\3zT.ico"
Name: "{autodesktop}\3zT Agent"; Filename: "{app}\runtime\python\pythonw.exe"; Parameters: """{app}\app\server.py"""; WorkingDir: "{app}\app"; IconFilename: "{app}\assets\3zT.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\runtime\python\pythonw.exe"; Parameters: """{app}\app\server.py"""; WorkingDir: "{app}\app"; Description: "{cm:LaunchProgram,3zT Agent}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Get-CimInstance Win32_Process | Where-Object {{ $_.ExecutablePath -and $_.ExecutablePath.StartsWith('{app}', 'OrdinalIgnoreCase') } | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }"""; Flags: runhidden; RunOnceId: "StopApp"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\app"

[Code]
procedure StopRunningApp();
var
  Code: Integer;
  Dir: String;
begin
  Dir := ExpandConstant('{app}');
  Exec('powershell.exe',
    '-NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith(''' + Dir + ''', ''OrdinalIgnoreCase'') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"',
    '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopRunningApp();   { an open copy would lock runtime files }
  Result := '';
end;
