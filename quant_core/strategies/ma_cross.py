"""双均线交叉策略"""
import pandas as pd
from quant_core.strategies.base import Strategy


class MACross(Strategy):
    id = "ma_cross"
    name = "双均线交叉"
    icon = "📏"
    description = "MA 短上穿长做多，下穿做空。最经典趋势策略，适合趋势市。"
    category = "trend"

    params_schema = {
        "ma_short": {"label": "短均线", "type": "int", "default": 7, "min": 2, "max": 60},
        "ma_long":  {"label": "长均线", "type": "int", "default": 25, "min": 5, "max": 250},
    }

    def generate(self, df: pd.DataFrame) -> pd.DataFrame:
        short = int(self.params["ma_short"])
        long_ = int(self.params["ma_long"])
        out = df.copy()
        out[f"ma{short}"] = out["close"].rolling(short).mean()
        out[f"ma{long_}"] = out["close"].rolling(long_).mean()
        out["position"] = 0
        out.loc[out[f"ma{short}"] > out[f"ma{long_}"], "position"] = 1
        return out[["date", "close", "position"]].dropna().reset_index(drop=True)