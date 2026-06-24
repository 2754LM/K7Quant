"""因子 API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List

from backend.common.services import factor_service


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


class CustomFactorRequest(BaseModel):
    factor_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    name_zh: str = Field(..., min_length=1, max_length=64)
    category: str = Field("自定义类", max_length=32)
    formula: str = ""
    description: str = ""
    dsl_code: str = Field(..., min_length=1)


@router.get("/list")
def list_factors(category: str = None):
    return factor_service.list_factors(category)


@router.get("/dsl-docs")
def dsl_docs():
    """DSL 文档 (复用 strategy 引擎的同一份, 因子和策略共用一套语法)"""
    from backend.core.strategy import get_dsl_docs
    return get_dsl_docs()


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


@router.post("/create-custom")
def create_custom_factor(req: CustomFactorRequest):
    """创建用户自定义 DSL 因子 (仅一个表达式, 类似 Excel 公式)"""
    try:
        return factor_service.create_custom_factor(req.dict())
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/custom/{factor_id}")
def delete_custom_factor(factor_id: str):
    try:
        factor_service.delete_custom_factor(factor_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e))