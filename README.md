# EasyBarcodeScan

一个面向业务场景的桌面条形码扫码工具，基于 `Tkinter + 截图识别 + GDS 查询接口`。

支持全局快捷键截图扫码、登录态管理、Token 过期提醒、历史记录、后台监听、系统安全存储密码，以及 macOS `.app/.dmg` 打包交付。

## 功能特性

- 全局快捷键截图扫码
  - Windows 默认：`Ctrl + Alt + A`
  - macOS 默认：`Ctrl + Shift + A`
- 自动识别截图中的 69 码并转换查询码
- 平台账号登录，自动获取 Token
- Token 过期检测与失效提醒
- 扫描历史记录（本地持久化）
- 主窗口关闭后继续后台监听（不退出程序）
- 可选“记住密码”
  - Windows：DPAPI
  - macOS：Keychain

## 企业化目录结构

```text
EasyBarcodeScan/
├─ src/
│  └─ easybarcodescan/
│     ├─ __init__.py
│     ├─ __main__.py          # 模块入口：python -m easybarcodescan
│     ├─ app.py               # 主程序
│     ├─ global_hotkey.py     # 跨平台全局快捷键兼容层
│     └─ zbar_compat.py       # macOS 的 zbar 动态库兼容处理
├─ scripts/
│  ├─ macos_onekey.sh         # macOS 一键运行 / 构建 .app
│  ├─ build_macos_dmg.sh      # 由 .app 生成 .dmg
│  ├─ build_windows.ps1       # Windows 一键运行 / 构建 .exe
│  ├─ build_windows.bat       # Windows 批处理入口
│  └─ build_icon_assets.py    # 由 PNG 生成 .icns/.ico
├─ packaging/
│  └─ pyinstaller/
│     └─ easybarcodescan.spec # PyInstaller 打包配置
├─ config/
│  └─ config.example.json     # 配置模板
├─ assets/
│  ├─ icons/                  # 图标源文件与导出文件
│  └─ examples/               # 示例图片
├─ docs/
│  ├─ MACOS_QUICKSTART.md
│  ├─ MACOS_PACKAGING_NOTES.md
│  └─ PACKAGING.md
├─ legacy/
│  └─ gds_scan.py             # 旧版脚本备份
├─ requirements.txt
├─ README.md
└─ REPO_INTRO.md
```

## 快速开始

### 1) 安装依赖

```bash
pip install -r requirements.txt
```

### 2) 开发态运行

macOS / Linux：

```bash
PYTHONPATH=src python -m easybarcodescan
```

Windows PowerShell：

```powershell
$env:PYTHONPATH = "src"
python -m easybarcodescan
```

macOS 也可以直接用一键脚本启动：

```bash
bash scripts/macos_onekey.sh
```

### 3) 首次使用建议

- 点击“登录”完成账号登录
- 若需要自动填充密码，可勾选“记住密码”
- 使用全局快捷键截图条码区域开始查询
- 点击主窗口右上角关闭按钮时，程序会隐藏到后台但继续全局监听
- macOS 首次使用需授予权限后重启程序

## 配置说明

开发态默认配置文件：

- `config/config.json`

配置模板：

- `config/config.example.json`

初始化方式：

```bash
cp config/config.example.json config/config.json
```

Windows PowerShell：

```powershell
Copy-Item config/config.example.json config/config.json
```

打包为 `.app` 后，运行时配置位于：

- `~/Library/Application Support/EasyBarcodeScan/config.json`

程序会自动尝试迁移旧位置的 `config.json`。

## 常用脚本

本项目目标是同时兼容 macOS 和 Windows：

- macOS 交付物：`dist/macos/EasyBarcodeScan.app`、`dist/macos/EasyBarcodeScan-v<版本号>.dmg`
- Windows 交付物：`dist/windows/EasyBarcodeScan-v<版本号>.exe`

### 1) macOS 一键运行

```bash
bash scripts/macos_onekey.sh
```

作用：

- 自动安装 `zbar`
- 创建 `.venv_mac`
- 安装依赖
- 启动程序

### 2) 构建 macOS `.app`

```bash
bash scripts/macos_onekey.sh build
```

输出：

- `dist/macos/EasyBarcodeScan.app`

### 3) Windows 一键运行

PowerShell（默认系统 Python）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1 -Mode run
```

PowerShell（指定系统 Python 路径）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1 -Mode run -Python "C:\Python311\python.exe"
```

PowerShell（可选：虚拟环境 `.venv_win`）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1 -Mode run -UseVenvPython
```

或批处理（默认系统 Python）：

```bat
scripts\build_windows.bat run
```

批处理（可选：虚拟环境 `.venv_win`）：

```bat
scripts\build_windows.bat run venv
```

作用：

- 安装依赖（默认使用系统 Python）
- 启动程序

### 4) 构建 Windows `.exe`

PowerShell（默认系统 Python）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1 -Mode build
```

PowerShell（指定系统 Python 路径）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1 -Mode build -Python "C:\Python311\python.exe"
```

PowerShell（可选：虚拟环境 `.venv_win`）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1 -Mode build -UseVenvPython
```

或批处理（默认系统 Python）：

```bat
scripts\build_windows.bat build
```

批处理（可选：虚拟环境 `.venv_win`）：

```bat
scripts\build_windows.bat build venv
```

输出：

- `dist/windows/EasyBarcodeScan-v<版本号>.exe`

### 5) 构建 macOS `.dmg`

```bash
bash scripts/build_macos_dmg.sh
```

默认输入 / 输出：

- 输入：`dist/macos/EasyBarcodeScan.app`
- 输出：`dist/macos/EasyBarcodeScan-v<版本号>.dmg`

也可以自定义：

```bash
bash scripts/build_macos_dmg.sh dist/macos/EasyBarcodeScan.app dist/macos/EasyBarcodeScan-v1.0.0.dmg EasyBarcodeScan
```

### 6) 重新生成图标文件

如果你换了一张新的 PNG 图标图，可以重新生成打包用图标：

```bash
python3 scripts/build_icon_assets.py --source assets/icons/app_icon_1024.png
```

默认会输出：

- `assets/icons/app_icon_1024.png`
- `assets/icons/app_icon.icns`
- `assets/icons/app_icon.ico`

如果你的自定义图不在 `assets/icons/`，也可以直接指定路径：

```bash
python3 scripts/build_icon_assets.py --source /path/to/your-icon.png --output-dir assets/icons --name app_icon
```

说明：

- 脚本会把任意长宽比图片自动居中到透明的 `1024x1024`
- `packaging/pyinstaller/easybarcodescan.spec` 已自动引用 `assets/icons/app_icon.icns` 和 `assets/icons/app_icon.ico`

### 7) 推荐的客户交付流程

macOS：

```bash
# 1. 如需换图标，先准备一张 PNG
python3 scripts/build_icon_assets.py --source assets/icons/app_icon_1024.png

# 2. 打包 .app
bash scripts/macos_onekey.sh build

# 3. 再封装成 .dmg
bash scripts/build_macos_dmg.sh
```

macOS 最终交付文件：

- `dist/macos/EasyBarcodeScan-v<版本号>.dmg`

Windows：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1 -Mode build
```

Windows 最终交付文件：

- `dist/windows/EasyBarcodeScan-v<版本号>.exe`

> 当前产物建议进一步做 Apple Developer ID 签名与公证后再正式发客户。

## macOS 前置设置

如果在 macOS 上运行，请先打开“系统设置 → 隐私与安全性”：

- “屏幕录制”：用于系统截图框选条码区域，否则会出现 `screencapture` 失败
- “输入监控”：用于全局快捷键，否则快捷键无法触发
- “辅助功能”：用于拦截全局快捷键，避免快捷键继续传给输入框或系统菜单
- 从 Terminal、iTerm、VS Code 或 PyCharm 启动时，请授权对应启动器；打包后请授权 `EasyBarcodeScan.app`
- 如果按 `Command + Shift + A` 后出现 `PRIMARY selection` / `STRING not defined`，通常不是权限没开，而是快捷键被终端、IDE 或输入框抢走了；请改用 `Ctrl + Shift + A` 或其它冲突更少的组合键
- 主窗口点叉号后默认只隐藏到后台，仍可继续全局扫码；如需完全退出，请按 `Command + Q`（macOS）或点击“退出程序”
- 授权后请完全退出并重新打开程序

## 更多文档

- 打包说明：`docs/PACKAGING.md`
- macOS 快速上手：`docs/MACOS_QUICKSTART.md`
- macOS 打包补充说明：`docs/MACOS_PACKAGING_NOTES.md`
