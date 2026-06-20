"""交易 API (模拟/实盘 - 占位)"""
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


@router.get("/status")
def get_status():
    return trade_service.get_status()


@router.get("/trades")
def list_trades(mode: Optional[str] = None, limit: int = 100):
    return {"trades": trade_service.list_trades(mode, limit)}


@router.post("/record")
def record(req: RecordRequest):
    tid = trade_service.record_trade(**req.dict())
    return {"ok": True, "id": tid}