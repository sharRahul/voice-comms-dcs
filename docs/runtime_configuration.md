# Runtime configuration

Voice-Comms-DCS supports CLI flags and JSON config files for normal use. The repository also includes `.env.example` as a safe reference for local development variables.

## Environment file workflow

1. Copy `.env.example` to `.env` only on your local machine.
2. Fill in local values such as dashboard host, ports, optional dashboard token, Ollama model, Whisper path, Piper path, and optional SRS executable path.
3. Keep `.env` private. The repository ignores `.env` and `.env.*` while keeping `.env.example` committed.
4. Do not store real tokens, machine-specific private paths, or local secrets in shared JSON examples.

The current app still primarily uses CLI flags and `config/commands.json`; the variables in `.env.example` are a documented local-development reference for packaging and future lightweight env overrides.
