"""币种 API"""
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from typing import List

from backend.repositories.crud import crud


router = APIRouter()


# 严格白名单: Binance USDT 交易对 (大写字母+数字, 2-20 字符)
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{2,20}$")


def _validate_symbol(value: str) -> str:
    if not _SYMBOL_PATTERN.match(value):
        raise HTTPException(status_code=400, detail=f"非法 symbol: {value!r} (必须 ^[A-Z0-9]{{2,20}}$)")
    return value


class UpsertRequest(BaseModel):
    symbol: str = Field(..., description="Binance USDT 交易对, 如 BTCUSDT")
    name_zh: str
    name_en: str = ""
    category: str = ""
    market_cap_rank: int = 999
    description: str = ""
    tags: List[str] = []
    is_active: int = 0

    @field_validator("symbol")
    @classmethod
    def _check_symbol(cls, v: str) -> str:
        return _validate_symbol(v)


class ActiveSymbolsRequest(BaseModel):
    symbols: List[str]

    @field_validator("symbols")
    @classmethod
    def _check_symbols(cls, v: List[str]) -> List[str]:
        for s in v:
            _validate_symbol(s)
        return v


@router.get("/list")
def list_all(active_only: bool = False):
    return {"symbols": crud.list_symbols(active_only)}


@router.get("/{symbol}")
def get_one(symbol: str):
    s = crud.get_symbol(symbol)
    if not s:
        raise HTTPException(status_code=404, detail="币种不存在")
    return s


@router.post("/upsert")
def upsert(req: UpsertRequest):
    crud.upsert_symbol(**req.dict())
    return {"ok": True}


@router.post("/active")
def set_active(req: ActiveSymbolsRequest):
    crud.set_active_symbols(req.symbols)
    return {"ok": True, "active": req.symbols}


@router.get("/active/current")
def get_active():
    syms = [s["symbol"] for s in crud.list_symbols(active_only=True)]
    return {"active": syms}