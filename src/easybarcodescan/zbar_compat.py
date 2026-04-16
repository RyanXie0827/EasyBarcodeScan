import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def _find_zbar_path() -> str | None:
    try:
        from ctypes.util import find_library

        return find_library("zbar")
    except Exception:
        return None


def _append_candidate(directory: Path, candidates: list[str], seen: set[str]) -> None:
    try:
        normalized = str(directory.expanduser().resolve())
    except Exception:
        normalized = str(directory)
    if not normalized or normalized in seen:
        return
    if not Path(normalized).is_dir():
        return
    seen.add(normalized)
    candidates.append(normalized)


def _collect_macos_library_dirs() -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    for env_name in ("DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH"):
        for entry in os.environ.get(env_name, "").split(":"):
            if entry:
                _append_candidate(Path(entry), candidates, seen)

    for path_str in (
        "/opt/homebrew/lib",
        "/opt/homebrew/opt/zbar/lib",
        "/usr/local/lib",
        "/usr/local/opt/zbar/lib",
    ):
        _append_candidate(Path(path_str), candidates, seen)

    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        _append_candidate(executable_dir, candidates, seen)
        _append_candidate(executable_dir.parent / "Frameworks", candidates, seen)

    brew_bin = shutil.which("brew")
    if brew_bin:
        for args in ((brew_bin, "--prefix"), (brew_bin, "--prefix", "zbar")):
            try:
                result = subprocess.run(args, capture_output=True, text=True, check=True)
            except Exception:
                continue
            prefix = result.stdout.strip()
            if prefix:
                _append_candidate(Path(prefix) / "lib", candidates, seen)

    return candidates


def prepare_zbar_environment() -> None:
    if platform.system() != "Darwin":
        return
    if _find_zbar_path():
        return

    library_dirs = _collect_macos_library_dirs()
    if not library_dirs:
        return

    for env_name in ("DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH"):
        existing = [entry for entry in os.environ.get(env_name, "").split(":") if entry]
        merged: list[str] = []
        seen: set[str] = set()
        for entry in library_dirs + existing:
            if entry and entry not in seen:
                seen.add(entry)
                merged.append(entry)
        if merged:
            os.environ[env_name] = ":".join(merged)
