from __future__ import annotations

import json
from pathlib import Path


def test_dockerfile_exists_and_is_dev_test_focused():
    dockerfile = Path("Dockerfile")
    content = dockerfile.read_text(encoding="utf-8")

    assert dockerfile.exists()
    assert "FROM python:3.11-slim" in content
    assert 'CMD ["python", "-m", "pytest", "-q"]' in content
    assert "COPY models" not in content
    assert "COPY .env" not in content


def test_dockerignore_excludes_sensitive_and_generated_content():
    content = Path(".dockerignore").read_text(encoding="utf-8")

    expected_entries = (".env", ".env.*", "models", "dist", "build_output", "*.bin", "*.onnx")
    for expected in expected_entries:
        assert expected in content
    assert "!/.env.example" in content


def test_devcontainer_exists_and_uses_root_dockerfile():
    devcontainer = json.loads(Path(".devcontainer/devcontainer.json").read_text(encoding="utf-8"))

    assert devcontainer["name"] == "Voice-Comms-DCS Dev"
    assert devcontainer["build"]["dockerfile"] == "../Dockerfile"
    assert devcontainer["build"]["context"] == ".."
    assert "python -m pip install -e . --no-deps" in devcontainer["postCreateCommand"]
