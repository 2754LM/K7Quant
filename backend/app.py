"""K7Quant FastAPI 后端"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional

from backend.services import backtest_service


app = FastAPI(title="K7Quant - 币安量化回测系统", version="3.0")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


class BacktestRequest(BaseModel):
    symbol: str = "BTCUSDT"
    strategy: str = "ma_cross"
    timeframe: str = "4h"
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
    initial_capital: float = 10000
    commission: float = 0.0004
    leverage: float = 1
    start_date: str = "20240101"
    end_date: str = "20250601"


class ScanRequest(BaseModel):
    strategy: str = "ma_cross"
    symbols: Optional[List[str]] = None
    timeframe: str = "4h"
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
    initial_capital: float = 10000
    commission: float = 0.0004
    leverage: float = 1
    start_date: str = "20240101"
    end_date: str = "20250601"


class FilterRequest(BaseModel):
    strategy: str = "ma_cross"
    symbols: Optional[List[str]] = None
    timeframe: str = "1d"
    start_date: str = "20240101"
    end_date: str = "20250601"
    min_return: float = -1.0
    max_return: float = 100.0
    min_price: float = 0
    max_price: float = 1e12
    min_sharpe: float = -10


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/config")
def get_config():
    return backtest_service.get_config()


@app.post("/api/backtest")
def backtest(req: BacktestRequest):
    try:
        result = backtest_service.run_one(req.symbol, req.strategy, req.dict(),
                                          timeframe=req.timeframe)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/scan")
def scan(req: ScanRequest):
    try:
        result = backtest_service.scan_pool(req.dict())
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/kline/{symbol}")
def kline(symbol: str, timeframe: str = "1d",
          start: str = "20240101", end: str = "20250601"):
    try:
        return backtest_service.get_kline(symbol, timeframe, start, end)
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/filter")
def filter_stocks(req: FilterRequest):
    try:
        return backtest_service.filter_stocks(req.dict())
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/data")
def list_data():
    return backtest_service.list_data()


FRONTEND_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")
if os.path.isdir(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/")
    def serve_index():
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))

    @app.get("/{path:path}")
    def serve_spa(path: str):
        full = os.path.join(FRONTEND_DIST, path)
        if os.path.isfile(full):
            return FileResponse(full)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")