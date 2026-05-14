from __future__ import annotations

import hashlib
import json
from pathlib import Path

from voice_comms_dcs import dependency_manager
from voice_comms_dcs.dependency_manager import DependencyManager, DownloadItem


class FakeResponse:
    def __init__(self, status_code: int, body: bytes) -> None:
        self.status_code = status_code
        self.body = body
        self.headers = {"Content-Length": str(len(body))}

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int) -> list[bytes]:
        return [self.body]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_successful_download_records_manifest_entry(monkeypatch, tmp_path: Path) -> None:
    body = b"owned model"

    def fake_get(*_args, **_kwargs) -> FakeResponse:
        return FakeResponse(200, body)

    monkeypatch.setattr(dependency_manager.requests, "get", fake_get)
    manager = DependencyManager(root=tmp_path, progress=lambda *_args: None)
    target = tmp_path / "models" / "whisper" / "ggml-base.en.bin"

    manager.download_file(
        DownloadItem(
            "Whisper base.en",
            "https://example.test/ggml-base.en.bin",
            target,
            sha256=digest(body),
            component="whisper",
            key="base.en",
            languages=("en",),
        )
    )

    manifest_path = tmp_path / "models" / ".voice-comms-dcs-installed.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["installed_by"] == "voice-comms-dcs"
    assert payload["files"][0]["component"] == "whisper"
    assert payload["files"][0]["key"] == "base.en"
    assert payload["files"][0]["path"] == "models/whisper/ggml-base.en.bin"
    assert payload["files"][0]["sha256"] == digest(body)


def test_uninstall_removes_tracked_file(monkeypatch, tmp_path: Path) -> None:
    body = b"owned model"

    def fake_get(*_args, **_kwargs) -> FakeResponse:
        return FakeResponse(200, body)

    monkeypatch.setattr(dependency_manager.requests, "get", fake_get)
    manager = DependencyManager(root=tmp_path, progress=lambda *_args: None)
    target = tmp_path / "models" / "whisper" / "ggml-base.en.bin"
    manager.download_file(
        DownloadItem(
            "Whisper base.en",
            "https://example.test/ggml-base.en.bin",
            target,
            sha256=digest(body),
            component="whisper",
            key="base.en",
            languages=("en",),
        )
    )

    removed = manager.uninstall_downloaded_models(("en",), remove_piper=False)

    assert removed == [target]
    assert not target.exists()
    assert not manager.installed_models_manifest_path.exists()


def test_uninstall_does_not_remove_untracked_custom_whisper_model(monkeypatch, tmp_path: Path) -> None:
    body = b"owned model"

    def fake_get(*_args, **_kwargs) -> FakeResponse:
        return FakeResponse(200, body)

    monkeypatch.setattr(dependency_manager.requests, "get", fake_get)
    manager = DependencyManager(root=tmp_path, progress=lambda *_args: None)
    custom = tmp_path / "models" / "whisper" / "ggml-custom.bin"
    custom.parent.mkdir(parents=True)
    custom.write_bytes(b"user custom model")
    tracked = tmp_path / "models" / "whisper" / "ggml-base.en.bin"
    manager.download_file(
        DownloadItem(
            "Whisper base.en",
            "https://example.test/ggml-base.en.bin",
            tracked,
            sha256=digest(body),
            component="whisper",
            key="base.en",
            languages=("en",),
        )
    )

    manager.uninstall_downloaded_models(("en",), remove_piper=False)

    assert custom.read_bytes() == b"user custom model"
    assert not tracked.exists()


def test_uninstall_missing_manifest_is_safe_and_idempotent(tmp_path: Path) -> None:
    manager = DependencyManager(root=tmp_path, progress=lambda *_args: None)
    custom = tmp_path / "models" / "whisper" / "ggml-custom.bin"
    custom.parent.mkdir(parents=True)
    custom.write_bytes(b"user custom model")

    assert manager.uninstall_downloaded_models(("en",)) == []
    assert manager.uninstall_downloaded_models(("en",)) == []
    assert custom.exists()
