#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MACOS_DIST_DIR="${MACOS_DIST_DIR:-$ROOT_DIR/dist/macos}"
MACOS_BUILD_DIR="${BUILD_DIR:-$ROOT_DIR/build/macos}"
PYINSTALLER_CACHE_DIR="${PYINSTALLER_CONFIG_DIR:-$ROOT_DIR/.pyinstaller/macos}"
APP_VERSION="$(python3 -c 'from pathlib import Path; ns = {}; exec(Path("src/easybarcodescan/version.py").read_text(encoding="utf-8"), ns); print(ns["APP_VERSION"])')"
VERSION_SUFFIX="${VERSION_SUFFIX:-v${APP_VERSION}}"
APP_PATH="${1:-$MACOS_DIST_DIR/EasyBarcodeScan.app}"
OUTPUT_PATH="${2:-$MACOS_DIST_DIR/EasyBarcodeScan-${VERSION_SUFFIX}.dmg}"
VOLUME_NAME="${3:-EasyBarcodeScan}"

cd "$ROOT_DIR"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "❌ This script only supports macOS."
  exit 1
fi

echo "🧹 Cleaning previous packaging artifacts ..."
rm -rf "$MACOS_BUILD_DIR" "$MACOS_DIST_DIR" "$PYINSTALLER_CACHE_DIR"

TMP_DIR="$(mktemp -d /tmp/easybarcodescan_dmg.XXXXXX)"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

echo "🏗️ Building macOS app ..."
DIST_DIR="$MACOS_DIST_DIR" BUILD_DIR="$MACOS_BUILD_DIR" PYINSTALLER_CONFIG_DIR="$PYINSTALLER_CACHE_DIR" bash scripts/macos_onekey.sh build

if [[ ! -d "$APP_PATH" ]]; then
  echo "❌ App bundle not found after build: $APP_PATH"
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT_PATH")"
rm -f "$OUTPUT_PATH"
cp -R "$APP_PATH" "$TMP_DIR/"
ln -s /Applications "$TMP_DIR/Applications"

echo "📦 Creating DMG ..."
hdiutil create -volname "$VOLUME_NAME" -srcfolder "$TMP_DIR" -ov -format UDZO "$OUTPUT_PATH"
echo "✅ Done: $OUTPUT_PATH"
