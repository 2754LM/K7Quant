"""策略 API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from backend.services import strategy_service


router = APIRouter()


class CreateRequest(BaseModel):
    name: str
    description: str = ""
    category: str = "custom"
    code: str
    code_type: str = "dsl"
    params_schema: dict = {}
    context_timeframes: list = []
    context_lookback: int = 20


class UpdateRequest(CreateRequest):
    id: int


class ValidateRequest(BaseModel):
    code: str
    code_type: str = "dsl"
    context_timeframes: list = []
    context_lookback: int = 20


class CompilePythonRequest(BaseModel):
    code: str


@router.get("/list")
def list_all():
    return {"strategies": strategy_service.list_strategies()}


@router.get("/templates")
def templates():
    return strategy_service.get_templates()


@router.get("/dsl-docs")
def dsl_docs():
    return strategy_service.get_dsl_docs()


@router.get("/{strategy_id}")
def get_one(strategy_id: int):
    s = strategy_service.get_strategy(strategy_id)
    if not s:
        raise HTTPException(status_code=404, detail="策略不存在")
    return s


@router.post("/create")
def create(req: CreateRequest):
    result = strategy_service.create_strategy(req.dict())
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/update")
def update(req: UpdateRequest):
    result = strategy_service.update_strategy(req.id, req.dict())
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.delete("/{strategy_id}")
def delete(strategy_id: int):
    return strategy_service.delete_strategy(strategy_id)


@router.post("/validate")
def validate(req: ValidateRequest):
    return strategy_service.validate_code(
        req.code, code_type=req.code_type,
        context_timeframes=req.context_timeframes,
        context_lookback=req.context_lookback,
    )


@router.post("/compile-python")
def compile_python(req: CompilePythonRequest):
    """校验 + 测试编译 Python 策略, 返回 {ok, error, has_init, on_bar_args}"""
    return strategy_service.validate_python(req.code)