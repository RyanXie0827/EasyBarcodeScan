#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-run}" # run | build
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv_mac}"
APP_NAME="EasyBarcodeScan"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

if [[ ! -d "$VENV_DIR" ]]; then
  echo "🐍 Creating virtual env: $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

echo "📦 Installing Python dependencies ..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

case "$MODE" in
  run)
    echo "🚀 Starting ${APP_NAME} ..."
    python gds_scan_v2.py
    ;;
  build)
    echo "🧹 Cleaning old build artifacts ..."
    rm -rf build dist
    echo "🏗️ Building macOS app ..."
    python -m PyInstaller --noconfirm --clean easybarcodescan.spec
    echo "✅ Done: dist/${APP_NAME}.app"
    ;;
  *)
    echo "Usage: bash macos_onekey.sh [run|build]"
    echo "  run   Install deps and run app (default)"
    echo "  build Install deps and build .app package"
    exit 2
    ;;
esac

