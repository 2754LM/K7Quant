"""数据业务: 缓存查询 + 清理 + 交易对列表"""
import os
from typing import List

from backend.data.cache import get_cache
from backend.data.fetcher import get_fetcher
from backend.core import config as sys_config


def list_cache() -> dict:
    return get_cache().stats()


def clear_cache(timeframe: str = None, symbol: str = None):
    get_cache().clear(timeframe, symbol)
    return get_cache().stats()


def get_symbols() -> List[dict]:
    """获取缓存里的所有交易对 (从 Binance 拉)"""
    try:
        all_syms = get_fetcher().list_usdt_symbols()
        return [{"symbol": s, "exchange": "binance"} for s in all_syms[:200]]
    except Exception:
        return []


def test_connectivity() -> dict:
    """测试 Binance 连接 + 返回诊断信息"""
    fetcher = get_fetcher()
    return fetcher.test_connectivity()


def fetch_one(symbol: str, timeframe: str, start: str, end: str) -> dict:
    """手动触发下载"""
    from backend.data.access import get_kline
    df = get_kline(symbol, timeframe, start, end, use_cache=True)
    if df.empty:
        return {"error": f"无法下载 {symbol} {timeframe}"}
    return {"ok": True, "rows": len(df),
            "start": str(df["date"].iloc[0]), "end": str(df["date"].iloc[-1])}