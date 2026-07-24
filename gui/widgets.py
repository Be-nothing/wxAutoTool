# -*- coding: utf-8 -*-
"""自定义组件：监控线程 + 日志显示窗口。

线程模型：
    MainWindow ──start──> MonitorThread.run() ──> WechatMonitor.start()
             <──signal──  (log_message / status_changed / finished)

- MonitorThread 在子线程运行监控循环（阻塞），通过 Signal 回传日志/状态
- WechatMonitor.stop() 由主线程调用，置 running=False，循环安全退出
- 日志通过 core.logger 的全局回调桥接到 Signal，跨线程安全
"""

import logging
from typing import Optional

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit

from core.config import ConfigManager
from core.logger import set_gui_log_callback
from core.monitor import WechatMonitor


class MonitorThread(QThread):
    """监控后台线程：封装 WechatMonitor，通过 Signal 上报日志与状态。"""

    # (格式化日志文本, 级别名)
    log_message = Signal(str, str)
    # (状态类别, 状态值)：类别 "wechat"/"run"
    status_changed = Signal(str, str)
    # 线程结束
    monitor_finished = Signal()

    def __init__(self, config_manager: ConfigManager) -> None:
        super().__init__()
        self.config_manager = config_manager
        self.monitor: Optional[WechatMonitor] = None

    def run(self) -> None:
        """线程入口：创建监控器并启动阻塞循环。"""
        # 注册全局日志回调 → 转发到本线程的 Signal（跨线程投递到主线程）
        set_gui_log_callback(self._on_log)
        try:
            self.monitor = WechatMonitor(self.config_manager)
            self.monitor.set_status_callback(self._on_status)
            self.monitor.start()
        except Exception as e:
            logging.getLogger("wechat.gui").error(f"监控线程异常：{e}", exc_info=True)
        finally:
            set_gui_log_callback(None)
            self.monitor_finished.emit()

    def stop_monitor(self) -> None:
        """主线程调用：请求停止监控。"""
        if self.monitor is not None:
            self.monitor.stop()

    def _on_log(self, text: str, level: str) -> None:
        """日志回调（在产生日志的线程执行），emit Signal 转交主线程。"""
        try:
            self.log_message.emit(text, level)
        except RuntimeError:
            # 线程/对象已销毁时忽略
            pass

    def _on_status(self, kind: str, value: str) -> None:
        """状态回调（在工作线程执行），emit Signal 转交主线程。"""
        try:
            self.status_changed.emit(kind, value)
        except RuntimeError:
            pass


class LogTextEdit(QTextEdit):
    """实时日志显示窗口：按级别着色、自动滚动、限制最大行数。"""

    MAX_BLOCKS = 2000  # 超过此行数自动裁剪头部，避免内存膨胀

    # 级别 → 颜色
    LEVEL_COLORS = {
        "DEBUG": "#888888",
        "INFO": "#1f1f1f",
        "WARNING": "#cc7a00",
        "ERROR": "#cc0000",
        "CRITICAL": "#8b0000",
    }

    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        # 等宽字体，对齐日志时间戳
        self.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 12px;")

    def append_log(self, text: str, level: str) -> None:
        """追加一条日志，按级别着色。"""
        color = self.LEVEL_COLORS.get(level, "#1f1f1f")
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))

        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text + "\n", fmt)
        self.setTextCursor(cursor)

        # 自动滚动到底部
        self.ensureCursorVisible()

        # 裁剪超额行
        if self.document().blockCount() > self.MAX_BLOCKS:
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.movePosition(
                QTextCursor.MoveOperation.Down,
                QTextCursor.MoveMode.KeepAnchor,
                self.document().blockCount() - self.MAX_BLOCKS,
            )
            cursor.removeSelectedText()

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        """禁用编辑快捷键，仅允许复制。"""
        if event.key() == Qt.Key.Key_C and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.copy()
        # 其余按键不处理（只读）
