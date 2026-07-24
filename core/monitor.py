# -*- coding: utf-8 -*-
"""微信监控核心逻辑。

将原 monitor.py 的 while True 脚本改造为可控的 WechatMonitor 类：
- start()/stop() 支持启停
- check_message() 单次消息检测
- 循环可被 running 标志安全终止，不阻塞 GUI
- 所有微信操作委托 WxService，异常被捕获并记录

设计为在 QThread 中运行：start() 阻塞至 stop() 被调用。
状态变化通过回调上报给 GUI 层（不依赖 PySide6）。
"""

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from .config import ConfigManager
from .wx_service import FRIEND_TYPE, SELF_TYPE, WxService

# 状态回调签名：(类别, 值)
#   类别 "wechat": "connected" | "disconnected"
#   类别 "run": "running" | "stopped"
StatusCallback = Callable[[str, str], None]

# 分段睡眠间隔，便于快速响应停止请求
_SLEEP_SLICE = 0.2


class WechatMonitor:
    """微信消息监控器：启停可控、异常安全、非阻塞。"""

    def __init__(self, config: ConfigManager) -> None:
        cfg = config.config
        self.config = config

        # 监听配置
        self.listeners: List[Dict[str, Any]] = cfg.get("listeners", [])
        self.ignore_self: bool = cfg.get("ignore_self", True)
        self.ignore_system: bool = cfg.get("ignore_system", True)
        self.send_interval: float = float(cfg.get("send_interval", 3))
        # 优先使用 monitor.interval（新结构），兼容旧 poll_interval
        monitor_cfg = cfg.get("monitor", {}) or {}
        self.poll_interval: float = float(
            monitor_cfg.get("interval") or cfg.get("poll_interval", 5)
        )
        self.auto_reply: bool = bool((cfg.get("action", {}) or {}).get("auto_reply", False))

        # 运行状态
        self.running: bool = False
        self.last_send_time: float = 0.0
        self.name_to_rules: Dict[str, List[Dict[str, Any]]] = {}
        self._disconnected_warned: bool = False
        self._slow_warned: bool = False  # 拉取慢告警（避免刷屏）

        # 依赖
        self.service = WxService()
        self.logger = logging.getLogger("wechat.monitor")

        # 状态回调（GUI 层注册）
        self._status_cb: Optional[StatusCallback] = None

    def set_status_callback(self, callback: Optional[StatusCallback]) -> None:
        """注册状态变化回调。"""
        self._status_cb = callback

    def _emit_status(self, kind: str, value: str) -> None:
        """上报状态。"""
        if self._status_cb is not None:
            try:
                self._status_cb(kind, value)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 启停控制
    # ------------------------------------------------------------------
    def start(self) -> None:
        """启动检测：连接微信、添加监听、进入轮询循环（阻塞至 stop）。"""
        if self.running:
            return

        self.running = True
        self._disconnected_warned = False
        self.logger.info("=" * 50)
        self.logger.info("微信消息监控程序启动")
        self._build_rules()
        self._emit_status("run", "running")

        # 连接微信并添加监听
        if self._connect_and_listen():
            self.logger.info("监控已启动，等待消息中...")
        else:
            self.logger.warning("微信未连接，将进入重连等待状态")

        # 主循环（可被 stop 终止）
        self._loop()

    def stop(self) -> None:
        """停止检测：置 running=False，循环将在当前轮次结束后退出。"""
        if not self.running:
            return
        self.running = False
        self.logger.info("正在停止监控...")
        self._emit_status("run", "stopped")
        self.service.disconnect()
        self._emit_status("wechat", "disconnected")

    # ------------------------------------------------------------------
    # 消息检测
    # ------------------------------------------------------------------
    def check_message(self) -> None:
        """单次微信消息检测与处理。

        若微信未连接则尝试重连；连接成功后拉取监听消息并按规则匹配回复。
        单次检测耗时会被记录，超过阈值（默认 3 秒）时告警，
        提示用户延迟来源于 wxauto 的 UI 自动化遍历（监听对象越多越慢）。
        """
        # 未连接则尝试重连
        if not self.service.connected:
            if not self.service.connect():
                self._emit_status("wechat", "disconnected")
                if not self._disconnected_warned:
                    self.logger.warning("微信连接断开，请重新登录。")
                    self._disconnected_warned = True
                return
            # 重连成功：重新添加监听并复位告警
            self._disconnected_warned = False
            self._emit_status("wechat", "connected")
            self._add_listeners()

        # 记录单次拉取耗时（wxauto 的 GetListenMessage 是延迟主因）
        fetch_start = time.time()
        msgs_dict = self.service.get_listen_messages()
        fetch_cost = time.time() - fetch_start
        # 超过 3 秒告警一次（避免刷屏），帮助用户理解延迟来源
        if fetch_cost > 3.0 and not self._slow_warned:
            self.logger.warning(
                f"本次消息拉取耗时 {fetch_cost:.1f} 秒（监听对象 {len(self.listeners)} 个）。"
                f"wxauto 基于 UI 自动化逐个遍历聊天窗口，监听对象越多越慢，"
                f"属固有行为，非程序卡死。"
            )
            self._slow_warned = True
        elif fetch_cost <= 1.0:
            # 恢复正常后复位告警标志，便于下次再次变慢时提示
            self._slow_warned = False

        if not msgs_dict:
            return

        for chat_obj, msg_list in msgs_dict.items():
            chat_name = getattr(chat_obj, "who", "")
            rules = self.name_to_rules.get(chat_name, [])
            if not rules:
                continue

            for msg in msg_list:
                try:
                    self._handle_message(chat_obj, chat_name, rules, msg)
                except Exception as e:
                    self.logger.error(f"处理消息出错：{e}", exc_info=True)

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------
    def _build_rules(self) -> None:
        """构建 名称→规则 映射。"""
        self.name_to_rules = {}
        self.logger.info(f"监听对象数量：{len(self.listeners)}")
        for listener in self.listeners:
            ltype = listener.get("type", "unknown")
            name = listener.get("name", "")
            rules = listener.get("rules", [])
            self.name_to_rules[name] = rules
            self.logger.info(f"  [{ltype}] {name} - {len(rules)}条规则")
        self.logger.info(f"忽略自己消息：{self.ignore_self}")
        self.logger.info(f"忽略系统消息：{self.ignore_system}")
        self.logger.info(f"发送间隔：{self.send_interval}秒")
        self.logger.info(f"轮询间隔：{self.poll_interval}秒")
        self.logger.info(f"自动回复：{self.auto_reply}")
        self.logger.info("=" * 50)

    def _connect_and_listen(self) -> bool:
        """连接微信并添加所有监听对象。"""
        self.logger.info("正在连接微信客户端...")
        if not self.service.connect():
            self._emit_status("wechat", "disconnected")
            self.logger.warning("微信未连接，请确认微信已登录并处于前台")
            return False
        self._emit_status("wechat", "connected")
        self._add_listeners()
        return True

    def _add_listeners(self) -> None:
        """逐个添加监听对象。"""
        for listener in self.listeners:
            name = listener.get("name", "")
            ltype = listener.get("type", "friend")
            if not self.service.add_listen(name):
                self.logger.error(
                    f"请确认名称与微信中显示完全一致，且 '{name}' 在聊天列表中"
                )

    def _handle_message(
        self,
        chat_obj: Any,
        chat_name: str,
        rules: List[Dict[str, Any]],
        msg: Any,
    ) -> None:
        """处理单条消息：过滤、记录、匹配、回复。"""
        # 系统消息过滤
        if self.ignore_system and msg.type not in (FRIEND_TYPE, SELF_TYPE):
            return
        # 自己消息过滤
        if self.ignore_self and msg.type == SELF_TYPE:
            return

        sender = msg.sender
        content = msg.content
        self.logger.info(f"[{chat_name}] {sender}: {content}")

        if not self.auto_reply:
            return

        reply = self._match_rules(rules, sender, content)
        if not reply:
            return
        if not self._can_send():
            self.logger.info(f"  -> 受发送间隔限制，跳过本次回复：{reply}")
            return
        self.logger.info(f"  -> 匹配成功，准备回复：{reply}")
        if self.service.send_msg(chat_obj, reply):
            self.last_send_time = time.time()
            self.logger.info(f"  -> 已发送回复：{reply}")

    def _match_rules(
        self,
        rules: List[Dict[str, Any]],
        sender: str,
        content: str,
    ) -> Optional[str]:
        """按规则匹配回复内容。

        - sender 为空表示不限制发送人
        - keyword 为空表示匹配任意内容
        - keyword 大小写不敏感
        """
        text = (content or "").strip()
        for rule in rules:
            rule_sender = (rule.get("sender", "") or "").strip()
            keyword = rule.get("keyword", "") or ""
            reply = rule.get("reply", "")

            if rule_sender and rule_sender != sender:
                continue
            if keyword == "" or keyword.lower() in text.lower():
                return reply
        return None

    def _can_send(self) -> bool:
        """是否满足发送间隔限流。"""
        return (time.time() - self.last_send_time) >= self.send_interval

    def _loop(self) -> None:
        """主轮询循环：检测消息 → 分段睡眠，running=False 时退出。"""
        while self.running:
            try:
                self.check_message()
            except Exception as e:
                self.logger.error(f"轮询出错：{e}", exc_info=True)
            self._sleep_interruptible(self.poll_interval)
        self.logger.info("监控已停止")

    def _sleep_interruptible(self, seconds: float) -> None:
        """分段睡眠，便于在睡眠期间快速响应停止请求。"""
        remaining = seconds
        while remaining > 0 and self.running:
            time.sleep(min(_SLEEP_SLICE, remaining))
            remaining -= _SLEEP_SLICE
