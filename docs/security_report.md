# Voice-Comms-DCS Security Report

## Scope

This report covers Phase 3 local WebRTC signaling, dashboard routes, microphone access, HID input capture, Whisper.cpp STT, and DCS UDP command/telemetry flows.

## Security objectives

- Keep all processing local by default.
- Prevent remote microphone access.
- Avoid exposing DCS command control to the LAN or internet.
- Avoid arbitrary code execution from transcripts, LLM outputs, or UDP packets.
- Keep HOTAS/keyboard capture transparent and user-controlled.

## Local network exposure

Default bind addresses:

| Service | Default bind | Risk posture |
|---|---|---|
| WebRTC/dashboard | `127.0.0.1:8765` | Local browser only |
| Command UDP | `127.0.0.1:10308` | Python-to-DCS local only |
| Telemetry UDP | `127.0.0.1:10309` | DCS-to-Python local only |
| Ollama | `127.0.0.1:11434` | Local LLM only |

Do not bind the WebRTC bridge to `0.0.0.0` unless you understand the risk and have firewall controls in place.

## Microphone protection

The browser dashboard requests microphone access only after the user clicks **Connect WebRTC**. The browser permission prompt remains the first line of defence. The WebRTC bridge does not publish microphone audio to a third-party service.

Recommended controls:

- Use `127.0.0.1` for dashboard access.
- Do not reverse-proxy the dashboard to the internet.
- Do not run the app on a shared machine without OS account controls.
- Stop the WebRTC bridge after flying.

## WebRTC signaling

The `/ws` endpoint accepts local WebRTC offers and transcript test messages. Because this is local-first software, there is no authentication layer in the Phase 3 scaffold.

Risk if exposed beyond localhost:

- A remote page could attempt to signal a peer connection.
- A remote client could send manual transcript commands.
- A remote client could read telemetry/status exposed by dashboard endpoints.

Mitigation:

- Bind to `127.0.0.1` by default.
- Add token authentication before any LAN/multiplayer server deployment.
- Use OS firewall rules if changing bind address.

## DCS command safety

DCS command execution still uses the Phase 1 Flag/Command bridge. The system does not execute arbitrary Lua from STT or LLM output.

Controls:

- UDP command packets must start with `VCDCS`.
- Command IDs use safe identifiers.
- Flag IDs must be numeric.
- Lua bridge does not use `os.execute`.
- Mission logic owns final behavior.

## LLM safety

Nimbus uses deterministic command matching first. Local LLM output is used for conversation, not executable mission control.

Controls:

- Command intent goes through configured `commands.json` only.
- Informational questions can be answered from telemetry without LLM use.
- LLM output is never sent to DCS as Lua code.

## HID/PTT privacy

`pynput` captures keyboard events globally so PTT works while DCS is focused. `pygame.joystick` polls joystick state without exclusive device acquisition.

Risks:

- Global hotkey libraries can observe keyboard events.
- Misconfigured hotkeys may collide with DCS controls.

Mitigation:

- Use a single modifier key or joystick button dedicated to PTT.
- Do not log raw keyboard input; this implementation logs only PTT transitions.
- Run `voice-comms-dcs-input --list` and test bindings before flying.

## Model and binary supply chain

Whisper/Piper model files and binaries are not committed. The setup script downloads Whisper models from the public whisper.cpp model hosting location.

Recommended controls:

- Prefer known model sources.
- Keep hashes in a future release manifest.
- Do not run unknown TTS/STT binaries from untrusted sources.
- Code-sign release installers before public distribution.

## Recommended hardening before public release

- Add dashboard/session token for `/ws` and `/api/live`.
- Add explicit CORS denial for non-local origins.
- Add bind-address warning when `--host` is not `127.0.0.1` or `localhost`.
- Add installer checkbox for Windows Firewall rule only when LAN access is explicitly desired.
- Add signed release builds.
- Add model checksum verification for Whisper/Piper downloads.
