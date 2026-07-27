# -*- coding: utf-8 -*-
"""路径管理：统一解析项目根目录与可写资源路径。

打包后（PyInstaller onedir）：
- 代码与只读资源在 _internal/ 下
- 可写文件（config.yaml、logs/）放在 %APPDATA%\wxAutoTool\ 下，
  与 exe 完全分离，重新打包不会覆盖用户配置

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


def _user_data_dir() -> str:
    """用户数据目录：打包后优先 %LOCALAPPDATA%\\wxAutoTool，开发时为项目根。

    将配置和日志放到用户目录，避免重新打包时 dist 被清空导致配置丢失。
    依次尝试 %LOCALAPPDATA%、%APPDATA%、exe 同级目录，返回第一个可写的。

    根据 exe 名字决定目录名，实现多版本隔离：
    - 含 "_uia" → wxAutoTool_uia（旧 UIA 版本）
    - 含 "回复" → wxAutoTool_reply（微信自动回复助手）
    - 其他 → wxAutoTool
    """
    if is_frozen():
        # 根据 exe 名字决定目录名，实现多版本隔离
        exe_name = os.path.basename(sys.executable)
        if "_uia" in exe_name.lower():
            dir_name = "wxAutoTool_uia"
        elif "回复" in exe_name:
            dir_name = "wxAutoTool_reply"
        else:
            dir_name = "wxAutoTool"
        candidates = []
        for env_key in ("LOCALAPPDATA", "APPDATA"):
            env_val = os.environ.get(env_key)
            if env_val:
                candidates.append(os.path.join(env_val, dir_name))
        candidates.append(os.path.dirname(sys.executable))  # exe 同级目录兜底

        for path in candidates:
            try:
                os.makedirs(path, exist_ok=True)
                test_file = os.path.join(path, ".write_test")
                with open(test_file, "w") as f:
                    f.write("ok")
                os.remove(test_file)
                return path
            except Exception:
                continue
        # 全部失败，返回最后一个（exe 同级目录）
        return candidates[-1]
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config_path() -> str:
    """配置文件路径（可写，与 exe 分离）。"""
    return os.path.join(_user_data_dir(), "config.yaml")


def log_dir() -> str:
    """日志目录路径（可写，与 exe 分离）。"""
    return os.path.join(_user_data_dir(), "logs")


def log_path() -> str:
    """日志文件路径（可写，与 exe 分离）。"""
    return os.path.join(log_dir(), "app.log")


def icon_path() -> str:
    """图标路径（只读资源）。"""
    return os.path.join(resource_root(), "resources", "icon.ico")


def qss_path(filename: str = "style.qss") -> str:
    """样式表路径（只读资源，可指定文件名）。"""
    return os.path.join(resource_root(), "gui", filename)
