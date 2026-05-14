# DCS Lua timing guide

This guide explains how the Nimbus Lua bridge and telemetry exporter should behave inside DCS World. The goal is simple: collect cockpit data and process command packets without adding measurable frame-time cost.

## Export.lua execution model

DCS loads `Saved Games\DCS\Scripts\Export.lua` during mission runtime and calls well-known Lua export callbacks as part of the simulation/render loop. Nimbus installs wrapper callbacks around existing functions rather than replacing them:

- `LuaExportStart` starts Lua-side sockets when the mission begins.
- `LuaExportAfterNextFrame` is called after each simulation frame and is used for telemetry export and UDP command polling.
- `LuaExportStop` closes Lua-side sockets when the mission stops.

Because these callbacks run on the DCS simulation path, they must finish quickly and must not wait on network, disk, shell, or long computation.

## Why blocking Export.lua code hurts frame time

A blocking call inside `Export.lua` pauses the DCS simulation thread. Even a short wait can show up as a frame-time spike because DCS cannot finish the current frame until the Lua callback returns.

Avoid these patterns in Export.lua code:

- Waiting for a UDP/TCP acknowledgement before returning.
- Synchronous HTTP calls.
- `os.execute`, shell commands, or external process launches.
- Disk writes on every frame.
- Long loops over mission objects without throttling.
- Large JSON payloads or complex string work every frame.

At 60 FPS, one frame has about 16.7 ms. At 90 FPS, one frame has about 11.1 ms. Export hooks should aim to complete in under about 1 ms so there is enough headroom for DCS, other scripts, SRS, Tacview, and mission logic.

## Telemetry path: non-blocking UDP send

`dcs_telemetry.lua` sends compact JSON-over-UDP telemetry to the local Python listener. It uses these safeguards:

- UDP is created during `LuaExportStart`.
- `udp:settimeout(0)` makes the socket non-blocking.
- Telemetry is throttled to `0.10` seconds by default, which is 10 Hz.
- Each packet is sent fire-and-forget with no acknowledgement and no retry.
- Data collection is wrapped with `pcall` helpers so missing DCS APIs produce partial telemetry rather than breaking the export loop.

This means telemetry can be dropped if the Python receiver is not running. That is acceptable because each packet is a live snapshot and the next packet replaces the previous one.

## Command path: non-blocking UDP receive and DCS flags

`VoiceBridge.lua` receives command packets from the Python companion app on local UDP port `10308` by default. It also sets `udp:settimeout(0)`, then polls packets from `LuaExportAfterNextFrame`.

The command bridge is intentionally narrow:

1. Read all immediately available UDP packets without waiting.
2. Reject packets with the wrong protocol prefix or unsafe command identifiers.
3. Accept supported actions such as `flag` and validated named commands.
4. Set mission user flags through `trigger.action.setUserFlag` when available, with a tightly formatted `net.dostring_in` fallback for mission environments that need it.
5. Return to DCS without blocking for a response from Python.

The v2 command protocol supports acknowledgement packets, but the Lua side still sends them opportunistically over non-blocking UDP. The export callback must never wait for Python to receive or process the acknowledgement.

## Timing constraints

Keep these practical limits in mind:

- Export callbacks should normally finish in under about 1 ms.
- Telemetry should stay at 10 Hz unless a specific mission has been benchmarked at a higher rate.
- Lua callbacks should allocate as little as possible per frame.
- JSON payloads should stay compact and avoid full mission-state dumps.
- Network I/O must use non-blocking sockets.
- Command handlers must not run arbitrary mission scripts from packet contents.

The 1 ms target is a project engineering budget rather than a DCS-enforced hard limit. The lower the callback cost, the less likely Nimbus is to contribute to visible stutter in heavy missions.

## Troubleshooting blocking Export.lua behaviour

Common symptoms include:

- Frame-time spikes visible in the DCS FPS counter or frame-time overlay.
- Short audio stutters when telemetry export runs.
- Input lag when pressing HOTAS/PTT or issuing radio commands.
- DCS pauses when the Python companion app is closed or restarted.
- Stutter that disappears after temporarily removing `Export.lua` hooks.

Likely causes:

- A socket was created without `settimeout(0)`.
- A script waits for a network response inside `LuaExportAfterNextFrame`.
- Another export consumer is doing heavy work before or after the Nimbus wrapper.
- Telemetry interval was reduced too aggressively.
- A mission-specific command handler performs expensive work synchronously.

## How to test

Use one of these approaches before raising telemetry frequency or adding new Lua-side work:

1. Enable the built-in DCS FPS/frame-time display and compare a mission with Nimbus hooks enabled and disabled.
2. Use external frame-time tools such as CapFrameX, PresentMon, or a GPU driver overlay to look for regular spikes at the telemetry interval.
3. Temporarily increase `DcsTelemetry.interval` and confirm frame spikes reduce or disappear.
4. Run DCS with the Python receiver closed; telemetry sends should not block and command polling should continue returning immediately.
5. Add timing logs only for short diagnostic runs. Do not leave per-frame logging enabled.

A healthy configuration should show no obvious frame-time rhythm at the telemetry interval and no pause when the companion app is not listening.
