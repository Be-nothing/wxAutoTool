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
        """断开连接（仅释放引用，不关闭微信窗口）。"""
        self.wx = None
        self.logger.info("微信连接已断开")

    def add_listen(self, who: str) -> bool:
        """添加监听对象（群聊或私聊名称需与微信显示完全一致）。"""
        if not self.connected:
            return False
        try:
            self.wx.AddListenChat(who=who)
            self.logger.info(f"已添加监听：{who}")
            return True
        except Exception as e:
            self.logger.error(f"添加监听 '{who}' 失败：{e}")
            return False

    def get_listen_messages(self) -> Dict[Any, List[Any]]:
        """获取监听对象的新消息，返回 {聊天对象: [消息列表]}。"""
        if not self.connected:
            return {}
        try:
            return self.wx.GetListenMessage() or {}
        except Exception as e:
            self.logger.error(f"获取监听消息失败：{e}", exc_info=True)
            return {}

    def send_msg(self, chat_obj: Any, msg: str) -> bool:
        """向指定聊天对象发送消息。"""
        if not self.connected:
            return False
        try:
            chat_obj.SendMsg(msg)
            return True
        except Exception as e:
            self.logger.error(f"发送消息失败：{e}", exc_info=True)
            return False
