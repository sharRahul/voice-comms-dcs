# Voice-Comms-DCS / Nimbus

Voice-Comms-DCS is a local-first Windows companion app for DCS World. It started as a safe voice-command-to-DCS-flag bridge and now includes **Nimbus**, a multilingual telemetry-aware AI wingman stack with WebRTC audio, HOTAS/keyboard push-to-talk, Whisper.cpp STT, local Ollama orchestration, Piper radio-effect TTS, a browser-based dashboard, and a zero-touch installer path.

```mermaid
flowchart LR
    A[Installer language selection] --> B[Dependency manager]
    B --> C[Ollama model]
    B --> D[Whisper.cpp model]
    B --> E[Piper voice]
    F[DCS smart installer] --> G[Saved Games DCS Scripts]
    G --> H[Export.lua backup + hooks]
    I[Dashboard language dropdown] --> J[Whisper language]
    J --> K[Nimbus intelligence]
    K --> L[Piper voice output]
    K --> M[DCS UDP command bridge]

flowchart LR
	L[Installer language selection] --> M[Whisper STT Local speech-to-text] --> N[Nimbus LLM orchestration + command handler] --> O[Piper TTS Radio voice output]
	P[DCS World dcs_telemetry.lua hook] --> Q[Telemetry parser UDP 10 Hz → JSON context] --> N[Nimbus LLM orchestration + command handler] --> R[VoiceBridge DCS mission flags]
```

## Supported languages

Nimbus supports these UI, STT/TTS routing, and AI response languages:

| Code | Language |
|---|---|
| `en` | English |
| `zh` | Chinese |
| `ko` | Korean |
| `fr` | French |
| `ru` | Russian |
| `es` | Spanish |

English can use English-only Whisper models such as `ggml-base.en.bin`. Chinese, Korean, French, Russian, and Spanish require multilingual Whisper weights such as `ggml-base.bin`.

Korean TTS note: the current Korean Piper-compatible voice is a community model, not from the official `rhasspy/piper-voices` tree. Review its upstream licence before commercial use.

## Automated setup

The Phase 4 installer is designed to handle the main setup steps automatically:

1. Detect DCS Saved Games folders, including moved Saved Games locations.
2. Copy `VoiceBridge.lua` and `dcs_telemetry.lua` into each discovered DCS `Scripts` folder.
3. Back up `Export.lua` before patching.
4. Add marked, uninstallable Voice-Comms-DCS hook blocks.
5. Download selected Ollama, Whisper.cpp, and Piper model files.
6. Install selected language UI files and model mappings.

Manual equivalent:

```powershell
voice-comms-dcs --install-lua --dcs-source-dir dcs_scripts
```

```powershell
voice-comms-dcs --setup-dependencies-ui --languages en fr es --ollama-model qwen2.5:0.5b --whisper-quality base
```

Uninstall equivalent:

```powershell
voice-comms-dcs --uninstall-lua
voice-comms-dcs --remove-dependencies --languages en zh ko fr ru es
```

## Local model profiles

Voice-Comms-DCS keeps safety-critical actions deterministic, so the LLM can stay small. Commands go through configured phrases and DCS flags, while telemetry questions are answered from JSON telemetry.

| Component | Minimum profile | Recommended low-load profile |
|---|---|---|
| Ollama LLM | `qwen2.5:0.5b` | `qwen2.5:1.5b` |
| Whisper STT | `tiny` / `tiny.en` | `base` / `base.en` |
| Piper TTS | language-specific low/medium voice | same |

Recommended English-only minimum:

```powershell
voice-comms-dcs --setup-dependencies-ui --languages en --ollama-model qwen2.5:0.5b --whisper-quality base
```

Recommended global six-language install:

```powershell
voice-comms-dcs --setup-dependencies-ui --languages en zh ko fr ru es --ollama-model qwen2.5:0.5b --whisper-quality base
```

## Dashboard workflow

Start the WebRTC bridge:

```powershell
voice-comms-dcs-webrtc `
  --config config\commands.json `
  --aircraft-profile config\aircraft_profiles\su57.json `
  --joystick-index 0 `
  --joystick-button 1 `
  --ptt-hotkey right_ctrl
```

The bridge prints a local dashboard URL at startup. Open that exact URL:

```text
Dashboard: http://127.0.0.1:8765/dashboard?token=<startup-token>
```

Dashboard, API, WebSocket, and WebRTC control routes require this token by default. The browser stores it in session storage and removes it from the visible URL after loading the dashboard. You can supply a stable token for a local session with `--dashboard-token`, but do not store real tokens in config files.

The dashboard provides:

- WebRTC microphone connection.
- HOTAS/keyboard PTT state.
- Language dropdown.
- Pilot/Nimbus conversation terminal.
- STT transcript and latency events.
- Fuel, altitude, airspeed, and G-load gauges.
- Current telemetry context window.

## Language switching

You can change language in the dashboard dropdown. The backend then updates:

- Whisper language code.
- Whisper model path, using multilingual weights for non-English where available.
- Piper voice model path.
- Nimbus local LLM language instruction.
- Deterministic telemetry answer language.

Manual launch example for Spanish:

```powershell
voice-comms-dcs-webrtc --language es --config config\commands.json
```

## DCS integration details

The smart installer searches for DCS folders under Saved Games, including users who moved Saved Games to another drive via Windows shell folder settings. It patches `Export.lua` using marked blocks:

```lua
-- BEGIN VOICE_COMMS_DCS_BRIDGE
-- END VOICE_COMMS_DCS_BRIDGE

-- BEGIN VOICE_COMMS_DCS_TELEMETRY
-- END VOICE_COMMS_DCS_TELEMETRY
```

Before patching an existing `Export.lua`, it creates:

```text
Export.lua.voice-comms-dcs.bak
```

DCS actions still use the safe command protocol:

```text
VCDCS|request_tanker|flag|5101|1
```

The Lua bridge validates the packet and sets user flags for mission-owned logic.

## Hardware and storage guidance

Approximate additional storage:

| Install type | Typical extra storage |
|---|---:|
| English-only minimum | ~700 MB to 1 GB |
| Six-language install | ~1.2 GB to 2 GB+ |
| Larger LLM / Whisper models | More than 2 GB |

Recommended runtime baseline:

- 32 GB RAM minimum; 64 GB preferred for DCS plus local AI.
- Modern 8-core CPU minimum; 12-core+ preferred.
- Keep telemetry at 10 Hz unless tested.
- Start with `qwen2.5:0.5b`; upgrade to `qwen2.5:1.5b` only if DCS remains smooth.

## Troubleshooting

### DCS folder not detected

```powershell
voice-comms-dcs --install-lua --saved-games "D:\Saved Games"
```

### Export.lua conflict

Run:

```powershell
voice-comms-dcs --uninstall-lua
```

Or restore:

```text
Export.lua.voice-comms-dcs.bak
```

### Model download interrupted

Run the same dependency command again. Whisper and Piper downloads use `.part` files and HTTP range resume when supported. Ollama pulls can be re-run and reuse already downloaded layers.

### Non-English STT does not work correctly

Install multilingual Whisper weights:

```powershell
voice-comms-dcs --setup-dependencies-ui --languages zh ko fr ru es --whisper-quality base --skip-ollama --skip-piper
```

Avoid `ggml-base.en.bin` for non-English speech.

### Piper voice missing

Install the selected language voice:

```powershell
voice-comms-dcs --setup-dependencies-ui --languages es --skip-ollama --skip-whisper
```

## Project layout

```text
voice-comms-dcs/
├── config/
│   ├── commands.example.json
│   ├── aircraft_profiles/
│   └── i18n/
├── dcs_scripts/
│   ├── VoiceBridge.lua
│   └── dcs_telemetry.lua
├── src/voice_comms_dcs/
│   ├── dcs_installer_utils.py
│   ├── dependency_manager.py
│   ├── dependency_setup_ui.py
│   ├── language_models.py
│   ├── nimbus_intelligence.py
│   ├── radio_voice.py
│   ├── stt_whisper_engine.py
│   ├── webrtc_bridge.py
│   └── web_ui/
├── build/
│   ├── build_exe.ps1
│   ├── setup_local_models.ps1
│   ├── setup_whisper.ps1
│   ├── pyinstaller.spec
│   └── voice-comms-dcs.iss
└── docs/
    ├── phase4_global_deployment.md
    ├── model_selection.md
    └── security_report.md
```

## Build and installer

Build the PyInstaller output:

```powershell
.\build\build_exe.ps1
```

Then compile:

```text
build\voice-comms-dcs.iss
```

The Inno Setup installer includes language model checkboxes and can run the Lua bridge installer and model downloader after installation.

## Security posture

Voice-Comms-DCS is local-first by default. The dashboard/WebRTC bridge binds to `127.0.0.1`, generates a startup token, and accepts browser origins only from `localhost` or `127.0.0.1` on the configured port unless extra origins are supplied with `--allowed-origin`.

LAN binding is refused unless `--allow-lan` is passed, and dashboard authentication must remain enabled for LAN/non-local hosts. `--disable-dashboard-auth` is intended only for local development on localhost. Do not expose `/dashboard`, `/ws`, `/api/live`, or dashboard API routes to the public internet.

## Roadmap

- Backend wiring for dashboard personality toggle.
- Browser UI polishing and aircraft-specific skins.
- Joystick profile presets for Warthog, Winwing, T16000M, Logitech, and Viper panels.
- SRS-specific audio injection path.
- Aircraft-specific RWR adapters.
- Signed installer and model checksum manifest.

## License

MIT License. See `LICENSE`.
