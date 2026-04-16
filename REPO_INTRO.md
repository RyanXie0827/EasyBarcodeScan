# 仓库简介

`EasyBarcodeScan` 是一个轻量桌面扫码工具，面向需要快速核验条码商品信息的业务场景。

## 核心价值

- **效率**：通过全局快捷键 + 截图识别，减少手工输入条码。
- **稳定**：对 Token 进行启动检测、扫描前校验、接口失效兜底。
- **易用**：登录、历史记录、快捷键管理都在单个窗口可视化完成。
- **安全**：记住密码走系统安全机制（Windows DPAPI / macOS Keychain）。

## 技术实现

- GUI：`Tkinter`
- 图像处理：`Pillow`、`numpy`
- 条码识别：`pyzbar`
- 网络请求：`curl_cffi`
- 快捷键：`keyboard`
- 打包：`PyInstaller`

## 适用平台

- Windows（主测）
- macOS（可打包 `.app`，需在 macOS 本机执行打包）

## 后续可扩展方向

- 多语言界面（中/英）
- 主题切换（浅色/深色）
- 历史记录导出（CSV/Excel）
- 扫描结果详情侧边栏展示

