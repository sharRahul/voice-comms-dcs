from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests

from .language_models import PIPER_VOICES, SUPPORTED_LANGUAGES, WHISPER_MODELS, get_whisper_model_key

ProgressCallback = Callable[[str, float | None, str], None]
INSTALLED_MODELS_MANIFEST = Path("models") / ".voice-comms-dcs-installed.json"


@dataclass(frozen=True)
class DownloadItem:
    label: str
    url: str
    path: Path
    sha256: str | None = None
    component: str | None = None
    key: str | None = None
    languages: tuple[str, ...] = ()


@dataclass(frozen=True)
class DependencyPlan:
    languages: tuple[str, ...]
    ollama_model: str
    whisper_quality: str
    include_ollama: bool = True
    include_whisper: bool = True
    include_piper: bool = True


@dataclass(frozen=True)
class InstalledModelEntry:
    component: str
    key: str
    path: str
    sha256: str
    installed_at_unix: float
    languages: tuple[str, ...] = ()


@dataclass(frozen=True)
class InstalledModelsManifest:
    version: int
    installed_by: str
    files: tuple[InstalledModelEntry, ...]


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

    @property
    def installed_models_manifest_path(self) -> Path:
        return self.root / INSTALLED_MODELS_MANIFEST

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
        """Remove only model files recorded in the install ownership manifest.

        Older versions deleted every `models/whisper/ggml-*.bin` file. That could remove custom
        or manually managed model files. The manifest is now the source of truth for ownership.
        """

        removed: list[Path] = []
        valid_languages = validate_languages(tuple(languages))
        manifest = self._load_installed_models_manifest()
        if not manifest.files:
            self.progress(
                "uninstall",
                None,
                "No Voice-Comms-DCS model ownership manifest found; no model files were removed.",
            )
            return removed

        remaining: list[InstalledModelEntry] = []
        for entry in manifest.files:
            if self._manifest_entry_matches_uninstall(
                entry,
                valid_languages,
                remove_whisper=remove_whisper,
                remove_piper=remove_piper,
            ):
                path = self.root / entry.path
                if path.exists():
                    path.unlink()
                    removed.append(path)
                continue
            remaining.append(entry)

        self._write_installed_models_manifest(
            InstalledModelsManifest(
                version=manifest.version,
                installed_by=manifest.installed_by,
                files=tuple(remaining),
            )
        )
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
        valid_languages = validate_languages(tuple(languages))
        languages_by_key: dict[str, list[str]] = {}
        for language in valid_languages:
            languages_by_key.setdefault(get_whisper_model_key(language, quality), []).append(language)

        for key in sorted(languages_by_key):
            spec = WHISPER_MODELS[key]
            self.download_file(
                DownloadItem(
                    label=f"Whisper {key}",
                    url=spec.url,
                    path=self.root / spec.model_path,
                    sha256=spec.sha256,
                    component="whisper",
                    key=key,
                    languages=tuple(sorted(languages_by_key[key])),
                )
            )

    def download_piper_voices(self, languages: Iterable[str]) -> None:
        for language in validate_languages(tuple(languages)):
            voice = PIPER_VOICES[language]
            self.download_file(
                DownloadItem(
                    f"Piper {voice.label}",
                    voice.model_url,
                    self.root / voice.model_path,
                    sha256=voice.model_sha256,
                    component="piper",
                    key=f"{language}:model",
                    languages=(language,),
                )
            )
            self.download_file(
                DownloadItem(
                    f"Piper {voice.label} config",
                    voice.config_url,
                    self.root / voice.config_path,
                    sha256=voice.config_sha256,
                    component="piper",
                    key=f"{language}:config",
                    languages=(language,),
                )
            )

    def download_file(self, item: DownloadItem) -> Path:
        target = item.path
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".part")

        restart_without_range = False
        for attempt in range(2):
            existing = partial.stat().st_size if partial.exists() and not restart_without_range else 0
            headers: dict[str, str | bytes] = {"Range": f"bytes={existing}-"} if existing > 0 else {}

            with requests.get(item.url, headers=headers, stream=True, timeout=30) as response:
                if response.status_code == 416:
                    if self._handle_range_not_satisfiable(item, partial, target):
                        return target
                    restart_without_range = True
                    if attempt == 0:
                        continue
                    raise RuntimeError(f"Unable to resume {item.label}: server returned HTTP 416.")

                response.raise_for_status()
                if response.status_code == 200 and existing > 0:
                    # Server ignored Range; restart cleanly.
                    partial.unlink(missing_ok=True)
                    existing = 0

                total_header = response.headers.get("Content-Length")
                total = int(total_header) + existing if total_header and total_header.isdigit() else None
                mode = "ab" if existing > 0 and response.status_code == 206 else "wb"
                downloaded = existing
                with partial.open(mode) as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        handle.write(chunk)
                        downloaded += len(chunk)
                        percent = downloaded / total * 100.0 if total else None
                        self.progress("download", percent, item.label)

            self._verify_or_warn(item, partial)
            partial.replace(target)
            digest = sha256_file(target)
            self._record_installed_file(item, target, digest)
            self.progress("download", 100.0, f"{item.label}: complete")
            return target

        raise RuntimeError(f"Unable to download {item.label}")

    def _handle_range_not_satisfiable(self, item: DownloadItem, partial: Path, target: Path) -> bool:
        if item.sha256 and partial.exists():
            digest = sha256_file(partial)
            if digest.lower() == item.sha256.lower():
                partial.replace(target)
                self._record_installed_file(item, target, digest)
                self.progress("download", 100.0, f"{item.label}: complete")
                return True
            partial.unlink(missing_ok=True)
            self.progress(
                "download",
                None,
                f"Discarded partial {item.label}: SHA256 mismatch after HTTP 416.",
            )
            return False

        partial.unlink(missing_ok=True)
        self.progress(
            "download",
            None,
            f"Discarded partial {item.label}: HTTP 416 cannot be trusted without SHA256.",
        )
        return False

    def _verify_or_warn(self, item: DownloadItem, partial: Path) -> None:
        if item.sha256:
            digest = sha256_file(partial)
            if digest.lower() != item.sha256.lower():
                partial.unlink(missing_ok=True)
                raise RuntimeError(f"SHA256 mismatch for {item.label}: {digest}")
            return

        self.progress(
            "download",
            None,
            f"WARNING: no SHA256 configured for {item.label}; verify and pin this model before release.",
        )

    def _record_installed_file(self, item: DownloadItem, target: Path, digest: str) -> None:
        if not item.component or not item.key:
            return

        relative_path = _relative_to_root(target, self.root)
        manifest = self._load_installed_models_manifest()
        entries = [
            entry
            for entry in manifest.files
            if not (entry.component == item.component and entry.key == item.key and entry.path == relative_path)
        ]
        entries.append(
            InstalledModelEntry(
                component=item.component,
                key=item.key,
                path=relative_path,
                sha256=digest,
                installed_at_unix=time.time(),
                languages=tuple(item.languages),
            )
        )
        self._write_installed_models_manifest(
            InstalledModelsManifest(
                version=manifest.version,
                installed_by=manifest.installed_by,
                files=tuple(sorted(entries, key=lambda entry: (entry.component, entry.key, entry.path))),
            )
        )

    def _load_installed_models_manifest(self) -> InstalledModelsManifest:
        path = self.installed_models_manifest_path
        if not path.exists():
            return InstalledModelsManifest(version=1, installed_by="voice-comms-dcs", files=())

        payload = json.loads(path.read_text(encoding="utf-8"))
        entries = []
        for item in payload.get("files", []):
            entries.append(
                InstalledModelEntry(
                    component=str(item["component"]),
                    key=str(item["key"]),
                    path=str(item["path"]),
                    sha256=str(item.get("sha256", "")),
                    installed_at_unix=float(item.get("installed_at_unix", 0.0)),
                    languages=tuple(str(language) for language in item.get("languages", ())),
                )
            )
        return InstalledModelsManifest(
            version=int(payload.get("version", 1)),
            installed_by=str(payload.get("installed_by", "voice-comms-dcs")),
            files=tuple(entries),
        )

    def _write_installed_models_manifest(self, manifest: InstalledModelsManifest) -> None:
        path = self.installed_models_manifest_path
        if not manifest.files:
            path.unlink(missing_ok=True)
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "version": manifest.version,
            "installed_by": manifest.installed_by,
            "files": [asdict(entry) for entry in manifest.files],
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _manifest_entry_matches_uninstall(
        self,
        entry: InstalledModelEntry,
        languages: tuple[str, ...],
        *,
        remove_whisper: bool,
        remove_piper: bool,
    ) -> bool:
        if entry.component == "whisper" and remove_whisper:
            requested_keys = {
                get_whisper_model_key(language, quality)
                for language in languages
                for quality in ("tiny", "base")
            }
            return bool(set(entry.languages) & set(languages)) or entry.key in requested_keys

        if entry.component == "piper" and remove_piper:
            entry_language = entry.key.split(":", maxsplit=1)[0]
            return bool(set(entry.languages) & set(languages)) or entry_language in languages

        return False


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


def _relative_to_root(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


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
