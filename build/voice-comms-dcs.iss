; Voice-Comms-DCS Inno Setup template
; Build PyInstaller output first using build\build_exe.ps1.

#define MyAppName "Voice-Comms-DCS"
#define MyAppVersion "0.4.0"
#define MyAppPublisher "Rahul Sharma"
#define MyAppExeName "Voice-Comms-DCS.exe"

[Setup]
AppId={{A5F25599-8D4F-4A3E-90C0-0D01510308DC}}
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
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "installlua"; Description: "Install DCS Lua bridge now. This modifies Saved Games Scripts\Export.lua after creating a backup; you can also run it later from the CLI."; GroupDescription: "DCS integration:"; Flags: unchecked
Name: "downloadmodels"; Description: "Download local AI models after installation"; GroupDescription: "Local AI models:"; Flags: checkedonce
Name: "lang\en"; Description: "English"; GroupDescription: "Install language models:"; Flags: checkedonce
Name: "lang\zh"; Description: "Chinese"; GroupDescription: "Install language models:"
Name: "lang\ko"; Description: "Korean"; GroupDescription: "Install language models:"
Name: "lang\fr"; Description: "French"; GroupDescription: "Install language models:"
Name: "lang\ru"; Description: "Russian"; GroupDescription: "Install language models:"
Name: "lang\es"; Description: "Spanish"; GroupDescription: "Install language models:"

[Files]
Source: "..\dist\Voice-Comms-DCS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\config\commands.example.json"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "..\config\aircraft_profiles\*"; DestDir: "{app}\config\aircraft_profiles"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\config\i18n\*"; DestDir: "{app}\config\i18n"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\config\joystick_profiles\*"; DestDir: "{app}\config\joystick_profiles"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\config\rwr\*"; DestDir: "{app}\config\rwr"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\config\srs\*"; DestDir: "{app}\config\srs"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\src\voice_comms_dcs\web_ui\*"; DestDir: "{app}\voice_comms_dcs\web_ui"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dcs_scripts\Export.lua"; DestDir: "{app}\dcs_scripts"; Flags: ignoreversion
Source: "..\dcs_scripts\VoiceBridge.lua"; DestDir: "{app}\dcs_scripts"; Flags: ignoreversion
Source: "..\dcs_scripts\dcs_telemetry.lua"; DestDir: "{app}\dcs_scripts"; Flags: ignoreversion
Source: "..\dcs_scripts\Export.lua.append.example"; DestDir: "{app}\dcs_scripts"; Flags: ignoreversion
Source: "..\dcs_scripts\mission_trigger_example.lua"; DestDir: "{app}\dcs_scripts"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\architecture.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\phase2_conversational_cockpit.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\phase3_frontend_high_fidelity.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\phase4_global_deployment.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\model_selection.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\runtime_benchmark_tuning.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\security_report.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\installer_roadmap.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\security_and_limitations.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\developer_setup.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\installer_hardening.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\release_signing.md"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Dashboard"; Filename: "http://127.0.0.1:8765/dashboard"
Name: "{group}\Documentation"; Filename: "{app}\README.md"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--install-lua --dcs-source-dir ""{app}\dcs_scripts"""; WorkingDir: "{app}"; Description: "Install DCS Lua bridge"; Flags: runhidden; Tasks: installlua
Filename: "{app}\{#MyAppExeName}"; Parameters: "--setup-dependencies-ui --languages {code:SelectedLanguageArgs} --ollama-model qwen2.5:0.5b --whisper-quality base"; WorkingDir: "{app}"; Description: "Download selected local AI models"; Flags: postinstall skipifsilent; Tasks: downloadmodels
Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--uninstall-lua"; WorkingDir: "{app}"; Flags: runhidden
Filename: "{app}\{#MyAppExeName}"; Parameters: "--remove-dependencies --languages en zh ko fr ru es"; WorkingDir: "{app}"; Flags: runhidden

[Code]
function SelectedLanguageArgs(Param: String): String;
begin
  Result := '';
  if WizardIsTaskSelected('lang\en') then Result := Result + ' en';
  if WizardIsTaskSelected('lang\zh') then Result := Result + ' zh';
  if WizardIsTaskSelected('lang\ko') then Result := Result + ' ko';
  if WizardIsTaskSelected('lang\fr') then Result := Result + ' fr';
  if WizardIsTaskSelected('lang\ru') then Result := Result + ' ru';
  if WizardIsTaskSelected('lang\es') then Result := Result + ' es';
  if Result = '' then Result := ' en';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    Log('Voice-Comms-DCS installed. Lua bridge installation is opt-in; model downloader, RWR/SRS configs, and benchmark tooling have been configured.');
    Log('Selected languages: ' + SelectedLanguageArgs(''));
  end;
end;
