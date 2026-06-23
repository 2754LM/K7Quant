"""数据 API"""
from fastapi import APIRouter, Query

from backend.services import data_service


router = APIRouter()


@router.get("/cache")
def list_cache():
    return data_service.list_cache()


@router.delete("/cache")
def clear_cache(timeframe: str = Query(None), symbol: str = Query(None)):
    return data_service.clear_cache(timeframe, symbol)


@router.get("/exchange-symbols")
def exchange_symbols():
    return {"symbols": data_service.get_symbols()}


@router.get("/exchange-info/{symbol}")
def exchange_info(symbol: str):
    """单个币种的交易所元信息 (filters, permissions, 状态) - 用于币种详情页"""
    from backend.data.fetcher import get_fetcher
    return get_fetcher().get_symbol_info(symbol)


@router.get("/timeframes")
def list_timeframes():
    """Binance 支持的 timeframe 白名单 (前端 UI 用)"""
    from backend.data.fetcher import BINANCE_TIMEFRAMES
    return {"timeframes": sorted(BINANCE_TIMEFRAMES)}


@router.get("/test-connection")
def test_connection():
    # 包一层 binance, 与前端 DataPanel 读取的 res.data.binance 对齐
    return {"binance": data_service.test_connectivity()}


@router.post("/fetch")
def fetch(symbol: str, timeframe: str = "4h",
          start: str = "20240101", end: str = "20250601"):
    return data_service.fetch_one(symbol, timeframe, start, end)