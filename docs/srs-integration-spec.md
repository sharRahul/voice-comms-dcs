# SRS integration specification

## Purpose

Simple Radio Standalone (SRS) is the de facto multiplayer radio tool for many DCS World servers. It provides aircraft radio simulation, frequency selection, coalition separation, modulation effects, and server-side radio behaviour that is much closer to real multiplayer operations than generic voice chat.

Nimbus already produces a radio-style voice response through Piper and `radio_voice.py`. The SRS integration path defines how that generated audio can be transmitted through SRS so other multiplayer pilots hear Nimbus on the correct radio channel instead of only through the local dashboard or speaker output.

## Goals

- Route Nimbus TTS output into an SRS-compatible transmit path.
- Preserve the existing Piper/radio-effect chain.
- Avoid unsafe shell invocation or arbitrary command execution.
- Keep the feature optional and disabled by default.
- Fail gracefully to local speaker/dashboard output when SRS is not installed or not connected.

## Non-goals

- Replacing SRS or implementing a full radio stack inside Nimbus.
- Bypassing DCS server rules or coalition restrictions.
- Transmitting without explicit local configuration by the pilot.
- Sending microphone audio captured from other applications.

## Current audio chain

The intended chain is:

```text
Nimbus text response
  -> Piper TTS voice model
  -> radio_voice.py band-pass/static/radio effect
  -> local WAV/PCM output
  -> SRS injection adapter
  -> SRS selected radio/frequency
```

The same generated audio should still be available to the browser dashboard as text and to WebRTC/speaker output as a fallback.

## Option A: audio loopback device injection

This approach uses a virtual audio cable or loopback input device. Nimbus plays the generated radio-effect audio into the virtual output device, and SRS is configured to use the paired virtual input as its microphone.

### Candidate libraries

- `sounddevice` for selecting and playing to a specific Windows audio device.
- `pyaudio` as an alternative device I/O backend if `sounddevice` cannot cover a user setup.
- Python `wave` or `soundfile` for WAV loading, depending on final packaging constraints.

### Advantages

- Works with normal SRS microphone input behaviour.
- Does not depend on private or unstable SRS APIs.
- Easy for users to understand because it follows the same pattern as virtual audio cable setups.

### Disadvantages

- Requires the user to install and configure a virtual audio cable.
- Can interfere with the user's real microphone if SRS only accepts one input device.
- Audio routing differs across Windows installations.
- Push-to-talk state and radio selection still need careful coordination.

### Implementation notes

- Add an SRS audio output device setting to the dashboard/config.
- Validate the chosen device at startup and show a warning if it is missing.
- Play only Nimbus-generated audio to the loopback device.
- Keep local speaker output optional so pilots can avoid double-monitoring.
- Provide a test tone/test phrase button in the dashboard.

## Option B: SRS external audio interface

This approach uses an SRS-supported external audio command/API if available in the installed SRS version. Nimbus prepares the radio-effect audio file and hands it to an SRS external audio executable or API adapter.

The repository already contains `src/voice_comms_dcs/srs_audio.py`, which is a safe adapter shape for an ExternalAudio-style executable. It avoids shell execution and builds explicit argument vectors.

### Candidate libraries

- `subprocess` with explicit argv tokens for a local SRS external-audio executable.
- `requests` or `websockets` only if SRS exposes a documented local API in a supported release.
- `sounddevice` remains useful for preview/fallback playback.

### Advantages

- Avoids taking over the user's microphone device.
- Can be more deterministic than virtual audio routing.
- Easier to select frequency, modulation, coalition, and callsign if the external interface supports those fields.

### Disadvantages

- Depends on the exact SRS version and documented interface availability.
- External executable/API behaviour must be verified across installs.
- May not be accepted on all multiplayer servers.

### Implementation notes

- Keep command templates disabled by default unless explicitly allowed.
- Allow only local executable paths and block shell interpreters.
- Use a timeout for any external process call.
- Log failure reason without exposing raw command-line secrets in the dashboard.
- Fall back to dashboard/local speaker output when the SRS adapter fails.

## Required configuration

Suggested future config block:

```json
{
  "srs": {
    "enabled": false,
    "mode": "external_audio",
    "external_audio_exe": "C:/Program Files/DCS-SimpleRadio-Standalone/DCS-SR-ExternalAudio.exe",
    "audio_device_name": "CABLE Input",
    "frequency_mhz": 251.0,
    "modulation": "AM",
    "coalition": "blue",
    "timeout_seconds": 10.0
  }
}
```

## Open questions and blockers

- Which SRS versions expose a stable external audio path?
- Does the external audio interface support frequency/modulation/coalition selection without changing the pilot's live radio state?
- How should Nimbus coordinate with the pilot's own PTT so it does not transmit over the human pilot?
- Should the feature be server-gated or profile-gated for multiplayer etiquette?
- How should mixed local languages and SRS coalition channels be handled?
- What is the best default for audio ducking so Nimbus does not mask human radio traffic?

## Acceptance criteria

A first implementation should meet these criteria:

1. SRS integration is disabled by default.
2. The dashboard clearly shows whether SRS output is available, disabled, or failed.
3. Nimbus can transmit a generated test phrase through the selected SRS path.
4. Failure to find SRS or the selected audio device does not break dashboard, telemetry, TTS, or deterministic DCS commands.
5. External process calls use explicit argv, no shell, blocked interpreter names, and a timeout.
6. Audio output remains local-first and does not send data to any cloud service.
7. Documentation explains the required Windows audio/SRS configuration steps.
8. Automated tests cover config validation and failure paths.

## Recommended path

Use Option B first where a documented SRS external audio interface is available, because it avoids taking over the user's microphone. Keep Option A as a fallback for users and servers where external audio is not viable.
