# Model Selection: Smallest Practical Piper and Ollama Models

## Recommendation summary

For Voice-Comms-DCS / Nimbus, the smallest practical local-first profile is:

| Component | Minimum practical default | Why |
|---|---|---|
| Ollama LLM | `qwen2.5:0.5b` | Very small download, enough for short wingman-style conversational filler because command and telemetry paths are deterministic. |
| Piper TTS | `en_US-lessac-low` | Compact US English Piper voice, 16 kHz, suitable for radio-effect output. |
| Whisper STT | `ggml-base.en.bin` | Best balance for cockpit command recognition; use `tiny.en` only when latency is more important than accuracy. |

Recommended low-load production profile:

| Component | Recommended | Why |
|---|---|---|
| Ollama LLM | `qwen2.5:1.5b` | Still light, but more stable for short tactical persona and instruction following than 0.5B. |
| Piper TTS | `en_US-lessac-low` or `en_US-ryan-low` | Both are small English voices; `ryan-low` gives a more male wingman feel. |
| Whisper STT | `ggml-base.en.bin` | Better military phrase recognition than `tiny.en`. |

## Why a very small LLM is acceptable here

Nimbus does not rely on the LLM for safety-critical command execution.

Command flow:

```text
Pilot speech -> Whisper -> deterministic command matcher -> UDP command -> DCS flag
```

Telemetry question flow:

```text
Pilot asks “what is my fuel?” -> deterministic telemetry parser -> answer from JSON telemetry
```

LLM flow:

```text
Only used for non-critical conversational wingman responses
```

Because of this split, a tiny Ollama model is acceptable. The LLM is not allowed to invent commands or execute Lua.

## Ollama candidates reviewed

| Model | Approx. Ollama size | Fit for Nimbus |
|---|---:|---|
| `gemma3:270m` | ~292 MB | Smallest, but too weak for reliable tactical persona. Keep as experimental only. |
| `qwen2.5:0.5b` | ~398 MB | Smallest practical default for this architecture. Good enough because commands are deterministic. |
| `qwen3:0.6b` | ~523 MB | Also viable, but Qwen3 thinking-style behavior can be less predictable for very short tactical responses. |
| `gemma3:1b` | ~815 MB | Good alternative if Qwen output style is not preferred. |
| `qwen2.5:1.5b` | ~986 MB | Recommended low-load profile. Better response quality while still small. |
| `llama3.2:1b` | ~1.3 GB | Good general chat model, but larger than Qwen2.5 1.5B in Ollama packaging. |
| `qwen2.5:3b` | ~1.9 GB | Stronger, but no longer the smallest reasonable option. Use only if resources allow. |
| `llama3.2:3b` | ~2.0 GB | Good quality, but heavier than needed for command-and-telemetry architecture. |

## Final Ollama recommendation

### Minimum profile

```powershell
ollama pull qwen2.5:0.5b
```

Use this when DCS frame-rate headroom is the priority.

### Recommended low-load profile

```powershell
ollama pull qwen2.5:1.5b
```

Use this if the PC has enough spare CPU/RAM/VRAM. This should be the preferred default for a polished Nimbus experience.

### Higher-quality optional profile

```powershell
ollama pull llama3.2:3b
```

Use this only if DCS remains smooth and you want better conversational responses.

## Piper candidates reviewed

Piper quality levels are a size/speed/audio-quality trade-off:

| Piper quality | Typical traits |
|---|---|
| `x_low` | Smallest, fastest, basic quality. Not generally available for common US English voices. |
| `low` | Small, fast, good enough for embedded/real-time use. |
| `medium` | Better audio quality, still moderate size. |
| `high` | Largest and best quality, not needed once radio filtering is applied. |

For a cockpit-radio voice, high fidelity is less important because Voice-Comms-DCS intentionally applies:

- 300 Hz to 3 kHz bandpass.
- Slight compression.
- Light static/noise overlay.

This means the `low` voice tier is a good match.

## Final Piper recommendation

### Minimum/recommended default

```text
models/piper/en_US-lessac-low.onnx
models/piper/en_US-lessac-low.onnx.json
```

Reason:

- US English.
- Small `low` tier model.
- 16 kHz is sufficient for radio-effect output.
- Good continuity with the current default `lessac` voice family.

### Optional male wingman voice

```text
models/piper/en_US-ryan-low.onnx
models/piper/en_US-ryan-low.onnx.json
```

Reason:

- Similar small footprint.
- More natural for a male wingman/RIO persona.

## Recommended default config

```json
{
  "llm": {
    "provider": "ollama",
    "base_url": "http://127.0.0.1:11434",
    "model": "qwen2.5:0.5b",
    "recommended_model": "qwen2.5:1.5b",
    "timeout_seconds": 3.0
  },
  "tts": {
    "engine": "piper",
    "piper_exe": "piper",
    "piper_model": "models/piper/en_US-lessac-low.onnx"
  }
}
```

## Performance profile

Minimum local model stack:

| Component | Model | Expected footprint |
|---|---|---:|
| LLM | `qwen2.5:0.5b` | ~398 MB Ollama model |
| TTS | `en_US-lessac-low` | ~63 MB ONNX model |
| STT | Whisper `base.en` | Moderate CPU use, command-length utterances only |

This is the best starting point for running alongside DCS without unnecessary frame-rate risk.

## Decision

Use this as the new default minimum profile:

```text
Ollama: qwen2.5:0.5b
Piper:  en_US-lessac-low
Whisper: ggml-base.en.bin
```

Document this as the minimum viable profile, while recommending `qwen2.5:1.5b` as the better low-load profile once the user confirms DCS remains smooth.
