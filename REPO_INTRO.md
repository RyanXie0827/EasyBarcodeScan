# 仓库简介

`EasyBarcodeScan` 是一个面向业务核验场景的桌面扫码工具，支持通过全局快捷键截图识别条形码并调用 GDS 接口查询商品信息。

## 核心价值

- **效率**：全局快捷键 + 截图识别，减少手工输入条码
- **稳定**：启动检测 Token、扫描前校验、接口失效兜底
- **易用**：登录、历史、快捷键、结果展示都在 GUI 中完成
- **可交付**：支持 macOS `.app/.dmg` 打包，目录结构已按源码 / 脚本 / 打包 / 配置 / 资源分层

## 主要目录

- 源码：`src/easybarcodescan/`
- 脚本：`scripts/`
- 打包：`packaging/pyinstaller/`
- 配置：`config/`
- 资源：`assets/`
- 文档：`docs/`
- 历史备份：`legacy/`

## 技术实现

- GUI：`Tkinter`
- 图像处理：`Pillow`、`numpy`
- 条码识别：`pyzbar`
- 网络请求：`curl_cffi`
- 快捷键：`src/easybarcodescan/global_hotkey.py`
- 打包：`PyInstaller`

## 适用平台

- Windows
- macOS（可打包 `.app/.dmg`，需在 macOS 本机执行）

## 推荐入口

- 开发运行：`PYTHONPATH=src python -m easybarcodescan`
- macOS 一键运行：`bash scripts/macos_onekey.sh`
- macOS 打包：`bash scripts/macos_onekey.sh build`
- Windows 一键运行：`powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1 -Mode run`
- Windows 打包：`powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1 -Mode build`
