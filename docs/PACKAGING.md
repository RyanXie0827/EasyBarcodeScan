# EasyBarcodeScan 打包说明

## 1) 环境准备

在项目根目录执行：

```bash
python -m pip install -r requirements.txt
```

## 2) Windows 打包 EXE

推荐方式（默认系统 Python）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1 -Mode build
```

或批处理（默认系统 Python）：

```bat
scripts\build_windows.bat build
```

可选方式（指定系统 Python 路径）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1 -Mode build -Python "C:\Python311\python.exe"
```

可选方式（虚拟环境 `.venv_win`）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1 -Mode build -UseVenvPython
```

或批处理（虚拟环境 `.venv_win`）：

```bat
scripts\build_windows.bat build venv
```

手动方式：

```powershell
$env:PYTHONPATH = "src"
python -m PyInstaller --noconfirm --clean --distpath dist/windows --workpath build/windows packaging/pyinstaller/easybarcodescan.spec
```

输出文件：

- `dist/windows/EasyBarcodeScan-v<版本号>.exe`

## 3) macOS 打包 APP

> 必须在 macOS 系统上执行，Windows 不能直接交叉打包 `.app`。

推荐方式：

```bash
bash scripts/macos_onekey.sh build
```

或手动方式：

```bash
python3 -m pip install -r requirements.txt
PYTHONPATH=src python3 -m PyInstaller --noconfirm --clean --distpath dist/macos --workpath build/macos packaging/pyinstaller/easybarcodescan.spec
```

输出文件：

- `dist/macos/EasyBarcodeScan.app`

## 4) macOS 打包 DMG

```bash
bash scripts/build_macos_dmg.sh
```

输出文件：

- `dist/macos/EasyBarcodeScan-v<版本号>.dmg`

## 5) 图标资源

打包配置默认读取：

- `assets/icons/app_icon.icns`
- `assets/icons/app_icon.ico`

如需重新生成：

```bash
python3 scripts/build_icon_assets.py --source assets/icons/app_icon_1024.png
```

## 6) 常见问题

- `ModuleNotFoundError: pyzbar`：先确认安装了 `pyzbar`，并重新执行打包命令
- 条码识别失败：检查系统是否具备 `zbar` 运行依赖（`packaging/pyinstaller/easybarcodescan.spec` 已尝试自动收集）
- Windows 全局快捷键不可用：尝试以管理员身份运行；`keyboard` 库在部分安全策略较严格的环境下可能需要更高权限
- Windows 截图异常：确认没有被安全软件拦截屏幕截图权限
- macOS 首次运行无法截屏：在“系统设置 → 隐私与安全性 → 屏幕录制”中授权启动器或 `EasyBarcodeScan.app`
- macOS 全局快捷键不可用：确认已通过 `requirements.txt` 安装 `pyobjc-framework-Quartz`，并在“输入监控”中授权
- macOS 快捷键触发后被输入框/系统菜单继续处理：在“辅助功能”中授权启动器或 `EasyBarcodeScan.app`
- macOS 按 `Command + Shift + A` 后出现 `PRIMARY selection` / `STRING not defined`：通常不是权限没开，而是快捷键被终端、IDE 或输入框抢走了；请改用默认的 `Ctrl + Shift + A` 或其它冲突更少的组合键
- macOS 从 Terminal、iTerm、VS Code 或 PyCharm 启动时，权限应授予对应启动器；授权后需重启程序
- “记住密码”采用系统安全存储：Windows 使用 DPAPI，macOS 使用 Keychain
