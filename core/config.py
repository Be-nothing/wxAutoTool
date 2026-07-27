# -*- coding: utf-8 -*-
"""配置管理模块。

负责加载/保存 config.yaml，提供默认值合并，供 GUI 与监控逻辑共用。
"""

import logging
import os
from typing import Any, Dict, Optional

import yaml

from core.paths import config_path

# 配置文件路径（打包后为 exe 同级，开发时为项目根）
DEFAULT_CONFIG_PATH = config_path()

# 默认配置：融合需求示例字段 + 现有 listeners 富结构
DEFAULT_CONFIG: Dict[str, Any] = {
    "wechat": {"target": ""},
    "monitor": {"interval": 2},
    "action": {"auto_reply": False},
    "listeners": [],
    "ignore_self": True,
    "ignore_system": True,
    "send_interval": 1.5,
    "log_file": "logs/app.log",
    "theme": "system",  # 主题：system(跟随系统) / light(浅色) / dark(深色)
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """递归合并：override 覆盖 base，未出现的键保留 base 默认值。"""
    result = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class ConfigManager:
    """配置管理器：加载、保存、读写配置项。"""

    def __init__(self, path: str = DEFAULT_CONFIG_PATH) -> None:
        self._logger = logging.getLogger("wechat.config")
        original_path = path
        self.path = self._ensure_writable_path(path)
        # 记录最终配置路径，便于排查"配置丢失"类问题
        if self.path != original_path:
            self._logger.warning(
                f"配置文件路径回退：{original_path} → {self.path}（原路径不可写）"
            )
        self._logger.info(f"配置文件路径：{self.path}")
        self._config: Dict[str, Any] = {}
        self.load()

    def _ensure_writable_path(self, path: str) -> str:
        """确保配置路径可写，不可写则回退到 exe 同级目录。

        使用 创建+写入+删除 三步测试，避免仅检查目录可写但文件不可写的情况
        （某些杀软会拦截 .yaml 文件创建但允许目录写）。
        """
        try:
            dirpath = os.path.dirname(path)
            if dirpath:
                os.makedirs(dirpath, exist_ok=True)
            # 用 .write_test 做完整可写测试（创建+删除），不污染 config.yaml
            test_file = path + ".write_test"
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(test_file)
            return path
        except Exception as e:
            # 回退到 exe 同级目录
            from core.paths import is_frozen, app_root
            if is_frozen():
                fallback = os.path.join(app_root(), "config.yaml")
                # 回退路径也需验证可写，避免再次失败
                try:
                    os.makedirs(app_root(), exist_ok=True)
                    with open(fallback + ".write_test", "w") as f:
                        f.write("ok")
                    os.remove(fallback + ".write_test")
                except Exception:
                    pass  # 兜底失败也只能用这个路径
                return fallback
            return path

    def load(self) -> Dict[str, Any]:
        """从磁盘加载配置，与默认值合并。配置损坏时自动从 .bak 恢复。"""
        # 打包后：若配置文件不存在，从 _internal 拷贝初始配置
        if not os.path.exists(self.path):
            self._ensure_initial_config()
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = yaml.safe_load(f) or {}
                self._config = _deep_merge(DEFAULT_CONFIG, loaded)
            except (yaml.YAMLError, OSError) as e:
                self._logger.warning(f"配置文件损坏：{e}，尝试从备份恢复")
                if self.restore_backup():
                    return self._config
                # 无备份或恢复失败：用默认配置
                self._logger.warning("无可用备份，使用默认配置")
                self._config = dict(DEFAULT_CONFIG)
                self.save()
        else:
            # 仍不存在则写入默认配置
            self._config = dict(DEFAULT_CONFIG)
            self.save()
        return self._config

    def _ensure_initial_config(self) -> None:
        """打包后首次运行：从 _internal 拷贝预置 config.yaml 到用户数据目录。"""
        from core.paths import is_frozen, resource_root
        if not is_frozen():
            return
        bundled = os.path.join(resource_root(), "config.yaml")
        if os.path.exists(bundled):
            import shutil
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                shutil.copy2(bundled, self.path)
            except Exception:
                pass  # 路径不可写时静默失败，load() 会回退到默认配置

    def save(self, config: Optional[Dict[str, Any]] = None) -> None:
        """保存配置到磁盘（原子写入 + .bak 备份）。

        原子写入流程：写临时文件 → 备份旧文件为 .bak → 重命名临时文件为目标文件。
        避免写入中途崩溃导致配置文件损坏成半截 YAML。
        """
        if config is not None:
            self._config = config
        tmp_path = self.path + ".tmp"
        bak_path = self.path + ".bak"
        try:
            # 1. 写入临时文件
            with open(tmp_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(self._config, f, allow_unicode=True, sort_keys=False)
            # 2. 备份旧配置（若存在）
            if os.path.exists(self.path):
                try:
                    # 删除旧 .bak，重命名当前配置为 .bak
                    if os.path.exists(bak_path):
                        os.remove(bak_path)
                    os.rename(self.path, bak_path)
                except Exception:
                    pass  # 备份失败不影响主流程
            # 3. 临时文件重命名为目标文件（原子操作）
            os.rename(tmp_path, self.path)
            self._logger.info(f"配置已保存到：{self.path}")
        except Exception:
            # 异常时清理临时文件
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            raise

    def restore_backup(self) -> bool:
        """从 .bak 恢复配置（配置损坏时的兜底）。成功返回 True。"""
        bak_path = self.path + ".bak"
        if not os.path.exists(bak_path):
            return False
        try:
            import shutil
            shutil.copy2(bak_path, self.path)
            self.load()
            self._logger.info(f"已从备份恢复配置：{bak_path}")
            return True
        except Exception as e:
            self._logger.error(f"恢复备份失败：{e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """读取顶层配置项。"""
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """设置顶层配置项（仅内存，需调用 save() 落盘）。"""
        self._config[key] = value

    @property
    def config(self) -> Dict[str, Any]:
        """返回完整配置字典。"""
        return self._config


def load_config(path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """快捷函数：加载并返回配置字典。"""
    return ConfigManager(path).config


def save_config(config: Dict[str, Any], path: str = DEFAULT_CONFIG_PATH) -> None:
    """快捷函数：保存配置字典到磁盘。"""
    ConfigManager(path).save(config)
