#!/usr/bin/env bash
set -euo pipefail

APP_PATH="${1:-dist/EasyBarcodeScan.app}"
OUTPUT_PATH="${2:-dist/EasyBarcodeScan.dmg}"
VOLUME_NAME="${3:-EasyBarcodeScan}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "❌ This script only supports macOS."
  exit 1
fi

if [[ ! -d "$APP_PATH" ]]; then
  echo "❌ App bundle not found: $APP_PATH"
  echo "   Build it first with: bash scripts/macos_onekey.sh build"
  exit 1
fi

TMP_DIR="$(mktemp -d /tmp/easybarcodescan_dmg.XXXXXX)"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

mkdir -p "$(dirname "$OUTPUT_PATH")"
rm -f "$OUTPUT_PATH"
cp -R "$APP_PATH" "$TMP_DIR/"
ln -s /Applications "$TMP_DIR/Applications"

echo "📦 Creating DMG ..."
hdiutil create -volname "$VOLUME_NAME" -srcfolder "$TMP_DIR" -ov -format UDZO "$OUTPUT_PATH"
echo "✅ Done: $OUTPUT_PATH"
