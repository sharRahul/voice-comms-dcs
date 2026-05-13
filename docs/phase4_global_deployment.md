# Phase 4: Global Deployment and Zero-Touch Installer

## Purpose

Phase 4 prepares Voice-Comms-DCS / Nimbus for a global release. It adds multilingual STT/TTS routing, dashboard localization, automatic DCS Lua installation, resumable model downloads, and installer-level language selection.

Supported languages:

| Code | Language |
|---|---|
| `en` | English |
| `zh` | Chinese |
| `ko` | Korean |
| `fr` | French |
| `ru` | Russian |
| `es` | Spanish |

## Architecture changes

```mermaid
flowchart LR
    A[Installer language tasks] --> B[Dependency Manager]
    B --> C[Ollama /api/pull]
    B --> D[Whisper.cpp models]
    B --> E[Piper ONNX + JSON voices]
    A --> F[DCS Lua Smart Installer]
    F --> G[Saved Games DCS*/Scripts]
    F --> H[Export.lua backup + marked hooks]
    I[Dashboard language dropdown] --> J[/api/language]
    J --> K[WebRTC Bridge]
    K --> L[Whisper language code]
    K --> M[Piper voice mapping]
    K --> N[Nimbus response language]
```

## Language model routing

Language-specific model choices are centralized in:

```text
src/voice_comms_dcs/language_models.py
```

### Whisper.cpp

English can use English-only models:

```text
models/whisper/ggml-base.en.bin
```

Non-English languages require multilingual Whisper.cpp weights:

```text
models/whisper/ggml-base.bin
```

The WebRTC bridge automatically switches from English-only weights to multilingual weights when a non-English language is selected, unless the user explicitly provides `--whisper-model`.

### Piper TTS

Piper voices are mapped by language. Each voice requires both files:

```text
*.onnx
*.onnx.json
```

Current mappings:

| Language | Voice |
|---|---|
| English | `en_US-lessac-low` |
| Chinese | `zh_CN-huayan-x_low` |
| Korean | `piper-kss-korean` |
| French | `fr_FR-siwis-low` |
| Russian | `ru_RU-ruslan-medium` |
| Spanish | `es_ES-mls_9972-low` |

Korean note: the Korean voice is not from the official `rhasspy/piper-voices` tree. It is a Piper-compatible community model and should be reviewed for licensing before commercial distribution.

## Smart DCS Lua installer

Module:

```text
src/voice_comms_dcs/dcs_installer_utils.py
```

Compatibility entrypoint:

```text
src/voice_comms_dcs/install_lua_bridge.py
```

Commands:

```powershell
voice-comms-dcs --install-lua --dcs-source-dir dcs_scripts
voice-comms-dcs --uninstall-lua
```

The installer:

1. Detects likely Saved Games paths.
2. Checks Windows `User Shell Folders` and `Shell Folders` registry keys so moved Saved Games locations are handled.
3. Searches for `DCS`, `DCS.openbeta`, and other `DCS.*` folders.
4. Creates the `Scripts` folder if required.
5. Copies `VoiceBridge.lua` and `dcs_telemetry.lua`.
6. Backs up `Export.lua` before modifying it.
7. Appends marked hook blocks.
8. Can uninstall its own marked blocks and copied scripts.

Marked blocks:

```lua
-- BEGIN VOICE_COMMS_DCS_BRIDGE
-- END VOICE_COMMS_DCS_BRIDGE

-- BEGIN VOICE_COMMS_DCS_TELEMETRY
-- END VOICE_COMMS_DCS_TELEMETRY
```

## Dependency manager

Module:

```text
src/voice_comms_dcs/dependency_manager.py
```

Compatibility entrypoint:

```text
src/voice_comms_dcs/setup_dependencies.py
```

Progress UI:

```text
src/voice_comms_dcs/dependency_setup_ui.py
```

Examples:

```powershell
voice-comms-dcs --setup-dependencies-ui --languages en fr es --ollama-model qwen2.5:0.5b --whisper-quality base
```

```powershell
voice-comms-dcs --setup-dependencies --languages en zh ko fr ru es --ollama-model qwen2.5:0.5b --whisper-quality base
```

```powershell
voice-comms-dcs --remove-dependencies --languages en zh ko fr ru es
```

### Resume behavior

Whisper and Piper downloads use partial `.part` files and HTTP `Range` requests. If the server supports range requests, interrupted downloads resume from the partial file. If the server ignores range requests, the downloader safely restarts the file.

Ollama model pulls use Ollama's `/api/pull` endpoint with streaming progress. If an Ollama pull is interrupted, re-running the same pull resumes or reuses already downloaded layers on the Ollama side.

## Dashboard localization

Files:

```text
config/i18n/en.json
config/i18n/zh.json
config/i18n/ko.json
config/i18n/fr.json
config/i18n/ru.json
config/i18n/es.json
```

Routes:

```text
GET  /api/i18n/{language}
POST /api/language
```

The dashboard language dropdown:

1. Loads localized labels.
2. Tells the backend to switch language.
3. Updates Whisper language code.
4. Updates Piper voice model path.
5. Updates Nimbus LLM language instruction.

## Installer behavior

The Inno Setup template now provides tasks for:

- Desktop shortcut.
- Automatic DCS Lua bridge installation.
- Model download after install.
- Language model selection for English, Chinese, Korean, French, Russian, and Spanish.

Post-install actions:

```text
Voice-Comms-DCS.exe --install-lua --dcs-source-dir "{app}\dcs_scripts"
Voice-Comms-DCS.exe --setup-dependencies-ui --languages <selected> --ollama-model qwen2.5:0.5b --whisper-quality base
```

Uninstall actions:

```text
Voice-Comms-DCS.exe --uninstall-lua
Voice-Comms-DCS.exe --remove-dependencies --languages en zh ko fr ru es
```

## Storage expectations

Approximate storage varies by selected languages and model quality.

| Component | Single-language English | Six-language install |
|---|---:|---:|
| Ollama `qwen2.5:0.5b` | ~400 MB | ~400 MB |
| Whisper base models | ~150 MB English-only | ~300 MB English + multilingual |
| Piper voices | ~60 to 100 MB | ~400 to 800 MB depending voices |
| Total additional storage | ~700 MB to 1 GB | ~1.2 GB to 2 GB+ |

Higher-quality LLMs or larger Whisper models will increase this significantly.

## Troubleshooting

### DCS folder not detected

Run:

```powershell
voice-comms-dcs --install-lua
```

If no DCS folders are found, specify Saved Games manually:

```powershell
voice-comms-dcs --install-lua --saved-games "D:\Saved Games"
```

### Export.lua broken or conflicts with another tool

The installer creates a backup:

```text
Export.lua.voice-comms-dcs.bak
```

Remove the marked Voice-Comms-DCS blocks or run:

```powershell
voice-comms-dcs --uninstall-lua
```

### Model download interrupted

Re-run the same dependency command. Partial files are reused where HTTP range resume is supported.

### Ollama not running

Start Ollama first, then run:

```powershell
ollama pull qwen2.5:0.5b
```

### Non-English STT returns English text

Use the multilingual Whisper model:

```text
models/whisper/ggml-base.bin
```

Do not use `ggml-base.en.bin` for Chinese, Korean, French, Russian, or Spanish.

### Korean TTS licensing

The current Korean voice is a community Piper-compatible model, not an official Piper voice from the `rhasspy/piper-voices` tree. Review its upstream licence before commercial use.

## Verification checklist

- DCS Saved Games path found through registry or fallback.
- `VoiceBridge.lua` copied into each discovered DCS Scripts folder.
- `dcs_telemetry.lua` copied into each discovered DCS Scripts folder.
- `Export.lua` backed up before patching.
- `Export.lua` hooks are marked and uninstallable.
- Selected language models download successfully.
- Interrupted downloads resume or restart safely.
- Dashboard language dropdown changes UI labels.
- Nimbus replies in selected language.
- Whisper uses multilingual weights for non-English languages.
- Lua files and command strings remain UTF-8.
