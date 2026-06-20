"""回测相关 API"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional

from backend.services.backtest_service import (
    backtest_single, scan_pool, filter_symbols, get_kline_data,
)
from quant_core.settings import C


router = APIRouter(prefix="/api/backtest", tags=["backtest"])


class SingleRequest(BaseModel):
    symbol: str
    strategy: str
    timeframe: Optional[str] = None
    ma_short: int = 7
    ma_long: int = 25
    top_n: int = 3
    hold: int = 12
    lookback: int = 24
    rsi_period: int = 14
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    initial_capital: Optional[float] = None
    commission: Optional[float] = None
    leverage: float = 1
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class ScanRequest(BaseModel):
    strategy: str
    symbols: Optional[List[str]] = None
    timeframe: Optional[str] = None
    ma_short: int = 7
    ma_long: int = 25
    top_n: int = 3
    hold: int = 12
    lookback: int = 24
    rsi_period: int = 14
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    initial_capital: Optional[float] = None
    commission: Optional[float] = None
    leverage: float = 1
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class FilterRequest(BaseModel):
    strategy: str = "ma_cross"
    symbols: Optional[List[str]] = None
    timeframe: str = "1d"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    min_return: float = -1.0
    max_return: float = 100.0
    min_price: float = 0
    max_price: float = 1e12
    min_sharpe: float = -10


@router.post("/single")
def single(req: SingleRequest):
    try:
        p = req.dict()
        result = backtest_single(
            symbol=req.symbol, strategy_id=req.strategy,
            timeframe=req.timeframe, params=p,
            start=req.start_date, end=req.end_date,
            initial_capital=req.initial_capital, commission=req.commission,
            leverage=req.leverage,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scan")
def scan(req: ScanRequest):
    try:
        symbols = req.symbols or C.active_symbols()
        p = req.dict()
        result = scan_pool(
            strategy_id=req.strategy, symbols=symbols,
            timeframe=req.timeframe, params=p,
            start=req.start_date, end=req.end_date,
            initial_capital=req.initial_capital, commission=req.commission,
            leverage=req.leverage,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/filter")
def filter_stocks(req: FilterRequest):
    try:
        result = filter_symbols({**req.dict(), "symbols": req.symbols or C.active_symbols()})
        return result
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kline/{symbol}")
def kline(symbol: str, timeframe: str = "4h", start: str = None, end: str = None):
    try:
        return get_kline_data(symbol, timeframe, start, end)
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))