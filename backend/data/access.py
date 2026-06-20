"""数据访问层: 缓存优先, 缺失时下载"""
import time
import pandas as pd

from backend.data.fetcher import get_fetcher
from backend.data.cache import get_cache
from backend.core import config as sys_config
from backend.core.logger import log


def get_kline(symbol: str, timeframe: str = None,
              start: str = None, end: str = None,
              use_cache: bool = True) -> pd.DataFrame:
    """取 K 线, 缓存优先"""
    tf = timeframe or sys_config.get("backtest.default_timeframe", "4h")
    start = start or sys_config.get("backtest.start_date", "20240101")
    end = end or _resolve_end_date()

    cache = get_cache()
    fetcher = get_fetcher()

    if use_cache:
        df = cache.read(symbol, tf)
        if df is not None and len(df) > 10:
            return _filter(df, start, end)

    try:
        df = fetcher.fetch(symbol, tf, start, end)
        if not df.empty:
            cache.write(symbol, tf, df)
            time.sleep(0.25)
        return _filter(df, start, end)
    except Exception as e:
        log.error(f"下载 {symbol} {tf} 失败: {e}")
        return pd.DataFrame()


def get_many(symbols: list, timeframe: str = None,
             start: str = None, end: str = None) -> dict:
    """批量取 K 线"""
    out = {}
    for s in symbols:
        df = get_kline(s, timeframe, start, end)
        if not df.empty:
            out[s] = df
    return out


def get_trading_symbols() -> list:
    """获取 Binance 全部 USDT 交易对"""
    return get_fetcher().list_usdt_symbols()


def _filter(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    if df.empty:
        return df
    return df[(df["date"] >= start) & (df["date"] <= end)].reset_index(drop=True)


def _resolve_end_date() -> str:
    v = sys_config.get("backtest.end_date", "auto")
    if v == "auto":
        from datetime import datetime
        return datetime.now().strftime("%Y%m%d")
    return v