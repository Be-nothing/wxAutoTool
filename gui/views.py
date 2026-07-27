# -*- coding: utf-8 -*-
"""工作区视图：仪表盘 / 监听对象 / 日志 / 设置。

每个视图是独立 QWidget，由 MainWindow 装入 QStackedWidget 切换显示。
视图只负责 UI 与编辑态，落盘通过 ConfigManager 完成。
"""

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QPainter, QColor, QIcon, QPalette
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.config import ConfigManager
from core.version import VERSION
from gui.widgets import LogTextEdit


# ======================================================================
# SVG 图标（Lucide 风格，stroke=currentColor 便于运行时染色）
# ======================================================================
_SVG_DASHBOARD = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/></svg>'
_SVG_MESSAGE = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>'
_SVG_FILE = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><line x1="10" y1="9" x2="8" y2="9"/></svg>'
_SVG_SETTINGS = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>'
_SVG_LAYERS = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>'
_SVG_PLAY = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="6 3 20 12 6 21 6 3"/></svg>'
_SVG_STOP = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor" stroke="none"><rect x="5" y="5" width="14" height="14" rx="1"/></svg>'


def _svg_to_pixmap(svg: str, color: str, size: int = 22) -> QPixmap:
    """SVG 字符串 → 指定颜色的 QPixmap（运行时染色）。

    SVG 中 stroke/fill="currentColor" 会被替换为传入的 color。
    使用 QSvgRenderer 渲染，抗锯齿。
    """
    renderer = QSvgRenderer(svg.replace("currentColor", color).encode("utf-8"))
    if not renderer.isValid():
        return QPixmap()
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    return pix


def _make_icon(svg: str, color: str, size: int = 22) -> QIcon:
    """SVG → 指定颜色的 QIcon。"""
    return QIcon(_svg_to_pixmap(svg, color, size))


# ======================================================================
# 导航按钮
# ======================================================================
class NavButton(QToolButton):
    """导航栏按钮：SVG 图标在上，文字在下，checkable 互斥。

    选中时图标变白，未选中时灰色，hover 时浅色。
    """

    def __init__(self, svg: str, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._svg = svg
        self.setCheckable(True)
        self.setAutoRaise(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setText(text)
        self.setIconSize(QSize(22, 22))
        self.setFixedHeight(60)
        self.setMinimumWidth(68)
        self.toggled.connect(self._update_icon)
        self._update_icon()

    def _update_icon(self) -> None:
        """根据选中状态切换图标颜色（使用调色板适配浅色/深色主题）。"""
        if self.isChecked():
            color = "#ffffff"
        else:
            # 从调色板获取文字颜色（QSS 设置的 color 属性会同步到调色板）
            pal = self.palette()
            text_color = pal.color(QPalette.ColorRole.WindowText)
            if not text_color.isValid() or text_color.lightness() < 50:
                color = "#8f959e"  # 兜底
            else:
                color = text_color.name()
        self.setIcon(_make_icon(self._svg, color))

    def enterEvent(self, event) -> None:  # type: ignore[override]
        super().enterEvent(event)
        if not self.isChecked():
            self._update_icon()

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        super().leaveEvent(event)
        if not self.isChecked():
            self._update_icon()


# ======================================================================
# 仪表盘视图
# ======================================================================
class DashboardView(QWidget):
    """仪表盘：状态卡片 + 主操作按钮 + 快速概览。"""

    start_requested = Signal()
    stop_requested = Signal()
    nav_to_listeners = Signal()  # 跳转到监听对象视图

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(20)

        # 欢迎语
        header = QHBoxLayout()
        header_left = QVBoxLayout()
        header_left.setSpacing(4)
        hello = QLabel("微信自动回复助手")
        hello.setObjectName("dashboardTitle")
        header_left.addWidget(hello)
        sub = QLabel(f"v{VERSION} · 基于 UIA 增量拉取，响应快、开销低")
        sub.setObjectName("dashboardSub")
        header_left.addWidget(sub)
        header.addLayout(header_left)
        header.addStretch()
        # logo 图标
        logo_lbl = QLabel()
        logo_lbl.setPixmap(_svg_to_pixmap(_SVG_LAYERS, "#3370ff", 32))
        logo_lbl.setFixedSize(36, 36)
        header.addWidget(logo_lbl)
        root.addLayout(header)

        # 状态卡片网格（2x2）
        cards = QGridLayout()
        cards.setSpacing(14)
        self.card_wx = self._make_card("微信状态", "未连接", "#8f959e")
        self.card_run = self._make_card("运行状态", "已停止", "#8f959e")
        self.card_listen = self._make_card("监听对象", "0", "#3370ff")
        self.card_stage = self._make_card("当前阶段", "就绪", "#8f959e")
        cards.addWidget(self.card_wx, 0, 0)
        cards.addWidget(self.card_run, 0, 1)
        cards.addWidget(self.card_listen, 1, 0)
        cards.addWidget(self.card_stage, 1, 1)
        root.addLayout(cards)

        # 主操作按钮
        btn_box = QHBoxLayout()
        btn_box.setSpacing(12)
        self.start_btn = QPushButton("  启动检测")
        self.start_btn.setObjectName("primaryBtn")
        self.start_btn.setMinimumHeight(46)
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.setIcon(_make_icon(_SVG_PLAY, "#ffffff", 16))
        self.stop_btn = QPushButton("  停止检测")
        self.stop_btn.setObjectName("dangerBtn")
        self.stop_btn.setMinimumHeight(46)
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_btn.setIcon(_make_icon(_SVG_STOP, "#dc2626", 16))
        self.start_btn.clicked.connect(self.start_requested.emit)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        btn_box.addWidget(self.start_btn, 1)
        btn_box.addWidget(self.stop_btn, 1)
        root.addLayout(btn_box)

        root.addStretch()

        # 快速概览
        tip_box = QFrame()
        tip_box.setObjectName("tipBox")
        tip_layout = QVBoxLayout(tip_box)
        tip_layout.setContentsMargins(20, 16, 20, 16)
        tip_layout.setSpacing(8)
        tip_title = QLabel("快速开始")
        tip_title.setObjectName("tipTitle")
        tip_layout.addWidget(tip_title)
        tips = [
            "在「监听对象」视图添加要监听的群聊/私聊",
            "在「设置」视图调整轮询间隔与自动回复开关",
            "点击「启动检测」，主窗口会缩小为悬浮组件",
            "添加监听对象完成后自动切回主界面",
        ]
        for i, t in enumerate(tips, 1):
            lbl = QLabel(f"{i}.  {t}")
            lbl.setObjectName("tipItem")
            tip_layout.addWidget(lbl)

        goto_btn = QPushButton("去配置监听对象")
        goto_btn.setObjectName("linkBtn")
        goto_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        goto_btn.clicked.connect(self.nav_to_listeners.emit)
        tip_layout.addWidget(goto_btn)
        root.addWidget(tip_box)

    @staticmethod
    def _make_card(title: str, value: str, color: str) -> QFrame:
        """状态卡片：右上角状态点 + 标题 + 大号数值。"""
        card = QFrame()
        card.setObjectName("statusCard")
        v_layout = QVBoxLayout(card)
        v_layout.setContentsMargins(20, 16, 20, 16)
        v_layout.setSpacing(8)

        # 标题行：标题 + 右侧状态点
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        t = QLabel(title)
        t.setObjectName("cardTitle")
        top_row.addWidget(t)
        top_row.addStretch()
        dot = QLabel("●")
        dot.setObjectName("cardDot")
        dot.setStyleSheet(f"color: {color}; font-size: 10px;")
        dot.setFixedWidth(10)
        top_row.addWidget(dot)
        v_layout.addLayout(top_row)

        # 数值
        val = QLabel(value)
        val.setObjectName("cardValue")
        val.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: 600;")
        v_layout.addWidget(val)
        return card

    def _set_card_state(self, card: QFrame, text: str, color: str) -> None:
        v = card.findChild(QLabel, "cardValue")
        dot = card.findChild(QLabel, "cardDot")
        if v:
            v.setText(text)
            v.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: 600;")
        if dot:
            dot.setStyleSheet(f"color: {color}; font-size: 10px;")

    def update_wx_status(self, connected: bool) -> None:
        if connected:
            self._set_card_state(self.card_wx, "已连接", "#16a34a")
        else:
            self._set_card_state(self.card_wx, "未连接", "#8f959e")

    def update_run_status(self, running: bool) -> None:
        if running:
            self._set_card_state(self.card_run, "运行中", "#3370ff")
        else:
            self._set_card_state(self.card_run, "已停止", "#8f959e")

    def update_listen_count(self, count: int) -> None:
        self._set_card_state(self.card_listen, str(count), "#3370ff")

    def update_stage(self, text: str, state: str = "idle") -> None:
        color_map = {
            "idle": "#8f959e",
            "running": "#f59e0b",
            "active": "#16a34a",
            "error": "#dc2626",
        }
        self._set_card_state(self.card_stage, text, color_map.get(state, "#8f959e"))


# ======================================================================
# 监听对象视图
# ======================================================================
class ListenersView(QWidget):
    """监听对象管理：左列表 + 右规则表格，内嵌视图（非对话框）。

    编辑期间维护工作副本 _listeners，点击「保存」写回 ConfigManager 落盘。
    """

    COL_SENDER = 0
    COL_KEYWORD = 1
    COL_REPLY = 2

    # 配置已保存（用于通知主窗口刷新计数）
    config_saved = Signal()

    def __init__(
        self,
        config_manager: ConfigManager,
        verify_callback=None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config_manager = config_manager
        self._verify_callback = verify_callback
        self._listeners: list = []
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        # 标题行
        header = QHBoxLayout()
        title = QLabel("监听对象")
        title.setObjectName("viewTitle")
        header.addWidget(title)
        header.addStretch()
        self.save_btn = QPushButton("保存")
        self.save_btn.setObjectName("primaryBtn")
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.clicked.connect(self._on_save)
        header.addWidget(self.save_btn)
        root.addLayout(header)

        # 主体：左列表 + 右规则
        body = QHBoxLayout()
        body.setSpacing(12)

        # 左侧：监听对象列表
        left = QVBoxLayout()
        left.setSpacing(6)
        left_label = QLabel("监听对象（群聊/私聊）")
        left_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        left.addWidget(left_label)
        self.listener_list = QListWidget()
        self.listener_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.listener_list.currentRowChanged.connect(self._on_listener_selected)
        left.addWidget(self.listener_list, 1)

        listener_btns = QHBoxLayout()
        btn_add = QPushButton("添加")
        btn_edit = QPushButton("编辑")
        btn_del = QPushButton("删除")
        btn_test = QPushButton("测试")
        btn_test.setToolTip("连接微信并验证该监听对象名称是否存在于会话列表")
        btn_add.clicked.connect(self._on_add_listener)
        btn_edit.clicked.connect(self._on_edit_listener)
        btn_del.clicked.connect(self._on_del_listener)
        btn_test.clicked.connect(self._on_test_listener)
        for b in (btn_add, btn_edit, btn_del, btn_test):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        listener_btns.addWidget(btn_add)
        listener_btns.addWidget(btn_edit)
        listener_btns.addWidget(btn_del)
        listener_btns.addWidget(btn_test)
        left.addLayout(listener_btns)
        body.addLayout(left, 1)

        # 右侧：规则表格
        right = QVBoxLayout()
        right.setSpacing(6)
        right_label = QLabel("回复规则（双击单元格编辑）")
        right_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        right.addWidget(right_label)
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
        btn_rule_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_rule_del.setCursor(Qt.CursorShape.PointingHandCursor)
        rule_btns.addWidget(btn_rule_add)
        rule_btns.addWidget(btn_rule_del)
        rule_btns.addStretch()
        right.addLayout(rule_btns)
        body.addLayout(right, 2)

        root.addLayout(body, 1)

        tip = QLabel(
            "提示：发送人留空=不限发送人（私聊自动匹配对方）；关键词留空=匹配任意内容。"
            "监听对象越多，消息检测越慢。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #888; font-size: 12px;")
        root.addWidget(tip)

    def reload(self) -> None:
        """从 ConfigManager 重新加载工作副本。"""
        self._listeners = [
            {
                "type": l.get("type", "friend"),
                "name": l.get("name", ""),
                "rules": [dict(r) for r in l.get("rules", [])],
            }
            for l in self.config_manager.config.get("listeners", [])
        ]
        self._refresh_listener_list()

    def _refresh_listener_list(self) -> None:
        self.listener_list.blockSignals(True)
        self.listener_list.clear()
        for l in self._listeners:
            tag = "群" if l.get("type") == "group" else "私"
            name = l.get("name", "")
            item = QListWidgetItem(f"[{tag}] {name}")
            item.setData(Qt.UserRole, l)
            self.listener_list.addItem(item)
        self.listener_list.blockSignals(False)
        if self.listener_list.count() > 0:
            self.listener_list.setCurrentRow(0)
        else:
            self._load_rules_into_table(None)

    def _current_listener(self) -> Optional[dict]:
        row = self.listener_list.currentRow()
        if 0 <= row < len(self._listeners):
            return self._listeners[row]
        return None

    def _on_listener_selected(self, row: int) -> None:
        if 0 <= row < len(self._listeners):
            self._load_rules_into_table(self._listeners[row])
        else:
            self._load_rules_into_table(None)

    def _on_add_listener(self) -> None:
        dlg = ListenerEditDialog(parent=self, verify_callback=self._verify_callback)
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
        dlg = ListenerEditDialog(cur, self, verify_callback=self._verify_callback)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        v = dlg.values()
        if not v["name"]:
            QMessageBox.warning(self, "提示", "名称不能为空")
            return
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

    def _on_test_listener(self) -> None:
        """测试当前选中的监听对象名称是否存在于微信会话列表。"""
        cur = self._current_listener()
        if cur is None:
            QMessageBox.information(self, "提示", "请先在左侧选择一个监听对象")
            return
        name = cur.get("name", "")
        if not name:
            QMessageBox.warning(self, "提示", "该监听对象名称为空，无法测试")
            return
        if self._verify_callback is None:
            QMessageBox.warning(self, "提示", "验证回调未注册，无法测试")
            return
        QMessageBox.information(
            self, "测试中",
            f"即将连接微信验证「{name}」是否存在，请勿移动鼠标和键盘...",
        )
        try:
            result = self._verify_callback(name)
            if result[0]:
                QMessageBox.information(self, "测试成功", f"✓ {result[1]}")
            else:
                QMessageBox.warning(self, "测试失败", f"✗ {result[1]}")
        except Exception as e:
            QMessageBox.critical(self, "测试出错", f"测试失败：{e}")

    def _load_rules_into_table(self, listener: Optional[dict]) -> None:
        self.rules_table.itemChanged.disconnect(self._on_rule_item_changed)
        self.rules_table.setRowCount(0)
        if listener is None:
            self.rules_table.setEnabled(False)
            return
        self.rules_table.setEnabled(True)
        rules = listener.get("rules", [])
        is_friend = listener.get("type", "friend") == "friend"
        self.rules_table.setColumnHidden(self.COL_SENDER, is_friend)
        self.rules_table.setRowCount(len(rules))
        for i, r in enumerate(rules):
            self.rules_table.setItem(i, self.COL_SENDER, QTableWidgetItem(r.get("sender", "")))
            self.rules_table.setItem(i, self.COL_KEYWORD, QTableWidgetItem(r.get("keyword", "")))
            self.rules_table.setItem(i, self.COL_REPLY, QTableWidgetItem(r.get("reply", "")))
        self.rules_table.itemChanged.connect(self._on_rule_item_changed)

    def _on_rule_item_changed(self, item: QTableWidgetItem) -> None:
        cur = self._current_listener()
        if cur is None:
            return
        rules = cur.setdefault("rules", [])
        row = item.row()
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
        self._load_rules_into_table(cur)
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

    def _on_save(self) -> None:
        """同步表格编辑并写回配置。"""
        cur = self._current_listener()
        if cur is not None:
            rules = cur.setdefault("rules", [])
            for row in range(self.rules_table.rowCount()):
                while len(rules) <= row:
                    rules.append({"sender": "", "keyword": "", "reply": ""})
                rules[row]["sender"] = self.rules_table.item(row, self.COL_SENDER).text() if self.rules_table.item(row, self.COL_SENDER) else ""
                rules[row]["keyword"] = self.rules_table.item(row, self.COL_KEYWORD).text() if self.rules_table.item(row, self.COL_KEYWORD) else ""
                rules[row]["reply"] = self.rules_table.item(row, self.COL_REPLY).text() if self.rules_table.item(row, self.COL_REPLY) else ""

        cfg = self.config_manager.config
        cfg["listeners"] = self._listeners
        try:
            self.config_manager.save()
            QMessageBox.information(self, "保存成功", "监听对象配置已保存。")
            self.config_saved.emit()
            logging.getLogger("wechat.gui").info("监听对象配置已保存")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"配置保存失败：\n{e}")


# ======================================================================
# 监听对象编辑对话框
# ======================================================================
class ListenerEditDialog(QDialog):
    """监听对象编辑对话框：设置类型与名称，支持检测名称是否存在。"""

    def __init__(
        self,
        listener: Optional[dict] = None,
        parent: Optional[QWidget] = None,
        verify_callback=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("监听对象")
        self.setMinimumWidth(360)
        self._verify_callback = verify_callback

        layout = QFormLayout(self)
        self.type_combo = QComboBox()
        self.type_combo.addItem("群聊", "group")
        self.type_combo.addItem("私聊", "friend")
        layout.addRow("类型：", self.type_combo)

        name_row = QHBoxLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("与微信中显示的名称完全一致")
        self.check_btn = QPushButton("检测")
        self.check_btn.setToolTip("连接微信并验证该名称是否存在于会话列表")
        self.check_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.check_btn.clicked.connect(self._on_check_name)
        name_row.addWidget(self.name_edit, 1)
        name_row.addWidget(self.check_btn)
        layout.addRow("名称：", name_row)

        self.hint_label = QLabel("")
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("font-size: 12px;")
        layout.addRow("", self.hint_label)

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

        if self._verify_callback is None:
            self.check_btn.hide()

    def _on_check_name(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            self.hint_label.setStyleSheet("color: #cc0000; font-size: 12px;")
            self.hint_label.setText("请先输入名称")
            return
        if self._verify_callback is None:
            return

        self.check_btn.setEnabled(False)
        self.check_btn.setText("检测中...")
        self.hint_label.setText("正在连接微信获取会话列表...")
        self.hint_label.setStyleSheet("color: #888; font-size: 12px;")
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            result = self._verify_callback(name)
            if result[0]:
                self.hint_label.setStyleSheet("color: #107c10; font-size: 12px;")
                self.hint_label.setText(f"✓ {result[1]}")
            else:
                self.hint_label.setStyleSheet("color: #cc0000; font-size: 12px;")
                self.hint_label.setText(f"✗ {result[1]}")
        except Exception as e:
            self.hint_label.setStyleSheet("color: #cc0000; font-size: 12px;")
            self.hint_label.setText(f"检测失败：{e}")
        finally:
            self.check_btn.setEnabled(True)
            self.check_btn.setText("检测")

    def values(self) -> dict:
        return {
            "type": self.type_combo.currentData(),
            "name": self.name_edit.text().strip(),
            "rules": [],
        }


# ======================================================================
# 日志视图
# ======================================================================
class LogView(QWidget):
    """日志视图：LogTextEdit + 工具栏。"""

    def __init__(self, log_view: LogTextEdit, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._log_view = log_view
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("运行日志")
        title.setObjectName("viewTitle")
        header.addWidget(title)
        header.addStretch()

        self.clear_btn = QPushButton("清空日志")
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.clicked.connect(self._on_clear)
        header.addWidget(self.clear_btn)
        root.addLayout(header)

        root.addWidget(self._log_view, 1)

    def _on_clear(self) -> None:
        self._log_view.clear()


# ======================================================================
# 设置视图
# ======================================================================
class SettingsView(QWidget):
    """设置视图：全局配置表单。"""

    config_saved = Signal()

    def __init__(
        self,
        config_manager: ConfigManager,
        is_running_cb=None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config_manager = config_manager
        self._is_running_cb = is_running_cb
        self._build_ui()
        self._load_values()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("全局设置")
        title.setObjectName("viewTitle")
        header.addWidget(title)
        header.addStretch()
        self.save_btn = QPushButton("保存")
        self.save_btn.setObjectName("primaryBtn")
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.clicked.connect(self._on_save)
        header.addWidget(self.save_btn)
        root.addLayout(header)

        # 基本设置
        basic_group = QGroupBox("监控设置")
        basic_form = QFormLayout(basic_group)
        basic_form.setSpacing(10)

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 3600)
        self.interval_spin.setSuffix(" 秒")
        self.interval_spin.setToolTip("多久检查一次新消息。监听对象越多，单次检测越慢")
        basic_form.addRow("轮询间隔：", self.interval_spin)

        self.send_interval_spin = QDoubleSpinBox()
        self.send_interval_spin.setRange(0.1, 3600.0)
        self.send_interval_spin.setSingleStep(0.5)
        self.send_interval_spin.setSuffix(" 秒")
        self.send_interval_spin.setToolTip(
            "对同一聊天对象的两次回复间的最小间隔（按聊天对象独立计时，互不影响）。"
            "降低可加快响应，过低可能触发微信风控"
        )
        basic_form.addRow("发送间隔：", self.send_interval_spin)
        root.addWidget(basic_group)

        # 行为设置
        action_group = QGroupBox("行为设置")
        action_form = QFormLayout(action_group)
        action_form.setSpacing(10)

        self.auto_reply_check = QCheckBox("启用自动回复（关闭则仅记录日志）")
        action_form.addRow(self.auto_reply_check)

        self.ignore_self_check = QCheckBox("忽略自己发送的消息")
        action_form.addRow(self.ignore_self_check)

        self.ignore_system_check = QCheckBox("忽略系统消息")
        action_form.addRow(self.ignore_system_check)
        root.addWidget(action_group)

        # 外观设置
        appearance_group = QGroupBox("外观设置")
        appearance_form = QFormLayout(appearance_group)
        appearance_form.setSpacing(10)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("跟随系统", "system")
        self.theme_combo.addItem("浅色", "light")
        self.theme_combo.addItem("深色", "dark")
        self.theme_combo.setToolTip("选择界面主题颜色方案，跟随系统将自动匹配 Windows 深浅色设置")
        appearance_form.addRow("主题：", self.theme_combo)
        root.addWidget(appearance_group)

        root.addStretch()

        tip = QLabel(
            "说明：修改设置后点击「保存」。若检测正在运行，需停止后重新启动才会生效。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #888; font-size: 12px;")
        root.addWidget(tip)

    def _load_values(self) -> None:
        cfg = self.config_manager.config
        monitor_cfg = cfg.get("monitor", {}) or {}
        action_cfg = cfg.get("action", {}) or {}
        self.interval_spin.setValue(int(monitor_cfg.get("interval", 2)))
        self.send_interval_spin.setValue(float(cfg.get("send_interval", 1.5)))
        self.auto_reply_check.setChecked(bool(action_cfg.get("auto_reply", False)))
        self.ignore_self_check.setChecked(bool(cfg.get("ignore_self", True)))
        self.ignore_system_check.setChecked(bool(cfg.get("ignore_system", True)))
        theme = cfg.get("theme", "system")
        idx = self.theme_combo.findData(theme)
        self.theme_combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _on_save(self) -> None:
        cfg = self.config_manager.config
        cfg.setdefault("monitor", {})["interval"] = self.interval_spin.value()
        cfg.setdefault("action", {})["auto_reply"] = self.auto_reply_check.isChecked()
        cfg["send_interval"] = self.send_interval_spin.value()
        cfg["ignore_self"] = self.ignore_self_check.isChecked()
        cfg["ignore_system"] = self.ignore_system_check.isChecked()
        cfg["theme"] = self.theme_combo.currentData()
        try:
            self.config_manager.save()
            msg = "设置已保存。"
            if self._is_running_cb and self._is_running_cb():
                msg += "\n\n检测正在运行，需停止后重新启动才会生效。"
            QMessageBox.information(self, "保存成功", msg)
            self.config_saved.emit()
            logging.getLogger("wechat.gui").info("全局设置已保存")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"设置保存失败：\n{e}")

    def reload(self) -> None:
        self._load_values()
