# macOS Packaging Notes (EasyBarcodeScan)

## What was hardened

- `gds_scan_v2.py` now uses app data config path when running as packaged app:
  - `~/Library/Application Support/EasyBarcodeScan/config.json`
- Legacy `config.json` in old locations is auto-migrated to the new path.
- `easybarcodescan.spec` now explicitly tries to collect `libzbar` from Homebrew paths:
  - `/opt/homebrew/opt/zbar/lib/libzbar.dylib`
  - `/usr/local/opt/zbar/lib/libzbar.dylib`
  - and versioned `Cellar` paths.

## Build command

```bash
bash macos_onekey.sh build
```

## Runtime permissions

Enable in macOS:
- Privacy & Security → Screen Recording
- Privacy & Security → Input Monitoring

