# Aircraft-specific RWR adapter specification

## Purpose

Radar Warning Receiver (RWR) behaviour differs between DCS aircraft. Western aircraft, Soviet/Russian aircraft, FC3 modules, and full-fidelity modules can present different symbols, threat categories, update rates, and available export data. Nimbus needs an adapter layer that normalises those aircraft-specific details into clear cockpit callouts.

Example output:

```text
SA-10 at 4 o'clock, 15 miles.
MiG-29 spike, 11 o'clock.
Missile launch, right side.
```

## Telemetry export shape

The DCS telemetry exporter should provide RWR data under the tactical section:

```json
{
  "tactical": {
    "rwr_alerts": [
      {
        "symbol": "10",
        "threat_type": "sam",
        "label": "SA-10",
        "bearing_deg": 120,
        "direction": "4 o'clock",
        "range_nm": 15,
        "severity": "spike"
      }
    ],
    "rwr_profile": "fa18c",
    "rwr_summary": "spike SA-10 4 o'clock"
  }
}
```

Expected fields:

| Field | Type | Description |
|---|---|---|
| `symbol` | string | Raw aircraft/module RWR symbol where available. |
| `threat_type` | string | Normalised category such as `sam`, `fighter`, `aaa`, `missile`, or `unknown`. |
| `label` | string | Human-readable emitter label such as `SA-10`, `MiG-29`, or `Unknown search radar`. |
| `bearing_deg` | number/null | Bearing from ownship in degrees, if available. |
| `direction` | string/null | Human-friendly clock direction, if derived or exported. |
| `range_nm` | number/null | Estimated range in nautical miles, if available. Many RWRs do not provide reliable range. |
| `severity` | string | `search`, `track`, `spike`, `launch`, `missile`, or `critical`. |

Default telemetry update rate should remain 10 Hz. RWR callouts should be rate-limited above the adapter layer so Nimbus does not repeatedly speak the same threat every telemetry frame.

## Adapter responsibility

An RWR adapter converts raw telemetry into stable callout data for Nimbus. It should:

1. Identify the active aircraft/profile.
2. Map raw DCS/module threat symbols to normalised threat labels.
3. Preserve severity from the module where available.
4. Derive a clock direction from bearing when the export only provides degrees.
5. Avoid inventing range when the aircraft/module does not export it.
6. Prioritise launch/missile/critical threats over search radars.
7. Produce short text suitable for Piper TTS.

## Proposed Python interface

```python
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RWRContact:
    symbol: str
    threat_type: str
    label: str
    bearing_deg: float | None
    direction: str | None
    range_nm: float | None
    severity: str


class RWRAdapter(Protocol):
    aircraft_id: str

    def parse_rwr_contacts(self, telemetry: dict) -> list[RWRContact]:
        """Return normalised RWR contacts from one telemetry snapshot."""

    def format_callout(self, contact: RWRContact, language: str) -> str:
        """Return a short spoken callout for the selected Nimbus language."""
```

The current repository contains `src/voice_comms_dcs/rwr_adapters.py`, which already implements a registry-based normalisation layer. The interface above is the next feature boundary for richer aircraft-specific formatting and multilingual speech.

## Threat mapping examples

| Raw symbol | Example mapping | Severity |
|---|---|---|
| `10` | SA-10 / S-300 search or track radar | `spike` or `track` |
| `11` | SA-11 / Buk | `spike` |
| `15` | SA-15 / Tor | `track` |
| `29` | MiG-29 | `spike` |
| `F16` | F-16C radar | `spike` |
| `M` / `MSL` | Missile launch | `missile` |

Mappings must be profile-specific because the same raw symbol can be displayed differently across modules.

## Aircraft priority

Prioritise these profiles first:

1. **F/A-18C**: common multiplayer aircraft, full-fidelity, Western RWR presentation.
2. **F-16C**: common SEAD/DEAD platform, Western RWR presentation.
3. **A-10C II**: CAS-focused aircraft where threat callouts are valuable and workload is high.
4. **Su-27 / Su-33**: Eastern/FC3 RWR behaviour and symbology.
5. **MiG-29**: Eastern/FC3 RWR behaviour, high relevance to red-air scenarios.

Western and Eastern aircraft should not share a single mapping table unless the raw export has already been normalised. Keep profile-specific mapping files under `config/rwr/` so pilots can update them without changing Python code.

## Callout formatting

Suggested English format rules:

- If range and direction are available: `{label} at {direction}, {range_nm:.0f} miles.`
- If only direction is available: `{label} {severity}, {direction}.`
- If only bearing is available: `{label} {severity}, bearing {bearing_deg:.0f}.`
- If only threat label is available: `{label} {severity}.`
- For missile/launch severity: `Missile launch, {direction}.`

Multilingual support should be implemented with the same language codes used by Nimbus: `en`, `zh`, `ko`, `fr`, `ru`, and `es`. If a translation is missing, fall back to English rather than suppressing the warning.

## Integration with Nimbus TTS

The intended callout chain is:

```text
DCS telemetry snapshot
  -> RWR adapter normalisation
  -> Nimbus context window and priority warning logic
  -> deterministic threat callout decision
  -> Piper TTS through radio_voice.py
  -> WebRTC speaker/dashboard output
  -> optional SRS adapter when enabled
```

RWR callouts should enter Nimbus before generic LLM conversation. Threat warnings are safety/workload information and must remain deterministic. The LLM may explain a threat only when the pilot asks an unrecognised question and telemetry context is available.

## Rate limiting and suppression

To avoid noisy cockpit audio:

- Speak missile/launch threats immediately.
- Suppress duplicate callouts for the same symbol/direction/severity for a short interval.
- Allow repeated reminders for persistent critical threats at a slower cadence.
- Do not speak search radar contacts continuously.
- Reset suppression when severity increases, for example from `search` to `launch`.

## Open questions

- Which DCS modules expose RWR data reliably through `LoGetRWRInfo` or equivalent export calls?
- Which fields are available per aircraft: symbol, azimuth, lock/launch status, and range?
- How should FC3 aircraft be distinguished when telemetry exposes limited aircraft identifiers?
- Should community mapping files be accepted, and how should they be validated?
- How much RWR data should the dashboard expose when privacy mode hides tactical telemetry?

## Acceptance criteria

1. At least F/A-18C, F-16C, A-10C II, Su-27/33, and MiG-29 profiles can be selected or auto-resolved.
2. Unknown symbols degrade to `Unknown threat` rather than failing.
3. Missile/launch severity produces an immediate deterministic Nimbus warning.
4. Callouts are short enough for combat use and respect the current Nimbus language.
5. Duplicate threat suppression prevents repeated speech every telemetry frame.
6. Unit tests cover mapping, unknown fallback, direction formatting, and severity ordering.
7. The dashboard can show the active RWR profile and current top threat without exposing raw tactical fields when privacy mode disables them.
