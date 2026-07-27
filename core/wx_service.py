# -*- coding: utf-8 -*-
"""微信操作封装层。

对 wxauto.WeChat 进行封装，所有微信操作均 try/except，绝不向上抛出异常。
同时负责 libs/ 依赖路径引导，确保 wxauto 及 pywin32 可正常导入。

本模块是唯一与 wxauto 直接交互的地方，监控逻辑只依赖本模块，便于维护。
"""

import logging
import os
import sys
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 消息类型：friend 私聊 / self 自己发送 / system 系统
FRIEND_TYPE = "friend"
SELF_TYPE = "self"


def _ensure_wxauto_importable() -> None:
    """将 libs/ 加入 sys.path 并引导 pywin32，确保 wxauto 可导入。

    逻辑迁移自原 monitor.py 顶部，支持离线运行与 PyInstaller 打包环境。
    """
    libs_dir = os.path.join(BASE_DIR, "libs")
    if not os.path.isdir(libs_dir):
        return

    for sub in ("", "win32", os.path.join("win32", "lib"), "pythonwin"):
        path = os.path.join(libs_dir, sub) if sub else libs_dir
        if os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)

    # pywin32 运行所需 DLL 目录
    pywin32_dll = os.path.join(libs_dir, "pywin32_system32")
    if os.path.isdir(pywin32_dll):
        os.environ["PATH"] = pywin32_dll + os.pathsep + os.environ.get("PATH", "")

    try:
        import pywin32_bootstrap  # type: ignore
    except Exception:
        # bootstrap 可能在打包环境已处理，忽略失败
        pass


# 自愈式导入：优先用系统已安装的依赖；导入失败时才引导 libs/ 作为兜底
# （libs 中的部分 C 扩展可能与当前 Python 版本不匹配，故不抢占系统包）
try:
    from wxauto import WeChat  # type: ignore
except ImportError:
    _ensure_wxauto_importable()
    from wxauto import WeChat  # type: ignore  # noqa: E402


class WxService:
    """微信操作服务：连接、监听、收发消息，全部异常安全。"""

    def __init__(self, language: str = "cn", debug: bool = False) -> None:
        self.language = language
        self.debug = debug
        self.wx: Optional[WeChat] = None
        self.logger = logging.getLogger("wechat.wx_service")

    @property
    def connected(self) -> bool:
        """当前是否已连接微信。"""
        return self.wx is not None

    @property
    def nickname(self) -> str:
        """当前登录账号昵称，未连接返回空串。"""
        return getattr(self.wx, "nickname", "") if self.connected else ""

    def _co_initialize(self) -> None:
        """在工作线程中初始化 COM（wxauto 内部 comtypes 依赖）。

        原脚本在主线程运行，COM 已由系统初始化；改入 QThread 后必须手动 CoInitialize，
        否则 comtypes 创建 IUIAutomation 会抛 WinError -2147221008。
        可重复调用，每线程维护引用计数。
        """
        try:
            import pythoncom  # type: ignore
            pythoncom.CoInitialize()
        except Exception as e:
            self.logger.debug(f"COM 初始化跳过：{e}")

    def connect(self) -> bool:
        """连接微信客户端。成功返回 True，失败返回 False（不抛异常）。"""
        self._co_initialize()
        try:
            self.wx = WeChat(language=self.language, debug=self.debug)
            self.logger.info(f"微信连接成功，当前账号：{self.nickname}")
            return True
        except Exception as e:
            self.wx = None
            self.logger.error(f"微信连接失败：{e}", exc_info=True)
            return False

    def disconnect(self) -> None:
        """断开连接：清理 wxauto 内部 listen 字典后释放引用。

        必须先清理 wxauto.WeChat.listen，否则残留的聊天窗口 COM 引用
        会在后续 GetListenMessage 中触发 COMError 刷屏
       （错误码 -2147220991 '事件无法调用任何订户'）。
        """
        if self.wx is not None:
            try:
                # 清理 wxauto 内部监听字典，释放聊天窗口 COM 引用
                self.wx.listen.clear()
            except Exception:
                pass
        self.wx = None
        self.logger.info("微信连接已断开")

    def add_listen(self, who: str) -> bool:
        """添加监听对象（群聊或私聊名称需与微信显示完全一致）。

        失败时给出更明确的错误原因，帮助用户排查：
        - Find Control Timeout / list index out of range：名称不匹配
        - COMError：COM 环境异常，可能需要重启微信
        """
        if not self.connected:
            return False
        try:
            self.wx.AddListenChat(who=who)
            self.logger.info(f"已添加监听：{who}")
            return True
        except Exception as e:
            err = str(e)
            # 识别常见错误模式，给出针对性提示
            if "Find Control Timeout" in err or "list index out of range" in err:
                hint = "名称与微信显示不一致，或该聊天不在会话栏"
            elif "COMError" in err or "订户" in err:
                hint = "COM 异常，建议重启微信后重试"
            elif "cannot unpack" in err:
                hint = "搜索结果为空，名称不匹配"
            else:
                hint = "未知原因"
            self.logger.error(f"添加监听 '{who}' 失败：{err}（{hint}）")
            return False

    def get_listen_messages(self) -> Dict[Any, List[Any]]:
        """获取监听对象的新消息，返回 {聊天对象: [消息列表]}。

        COM 异常采用计数静默策略：连续失败仅周期性记录一次，
        避免停止检测瞬间 COM 对象失效导致日志刷屏。
        """
        if not self.connected:
            return {}
        try:
            result = self.wx.GetListenMessage() or {}
            # 成功一次即复位错误计数
            self._msg_err_count = 0
            return result
        except Exception as e:
            # COMError 在停止检测瞬间高频出现，采用计数降频
            self._msg_err_count = getattr(self, "_msg_err_count", 0) + 1
            # 前 2 次记录完整错误，之后每 10 次记录一次，避免刷屏
            if self._msg_err_count <= 2 or self._msg_err_count % 10 == 0:
                self.logger.error(
                    f"获取监听消息失败（第 {self._msg_err_count} 次）：{e}"
                )
            return {}

    def get_session_names(self) -> List[str]:
        """获取微信会话栏所有聊天对象名（用于 GUI 名称检测）。

        返回当前会话栏可见的聊天对象名列表。用户可据此验证
        监听对象名称是否与微信显示完全一致。
        """
        if not self.connected:
            return []
        try:
            sessions = self.wx.GetSessionList()  # type: ignore[attr-defined]
            return list(sessions.keys()) if sessions else []
        except Exception as e:
            self.logger.debug(f"获取会话列表失败：{e}")
            return []

    def send_msg(self, chat_obj: Any, msg: str) -> bool:
        """向指定聊天对象发送消息（快速版）。

        优化点：绕过 wxauto ChatWnd.SendMsg 内部的 _show()，
        该方法每次调用 4 个 Win32 API（FindWindow+ShowWindow+SetWindowPos×2），
        耗时约 0.5-1 秒。我们直接操作 editbox 粘贴发送，减少这部分开销。
        回退策略：快速发送失败则回退到 wxauto 原生 SendMsg。
        """
        if not self.connected:
            return False
        # 第一次发送时尝试快速路径
        try:
            self._fast_send(chat_obj, msg)
            return True
        except Exception as e:
            self.logger.debug(f"快速发送失败，回退原生 SendMsg：{e}")
            # 回退到 wxauto 原生 SendMsg（含 _show 窗口激活）
            try:
                chat_obj.SendMsg(msg)
                return True
            except Exception as e2:
                self.logger.error(f"发送消息失败：{e2}", exc_info=True)
                return False

    def _fast_send(self, chat_obj: Any, msg: str) -> None:
        """快速发送：跳过 _show()，直接操作 editbox。

        wxauto ChatWnd.SendMsg 流程：_show → click → SetClipboardText → Ctrl+V → 验证 → Enter
        快速版流程：click → SetClipboardText → Ctrl+V → 验证 → Enter
        省掉 _show 的 4 个 Win32 API 调用。
        """
        import time as _time
        from wxauto.utils import SetClipboardText  # type: ignore

        editbox = chat_obj.editbox
        # 获取焦点（轻量级，仅 1 个 UI 调用，vs _show 的 4 个 Win32 API）
        if not editbox.HasKeyboardFocus:
            editbox.Click(simulateMove=False)

        # 粘贴消息并验证（与 wxauto 原生逻辑一致，但超时缩短为 5 秒）
        t0 = _time.time()
        while True:
            if _time.time() - t0 > 5:
                raise TimeoutError(f"快速发送粘贴超时：{msg[:20]}")
            SetClipboardText(msg)
            editbox.SendKeys('{Ctrl}v')
            if editbox.GetValuePattern().Value:
                break
        editbox.SendKeys('{Enter}')
