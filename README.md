<div align="center">

# 💬 微信自动回复助手

**基于 PySide6 + wxauto 的微信 PC 版自动化工具**

轻量 · 稳定 · 高性能 · 现代化 UI · 快速回复

---

[![Release](https://img.shields.io/github/v/release/Be-nothing/wxAutoTool?style=flat-square&logo=github&color=blue)](https://github.com/Be-nothing/wxAutoTool/releases)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-blue?style=flat-square&logo=windows&color=0078D6)](https://github.com/Be-nothing/wxAutoTool)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/PySide6-6.6-41CD52?style=flat-square&logo=qt&logoColor=white)](https://www.qt.io/)
[![License](https://img.shields.io/badge/license-Private-red?style=flat-square)](./LICENSE)
[![Stars](https://img.shields.io/github/stars/Be-nothing/wxAutoTool?style=flat-square&logo=github&color=yellow)](https://github.com/Be-nothing/wxAutoTool/stargazers)

</div>

---

> 🚀 **一键安装，开箱即用** — 提供独立安装包，无需配置 Python 环境，下载即用。
> 基于 Windows UIA 自动化，不修改微信客户端、不读取本地数据库，安全可控。

---

## 📑 目录

- [✨ 功能特性](#-功能特性)
- [📸 界面预览](#-界面预览)
- [🚀 快速开始](#-快速开始)
- [🛠️ 技术栈](#️-技术栈)
- [📁 项目结构](#-项目结构)
- [⚙️ 配置说明](#️-配置说明)
- [🔧 开发指南](#-开发指南)
- [💡 技术要点](#-技术要点)
- [❓ 常见问题](#-常见问题)
- [🤝 贡献](#-贡献)
- [📄 许可证](#-许可证)

---

## ✨ 功能特性

### 🎨 现代化界面

| 特性 | 描述 |
|:---:|:---|
| 🌗 **主题系统** | 浅色 / 深色 / 跟随系统，自动适配 Windows 深浅色 |
| 🪟 **悬浮组件** | 启动检测后可缩小为右上角悬浮窗，不遮挡微信操作 |
| 🎨 **飞书风格** | 克制配色 + 充足留白，长时间使用不疲劳 |
| 📊 **仪表盘** | 实时显示微信连接状态、监听对象数、今日消息数 |

### ⚡ 自动化能力

| 特性 | 描述 |
|:---:|:---|
| 🎯 **UIA 直采** | 增量拉取新消息，O(N) → O(新增数)，性能提升 10x+ |
| 🔍 **状态检测** | 启动前自动检测微信连接，未连接不允许启动 |
| 🧪 **对象测试** | 一键验证监听对象名称是否存在于微信会话列表 |
| 📝 **规则回复** | 关键词匹配 + 默认回复，每个对象独立配置 |
| 🚫 **智能过滤** | 可选忽略自己消息、系统消息 |

### 🛡️ 稳定性保障

| 特性 | 描述 |
|:---:|:---|
| 🔇 **无 CMD 闪屏** | Patch subprocess/os.system，windowed 模式下完全静默 |
| 💾 **原子配置** | 临时文件 + 重命名写入，配置损坏自动从 .bak 恢复 |
| 🔄 **自动重连** | 消息拉取失败自动重试，连续失败按指数退避 |
| 📋 **彩色日志** | 按级别着色，自动滚动，限制 2000 行避免内存膨胀 |
| ⚡ **快速发送** | 粘贴发送 + editbox 缓存，发送延迟 < 2 秒 |
| 🔄 **窗口恢复** | 最小化窗口收到消息时自动恢复（不置顶），editbox 按需 refind |

---

## 📸 界面预览

```
┌─────────────────────────────────────────────────────┐
│  💬 微信自动回复助手                          ─ □ ×   │
├─────┬───────────────────────────────────────────────┤
│     │                                               │
│ 🏠  │   仪表盘                                       │
│ 仪表 │   ┌───────────┬───────────┬───────────┐      │
│     │   │ 微信状态   │ 监听对象   │ 今日消息   │      │
│ 📋  │   │   ● 已连接 │     3     │    128    │      │
│ 监听 │   └───────────┴───────────┴───────────┘      │
│     │                                               │
│ 📝  │   ┌─────────────────────────────────────┐    │
│ 日志 │   │ [INFO]  已添加 UIA 监听：张三         │    │
│     │   │ [INFO]  [解析] #0 type=friend ...    │    │
│ ⚙️  │   │ [WARN]  拉取超时，重试中...           │    │
│ 设置 │   └─────────────────────────────────────┘    │
│     │                                               │
└─────┴───────────────────────────────────────────────┘
```

> 💡 **提示**：启动检测后，主窗口可缩小为 220×60 的悬浮组件，实时显示监听状态。

---

## 🚀 快速开始

### 📦 安装

**方式一：下载安装包（推荐）**

1. 前往 [Releases](https://github.com/Be-nothing/wxAutoTool/releases/latest) 下载最新版安装包
2. 运行 `微信自动回复助手_Setup_v*.exe`
3. 按提示完成安装（支持自定义安装目录）

**方式二：源码运行**

```bash
git clone https://github.com/Be-nothing/wxAutoTool.git
cd wxAutoTool
pip install -r requirements.txt
python main.py
```

### 🎯 使用流程

```
启动微信并登录  →  打开助手  →  添加监听对象  →  配置回复规则  →  启动检测
```

<details>
<summary>📖 详细步骤</summary>

1. **启动微信 PC 版**并完成登录
2. **打开"微信自动回复助手"**
3. 切换到**「监听对象」**页，点击「添加」
4. 输入微信会话名称（与微信中显示完全一致），点击「测试」验证
5. 配置回复规则：
   - **关键词回复**：消息包含关键词时回复指定内容
   - **默认回复**：未匹配任何关键词时回复
6. 点击「启动检测」，确认后开始自动监听
7. 监听期间可点击「缩小」切换为悬浮组件模式

</details>

### ⚙️ 前置要求

| 要求 | 版本 | 说明 |
|:---|:---|:---|
| 操作系统 | Windows 10/11 (64 位) | 依赖 Windows UIA |
| 微信 PC 版 | 3.9+ | 需已登录 |
| .NET Framework | 4.7+ | Windows 自带 |

---

## 🛠️ 技术栈

| 类别 | 技术 | 用途 |
|:---|:---|:---|
| ![Python](https://img.shields.io/badge/-Python-3776AB?style=flat-square&logo=python&logoColor=white) | Python 3.10+ | 主语言 |
| ![PySide6](https://img.shields.io/badge/-PySide6-41CD52?style=flat-square&logo=qt&logoColor=white) | PySide6 6.6 | GUI 框架 |
| ![wxauto](https://img.shields.io/badge/-wxauto-blue?style=flat-square) | wxauto | 微信 UIA 封装 |
| ![UIA](https://img.shields.io/badge/-Windows%20UIA-0078D6?style=flat-square&logo=windows&logoColor=white) | Windows UIA | 自动化底层 |
| ![PyInstaller](https://img.shields.io/badge/-PyInstaller-3776AB?style=flat-square) | PyInstaller | 打包 |
| ![Inno Setup](https://img.shields.io/badge/-Inno%20Setup-264E9B?style=flat-square) | Inno Setup 6 | 安装包 |
| ![YAML](https://img.shields.io/badge/-YAML-CB171E?style=flat-square&logo=yaml&logoColor=white) | PyYAML | 配置管理 |

---

## 📁 项目结构

```
wxAutoTool/
├── main.py                     # 🚀 程序入口（含 CMD 闪屏修复）
├── config.yaml                 # ⚙️ 默认配置
├── requirements.txt            # 📦 Python 依赖
├── build_reply.spec            # 📦 PyInstaller 打包配置
├── installer_reply.iss         # 📦 Inno Setup 安装脚本
│
├── core/                       # 🔧 核心逻辑
│   ├── config.py               #    配置管理（原子写入 + .bak 备份）
│   ├── monitor.py              #    监控调度
│   ├── wx_service.py           #    微信服务基类
│   ├── wx_service_uia.py       #    UIA 直采版（高性能增量拉取）
│   ├── logger.py               #    日志系统
│   ├── paths.py                #    路径管理
│   └── version.py              #    版本信息
│
├── gui/                        # 🎨 图形界面
│   ├── main_window.py          #    主窗口
│   ├── views.py                #    各功能页面
│   ├── widgets.py              #    自定义组件（日志、悬浮窗）
│   ├── style.qss               #    浅色主题样式
│   └── style_dark.qss          #    深色主题样式
│
├── resources/                  # 🖼️ 图标资源
│   ├── icon.ico
│   └── icon.png
│
└── wxauto/                     # 📚 wxauto 库（UIA 封装）
```

---

## ⚙️ 配置说明

配置文件 `config.yaml` 位于用户数据目录，支持以下字段：

<details>
<summary>📄 完整配置示例</summary>

```yaml
# 微信配置
wechat:
  target: ""                    # 默认监听对象

# 监控配置
monitor:
  interval: 2                   # 轮询间隔（秒）

# 行为配置
action:
  auto_reply: false             # 是否启用自动回复

# 监听对象列表
listeners:
  - name: "张三"                # 会话名称（与微信显示一致）
    enabled: true
    rules:
      - keyword: "你好"
        reply: "你好，我现在不方便回复"
    default_reply: "收到，稍后回复"

# 过滤规则
ignore_self: true               # 忽略自己发送的消息
ignore_system: true             # 忽略系统消息

# 发送配置
send_interval: 1.5              # 发送间隔（秒，防风控）

# 日志配置
log_file: logs/app.log

# 主题配置
theme: system                   # system(跟随系统) / light(浅色) / dark(深色)
```

</details>

---

## 🔧 开发指南

### 环境准备

```bash
# 克隆仓库
git clone https://github.com/Be-nothing/wxAutoTool.git
cd wxAutoTool

# 安装依赖
pip install -r requirements.txt
```

### 本地运行

```bash
python main.py
```

### 打包

```bash
# 1. PyInstaller 打包（生成 dist/微信自动回复助手/）
python -m PyInstaller build_reply.spec --noconfirm

# 2. Inno Setup 生成安装包（输出到 product/）
ISCC.exe installer_reply.iss
```

<details>
<summary>📦 打包注意事项</summary>

- 已排除 `urllib`、`PIL`、`socket` 等被间接依赖的模块
- 显式包含 `Qt6Svg.dll`、`Qt6SvgWidgets.dll` 解决 SVG 渲染问题
- 使用 LZMA2 ultra64 + solid 压缩，64MB → 20MB
- 安装包支持自定义目录（`UsePreviousAppDir=no`）

</details>

---

## 💡 技术要点

### 🔇 CMD 闪屏修复

打包为 windowed 模式（`console=False`）后，依赖库内部的 `subprocess.Popen` 和 `os.system` 会弹出 CMD 窗口。在 `main.py` 入口处 patch 这两个函数：

```python
# patch subprocess.Popen 强制加 CREATE_NO_WINDOW
_orig_popen = subprocess.Popen
def _patched_popen(*args, **kwargs):
    kwargs["creationflags"] = kwargs.get("creationflags", 0) | 0x08000000
    return _orig_popen(*args, **kwargs)
subprocess.Popen = _patched_popen

# patch os.system 阻止空命令弹 CMD（wxauto/color.py 的 os.system('')）
_orig_system = os.system
def _patched_system(cmd):
    if not cmd or not str(cmd).strip():
        return 0
    return subprocess.call(str(cmd), shell=True)
os.system = _patched_system
```

### ⚡ UIA 增量拉取

传统方式（`GetChildren`）全量遍历所有消息，复杂度 O(总数)。自研 UIA 直采版用 `GetLastChildControl` + `GetPreviousSiblingControl` 倒序遍历，遇到已读 ID 立即停止，复杂度降至 O(新增数)。

```
假设列表共 100 条，新增 2 条：
- wxauto GetNewMessage: GetChildren() 遍历 100 条 = 100+ 次 UIA 调用
- 本方法: GetLastChildControl + 2 次 GetPreviousSiblingControl = 3 次 UIA 调用
```

### 🌗 主题系统

通过两套 QSS 文件实现浅色/深色主题。跟随系统模式通过读取 Windows 注册表检测：

```python
key = winreg.OpenKey(
    winreg.HKEY_CURRENT_USER,
    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
)
value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
is_dark = (value == 0)  # 0 = 深色, 1 = 浅色
```

### ⚡ 快速发送优化

发送消息时绕过 wxauto 的 `_show()`（4 个 Win32 API 调用，耗时 0.5-1 秒），直接操作 editbox 粘贴发送：

```python
# 直接用 editbox 粘贴发送，跳过 wxauto SendMsg 的 _show()
SetClipboardText(msg)
editbox.SendKeys("{Ctrl}v")
editbox.SendKeys("{Enter}")
```

**窗口最小化场景**：发送前检测 `IsIconic`，是则 `SW_RESTORE` 恢复（不置顶），等待 150ms 让窗口管理器完成恢复，editbox 标记为 stale 由 property 按需 refind，避免发送阻塞。

**优化效果**：发送延迟从 5-6 秒降至 1-2 秒。

### 💾 配置原子写入

采用「写临时文件 → 备份旧文件 → 重命名」三步流程，避免写入中途崩溃导致配置损坏：

```
config.yaml.tmp  →  config.yaml.bak  →  config.yaml
（写入临时）        （备份旧文件）       （原子重命名）
```

---

## ❓ 常见问题

<details>
<summary><b>启动检测时提示"微信未连接"</b></summary>

- 确认微信 PC 版已登录并处于前台
- 确认微信窗口未被最小化到托盘
- 助手仅检测 `WeChatMainWndForPC` 窗口类，不支持网页版微信

</details>

<details>
<summary><b>监听对象测试失败</b></summary>

- 确认会话名称与微信中显示**完全一致**（包括 emoji、空格）
- 确认该会话在微信聊天列表中可见
- 尝试在微信中打开该会话窗口后重试

</details>

<details>
<summary><b>消息拉取失败/无响应</b></summary>

- 检查日志面板是否有 UIA 错误
- 确认未在监听期间手动关闭聊天窗口
- 重启助手并重新添加监听对象

</details>

<details>
<summary><b>安装后无法启动</b></summary>

- 检查是否被杀毒软件拦截（可添加信任）
- 以管理员身份运行
- 查看安装目录下的 `logs/app.log`

</details>

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request。

- 提交前请确保 `python -m py_compile` 无语法错误
- 遵循现有代码风格（PEP 8 + 中文注释）
- 新功能请附带说明文档

---

## 📄 许可证

私有项目，未经授权不得分发。

---

<div align="center">

**如果这个项目对你有帮助，请给一个 ⭐ Star**

[![Star History](https://api.star-history.com/svg?repos=Be-nothing/wxAutoTool&type=Date)](https://github.com/Be-nothing/wxAutoTool/stargazers)

---

<sub>Built with ❤️ using PySide6 + wxauto</sub>

</div>
