# macOS Quick Start

## 1) Clone and enter project

```bash
git clone <your-repo-url>
cd easybarcodescan_repo
```

## 2) One-command run

```bash
bash macos_onekey.sh
```

This will:
- install `zbar` via Homebrew (if missing)
- create `.venv_mac`
- install Python dependencies
- run `gds_scan_v2.py`

## 3) Build `.app`

```bash
bash macos_onekey.sh build
```

Output:
- `dist/EasyBarcodeScan.app`

## 4) Config and login cache path

When packaged as `.app`, config is stored in:

- `~/Library/Application Support/EasyBarcodeScan/config.json`

## 5) First-run permissions on macOS

For screenshot and hotkey features, grant app permissions in:
- Privacy & Security → Screen Recording
- Privacy & Security → Input Monitoring
