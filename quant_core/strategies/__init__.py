"""策略注册表"""
from quant_core.strategies.base import Strategy
from quant_core.strategies.ma_cross import MACross
from quant_core.strategies.momentum_rotation import MomentumRotation
from quant_core.strategies.rsi import RSIStrategy
from quant_core.strategies.macd import MACDStrategy


ALL_STRATEGIES: list[Strategy] = [
    MACross(),
    MomentumRotation(),
    RSIStrategy(),
    MACDStrategy(),
]

BY_ID: dict[str, Strategy] = {s.id: s for s in ALL_STRATEGIES}


def get(strategy_id: str) -> Strategy:
    if strategy_id not in BY_ID:
        raise ValueError(f"未知策略: {strategy_id}，可选: {list(BY_ID)}")
    return BY_ID[strategy_id]