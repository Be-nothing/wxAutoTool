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

from PySide6.QtCore import QThread, Qt, Signal, QPoint, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QPainter, QBrush, QPalette, QFont
from PySide6.QtWidgets import QTextEdit, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QFrame

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
        "INFO": "#d4d4d8",
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
        color = self.LEVEL_COLORS.get(level, "#d4d4d8")
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


class MiniFloatWidget(QWidget):
    """迷你悬浮组件：启动检测后缩小到右上角，实时显示监听状态。

    特性：
    - 无边框、置顶、可拖动、半透明背景
    - 紧凑尺寸（200x56），不遮挡微信操作
    - 动态状态文本："正在添加监听对象 1/3..." → "监听中"
    - 点击切换"返回主界面"菜单
    """

    # 用户点击"返回主界面"时发射
    return_to_main = Signal()
    # 用户点击"停止检测"时发射
    stop_monitor = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._init_window_flags()
        self._build_ui()
        self._drag_offset: Optional[QPoint] = None

    def _init_window_flags(self) -> None:
        """无边框 + 置顶 + 工具窗口（不在任务栏显示）。"""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedSize(220, 60)

    def _build_ui(self) -> None:
        # 深色卡片背景
        self.setStyleSheet("""
            MiniFloatWidget {
                background: #2d2d30;
                border: 1px solid #3e3e42;
                border-radius: 10px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        # 状态行：圆点 + 状态文本
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: #f59e0b; font-size: 12px;")
        self.status_dot.setFixedWidth(14)
        top_row.addWidget(self.status_dot)

        self.status_label = QLabel("准备中...")
        self.status_label.setStyleSheet(
            "color: #ffffff; font-size: 12px; font-weight: 600;"
        )
        top_row.addWidget(self.status_label, 1)
        layout.addLayout(top_row)

        # 底部行：操作按钮
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)

        self.btn_return = QPushButton("返回主界面")
        self.btn_return.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #a8a8ab;
                border: none;
                font-size: 11px;
                padding: 2px 4px;
            }
            QPushButton:hover { color: #ffffff; }
        """)
        self.btn_return.clicked.connect(self.return_to_main.emit)
        bottom_row.addWidget(self.btn_return)

        self.btn_stop = QPushButton("停止")
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #ef4444;
                border: none;
                font-size: 11px;
                padding: 2px 4px;
            }
            QPushButton:hover { color: #f87171; }
        """)
        self.btn_stop.clicked.connect(self.stop_monitor.emit)
        bottom_row.addWidget(self.btn_stop)

        bottom_row.addStretch()
        layout.addLayout(bottom_row)

    def set_status(self, text: str, state: str = "running") -> None:
        """更新状态文本和圆点颜色。

        Args:
            text: 状态描述
            state: running(橙)/active(绿)/error(红)
        """
        self.status_label.setText(text)
        color_map = {
            "running": "#f59e0b",  # 橙：进行中
            "active": "#34c759",   # 绿：监听中
            "error": "#ef4444",    # 红：错误
        }
        self.status_dot.setStyleSheet(
            f"color: {color_map.get(state, '#f59e0b')}; font-size: 12px;"
        )

    # ---------- 拖动支持 ----------
    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            # 点击在按钮上时不拖动
            child = self.childAt(event.position().toPoint())
            if isinstance(child, QPushButton):
                return
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self._drag_offset = None
        event.accept()

    def show_at_top_right(self) -> None:
        """显示在屏幕右上角（距右边距 20px，距上边距 80px，避开任务栏）。"""
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.show()
            return
        geo = screen.availableGeometry()
        x = geo.right() - self.width() - 20
        y = geo.top() + 80
        self.move(x, y)
        self.show()
