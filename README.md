# 微信自动回复助手

基于 PySide6 + wxauto 的微信 PC 版自动回复工具，提供友好的图形界面，支持监听指定对象并自动回复。

## 功能特性

- **图形界面**：基于 PySide6 的现代化 UI，支持浅色/深色/跟随系统主题
- **自动监听**：基于 Windows UIA 自动化，实时监听指定微信会话的新消息
- **规则回复**：支持为每个监听对象配置独立的回复规则（关键词匹配、默认回复）
- **性能优化**：UIA 直采版增量拉取，仅对新消息触发处理，避免全量遍历
- **状态检测**：启动前自动检测微信连接状态，未连接不允许启动
- **悬浮组件**：启动检测后可缩小为悬浮组件，实时显示监听状态
- **日志面板**：实时彩色日志，按级别着色，自动滚动
- **一键打包**：PyInstaller + Inno Setup，生成单一安装包

## 界面预览

- 仪表盘：实时显示微信连接状态、监听对象数、今日消息数
- 监听对象：添加/编辑/删除/测试监听对象，配置回复规则
- 日志面板：彩色实时日志，支持自动滚动和行数限制
- 设置：监听间隔、自动回复开关、忽略系统消息、主题切换

## 快速开始

### 安装

1. 前往 [Releases](../../releases) 下载最新版安装包
2. 运行 `微信自动回复助手_Setup_v*.exe`
3. 按提示完成安装（可自定义安装目录）

### 使用

1. 启动微信 PC 版并登录
2. 打开"微信自动回复助手"
3. 在"监听对象"页添加需要监听的微信会话名称
4. 配置回复规则（关键词 → 回复内容）
5. 点击"启动检测"，确认后开始自动监听

### 前置要求

- Windows 10/11（64 位）
- 微信 PC 版 3.9+ 已登录
- .NET Framework 4.7+（Windows 自带）

## 项目结构

```
wxAutoTool/
├── main.py                 # 程序入口（含 CMD 闪屏修复）
├── config.yaml             # 默认配置
├── requirements.txt        # Python 依赖
├── build_reply.spec        # PyInstaller 打包配置
├── installer_reply.iss     # Inno Setup 安装脚本
├── core/                   # 核心逻辑
│   ├── config.py           # 配置管理
│   ├── monitor.py          # 监控调度
│   ├── wx_service.py       # 微信服务基类
│   ├── wx_service_uia.py   # UIA 直采版（高性能）
│   ├── logger.py           # 日志系统
│   └── paths.py            # 路径管理
├── gui/                    # 图形界面
│   ├── main_window.py      # 主窗口
│   ├── views.py            # 各功能页面
│   ├── widgets.py          # 自定义组件
│   ├── style.qss           # 浅色主题样式
│   └── style_dark.qss      # 深色主题样式
├── resources/              # 图标资源
└── wxauto/                 # wxauto 库（UIA 封装）
```

## 开发

### 环境准备

```bash
pip install -r requirements.txt
```

### 本地运行

```bash
python main.py
```

### 打包

```bash
# 1. PyInstaller 打包
python -m PyInstaller build_reply.spec --noconfirm

# 2. Inno Setup 生成安装包
ISCC.exe installer_reply.iss
```

安装包输出到 `product/` 目录。

## 技术要点

### CMD 闪屏修复

打包为 windowed 模式（`console=False`）后，依赖库内部的 `subprocess.Popen` 和 `os.system` 会弹出 CMD 窗口。在 `main.py` 入口处 patch 这两个函数，强制添加 `CREATE_NO_WINDOW` 标志。

### UIA 增量拉取

传统方式（`GetChildren`）全量遍历所有消息，O(总数)。自研 UIA 直采版用 `GetLastChildControl` + `GetPreviousSiblingControl` 倒序遍历，遇到已读 ID 立即停止，O(新增数)。

### 主题系统

通过两套 QSS 文件（`style.qss` / `style_dark.qss`）实现浅色/深色主题。跟随系统模式通过读取 Windows 注册表 `AppsUseLightTheme` 检测系统主题。

## License

私有项目，未经授权不得分发。
