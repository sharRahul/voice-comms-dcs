from __future__ import annotations

from pathlib import Path


def test_dependency_security_files_exist() -> None:
    assert Path("constraints.txt").is_file()
    assert Path("requirements-dev.txt").is_file()
    assert Path("docs/dependency_security.md").is_file()
    assert Path("docs/model_integrity.md").is_file()


def test_build_script_requires_constraints() -> None:
    script = Path("build/build_exe.ps1").read_text(encoding="utf-8")
    assert "$ConstraintsPath" in script
    assert "Constraints file not found" in script
    assert "pip install -r $RequirementsPath -c $ConstraintsPath" in script


def test_ci_and_env_examples_exist() -> None:
    assert Path(".github/workflows/ci.yml").is_file()
    assert Path(".env.example").is_file()
    assert Path("config/model_hashes.example.json").is_file()


def test_env_is_ignored_but_example_is_allowed() -> None:
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    assert "\n.env\n" in gitignore
    assert "!.env.example" in gitignore


def test_srs_default_config_disables_custom_command_templates() -> None:
    config = Path("config/srs/srs_audio.json").read_text(encoding="utf-8")
    assert '"allow_custom_command_template": false' in config
    assert '"command_template"' not in config
