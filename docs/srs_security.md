# SRS security

The SRS adapter prepares radio-effect WAV files and can call a local SRS ExternalAudio helper. It must not become a generic local command launcher.

## Safe defaults

`config/srs/srs_audio.json` disables SRS by default and uses a fixed argv template internally:

```text
{exe} --file {file} --freq {frequency_mhz} --modulation {modulation} --coalition {coalition}
```

The adapter calls `subprocess.run(..., shell=False)`.

## Validation

The adapter validates:

- `frequency_mhz` must be between 1.0 and 1000.0;
- `modulation` must be `AM` or `FM`;
- `coalition` must be `blue`, `red`, or `neutral`;
- blocked shell launchers such as `cmd.exe`, `powershell.exe`, `pwsh`, `bash`, and `sh` cannot be used as the executable;
- paths with a suffix must use `.exe`.

## Custom templates

`command_template` is ignored unless `allow_custom_command_template` is explicitly `true`. When enabled, the first token must be `{exe}` or the configured executable path, and the same blocked launcher validation still applies.

Keep custom templates for local lab testing only and do not store machine-specific paths in shared configs.
