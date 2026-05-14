# Runtime Reliability Configuration

Nimbus remains local-first. The runtime now uses explicit safety limits for subprocesses, PTT audio buffering, dashboard broadcasts, and local configuration precedence.

## Subprocess timeouts

The local external tools are bounded by default so a missing or stalled executable cannot hang the WebRTC/audio pipeline indefinitely.

| Component | Config field | Default |
|---|---|---:|
| Whisper CLI STT | `stt.whisper.cli_timeout_seconds` | `30.0` seconds |
| Piper TTS | `tts.piper_timeout_seconds` | `30.0` seconds |
| SRS ExternalAudio adapter | `config/srs/srs_audio.json -> timeout_seconds` | `10.0` seconds |

Timeout errors are sanitized before they reach dashboard callers. They do not include full command lines or local filesystem paths.

## Push-to-talk audio cap

PTT audio is capped with:

```json
"push_to_talk": {
  "pre_roll_ms": 500,
  "max_context_ms": 15000
}
```

The rolling buffer keeps the newest active audio and trims older chunks when the cap is reached. This preserves normal pre-roll behaviour while bounding memory use if PTT is held or stuck.

## TTS temporary cleanup

`RadioVoice.synthesise_to_temp_wav()` still returns a WAV path for the existing playback/SRS flow. After SRS dispatch and WebRTC enqueue complete, the WebRTC bridge removes the temporary `voice-comms-dcs-tts-*` directory on a best-effort basis. User-provided output paths from `synthesise_to_wav(output_path=...)` are not removed.

## Config precedence

When launching `voice-comms-dcs-webrtc`, CLI flags override `config/commands.json`. If a CLI value is omitted, the bridge uses the typed config sections:

- `telemetry.host`, `telemetry.port`
- `webrtc.host`, `webrtc.port`, `webrtc.vad.rms_threshold`, `webrtc.vad.hangover_frames`
- `input.keyboard_enabled`, `input.joystick_enabled`, `input.hotkey`, `input.joystick_index`, `input.joystick_button`, `input.poll_hz`
- `push_to_talk.enabled`, `push_to_talk.hotkey`, `push_to_talk.pre_roll_ms`, `push_to_talk.max_context_ms`
- `stt.whisper.*` for Whisper CLI/binding runtime values
- `tts.piper_timeout_seconds` for Piper synthesis timeout

`--disable-input-manager` still disables local keyboard and joystick PTT regardless of config.
