# Security and Limitations

## Security model

Voice-Comms-DCS is designed around a narrow command contract. The desktop app sends known command IDs and action parameters. The Lua bridge validates the packet and performs only supported action types.

The project intentionally avoids these unsafe patterns:

- Sending arbitrary Lua code over UDP.
- Executing speech transcripts directly.
- Automatically clicking dynamic F10 menu positions by keyboard macro.
- Trusting unvalidated network packets.

## Localhost assumption

The default configuration sends UDP to:

```text
127.0.0.1:10308
```

This means the app and DCS are expected to run on the same Windows machine. If you choose to bind beyond localhost, treat the bridge as a network-exposed control surface and restrict access with host firewall rules.

## Mission flag safety

Use a reserved flag range for voice commands, for example:

```text
5100-5199: Voice-Comms-DCS commands
```

Do not reuse these flags for unrelated mission logic. Always reset one-shot flags after handling them.

## STT privacy

The default Vosk backend is offline. Audio is processed locally. Future cloud STT backends should be opt-in and documented clearly.

## Known limitations

### Dynamic F10 menus

DCS F10 menus can be dynamic and mission-specific. This project does not guarantee automatic discovery or clicking of arbitrary F10 items. Use mission flags or a mission-side command registry for reliable behavior.

### DCS Lua environment differences

DCS has different Lua environments for mission scripts, export scripts, and hooks. Socket availability and mission API access can vary depending on where the bridge is loaded and how the user's DCS installation is configured.

Preferred integration for v0.1:

1. Load the UDP bridge where sockets are available.
2. Convert received voice commands into mission flags.
3. Handle the final action inside mission triggers or mission Lua.

### Multiplayer servers

Server-side scripting restrictions may prevent arbitrary client-side mission actions. For multiplayer, use server-approved mission scripting or a server-hosted bridge.

### False positives

Speech recognition can mishear commands. Use short but distinct phrases and keep `min_confidence` high for safety-critical actions such as abort, jettison, or weapons-related mission actions.

## Hardening checklist

- Keep UDP bound to localhost unless there is a strong reason not to.
- Use numeric mission flags only.
- Keep voice command actions deterministic.
- Do not use a phrase like `fire` for destructive or irreversible actions.
- Keep a visible UI confirmation log.
- Add push-to-talk before using the tool in complex combat missions.
- Back up `Export.lua` before modifying it.
