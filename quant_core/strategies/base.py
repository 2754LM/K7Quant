"""策略基类"""
from abc import ABC, abstractmethod
from typing import Dict, Any
import pandas as pd


class Strategy(ABC):
    """所有策略继承这个类"""

    id: str = "base"
    name: str = "Base"
    icon: str = "📊"
    description: str = ""
    category: str = "trend"  # trend / mean_reversion / momentum
    params_schema: Dict[str, Dict[str, Any]] = {}

    def __init__(self, **params):
        self.params = self._defaults()
        self.params.update(params)

    def _defaults(self) -> dict:
        return {k: v.get("default") for k, v in self.params_schema.items()}

    @abstractmethod
    def generate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        输入: 包含 date/open/high/low/close/volume 的 df
        输出: 必须包含 date/close/position (0/1) 列
        """
        raise NotImplementedError


def to_records_dict():
    """返回所有策略信息用于 API"""
    from quant_core.strategies import ALL_STRATEGIES
    return [{
        "id": s.id, "name": s.name, "icon": s.icon,
        "description": s.description, "category": s.category,
        "params_schema": s.params_schema,
    } for s in ALL_STRATEGIES]