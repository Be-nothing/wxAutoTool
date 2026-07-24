# -*- coding: utf-8 -*-
"""微信自动检测助手 - 程序入口。

负责：libs 路径引导、日志初始化、启动 PySide6 GUI。
"""

import os
import sys

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


def main() -> None:
    # 全程异常捕获：console=False 模式下任何未捕获异常都会让 exe 静默退出
    try:
        # 路径引导（必须在导入 core/gui 之前）
        _bootstrap_libs()
        # 高 DPI 支持（PySide6 默认开启，显式设置以兼容旧版）
        os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
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
