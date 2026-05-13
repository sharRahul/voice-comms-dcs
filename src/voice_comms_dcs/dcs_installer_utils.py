from __future__ import annotations

import argparse
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


def get_saved_games_candidates() -> list[Path]:
    """Resolve likely Saved Games paths, including moved Shell Folder locations.

    The first candidates come from Windows User Shell Folders/Shell Folders registry values. This
    is more reliable than assuming `%USERPROFILE%\\Saved Games` when the user moved Saved Games
    to another drive.
    """
    candidates: list[Path] = []

    if sys.platform.startswith("win"):
        try:
            import winreg

            keys = [
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"),
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"),
            ]
            for root_key, key_path in keys:
                try:
                    with winreg.OpenKey(root_key, key_path) as key:
                        for value_name in ("{4C5C32FF-BB9D-43B0-B5B4-2D72E54EAAA4}", "SavedGames", "Saved Games"):
                            try:
                                value, _value_type = winreg.QueryValueEx(key, value_name)
                                expanded = os.path.expandvars(str(value))
                                candidates.append(Path(expanded))
                            except FileNotFoundError:
                                continue
                except FileNotFoundError:
                    continue
        except Exception:
            pass

    profile = Path(os.environ.get("USERPROFILE", str(Path.home())))
    candidates.extend([
        profile / "Saved Games",
        Path.home() / "Saved Games",
    ])

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = candidate.expanduser()
        key = str(resolved).lower()
        if key not in seen:
            seen.add(key)
            unique.append(resolved)
    return unique


def get_saved_games_path() -> Path:
    for candidate in get_saved_games_candidates():
        if candidate.exists():
            return candidate
    return get_saved_games_candidates()[0]


def discover_dcs_targets(saved_games: Path | None = None) -> list[DcsInstallTarget]:
    roots = [saved_games] if saved_games else get_saved_games_candidates()
    targets: list[DcsInstallTarget] = []
    seen: set[str] = set()
    for root in roots:
        if root is None or not root.exists():
            continue
        for child in root.iterdir():
            if not child.is_dir():
                continue
            name = child.name.lower()
            if name == "dcs" or name.startswith("dcs.") or name in {"dcs.openbeta", "dcs.openalpha"}:
                key = str(child.resolve()).lower()
                if key in seen:
                    continue
                seen.add(key)
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
        print("Searched:")
        for path in get_saved_games_candidates():
            print(f"  {path}")
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
