from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .app import VoiceCommsService
from .config import ConfigError, load_config
from .ui import VoiceCommsUi


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="voice-comms-dcs",
        description="Voice-to-DCS bridge for custom F10-style mission commands.",
    )
    parser.add_argument(
        "--config",
        default="config/commands.json",
        help="Path to commands.json. Defaults to config/commands.json.",
    )
    parser.add_argument(
        "--test-phrase",
        help="Run one command-matching and UDP dispatch test without opening the GUI.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

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
