# -*- coding: utf-8 -*-
"""日志管理模块。

同时输出到：
1. 文件 logs/app.log（FileHandler）
2. 控制台（StreamHandler，调试用）
3. GUI 日志窗口（GuiLogHandler → 回调，由 GUI 层注册）

本模块不依赖 PySide6，通过回调将日志文本转发给 GUI，避免循环依赖。
"""

import logging
import os
from typing import Callable, Optional

from core.paths import log_dir, log_path

# 日志文件路径（打包后为 exe 同级，开发时为项目根）
DEFAULT_LOG_FILE = log_path()

# 日志格式
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
DATE_FORMAT = "%H:%M:%S"

# 回调签名：(格式化后的日志文本, 日志级别名)
LogCallback = Callable[[str, str], None]


class GuiLogHandler(logging.Handler):
    """将日志通过回调转发到 GUI 的 Handler。

    GUI 层通过 set_gui_log_callback 注册回调；未注册时静默丢弃（不影响文件/控制台输出）。
    """

    def __init__(self) -> None:
        super().__init__()
        self._callback: Optional[LogCallback] = None

    def set_callback(self, callback: Optional[LogCallback]) -> None:
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = self.format(record)
            if self._callback is not None:
                self._callback(text, record.levelname)
        except Exception:
            # 日志 Handler 内部绝不能再抛出异常
            pass


# 全局 GUI Handler 引用（由 setup_logging 创建）
_gui_handler: Optional[GuiLogHandler] = None
# 待注册回调：GUI 可能在 setup_logging 之前注册，此时先暂存
_pending_callback: Optional[LogCallback] = None


def setup_logging(
    log_file: str = DEFAULT_LOG_FILE,
    level: int = logging.INFO,
) -> logging.Logger:
    """初始化 root logger，挂载文件/控制台/GUI 三个 Handler。"""
    global _gui_handler

    log_dirpath = os.path.dirname(log_file)
    if log_dirpath and not os.path.isdir(log_dirpath):
        os.makedirs(log_dirpath, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(level)
    # 清空旧 Handler，避免重复初始化时日志重复输出
    logger.handlers.clear()

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    _gui_handler = GuiLogHandler()
    _gui_handler.setFormatter(formatter)
    # 应用暂存的回调
    if _pending_callback is not None:
        _gui_handler.set_callback(_pending_callback)
    logger.addHandler(_gui_handler)

    return logger


def get_logger(name: str = "wechat") -> logging.Logger:
    """获取命名 logger。"""
    return logging.getLogger(name)


def set_gui_log_callback(callback: Optional[LogCallback]) -> None:
    """注册 GUI 日志回调。

    若 setup_logging 尚未调用，则暂存回调，待初始化时应用。
    """
    global _pending_callback
    _pending_callback = callback
    if _gui_handler is not None:
        _gui_handler.set_callback(callback)
