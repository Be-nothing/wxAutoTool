# -*- coding: utf-8 -*-
"""主窗口：导航+工作区布局。

左侧图标导航栏切换四个视图（仪表盘/监听对象/日志/设置），
主区域用 QStackedWidget 每次专注一个视图。
启动流程（确认→悬浮→切回）与监控线程管理在此协调。
"""

import logging
import os
import sys
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QSettings
from PySide6.QtGui import QAction, QIcon, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from core.config import ConfigManager
from core.logger import setup_logging
from core.paths import icon_path, qss_path
from core.version import VERSION
from gui.views import (
    DashboardView,
    ListenersView,
    LogView,
    NavButton,
    SettingsView,
    _SVG_DASHBOARD,
    _SVG_MESSAGE,
    _SVG_FILE,
    _SVG_SETTINGS,
    _SVG_LAYERS,
    _svg_to_pixmap,
)
from gui.widgets import LogTextEdit, MonitorThread, MiniFloatWidget


def _load_icon() -> QIcon:
    """加载图标，文件不存在时返回空图标（不报错）。"""
    p = icon_path()
    if os.path.exists(p):
        return QIcon(p)
    return QIcon()


class MainWindow(QMainWindow):
    """主窗口：导航+工作区四视图。"""

    def __init__(self) -> None:
        super().__init__()
        self.config_manager = ConfigManager()
        self.monitor_thread: Optional[MonitorThread] = None
        self._really_quit = False  # 托盘"退出"才真正退出，否则隐藏到托盘
        self.mini_float: Optional[MiniFloatWidget] = None

        self._build_ui()
        self._build_tray()
        self._apply_style()
        self._update_button_state()
        self._refresh_listen_count()

        # 微信状态定时检测：启动时检测一次，之后每 5 秒轮询
        # 监控运行期间由 monitor 回调更新状态，跳过轮询
        self._wx_status_timer = QTimer(self)
        self._wx_status_timer.timeout.connect(self._refresh_wx_status)
        self._wx_status_timer.start(5000)
        # 延迟 500ms 首次检测，避免阻塞窗口显示
        QTimer.singleShot(500, self._refresh_wx_status)

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.setWindowTitle(f"微信自动回复助手 v{VERSION}")
        self.setWindowIcon(_load_icon())
        self.resize(880, 600)
        self.setMinimumSize(680, 480)

        # 菜单栏（保留 F1 关于）
        menubar = self.menuBar()
        help_menu = menubar.addMenu("帮助(&H)")
        act_about = QAction("关于(&A)", self)
        act_about.setShortcut("F1")
        act_about.triggered.connect(self._on_about)
        help_menu.addAction(act_about)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 左侧导航栏
        nav = self._build_nav()
        root.addWidget(nav)

        # 右侧工作区
        self.stack = QStackedWidget()
        self.stack.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.stack, 1)

        # 创建日志视图（共享 LogTextEdit 实例）
        self.log_view = LogTextEdit()

        # 四个视图
        self.dashboard_view = DashboardView()
        self.listeners_view = ListenersView(
            self.config_manager,
            verify_callback=self._verify_listener_name,
        )
        self.log_container = LogView(self.log_view)
        self.settings_view = SettingsView(
            self.config_manager,
            is_running_cb=self._is_running,
        )

        self.stack.addWidget(self.dashboard_view)
        self.stack.addWidget(self.listeners_view)
        self.stack.addWidget(self.log_container)
        self.stack.addWidget(self.settings_view)

        # 信号连接
        self.dashboard_view.start_requested.connect(self.on_start)
        self.dashboard_view.stop_requested.connect(self.on_stop)
        self.dashboard_view.nav_to_listeners.connect(lambda: self._switch_view(1))
        self.listeners_view.config_saved.connect(self._refresh_listen_count)
        self.settings_view.config_saved.connect(self._on_settings_saved)

    def _build_nav(self) -> QWidget:
        """左侧导航栏：SVG 图标按钮垂直排列 + 底部缩小按钮。"""
        nav = QFrame()
        nav.setObjectName("navBar")
        nav.setFixedWidth(76)
        layout = QVBoxLayout(nav)
        layout.setContentsMargins(0, 20, 0, 20)
        layout.setSpacing(4)

        # 应用 logo
        logo_lbl = QLabel()
        logo_lbl.setPixmap(_svg_to_pixmap(_SVG_LAYERS, "#3370ff", 28))
        logo_lbl.setFixedSize(32, 32)
        logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_lay = QHBoxLayout()
        logo_lay.addStretch()
        logo_lay.addWidget(logo_lbl)
        logo_lay.addStretch()
        layout.addLayout(logo_lay)
        layout.addSpacing(20)

        self.nav_btns = QButtonGroup(self)
        self.nav_btns.setExclusive(True)

        buttons = [
            (_SVG_DASHBOARD, "概览"),
            (_SVG_MESSAGE, "监听"),
            (_SVG_FILE, "日志"),
            (_SVG_SETTINGS, "设置"),
        ]
        for i, (svg, text) in enumerate(buttons):
            btn = NavButton(svg, text)
            btn.clicked.connect(lambda checked, idx=i: self._switch_view(idx))
            self.nav_btns.addButton(btn, i)
            layout.addWidget(btn)

        # 默认选中第一个
        self.nav_btns.button(0).setChecked(True)

        layout.addStretch()

        # 缩小为悬浮组件按钮（仅检测运行时可用）
        self.minimize_btn = QPushButton("")
        self.minimize_btn.setObjectName("navMinBtn")
        self.minimize_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.minimize_btn.setEnabled(False)
        self.minimize_btn.clicked.connect(self._on_minimize_to_float)
        layout.addWidget(self.minimize_btn)

        return nav

    def _switch_view(self, idx: int) -> None:
        """切换工作区视图。"""
        self.stack.setCurrentIndex(idx)

    def _build_tray(self) -> None:
        """系统托盘：图标 + 右键菜单 + 双击显示。"""
        self.tray = QSystemTrayIcon(_load_icon(), self)
        self.tray.setToolTip(f"微信自动回复助手 v{VERSION}")
        menu = QMenu(self)
        act_show = QAction("显示主窗口", self)
        act_start = QAction("启动检测", self)
        act_stop = QAction("停止检测", self)
        act_quit = QAction("退出程序", self)
        act_show.triggered.connect(self._show_from_tray)
        act_start.triggered.connect(self.on_start)
        act_stop.triggered.connect(self.on_stop)
        act_quit.triggered.connect(self._quit_from_tray)
        menu.addAction(act_show)
        menu.addSeparator()
        menu.addAction(act_start)
        menu.addAction(act_stop)
        menu.addSeparator()
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _apply_style(self) -> None:
        """加载 QSS 样式（根据主题选择浅色/深色）。"""
        theme = self.config_manager.get("theme", "system")
        if theme == "system":
            theme = "dark" if self._is_system_dark() else "light"
        qss_file = "style_dark.qss" if theme == "dark" else "style.qss"
        p = qss_path(qss_file)
        if not os.path.exists(p):
            p = qss_path()  # 回退到默认 style.qss
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    @staticmethod
    def _is_system_dark() -> bool:
        """检测 Windows 系统是否使用深色主题。"""
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return value == 0  # 0 = 深色, 1 = 浅色
        except Exception:
            return False

    # ------------------------------------------------------------------
    # 状态更新
    # ------------------------------------------------------------------
    def _is_running(self) -> bool:
        return self.monitor_thread is not None and self.monitor_thread.isRunning()

    def _update_button_state(self) -> None:
        running = self._is_running()
        self.dashboard_view.start_btn.setEnabled(not running)
        self.dashboard_view.stop_btn.setEnabled(running)
        self.minimize_btn.setEnabled(running)

    def _refresh_listen_count(self) -> None:
        """刷新仪表盘的监听对象计数。"""
        count = len(self.config_manager.config.get("listeners", []) or [])
        self.dashboard_view.update_listen_count(count)

    def _refresh_wx_status(self) -> None:
        """刷新仪表盘的微信连接状态（仅在未监控时主动检测）。"""
        # 监控运行中由 monitor 回调更新，跳过
        if self._is_running():
            return
        connected = self._check_wx_connected()
        self._set_wx_status("connected" if connected else "disconnected")

    def _set_wx_status(self, value: str) -> None:
        connected = (value == "connected")
        self.dashboard_view.update_wx_status(connected)

    def _set_run_status(self, value: str) -> None:
        running = (value == "running")
        self.dashboard_view.update_run_status(running)

    def _on_settings_saved(self) -> None:
        """设置视图保存后，重新加载配置并重新应用样式（主题可能已更改）。"""
        self.config_manager.load()
        self._apply_style()
        # 刷新导航按钮图标颜色（适配新主题）
        for i in range(self.nav_btns.buttons().__len__()):
            btn = self.nav_btns.button(i)
            if btn is not None:
                btn._update_icon()

    # ------------------------------------------------------------------
    # 关于
    # ------------------------------------------------------------------
    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "关于",
            f"<h3>微信自动回复助手</h3>"
            f"<p>版本：v{VERSION}</p>"
            f"<p>基于 Windows UI 自动化技术，自动检测微信消息并按规则回复。</p>"
            f"<p><b>主要功能：</b></p>"
            f"<ul>"
            f"<li>监听指定群聊/私聊的新消息</li>"
            f"<li>按发送人 + 关键词匹配回复规则</li>"
            f"<li>UIA 增量拉取，响应快、开销低</li>"
            f"<li>按聊天对象独立限流，避免风控</li>"
            f"</ul>"
            f"<p><b>配置与日志位置：</b><br>%LOCALAPPDATA%\\wxAutoTool_reply\\</p>"
            f"<p><b>项目地址：</b>"
            f"<a href='https://github.com/Be-nothing/wxAutoTool'>"
            f"github.com/Be-nothing/wxAutoTool</a></p>"
            f"<hr>"
            f"<p style='color:#888;'>本软件仅供个人学习研究使用，"
            f"请遵守微信用户协议和相关法律法规。</p>"
        )

    # ------------------------------------------------------------------
    # 启动/停止
    # ------------------------------------------------------------------
    def on_start(self) -> None:
        """启动检测：预检微信 → 确认 → 缩小为悬浮组件 → 后台启动监控 → 完成后切回主窗口。"""
        if self._is_running():
            return

        # 启动前重新加载配置，确保改动生效
        self.config_manager.load()
        self.listeners_view.reload()
        self.settings_view.reload()

        # 自动检测微信连接状态：未连接则不允许启动
        if not self._check_wx_connected():
            QMessageBox.warning(
                self,
                "微信未连接",
                "未检测到微信客户端，请确认微信已登录并处于前台后重试。",
            )
            return

        ret = QMessageBox.question(
            self,
            "启动检测",
            "即将连接微信并自动选择监听对象。\n\n"
            "请在接下来的几秒内：\n"
            "• 不要移动鼠标和键盘\n"
            "• 不要切换微信窗口\n"
            "• 保持微信客户端已登录",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Ok,
        )
        if ret != QMessageBox.StandardButton.Ok:
            return

        # 立即显示"启动中"状态
        self.dashboard_view.update_stage("正在启动...", "running")

        # 创建悬浮组件并显示在右上角
        self._create_mini_float()
        self.mini_float.set_status("正在启动...", "running")

        # 主窗口最小化（不隐藏，让 monitor 能切回来）
        self.showMinimized()

        # 启动监控线程
        self.monitor_thread = MonitorThread(self.config_manager)
        self.monitor_thread.log_message.connect(self.log_view.append_log)
        self.monitor_thread.status_changed.connect(self._on_status_changed)
        self.monitor_thread.monitor_finished.connect(self._on_monitor_finished)
        self.monitor_thread.start()
        self._update_button_state()
        self._set_run_status("running")
        logging.getLogger("wechat.gui").info("点击启动检测，主窗口已最小化，监控线程已启动")

    def _create_mini_float(self) -> None:
        """创建或重置迷你悬浮组件。"""
        if self.mini_float is not None:
            self.mini_float.close()
            self.mini_float.deleteLater()
        self.mini_float = MiniFloatWidget()
        self.mini_float.return_to_main.connect(self._on_return_to_main)
        self.mini_float.stop_monitor.connect(self.on_stop)
        self.mini_float.show_at_top_right()

    def _on_minimize_to_float(self) -> None:
        """从主界面缩小为悬浮组件（检测运行时）。"""
        if not self._is_running():
            return
        self._create_mini_float()
        self.mini_float.set_status("监听中", "active")
        self.showMinimized()

    def _on_return_to_main(self) -> None:
        """从悬浮组件返回主界面。"""
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def on_stop(self) -> None:
        """停止检测。"""
        if not self._is_running():
            return
        logging.getLogger("wechat.gui").info("点击停止检测，正在停止监控线程...")
        self.monitor_thread.stop_monitor()
        QTimer.singleShot(0, self._wait_thread_quit)

    def _wait_thread_quit(self) -> None:
        """非阻塞等待线程退出。"""
        if self.monitor_thread is None:
            return
        if not self.monitor_thread.isRunning():
            self._on_monitor_finished()
            return
        if not hasattr(self, "_wait_count"):
            self._wait_count = 0
        self._wait_count += 1
        if self._wait_count > 30:
            self._wait_count = 0
            logging.getLogger("wechat.gui").warning(
                "停止超时：监控线程可能正卡在微信操作上，将在当前操作完成后退出"
            )
            return
        QTimer.singleShot(100, self._wait_thread_quit)

    def _check_wx_connected(self) -> bool:
        """检测微信是否已运行并登录（不打开/激活微信窗口）。

        用 ctypes 直接调 FindWindowW，避免 win32gui 包装层异常。
        兼容多个微信版本的窗口类名。
        """
        try:
            import ctypes
            user32 = ctypes.windll.user32
            # 微信 PC 版不同版本的主窗口类名
            # WeChatMainWndForPC: 3.x 经典版
            # WeixinMainWndForPC: 4.x 新版（2024+ 改名）
            class_names = ["WeChatMainWndForPC", "WeixinMainWndForPC"]
            for cls in class_names:
                hwnd = user32.FindWindowW(cls, None)
                if hwnd:
                    return True
            return False
        except Exception as e:
            logging.getLogger("wechat.gui").warning(f"微信连接检测失败：{e}")
            return False

    def _verify_listener_name(self, name: str) -> tuple:
        """验证监听对象名称是否存在于微信会话列表。"""
        if self.monitor_thread and self.monitor_thread.monitor:
            svc = self.monitor_thread.monitor.service
            if svc.connected:
                sessions = svc.get_session_names()
                if name in sessions:
                    return (True, f"名称「{name}」在微信会话列表中存在")
                return (False, f"名称「{name}」不在会话列表中。会话列表共 {len(sessions)} 项，请检查名称是否完全一致（含空格、特殊字符）")

        try:
            from core.wx_service_uia import UiaWxService
            svc = UiaWxService()
            if not svc.connect():
                return (False, "无法连接微信，请确认微信已登录并处于前台")
            sessions = svc.get_session_names()
            svc.disconnect()
            if name in sessions:
                return (True, f"名称「{name}」在微信会话列表中存在")
            return (False, f"名称「{name}」不在会话列表中。会话列表共 {len(sessions)} 项，请检查名称是否完全一致")
        except Exception as e:
            return (False, f"连接微信失败：{e}")

    # ------------------------------------------------------------------
    # 信号槽
    # ------------------------------------------------------------------
    def _on_status_changed(self, kind: str, value: str) -> None:
        """监控状态变化。"""
        if kind == "wechat":
            self._set_wx_status(value)
        elif kind == "run":
            self._set_run_status(value)
        elif kind == "stage":
            # 同步到仪表盘阶段卡片
            if "监听" in value and "添加" not in value:
                state = "active"
            elif "错误" in value or "失败" in value:
                state = "error"
            else:
                state = "running"
            self.dashboard_view.update_stage(value, state)
            # 同步到悬浮组件
            if self.mini_float is not None:
                self.mini_float.set_status(value, state)
        elif kind == "alert":
            QMessageBox.warning(self, "提示", value)
            if self.mini_float is not None:
                self.mini_float.set_status("发生错误，请返回主界面查看", "error")
        elif kind == "started":
            if self.mini_float is not None:
                self.mini_float.set_status("监听中", "active")

    def _on_monitor_finished(self) -> None:
        """监控线程结束。"""
        self._set_run_status("stopped")
        self._set_wx_status("disconnected")
        self.dashboard_view.update_stage("就绪", "idle")
        self._update_button_state()
        if hasattr(self, "_wait_count"):
            self._wait_count = 0
        if self.mini_float is not None:
            self.mini_float.close()
            self.mini_float.deleteLater()
            self.mini_float = None
        self.showNormal()
        self.activateWindow()
        self.raise_()

    # ------------------------------------------------------------------
    # 托盘
    # ------------------------------------------------------------------
    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _quit_from_tray(self) -> None:
        self._really_quit = True
        self.close()

    # ------------------------------------------------------------------
    # 关闭事件
    # ------------------------------------------------------------------
    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        if self._really_quit:
            if self._is_running():
                self.monitor_thread.stop_monitor()
                self.monitor_thread.wait(3000)
            if self.mini_float is not None:
                self.mini_float.close()
                self.mini_float = None
            self.tray.hide()
            event.accept()
            return

        settings = QSettings("wxAutoTool", "wxAutoTool_reply")
        close_action = settings.value("closeAction", "")

        if close_action == "tray":
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "微信自动回复助手",
                "程序已最小化到托盘，双击图标恢复。",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
            return
        elif close_action == "quit":
            self._really_quit = True
            if self._is_running():
                self.monitor_thread.stop_monitor()
                self.monitor_thread.wait(3000)
            self.tray.hide()
            event.accept()
            return

        # 首次关闭：弹窗询问
        msg = QMessageBox(self)
        msg.setWindowTitle("关闭确认")
        msg.setText("您选择了关闭窗口，请选择后续行为：")
        tray_btn = msg.addButton("最小化到托盘", QMessageBox.ButtonRole.AcceptRole)
        quit_btn = msg.addButton("退出程序", QMessageBox.ButtonRole.RejectRole)
        cancel_btn = msg.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        remember_check = QCheckBox("记住选择（不再询问）")
        msg.setCheckBox(remember_check)
        msg.exec()
        clicked = msg.clickedButton()

        if clicked is tray_btn:
            if remember_check.isChecked():
                settings.setValue("closeAction", "tray")
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "微信自动回复助手",
                "程序已最小化到托盘，双击图标恢复。",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
        elif clicked is quit_btn:
            if remember_check.isChecked():
                settings.setValue("closeAction", "quit")
            self._really_quit = True
            if self._is_running():
                self.monitor_thread.stop_monitor()
                self.monitor_thread.wait(3000)
            self.tray.hide()
            event.accept()
        else:
            event.ignore()


def run() -> None:
    """GUI 启动入口（供 main.py 调用）。"""
    setup_logging()
    log = logging.getLogger("wechat.gui")
    log.info("GUI 启动中...")

    argv = sys.argv if sys.argv else ["wechat-monitor"]
    app = QApplication.instance() or QApplication(argv)
    log.info(f"QApplication 已创建，argv={argv}")

    try:
        window = MainWindow()
        window.show()
        log.info("主窗口已显示，进入事件循环")
    except Exception as e:
        log.error(f"主窗口初始化失败：{e}", exc_info=True)
        raise

    exit_code = app.exec()
    log.info(f"事件循环退出，code={exit_code}")
    sys.exit(exit_code)
