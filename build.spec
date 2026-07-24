# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：微信自动检测助手。

打包命令：
    pyinstaller build.spec

产物：dist/微信自动检测助手/微信自动检测助手.exe（单目录模式，便于携带依赖）

说明：
- onedir 模式：wxauto、libs(pywin32 DLL)、resources 需以真实路径存在，单目录最稳妥
- 携带 wxauto/、config.yaml、resources/、libs/ 到产物根目录
"""

import os

block_cipher = None

BASE_DIR = os.path.abspath(".")

a = Analysis(
    ["main.py"],
    pathex=[BASE_DIR],
    binaries=[],
    datas=[
        # wxauto 核心库
        ("wxauto", "wxauto"),
        # 配置文件
        ("config.yaml", "."),
        # 资源（图标、样式）
        ("resources", "resources"),
        # GUI 样式
        ("gui/style.qss", "gui"),
        # libs 依赖（pywin32 DLL、pystray 等，确保离线运行）
        ("libs", "libs"),
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
        # core 子模块（函数内 import 需显式声明）
        "core.paths",
        "core.config",
        "core.logger",
        "core.wx_service",
        "core.monitor",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name="微信自动检测助手",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI 程序，无控制台
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join("resources", "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="微信自动检测助手",
)
