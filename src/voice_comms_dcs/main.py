from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .app import VoiceCommsService
from .config import ConfigError, load_config
from .dependency_manager import DependencyManager, DependencyPlan, validate_languages
from .dcs_installer_utils import discover_dcs_targets, install_lua_bridge, uninstall_lua_bridge
from .ui import VoiceCommsUi


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="voice-comms-dcs",
        description="Voice-to-DCS bridge and Nimbus local AI cockpit assistant.",
    )
    parser.add_argument("--config", default="config/commands.json")
    parser.add_argument("--test-phrase")
    parser.add_argument("--install-lua", action="store_true")
    parser.add_argument("--uninstall-lua", action="store_true")
    parser.add_argument("--dcs-source-dir", default="dcs_scripts")
    parser.add_argument("--saved-games")
    parser.add_argument("--setup-dependencies", action="store_true")
    parser.add_argument("--setup-dependencies-ui", action="store_true")
    parser.add_argument("--remove-dependencies", action="store_true")
    parser.add_argument("--languages", nargs="+", default=None, choices=["en", "zh", "ko", "fr", "ru", "es"])
    parser.add_argument("--ollama-model", default="qwen2.5:0.5b")
    parser.add_argument("--whisper-quality", choices=["tiny", "base"], default="base")
    parser.add_argument("--skip-ollama", action="store_true")
    parser.add_argument("--skip-whisper", action="store_true")
    parser.add_argument("--skip-piper", action="store_true")
    parser.add_argument("--benchmark", action="store_true", help="Run local runtime benchmark probes.")
    parser.add_argument("--benchmark-samples", type=int, default=20)
    parser.add_argument("--benchmark-output", default="build_output/runtime_benchmark.json")
    parser.add_argument("--generate-manifest", action="store_true", help="Generate release checksum manifest.")
    parser.add_argument("--verify-manifest", action="store_true", help="Verify an existing release checksum manifest.")
    parser.add_argument("--manifest-output", default="build_output/release_manifest.json")
    parser.add_argument("--manifest-root", default=".")
    parser.add_argument("--generate-model-manifest", action="store_true", help="Generate checksum manifest for downloaded AI models.")
    parser.add_argument("--verify-model-manifest", action="store_true", help="Verify downloaded AI model checksum manifest.")
    parser.add_argument("--model-manifest-output", default="build_output/model_manifest.json")
    parser.add_argument("--model-manifest-root", default=".")
    return parser


def _write_model_manifest(root: Path, output: Path) -> None:
    from .model_manifest import build_model_manifest, write_model_manifest

    manifest = build_model_manifest(root=root)
    write_model_manifest(manifest, output)
    print(f"Wrote {output}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.install_lua or args.uninstall_lua:
        saved_games = Path(args.saved_games) if args.saved_games else None
        targets = discover_dcs_targets(saved_games)
        if not targets:
            print("No DCS Saved Games folders found.", file=sys.stderr)
            return 1
        if args.uninstall_lua:
            for message in uninstall_lua_bridge(targets):
                print(message)
            return 0
        results = install_lua_bridge(Path(args.dcs_source_dir), targets=targets)
        for result in results:
            print(f"{result.target.root}: {result.message}")
            if result.backup_path:
                print(f"  backup: {result.backup_path}")
        return 0

    if args.setup_dependencies_ui:
        from .dependency_setup_ui import DependencySetupUi

        app = DependencySetupUi(
            languages=validate_languages(args.languages or ["en"]),
            ollama_model=args.ollama_model,
            whisper_quality=args.whisper_quality,
        )
        app.mainloop()
        return 1 if app.failed else 0

    if args.setup_dependencies or args.remove_dependencies:
        languages = validate_languages(args.languages or ["en"])
        manager = DependencyManager(root=".")
        if args.remove_dependencies:
            for path in manager.uninstall_downloaded_models(languages):
                print(f"removed {path}")
            return 0
        manager.install(
            DependencyPlan(
                languages=languages,
                ollama_model=args.ollama_model,
                whisper_quality=args.whisper_quality,
                include_ollama=not args.skip_ollama,
                include_whisper=not args.skip_whisper,
                include_piper=not args.skip_piper,
            )
        )
        _write_model_manifest(Path(args.model_manifest_root).resolve(), Path(args.model_manifest_output))
        return 0

    if args.benchmark:
        from .runtime_benchmark import RuntimeBenchmark, write_report
        import json
        from dataclasses import asdict

        report = RuntimeBenchmark(samples=args.benchmark_samples).run()
        write_report(report, Path(args.benchmark_output))
        print(json.dumps(asdict(report), indent=2))
        return 0

    if args.generate_manifest or args.verify_manifest:
        from .release_manifest import build_manifest, default_release_paths, verify_manifest, write_manifest

        root = Path(args.manifest_root).resolve()
        output = Path(args.manifest_output)
        if args.verify_manifest:
            ok, failures = verify_manifest(output, root)
            if failures:
                for failure in failures:
                    print(failure)
            else:
                print(f"Manifest verified: {output}")
            return 0 if ok else 1
        manifest = build_manifest(default_release_paths(root), root=root)
        write_manifest(manifest, output)
        print(f"Wrote {output}")
        return 0

    if args.generate_model_manifest or args.verify_model_manifest:
        from .model_manifest import build_model_manifest, verify_model_manifest, write_model_manifest

        root = Path(args.model_manifest_root).resolve()
        output = Path(args.model_manifest_output)
        if args.verify_model_manifest:
            ok, failures = verify_model_manifest(output, root)
            if failures:
                for failure in failures:
                    print(failure)
            else:
                print(f"Model manifest verified: {output}")
            return 0 if ok else 1
        manifest = build_model_manifest(root=root)
        write_model_manifest(manifest, output)
        print(f"Wrote {output}")
        return 0

    config_path = Path(args.config)
    try:
        config = load_config(config_path)
    except (ConfigError, OSError, ValueError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    if args.test_phrase:
        service = VoiceCommsService(config)
        try:
            result = service.handle_transcript(args.test_phrase)
        finally:
            service.close()

        if not result.matched:
            print(f"No match: {result.reason}")
            return 1

        assert result.match is not None
        print(
            "Matched "
            f"{result.match.command.id} "
            f"confidence={result.match.confidence:.2f} "
            f"payload={result.payload}"
        )
        return 0

    app = VoiceCommsUi(config=config, config_path=str(config_path))
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
