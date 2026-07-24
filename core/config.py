# -*- coding: utf-8 -*-
"""配置管理模块。

负责加载/保存 config.yaml，提供默认值合并，供 GUI 与监控逻辑共用。
"""

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
    "send_interval": 3,
    "log_file": "logs/app.log",
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
        self.path = path
        self._config: Dict[str, Any] = {}
        self.load()

    def load(self) -> Dict[str, Any]:
        """从磁盘加载配置，与默认值合并。"""
        # 打包后：若 exe 同级无 config.yaml，从 _internal 拷贝初始配置
        if not os.path.exists(self.path):
            self._ensure_initial_config()
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
            self._config = _deep_merge(DEFAULT_CONFIG, loaded)
        else:
            # 仍不存在则写入默认配置
            self._config = dict(DEFAULT_CONFIG)
            self.save()
        return self._config

    def _ensure_initial_config(self) -> None:
        """打包后首次运行：从 _internal 拷贝预置 config.yaml 到 exe 同级。"""
        from core.paths import is_frozen, resource_root
        if not is_frozen():
            return
        bundled = os.path.join(resource_root(), "config.yaml")
        if os.path.exists(bundled):
            import shutil
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            shutil.copy2(bundled, self.path)

    def save(self, config: Optional[Dict[str, Any]] = None) -> None:
        """保存配置到磁盘。传入 config 则替换当前配置后保存。"""
        if config is not None:
            self._config = config
        with open(self.path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self._config, f, allow_unicode=True, sort_keys=False)

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
