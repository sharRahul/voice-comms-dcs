# Voice-Comms-DCS / Nimbus — User Manual

**Version 0.4.0**

---

## Table of contents

1. [Overview](#overview)
2. [System requirements](#system-requirements)
3. [GUI installer wizard](#gui-installer-wizard)
4. [Nimbus Launcher](#nimbus-launcher)
5. [Installation (CLI / advanced)](#installation-cli--advanced)
   - [Step 1 — Install Python and base package](#step-1--install-python-and-base-package)
   - [Step 2 — Download AI models](#step-2--download-ai-models)
   - [Step 3 — Install the DCS Lua bridge](#step-3--install-the-dcs-lua-bridge)
   - [Step 4 — Configure voice commands](#step-4--configure-voice-commands)
6. [Starting the dashboard](#starting-the-dashboard)
7. [Using the dashboard](#using-the-dashboard)
   - [Connecting the microphone](#connecting-the-microphone)
   - [Push-to-talk](#push-to-talk)
   - [Language switching](#language-switching)
   - [Conversation log](#conversation-log)
   - [Telemetry gauges](#telemetry-gauges)
   - [Aircraft skins](#aircraft-skins)
8. [Voice commands](#voice-commands)
   - [How command matching works](#how-command-matching-works)
   - [Defining commands](#defining-commands)
   - [Testing commands](#testing-commands)
9. [Aircraft profiles](#aircraft-profiles)
10. [Command-line reference](#command-line-reference)
    - [voice-comms-dcs-installer](#voice-comms-dcs-installer)
    - [voice-comms-dcs-launcher](#voice-comms-dcs-launcher)
    - [voice-comms-dcs](#voice-comms-dcs)
    - [voice-comms-dcs-webrtc](#voice-comms-dcs-webrtc)
11. [Configuration file reference](#configuration-file-reference)
12. [Environment variables](#environment-variables)
13. [Model selection guide](#model-selection-guide)
14. [SRS integration](#srs-integration)
15. [RWR adapters](#rwr-adapters)
16. [DCS Lua bridge details](#dcs-lua-bridge-details)
17. [Security](#security)
18. [Troubleshooting](#troubleshooting)
19. [Uninstalling](#uninstalling)

---

## Overview

Voice-Comms-DCS turns spoken phrases into DCS mission flag commands. Say "request tanker" and DCS sets user flag 5101 — no keyboard required. The same audio pipeline feeds **Nimbus**, a local AI wingman that reads your aircraft telemetry and responds in a tactical brevity style.

Everything runs locally:

| Component | What it does |
|-----------|-------------|
| **Whisper.cpp** | Speech-to-text (microphone → transcript) |
| **Command matcher** | Matches transcript against configured phrases — deterministic, no AI |
| **VoiceBridge.lua** | Receives UDP commands and sets DCS user flags |
| **dcs_telemetry.lua** | Streams aircraft state to Nimbus at 10 Hz |
| **Ollama** | Local LLM for conversational wingman responses |
| **Piper** | Text-to-speech with a radio bandpass filter |
| **Dashboard** | Browser UI for microphone, gauges, settings, and conversation |

The command path (speech → flag) is fully deterministic and never routes through the LLM. Ollama handles only free-form wingman questions. If Ollama is unavailable, voice commands continue working normally.

---

## System requirements

- **OS:** Windows 10 or Windows 11 (64-bit)
- **RAM:** 32 GB minimum; 64 GB recommended (DCS World and local AI run concurrently)
- **CPU:** 8-core modern CPU minimum; 12-core+ recommended
- **Disk:** ~1–2 GB for the minimum English install; up to ~3 GB for a six-language install with larger models
- **Python:** 3.11 or later (if running from source)
- **DCS World:** any version that supports Export.lua hooks

---

## GUI installer wizard

The quickest way to get set up is the graphical installer wizard. Run it from the packaged `.exe` shortcut, or via:

```powershell
voice-comms-dcs-installer
```

The wizard walks through seven steps:

| Step | What happens |
|------|-------------|
| **Welcome** | System requirement checks (Python, RAM, disk, DCS World) |
| **Licence** | MIT licence — must accept to continue |
| **Install location** | Choose the folder; live disk-space indicator turns amber if space is tight |
| **Languages & models** | Tick the languages you fly in; pick Ollama model size and Whisper quality; download size estimate updates in real time |
| **DCS bridge** | Detects DCS Saved Games folders; tick each installation target; skip if not using DCS yet |
| **Progress** | Downloads models and installs the Lua bridge in the background; per-component progress bars; full log visible |
| **Complete** | Summary of what was installed; **Launch** button opens the Nimbus Launcher |

Interrupted installs resume from where they stopped. You can re-run the wizard at any time to add languages or upgrade models.

---

## Nimbus Launcher

After installation, use the **Nimbus Launcher** as your day-to-day control panel:

```powershell
voice-comms-dcs-launcher
```

### Launcher features

- **Status cards** — shows live status for the WebRTC bridge, Ollama LLM, and DCS connection (green = running, amber = starting, red = stopped/unreachable).
- **Start / Stop bridge** — one-click toggle for `voice-comms-dcs-webrtc`. Logs appear in the activity panel.
- **Open Dashboard** — opens the browser dashboard at the current session URL.
- **System tray** — minimises to the system tray; right-click for Open / Show-Hide / Quit. The tray icon persists so the bridge stays running in the background.
- **Quick settings** — personality style, language, and HOTAS preset without opening the full dashboard.
- **Minimize to tray on close** — configurable; the bridge keeps running until you choose Quit from the tray menu.

---

## Installation (CLI / advanced)

### Step 1 — Install Python and base package

If using the packaged installer (`.exe`), run the setup wizard described above. The wizard handles Python and dependency setup automatically.

If installing from source:

```powershell
python -m pip install -e .
```

### Step 2 — Download AI models

Use the dependency UI to download Ollama, Whisper, and Piper models for your chosen languages:

```powershell
# English-only (recommended starting point)
voice-comms-dcs --setup-dependencies-ui --languages en --ollama-model qwen2.5:0.5b --whisper-quality base

# Six-language install
voice-comms-dcs --setup-dependencies-ui --languages en zh ko fr ru es --ollama-model qwen2.5:0.5b --whisper-quality base
```

The UI shows per-model download progress and verifies SHA-256 checksums. Interrupted downloads resume automatically using HTTP range requests.

**Storage estimates:**

| Languages | Whisper quality | Approximate size |
|-----------|----------------|-----------------|
| English only | `base` | ~700 MB – 1 GB |
| Six languages | `base` (multilingual) | ~1.2 GB – 2 GB |
| With `qwen2.5:1.5b` LLM | any | +~600 MB |

### Step 3 — Install the DCS Lua bridge

```powershell
voice-comms-dcs --install-lua
```

The installer:

1. Scans for DCS Saved Games folders (including non-default drive locations).
2. Copies `VoiceBridge.lua` and `dcs_telemetry.lua` into each `Scripts/` folder.
3. Backs up your existing `Export.lua` as `Export.lua.voice-comms-dcs.bak`.
4. Appends clearly marked hook blocks to `Export.lua`.

To preview without modifying any files:

```powershell
voice-comms-dcs --install-lua --dry-run
```

To target a non-default Saved Games location:

```powershell
voice-comms-dcs --install-lua --saved-games "D:\Saved Games"
```

### Step 4 — Configure voice commands

Copy the example config and edit it:

```powershell
copy config\commands.example.json config\commands.json
```

Open `config\commands.json` and define your commands. See [Voice commands](#voice-commands) for the full schema.

---

## Starting the dashboard

```powershell
voice-comms-dcs-webrtc --config config\commands.json
```

The bridge prints a dashboard URL at startup:

```text
Dashboard: http://127.0.0.1:8765/dashboard?token=<startup-token>
```

Open that exact URL in your browser. The token is a per-session secret; the browser stores it automatically and removes it from the visible address bar after loading.

Common launch options:

```powershell
# With a specific aircraft profile and HOTAS button
voice-comms-dcs-webrtc `
  --config config\commands.json `
  --aircraft-profile config\aircraft_profiles\f18.json `
  --joystick-index 0 `
  --joystick-button 1 `
  --ptt-hotkey right_ctrl

# Spanish language, right-Shift PTT
voice-comms-dcs-webrtc --config config\commands.json --language es --ptt-hotkey right_shift

# Larger LLM model
voice-comms-dcs-webrtc --config config\commands.json --ollama-model qwen2.5:1.5b
```

---

## Using the dashboard

### Connecting the microphone

Click **Connect mic** in the dashboard. Your browser will ask for microphone permission — grant it. The WebRTC stream goes directly to the local Whisper engine; no audio leaves your machine.

The PTT indicator turns green when the push-to-talk key is held.

### Push-to-talk

Hold the configured PTT key or joystick button to activate the microphone. Release to trigger Whisper transcription. A short grace period (300 ms by default) prevents accidental cutoffs.

Default PTT key: `right_ctrl`

Configure in `commands.json`:

```json
"push_to_talk": {
  "hotkey": "right_shift",
  "release_grace_ms": 400,
  "pre_roll_ms": 500,
  "max_context_ms": 15000
}
```

Or override at launch:

```powershell
voice-comms-dcs-webrtc --ptt-hotkey right_shift --joystick-index 0 --joystick-button 2
```

### Language switching

Use the language dropdown in the dashboard. Switching language updates the Whisper model path, STT language code, Piper voice, and Nimbus LLM instruction simultaneously. The change takes effect on the next PTT press.

The installed language list comes from `language.installed` in your `commands.json`. Only languages downloaded in Step 2 will appear.

### Conversation log

The chat log shows the bidirectional exchange between you and Nimbus as speech bubbles:

- **Orange bubble (right)** — your transcribed speech (PILOT)
- **Blue bubble (left)** — Nimbus responses, with a command-intent badge when a DCS flag was set
- **Yellow monospace** — system events (connected, PTT preset loaded)
- **Red** — errors (mic permission denied, auth failure)

Type text directly into the input field at the bottom to send a test phrase without using PTT.

### Telemetry gauges

When DCS is running and `dcs_telemetry.lua` is active, the sidebar shows live arc gauges for:

| Gauge | Range | Colour |
|-------|-------|--------|
| FUEL kg | 0 – 10 000 kg | Orange (DCS accent) |
| ALT ft | 0 – 50 000 ft | Sky blue |
| IAS kt | 0 – 700 kt | Orange |
| G LOAD | 0 – 9 g | Red |

Below the gauges: **HDG** (heading in degrees), **GEAR** (UP/DN), **FLAPS** (%).

The telemetry age badge on the card header turns amber when the last packet is more than 2 seconds old.

If DCS is not running, gauges show `–` and Nimbus answers without aircraft context.

### Aircraft skins

Select an aircraft in the **Aircraft skin** dropdown in the top navigation bar. Each skin changes the accent colour scheme to match the airframe:

| Skin | Accent | Secondary |
|------|--------|-----------|
| Default | Orange | Sky blue |
| F-16 Viper | Orange | Cyan |
| F/A-18 Hornet | Orange | Blue |
| F-15 Eagle | Orange | Periwinkle |
| Su-27 Flanker | Orange | Red |
| MiG-29 Fulcrum | Orange | Pink |
| Su-57 Felon | Orange | Sky blue |
| F-22 Raptor | Orange | Violet |

The skin preference is saved to `localStorage` and restored on next visit.

---

## Voice commands

### How command matching works

Voice-Comms-DCS uses a two-stage matching pipeline:

1. **Exact match** — normalised transcript matches a configured phrase exactly (confidence 1.0).
2. **Fuzzy match** — SequenceMatcher + token overlap scoring. A command is dispatched only if confidence ≥ `matching.min_confidence` (default `0.78`).

Matched commands are dispatched immediately via UDP to VoiceBridge.lua, which sets the configured DCS user flag. No LLM call is made.

Unmatched transcripts are routed to Nimbus (Ollama) for a conversational response.

### Defining commands

Commands live in `config/commands.json` under the `"commands"` array:

```json
{
  "commands": [
    {
      "id": "request_tanker",
      "description": "Request refuelling from the tanker",
      "phrases": [
        "request tanker",
        "tanker request",
        "texaco rejoin",
        "send the tanker"
      ],
      "action": {
        "type": "flag",
        "flag": 5101,
        "value": 1
      }
    },
    {
      "id": "gear_down",
      "description": "Lower landing gear",
      "phrases": ["gear down", "lower the gear", "drop gear"],
      "action": {
        "type": "flag",
        "flag": 5110
      }
    }
  ]
}
```

**Action types:**

| Type | Required fields | Description |
|------|----------------|-------------|
| `flag` | `flag` (int) | Sets a DCS user flag. `value` defaults to `1`. |

**Tips for good phrases:**

- Add natural speech variations — people say "request tanker", "send tanker", and "texaco" for the same thing.
- Avoid very short phrases (fewer than two words) — they match too broadly.
- Use the `--test-phrase` tool to verify confidence before committing.
- Confidence threshold can be lowered in `matching.min_confidence` if legitimate phrases are being missed.

### Testing commands

Test any phrase without launching DCS:

```powershell
voice-comms-dcs --config config\commands.json --test-phrase "request tanker"
```

Output:

```text
Matched request_tanker confidence=1.00 payload=flag:5101=1
```

If no command matches:

```text
No match: confidence 0.61 below threshold 0.78
```

---

## Aircraft profiles

Aircraft profiles give Nimbus context about the aircraft it is supporting — role, callsign, brevity style, and reserved flag ranges.

Profiles live in `config/aircraft_profiles/`. Load one with `--aircraft-profile`:

```powershell
voice-comms-dcs-webrtc --config config\commands.json --aircraft-profile config\aircraft_profiles\su57.json
```

**Available profiles:**

| File | Aircraft | Role |
|------|----------|------|
| `default.json` | Generic | AI wingman and radio assistant |
| `su57.json` | Sukhoi Su-57 / Su-57M | Tactical systems assistant |

**Profile schema:**

```json
{
  "id": "f18",
  "display_name": "F/A-18C Hornet",
  "role": "AI wingman and tactical systems assistant",
  "callsign": "Nimbus",
  "brevity_style": "short tactical fighter brevity",
  "reserved_voice_flags": [5100, 5199],
  "notes": "Keep responses under ten words in combat mode."
}
```

Create your own profile by copying `default.json` and editing the fields. The `reserved_voice_flags` field is informational — it describes which DCS flag numbers your commands use.

---

## Command-line reference

### voice-comms-dcs-installer

Opens the 7-step graphical setup wizard.

```text
voice-comms-dcs-installer
```

No arguments. All options are configured interactively. Re-running the wizard is safe — it will not overwrite models already present unless you change the quality tier.

### voice-comms-dcs-launcher

Opens the Nimbus Launcher control panel.

```text
voice-comms-dcs-launcher
```

No arguments. Launcher settings (tray preference, last config path) are stored in the OS settings store (`QSettings`).

### voice-comms-dcs

Main CLI for installation, setup, and utilities.

```text
voice-comms-dcs [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--config PATH` | `config/commands.json` | Path to commands config file |
| `--install-lua` | — | Install Lua bridge into DCS Saved Games |
| `--uninstall-lua` | — | Remove Lua bridge from DCS Saved Games |
| `--dry-run` | — | Preview Lua install without modifying files |
| `--dcs-source-dir DIR` | `dcs_scripts` | Source directory for Lua files |
| `--saved-games PATH` | auto-detect | Override DCS Saved Games location |
| `--setup-dependencies` | — | Download models (non-interactive) |
| `--setup-dependencies-ui` | — | Download models (GUI) |
| `--remove-dependencies` | — | Remove downloaded model files |
| `--languages CODES…` | — | Language codes: `en zh ko fr ru es` |
| `--ollama-model MODEL` | `qwen2.5:0.5b` | Ollama model to install |
| `--whisper-quality TIER` | `base` | Whisper quality: `tiny` or `base` |
| `--skip-ollama` | — | Skip Ollama during dependency setup |
| `--skip-whisper` | — | Skip Whisper during dependency setup |
| `--skip-piper` | — | Skip Piper during dependency setup |
| `--test-phrase TEXT` | — | Test a phrase against configured commands |
| `--benchmark` | — | Run local runtime benchmark |
| `--benchmark-samples N` | `20` | Number of benchmark samples |
| `--generate-manifest` | — | Generate release checksum manifest |
| `--verify-manifest` | — | Verify release checksum manifest |
| `--generate-model-manifest` | — | Generate AI model checksum manifest |
| `--verify-model-manifest` | — | Verify AI model checksum manifest |

### voice-comms-dcs-webrtc

Runs the full Nimbus stack: WebRTC bridge, STT, LLM, TTS, telemetry, dashboard, and input manager.

```text
voice-comms-dcs-webrtc --config PATH [options]
```

**Configuration:**

| Option | Default | Description |
|--------|---------|-------------|
| `--config PATH` | *(required)* | Commands config file |
| `--aircraft-profile PATH` | `config/aircraft_profiles/default.json` | Aircraft personality profile |
| `--rwr-registry PATH` | `config/rwr/adapters.json` | RWR adapter registry |
| `--srs-config PATH` | `config/srs/srs_audio.json` | SRS integration config |

**Network:**

| Option | Default | Description |
|--------|---------|-------------|
| `--host HOST` | from config (`127.0.0.1`) | Dashboard/WebRTC listen address |
| `--port PORT` | from config (`8765`) | Dashboard/WebRTC port |
| `--telemetry-host HOST` | from config (`127.0.0.1`) | Telemetry listener address |
| `--telemetry-port PORT` | from config (`10309`) | Telemetry listener port |
| `--allow-lan` | `false` | Allow LAN connections (non-localhost) |
| `--allowed-origin URL` | — | Extra allowed CORS origin |
| `--dashboard-token TOKEN` | random | Fixed dashboard auth token |
| `--disable-dashboard-auth` | — | Disable token auth (localhost dev only) |

**Input / PTT:**

| Option | Default | Description |
|--------|---------|-------------|
| `--ptt-hotkey KEY` | from config (`right_ctrl`) | Keyboard PTT key |
| `--joystick-index N` | from config (`0`) | Joystick device index |
| `--joystick-button N` | from config (`1`) | Joystick button number |
| `--joystick-profile NAME` | — | Named joystick preset |
| `--disable-input-manager` | — | Disable keyboard/joystick input |

**Language / AI:**

| Option | Default | Description |
|--------|---------|-------------|
| `--language CODE` | from config (`en`) | STT/TTS/LLM language |
| `--personality STYLE` | `professional` | Nimbus personality (`professional`, `casual`) |
| `--skin NAME` | `default` | Dashboard UI skin |
| `--whisper-model-path PATH` | from config | Override Whisper model file |
| `--whisper-engine ENGINE` | `auto` | `auto`, `cli`, or `binding` |
| `--whisper-cli-exe PATH` | `whisper-cli` | Path to whisper-cli executable |
| `--ollama-model MODEL` | from config | Override Ollama model |
| `--rwr-profile NAME` | — | RWR adapter profile name |

---

## Configuration file reference

Copy `config/commands.example.json` to `config/commands.json` as your starting point. All sections are optional — omitted fields use built-in defaults.

### Top-level fields

| Field | Default | Description |
|-------|---------|-------------|
| `dcs_host` | `"127.0.0.1"` | UDP destination host for DCS commands |
| `dcs_port` | `10308` | UDP destination port for DCS commands |

### `language`

```json
"language": {
  "selected": "en",
  "installed": ["en", "fr"]
}
```

`installed` controls which languages appear in the dashboard dropdown.

### `telemetry`

```json
"telemetry": {
  "host": "127.0.0.1",
  "port": 10309,
  "max_age_seconds": 2.0
}
```

`max_age_seconds`: telemetry older than this is treated as stale; gauges show `--`.

### `webrtc`

```json
"webrtc": {
  "host": "127.0.0.1",
  "port": 8765,
  "vad": {
    "engine": "energy",
    "rms_threshold": 0.012,
    "hangover_frames": 8
  }
}
```

`rms_threshold`: raise if background noise triggers false PTT releases. `hangover_frames`: frames of silence before PTT is considered released.

### `push_to_talk`

```json
"push_to_talk": {
  "enabled": true,
  "hotkey": "right_ctrl",
  "release_grace_ms": 300,
  "pre_roll_ms": 500,
  "max_context_ms": 15000
}
```

`pre_roll_ms`: audio buffered before PTT press, so the start of your phrase is not clipped. `max_context_ms`: maximum audio recorded per PTT press.

### `input`

```json
"input": {
  "keyboard_enabled": true,
  "joystick_enabled": true,
  "hotkey": "right_ctrl",
  "joystick_index": 0,
  "joystick_button": 1,
  "poll_hz": 60
}
```

### `matching`

```json
"matching": {
  "min_confidence": 0.78
}
```

Lower this value (e.g. `0.70`) if legitimate phrases are rejected. Raise it (e.g. `0.85`) if wrong commands fire.

### `stt`

```json
"stt": {
  "engine": "whisper_cpp",
  "language": "en",
  "model_path": "models/whisper/ggml-base.en.bin",
  "whisper": {
    "engine": "auto",
    "cli_exe": "whisper-cli",
    "threads": 4,
    "beam_size": 1,
    "pre_roll_ms": 500,
    "max_context_ms": 15000,
    "highpass_hz": 120.0,
    "lowpass_hz": 7600.0,
    "cli_timeout_seconds": 30.0
  }
}
```

`engine`: `"whisper_cpp"` uses Whisper.cpp (recommended). `"vosk"` uses the offline Vosk fallback. `"auto"` picks the best available.

`threads`: set to your physical CPU core count for best performance. `beam_size: 1` is fastest and sufficient for short command phrases.

### `llm`

```json
"llm": {
  "provider": "ollama",
  "base_url": "http://127.0.0.1:11434",
  "model": "qwen2.5:0.5b",
  "timeout_seconds": 3.0
}
```

`timeout_seconds`: Ollama requests that exceed this return the offline notice. Increase if your system is slow to respond.

### `tts`

```json
"tts": {
  "engine": "piper",
  "piper_exe": "piper",
  "piper_model": "models/piper/en_US-lessac-low.onnx",
  "radio_filter": {
    "bandpass_low_hz": 300,
    "bandpass_high_hz": 3000,
    "static_level": 0.012
  }
}
```

The radio filter shapes Piper output to sound like cockpit comms. `static_level` adds a subtle noise floor; set to `0` to disable.

### `udp_reliability`

```json
"udp_reliability": {
  "enabled": true,
  "require_ack": false,
  "retries": 0,
  "ack_timeout_seconds": 0.05,
  "protocol_version": 2
}
```

For reliable command delivery over loopback, `require_ack: false` is sufficient. Enable `require_ack` and set `retries` if you run DCS on a different machine.

### `dashboard.privacy`

```json
"dashboard": {
  "privacy": {
    "expose_position": false,
    "expose_tactical": true,
    "expose_context": true,
    "expose_model_paths": false,
    "expose_last_transcript": true
  }
}
```

| Field | Default | What it controls |
|-------|---------|-----------------|
| `expose_position` | `false` | Lat/lon in telemetry gauges |
| `expose_tactical` | `true` | Locked target, RWR data in context |
| `expose_context` | `true` | Full Nimbus context window in dashboard |
| `expose_model_paths` | `false` | Model file paths in dashboard API |
| `expose_last_transcript` | `true` | Last STT transcript in dashboard events |

### `commands`

Array of voice command objects. See [Defining commands](#defining-commands).

---

## Environment variables

All settings can be overridden with environment variables. Useful for automated startup or keeping secrets out of config files.

| Variable | Default | Description |
|----------|---------|-------------|
| `VCDCS_DASHBOARD_HOST` | `127.0.0.1` | Dashboard listen address |
| `VCDCS_DASHBOARD_PORT` | `8765` | Dashboard port |
| `VCDCS_DASHBOARD_TOKEN` | *(random)* | Fixed dashboard auth token |
| `VCDCS_ALLOW_LAN` | `false` | Allow non-localhost connections |
| `VCDCS_DCS_HOST` | `127.0.0.1` | UDP command destination |
| `VCDCS_DCS_PORT` | `10308` | UDP command port |
| `VCDCS_TELEMETRY_HOST` | `127.0.0.1` | Telemetry listener address |
| `VCDCS_TELEMETRY_PORT` | `10309` | Telemetry listener port |
| `VCDCS_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama API URL |
| `VCDCS_OLLAMA_MODEL` | `qwen2.5:0.5b` | Active Ollama model |
| `VCDCS_OLLAMA_TIMEOUT_SECONDS` | `3` | LLM request timeout |
| `VCDCS_WHISPER_MODEL` | `models/whisper/ggml-base.en.bin` | Whisper model path |
| `VCDCS_WHISPER_CLI_EXE` | `whisper-cli` | Whisper CLI executable |
| `VCDCS_WHISPER_TIMEOUT_SECONDS` | `30` | Whisper CLI timeout |
| `VCDCS_PIPER_EXE` | `piper` | Piper executable |
| `VCDCS_PIPER_MODEL` | `models/piper/en_US-lessac-low.onnx` | Piper voice model |
| `VCDCS_PIPER_TIMEOUT_SECONDS` | `30` | Piper TTS timeout |
| `VCDCS_SRS_ENABLED` | `false` | Enable SRS audio injection |
| `VCDCS_SRS_EXTERNAL_AUDIO_EXE` | *(SRS default path)* | Path to DCS-SR-ExternalAudio.exe |
| `VCDCS_SRS_TIMEOUT_SECONDS` | `10` | SRS operation timeout |
| `VCDCS_EXPOSE_POSITION` | `false` | Expose position in dashboard |
| `VCDCS_EXPOSE_MODEL_PATHS` | `false` | Expose model paths in dashboard API |

Copy `.env.example` to `.env` and fill in values as needed.

---

## Model selection guide

### Why small models work

Voice-Comms-DCS splits the workload so the LLM is never on the critical path for command execution:

- **Command path:** speech → Whisper → deterministic phrase matcher → UDP → DCS flag (no LLM)
- **Telemetry path:** "what's my altitude?" → direct answer from JSON telemetry (no LLM)
- **LLM path:** only free-form wingman questions that didn't match a command or telemetry query

Because LLM calls are non-blocking and non-critical, small quantised models give acceptable latency.

### Ollama model recommendations

| Model | Size | Use case |
|-------|------|----------|
| `qwen2.5:0.5b` | ~400 MB | Minimum viable — default |
| `qwen2.5:1.5b` | ~990 MB | Recommended — better persona stability |
| `qwen2.5:3b` | ~1.9 GB | Higher quality; only if DCS runs smoothly |
| `llama3.2:1b` | ~1.3 GB | Good alternative, slightly larger than Qwen 1.5B |
| `llama3.2:3b` | ~2.0 GB | High quality; heavy for concurrent DCS use |

Start with `qwen2.5:0.5b`. Switch to `qwen2.5:1.5b` only once you confirm DCS frame rates are unaffected.

### Whisper model recommendations

| Model file | English-only | Size | Recommendation |
|------------|-------------|------|----------------|
| `ggml-tiny.en.bin` | Yes | ~75 MB | Lowest latency; use if CPU is tight |
| `ggml-base.en.bin` | Yes | ~148 MB | Best balance — **recommended for English** |
| `ggml-base.bin` | No (multilingual) | ~148 MB | Required for non-English languages |

Never use `ggml-base.en.bin` for non-English speech — it will return garbled output.

### Piper voice model notes

Piper uses a radio bandpass filter (300–3000 Hz) that makes the output sound like cockpit comms. The `low` tier models produce output indistinguishable from `high` tier after filtering, so higher tiers offer no real benefit here.

Default English voice: `en_US-lessac-low.onnx` (female). For a male voice: `en_US-ryan-low.onnx`.

---

## SRS integration

DCS Simple Radio Standalone (SRS) integration is optional and disabled by default.

When enabled, Nimbus TTS audio is injected directly onto a configured SRS frequency, letting other pilots hear Nimbus responses over their SRS radio.

### Enabling SRS

Edit `config/srs/srs_audio.json`:

```json
{
  "enabled": true,
  "external_audio_exe": "C:/Program Files/DCS-SimpleRadio-Standalone/DCS-SR-ExternalAudio.exe",
  "frequency_mhz": 251.0,
  "modulation": "AM",
  "coalition": "blue",
  "timeout_seconds": 10.0
}
```

Or set `VCDCS_SRS_ENABLED=true` and `VCDCS_SRS_EXTERNAL_AUDIO_EXE=<path>` in your environment.

**Note:** SRS must be running and connected before Nimbus starts TTS output. The SRS integration uses a fixed safe subprocess command template and never shells through `cmd.exe`.

---

## RWR adapters

RWR (Radar Warning Receiver) adapters translate raw DCS threat codes into human-readable brevity messages that Nimbus includes in its tactical context.

The adapter registry lives at `config/rwr/adapters.json`.

**Built-in profiles:**

| Profile ID | Aircraft | RWR style |
|-----------|---------|-----------|
| `generic` | Any | Generic NATO/Russian symbols |
| `f16` | F-16C | ALR-56M style |
| `f18` | F/A-18C | ALR-67 style |
| `f15` | F-15C/E | TEWS style |
| `flanker` | Su-27/33, MiG-29, Su-57 | Russian SPO style |
| `f22` | F-22 | Simplified fifth-gen display |

Select a profile at launch:

```powershell
voice-comms-dcs-webrtc --config config\commands.json --rwr-profile f18
```

If no profile is specified, or if the aircraft does not match any profile, the `generic` adapter is used.

---

## DCS Lua bridge details

### How commands reach DCS

When a voice command is matched, Voice-Comms-DCS sends a UDP packet to DCS:

```
VCDCS|<command_id>|flag|<flag_number>|<value>
```

Example:

```
VCDCS|request_tanker|flag|5101|1
```

`VoiceBridge.lua` receives this on port 10308, validates the packet format, and calls `trigger.action.setUserFlag(5101, true)`. Your DCS mission script can then react to flag 5101 normally.

### Export.lua hooks

The installer appends two clearly marked blocks to `Export.lua`:

```lua
-- BEGIN VOICE_COMMS_DCS_BRIDGE
dofile(lfs.writedir() .. "Scripts/VoiceBridge.lua")
-- END VOICE_COMMS_DCS_BRIDGE

-- BEGIN VOICE_COMMS_DCS_TELEMETRY
dofile(lfs.writedir() .. "Scripts/dcs_telemetry.lua")
-- END VOICE_COMMS_DCS_TELEMETRY
```

These blocks are removed cleanly by `--uninstall-lua`. The original `Export.lua` is backed up before any modification.

### Telemetry data

`dcs_telemetry.lua` streams aircraft state to port 10309 at ~10 Hz. Nimbus uses this to answer questions like "what's my fuel?" and to build tactical context for the LLM. The data never leaves your machine.

Streamed fields include: altitude ASL/AGL, IAS, heading, fuel, engine RPM, G-load, gear/flap state, latitude, longitude, locked target (range, bearing, velocity), and RWR alerts.

---

## Security

### Dashboard access

The dashboard binds to `127.0.0.1` by default and is only reachable from the same machine. A per-session auth token is generated at startup and must be included in every request. The browser stores the token automatically from the startup URL.

Use `--dashboard-token` to set a stable token for a persistent local setup. Do not commit tokens to config files.

### LAN access

LAN access is off by default. To enable:

```powershell
voice-comms-dcs-webrtc --config config\commands.json --allow-lan
```

When `--allow-lan` is active, dashboard authentication must remain enabled. Never disable authentication on a LAN-accessible host.

### Privacy controls

By default, aircraft position (lat/lon) and model file paths are not sent to the dashboard. Enable them in `commands.json`:

```json
"dashboard": {
  "privacy": {
    "expose_position": true,
    "expose_model_paths": false
  }
}
```

### What stays local

- All audio is processed locally by Whisper.cpp.
- Nimbus context (conversation history, telemetry) is held in memory only and not written to disk.
- Ollama runs locally; no data is sent to external LLM providers.
- The Lua bridge operates entirely over loopback UDP.

---

## Troubleshooting

### DCS folder not detected

```powershell
voice-comms-dcs --install-lua --saved-games "D:\Saved Games"
```

The auto-detect covers both default and Windows shell-redirected Saved Games locations. Use `--saved-games` to override.

### Export.lua conflict with another mod

Uninstall the bridge, resolve the conflict, then reinstall:

```powershell
voice-comms-dcs --uninstall-lua
# resolve conflict manually
voice-comms-dcs --install-lua
```

Or restore from backup:

```text
Saved Games\DCS\Scripts\Export.lua.voice-comms-dcs.bak
```

### Dashboard shows "No connection"

- Verify the bridge is running (`voice-comms-dcs-webrtc` is in the terminal).
- Make sure you opened the exact URL printed at startup (including the `?token=` parameter).
- If the session expired, restart the bridge and use the new URL.

### Model download interrupted

Run the same download command again. Downloads resume from where they stopped using HTTP range requests. Completed files are verified by SHA-256 checksum before being moved to their final location.

### Non-English STT produces garbled output

You need the multilingual Whisper model (`ggml-base.bin`), not the English-only one (`ggml-base.en.bin`):

```powershell
voice-comms-dcs --setup-dependencies-ui --languages zh ko fr ru es --skip-ollama --skip-piper
```

Then set `stt.model_path` in `commands.json` to `models/whisper/ggml-base.bin`.

### Nimbus says "Comms system offline"

Ollama is not running or timed out. Voice commands still work normally. To start Ollama:

```powershell
ollama serve
```

Check that the model is pulled:

```powershell
ollama pull qwen2.5:0.5b
```

### Piper TTS produces no audio

Verify the model file exists:

```powershell
Get-Item models\piper\en_US-lessac-low.onnx
```

If missing, reinstall Piper voices:

```powershell
voice-comms-dcs --setup-dependencies-ui --languages en --skip-ollama --skip-whisper
```

### Commands fire at wrong confidence

Use `--test-phrase` to inspect confidence scores:

```powershell
voice-comms-dcs --config config\commands.json --test-phrase "bogey dope"
```

If the confidence is close to but below the threshold, add the phrase variant to the command's `phrases` array, or lower `matching.min_confidence` slightly.

### High CPU usage / DCS stutters

Switch to a smaller Ollama model:

```powershell
voice-comms-dcs-webrtc --config config\commands.json --ollama-model qwen2.5:0.5b
```

Or increase the LLM timeout so Nimbus fails faster when the system is busy:

```json
"llm": { "timeout_seconds": 2.0 }
```

Reduce telemetry rate in `dcs_telemetry.lua` if needed (default is 10 Hz).

---

## Uninstalling

Remove the DCS Lua bridge:

```powershell
voice-comms-dcs --uninstall-lua
```

Remove downloaded AI models:

```powershell
voice-comms-dcs --remove-dependencies --languages en zh ko fr ru es
```

Uninstall the Python package:

```powershell
pip uninstall voice-comms-dcs
```

If installed via the Windows installer (`.exe`), use **Add or Remove Programs** in Windows Settings.
