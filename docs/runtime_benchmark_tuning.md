# DCS Runtime Benchmark and Tuning Guide

## Purpose

This guide provides repeatable checks for running DCS World, Nimbus WebRTC audio, Whisper.cpp, Piper TTS, and a small Ollama model on the same PC without causing DCS frame stutters.

## Benchmark command

Start DCS and Nimbus first, then run:

```powershell
voice-comms-dcs-benchmark --samples 30 --output build_output\runtime_benchmark.json
```

The command writes:

```text
build_output/runtime_benchmark.json
build_output/runtime_benchmark.csv
```

## What is measured

| Probe | Target |
|---|---:|
| Dashboard `/health` latency p95 | < 100 ms |
| Telemetry age | < 2 seconds |
| UDP command send | no failures |
| Ollama `/api/tags` latency p95 | < 250 ms |

## Flight-test tuning checklist

1. Start with `qwen2.5:0.5b`.
2. Use `ggml-base.en.bin` for English-only flights.
3. Use `ggml-base.bin` only when non-English STT is needed.
4. Keep DCS telemetry export at 10 Hz until the mission is tested.
5. Keep WebRTC/dashboard bound to `127.0.0.1`.
6. Prefer PTT over continuous speech recognition.
7. Use a low/medium Piper voice, not a large neural TTS stack.
8. Avoid running benchmarks during heavy DCS shader compilation.
9. Test with your heaviest mission, not an empty map.
10. Record DCS FPS/frame-time before and after enabling Nimbus.

## Recommended starting profiles

### Mid-range PC

```text
LLM: qwen2.5:0.5b
Whisper: base.en or tiny.en
Piper: low voice
Telemetry: 10 Hz
Dashboard: localhost only
```

### High-end PC

```text
LLM: qwen2.5:1.5b
Whisper: base.en / base multilingual
Piper: low or medium voice
Telemetry: 10 Hz to 20 Hz after testing
Dashboard: localhost only
```

## When DCS stutters

Reduce in this order:

1. LLM size.
2. Whisper model size.
3. Telemetry frequency.
4. Dashboard polling frequency.
5. TTS quality/model size.
6. Browser tabs and overlays.

## Troubleshooting benchmark output

### Telemetry stale

Check:

```text
Saved Games\DCS*\Scripts\Export.lua
Saved Games\DCS*\Scripts\VoiceBridge.lua
Saved Games\DCS*\Scripts\dcs_telemetry.lua
UDP 127.0.0.1:10309
```

### Ollama unavailable

Run:

```powershell
ollama list
ollama pull qwen2.5:0.5b
```

### UDP command send fails

Check local firewall rules and that the Lua bridge is listening on the configured command port.

### Dashboard health high

Close extra browser tabs, keep the dashboard local-only, and avoid opening multiple dashboard sessions during heavy missions.
