"""config - 配置中心

所有"配置相关"的东西都集中在这里:
- paths.py:   文件/目录路径常量
- settings.py: YAML 配置加载/保存 (load_config / get / put / DEFAULTS)
- secrets.py: 敏感凭据 (Binance demo API)
- constants.py: 业务常量 (Binance 周期白名单, 默认币种, 内置分类等)

用法:
    from backend.config import config as sys_config
    from backend.config.constants import BINANCE_TIMEFRAMES
    from backend.config.paths import DATA_DIR, DB_PATH
    from backend.config.secrets import get_demo_credentials
"""
from . import settings as config
from . import secrets
from .paths import ROOT, DATA_DIR, LOGS_DIR, CACHE_DIR, EXPORT_DIR, DB_PATH, CONFIG_PATH
from .constants import (
    BINANCE_TIMEFRAMES, BINANCE_TIMEFRAMES_SET, is_valid_timeframe,
    DEFAULT_SYMBOLS,
    DEFAULT_BACKTEST_START_DATE, DEFAULT_BACKTEST_TIMEFRAME,
    DEFAULT_BACKTEST_CAPITAL, DEFAULT_COMMISSION_RATE, DEFAULT_SLIPPAGE,
    LIVE_TF_SECONDS, LIVE_DEFAULT_TIMEFRAME, LIVE_LOOKBACK_BARS,
    LIVE_SLTP_TICK_SECONDS,
    API_LOG_TAIL_DEFAULT_LINES, API_LOG_TAIL_MAX_LINES,
    API_BACKTEST_TIMEOUT_SECONDS,
)


__all__ = [
    "config", "secrets",
    "ROOT", "DATA_DIR", "LOGS_DIR", "CACHE_DIR", "EXPORT_DIR", "DB_PATH", "CONFIG_PATH",
    "BINANCE_TIMEFRAMES", "BINANCE_TIMEFRAMES_SET", "is_valid_timeframe",
    "DEFAULT_SYMBOLS",
    "DEFAULT_BACKTEST_START_DATE", "DEFAULT_BACKTEST_TIMEFRAME",
    "DEFAULT_BACKTEST_CAPITAL", "DEFAULT_COMMISSION_RATE", "DEFAULT_SLIPPAGE",
    "LIVE_TF_SECONDS", "LIVE_DEFAULT_TIMEFRAME", "LIVE_LOOKBACK_BARS",
    "LIVE_SLTP_TICK_SECONDS",
    "API_LOG_TAIL_DEFAULT_LINES", "API_LOG_TAIL_MAX_LINES",
    "API_BACKTEST_TIMEOUT_SECONDS",
]