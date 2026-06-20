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


@router.get("/test-connection")
def test_connection():
    return data_service.test_connectivity()


@router.post("/fetch")
def fetch(symbol: str, timeframe: str = "4h",
          start: str = "20240101", end: str = "20250601"):
    return data_service.fetch_one(symbol, timeframe, start, end)