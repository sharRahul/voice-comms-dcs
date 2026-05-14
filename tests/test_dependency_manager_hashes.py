from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from voice_comms_dcs import dependency_manager
from voice_comms_dcs.dependency_manager import DependencyManager, DownloadItem


class FakeResponse:
    def __init__(self, status_code: int, body: bytes = b"", headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.body = body
        self.headers = headers or {"Content-Length": str(len(body))}

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int) -> list[bytes]:
        return [self.body] if self.body else []


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patch_get(monkeypatch: pytest.MonkeyPatch, responses: list[FakeResponse]) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        calls.append({"url": url, **kwargs})
        return responses.pop(0)

    monkeypatch.setattr(dependency_manager.requests, "get", fake_get)
    return calls


def test_sha_success_promotes_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    body = b"trusted model"
    patch_get(monkeypatch, [FakeResponse(200, body)])
    manager = DependencyManager(root=tmp_path, progress=lambda *_args: None)

    target = manager.download_file(
        DownloadItem("model", "https://example.test/model.bin", tmp_path / "model.bin", sha256=digest(body))
    )

    assert target.read_bytes() == body
    assert not target.with_suffix(".bin.part").exists()


def test_sha_mismatch_raises_and_does_not_promote(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    patch_get(monkeypatch, [FakeResponse(200, b"tampered")])
    manager = DependencyManager(root=tmp_path, progress=lambda *_args: None)
    target = tmp_path / "model.bin"

    with pytest.raises(RuntimeError, match="SHA256 mismatch"):
        manager.download_file(
            DownloadItem("model", "https://example.test/model.bin", target, sha256=digest(b"expected"))
        )

    assert not target.exists()
    assert not target.with_suffix(".bin.part").exists()


def test_missing_sha_is_visible_as_warning(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    messages: list[str] = []
    patch_get(monkeypatch, [FakeResponse(200, b"unverified")])
    manager = DependencyManager(root=tmp_path, progress=lambda _kind, _percent, message: messages.append(message))

    manager.download_file(DownloadItem("model", "https://example.test/model.bin", tmp_path / "model.bin"))

    assert any("no SHA256 configured" in message for message in messages)


def test_http_416_with_matching_sha_promotes_partial(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    body = b"complete already"
    target = tmp_path / "model.bin"
    partial = target.with_suffix(".bin.part")
    partial.write_bytes(body)
    patch_get(monkeypatch, [FakeResponse(416)])
    manager = DependencyManager(root=tmp_path, progress=lambda *_args: None)

    manager.download_file(DownloadItem("model", "https://example.test/model.bin", target, sha256=digest(body)))

    assert target.read_bytes() == body
    assert not partial.exists()


def test_http_416_without_sha_deletes_partial_and_restarts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "model.bin"
    partial = target.with_suffix(".bin.part")
    partial.write_bytes(b"untrusted partial")
    calls = patch_get(monkeypatch, [FakeResponse(416), FakeResponse(200, b"fresh full file")])
    manager = DependencyManager(root=tmp_path, progress=lambda *_args: None)

    manager.download_file(DownloadItem("model", "https://example.test/model.bin", target))

    assert target.read_bytes() == b"fresh full file"
    assert calls[0]["headers"] == {"Range": f"bytes={len(b'untrusted partial')}-"}
    assert calls[1]["headers"] == {}


def test_http_416_with_mismatched_sha_does_not_promote_partial(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "model.bin"
    partial = target.with_suffix(".bin.part")
    partial.write_bytes(b"bad partial")
    fresh = b"trusted full file"
    patch_get(monkeypatch, [FakeResponse(416), FakeResponse(200, fresh)])
    manager = DependencyManager(root=tmp_path, progress=lambda *_args: None)

    manager.download_file(
        DownloadItem("model", "https://example.test/model.bin", target, sha256=digest(fresh))
    )

    assert target.read_bytes() == fresh
