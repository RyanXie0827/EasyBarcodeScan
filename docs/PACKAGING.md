# EasyBarcodeScan 打包说明

## 1) 环境准备

在项目根目录执行：

```powershell
python -m pip install -r requirements.txt
```

## 2) Windows 打包 EXE

```powershell
python -m PyInstaller --noconfirm --clean easybarcodescan.spec
```

输出文件：

- `dist/EasyBarcodeScan.exe`

## 3) macOS 打包 APP

> 必须在 macOS 系统上执行，Windows 不能直接交叉打包 `.app`。

```bash
python3 -m pip install -r requirements.txt
python3 -m PyInstaller --noconfirm --clean easybarcodescan.spec
```

输出文件：

- `dist/EasyBarcodeScan.app`

## 4) 常见问题

- `ModuleNotFoundError: pyzbar`：先确认安装了 `pyzbar`，并重新执行打包命令。
- 条码识别失败：检查系统是否具备 `zbar` 运行依赖（`easybarcodescan.spec` 已尝试自动收集）。
- macOS 首次运行无法截屏：在系统“隐私与安全性”中为应用授予“屏幕录制”权限。
- “记住密码”采用系统安全存储：Windows 使用 DPAPI，macOS 使用 Keychain。
