from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ManifestFile:
    path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class ReleaseManifest:
    project: str
    version: str
    generated_at_unix: float
    generated_on: str
    files: list[ManifestFile]


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def iter_files(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        if not path.exists():
            continue
        if path.is_file():
            yield path
            continue
        for child in sorted(path.rglob("*")):
            if child.is_file() and not child.name.endswith((".part", ".tmp")):
                yield child


def build_manifest(
    paths: Iterable[Path],
    root: Path,
    project: str = "voice-comms-dcs",
    version: str = "0.4.0",
) -> ReleaseManifest:
    root = root.resolve()
    entries: list[ManifestFile] = []
    for file_path in iter_files(paths):
        resolved = file_path.resolve()
        try:
            relative = resolved.relative_to(root)
        except ValueError:
            relative = Path(resolved.name)
        entries.append(
            ManifestFile(
                path=relative.as_posix(),
                size_bytes=resolved.stat().st_size,
                sha256=sha256_file(resolved),
            )
        )
    return ReleaseManifest(
        project=project,
        version=version,
        generated_at_unix=time.time(),
        generated_on=f"{platform.system()} {platform.release()} ({platform.machine()})",
        files=sorted(entries, key=lambda item: item.path),
    )


def write_manifest(manifest: ReleaseManifest, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asdict(manifest), indent=2, ensure_ascii=False), encoding="utf-8")

    sha_path = output.with_suffix(output.suffix + ".sha256")
    digest = sha256_file(output)
    sha_path.write_text(f"{digest}  {output.name}\n", encoding="utf-8")


def verify_manifest(manifest_path: Path, root: Path) -> tuple[bool, list[str]]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    for item in payload.get("files", []):
        file_path = root / item["path"]
        if not file_path.exists():
            failures.append(f"missing: {item['path']}")
            continue
        actual = sha256_file(file_path)
        if actual.lower() != str(item["sha256"]).lower():
            failures.append(f"sha256 mismatch: {item['path']}")
    return not failures, failures


def default_release_paths(root: Path) -> list[Path]:
    return [
        root / "dist" / "Voice-Comms-DCS",
        root / "build_output",
        root / "config" / "commands.example.json",
        root / "config" / "aircraft_profiles",
        root / "config" / "i18n",
        root / "config" / "joystick_profiles",
        root / "config" / "rwr",
        root / "config" / "srs",
        root / "dcs_scripts",
        root / "docs",
        root / "README.md",
        root / "LICENSE",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate or verify a Voice-Comms-DCS release checksum manifest.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="build_output/release_manifest.json")
    parser.add_argument("--project", default="voice-comms-dcs")
    parser.add_argument("--version", default="0.4.0")
    parser.add_argument("--include", nargs="*", default=None, help="Optional paths to include instead of the default release set.")
    parser.add_argument("--verify", action="store_true", help="Verify an existing manifest instead of generating one.")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    output = Path(args.output)
    if args.verify:
        ok, failures = verify_manifest(output, root)
        if failures:
            for failure in failures:
                print(failure)
        else:
            print(f"Manifest verified: {output}")
        return 0 if ok else 1

    paths = [root / item for item in args.include] if args.include else default_release_paths(root)
    manifest = build_manifest(paths, root=root, project=args.project, version=args.version)
    write_manifest(manifest, output)
    print(f"Wrote {output} with {len(manifest.files)} file entries")
    print(f"Wrote {output}.sha256")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
