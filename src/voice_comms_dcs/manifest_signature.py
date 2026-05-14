from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class ManifestSignatureError(RuntimeError):
    """Raised when detached manifest signing or verification cannot be completed."""


def signature_path_for(manifest_path: Path, signature_tool: str = "minisign") -> Path:
    tool = signature_tool.lower()
    if tool == "minisign":
        return manifest_path.with_name(manifest_path.name + ".minisig")
    if tool == "cosign":
        return manifest_path.with_name(manifest_path.name + ".sig")
    raise ManifestSignatureError(f"Unsupported manifest signature tool: {signature_tool}")


def build_manifest_signature_command(
    manifest_path: Path,
    *,
    signature_tool: str = "minisign",
    sign: bool = False,
    verify: bool = False,
    private_key: Path | None = None,
    public_key: Path | None = None,
    signature_path: Path | None = None,
) -> list[str]:
    if sign == verify:
        raise ManifestSignatureError("Choose exactly one manifest signature action: sign or verify.")

    tool = signature_tool.lower()
    if tool != "minisign":
        raise ManifestSignatureError(f"Unsupported manifest signature tool: {signature_tool}")

    if sign:
        if private_key is None:
            raise ManifestSignatureError("Manifest signing requested but no private key was provided.")
        return [tool, "-Sm", str(manifest_path), "-s", str(private_key)]

    if public_key is None:
        raise ManifestSignatureError("Manifest signature verification requested but no public key was provided.")
    command = [tool, "-Vm", str(manifest_path), "-p", str(public_key)]
    if signature_path is not None:
        command.extend(["-x", str(signature_path)])
    return command


def run_manifest_signature(
    manifest_path: Path,
    *,
    signature_tool: str = "minisign",
    sign: bool = False,
    verify: bool = False,
    private_key: Path | None = None,
    public_key: Path | None = None,
    signature_path: Path | None = None,
) -> None:
    command = build_manifest_signature_command(
        manifest_path,
        signature_tool=signature_tool,
        sign=sign,
        verify=verify,
        private_key=private_key,
        public_key=public_key,
        signature_path=signature_path,
    )
    if shutil.which(command[0]) is None:
        raise ManifestSignatureError(f"{command[0]} was not found on PATH.")
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        action = "sign" if sign else "verify"
        raise ManifestSignatureError(f"Manifest signature {action} command failed: exit {completed.returncode}")
