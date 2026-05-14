# Release signing

Release integrity uses two layers:

1. Authenticode signing for Windows `.exe` and `.dll` files.
2. Detached cryptographic signatures for release and model manifest JSON files.

Checksums prove file integrity. Detached signatures prove the manifest was produced by a holder of the release signing key.

## Environment variables

Set these on the release machine only:

```powershell
$env:VCDCS_SIGN_CERT_THUMBPRINT = "<code signing certificate thumbprint>"
$env:VCDCS_MANIFEST_MINISIGN_PRIVATE_KEY = "C:\secure\voice-comms-dcs-release.key"
$env:VCDCS_MANIFEST_MINISIGN_PUBLIC_KEY = "C:\secure\voice-comms-dcs-release.pub"
```

Private keys, signing certificates, `.env` files, and machine-specific signing material must never be committed.

## Signing

```powershell
.\build\sign_release.ps1
```

For local development without release keys:

```powershell
.\build\sign_release.ps1 -SkipSigning -SkipManifestSigning
```

The script signs or verifies Windows binaries with `signtool`, generates `release_manifest.json` and `model_manifest.json`, verifies their checksums, and signs each manifest with `minisign`.

Expected detached signature files:

```text
build_output\release_manifest.json.minisig
build_output\model_manifest.json.minisig
```

## Verification

```powershell
.\build\sign_release.ps1 -VerifyOnly
```

Users can also verify a manifest directly when `minisign` and the public key are available:

```powershell
minisign -Vm build_output\release_manifest.json -p voice-comms-dcs-release.pub
minisign -Vm build_output\model_manifest.json -p voice-comms-dcs-release.pub
```

## Runtime diagnostics

Input-manager callback, keyboard, and joystick errors are logged internally with rate limiting. The diagnostic snapshot exposes safe state such as device availability, last error code, joystick name, and button count without exposing stack traces to the browser by default.
