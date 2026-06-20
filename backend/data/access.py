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
    """取 K 线, 缓存优先; 缓存不够时再补下载"""
    tf = timeframe or sys_config.get("backtest.default_timeframe", "4h")
    start = start or sys_config.get("backtest.start_date", "20240101")
    end = end or _resolve_end_date()

    cache = get_cache()
    fetcher = get_fetcher()

    if use_cache:
        df = cache.read(symbol, tf)
        if df is not None and len(df) > 10:
            filtered = _filter(df, start, end)
            if not filtered.empty:
                log.debug(f"[cache HIT] {symbol} {tf} ({len(filtered)} rows from {len(df)} cached)")
                return filtered
            # 缓存有数据但过滤为空 -> 看下请求区间是否完全在缓存外
            try:
                cache_min = str(df["date"].min())
                cache_max = str(df["date"].max())
            except Exception:
                cache_min = cache_max = ""
            log.info(f"[cache STALE] {symbol} {tf}: cache [{cache_min}..{cache_max}] 不覆盖请求 [{start}..{end}]")

    try:
        log.info(f"[fetch] {symbol} {tf} range={start}..{end}")
        df = fetcher.fetch(symbol, tf, start, end)
        if not df.empty:
            cache.write(symbol, tf, df)
            log.info(f"[fetch OK] {symbol} {tf} {len(df)} rows")
            time.sleep(0.25)
        else:
            log.warning(f"[fetch EMPTY] {symbol} {tf}")
        return _filter(df, start, end)
    except Exception as e:
        log.error(f"[fetch FAIL] {symbol} {tf}: {e}")
        return pd.DataFrame()


def get_many(symbols: list, timeframe: str = None,
             start: str = None, end: str = None) -> dict:
    """批量取 K 线"""
    out = {}
    for s in symbols:
        df = get_kline(s, timeframe, start, end)
        if not df.empty:
            out[s] = df
    log.info(f"[get_many] 命中 {len(out)}/{len(symbols)} ({timeframe})")
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