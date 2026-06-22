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
    """取 K 线, 缓存优先; 缓存不够时再补下载

    返回 df 已经按 [start..end] 过滤; 如果 fetch 失败回退到缓存,
    df 为缓存全集 (未经过滤), 由调用方按实际范围调整。
    """
    tf = timeframe or sys_config.get("backtest.default_timeframe", "4h")
    start = start or sys_config.get("backtest.start_date", "20240101")
    end = end or _resolve_end_date()

    cache = get_cache()
    fetcher = get_fetcher()

    cached_df = None
    cached_min = cached_max = None
    if use_cache:
        df = cache.read(symbol, tf)
        if df is not None and len(df) > 10:
            cached_df = df
            try:
                cached_min = _date_to_ymd(df["date"].min())
                cached_max = _date_to_ymd(df["date"].max())
            except Exception:
                pass
            filtered = _filter(df, start, end)
            cache_covers_range = (
                cached_min is not None and cached_max is not None
                and cached_min <= start and cached_max >= end
            )
            if not filtered.empty and cache_covers_range:
                log.debug(f"[cache HIT] {symbol} {tf} ({len(filtered)} rows from {len(df)} cached)")
                return filtered
            log.info(
                f"[cache STALE] {symbol} {tf}: cache [{cached_min}..{cached_max}] "
                f"不覆盖请求 [{start}..{end}]"
            )

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
        # 网络挂时不静默失败: 退回到已缓存的数据全集, 让上层按真实范围调整
        if cached_df is not None and not cached_df.empty:
            log.warning(f"[fetch FAIL→fallback cache] {symbol} {tf}: 返回缓存 {len(cached_df)} 行 (请求区间 {start}..{end}, 缓存 {cached_min}..{cached_max})")
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


def _date_to_ymd(value) -> str:
    return pd.to_datetime(value).strftime("%Y%m%d")


def _resolve_end_date() -> str:
    v = sys_config.get("backtest.end_date", "auto")
    if v == "auto":
        from datetime import datetime
        return datetime.now().strftime("%Y%m%d")
    return v
