"""系统配置: 启动时从 config.yaml 加载, 文件覆盖默认值后全局缓存"""
import os
import copy
from pathlib import Path
from typing import Any
import yaml


CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.yaml"


def _binance_timeframes():
    """从 fetcher 拿 Binance 白名单 (作为单一 source of truth)
    按 Binance 官方顺序 (秒/分/时/日/周/月), 不是字母序
    """
    # 延后导入避免循环 (config.py 被 fetcher.py 反向引用)
    from backend.data.fetcher import BINANCE_TIMEFRAMES
    return list(BINANCE_TIMEFRAMES)


# 默认配置 (timeframes 字段延后填充, 避免循环导入)
DEFAULTS_TEMPLATE = {
    "server": {
        "host": "127.0.0.1",
        "port": 8765,
        "auto_open_browser": True,
        "log_level": "INFO",
    },
    "data_source": {
        "exchange": "binance",
        "api_base": "https://api.binance.com",
        # 模拟盘 (Demo Mode) REST 基址; 鉴权方式与正式盘相同
        "demo_api_base": "https://demo-api.binance.com",
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
        "rebalance_bars": 1,          # 调仓频率: 每 N 根 K 线才换一次仓
        "default_timeframe": "4h",
        "start_date": "20240101",
        "end_date": "auto",
    },
    # 前端 UI 时间框架下拉 (从 Binance 白名单派生, 单一来源)
    "timeframes": None,  # ← 由 _build_defaults() 动态填充
    "ui": {
        "theme": "dark",              # dark / light
        "show_help_tooltips": True,   # 全局问号提示开关
        "default_page": "dashboard",
    },
    "trading": {
        "enabled": False,             # 模拟/实盘开关
        "mode": "simulation",         # simulation / live
        "recv_window": 5000,          # 签名请求有效窗口 (ms), 规避时间戳误差
        "max_position_pct": 0.3,      # 单币种最大仓位
        "max_total_pct": 0.95,        # 最大总仓位
        "stop_loss_pct": 0.05,        # 止损
        "take_profit_pct": 0.15,      # 止盈
    },
}


# DEFAULTS 用模板 + 懒填充 timeframes 字段 (避免模块加载时 config<->fetcher 循环)
DEFAULTS = copy.deepcopy(DEFAULTS_TEMPLATE)
DEFAULTS["timeframes"] = None  # 占位, 首次访问时填充


def _ensure_defaults_timeframes():
    """懒填充 DEFAULTS.timeframes (首次 get("timeframes") 时调用, 此时 fetcher 已加载)"""
    if DEFAULTS.get("timeframes") is None:
        DEFAULTS["timeframes"] = _binance_timeframes()


_cached: dict = {}


def load_config(path: Path = None) -> dict:
    """加载配置: 文件覆盖默认, 全局缓存"""
    global _cached
    if _cached:
        return _cached

    # 懒填充 timeframes (Binance 白名单, 后端唯一 source of truth)
    _ensure_defaults_timeframes()
    cfg = copy.deepcopy(DEFAULTS)

    p = path or CONFIG_PATH
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
        _deep_merge(cfg, user_cfg)
    # 兜底: 如果 cfg.timeframes 仍为 None (用户清空了), 用白名单
    if cfg.get("timeframes") is None:
        cfg["timeframes"] = _binance_timeframes()
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
    # 懒填充 timeframes (Binance 白名单, 后端唯一 source of truth)
    if path == "timeframes" or path.startswith("timeframes."):
        _ensure_defaults_timeframes()
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