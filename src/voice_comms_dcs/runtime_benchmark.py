from __future__ import annotations

import argparse
import csv
import json
import socket
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import requests


@dataclass(frozen=True)
class ProbeResult:
    name: str
    success: bool
    samples: int
    min_ms: float | None = None
    median_ms: float | None = None
    p95_ms: float | None = None
    max_ms: float | None = None
    message: str = ""


@dataclass(frozen=True)
class BenchmarkReport:
    started_at_unix: float
    duration_seconds: float
    results: list[ProbeResult]
    recommendations: list[str]


class RuntimeBenchmark:
    """Runtime probes for DCS + Nimbus performance tuning.

    The benchmark is intentionally non-invasive. It does not control DCS. It measures local bridge
    responsiveness, telemetry freshness, Ollama availability, UDP command latency to localhost,
    and optional dashboard health latency.
    """

    def __init__(
        self,
        bridge_url: str = "http://127.0.0.1:8765",
        ollama_url: str = "http://127.0.0.1:11434",
        command_host: str = "127.0.0.1",
        command_port: int = 10308,
        samples: int = 20,
    ) -> None:
        self.bridge_url = bridge_url.rstrip("/")
        self.ollama_url = ollama_url.rstrip("/")
        self.command_host = command_host
        self.command_port = command_port
        self.samples = max(1, samples)

    def run(self) -> BenchmarkReport:
        started = time.time()
        results = [
            self.probe_dashboard_health(),
            self.probe_telemetry_freshness(),
            self.probe_udp_command_send(),
            self.probe_ollama_tags(),
        ]
        recommendations = build_recommendations(results)
        return BenchmarkReport(
            started_at_unix=started,
            duration_seconds=time.time() - started,
            results=results,
            recommendations=recommendations,
        )

    def probe_dashboard_health(self) -> ProbeResult:
        latencies: list[float] = []
        failures = 0
        last_error = ""
        for _ in range(self.samples):
            started = time.perf_counter()
            try:
                response = requests.get(f"{self.bridge_url}/health", timeout=1.0)
                response.raise_for_status()
                _payload = response.json()
                latencies.append((time.perf_counter() - started) * 1000.0)
            except Exception as exc:
                failures += 1
                last_error = str(exc)
            time.sleep(0.05)
        return summarise("dashboard_health", latencies, failures, last_error)

    def probe_telemetry_freshness(self) -> ProbeResult:
        try:
            response = requests.get(f"{self.bridge_url}/api/status", timeout=1.0)
            response.raise_for_status()
            payload = response.json()
            age = float(payload.get("telemetry_age_seconds", float("inf")))
            success = age < 2.0
            return ProbeResult(
                name="telemetry_freshness",
                success=success,
                samples=1,
                min_ms=age * 1000.0 if age != float("inf") else None,
                median_ms=age * 1000.0 if age != float("inf") else None,
                p95_ms=age * 1000.0 if age != float("inf") else None,
                max_ms=age * 1000.0 if age != float("inf") else None,
                message="telemetry fresh" if success else f"telemetry stale: {age:.2f}s",
            )
        except Exception as exc:
            return ProbeResult("telemetry_freshness", False, 0, message=str(exc))

    def probe_udp_command_send(self) -> ProbeResult:
        latencies: list[float] = []
        failures = 0
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            for index in range(self.samples):
                payload = f"VCDCS|benchmark_{index}|flag|5999|0".encode("utf-8")
                started = time.perf_counter()
                try:
                    sent = sock.sendto(payload, (self.command_host, self.command_port))
                    if sent != len(payload):
                        failures += 1
                    else:
                        latencies.append((time.perf_counter() - started) * 1000.0)
                except OSError:
                    failures += 1
                time.sleep(0.01)
        finally:
            sock.close()
        return summarise("udp_command_send", latencies, failures, "UDP send failed")

    def probe_ollama_tags(self) -> ProbeResult:
        latencies: list[float] = []
        failures = 0
        last_error = ""
        for _ in range(min(self.samples, 5)):
            started = time.perf_counter()
            try:
                response = requests.get(f"{self.ollama_url}/api/tags", timeout=1.0)
                response.raise_for_status()
                latencies.append((time.perf_counter() - started) * 1000.0)
            except Exception as exc:
                failures += 1
                last_error = str(exc)
            time.sleep(0.05)
        return summarise("ollama_tags", latencies, failures, last_error)


def summarise(name: str, latencies: list[float], failures: int, last_error: str = "") -> ProbeResult:
    if not latencies:
        return ProbeResult(name=name, success=False, samples=0, message=last_error or "no successful samples")
    sorted_values = sorted(latencies)
    p95_index = min(len(sorted_values) - 1, int(round((len(sorted_values) - 1) * 0.95)))
    return ProbeResult(
        name=name,
        success=failures == 0,
        samples=len(latencies),
        min_ms=min(latencies),
        median_ms=statistics.median(latencies),
        p95_ms=sorted_values[p95_index],
        max_ms=max(latencies),
        message=f"{failures} failures" if failures else "ok",
    )


def build_recommendations(results: list[ProbeResult]) -> list[str]:
    by_name = {result.name: result for result in results}
    recommendations: list[str] = []
    health = by_name.get("dashboard_health")
    if health and (not health.success or (health.p95_ms or 0) > 100.0):
        recommendations.append("Dashboard health latency is high. Keep the bridge bound to localhost, close unused browser tabs, and reduce dashboard polling if needed.")
    telemetry = by_name.get("telemetry_freshness")
    if telemetry and not telemetry.success:
        recommendations.append("Telemetry is stale. Check Export.lua hooks, DCS mission running state, UDP port 10309, and firewall rules.")
    ollama = by_name.get("ollama_tags")
    if ollama and not ollama.success:
        recommendations.append("Ollama is unavailable. Start Ollama or disable LLM features for command-only operation.")
    elif ollama and (ollama.p95_ms or 0) > 250.0:
        recommendations.append("Ollama API latency is high. Use qwen2.5:0.5b, reduce num_ctx, or run the LLM on CPU threads that do not starve DCS.")
    udp = by_name.get("udp_command_send")
    if udp and not udp.success:
        recommendations.append("UDP command sending failed. Check local firewall and DCS Lua bridge listener port 10308.")
    if not recommendations:
        recommendations.append("Runtime probes look healthy. Keep telemetry at 10 Hz and upgrade models only after flight testing.")
    return recommendations


def write_report(report: BenchmarkReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
    csv_path = output.with_suffix(".csv")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "success", "samples", "min_ms", "median_ms", "p95_ms", "max_ms", "message"])
        writer.writeheader()
        for result in report.results:
            writer.writerow(asdict(result))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local Voice-Comms-DCS runtime benchmark probes.")
    parser.add_argument("--bridge-url", default="http://127.0.0.1:8765")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--command-host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=10308)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--output", default="build_output/runtime_benchmark.json")
    args = parser.parse_args(argv)

    benchmark = RuntimeBenchmark(
        bridge_url=args.bridge_url,
        ollama_url=args.ollama_url,
        command_host=args.command_host,
        command_port=args.command_port,
        samples=args.samples,
    )
    report = benchmark.run()
    write_report(report, Path(args.output))
    print(json.dumps(asdict(report), indent=2))
    return 0 if all(result.success for result in report.results if result.name != "telemetry_freshness") else 1


if __name__ == "__main__":
    raise SystemExit(main())
