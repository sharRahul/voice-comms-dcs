from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .language_models import PIPER_VOICES, SUPPORTED_LANGUAGES, WHISPER_MODELS, get_whisper_model_key

ProgressCallback = Callable[[str, float | None, str], None]


@dataclass(frozen=True)
class DownloadItem:
    label: str
    url: str
    path: Path
    sha256: str | None = None


@dataclass(frozen=True)
class DependencyPlan:
    languages: tuple[str, ...]
    ollama_model: str
    whisper_quality: str
    include_ollama: bool = True
    include_whisper: bool = True
    include_piper: bool = True


class DependencyManager:
    """Downloads and removes local-first Nimbus dependencies.

    HTTP file downloads are resumable through Range requests when the server supports them.
    Ollama downloads use `/api/pull`, which streams progress and resumes cancelled pulls on the
    Ollama side.
    """

    def __init__(
        self,
        root: Path | str = ".",
        ollama_base_url: str = "http://127.0.0.1:11434",
        progress: ProgressCallback | None = None,
    ) -> None:
        self.root = Path(root)
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.progress = progress or console_progress

    def install(self, plan: DependencyPlan) -> None:
        languages = validate_languages(plan.languages)
        if plan.include_ollama:
            self.pull_ollama_model(plan.ollama_model)
        if plan.include_whisper:
            self.download_whisper_models(languages, plan.whisper_quality)
        if plan.include_piper:
            self.download_piper_voices(languages)

    def uninstall_downloaded_models(
        self,
        languages: Iterable[str],
        remove_whisper: bool = True,
        remove_piper: bool = True,
    ) -> list[Path]:
        removed: list[Path] = []
        valid_languages = validate_languages(tuple(languages))
        if remove_whisper:
            whisper_dir = self.root / "models" / "whisper"
            if whisper_dir.exists():
                for path in whisper_dir.glob("ggml-*.bin"):
                    path.unlink(missing_ok=True)
                    removed.append(path)
        if remove_piper:
            for language in valid_languages:
                voice = PIPER_VOICES[language]
                for path in (self.root / voice.model_path, self.root / voice.config_path):
                    path.unlink(missing_ok=True)
                    removed.append(path)
        return removed

    def pull_ollama_model(self, model: str) -> None:
        url = f"{self.ollama_base_url}/api/pull"
        self.progress("ollama", None, f"pulling {model}")
        try:
            response = requests.post(url, json={"model": model, "stream": True}, stream=True, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Unable to contact Ollama at {self.ollama_base_url}. Install/start Ollama first. {exc}"
            ) from exc

        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            total = payload.get("total")
            completed = payload.get("completed")
            percent = None
            if isinstance(total, int) and total > 0 and isinstance(completed, int):
                percent = min(100.0, completed / total * 100.0)
            status = str(payload.get("status", "pulling"))
            self.progress("ollama", percent, f"{model}: {status}")
            if status == "success":
                self.progress("ollama", 100.0, f"{model}: success")

    def download_whisper_models(self, languages: Iterable[str], quality: str = "base") -> None:
        keys = sorted({get_whisper_model_key(language, quality) for language in languages})
        for key in keys:
            spec = WHISPER_MODELS[key]
            self.download_file(
                DownloadItem(
                    label=f"Whisper {key}",
                    url=spec.url,
                    path=self.root / spec.model_path,
                )
            )

    def download_piper_voices(self, languages: Iterable[str]) -> None:
        for language in validate_languages(tuple(languages)):
            voice = PIPER_VOICES[language]
            self.download_file(DownloadItem(f"Piper {voice.label}", voice.model_url, self.root / voice.model_path))
            self.download_file(DownloadItem(f"Piper {voice.label} config", voice.config_url, self.root / voice.config_path))

    def download_file(self, item: DownloadItem) -> Path:
        target = item.path
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".part")
        existing = partial.stat().st_size if partial.exists() else 0
        headers = {"Range": f"bytes={existing}-"} if existing > 0 else {}

        with requests.get(item.url, headers=headers, stream=True, timeout=30) as response:
            if response.status_code == 416:
                partial.replace(target)
                return target
            response.raise_for_status()
            if response.status_code == 200 and existing > 0:
                # Server ignored Range; restart cleanly.
                partial.unlink(missing_ok=True)
                existing = 0

            total_header = response.headers.get("Content-Length")
            total = int(total_header) + existing if total_header and total_header.isdigit() else None
            mode = "ab" if existing > 0 and response.status_code == 206 else "wb"
            downloaded = existing
            with partial.open(mode + "b") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    downloaded += len(chunk)
                    percent = downloaded / total * 100.0 if total else None
                    self.progress("download", percent, item.label)

        if item.sha256:
            digest = sha256_file(partial)
            if digest.lower() != item.sha256.lower():
                raise RuntimeError(f"SHA256 mismatch for {item.label}: {digest}")
        partial.replace(target)
        self.progress("download", 100.0, f"{item.label}: complete")
        return target


def validate_languages(languages: Iterable[str]) -> tuple[str, ...]:
    result = tuple(dict.fromkeys(language.strip().lower() for language in languages if language.strip()))
    invalid = [language for language in result if language not in SUPPORTED_LANGUAGES]
    if invalid:
        raise ValueError(f"Unsupported language(s): {', '.join(invalid)}")
    return result or ("en",)


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def console_progress(kind: str, percent: float | None, message: str) -> None:
    if percent is None:
        print(f"[{kind}] {message}")
    else:
        print(f"[{kind}] {percent:6.2f}% {message}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install or remove Voice-Comms-DCS local AI models.")
    parser.add_argument("--languages", nargs="+", default=["en"], choices=sorted(SUPPORTED_LANGUAGES))
    parser.add_argument("--ollama-model", default="qwen2.5:0.5b")
    parser.add_argument("--whisper-quality", choices=["tiny", "base"], default="base")
    parser.add_argument("--root", default=".")
    parser.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--skip-ollama", action="store_true")
    parser.add_argument("--skip-whisper", action="store_true")
    parser.add_argument("--skip-piper", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--all", action="store_true", help="Install Ollama, Whisper, and Piper assets.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manager = DependencyManager(root=args.root, ollama_base_url=args.ollama_base_url)
    languages = validate_languages(args.languages)

    if args.uninstall:
        removed = manager.uninstall_downloaded_models(languages)
        for path in removed:
            print(f"removed {path}")
        return 0

    plan = DependencyPlan(
        languages=languages,
        ollama_model=args.ollama_model,
        whisper_quality=args.whisper_quality,
        include_ollama=args.all or not args.skip_ollama,
        include_whisper=args.all or not args.skip_whisper,
        include_piper=args.all or not args.skip_piper,
    )
    manager.install(plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
