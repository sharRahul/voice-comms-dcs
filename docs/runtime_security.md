# Runtime Security Notes

This document captures the local runtime controls added for audit findings F-12 to F-18.

## Configuration precedence

Runtime values are resolved in this order:

1. Explicit CLI arguments.
2. Values in `config/commands.json` or another file passed with `--config`.
3. Safe local defaults in `src/voice_comms_dcs/config.py`.

This keeps existing CLI behaviour stable while making the JSON configuration sections effective for WebRTC, telemetry, input, push-to-talk, STT, TTS, UDP reliability, and dashboard privacy.

## UDP command protocol

The Lua bridge accepts both packet formats:

```text
VCDCS|<command_id>|flag|<flag_number>|<flag_value>
VCDCS|<command_id>|command|<command_name>
```

and the newer v2 sequence format:

```text
VCDCS|v2|<sequence>|<command_id>|flag|<flag_number>|<flag_value>
VCDCS|v2|<sequence>|<command_id>|command|<command_name>
```

V2 adds a monotonically increasing sequence number. The Lua bridge tracks a fixed replay window and rejects duplicate sequence values. When the sender requests acknowledgements, Lua replies with:

```text
VCDCS_ACK|<sequence>|ok
VCDCS_ACK|<sequence>|rejected|<reason_code>
```

Acknowledgement waiting is optional and disabled by default so existing missions keep working even if no ACK is received.

## Dashboard privacy defaults

Dashboard status redacts sensitive fields by default:

- `spatial.lat`, `spatial.lon`, `spatial.x`, `spatial.y`, and `spatial.z` are removed.
- Full model paths are reduced to the model filename.
- `/health` remains minimal: `{ "status": "ok" }`.

Local debugging can opt into richer telemetry through `config/commands.json`:

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

Do not enable position or model-path exposure on a LAN/shared machine unless you are comfortable with those values being visible to authenticated dashboard clients.

## Dependency reproducibility

Use the constraints file for app installs and CI/dev validation:

```powershell
python -m pip install -r requirements.txt -c constraints.txt
python -m pip install -r requirements-dev.txt -c constraints.txt
python -m pytest -q
python -m compileall src
ruff check src tests
pip-audit
```

The PyInstaller build script uses `constraints.txt` automatically when it exists:

```powershell
.\build\build_exe.ps1
```

Keep `requirements.txt` as the runtime dependency list. Refresh exact pins in `constraints.txt` intentionally, then run tests and `pip-audit` before release.
