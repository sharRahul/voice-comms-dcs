# Developer setup

Voice-Comms-DCS remains a Windows-first DCS companion app. Native Windows development is the primary path for installer validation, DCS Saved Games Lua bridge testing, joystick/HOTAS polling, microphone capture, SRS integration, Piper, Whisper.cpp, and real DCS runtime checks.

## Native Windows setup

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -c constraints.txt
python -m pip install -r requirements-dev.txt -c constraints.txt
python -m pip install -e . --no-deps
python -m pytest -q
python -m compileall src
ruff check src tests
```

Useful smoke tests:

```powershell
voice-comms-dcs --help
voice-comms-dcs-webrtc --help
voice-comms-dcs --config config\commands.example.json --test-phrase "request tanker"
```

## Docker and devcontainer setup

The repository includes a lightweight `Dockerfile`, `.dockerignore`, and `.devcontainer/devcontainer.json` for repeatable development, static checks, and tests.

```bash
docker build -t voice-comms-dcs-dev .
docker run --rm voice-comms-dcs-dev
```

VS Code users can reopen the repository in the devcontainer. The container installs constrained Python dependencies, then performs an editable install without dependencies so the pinned install path remains explicit.

## Container limitations

The container is for development and CI only. It does not run DCS World, audio device capture, joystick/HOTAS polling against real hardware, SRS, Piper runtime playback, Whisper model downloads, or Windows installer validation.

Downloaded AI models, `.env` files, build outputs, installers, `.part` files, `.tmp` files, `.exe`, `.dll`, `.bin`, `.onnx`, and archives are excluded from the Docker build context.
