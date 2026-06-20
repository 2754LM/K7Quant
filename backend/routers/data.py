"""数据管理 API"""
from fastapi import APIRouter, HTTPException, Query

from backend.services.data_service import list_cache, clear_cache


router = APIRouter(prefix="/api/data", tags=["data"])


@router.get("")
def list_data():
    return list_cache()


@router.delete("")
def clear_data(timeframe: str = Query(None), symbol: str = Query(None)):
    return clear_cache(timeframe, symbol)