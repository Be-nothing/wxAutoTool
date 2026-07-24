# -*- coding: utf-8 -*-
"""路径管理：统一解析项目根目录与可写资源路径。

打包后（PyInstaller onedir）：
- 代码与只读资源在 _internal/ 下
- 可写文件（config.yaml、logs/）应放在 exe 同级目录，便于用户修改且不被清理

开发时（python main.py）：
- 项目根目录即代码根，读写都在这里
"""

import os
import sys


def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包环境中。"""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def app_root() -> str:
    """可写根目录：打包后为 exe 所在目录，开发时为项目根目录。"""
    if is_frozen():
        # 打包后：exe 所在目录（_internal 的上一级）
        return os.path.dirname(sys.executable)
    # 开发时：core/ 的上一级
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_root() -> str:
    """只读资源根目录：打包后为 _internal，开发时为项目根。"""
    if is_frozen():
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config_path() -> str:
    """配置文件路径（可写）。"""
    return os.path.join(app_root(), "config.yaml")


def log_dir() -> str:
    """日志目录路径（可写）。"""
    return os.path.join(app_root(), "logs")


def log_path() -> str:
    """日志文件路径（可写）。"""
    return os.path.join(log_dir(), "app.log")


def icon_path() -> str:
    """图标路径（只读资源）。"""
    return os.path.join(resource_root(), "resources", "icon.ico")


def qss_path() -> str:
    """样式表路径（只读资源）。"""
    return os.path.join(resource_root(), "gui", "style.qss")
