"""交易业务: 模拟/实盘 (TODO 占位)"""
from typing import List

from backend.storage import crud


def get_status() -> dict:
    """获取交易状态 (模拟/实盘)"""
    from backend.core import config as sys_config
    trading = sys_config.get("trading", {})
    return {
        "enabled": trading.get("enabled", False),
        "mode": trading.get("mode", "simulation"),
        "max_position_pct": trading.get("max_position_pct", 0.3),
        "max_total_pct": trading.get("max_total_pct", 0.95),
        "stop_loss_pct": trading.get("stop_loss_pct", 0.05),
        "take_profit_pct": trading.get("take_profit_pct", 0.15),
        "active_orders": 0,  # TODO
        "today_pnl": 0.0,   # TODO
    }


def list_trades(mode: str = None, limit: int = 100) -> list:
    return crud.list_trades(mode, limit)


def record_trade(mode: str, symbol: str, side: str, price: float,
                 amount: float, pnl: float = 0, note: str = "") -> int:
    return crud.insert_trade(mode, symbol, side, price, amount, pnl, note)