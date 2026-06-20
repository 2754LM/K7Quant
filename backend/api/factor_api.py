"""因子 API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from backend.services import factor_service


router = APIRouter()


class ComputeRequest(BaseModel):
    symbol: str
    factor_id: str
    params: dict = {}
    timeframe: str = "1d"
    start: str = "20240101"
    end: str = "20250601"
    limit: int = 500


class ComputeManyRequest(BaseModel):
    symbol: str
    factor_ids: List[str]
    params_list: Optional[List[dict]] = None
    timeframe: str = "1d"
    start: str = "20240101"
    end: str = "20250601"
    limit: int = 500


class CorrelateRequest(BaseModel):
    symbol: str
    factor_ids: List[str]
    params_list: Optional[List[dict]] = None
    period: Optional[int] = None
    timeframe: str = "1d"
    start: str = "20240101"
    end: str = "20250601"


class RankRequest(BaseModel):
    symbols: List[str]
    factor_id: str
    params: dict = {}
    timeframe: str = "1d"
    start: str = "20240101"
    end: str = "20250601"
    top: int = 20


@router.get("/list")
def list_factors(category: str = None):
    return factor_service.list_factors(category)


@router.get("/{factor_id}")
def get_factor(factor_id: str):
    return factor_service.get_factor(factor_id)


@router.post("/compute")
def compute(req: ComputeRequest):
    return factor_service.compute(**req.dict())


@router.post("/compute-many")
def compute_many(req: ComputeManyRequest):
    return factor_service.compute_many(**req.dict())


@router.post("/correlate")
def correlate(req: CorrelateRequest):
    return factor_service.correlate(**req.dict())


@router.post("/rank")
def rank(req: RankRequest):
    return factor_service.rank_factors(**req.dict())