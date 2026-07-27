# -*- coding: utf-8 -*-
"""微信自动检测助手 - 程序入口。

负责：libs 路径引导、日志初始化、启动 PySide6 GUI。
"""

import os
import sys

# === 防止 windowed 模式（console=False）下子进程弹出 CMD 黑窗 ===
# 必须在导入任何可能调用 subprocess 的库之前执行。
# wxauto/uiautomation/win32 等依赖内部可能用 subprocess 调用外部命令，
# 默认会弹出 CMD 窗口。这里 patch subprocess.Popen 强制加 CREATE_NO_WINDOW。
try:
    import subprocess as _subprocess
    _CREATE_NO_WINDOW = 0x08000000
    _orig_popen = _subprocess.Popen

    def _patched_popen(*args, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | _CREATE_NO_WINDOW
        return _orig_popen(*args, **kwargs)

    _subprocess.Popen = _patched_popen
except Exception:
    pass

# windowed 模式下 sys.stdout/sys.stderr 可能为 None，
# 某些库（如 logging.StreamHandler）写入 None 会抛异常，重定向到 devnull。
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

# === patch os.system 阻止 wxauto/color.py 的 os.system('') 弹 CMD 窗口 ===
# wxauto/color.py 第 5 行调用 os.system('') 启用终端 ANSI 颜色，
# 但在 windowed GUI 应用中完全不需要，且会弹出 CMD 黑窗一闪而过。
# 这里替换 os.system：空命令直接跳过，非空命令用 subprocess 静默执行。
import os as _os
_orig_system = _os.system


def _patched_system(cmd):
    if not cmd or not str(cmd).strip():
        return 0  # 空命令直接返回，不创建任何进程
    # 非空命令用 subprocess 静默执行（CREATE_NO_WINDOW 已在上方 patch）
    import subprocess as _sp
    return _sp.call(str(cmd), shell=True)


_os.system = _patched_system

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _bootstrap_libs() -> None:
    """libs/ 兜底引导：仅当系统未安装依赖时才使用 libs。

    - pywin32_system32 DLL 目录无条件加入 PATH（pywin32 运行所需）
    - libs 子目录追加到 sys.path 末尾（不抢占系统已安装的包，
      避免 libs 中与当前 Python 版本不匹配的 C 扩展冲突）
    """
    libs_dir = os.path.join(BASE_DIR, "libs")
    if not os.path.isdir(libs_dir):
        return
    # pywin32 DLL 目录加入 PATH（无条件，DLL 查找独立于 sys.path）
    pywin32_dll = os.path.join(libs_dir, "pywin32_system32")
    if os.path.isdir(pywin32_dll):
        os.environ["PATH"] = pywin32_dll + os.pathsep + os.environ.get("PATH", "")
    # libs 子目录追加到末尾，作为依赖兜底
    for sub in ("", "win32", os.path.join("win32", "lib"), "pythonwin"):
        path = os.path.join(libs_dir, sub) if sub else libs_dir
        if os.path.isdir(path) and path not in sys.path:
            sys.path.append(path)
    try:
        import pywin32_bootstrap  # type: ignore
    except Exception:
        pass


def _check_single_instance() -> bool:
    """单实例锁：通过 Windows 命名互斥体确保只有一个实例运行。

    返回 True 表示当前是首个实例，False 表示已有实例运行。
    互斥体生命周期与进程绑定，进程退出自动释放，无需手动清理。

    互斥体名称按 exe 名区分，允许不同版本（UIA版/回复助手）同时运行。
    """
    try:
        import ctypes
        # 根据 exe 名决定互斥体名称，实现多版本隔离
        exe_name = os.path.basename(sys.executable) if getattr(sys, "frozen", False) else "dev"
        if "_uia" in exe_name.lower():
            mutex_name = "Global\\wxAutoTool_uia_SingleInstance"
        elif "回复" in exe_name:
            mutex_name = "Global\\wxAutoTool_reply_SingleInstance"
        else:
            mutex_name = "Global\\wxAutoTool_SingleInstance"
        # CreateMutex: 返回句柄；若同名互斥体已存在，GetLastError 返回 ERROR_ALREADY_EXISTS (183)
        ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
        return ctypes.windll.kernel32.GetLastError() != 183
    except Exception:
        # 非 Windows 或 ctypes 不可用，放行
        return True


def main() -> None:
    # 全程异常捕获：console=False 模式下任何未捕获异常都会让 exe 静默退出
    try:
        # 路径引导（必须在导入 core/gui 之前）
        _bootstrap_libs()
        # 高 DPI 支持（PySide6 默认开启，显式设置以兼容旧版）
        os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

        # 单实例检查：防止多开导致 COM 冲突和消息重复回复
        if not _check_single_instance():
            try:
                from PySide6.QtWidgets import QApplication, QMessageBox
                app = QApplication.instance() or QApplication(sys.argv if sys.argv else ["wxAutoTool"])
                QMessageBox.critical(
                    None, "提示",
                    "程序已在运行，请勿重复启动。\n\n"
                    "如需重启，请先退出当前实例（托盘右键 → 退出程序）。"
                )
            except Exception:
                pass
            return

        from gui.main_window import run
        run()
    except Exception as e:
        import traceback
        # 写到 exe 同级目录（确保可写）
        log_path = os.path.join(os.path.dirname(sys.executable), "crash.log")
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("主程序启动失败：\n")
                f.write(str(e) + "\n\n")
                traceback.print_exc(file=f)
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
