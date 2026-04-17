# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path
from importlib.util import find_spec

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules


project_root = Path(SPECPATH).resolve().parents[1]
source_root = project_root / "src"
mac_icon_path = project_root / "assets" / "icons" / "app_icon.icns"
windows_icon_path = project_root / "assets" / "icons" / "app_icon.ico"
version_ns = {}
exec((source_root / "easybarcodescan" / "version.py").read_text(encoding="utf-8"), version_ns)
app_version = version_ns["APP_VERSION"]

hidden_imports = []
pyzbar_binaries = []
zbar_binaries = []

if sys.platform == "darwin":
    hidden_imports.append("Quartz")
else:
    hidden_imports.append("keyboard")
    hidden_imports += ["pystray", "pystray._win32"]

pyzbar_spec = find_spec("pyzbar")
if pyzbar_spec and pyzbar_spec.submodule_search_locations:
    hidden_imports += ["pyzbar.pyzbar", "pyzbar.wrapper"]
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


a = Analysis(
    [str(project_root / "packaging" / "pyinstaller" / "entrypoint.py")],
    pathex=[str(project_root), str(source_root)],
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

if sys.platform == "darwin":
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="EasyBarcodeScan",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        console=False,
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=str(mac_icon_path) if mac_icon_path.exists() else None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name="EasyBarcodeScan",
    )
    app = BUNDLE(
        coll,
        name="EasyBarcodeScan.app",
        icon=str(mac_icon_path) if mac_icon_path.exists() else None,
        bundle_identifier="com.easybarcodescan.app",
        info_plist={
            "CFBundleShortVersionString": app_version,
            "CFBundleVersion": app_version,
            "NSHighResolutionCapable": "True",
        },
    )
else:
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
        icon=str(windows_icon_path) if windows_icon_path.exists() else None,
    )
