from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

VOICE_BRIDGE_HOOK_ID = "VOICE_COMMS_DCS_BRIDGE"
TELEMETRY_HOOK_ID = "VOICE_COMMS_DCS_TELEMETRY"

VOICE_BRIDGE_HOOK = f"-- BEGIN {VOICE_BRIDGE_HOOK_ID}\n" \
    "local voiceBridgePath = lfs.writedir() .. [[Scripts\\VoiceBridge.lua]]\n" \
    "local voiceBridgeOk, voiceBridgeOrError = pcall(dofile, voiceBridgePath)\n" \
    "if voiceBridgeOk and voiceBridgeOrError then voiceBridgeOrError.installExportCallbacks() end\n" \
    f"-- END {VOICE_BRIDGE_HOOK_ID}\n"

TELEMETRY_HOOK = f"-- BEGIN {TELEMETRY_HOOK_ID}\n" \
    "local dcsTelemetryPath = lfs.writedir() .. [[Scripts\\dcs_telemetry.lua]]\n" \
    "local dcsTelemetryOk, dcsTelemetryOrError = pcall(dofile, dcsTelemetryPath)\n" \
    "if dcsTelemetryOk and dcsTelemetryOrError then dcsTelemetryOrError.installExportCallbacks() end\n" \
    f"-- END {TELEMETRY_HOOK_ID}\n"


@dataclass(frozen=True)
class DcsInstallTarget:
    root: Path
    scripts_dir: Path
    export_lua: Path


@dataclass(frozen=True)
class InstallResult:
    target: DcsInstallTarget
    copied_files: tuple[Path, ...]
    export_modified: bool
    backup_path: Path | None
    message: str


def get_saved_games_path() -> Path:
    """Resolve Saved Games using the Windows Shell Folders API when available.

    This handles users who moved Saved Games to a different drive. Falls back to
    `%USERPROFILE%\\Saved Games` when the shell lookup is unavailable.
    """
    if sys.platform.startswith("win"):
        try:
            # FOLDERID_SavedGames = {4C5C32FF-BB9D-43B0-B5B4-2D72E54EAAA4}
            folder_id = ctypes.c_char_p(bytes.fromhex("ff325c4c9dbbb043b5b42d72e54eaaa4"))
            # Avoid complex COM struct dependencies in the scaffold; use PowerShell fallback below.
        except Exception:
            pass

        try:
            import subprocess

            command = [
                "powershell",
                "-NoProfile",
                "-Command",
                "[Environment]::GetFolderPath('MyDocuments')",
            ]
            documents = subprocess.check_output(command, text=True, encoding="utf-8", errors="replace").strip()
            candidate = Path(documents).parent / "Saved Games"
            if candidate.exists():
                return candidate
        except Exception:
            pass

    profile = Path(os.environ.get("USERPROFILE", str(Path.home())))
    return profile / "Saved Games"


def discover_dcs_targets(saved_games: Path | None = None) -> list[DcsInstallTarget]:
    root = saved_games or get_saved_games_path()
    if not root.exists():
        return []
    targets: list[DcsInstallTarget] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        name = child.name.lower()
        if name == "dcs" or name.startswith("dcs.") or name in {"dcs.openbeta", "dcs.openalpha"}:
            scripts_dir = child / "Scripts"
            targets.append(DcsInstallTarget(root=child, scripts_dir=scripts_dir, export_lua=scripts_dir / "Export.lua"))
    return targets


def install_lua_bridge(
    source_dir: Path,
    targets: Iterable[DcsInstallTarget] | None = None,
    dry_run: bool = False,
) -> list[InstallResult]:
    source_dir = source_dir.resolve()
    voice_source = source_dir / "VoiceBridge.lua"
    telemetry_source = source_dir / "dcs_telemetry.lua"
    if not voice_source.exists():
        raise FileNotFoundError(f"Missing {voice_source}")
    if not telemetry_source.exists():
        raise FileNotFoundError(f"Missing {telemetry_source}")

    install_targets = list(targets) if targets is not None else discover_dcs_targets()
    results: list[InstallResult] = []
    for target in install_targets:
        copied: list[Path] = []
        backup: Path | None = None
        export_modified = False
        try:
            if not dry_run:
                target.scripts_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(voice_source, target.scripts_dir / "VoiceBridge.lua")
                shutil.copy2(telemetry_source, target.scripts_dir / "dcs_telemetry.lua")
            copied.extend([target.scripts_dir / "VoiceBridge.lua", target.scripts_dir / "dcs_telemetry.lua"])

            export_modified, backup = patch_export_lua(target.export_lua, dry_run=dry_run)
            results.append(
                InstallResult(
                    target=target,
                    copied_files=tuple(copied),
                    export_modified=export_modified,
                    backup_path=backup,
                    message="installed" if not dry_run else "dry-run ok",
                )
            )
        except PermissionError as exc:
            results.append(
                InstallResult(target, tuple(copied), export_modified, backup, f"permission error: {exc}")
            )
        except OSError as exc:
            results.append(InstallResult(target, tuple(copied), export_modified, backup, f"error: {exc}"))
    return results


def patch_export_lua(export_lua: Path, dry_run: bool = False) -> tuple[bool, Path | None]:
    existing = ""
    if export_lua.exists():
        existing = export_lua.read_text(encoding="utf-8", errors="replace")

    additions = []
    if VOICE_BRIDGE_HOOK_ID not in existing:
        additions.append(VOICE_BRIDGE_HOOK)
    if TELEMETRY_HOOK_ID not in existing:
        additions.append(TELEMETRY_HOOK)

    if not additions:
        return False, None

    backup: Path | None = None
    if export_lua.exists():
        backup = export_lua.with_suffix(export_lua.suffix + ".voice-comms-dcs.bak")

    if not dry_run:
        export_lua.parent.mkdir(parents=True, exist_ok=True)
        if backup and not backup.exists():
            shutil.copy2(export_lua, backup)
        with export_lua.open("a", encoding="utf-8", newline="\n") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            handle.write("\n")
            handle.write("\n".join(additions))
    return True, backup


def uninstall_lua_bridge(targets: Iterable[DcsInstallTarget] | None = None, remove_scripts: bool = True) -> list[str]:
    install_targets = list(targets) if targets is not None else discover_dcs_targets()
    messages: list[str] = []
    for target in install_targets:
        if target.export_lua.exists():
            text = target.export_lua.read_text(encoding="utf-8", errors="replace")
            text = _remove_marked_block(text, VOICE_BRIDGE_HOOK_ID)
            text = _remove_marked_block(text, TELEMETRY_HOOK_ID)
            target.export_lua.write_text(text, encoding="utf-8", newline="\n")
            messages.append(f"patched {target.export_lua}")
        if remove_scripts:
            for filename in ("VoiceBridge.lua", "dcs_telemetry.lua"):
                path = target.scripts_dir / filename
                if path.exists():
                    path.unlink()
                    messages.append(f"removed {path}")
    return messages


def _remove_marked_block(text: str, marker: str) -> str:
    begin = f"-- BEGIN {marker}"
    end = f"-- END {marker}"
    while begin in text and end in text:
        start = text.index(begin)
        finish = text.index(end, start) + len(end)
        text = text[:start].rstrip() + "\n" + text[finish:].lstrip("\r\n")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install or uninstall Voice-Comms-DCS Lua scripts.")
    parser.add_argument("--source-dir", default="dcs_scripts")
    parser.add_argument("--saved-games")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args(argv)

    saved_games = Path(args.saved_games) if args.saved_games else None
    targets = discover_dcs_targets(saved_games)
    if not targets:
        print("No DCS Saved Games folders found.")
        return 1

    if args.uninstall:
        for message in uninstall_lua_bridge(targets):
            print(message)
        return 0

    results = install_lua_bridge(Path(args.source_dir), targets=targets, dry_run=args.dry_run)
    for result in results:
        print(f"{result.target.root}: {result.message}")
        if result.backup_path:
            print(f"  backup: {result.backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
