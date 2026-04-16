# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path
from importlib.util import find_spec

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules


project_root = Path(SPECPATH).resolve()

hidden_imports = ["keyboard"]
pyzbar_binaries = []
zbar_binaries = []

pyzbar_spec = find_spec("pyzbar")
if pyzbar_spec and pyzbar_spec.submodule_search_locations:
    hidden_imports += collect_submodules("pyzbar")
    pyzbar_binaries = collect_dynamic_libs("pyzbar")
else:
    hidden_imports += ["pyzbar.pyzbar", "pyzbar.wrapper"]

if sys.platform == "darwin":
    zbar_candidates = [
        Path("/opt/homebrew/opt/zbar/lib/libzbar.dylib"),
        Path("/usr/local/opt/zbar/lib/libzbar.dylib"),
    ]

    cellar_roots = [Path("/opt/homebrew/Cellar/zbar"), Path("/usr/local/Cellar/zbar")]
    for cellar_root in cellar_roots:
        if not cellar_root.exists():
            continue
        zbar_candidates += sorted(cellar_root.glob("*/lib/libzbar*.dylib"), reverse=True)

    seen_zbar = set()
    for candidate in zbar_candidates:
        if not candidate.exists():
            continue
        resolved_candidate = candidate.resolve()
        resolved_key = str(resolved_candidate)
        if resolved_key in seen_zbar:
            continue
        seen_zbar.add(resolved_key)
        zbar_binaries.append((resolved_key, "."))

data_files = []
if (project_root / "resources").exists():
    data_files.append(("resources", "resources"))


a = Analysis(
    ["gds_scan_v2.py"],
    pathex=[str(project_root)],
    binaries=pyzbar_binaries + zbar_binaries,
    datas=data_files,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="EasyBarcodeScan",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="EasyBarcodeScan.app",
        icon=None,
        bundle_identifier="com.easybarcodescan.app",
        info_plist={
            "NSHighResolutionCapable": "True",
        },
    )
