"""配置 API"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List

from backend.core import config as sys_config


router = APIRouter()


class BacktestConfigRequest(BaseModel):
    initial_capital: Optional[float] = None
    commission_rate: Optional[float] = None
    slippage: Optional[float] = None
    leverage: Optional[int] = None
    position_mode: Optional[str] = None
    fixed_amount: Optional[float] = None
    rebalance_bars: Optional[int] = None
    default_timeframe: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class DataSourceRequest(BaseModel):
    api_base: Optional[str] = None
    proxy_enabled: Optional[bool] = None
    proxy_http: Optional[str] = None
    proxy_https: Optional[str] = None


class UIConfigRequest(BaseModel):
    theme: Optional[str] = None
    show_help_tooltips: Optional[bool] = None


class TradingConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    mode: Optional[str] = None
    max_position_pct: Optional[float] = None
    max_total_pct: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None


@router.get("")
def get_full():
    from backend.services.config_service import get_full_config
    return get_full_config()


@router.put("/backtest")
def set_backtest(req: BacktestConfigRequest):
    cfg = sys_config.load_config()
    bt = cfg.setdefault("backtest", {})
    for k, v in req.dict().items():
        if v is not None:
            bt[k] = v
    sys_config.save_config(cfg)
    return cfg


@router.put("/data-source")
def set_data_source(req: DataSourceRequest):
    cfg = sys_config.load_config()
    ds = cfg.setdefault("data_source", {})
    if req.api_base is not None:
        ds["api_base"] = req.api_base
    proxy = ds.setdefault("proxy", {})
    if req.proxy_enabled is not None:
        proxy["enabled"] = req.proxy_enabled
    if req.proxy_http is not None:
        proxy["http"] = req.proxy_http
    if req.proxy_https is not None:
        proxy["https"] = req.proxy_https
    sys_config.save_config(cfg)
    return cfg


@router.put("/ui")
def set_ui(req: UIConfigRequest):
    cfg = sys_config.load_config()
    ui = cfg.setdefault("ui", {})
    for k, v in req.dict().items():
        if v is not None:
            ui[k] = v
    sys_config.save_config(cfg)
    return cfg


@router.put("/trading")
def set_trading(req: TradingConfigRequest):
    cfg = sys_config.load_config()
    tr = cfg.setdefault("trading", {})
    for k, v in req.dict().items():
        if v is not None:
            tr[k] = v
    sys_config.save_config(cfg)
    return cfg


@router.post("/test-connection")
def test():
    from backend.data.fetcher import get_fetcher
    return get_fetcher().test_connectivity()