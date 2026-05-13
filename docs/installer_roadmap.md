# Installer Roadmap

## Goal

Package Voice-Comms-DCS as a normal Windows application that installs the desktop app, example configuration, documentation, and optional DCS Lua helper files.

## Recommended packaging stack

For the Python version:

1. PyInstaller creates the runnable Windows application folder.
2. Inno Setup wraps that folder into a standard installer.
3. A later release can add code signing and automatic update checks.

Alternative future stack:

- Nuitka for a more compiled-style Python distribution.
- C#/.NET desktop application with WiX or Visual Studio Installer Projects if the app is rewritten in C#.

## Local build flow

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
.\build\build_exe.ps1
```

Expected output:

```text
dist/Voice-Comms-DCS/Voice-Comms-DCS.exe
```

## Inno Setup flow

1. Install Inno Setup.
2. Build the app with PyInstaller first.
3. Open `build/voice-comms-dcs.iss` in Inno Setup Compiler.
4. Compile the installer.
5. Test installation on a clean Windows user profile.

## Installer contents

The installer should include:

- `Voice-Comms-DCS.exe`
- `config/commands.example.json`
- `dcs_scripts/VoiceBridge.lua`
- `dcs_scripts/Export.lua.append.example`
- `dcs_scripts/mission_trigger_example.lua`
- `README.md`
- `docs/architecture.md`
- `docs/security_and_limitations.md`

## Installer tasks to add later

The first installer template should avoid writing directly into DCS folders without user consent. Later versions can add optional tasks:

- Locate `%USERPROFILE%\Saved Games\DCS\Scripts`.
- Copy `VoiceBridge.lua` into the Scripts folder.
- Append the Export.lua snippet only after creating a backup.
- Create `commands.json` from the example if it does not already exist.
- Create Start Menu shortcuts.
- Add an uninstall action that removes only files created by Voice-Comms-DCS.

## Release checklist

Before publishing a release:

- Run the GUI locally.
- Test `--test-phrase "request tanker"`.
- Confirm UDP is received by DCS or a local UDP listener.
- Confirm the Lua bridge loads from Saved Games.
- Confirm user flags are set in a test mission.
- Build PyInstaller output.
- Build Inno Setup installer.
- Install on a fresh Windows profile.
- Document known limitations in the release notes.

## Code signing

Unsigned Windows executables can trigger SmartScreen warnings. For public releases, use an Authenticode certificate and sign:

- The PyInstaller executable.
- The installer executable.

Code signing is not required for local development, but it is strongly recommended before sharing widely.
