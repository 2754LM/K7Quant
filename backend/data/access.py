"""数据访问层: 缓存优先, 缺失时下载"""
import os
import time
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

from backend.data.fetcher import get_fetcher
from backend.data.cache import get_cache
from backend.core import config as sys_config
from backend.core.logger import log


_FETCH_WORKERS = min(8, max(2, (os.cpu_count() or 4)))


def get_kline(symbol: str, timeframe: str = None,
              start: str = None, end: str = None,
              use_cache: bool = True) -> pd.DataFrame:
    """取 K 线, 缓存优先; 缓存不够时再补下载"""
    tf = timeframe or sys_config.get("backtest.default_timeframe", "4h")
    start = start or sys_config.get("backtest.start_date", "20240101")
    end = end or _resolve_end_date()

    cache = get_cache()
    fetcher = get_fetcher()

    cached_df = None
    if use_cache:
        df = cache.read(symbol, tf)
        if df is not None and len(df) > 10:
            cached_df = df
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
        # 网络挂时不静默失败: 退回到已缓存的数据 (即使区间不完全覆盖), 仍比无数据好
        if cached_df is not None and not cached_df.empty:
            log.warning(f"[fetch FAIL→fallback cache] {symbol} {tf}: 返回缓存 {len(cached_df)} 行 (区间可能不完整)")
            return cached_df
        return pd.DataFrame()


def get_many(symbols: list, timeframe: str = None,
             start: str = None, end: str = None) -> dict:
    """批量取 K 线 (并发下载, 缓存命中走快路径)"""
    if not symbols:
        return {}
    if len(symbols) <= 2:
        # 少量时顺序更快, 避免线程开销
        out = {s: get_kline(s, timeframe, start, end) for s in symbols}
    else:
        out = {}
        with ThreadPoolExecutor(max_workers=_FETCH_WORKERS) as ex:
            futures = {ex.submit(get_kline, s, timeframe, start, end): s for s in symbols}
            for fut in futures:
                df = fut.result()
                if df is not None and not df.empty:
                    out[futures[fut]] = df
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