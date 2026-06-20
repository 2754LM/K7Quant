"""配置管理 API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from backend.services.config_service import (
    get_full_config, update_active_symbols, update_strategy_defaults,
    update_timeframes, reset_settings,
)
from quant_core.settings import update_settings


router = APIRouter(prefix="/api/config", tags=["config"])


class ActiveSymbolsRequest(BaseModel):
    symbols: List[str]


class StrategyDefaultsRequest(BaseModel):
    strategy: str
    params: dict


class BacktestDefaultsRequest(BaseModel):
    initial_capital: Optional[float] = None
    commission: Optional[float] = None
    leverage: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    default_timeframe: Optional[str] = None


class TimeframesRequest(BaseModel):
    timeframes: List[str]


def _wrap():
    """返回标准 {settings: ...} 包装"""
    return {"settings": update_settings.__wrapped__() if hasattr(update_settings, "__wrapped__") else None}


@router.get("")
def get_config():
    return get_full_config()


@router.put("/active-symbols")
def set_active_symbols(req: ActiveSymbolsRequest):
    return update_active_symbols(req.symbols)


@router.put("/strategy-defaults")
def set_strategy_defaults(req: StrategyDefaultsRequest):
    return update_strategy_defaults(req.strategy, req.params)


@router.put("/backtest-defaults")
def set_backtest_defaults(req: BacktestDefaultsRequest):
    patch = {f"backtest.{k}": v for k, v in req.dict().items() if v is not None}
    return update_settings(patch)


@router.put("/timeframes")
def set_timeframes(req: TimeframesRequest):
    return update_timeframes(req.timeframes)


@router.post("/reset")
def reset():
    return reset_settings()