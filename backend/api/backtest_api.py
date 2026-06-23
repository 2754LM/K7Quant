"""回测 API"""
import time as _time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from backend.services import backtest_service
from backend.core.logger import log


router = APIRouter()


class BacktestRequest(BaseModel):
    strategy_id: int
    symbol: str = "BTCUSDT"
    symbols: Optional[List[str]] = None
    weights: Optional[dict] = None       # 自定义权重: {symbol: weight}, 留空 = 等权
    timeframe: Optional[str] = None
    ma_short: int = 7
    ma_long: int = 25
    rsi_period: int = 14
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    lookback: int = 20
    top_n: int = 3
    hold: int = 12
    break_period: int = 20
    vol_mult: float = 1.5
    adx_threshold: int = 25
    period: int = 20
    std: float = 2.0
    leverage: float = 1
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class CodeBacktestRequest(BaseModel):
    code: str
    code_type: str = "dsl"
    symbol: str = "BTCUSDT"
    timeframe: Optional[str] = None
    params: dict = {}
    leverage: float = 1
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    context_timeframes: list = []
    context_lookback: int = 20


class FilterRequest(BaseModel):
    strategy_id: Optional[int] = None
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
def single(req: BacktestRequest):
    t0 = _time.time()
    log.info(f"[API /backtest/single] symbol={req.symbol} sid={req.strategy_id} tf={req.timeframe}")
    try:
        result = backtest_service.backtest_single(
            symbol=req.symbol, strategy_id=req.strategy_id,
            params=req.dict(), timeframe=req.timeframe,
            start=req.start_date, end=req.end_date,
        )
        if "error" in result:
            log.warning(f"[API /backtest/single] 失败: {result['error']}")
            raise HTTPException(status_code=400, detail=result["error"])
        log.info(f"[API /backtest/single] 200 ({_time.time()-t0:.2f}s)")
        return result
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"[API /backtest/single] 500: {e}")
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scan")
def scan(req: BacktestRequest):
    t0 = _time.time()
    log.info(f"[API /backtest/scan] sid={req.strategy_id} tf={req.timeframe} symbols={len(req.symbols) if req.symbols else 'auto'} weights={'yes' if req.weights else 'no'}")
    try:
        symbols = req.symbols
        result = backtest_service.scan_pool(
            strategy_id=req.strategy_id, symbols=symbols, weights=req.weights,
            params=req.dict(), timeframe=req.timeframe,
            start=req.start_date, end=req.end_date,
        )
        if "error" in result:
            log.warning(f"[API /backtest/scan] 失败: {result['error']}")
            raise HTTPException(status_code=400, detail=result["error"])
        log.info(f"[API /backtest/scan] 200 count={result.get('count', 0)} ({_time.time()-t0:.2f}s)")
        return result
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"[API /backtest/scan] 500: {e}")
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/code")
def backtest_code(req: CodeBacktestRequest):
    """用临时代码跑回测 (调试/预览用)"""
    t0 = _time.time()
    log.info(f"[API /backtest/code] symbol={req.symbol} tf={req.timeframe} type={req.code_type} code={len(req.code)} bytes")
    try:
        # 把 context 参数合并到 params, 让 backtest_with_code 能拿到
        params = dict(req.params or {})
        if req.context_timeframes:
            params["context_timeframes"] = req.context_timeframes
            params["context_lookback"] = req.context_lookback
        result = backtest_service.backtest_with_code(
            symbol=req.symbol, code=req.code, params=params,
            timeframe=req.timeframe, start=req.start_date, end=req.end_date,
            code_type=req.code_type,
        )
        if "error" in result:
            log.warning(f"[API /backtest/code] 失败: {result['error']}")
            raise HTTPException(status_code=400, detail=result["error"])
        log.info(f"[API /backtest/code] 200 ({_time.time()-t0:.2f}s)")
        return result
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"[API /backtest/code] 500: {e}")
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/filter")
def filter_stocks(req: FilterRequest):
    try:
        log.info(f"[API /backtest/filter] tf={req.timeframe} symbols={len(req.symbols) if req.symbols else 'auto'}")
        return backtest_service.filter_symbols(req.dict())
    except Exception as e:
        log.error(f"[API /backtest/filter] 500: {e}")
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kline/{symbol}")
def kline(symbol: str, timeframe: str = "4h", start: str = "20240101", end: str = "20250601"):
    try:
        log.info(f"[API /backtest/kline] {symbol} tf={timeframe} range={start}..{end}")
        return backtest_service.get_kline_data(symbol, timeframe, start, end)
    except Exception as e:
        log.error(f"[API /backtest/kline] 500: {e}")
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs")
def list_runs(limit: int = 50):
    from backend.storage import crud
    return crud.list_backtest_runs(limit)