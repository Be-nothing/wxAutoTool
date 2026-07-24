# -*- coding: utf-8 -*-
"""主窗口：状态区 + 实时日志 + 操作按钮 + 系统托盘 + 配置对话框。"""

import logging
import os
import sys
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.config import ConfigManager, DEFAULT_CONFIG_PATH
from core.logger import setup_logging
from core.paths import icon_path, qss_path
from gui.widgets import LogTextEdit, MonitorThread


def _load_icon() -> QIcon:
    """加载图标，文件不存在时返回空图标（不报错）。"""
    p = icon_path()
    if os.path.exists(p):
        return QIcon(p)
    return QIcon()


class ListenerEditDialog(QDialog):
    """监听对象编辑对话框：设置类型与名称。"""

    def __init__(self, listener: Optional[dict] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("监听对象")
        self.setMinimumWidth(320)

        layout = QFormLayout(self)
        self.type_combo = QComboBox()
        self.type_combo.addItem("群聊", "group")
        self.type_combo.addItem("私聊", "friend")
        layout.addRow("类型：", self.type_combo)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("与微信中显示的名称完全一致")
        layout.addRow("名称：", self.name_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        if listener:
            ltype = listener.get("type", "friend")
            idx = self.type_combo.findData(ltype)
            self.type_combo.setCurrentIndex(idx if idx >= 0 else 1)
            self.name_edit.setText(listener.get("name", ""))

    def values(self) -> dict:
        return {
            "type": self.type_combo.currentData(),
            "name": self.name_edit.text().strip(),
            "rules": [],
        }


class ConfigDialog(QDialog):
    """配置设置对话框：表单式编辑，全程鼠标操作，自动生成 YAML 落盘。

    左侧监听对象列表（增删改），右侧选中对象的规则表格（增删改）。
    规则三列：发送人 / 关键词 / 回复内容，均可直接在表格内编辑。
    """

    # 规则表格列索引
    COL_SENDER = 0
    COL_KEYWORD = 1
    COL_REPLY = 2

    def __init__(self, config_manager: ConfigManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.config_manager = config_manager
        # 工作副本：编辑期间不直接改原配置，确定保存时才写回
        self._listeners: list = [
            {
                "type": l.get("type", "friend"),
                "name": l.get("name", ""),
                "rules": [dict(r) for r in l.get("rules", [])],
            }
            for l in config_manager.config.get("listeners", [])
        ]

        self.setWindowTitle("配置设置")
        self.resize(720, 520)
        self._build_ui()
        self._load_values()
        # 初始无选中，规则表置空
        self._refresh_listener_list()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # === 基本设置 ===
        basic_group = QGroupBox("基本设置")
        basic_form = QFormLayout(basic_group)

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 3600)
        self.interval_spin.setSuffix(" 秒")
        self.interval_spin.setToolTip("多久检查一次新消息。监听对象越多，单次检测越慢")
        basic_form.addRow("轮询间隔：", self.interval_spin)

        self.send_interval_spin = QDoubleSpinBox()
        self.send_interval_spin.setRange(0.1, 3600.0)
        self.send_interval_spin.setSingleStep(0.5)
        self.send_interval_spin.setSuffix(" 秒")
        basic_form.addRow("发送间隔：", self.send_interval_spin)

        self.auto_reply_check = QCheckBox("启用自动回复（关闭则仅记录日志）")
        basic_form.addRow(self.auto_reply_check)

        self.ignore_self_check = QCheckBox("忽略自己发送的消息")
        basic_form.addRow(self.ignore_self_check)

        self.ignore_system_check = QCheckBox("忽略系统消息")
        basic_form.addRow(self.ignore_system_check)

        layout.addWidget(basic_group)

        # === 监听对象 + 规则 ===
        listen_group = QGroupBox("监听对象与回复规则")
        listen_layout = QHBoxLayout(listen_group)

        # 左侧：监听对象列表
        left = QVBoxLayout()
        left.addWidget(QLabel("监听对象（群聊/私聊）"))
        self.listener_list = QListWidget()
        self.listener_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.listener_list.currentRowChanged.connect(self._on_listener_selected)
        left.addWidget(self.listener_list, 1)

        listener_btns = QHBoxLayout()
        btn_add = QPushButton("添加")
        btn_edit = QPushButton("编辑")
        btn_del = QPushButton("删除")
        btn_add.clicked.connect(self._on_add_listener)
        btn_edit.clicked.connect(self._on_edit_listener)
        btn_del.clicked.connect(self._on_del_listener)
        listener_btns.addWidget(btn_add)
        listener_btns.addWidget(btn_edit)
        listener_btns.addWidget(btn_del)
        left.addLayout(listener_btns)
        listen_layout.addLayout(left, 1)

        # 右侧：规则表格
        right = QVBoxLayout()
        right.addWidget(QLabel("回复规则（双击单元格编辑）"))
        self.rules_table = QTableWidget(0, 3)
        self.rules_table.setHorizontalHeaderLabels(["发送人", "关键词", "回复内容"])
        self.rules_table.horizontalHeader().setStretchLastSection(True)
        self.rules_table.horizontalHeader().setSectionResizeMode(
            self.COL_SENDER, QHeaderView.ResizeMode.Interactive
        )
        self.rules_table.horizontalHeader().setSectionResizeMode(
            self.COL_KEYWORD, QHeaderView.ResizeMode.Interactive
        )
        self.rules_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.rules_table.itemChanged.connect(self._on_rule_item_changed)
        right.addWidget(self.rules_table, 1)

        rule_btns = QHBoxLayout()
        btn_rule_add = QPushButton("添加规则")
        btn_rule_del = QPushButton("删除规则")
        btn_rule_add.clicked.connect(self._on_add_rule)
        btn_rule_del.clicked.connect(self._on_del_rule)
        rule_btns.addWidget(btn_rule_add)
        rule_btns.addWidget(btn_rule_del)
        rule_btns.addStretch()
        right.addLayout(rule_btns)
        listen_layout.addLayout(right, 2)

        layout.addWidget(listen_group, 1)

        # === 提示 ===
        tip = QLabel(
            "提示：发送人留空=不限发送人；关键词留空=匹配任意内容；"
            "监听对象越多，消息检测越慢（wxauto 基于 UI 自动化）。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(tip)

        # === 按钮 ===
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_values(self) -> None:
        cfg = self.config_manager.config
        monitor_cfg = cfg.get("monitor", {}) or {}
        action_cfg = cfg.get("action", {}) or {}
        self.interval_spin.setValue(int(monitor_cfg.get("interval", 2)))
        self.send_interval_spin.setValue(float(cfg.get("send_interval", 3)))
        self.auto_reply_check.setChecked(bool(action_cfg.get("auto_reply", False)))
        self.ignore_self_check.setChecked(bool(cfg.get("ignore_self", True)))
        self.ignore_system_check.setChecked(bool(cfg.get("ignore_system", True)))

    # ------------------------------------------------------------------
    # 监听对象列表
    # ------------------------------------------------------------------
    def _refresh_listener_list(self) -> None:
        """刷新左侧监听对象列表显示。"""
        self.listener_list.blockSignals(True)
        self.listener_list.clear()
        for l in self._listeners:
            tag = "群" if l.get("type") == "group" else "私"
            name = l.get("name", "")
            item = QListWidgetItem(f"[{tag}] {name}")
            item.setData(Qt.UserRole, l)
            self.listener_list.addItem(item)
        self.listener_list.blockSignals(False)
        # 默认选第一个
        if self.listener_list.count() > 0:
            self.listener_list.setCurrentRow(0)
        else:
            self._load_rules_into_table(None)

    def _current_listener(self) -> Optional[dict]:
        """获取当前选中的监听对象（工作副本引用，可直接修改）。"""
        row = self.listener_list.currentRow()
        if 0 <= row < len(self._listeners):
            return self._listeners[row]
        return None

    def _on_listener_selected(self, row: int) -> None:
        """选中监听对象时，右侧加载其规则。"""
        if 0 <= row < len(self._listeners):
            self._load_rules_into_table(self._listeners[row])
        else:
            self._load_rules_into_table(None)

    def _on_add_listener(self) -> None:
        dlg = ListenerEditDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        v = dlg.values()
        if not v["name"]:
            QMessageBox.warning(self, "提示", "名称不能为空")
            return
        self._listeners.append(v)
        self._refresh_listener_list()
        self.listener_list.setCurrentRow(self.listener_list.count() - 1)

    def _on_edit_listener(self) -> None:
        cur = self._current_listener()
        if cur is None:
            return
        dlg = ListenerEditDialog(cur, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        v = dlg.values()
        if not v["name"]:
            QMessageBox.warning(self, "提示", "名称不能为空")
            return
        # 保留原 rules
        v["rules"] = cur.get("rules", [])
        idx = self.listener_list.currentRow()
        self._listeners[idx] = v
        self._refresh_listener_list()
        self.listener_list.setCurrentRow(idx)

    def _on_del_listener(self) -> None:
        idx = self.listener_list.currentRow()
        if idx < 0:
            return
        name = self._listeners[idx].get("name", "")
        if QMessageBox.question(
            self, "确认删除", f"确定删除监听对象「{name}」及其所有规则？"
        ) != QMessageBox.StandardButton.Yes:
            return
        self._listeners.pop(idx)
        self._refresh_listener_list()

    # ------------------------------------------------------------------
    # 规则表格
    # ------------------------------------------------------------------
    def _load_rules_into_table(self, listener: Optional[dict]) -> None:
        """将指定监听对象的规则载入右侧表格。"""
        self.rules_table.itemChanged.disconnect(self._on_rule_item_changed)
        self.rules_table.setRowCount(0)
        if listener is None:
            self.rules_table.setEnabled(False)
            return
        self.rules_table.setEnabled(True)
        rules = listener.get("rules", [])
        self.rules_table.setRowCount(len(rules))
        for i, r in enumerate(rules):
            self.rules_table.setItem(i, self.COL_SENDER, QTableWidgetItem(r.get("sender", "")))
            self.rules_table.setItem(i, self.COL_KEYWORD, QTableWidgetItem(r.get("keyword", "")))
            self.rules_table.setItem(i, self.COL_REPLY, QTableWidgetItem(r.get("reply", "")))
        self.rules_table.itemChanged.connect(self._on_rule_item_changed)

    def _on_rule_item_changed(self, item: QTableWidgetItem) -> None:
        """表格单元格编辑后，同步回当前监听对象的规则。"""
        cur = self._current_listener()
        if cur is None:
            return
        rules = cur.setdefault("rules", [])
        row = item.row()
        # 行数可能不足，补齐
        while len(rules) <= row:
            rules.append({"sender": "", "keyword": "", "reply": ""})
        col = item.column()
        key = {self.COL_SENDER: "sender", self.COL_KEYWORD: "keyword", self.COL_REPLY: "reply"}[col]
        rules[row][key] = item.text()

    def _on_add_rule(self) -> None:
        cur = self._current_listener()
        if cur is None:
            QMessageBox.information(self, "提示", "请先在左侧选择一个监听对象")
            return
        rules = cur.setdefault("rules", [])
        rules.append({"sender": "", "keyword": "", "reply": ""})
        # 刷新表格（断开信号避免触发同步）
        self._load_rules_into_table(cur)
        # 选中并聚焦新行
        self.rules_table.selectRow(self.rules_table.rowCount() - 1)
        self.rules_table.editItem(self.rules_table.item(self.rules_table.rowCount() - 1, self.COL_SENDER))

    def _on_del_rule(self) -> None:
        cur = self._current_listener()
        if cur is None:
            return
        rules = cur.get("rules", [])
        rows = sorted({i.row() for i in self.rules_table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        for r in rows:
            if 0 <= r < len(rules):
                rules.pop(r)
        self._load_rules_into_table(cur)

    # ------------------------------------------------------------------
    # 保存
    # ------------------------------------------------------------------
    def _on_accept(self) -> None:
        """校验并保存配置。"""
        # 同步当前表格编辑（失焦未触发的改动）
        cur = self._current_listener()
        if cur is not None:
            rules = cur.setdefault("rules", [])
            for row in range(self.rules_table.rowCount()):
                while len(rules) <= row:
                    rules.append({"sender": "", "keyword": "", "reply": ""})
                rules[row]["sender"] = self.rules_table.item(row, self.COL_SENDER).text() if self.rules_table.item(row, self.COL_SENDER) else ""
                rules[row]["keyword"] = self.rules_table.item(row, self.COL_KEYWORD).text() if self.rules_table.item(row, self.COL_KEYWORD) else ""
                rules[row]["reply"] = self.rules_table.item(row, self.COL_REPLY).text() if self.rules_table.item(row, self.COL_REPLY) else ""

        # 写入配置并落盘
        cfg = self.config_manager.config
        cfg.setdefault("monitor", {})["interval"] = self.interval_spin.value()
        cfg.setdefault("action", {})["auto_reply"] = self.auto_reply_check.isChecked()
        cfg["send_interval"] = self.send_interval_spin.value()
        cfg["ignore_self"] = self.ignore_self_check.isChecked()
        cfg["ignore_system"] = self.ignore_system_check.isChecked()
        cfg["listeners"] = self._listeners
        try:
            self.config_manager.save()
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"配置保存失败：\n{e}")
            return
        self.accept()


class MainWindow(QMainWindow):
    """主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self.config_manager = ConfigManager()
        self.monitor_thread: Optional[MonitorThread] = None
        self._really_quit = False  # 托盘"退出"才真正退出，否则隐藏到托盘

        self._build_ui()
        self._build_tray()
        self._apply_style()
        self._update_button_state()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.setWindowTitle("微信自动检测助手")
        self.setWindowIcon(_load_icon())
        self.resize(720, 560)
        self.setMinimumSize(560, 420)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # === 顶部：标题 + 状态区 ===
        title = QLabel("微信自动检测助手")
        title.setObjectName("titleLabel")
        root.addWidget(title)

        status_box = QHBoxLayout()
        status_box.setSpacing(24)
        self.wx_status_label = QLabel("微信状态：未连接")
        self.wx_status_label.setObjectName("wxDisconnected")
        self.run_status_label = QLabel("运行状态：已停止")
        self.run_status_label.setObjectName("runStopped")
        status_box.addWidget(self.wx_status_label)
        status_box.addWidget(self.run_status_label)
        status_box.addStretch()
        root.addLayout(status_box)

        # === 中间：日志窗口 ===
        self.log_view = LogTextEdit()
        root.addWidget(self.log_view, 1)

        # === 底部：按钮 ===
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)
        self.start_btn = QPushButton("启动检测")
        self.stop_btn = QPushButton("停止检测")
        self.config_btn = QPushButton("配置设置")
        self.start_btn.setObjectName("startBtn")
        self.stop_btn.setObjectName("stopBtn")
        self.start_btn.setMinimumWidth(110)
        self.stop_btn.setMinimumWidth(110)
        self.config_btn.setMinimumWidth(110)
        self.start_btn.clicked.connect(self.on_start)
        self.stop_btn.clicked.connect(self.on_stop)
        self.config_btn.clicked.connect(self.on_config)
        btn_box.addStretch()
        btn_box.addWidget(self.start_btn)
        btn_box.addWidget(self.stop_btn)
        btn_box.addWidget(self.config_btn)
        root.addLayout(btn_box)

    def _build_tray(self) -> None:
        """系统托盘：图标 + 右键菜单 + 双击显示。"""
        from PySide6.QtWidgets import QSystemTrayIcon

        self.tray = QSystemTrayIcon(_load_icon(), self)
        self.tray.setToolTip("微信自动检测助手")
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
        """加载 QSS 样式。"""
        p = qss_path()
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    # ------------------------------------------------------------------
    # 状态更新
    # ------------------------------------------------------------------
    def _update_button_state(self) -> None:
        running = self.monitor_thread is not None and self.monitor_thread.isRunning()
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)

    def _set_wx_status(self, value: str) -> None:
        if value == "connected":
            self.wx_status_label.setText("微信状态：已连接")
            self.wx_status_label.setObjectName("wxConnected")
        else:
            self.wx_status_label.setText("微信状态：未连接")
            self.wx_status_label.setObjectName("wxDisconnected")
        # 强制重绘以应用 ObjectName 对应样式
        self.wx_status_label.style().unpolish(self.wx_status_label)
        self.wx_status_label.style().polish(self.wx_status_label)

    def _set_run_status(self, value: str) -> None:
        if value == "running":
            self.run_status_label.setText("运行状态：运行中")
            self.run_status_label.setObjectName("runRunning")
        else:
            self.run_status_label.setText("运行状态：已停止")
            self.run_status_label.setObjectName("runStopped")
        self.run_status_label.style().unpolish(self.run_status_label)
        self.run_status_label.style().polish(self.run_status_label)

    # ------------------------------------------------------------------
    # 按钮槽
    # ------------------------------------------------------------------
    def on_start(self) -> None:
        """启动检测。"""
        if self.monitor_thread is not None and self.monitor_thread.isRunning():
            return
        # 启动前重新加载配置，确保改动生效
        self.config_manager.load()
        self.monitor_thread = MonitorThread(self.config_manager)
        self.monitor_thread.log_message.connect(self.log_view.append_log)
        self.monitor_thread.status_changed.connect(self._on_status_changed)
        self.monitor_thread.monitor_finished.connect(self._on_monitor_finished)
        self.monitor_thread.start()
        self._update_button_state()
        self._set_run_status("running")
        logging.getLogger("wechat.gui").info("点击启动检测，监控线程已启动")

    def on_stop(self) -> None:
        """停止检测。"""
        if self.monitor_thread is None or not self.monitor_thread.isRunning():
            return
        logging.getLogger("wechat.gui").info("点击停止检测，正在停止监控线程...")
        self.monitor_thread.stop_monitor()
        # 等待线程退出（最多 3 秒），避免卡 UI
        QTimer.singleShot(0, self._wait_thread_quit)

    def _wait_thread_quit(self) -> None:
        """非阻塞等待线程退出。"""
        if self.monitor_thread is None:
            return
        if not self.monitor_thread.isRunning():
            self._on_monitor_finished()
            return
        # 仍在运行则稍后重试（最多累计约 3 秒）
        if not hasattr(self, "_wait_count"):
            self._wait_count = 0
        self._wait_count += 1
        if self._wait_count > 30:
            # 超时：可能卡在 wxauto UI 调用，提示用户
            self._wait_count = 0
            logging.getLogger("wechat.gui").warning(
                "停止超时：监控线程可能正卡在微信操作上，将在当前操作完成后退出"
            )
            return
        QTimer.singleShot(100, self._wait_thread_quit)

    def on_config(self) -> None:
        """打开配置设置对话框。"""
        running = self.monitor_thread is not None and self.monitor_thread.isRunning()
        if running:
            QMessageBox.information(
                self, "提示", "检测正在运行，修改配置需停止后重新启动才会生效。"
            )
        dlg = ConfigDialog(self.config_manager, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.config_manager.load()  # 重新加载到内存
            logging.getLogger("wechat.gui").info("配置已保存并重新加载")

    # ------------------------------------------------------------------
    # 信号槽
    # ------------------------------------------------------------------
    def _on_status_changed(self, kind: str, value: str) -> None:
        """监控状态变化。"""
        if kind == "wechat":
            self._set_wx_status(value)
        elif kind == "run":
            self._set_run_status(value)

    def _on_monitor_finished(self) -> None:
        """监控线程结束。"""
        self._set_run_status("stopped")
        self._set_wx_status("disconnected")
        self._update_button_state()
        if hasattr(self, "_wait_count"):
            self._wait_count = 0

    # ------------------------------------------------------------------
    # 托盘
    # ------------------------------------------------------------------
    def _on_tray_activated(self, reason) -> None:
        from PySide6.QtWidgets import QSystemTrayIcon

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
    # 关闭事件：隐藏到托盘
    # ------------------------------------------------------------------
    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        if not self._really_quit:
            # 隐藏到托盘
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "微信自动检测助手",
                "程序已最小化到托盘，双击图标恢复。",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
            return
        # 真正退出：先停止监控线程
        if self.monitor_thread is not None and self.monitor_thread.isRunning():
            self.monitor_thread.stop_monitor()
            self.monitor_thread.wait(3000)
        self.tray.hide()
        event.accept()


def run() -> None:
    """GUI 启动入口（供 main.py 调用）。"""
    from PySide6.QtWidgets import QApplication

    # 初始化日志系统（文件 + 控制台 + GUI 回调桥接）
    # 提前初始化，便于记录启动过程
    setup_logging()
    log = logging.getLogger("wechat.gui")
    log.info("GUI 启动中...")

    # 确保 sys.argv 可用（打包环境某些情况下可能为空）
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

    # 事件循环：app.exec() 阻塞至窗口关闭
    exit_code = app.exec()
    log.info(f"事件循环退出，code={exit_code}")
    sys.exit(exit_code)
