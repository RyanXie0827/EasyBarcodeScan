# macOS Packaging Notes (EasyBarcodeScan)

## What was hardened

- Source code is now organized under `src/easybarcodescan/`
- Development config is now stored at `config/config.json`
- Packaged app config remains:
  - `~/Library/Application Support/EasyBarcodeScan/config.json`
- Legacy `config.json` in old locations is auto-migrated to the new path
- `src/easybarcodescan/global_hotkey.py` uses Quartz event taps on macOS, avoiding the old `keyboard` listener path
- `requirements.txt` installs `pyobjc-framework-Quartz` only on macOS for hotkey support
- `packaging/pyinstaller/easybarcodescan.spec` explicitly tries to collect `libzbar` from Homebrew paths:
  - `/opt/homebrew/opt/zbar/lib/libzbar.dylib`
  - `/usr/local/opt/zbar/lib/libzbar.dylib`
  - versioned `Cellar` paths

## Build command

```bash
bash scripts/macos_onekey.sh build
```

## DMG command

```bash
bash scripts/build_macos_dmg.sh
```

## Runtime permissions

Enable in macOS:

- Privacy & Security → Screen Recording
- Privacy & Security → Input Monitoring
- Privacy & Security → Accessibility

If launched from Terminal, iTerm, VS Code, or PyCharm, grant permissions to that launcher.
If launched as a packaged app, grant permissions to `EasyBarcodeScan.app`.
Quit and reopen the app after changing permissions.
