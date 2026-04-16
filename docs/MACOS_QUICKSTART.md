# macOS Quick Start

## 1) Clone and enter project

```bash
git clone <your-repo-url>
cd EasyBarcodeScan
```

## 2) One-command run

```bash
bash scripts/macos_onekey.sh
```

This will:

- install `zbar` via Homebrew if missing
- create `.venv_mac`
- install Python dependencies, including `pyobjc-framework-Quartz`
- run `python -m easybarcodescan`

## 3) Build `.app`

```bash
bash scripts/macos_onekey.sh build
```

Output:

- `dist/EasyBarcodeScan.app`

## 4) Build `.dmg`

```bash
bash scripts/build_macos_dmg.sh
```

Output:

- `dist/EasyBarcodeScan.dmg`

## 5) Config path

When packaged as `.app`, config is stored in:

- `~/Library/Application Support/EasyBarcodeScan/config.json`

Development config template is:

- `config/config.example.json`

## 6) First-run permissions on macOS

For screenshot and hotkey features, open System Settings → Privacy & Security and grant:

- Screen Recording
- Input Monitoring
- Accessibility

Permission target:

- If you start from Terminal, iTerm, VS Code, or PyCharm, allow that launcher
- If you run the packaged app, allow `EasyBarcodeScan.app`

Quit and reopen EasyBarcodeScan after changing permissions.

Default hotkey on macOS:

- `Ctrl + Shift + A`
