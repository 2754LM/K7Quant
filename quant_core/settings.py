"""配置加载器 (单例模式)"""
import os
import threading
from pathlib import Path
from datetime import datetime
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
SETTINGS_PATH = CONFIG_DIR / "settings.yaml"
SYMBOLS_PATH = CONFIG_DIR / "symbols.yaml"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"

DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()
_settings_cache: dict = {}
_symbols_cache: dict = {}


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save_yaml(path: Path, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def load_settings(reload: bool = False) -> dict:
    global _settings_cache
    with _lock:
        if reload or not _settings_cache:
            _settings_cache = _load_yaml(SETTINGS_PATH)
        return _settings_cache


def save_settings(new_data: dict) -> dict:
    """覆盖式保存整个 settings.yaml"""
    global _settings_cache
    with _lock:
        _save_yaml(SETTINGS_PATH, new_data)
        _settings_cache = new_data
        return new_data


def update_settings(patch: dict) -> dict:
    """局部更新 settings.yaml"""
    global _settings_cache
    with _lock:
        # 注意: 不能直接调 load_settings()，会重入死锁
        if not _settings_cache:
            _settings_cache = _load_yaml(SETTINGS_PATH)
        current = _settings_cache
        _deep_update(current, patch)
        _save_yaml(SETTINGS_PATH, current)
        # 重新从文件加载，确保返回的数据是磁盘上的最新状态（无残留 key）
        _settings_cache = _load_yaml(SETTINGS_PATH)
        return _settings_cache


def load_symbols(reload: bool = False) -> dict:
    global _symbols_cache
    with _lock:
        if reload or not _symbols_cache:
            _symbols_cache = _load_yaml(SYMBOLS_PATH)
        return _symbols_cache


def save_symbols(data: dict) -> dict:
    global _symbols_cache
    with _lock:
        _save_yaml(SYMBOLS_PATH, data)
        _symbols_cache = data
        return data


def _deep_update(base: dict, patch: dict):
    """支持点路径: {'backtest.initial_capital': 20000}"""
    for k, v in patch.items():
        if "." in k:
            parts = k.split(".")
            cur = base
            for p in parts[:-1]:
                if p not in cur or not isinstance(cur[p], dict):
                    cur[p] = {}
                cur = cur[p]
            cur[parts[-1]] = v
        elif isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v


# ===== 便捷访问 =====

class C:
    """常量访问封装"""
    DATA_DIR = DATA_DIR
    OUTPUT_DIR = OUTPUT_DIR

    @staticmethod
    def get(path: str, default: Any = None) -> Any:
        """点路径取值: C.get('backtest.initial_capital')"""
        s = load_settings()
        cur: Any = s
        for k in path.split("."):
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                return default
        return cur

    @staticmethod
    def api_base() -> str:
        return C.get("data_source.api_base", "https://api.binance.com")

    @staticmethod
    def initial_capital() -> float:
        return float(C.get("backtest.initial_capital", 10000))

    @staticmethod
    def commission() -> float:
        return float(C.get("backtest.commission", 0.0004))

    @staticmethod
    def start_date() -> str:
        v = C.get("backtest.start_date", "20240101")
        if v == "auto":
            return "20240101"
        return str(v)

    @staticmethod
    def end_date() -> str:
        v = C.get("backtest.end_date", "auto")
        if v == "auto":
            return datetime.now().strftime("%Y%m%d")
        return str(v)

    @staticmethod
    def timeframes() -> list:
        return C.get("timeframes", ["1d"])

    @staticmethod
    def active_symbols() -> list:
        return C.get("active_symbols", ["BTCUSDT"])

    @staticmethod
    def default_timeframe() -> str:
        return C.get("backtest.default_timeframe", "4h")

    @staticmethod
    def strategy_params(strategy: str) -> dict:
        return C.get(f"strategy_defaults.{strategy}", {})


# 启动时建目录
for d in [C.DATA_DIR, C.OUTPUT_DIR]:
    d.mkdir(parents=True, exist_ok=True)