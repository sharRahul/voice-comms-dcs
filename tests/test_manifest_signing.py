from __future__ import annotations

from pathlib import Path

import pytest

from voice_comms_dcs.manifest_signature import (
    ManifestSignatureError,
    build_manifest_signature_command,
    signature_path_for,
)


def test_minisign_signature_filename():
    assert signature_path_for(Path("build_output/release_manifest.json")) == Path(
        "build_output/release_manifest.json.minisig"
    )


def test_build_minisign_sign_command_requires_private_key():
    with pytest.raises(ManifestSignatureError, match="private key"):
        build_manifest_signature_command(Path("manifest.json"), sign=True)


def test_build_minisign_sign_command():
    command = build_manifest_signature_command(
        Path("manifest.json"),
        sign=True,
        private_key=Path("release.key"),
    )
    assert command == ["minisign", "-Sm", "manifest.json", "-s", "release.key"]


def test_build_minisign_verify_command_requires_public_key():
    with pytest.raises(ManifestSignatureError, match="public key"):
        build_manifest_signature_command(Path("manifest.json"), verify=True)


def test_build_minisign_verify_command_with_signature_path():
    command = build_manifest_signature_command(
        Path("manifest.json"),
        verify=True,
        public_key=Path("release.pub"),
        signature_path=Path("manifest.json.minisig"),
    )
    assert command == [
        "minisign",
        "-Vm",
        "manifest.json",
        "-p",
        "release.pub",
        "-x",
        "manifest.json.minisig",
    ]


def test_cannot_sign_and_verify_at_same_time():
    with pytest.raises(ManifestSignatureError, match="exactly one"):
        build_manifest_signature_command(
            Path("manifest.json"),
            sign=True,
            verify=True,
            private_key=Path("release.key"),
            public_key=Path("release.pub"),
        )
