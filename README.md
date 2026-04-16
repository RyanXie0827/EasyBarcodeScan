# EasyBarcodeScan

一个基于 `Tkinter + 截图识别 + GDS 查询接口` 的桌面条码扫描工具。

支持全局快捷键截图识别、登录态管理、Token 过期提醒、历史记录查看、记住密码（系统安全存储）等能力。

## 功能特性

- 全局快捷键截图扫码（默认 `Ctrl + Alt + A`）
- 自动识别截图中的 69 码并转换查询码
- 平台账号登录，自动获取 Token
- Token 过期检测与失效提醒
- 扫描历史记录（本地持久化）
- 可选“记住密码”
  - Windows：DPAPI
  - macOS：Keychain

## 项目结构

```text
easybarcodescan_repo/
├─ gds_scan_v2.py            # 主程序（推荐使用）
├─ easybarcodescan.spec      # PyInstaller 打包配置
├─ requirements.txt          # 运行与打包依赖
├─ config.example.json       # 配置模板（不含真实凭据）
├─ docs/
│  └─ PACKAGING.md           # Windows/macOS 打包说明
├─ legacy/
│  └─ gds_scan.py            # 旧版脚本备份
├─ examples/
│  └─ 69scan.jpg             # 示例图片
└─ REPO_INTRO.md             # 仓库简介
```

## 快速开始

### 1) 安装依赖

```bash
pip install -r requirements.txt
```

### 2) 启动程序

```bash
python gds_scan_v2.py
```

### 3) 首次使用建议

- 点击“重新登录”完成账号登录
- 若需要自动填充密码，可勾选“记住密码”
- 用快捷键截图条码区域开始查询

## 配置说明

程序默认读取同目录 `config.json`。

如需初始化配置，可复制：

```bash
cp config.example.json config.json
```

Windows PowerShell：

```powershell
Copy-Item config.example.json config.json
```

## 打包

请参考：`docs/PACKAGING.md`

