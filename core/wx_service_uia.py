# -*- coding: utf-8 -*-
"""微信操作封装层（UIA 直采版）。

方案C：自研 UIA 直采，绕过 wxauto 的全量 GetChildren 拉取。

核心优化：
1. 增量拉取：用 GetLastChildControl + GetPreviousSiblingControl 倒序遍历，
   遇到已知 RuntimeId 立即停止。新增 N 条只调用 N+1 次 UIA，
   而 wxauto 的 GetChildren 会全量遍历所有消息（O(总数)）。
2. set 去重：用 set 替代 list，查重 O(1)。
3. 直接遍历子控件找发送人按钮：不用 wxauto 的 ButtonControl(foundIndex=) 搜索
   （后者会触发全树搜索）。
4. 缓存控件引用：msg_list / editbox / uia_api 只初始化一次。

窗口管理（ChatWith 等）复用 wxauto.WeChat，因其逻辑成熟稳定；
消息拉取与解析完全自研，是性能瓶颈所在。

与 wx_service.py 接口完全一致，可通过配置 use_uia 切换。
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from .wx_service import FRIEND_TYPE, SELF_TYPE, WxService

# 延迟导入 wxauto，避免主线程未 CoInitialize 时报错
_uia = None
def _get_uia():
    global _uia
    if _uia is None:
        from wxauto import uiautomation as uia
        _uia = uia
    return _uia


# 微信消息项高度（与 wxauto.WxParam 对齐）
_SYS_TEXT_HEIGHT = 33       # 系统提示
_TIME_TEXT_HEIGHT = 34      # 时间分隔
_RECALL_TEXT_HEIGHT = 45    # 撤回提示
_NEW_MSG_SEP_HEIGHT = 50    # "以下为新消息"分隔符（新版微信）


class Msg:
    """精简消息对象，兼容 wxauto 的 .type/.sender/.content 接口。"""

    __slots__ = ("type", "sender", "content")

    def __init__(self, type_: str, sender: str, content: str) -> None:
        self.type = type_
        self.sender = sender
        self.content = content

    def __repr__(self) -> str:
        return f"<Msg type={self.type} sender={self.sender!r} content={self.content!r}>"


class ChatWndLite:
    """精简版 ChatWnd：增量拉取 + 缓存控件。

    与 wxauto.elements.ChatWnd 的差异：
    - GetNewMessage 改为倒序增量遍历，不全量 GetChildren
    - _split 简化为 _parse_item，跳过图片/文件等复杂解析
    - usedmsgid 改用 set，查重 O(1)
    """

    def __init__(self, who: str, language: str = "cn") -> None:
        self.who = who
        self.language = language
        # 已读消息的 RuntimeId 集合（字符串化，便于哈希）
        self.used_msgids: set = set()
        # 控件引用缓存（只初始化一次）
        self._uia_api = None
        self._msg_list = None
        self._editbox = None
        self._init_window()

    def _init_window(self) -> None:
        """查找聊天窗口并缓存控件引用。

        wxauto.AddListenChat 已确保窗口就绪，这里直接查找控件。
        加 2 秒等待兜底，防止极端情况下 UIA 树刷新延迟。
        """
        uia = _get_uia()
        self._uia_api = uia.WindowControl(searchDepth=1, ClassName="ChatWnd", Name=self.who)
        # 等待窗口就绪（AddListenChat 应已打开，这里只是兜底）
        if not self._uia_api.Exists(maxSearchSeconds=2):
            raise RuntimeError(f"聊天窗口 '{self.who}' 未找到")
        self._editbox = self._uia_api.EditControl()
        self._msg_list = self._uia_api.ListControl()
        # 初始化：记录当前所有消息 ID 为已读，避免启动瞬间把历史消息当新消息
        self._init_used_msgids()

    def _init_used_msgids(self) -> None:
        """启动时把现有消息全部标记为已读。"""
        for item in self._iter_all_items():
            self.used_msgids.add(self._runtime_id(item))

    @staticmethod
    def _runtime_id(ctrl: Any) -> str:
        """RuntimeId 字符串化（与 wxauto 的 ''.join(map(str, ...)) 一致）。"""
        return "".join(str(i) for i in ctrl.GetRuntimeId())

    def _iter_all_items(self):
        """正向遍历所有 ListItemControl（仅初始化用，平时不用）。"""
        child = self._msg_list.GetFirstChildControl()
        while child:
            if child.ControlTypeName == "ListItemControl":
                yield child
            child = child.GetNextSiblingControl()

    def get_new_messages(self) -> List[Msg]:
        """增量拉取新消息：倒序遍历，遇到已读 ID 立即停止。

        性能对比（假设列表共 100 条，新增 2 条）：
        - wxauto GetNewMessage: GetChildren() 遍历 100 条 + 逐条 GetRuntimeId = 100+ 次 UIA 调用
        - 本方法: GetLastChildControl + 2 次 GetPreviousSiblingControl = 3 次 UIA 调用
        """
        new_items: List[Any] = []
        last = self._msg_list.GetLastChildControl()
        while last is not None:
            if last.ControlTypeName != "ListItemControl":
                last = last.GetPreviousSiblingControl()
                continue
            rid = self._runtime_id(last)
            if rid in self.used_msgids:
                break  # 遇到已读，前面的都是旧的，停止
            new_items.append(last)
            last = last.GetPreviousSiblingControl()
        if not new_items:
            return []
        new_items.reverse()  # 倒序变正序（旧→新）
        # 更新已读集合
        for item in new_items:
            self.used_msgids.add(self._runtime_id(item))
        # 解析为 Msg 对象
        msgs = [self._parse_item(item) for item in new_items]
        # 调试日志：帮助定位消息解析问题（找到消息但未回复时查看）
        import logging as _logging
        _log = _logging.getLogger("wechat.wx_service_uia")
        for i, m in enumerate(msgs):
            _log.info(
                f"[解析] #{i} type={m.type} sender={m.sender!r} content={m.content[:30]!r}"
            )
        return msgs

    def _parse_item(self, item: Any) -> Msg:
        """精简版 _split：只提取 type/sender/content，跳过图片/文件解析。

        与 wxauto._split 的差异：
        - 不调用 MsgItem.ButtonControl(foundIndex=) 搜索（改为直接遍历子控件）
        - 不处理图片/文件/语音下载
        - 不调用 TextControl().Exists()（额外的 UIA 调用）
        """
        import logging as _logging
        _log = _logging.getLogger("wechat.wx_service_uia")
        try:
            name = item.Name
            rect = item.BoundingRectangle
            height = rect.height()
        except Exception as e:
            _log.warning(f"[解析异常] 读取控件属性失败: {e}")
            return Msg("sys", "", "")

        _log.debug(f"[解析详情] name={name[:30]!r} height={height}")

        # 系统提示 / 时间分隔 / 撤回 / 新消息分隔符
        if height == _SYS_TEXT_HEIGHT:
            return Msg("sys", "", name)
        if height == _TIME_TEXT_HEIGHT:
            return Msg("sys", "", name)
        if height == _RECALL_TEXT_HEIGHT:
            return Msg("sys", "", name if "撤回" in name else "")
        if height == _NEW_MSG_SEP_HEIGHT:
            # "以下为新消息"分隔符，新版微信特有
            return Msg("sys", "", name)

        # 正常消息：遍历子控件找第一个 Name 非空的 ButtonControl
        sender, is_self = self._get_sender(item, rect)
        _log.debug(f"[解析详情] sender={sender!r} is_self={is_self} height={height}")
        if is_self:
            return Msg(SELF_TYPE, "", name)
        if sender:
            return Msg(FRIEND_TYPE, sender, name)
        # 找不到发送人按钮：可能是新版本微信控件结构变化
        # 兜底：按好友消息处理（content 仍可用），sender 留空让上层私聊逻辑兜底
        _log.warning(
            f"[解析兜底] 未找到发送人按钮，按 friend 兜底。height={height} name={name[:30]!r}"
        )
        return Msg(FRIEND_TYPE, "", name)

    @staticmethod
    def _get_sender(item: Any, item_rect: Any) -> Tuple[str, bool]:
        """遍历子控件找发送人按钮，返回 (sender, is_self)。

        新版微信控件结构（诊断实测）：
          ListItemControl(name=消息内容, h=80)
            └─ PaneControl(h=80)
                ├─ ButtonControl(name=发送人名, h=51)  ← 在第二层
                ├─ PaneControl(消息气泡)
                └─ PaneControl

        所以需要遍历到第二层（直接子 + 孙子）。
        wxauto 用 MsgItem.ButtonControl(foundIndex=) 全树搜索，
        这里改为限定深度的直接遍历，只调用必要的 UIA。
        """
        mid = (item_rect.left + item_rect.right) / 2

        # 第一层：ListItem 的直接子控件
        child = item.GetFirstChildControl()
        while child is not None:
            # 直接子就是 ButtonControl 的情况（旧版结构）
            if child.ControlTypeName == "ButtonControl":
                btn_name = child.Name
                if btn_name:
                    btn_rect = child.BoundingRectangle
                    if btn_rect.left < mid:
                        return (btn_name, False)  # 左侧 = 他人
                    return ("", True)  # 右侧 = 自己
            # 第二层：遍历子的子（新版结构，ButtonControl 在 Pane 下）
            else:
                grandchild = child.GetFirstChildControl()
                while grandchild is not None:
                    if grandchild.ControlTypeName == "ButtonControl":
                        btn_name = grandchild.Name
                        if btn_name:
                            btn_rect = grandchild.BoundingRectangle
                            if btn_rect.left < mid:
                                return (btn_name, False)  # 左侧 = 他人
                            return ("", True)  # 右侧 = 自己
                    grandchild = grandchild.GetNextSiblingControl()
            child = child.GetNextSiblingControl()
        return ("", False)

    def _ensure_window_visible(self) -> None:
        """确保聊天窗口可见（非最小化），避免发送失败和系统响声。

        最小化窗口上 editbox.Click/SendKeys 会失败，触发多次系统提示音，
        最后回退到 wxauto.SendMsg（_show 置顶）才成功。
        这里在发送前主动恢复窗口（SW_RESTORE，不置顶），让快速发送一次成功。
        """
        try:
            import win32gui
            hwnd = win32gui.FindWindow("ChatWnd", self.who)
            if hwnd and win32gui.IsIconic(hwnd):
                # SW_RESTORE = 9：恢复最小化窗口，不置顶
                win32gui.ShowWindow(hwnd, 9)
                # 等待窗口刷新，UIA 树需要时间重建
                import time as _time
                _time.sleep(0.3)
                self._uia_logger.info(f"聊天窗口 '{self.who}' 已从最小化恢复")
        except Exception as e:
            self._uia_logger.debug(f"恢复窗口可见失败（非致命）：{e}")

    @property
    def editbox(self) -> Any:
        """编辑框控件引用（供 send_msg 使用）。"""
        return self._editbox


class UiaWxService(WxService):
    """UIA 直采版微信服务：继承 WxService，重写消息拉取与发送。

    复用父类的 connect / add_listen / disconnect（窗口管理），
    重写 get_listen_messages（增量拉取）与 send_msg（快速发送）。
    """

    def __init__(self, language: str = "cn", debug: bool = False) -> None:
        super().__init__(language, debug)
        # 监听对象名 → ChatWndLite 实例
        self._chat_lites: Dict[str, ChatWndLite] = {}
        self._uia_logger = logging.getLogger("wechat.wx_service_uia")

    def add_listen(self, who: str) -> bool:
        """添加监听：复用 wxauto.AddListenChat 确保窗口就绪，再创建 ChatWndLite。

        wxauto.AddListenChat 会：检查窗口存在→不存在则ChatWith+双击→创建ChatWnd→GetAllMessage
        这一套流程确保聊天窗口完全渲染、ListControl 可访问。
        我们复用它打开窗口，然后创建自己的 ChatWndLite 做增量拉取。
        wxauto.ChatWnd 只在 add_listen 时用一次，后续轮询用 ChatWndLite。

        修复"独立打开聊天窗口导致重启检测不到"问题：
        - 每次启动时先清理可能残留的旧 ChatWnd 窗口（上次未正常关闭）
        - 强制 wxauto.AddListenChat 重新打开窗口，确保控件结构最新
        """
        if not self.connected:
            return False

        # 清理可能残留的旧聊天窗口：避免上次退出未关闭导致控件失效
        self._close_stale_chat_wnd(who)

        try:
            # 复用 wxauto.AddListenChat：它会确保窗口正确打开并渲染
            # 内部会创建 wxauto.ChatWnd 并调用 GetAllMessage（触发 ListControl Refind）
            self.wx.AddListenChat(who)  # type: ignore[attr-defined]
        except Exception as e:
            self.logger.error(f"wxauto.AddListenChat 打开聊天 '{who}' 失败：{e}")
            return False
        try:
            lite = ChatWndLite(who, self.language)
            self._chat_lites[who] = lite
            self._uia_logger.info(f"已添加 UIA 监听：{who}（初始已读 {len(lite.used_msgids)} 条）")
            return True
        except Exception as e:
            self._uia_logger.error(f"创建 ChatWndLite 失败 '{who}'：{e}", exc_info=True)
            return False

    def _close_stale_chat_wnd(self, who: str) -> None:
        """关闭可能残留的旧聊天窗口，避免重启时检测不到。

        wxauto.AddListenChat 会检查 ClassName='ChatWnd' 的窗口是否存在：
        - 如果存在（上次未关闭），直接复用旧窗口，但旧窗口控件可能已失效
        - 这里主动关闭旧窗口，强制 AddListenChat 重新打开干净的新窗口

        注意：只关闭窗口，不清理 wxauto.listen 字典（AddListenChat 会重新赋值）
        """
        try:
            from wxauto.uiautomation import uia
            # 查找所有匹配的 ChatWnd 窗口（可能多个）
            stale = uia.WindowControl(searchDepth=1, ClassName="ChatWnd", Name=who)
            if stale.Exists(maxSearchSeconds=0.2):
                # 发送 Esc 关闭窗口（比 SendKeys 更安全）
                try:
                    import win32gui
                    hwnd = stale.NativeWindowHandle
                    if hwnd:
                        win32gui.PostMessage(hwnd, 0x0010, 0, 0)  # WM_CLOSE
                        self._uia_logger.info(f"已关闭残留聊天窗口：{who}")
                except Exception:
                    # 退回 UIA 方式
                    stale.SendKeys("{Esc}")
                    self._uia_logger.info(f"已关闭残留聊天窗口（UIA）：{who}")
        except Exception as e:
            self._uia_logger.debug(f"清理旧窗口失败（非致命）：{e}")

    def get_listen_messages(self) -> Dict[Any, List[Any]]:
        """增量拉取所有监听对象的新消息。

        返回 {ChatWndLite: [Msg, ...]}，键为 ChatWndLite 实例（兼容父类接口，
        monitor.py 用 getattr(chat_obj, 'who', '') 取名字）。
        """
        if not self.connected:
            return {}
        result: Dict[Any, List[Any]] = {}
        for who, lite in self._chat_lites.items():
            try:
                msgs = lite.get_new_messages()
                if msgs:
                    result[lite] = msgs
                    self._msg_err_count = 0
            except Exception as e:
                self._msg_err_count = getattr(self, "_msg_err_count", 0) + 1
                if self._msg_err_count <= 2 or self._msg_err_count % 10 == 0:
                    self._uia_logger.error(
                        f"UIA 拉取 '{who}' 新消息失败（第 {self._msg_err_count} 次）：{e}"
                    )
        return result

    def send_msg(self, chat_obj: Any, msg: str) -> bool:
        """向指定聊天对象发送消息（快速版）。

        chat_obj 是 ChatWndLite 实例，直接用其 editbox，跳过 wxauto 的 _show()。
        """
        if not self.connected:
            return False
        # chat_obj 是 ChatWndLite，用其 editbox
        editbox = chat_obj.editbox
        if editbox is None:
            # 回退到父类（用 wxauto 原生 SendMsg）
            return super().send_msg(chat_obj, msg)
        # 发送前确保窗口可见（避免最小化时发送失败触发系统响声）
        if hasattr(chat_obj, "_ensure_window_visible"):
            chat_obj._ensure_window_visible()
        try:
            self._fast_send_via_editbox(editbox, msg)
            return True
        except Exception as e:
            self._uia_logger.debug(f"UIA 快速发送失败，回退 wxauto SendMsg：{e}")
            # 回退：用 wxauto 切换并发送
            try:
                self.wx.SendMsg(msg, who=chat_obj.who)  # type: ignore[attr-defined]
                return True
            except Exception as e2:
                self._uia_logger.error(f"发送消息失败：{e2}", exc_info=True)
                return False

    @staticmethod
    def _fast_send_via_editbox(editbox: Any, msg: str) -> None:
        """通过 editbox 粘贴发送（与 wx_service._fast_send 一致，但 editbox 来自 ChatWndLite）。"""
        import time as _time
        from wxauto.utils import SetClipboardText  # type: ignore

        if not editbox.HasKeyboardFocus:
            editbox.Click(simulateMove=False)
        t0 = _time.time()
        while True:
            if _time.time() - t0 > 5:
                raise TimeoutError(f"UIA 快速发送粘贴超时：{msg[:20]}")
            SetClipboardText(msg)
            editbox.SendKeys("{Ctrl}v")
            if editbox.GetValuePattern().Value:
                break
        editbox.SendKeys("{Enter}")

    def disconnect(self) -> None:
        """断开连接：清理 ChatWndLite 缓存后调用父类。"""
        self._chat_lites.clear()
        super().disconnect()
