; Voice-Comms-DCS Inno Setup template
; Build PyInstaller output first using build\build_exe.ps1.

#define MyAppName "Voice-Comms-DCS"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Rahul Sharma"
#define MyAppExeName "Voice-Comms-DCS.exe"

[Setup]
AppId={{A5F25599-8D4F-4A3E-90C0-VOICECOMMSDCS}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=..\LICENSE
OutputDir=..\build_output
OutputBaseFilename=Voice-Comms-DCS-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\Voice-Comms-DCS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\config\commands.example.json"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "..\dcs_scripts\VoiceBridge.lua"; DestDir: "{app}\dcs_scripts"; Flags: ignoreversion
Source: "..\dcs_scripts\Export.lua.append.example"; DestDir: "{app}\dcs_scripts"; Flags: ignoreversion
Source: "..\dcs_scripts\mission_trigger_example.lua"; DestDir: "{app}\dcs_scripts"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\architecture.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\security_and_limitations.md"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Documentation"; Filename: "{app}\README.md"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    Log('Voice-Comms-DCS installed. DCS Saved Games script installation remains manual in v0.1.');
  end;
end;
