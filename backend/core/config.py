"""系统配置: 启动时从 settings.yaml 加载, 写回 DB"""
import os
from pathlib import Path
from typing import Any
import yaml


CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.yaml"

# 默认配置
DEFAULTS = {
    "server": {
        "host": "127.0.0.1",
        "port": 8765,
        "auto_open_browser": True,
        "log_level": "INFO",
    },
    "data_source": {
        "exchange": "binance",
        "api_base": "https://api.binance.com",
        "timeout": 20,
        "retries": 3,
        # 代理设置 (国内用户必填)
        "proxy": {
            "enabled": False,
            "http": "",        # 例: "http://127.0.0.1:7890"
            "https": "",       # 例: "http://127.0.0.1:7890"
        },
    },
    "backtest": {
        "initial_capital": 10000.0,
        "commission_rate": 0.0004,    # 手续费率 (单边)
        "slippage": 0.0005,           # 滑点 (估算)
        "position_mode": "all_in",    # all_in / fixed_amount / ratio
        "fixed_amount": 1000,         # 当 position_mode=fixed_amount
        "leverage": 1,
        "default_timeframe": "4h",
        "start_date": "20240101",
        "end_date": "auto",
    },
    "ui": {
        "theme": "dark",              # dark / light
        "show_help_tooltips": True,   # 全局问号提示开关
        "default_page": "dashboard",
    },
    "trading": {
        "enabled": False,             # 模拟/实盘开关
        "mode": "simulation",         # simulation / live
        "max_position_pct": 0.3,      # 单币种最大仓位
        "max_total_pct": 0.95,        # 最大总仓位
        "stop_loss_pct": 0.05,        # 止损
        "take_profit_pct": 0.15,      # 止盈
    },
}


_cached: dict = {}


def load_config(path: Path = None) -> dict:
    """加载配置: 文件覆盖默认, 全局缓存"""
    global _cached
    if _cached:
        return _cached

    cfg = {k: dict(v) if isinstance(v, dict) else v
           for k, v in DEFAULTS.items()}

    p = path or CONFIG_PATH
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
        _deep_merge(cfg, user_cfg)
    _cached = cfg
    return cfg


def save_config(cfg: dict, path: Path = None):
    """保存到 YAML (后端首次启动时)"""
    p = path or CONFIG_PATH
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False,
                       default_flow_style=False)
    global _cached
    _cached = cfg


def get(path: str, default: Any = None) -> Any:
    """点路径取值: get('backtest.commission_rate')"""
    cfg = load_config()
    cur: Any = cfg
    for k in path.split("."):
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur


def _deep_merge(base: dict, patch: dict):
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v