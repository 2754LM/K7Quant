"""交易 API: 模拟盘 (Binance Demo Mode) + 本地审计记录"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from backend.services import trade_service


router = APIRouter()


class RecordRequest(BaseModel):
    mode: str = "simulation"
    symbol: str
    side: str  # buy / sell
    price: float
    amount: float
    pnl: float = 0
    note: str = ""


class OrderRequest(BaseModel):
    symbol: str
    side: str                      # BUY / SELL
    type: str = "LIMIT"            # LIMIT / MARKET
    quantity: float
    price: Optional[float] = None  # LIMIT 必填
    time_in_force: str = "GTC"


class LiveStartRequest(BaseModel):
    strategy_id: int
    symbol: str
    timeframe: str = "1h"
    params: dict = {}


# ---- 状态 / 诊断 ----
@router.get("/status")
def get_status():
    return trade_service.get_status()


@router.get("/connectivity")
def connectivity():
    return trade_service.test_connectivity()


# ---- 账户 ----
@router.get("/account")
def account():
    return trade_service.get_account()


# ---- 订单 ----
@router.get("/open-orders")
def open_orders(symbol: Optional[str] = None):
    return trade_service.get_open_orders(symbol)


@router.post("/order")
def place_order(req: OrderRequest):
    return trade_service.place_order(
        symbol=req.symbol, side=req.side, order_type=req.type,
        quantity=req.quantity, price=req.price, time_in_force=req.time_in_force)


@router.delete("/order")
def cancel_order(symbol: str, order_id: int):
    return trade_service.cancel_order(symbol, order_id)


@router.get("/my-trades")
def my_trades(symbol: str, limit: int = 50):
    return trade_service.get_my_trades(symbol, limit)


# ---- 本地审计记录 ----
@router.get("/trades")
def list_trades(mode: Optional[str] = None, limit: int = 100):
    return {"trades": trade_service.list_trades(mode, limit)}


@router.post("/record")
def record(req: RecordRequest):
    tid = trade_service.record_trade(**req.dict())
    return {"ok": True, "id": tid}


# ---- 沙盒重置 (一键平仓 + 清本地) ----
@router.post("/reset-sandbox")
def reset_sandbox():
    return trade_service.reset_sandbox()


# ---- 策略实盘运行 ----
@router.get("/live/status")
def live_status():
    return trade_service.live_status()


@router.post("/live/start")
def live_start(req: LiveStartRequest):
    return trade_service.live_start(req.strategy_id, req.symbol, req.timeframe, req.params)


@router.post("/live/stop")
def live_stop(flatten: bool = False):
    return trade_service.live_stop(flatten)
