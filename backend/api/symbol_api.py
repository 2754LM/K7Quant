"""币种 API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

from backend.storage import crud


router = APIRouter()


class UpsertRequest(BaseModel):
    symbol: str
    name_zh: str
    name_en: str = ""
    category: str = ""
    market_cap_rank: int = 999
    description: str = ""
    tags: List[str] = []
    is_active: int = 0


class ActiveSymbolsRequest(BaseModel):
    symbols: List[str]


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