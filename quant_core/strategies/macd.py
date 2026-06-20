"""MACD 策略"""
import pandas as pd
from quant_core.strategies.base import Strategy


class MACDStrategy(Strategy):
    id = "macd"
    name = "MACD 金叉死叉"
    icon = "📈"
    description = "MACD 上穿信号线做多，下穿做空。趋势 + 反转兼顾，最常用技术指标之一。"
    category = "trend"

    params_schema = {
        "macd_fast":   {"label": "快 EMA", "type": "int", "default": 12, "min": 2, "max": 60},
        "macd_slow":   {"label": "慢 EMA", "type": "int", "default": 26, "min": 5, "max": 120},
        "macd_signal": {"label": "信号线", "type": "int", "default": 9, "min": 2, "max": 50},
    }

    def generate(self, df: pd.DataFrame) -> pd.DataFrame:
        fast = int(self.params["macd_fast"])
        slow = int(self.params["macd_slow"])
        signal_p = int(self.params["macd_signal"])
        out = df.copy()

        ema_fast = out["close"].ewm(span=fast, adjust=False).mean()
        ema_slow = out["close"].ewm(span=slow, adjust=False).mean()
        out["macd"] = ema_fast - ema_slow
        out["signal_line"] = out["macd"].ewm(span=signal_p, adjust=False).mean()

        out["position"] = 0
        out.loc[out["macd"] > out["signal_line"], "position"] = 1
        out.loc[out["macd"] < out["signal_line"], "position"] = 0
        return out[["date", "close", "position"]].dropna().reset_index(drop=True)