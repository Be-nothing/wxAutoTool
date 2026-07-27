# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：微信自动回复助手（UIA 直采版）。

打包命令：
    pyinstaller build_reply.spec

产物：dist/微信自动回复助手/微信自动回复助手.exe

与 build_uia.spec 的差异：
- 产物名称改为"微信自动回复助手"，输出目录独立，不覆盖旧产物
- 种子 config.yaml 不再含 use_uia 字段（代码已强制启用 UIA）
- FileDescription / ProductName 同步更新
"""

import os
import yaml

block_cipher = None

BASE_DIR = os.path.abspath(".")

# === 生成干净种子 config.yaml ===
# 不读取项目根 config.yaml（含开发者私人数据），直接生成干净配置
# 安装包发给别人时，接收者看到的是空白配置，需要自己添加监听对象
_seed_config_path = os.path.join(BASE_DIR, "build_reply", "config.yaml")
os.makedirs(os.path.dirname(_seed_config_path), exist_ok=True)
_seed_cfg = {
    "wechat": {"target": ""},
    "monitor": {"interval": 2},
    "action": {"auto_reply": False},
    "listeners": [],  # 空：用户自行配置
    "ignore_self": True,
    "ignore_system": True,
    "send_interval": 1.5,
    "log_file": "logs/app.log",
}
with open(_seed_config_path, "w", encoding="utf-8") as _f:
    yaml.safe_dump(_seed_cfg, _f, allow_unicode=True, sort_keys=False)

# === 版本号：从 core/version.py 读取（唯一来源） ===
_version_ns: dict = {}
with open(os.path.join(BASE_DIR, "core", "version.py"), encoding="utf-8") as _f:
    exec(_f.read(), _version_ns)
VERSION = _version_ns["VERSION"]
VERSION_TUPLE = _version_ns["VERSION_TUPLE"]

# 生成 Windows 版本信息文件
_version_info_path = os.path.join(BASE_DIR, "build_reply", "version_info.txt")
os.makedirs(os.path.dirname(_version_info_path), exist_ok=True)
_version_info = f"""# UTF-8
# 自动生成，请勿手动编辑。版本号维护于 core/version.py
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={VERSION_TUPLE},
    prodvers={VERSION_TUPLE},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
    ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'080404B0',
        [StringStruct(u'CompanyName', u'wxAutoTool'),
        StringStruct(u'FileDescription', u'微信自动回复助手'),
        StringStruct(u'FileVersion', u'{VERSION}'),
        StringStruct(u'InternalName', u'wxAutoTool_reply'),
        StringStruct(u'LegalCopyright', u''),
        StringStruct(u'OriginalFilename', u'微信自动回复助手.exe'),
        StringStruct(u'ProductName', u'微信自动回复助手'),
        StringStruct(u'ProductVersion', u'{VERSION}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [0x0804, 1200])])
  ]
)
"""
with open(_version_info_path, "w", encoding="utf-8") as _f:
    _f.write(_version_info)

a = Analysis(
    ["main.py"],
    pathex=[BASE_DIR],
    binaries=[
        # 显式添加 Qt6Svg.dll / Qt6SvgWidgets.dll
        # PyInstaller 默认漏收集，但 QtSvg.pyd 依赖 Qt6Svg.dll（SVG 图标渲染必需）
        (r"C:\Users\34088\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\python\lib\site-packages\PySide6\Qt6Svg.dll", "PySide6"),
        (r"C:\Users\34088\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\python\lib\site-packages\PySide6\Qt6SvgWidgets.dll", "PySide6"),
    ],
    datas=[
        ("wxauto", "wxauto"),
        ("build_reply/config.yaml", "."),  # 干净种子配置
        # 只打包 icon.ico（代码仅引用 ico，icon.png 1.08MB 未使用）
        ("resources/icon.ico", "resources"),
        ("gui/style.qss", "gui"),
        ("gui/style_dark.qss", "gui"),
    ],
    hiddenimports=[
        "wxauto",
        "wxauto.wxauto",
        "wxauto.uiautomation",
        "wxauto.utils",
        "wxauto.elements",
        "wxauto.errors",
        "wxauto.languages",
        "wxauto.color",
        "pythoncom",
        "pywintypes",
        "win32api",
        "win32gui",
        "win32con",
        "win32clipboard",
        "win32process",
        "pyperclip",
        "psutil",
        "pystray._win32",
        "comtypes",
        "comtypes.client",
        "comtypes.gen",
        "yaml",
        "core.paths",
        "core.config",
        "core.logger",
        "core.wx_service",
        "core.wx_service_uia",
        "core.monitor",
        "core.version",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 排除无用模块，减少安装包体积
    excludes=[
        # 注：PIL/Pillow 不可排除！wxauto.uiautomation 依赖 PIL.ImageGrab
        "numpy", "numpy.libs",      # PIL 的依赖（Pillow 已不依赖 numpy，可安全排除）
        "setuptools", "pip",        # 打包工具
        "PyInstaller",              # 打包工具
        "pythonwin", "pywin",       # MFC GUI 框架
        "win32comext", "isapi",     # 未使用的 COM 扩展
        "adodbapi",                 # 数据库
        "matplotlib", "scipy",      # 科学计算
        "tkinter",                  # Tk GUI
        "unittest", "test",         # 测试框架
        "pydoc", "doctest",         # 文档工具
        # 第二轮瘦身：无压缩/XML 需求
        # 注：pathlib 不依赖 socket，但依赖 urllib.parse（不可排除 urllib）
        "libcrypto", "libssl",      # OpenSSL DLL（无网络需求）
        "_decimal",                 # 高精度十进制
        "pyexpat",                  # XML 解析器（PyYAML 自带）
        "_lzma",                    # LZMA 压缩
        "_bz2",                     # BZ2 压缩
        "xml", "xmlrpc",            # XML 全套
        "email",                    # 邮件
        "ftplib", "telnetlib",      # FTP/Telnet
        "smtplib", "poplib", "imaplib",  # 邮件协议
        "nntplib", "webbrowser",    # 新闻组/浏览器
        "xmlrpc.server", "xmlrpc.client",
        # 第三轮瘦身：仅排除项目确定不用、且无间接依赖的模块
        # 注意 1: socket/ssl/select 不可排除！psutil 依赖 socket（psutil/__init__.py:27）
        # 注意 2: urllib/http 不可排除！pathlib.as_uri() 依赖 urllib.parse
        # 注意 3: _hashlib.pyd 依赖 libcrypto-1_1.dll，DLL 已被删除，必须一并排除以避免 import 时崩溃
        "asyncio", "_asyncio", "_overlapped",     # 项目不用异步
        "multiprocessing", "_multiprocessing",   # 项目不用多进程
        "hashlib", "_hashlib",                     # 项目不用哈希，且 libcrypto DLL 已删
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="微信自动回复助手",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join("resources", "icon.ico"),
    version=_version_info_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="微信自动回复助手",
)

# === 打包后清理：删除 PySide6 中未使用的模块和资源，减少体积 ===
# 这些 DLL 在 QWidget 应用中完全不需要
import shutil as _shutil
import os as _os

_dist_dir = _os.path.join(BASE_DIR, "dist", "微信自动回复助手", "_internal")
_ps_dir = _os.path.join(_dist_dir, "PySide6")

# PySide6 无用 DLL（QWidget 应用不使用 QML/Quick/Pdf/Network/OpenGL/测试）
_ps_unused_files = [
    "opengl32sw.dll",       # 19.68 MB - 软件渲染器
    "Qt6Quick.dll",         # 6.29 MB - QML 引擎
    "Qt6Qml.dll",           # 5.13 MB - QML
    "Qt6Pdf.dll",           # 4.40 MB - PDF 模块
    "Qt6Network.dll",       # 1.69 MB - 网络
    "Qt6OpenGL.dll",        # 1.89 MB - OpenGL
    "Qt6Test.dll",          # 测试
    "Qt6PrintSupport.dll",  # 打印
    "Qt6Designer.dll",      # 设计器
    "Qt6Help.dll",          # 帮助
    "Qt6Location.dll",      # 定位
    "Qt6Multimedia.dll",    # 多媒体
    "Qt6Sql.dll",           # SQL
    # 注：Qt6Svg.dll / Qt6SvgWidgets.dll 不可删除！QtSvg.pyd 依赖它们（SVG 图标渲染）
    "Qt6WebEngineCore.dll",
    "Qt6WebEngineQuick.dll",
    "Qt6WebEngineWidgets.dll",
    "Qt6WebChannel.dll",
    "Qt6SerialPort.dll",
    "Qt6Bluetooth.dll",
    "Qt6Charts.dll",        # 暂时不用图表，后续 UI 重构时按需保留
    "Qt6DataVisualization.dll",
    "Qt6VirtualKeyboard.dll",
    "libEGL.dll",
    "libGLESv2.dll",
    "d3dcompiler_47.dll",
]

for _fname in _ps_unused_files:
    _p = _os.path.join(_ps_dir, _fname)
    if _os.path.exists(_p):
        _os.remove(_p)

# translations 整目录删除（app 用硬编码中文，不加载 Qt 翻译文件）
_trans_dir = _os.path.join(_ps_dir, "translations")
if _os.path.isdir(_trans_dir):
    _shutil.rmtree(_trans_dir, ignore_errors=True)

# plugins 只保留必要的：platforms/qwindows.dll, imageformats/qjpeg.dll, qico.dll
_plugins_dir = _os.path.join(_ps_dir, "plugins")
_keep_plugins = {
    "platforms": ["qwindows.dll"],
    "imageformats": ["qjpeg.dll", "qico.dll"],
    "styles": ["qmodernwindowsstyle.dll"],
}
if _os.path.isdir(_plugins_dir):
    for _subdir in _os.listdir(_plugins_dir):
        _sub_path = _os.path.join(_plugins_dir, _subdir)
        if not _os.path.isdir(_sub_path):
            continue
        _keep = _keep_plugins.get(_subdir, [])
        for _f in _os.listdir(_sub_path):
            if _f not in _keep:
                _fp = _os.path.join(_sub_path, _f)
                if _os.path.isfile(_fp):
                    _os.remove(_fp)

# 删除 PyWin32.chm 帮助文档
_chm = _os.path.join(_dist_dir, "libs", "PyWin32.chm")
if _os.path.exists(_chm):
    _os.remove(_chm)

# === 第二轮瘦身：删除 PySide6 残留的 QML/Network 绑定 ===
# QtNetwork.pyd（Qt6Network.dll 已删，pyd 是孤儿）
_qtnet_pyd = _os.path.join(_ps_dir, "QtNetwork.pyd")
if _os.path.exists(_qtnet_pyd):
    _os.remove(_qtnet_pyd)
# QML 相关 DLL（QWidget 不用）
for _qml_dll in ["Qt6QmlModels.dll", "Qt6QmlMeta.dll", "Qt6Qml.dll", "Qt6QmlWorkerScript.dll", "Qt6Quick.dll", "Qt6Quick3d.dll", "Qt6QuickControls2.dll", "Qt6QuickTemplates2.dll", "Qt6QuickWidgets.dll"]:
    _p = _os.path.join(_ps_dir, _qml_dll)
    if _os.path.exists(_p):
        _os.remove(_p)
# QML/QtQuick 目录
for _qml_dir in ["qml", "QtQuick"]:
    _p = _os.path.join(_ps_dir, _qml_dir)
    if _os.path.isdir(_p):
        _shutil.rmtree(_p, ignore_errors=True)

# === 删除 OpenSSL DLL（项目无网络需求，ssl/socket/hashlib 已在 excludes 中排除）===
# 注：urllib/http 未排除（pathlib 运行时依赖 urllib.parse）
for _ssl_file in ["libcrypto-1_1.dll", "libssl-1_1.dll"]:
    _p = _os.path.join(_dist_dir, _ssl_file)
    if _os.path.exists(_p):
        _os.remove(_p)

# === 删除无用的 Python 扩展 ===
for _unused_pyd in ["_decimal.pyd", "pyexpat.pyd", "_lzma.pyd", "_bz2.pyd"]:
    _p = _os.path.join(_dist_dir, _unused_pyd)
    if _os.path.exists(_p):
        _os.remove(_p)

# === 第三轮瘦身：删除异步/多进程/哈希相关 .pyd ===
# 注意 1: _hashlib.pyd 依赖已被删除的 libcrypto-1_1.dll，必须删除以避免运行时崩溃
# 注意 2: _ssl/_socket/select/_queue 不可删除！psutil 间接依赖 socket
for _unused_pyd in [
    "_asyncio.pyd", "_overlapped.pyd",
    "_multiprocessing.pyd", "_hashlib.pyd",
]:
    _p = _os.path.join(_dist_dir, _unused_pyd)
    if _os.path.exists(_p):
        _os.remove(_p)

# === 第四轮瘦身：删除 api-ms-win-*.dll（Windows 10+ 系统自带，冗余）===
# 这些是 Windows API Set 转发器（转发到 kernel32.dll/ucrtbase.dll 等），
# Windows 10+ 系统目录 C:\Windows\System32 已内置。
# PyInstaller 为兼容旧系统打包，但微信本身要求 Win10+，这些 DLL 完全冗余。
# 删除 42 个小文件（约 1MB），显著减少安装时文件创建数量和杀毒扫描开销。
for _f in _os.listdir(_dist_dir):
    if _f.lower().startswith("api-ms-win-") and _f.lower().endswith(".dll"):
        _os.remove(_os.path.join(_dist_dir, _f))

# 删除 .dist-info 目录（pip 元数据，运行时无用）
for _item in _os.listdir(_dist_dir):
    if _item.endswith(".dist-info"):
        _shutil.rmtree(_os.path.join(_dist_dir, _item), ignore_errors=True)
_libs_dir = _os.path.join(_dist_dir, "libs")
if _os.path.isdir(_libs_dir):
    for _item in _os.listdir(_libs_dir):
        if _item.endswith(".dist-info"):
            _shutil.rmtree(_os.path.join(_libs_dir, _item), ignore_errors=True)

# 删除 __pycache__ 目录
for _root, _dirs, _files in _os.walk(_dist_dir):
    for _d in _dirs:
        if _d == "__pycache__":
            _shutil.rmtree(_os.path.join(_root, _d), ignore_errors=True)
