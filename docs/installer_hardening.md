# Installer hardening

## Runtime config policy

`config/commands.example.json` is the packaged template. `config/commands.json` is treated as a local, user-owned runtime file.

On first run, the CLI creates `config/commands.json` from `config/commands.example.json` only when the default local config path is used and the file does not already exist. Existing user config is not overwritten by this helper.

Explicit custom config paths continue to fail clearly when the file is missing.

## Packaging policy

PyInstaller and Inno Setup install `commands.example.json`, aircraft profiles, i18n data, joystick profiles, RWR/SRS configuration, docs, web UI files, and DCS Lua scripts.

They do not require or install a local `config/commands.json`, and they do not package build-only signing or model setup scripts as runtime files.

## Lua bridge consent

The installer Lua bridge task is unchecked by default. Selecting it installs the DCS Lua bridge after the installer has shown the task description.

Manual install:

```powershell
voice-comms-dcs --install-lua --dcs-source-dir dcs_scripts
```

Dry run:

```powershell
voice-comms-dcs --install-lua --dry-run --dcs-source-dir dcs_scripts
```

Manual uninstall:

```powershell
voice-comms-dcs --uninstall-lua
```

The installer must not change user DCS files unless the user explicitly selects the Lua bridge task or runs the CLI command themselves.
