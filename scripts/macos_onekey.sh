#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-run}" # run | build
PYTHON_BIN="${PYTHON_BIN:-python3}"
APP_NAME="EasyBarcodeScan"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv_mac}"
DIST_DIR="${DIST_DIR:-$ROOT_DIR/dist/macos}"
BUILD_DIR="${BUILD_DIR:-$ROOT_DIR/build/macos}"
PYINSTALLER_CACHE_DIR="${PYINSTALLER_CONFIG_DIR:-$ROOT_DIR/.pyinstaller/macos}"
cd "$ROOT_DIR"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "❌ This script only supports macOS."
  exit 1
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "❌ Cannot find Python: $PYTHON_BIN"
  echo "   Set PYTHON_BIN or install Python 3 first."
  exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "❌ Homebrew is required to install zbar."
  echo "   Install Homebrew first: https://brew.sh"
  exit 1
fi

if ! brew list --versions zbar >/dev/null 2>&1; then
  echo "📦 Installing zbar ..."
  brew install zbar
fi

HOMEBREW_PREFIX="$(brew --prefix)"
ZBAR_PREFIX="$(brew --prefix zbar)"
LIB_PATHS=()
if [[ -d "${ZBAR_PREFIX}/lib" ]]; then
  LIB_PATHS+=("${ZBAR_PREFIX}/lib")
fi
if [[ -d "${HOMEBREW_PREFIX}/lib" ]]; then
  LIB_PATHS+=("${HOMEBREW_PREFIX}/lib")
fi
if [[ -n "${DYLD_LIBRARY_PATH:-}" ]]; then
  LIB_PATHS+=("${DYLD_LIBRARY_PATH}")
fi
if [[ ${#LIB_PATHS[@]} -gt 0 ]]; then
  export DYLD_LIBRARY_PATH="$(IFS=:; echo "${LIB_PATHS[*]}")"
  export DYLD_FALLBACK_LIBRARY_PATH="$DYLD_LIBRARY_PATH"
fi

if [[ ! -d "$VENV_DIR" ]]; then
  echo "🐍 Creating virtual env: $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

echo "📦 Installing Python dependencies ..."
export PIP_DISABLE_PIP_VERSION_CHECK=1
python -m pip install -r requirements.txt
export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
export PYINSTALLER_CONFIG_DIR="$PYINSTALLER_CACHE_DIR"
mkdir -p "$PYINSTALLER_CONFIG_DIR"

case "$MODE" in
  run)
    echo "🚀 Starting ${APP_NAME} ..."
    python -m easybarcodescan
    ;;
  build)
    echo "🧹 Cleaning old build artifacts ..."
    rm -rf "$BUILD_DIR" "$DIST_DIR" "$PYINSTALLER_CACHE_DIR"
    mkdir -p "$BUILD_DIR" "$DIST_DIR" "$PYINSTALLER_CACHE_DIR"
    echo "🏗️ Building macOS app ..."
    python -m PyInstaller --noconfirm --clean --distpath "$DIST_DIR" --workpath "$BUILD_DIR" packaging/pyinstaller/easybarcodescan.spec
    echo "✅ Done: ${DIST_DIR}/${APP_NAME}.app"
    ;;
  *)
    echo "Usage: bash scripts/macos_onekey.sh [run|build]"
    echo "  run   Install deps and run app (default)"
    echo "  build Install deps and build .app package"
    exit 2
    ;;
esac
