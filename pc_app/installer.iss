; ============================================================
;  installer.iss - Inno Setup script for ESP8266 Fan Controller
;  ----------------------------------------------------------
;  Builds a Windows installer that:
;    - Installs the app to Program Files
;    - Creates Start Menu shortcuts
;    - Creates desktop shortcut (optional)
;    - Adds uninstaller
;    - Registers with Windows for "Open at startup" option
;
;  Compile with: ISCC.exe installer.iss
;  Output: dist\FanController-Setup-v1.0.0.exe
; ============================================================

#define MyAppName "ESP8266 Fan Controller"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "DIY"
#define MyAppExeName "FanController.exe"
#define MyAppSource "dist\FanController"

[Setup]
AppId={{B8F3E4A2-7C92-4D6E-9F1A-ESP8266FAN001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=FanController-Setup-v{#MyAppVersion}
SetupIconFile=icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
AppCopyright=Copyright (c) 2024

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"; Flags: checkedonce
Name: "startup"; Description: "Run at Windows startup"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
; Main executable + bundled deps
Source: "{#MyAppSource}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{group}\Game Mode ON"; Filename: "{app}\GameMode_ON.bat"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Game Mode OFF"; Filename: "{app}\GameMode_OFF.bat"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{commondesktop}\Game Mode ON"; Filename: "{app}\GameMode_ON.bat"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startup

[Run]
; Final step: launch app
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
