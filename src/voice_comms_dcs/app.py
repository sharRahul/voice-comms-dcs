from __future__ import annotations

from dataclasses import dataclass

from .config import AppConfig
from .matcher import CommandMatcher, MatchResult
from .network import DcsUdpClient, UdpTarget


@dataclass(frozen=True)
class DispatchResult:
    matched: bool
    transcript: str
    payload: str | None = None
    match: MatchResult | None = None
    reason: str = ""


class VoiceCommsService:
    """Application service that turns recognised text into a DCS UDP command."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.matcher = CommandMatcher.from_commands(config.commands)
        self.client = DcsUdpClient(
            UdpTarget(config.dcs_host, config.dcs_port),
            reliability=config.udp_reliability,
        )

    def close(self) -> None:
        self.client.close()

    def handle_transcript(self, transcript: str) -> DispatchResult:
        match = self.matcher.find_best_match(
            transcript=transcript,
            min_confidence=self.config.min_confidence,
        )
        if match is None:
            return DispatchResult(
                matched=False,
                transcript=transcript,
                reason="No configured phrase matched above the confidence threshold.",
            )
        return self.dispatch_match(transcript, match)

    def dispatch_match(self, transcript: str, match: MatchResult) -> DispatchResult:
        payload = self.client.send_command(match.command)
        return DispatchResult(
            matched=True,
            transcript=transcript,
            payload=payload,
            match=match,
        )
