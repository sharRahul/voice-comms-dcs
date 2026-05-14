from __future__ import annotations

import shutil
from pathlib import Path

DEFAULT_COMMANDS_CONFIG = Path("config") / "commands.json"
DEFAULT_COMMANDS_TEMPLATE = Path("config") / "commands.example.json"


def ensure_user_config(config_path: Path, template_path: Path) -> Path:
    """Create a local user config from a template without overwriting an existing file."""

    if config_path.exists():
        return config_path
    if not template_path.exists():
        return config_path

    config_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template_path, config_path)
    return config_path


def _normalise_for_compare(path: Path) -> str:
    return path.as_posix().replace("//", "/").rstrip("/").lower()


def is_default_config_path(config_path: Path) -> bool:
    """Return true when a path points at the app's default local commands.json."""

    candidate = _normalise_for_compare(config_path)
    default = _normalise_for_compare(DEFAULT_COMMANDS_CONFIG)
    if candidate == default:
        return True
    if not config_path.is_absolute():
        return False
    try:
        return config_path.resolve() == DEFAULT_COMMANDS_CONFIG.resolve()
    except OSError:
        return False


def ensure_default_config(config_path: str | Path) -> Path:
    """Create the default local config from commands.example.json when it is missing."""

    path = Path(config_path)
    if is_default_config_path(path):
        return ensure_user_config(path, DEFAULT_COMMANDS_TEMPLATE)
    return path
