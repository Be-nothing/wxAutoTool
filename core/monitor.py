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
from .wx_service import FRIEND_TYPE, SELF_TYPE

# 状态回调签名：(类别, 值)
#   类别 "wechat": "connected" | "disconnected"
#   类别 "run": "running" | "stopped"
#   类别 "stage": 阶段描述文本，如 "正在连接微信..."、"正在添加监听对象..."、"监听中"
#   类别 "alert": 关键错误提示文本，GUI 层应弹窗显示
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
        # 按聊天对象独立限流：{chat_name: last_send_timestamp}
        # 避免全局限流导致 A 群回复后 B 群需等待
        self._last_send_times: Dict[str, float] = {}
        # 监听对象名 → {type, rules}，私聊场景用 type 做发送人自动匹配
        self.name_to_listener: Dict[str, Dict[str, Any]] = {}
        # 兼容旧字段（如有外部代码引用）
        self.name_to_rules: Dict[str, List[Dict[str, Any]]] = {}
        self._disconnected_warned: bool = False
        self._slow_warned: bool = False  # 拉取慢告警（避免刷屏）
        # 上一次 check_message 结束时刻，用于估算消息滞后
        self._last_check_end_time: float = 0.0

        # 依赖：UIA 版本强制使用自研增量拉取（方案C）
        from .wx_service_uia import UiaWxService
        self.service = UiaWxService()
        self._service_mode = "UIA"
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
        self._emit_status("stage", "正在准备...")
        self._build_rules()
        self._emit_status("run", "running")

        # 连接微信并添加监听
        if self._connect_and_listen():
            self.logger.info("监控已启动，等待消息中...")
            self._emit_status("stage", "监听中")
        else:
            self.logger.warning("微信未连接，将进入重连等待状态")
            self._emit_status("stage", "等待微信重连...")

        # 主循环（可被 stop 终止）
        self._loop()

    def stop(self) -> None:
        """停止检测：置 running=False，循环将在当前轮次结束后退出。"""
        if not self.running:
            return
        self.running = False
        self.logger.info("正在停止监控...")
        self._emit_status("stage", "正在停止...")
        self._emit_status("run", "stopped")
        self.service.disconnect()
        self._emit_status("wechat", "disconnected")
        self._emit_status("stage", "已停止")
        # 重置限流状态与慢告警标志，避免重启后状态残留
        self._last_send_times.clear()
        self._slow_warned = False
        self._disconnected_warned = False

    # ------------------------------------------------------------------
    # 消息检测
    # ------------------------------------------------------------------
    def check_message(self) -> None:
        """单次微信消息检测与处理。

        延迟链路分三段记录：
          1. 消息滞后：上次 check 结束 → 本次拉取到消息（等待下一轮的耗时）
          2. 拉取耗时：GetListenMessage 遍历所有监听窗口
          3. 发送耗时：SendMsg 的 UI 自动化操作
        端到端延迟 = 滞后 + 拉取 + 发送
        """
        # 未连接则尝试重连
        if not self.service.connected:
            if not self.service.connect():
                self._emit_status("wechat", "disconnected")
                if not self._disconnected_warned:
                    self.logger.warning("微信连接断开，请重新登录。")
                    self._emit_status(
                        "alert",
                        "微信连接已断开！\n请检查微信是否已退出登录或被关闭。\n程序将自动尝试重连。"
                    )
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

        # 消息滞后：从上次 check 结束 → 本次 fetch 开始的等待时间
        # 这部分是 sleep 时间，不包含 fetch_cost，避免重复计算
        if self._last_check_end_time > 0:
            lag = max(0.0, fetch_start - self._last_check_end_time)
        else:
            lag = 0.0

        for chat_obj, msg_list in msgs_dict.items():
            chat_name = getattr(chat_obj, "who", "")
            self.logger.info(
                f"收到消息：来自 '{chat_name}'，{len(msg_list)} 条"
                f"（拉取耗时 {fetch_cost:.1f}s，消息滞后约 {lag:.1f}s）"
            )
            listener = self.name_to_listener.get(chat_name)
            if not listener:
                # 名称不匹配：列出已配置的监听对象名，帮助定位差异
                self.logger.warning(
                    f"'{chat_name}' 无匹配规则，跳过。已配置监听："
                    f"{list(self.name_to_listener.keys())}"
                )
                continue
            rules = listener.get("rules", [])
            ltype = listener.get("type", "friend")

            for msg in msg_list:
                try:
                    self._handle_message(chat_obj, chat_name, rules, msg, fetch_cost, lag, ltype)
                except Exception as e:
                    self.logger.error(f"处理消息出错：{e}", exc_info=True)

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------
    def _build_rules(self) -> None:
        """构建 名称→监听对象 映射（含 type 和 rules）。"""
        self.name_to_listener = {}
        self.name_to_rules = {}
        self.logger.info(f"监听对象数量：{len(self.listeners)}")
        self.logger.info(f"消息拉取引擎：{self._service_mode}（UIA 增量直采）")
        for listener in self.listeners:
            ltype = listener.get("type", "unknown")
            name = listener.get("name", "")
            rules = listener.get("rules", [])
            self.name_to_listener[name] = {"type": ltype, "rules": rules}
            self.name_to_rules[name] = rules  # 兼容旧字段
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
        self._emit_status("stage", "正在连接微信...")
        if not self.service.connect():
            self._emit_status("wechat", "disconnected")
            self.logger.warning("微信未连接，请确认微信已登录并处于前台")
            self._emit_status(
                "alert",
                "无法连接微信客户端，请确认：\n1. 微信已登录并处于前台\n2. 没有其他程序占用微信窗口"
            )
            return False
        self._emit_status("wechat", "connected")
        self._add_listeners()
        return True

    def _add_listeners(self) -> None:
        """逐个添加监听对象。完成后切回应用窗口并发送 started 状态。"""
        total = len(self.listeners)
        self._emit_status("stage", f"正在添加监听对象（共 {total} 个）...")
        failed_names = []
        success_count = 0
        for i, listener in enumerate(self.listeners, 1):
            name = listener.get("name", "")
            ltype = listener.get("type", "friend")
            self._emit_status("stage", f"正在添加监听对象（{i}/{total}）：{name}")
            if self.service.add_listen(name):
                success_count += 1
            else:
                self.logger.error(
                    f"请确认名称与微信中显示完全一致，且 '{name}' 在聊天列表中"
                )
                failed_names.append(name)

        # 添加完成后，切回应用主窗口（用 win32 SetForegroundWindow）
        self._bring_app_to_foreground()

        if failed_names:
            names_str = "、".join(failed_names)
            self._emit_status(
                "alert",
                f"以下监听对象添加失败，请检查名称是否与微信完全一致：\n{names_str}"
            )

        # 发送"已启动"状态：让悬浮组件切换到"监听中"
        self._emit_status("started", f"已开始监听 {success_count}/{total} 个对象")

    def _bring_app_to_foreground(self) -> None:
        """添加完监听对象后，将应用主窗口切到前台。

        主窗口在 on_start 时被 showMinimized() 最小化了，
        这里通过 EnumWindows 找到它，用 ShowWindow(SW_RESTORE) 恢复，
        再 SetForegroundWindow 切到前台。
        """
        try:
            import win32gui
            result = []
            def _enum(hwnd, _):
                title = win32gui.GetWindowText(hwnd)
                if "微信自动" in title and title:
                    result.append(hwnd)
                return True
            win32gui.EnumWindows(_enum, None)
            if result:
                hwnd = result[0]
                # SW_RESTORE = 9：恢复最小化/最大化的窗口
                win32gui.ShowWindow(hwnd, 9)
                # 切到前台
                win32gui.SetForegroundWindow(hwnd)
                self.logger.info("已自动切回应用主窗口")
            else:
                self.logger.debug("未找到应用主窗口，可能已关闭")
        except Exception as e:
            self.logger.debug(f"切回应用窗口失败（非致命）：{e}")

    def _handle_message(
        self,
        chat_obj: Any,
        chat_name: str,
        rules: List[Dict[str, Any]],
        msg: Any,
        fetch_cost: float = 0.0,
        lag: float = 0.0,
        ltype: str = "friend",
    ) -> None:
        """处理单条消息：过滤、记录、匹配、回复。

        延迟三段：
          - lag: 消息滞后（上次 check 结束 → 本次拉取到消息）
          - fetch_cost: 拉取耗时（GetListenMessage）
          - send_cost: 发送耗时（SendMsg 的 UI 操作）
        端到端 ≈ lag + fetch_cost + send_cost

        私聊场景（ltype='friend'）：规则 sender 为空时自动匹配监听对象名，
        用户无需重复填写发送人。
        """
        # 系统消息过滤
        if self.ignore_system and msg.type not in (FRIEND_TYPE, SELF_TYPE):
            return
        # 自己消息过滤
        if self.ignore_self and msg.type == SELF_TYPE:
            return

        sender = msg.sender
        content = msg.content
        recv_t = time.time()
        # 私聊场景：发送人就是监听对象本身，日志直接显示监听对象名更直观
        display_sender = chat_name if (ltype == "friend" and not sender) else sender
        self.logger.info(f"[{chat_name}] {display_sender}: {content}")

        if not self.auto_reply:
            return

        reply = self._match_rules(rules, sender, content, chat_name, ltype)
        if not reply:
            return
        if not self._can_send(chat_name):
            # 按聊天对象限流：显示该对象还需等待多久，便于排查延迟
            last = self._last_send_times.get(chat_name, 0.0)
            wait = max(0.0, self.send_interval - (time.time() - last))
            self.logger.info(
                f"  -> 受发送间隔限制（{chat_name} 还需 {wait:.1f} 秒），跳过本次回复：{reply}"
            )
            return
        self.logger.info(f"  -> 匹配成功，准备回复：{reply}")
        send_start = time.time()
        if self.service.send_msg(chat_obj, reply):
            send_cost = time.time() - send_start
            self._last_send_times[chat_name] = time.time()
            # 端到端延迟分解：滞后 + 拉取 + 发送
            e2e = lag + fetch_cost + send_cost
            self.logger.info(
                f"  -> 已发送回复：{reply}"
                f"（发送 {send_cost:.1f}s，端到端约 {e2e:.1f}s"
                f" = 滞后 {lag:.1f} + 拉取 {fetch_cost:.1f} + 发送 {send_cost:.1f}）"
            )

    def _match_rules(
        self,
        rules: List[Dict[str, Any]],
        sender: str,
        content: str,
        chat_name: str = "",
        ltype: str = "friend",
    ) -> Optional[str]:
        """按规则匹配回复内容。

        - 规则 sender 为空：
          - 群聊：不限制发送人（匹配任意发送人）
          - 私聊：自动用监听对象名匹配（用户无需重复填写发送人）
        - keyword 为空表示匹配任意内容
        - keyword 大小写不敏感
        """
        text = (content or "").strip()
        for rule in rules:
            rule_sender = (rule.get("sender", "") or "").strip()
            keyword = rule.get("keyword", "") or ""
            reply = rule.get("reply", "")

            if rule_sender:
                # 显式指定了发送人，严格匹配
                if rule_sender != sender:
                    continue
            elif ltype == "friend":
                # 私聊且未指定发送人：自动匹配监听对象名
                # 私聊场景 sender 可能与监听对象名不完全一致（备注/昵称差异），
                # 这里放宽为：sender 为空时直接通过（私聊对方就是唯一发送人）
                pass
            # 群聊且未指定发送人：不限制，直接通过

            if keyword == "" or keyword.lower() in text.lower():
                return reply
        return None

    def _can_send(self, chat_name: str) -> bool:
        """是否满足发送间隔限流（按聊天对象独立计时）。"""
        last = self._last_send_times.get(chat_name, 0.0)
        return (time.time() - last) >= self.send_interval

    def _loop(self) -> None:
        """主轮询循环：检测消息 → 分段睡眠，running=False 时退出。

        sleep 时间会扣除本次 check_message 的耗时，避免"检测耗时 + 轮询间隔"
        叠加导致实际响应间隔远大于配置的 poll_interval。
        每轮结束时更新 _last_check_end_time，用于估算消息滞后。
        """
        while self.running:
            t0 = time.time()
            try:
                self.check_message()
            except Exception as e:
                self.logger.error(f"轮询出错：{e}", exc_info=True)
            # 记录本次 check 结束时刻，供下次拉取到消息时估算滞后
            self._last_check_end_time = time.time()
            # 扣除检测耗时：若检测本身已超过 poll_interval，则不额外睡眠
            elapsed = self._last_check_end_time - t0
            remaining = max(0.0, self.poll_interval - elapsed)
            self._sleep_interruptible(remaining)
        self.logger.info("监控已停止")

    def _sleep_interruptible(self, seconds: float) -> None:
        """分段睡眠，便于在睡眠期间快速响应停止请求。"""
        remaining = seconds
        while remaining > 0 and self.running:
            time.sleep(min(_SLEEP_SLICE, remaining))
            remaining -= _SLEEP_SLICE
