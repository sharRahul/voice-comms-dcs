from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .language_models import PIPER_VOICES, WHISPER_MODELS


@dataclass(frozen=True)
class ModelManifestEntry:
    component: str
    key: str
    path: str
    size_bytes: int
    sha256: str
    source_url: str = ""
    source: str = ""
    license_note: str = ""


@dataclass(frozen=True)
class ModelManifest:
    project: str
    generated_at_unix: float
    generated_on: str
    root: str
    models: list[ModelManifestEntry]


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def build_model_manifest(root: Path = Path("."), include_unknown: bool = True) -> ModelManifest:
    root = root.resolve()
    entries: list[ModelManifestEntry] = []

    known_paths: set[Path] = set()
    for key, spec in WHISPER_MODELS.items():
        path = root / spec.model_path
        known_paths.add(path.resolve())
        if path.exists():
            entries.append(
                ModelManifestEntry(
                    component="whisper",
                    key=key,
                    path=spec.model_path,
                    size_bytes=path.stat().st_size,
                    sha256=sha256_file(path),
                    source_url=spec.url,
                    source="ggerganov/whisper.cpp Hugging Face mirror",
                    license_note="See upstream whisper.cpp and Whisper model licensing.",
                )
            )

    for language, voice in PIPER_VOICES.items():
        for kind, model_path, url in (
            ("model", voice.model_path, voice.model_url),
            ("config", voice.config_path, voice.config_url),
        ):
            path = root / model_path
            known_paths.add(path.resolve())
            if path.exists():
                entries.append(
                    ModelManifestEntry(
                        component="piper",
                        key=f"{language}:{kind}",
                        path=model_path,
                        size_bytes=path.stat().st_size,
                        sha256=sha256_file(path),
                        source_url=url,
                        source=voice.source,
                        license_note=voice.license_note,
                    )
                )

    if include_unknown:
        for base in (root / "models" / "whisper", root / "models" / "piper"):
            if not base.exists():
                continue
            for path in sorted(base.rglob("*")):
                if not path.is_file() or path.name.endswith((".part", ".tmp")):
                    continue
                if path.resolve() in known_paths:
                    continue
                entries.append(
                    ModelManifestEntry(
                        component="unknown",
                        key=path.name,
                        path=str(path.relative_to(root)).replace("\\", "/"),
                        size_bytes=path.stat().st_size,
                        sha256=sha256_file(path),
                    )
                )

    return ModelManifest(
        project="voice-comms-dcs-models",
        generated_at_unix=time.time(),
        generated_on=f"{platform.system()} {platform.release()} ({platform.machine()})",
        root=str(root),
        models=sorted(entries, key=lambda item: item.path),
    )


def write_model_manifest(manifest: ModelManifest, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asdict(manifest), indent=2, ensure_ascii=False), encoding="utf-8")
    digest = sha256_file(output)
    output.with_suffix(output.suffix + ".sha256").write_text(f"{digest}  {output.name}\n", encoding="utf-8")


def verify_model_manifest(manifest_path: Path, root: Path = Path(".")) -> tuple[bool, list[str]]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    for item in payload.get("models", []):
        path = root / item["path"]
        if not path.exists():
            failures.append(f"missing: {item['path']}")
            continue
        actual = sha256_file(path)
        if actual.lower() != str(item["sha256"]).lower():
            failures.append(f"sha256 mismatch: {item['path']}")
    return not failures, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate or verify a checksum manifest for downloaded local AI models.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="build_output/model_manifest.json")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--known-only", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    output = Path(args.output)
    if args.verify:
        ok, failures = verify_model_manifest(output, root)
        if failures:
            for failure in failures:
                print(failure)
        else:
            print(f"Model manifest verified: {output}")
        return 0 if ok else 1

    manifest = build_model_manifest(root=root, include_unknown=not args.known_only)
    write_model_manifest(manifest, output)
    print(f"Wrote {output} with {len(manifest.models)} model entries")
    print(f"Wrote {output}.sha256")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
