# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

block_cipher = None
project_root = Path.cwd()

added_files = [
    (str(project_root / "config" / "commands.example.json"), "config"),
    (str(project_root / "config" / "aircraft_profiles"), "config/aircraft_profiles"),
    (str(project_root / "dcs_scripts" / "VoiceBridge.lua"), "dcs_scripts"),
    (str(project_root / "dcs_scripts" / "dcs_telemetry.lua"), "dcs_scripts"),
    (str(project_root / "dcs_scripts" / "Export.lua.append.example"), "dcs_scripts"),
    (str(project_root / "dcs_scripts" / "mission_trigger_example.lua"), "dcs_scripts"),
    (str(project_root / "README.md"), "."),
    (str(project_root / "docs" / "architecture.md"), "docs"),
    (str(project_root / "docs" / "phase2_conversational_cockpit.md"), "docs"),
    (str(project_root / "docs" / "installer_roadmap.md"), "docs"),
    (str(project_root / "docs" / "security_and_limitations.md"), "docs"),
]

a = Analysis(
    [str(project_root / "src" / "voice_comms_dcs" / "main.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        "vosk",
        "sounddevice",
        "aiortc",
        "aiohttp",
        "websockets",
        "av",
        "numpy",
        "scipy.signal",
        "requests",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Voice-Comms-DCS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Voice-Comms-DCS",
)
