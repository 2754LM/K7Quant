"""RSI 策略"""
import pandas as pd
from quant_core.strategies.base import Strategy


class RSIStrategy(Strategy):
    id = "rsi"
    name = "RSI 超买超卖"
    icon = "📊"
    description = "RSI 跌破超卖线买入，涨破超买线卖出。震荡市神器，单边市容易钝化。"
    category = "mean_reversion"

    params_schema = {
        "rsi_period":     {"label": "RSI 周期", "type": "int", "default": 14, "min": 2, "max": 50},
        "rsi_oversold":   {"label": "超卖线", "type": "int", "default": 30, "min": 5, "max": 50},
        "rsi_overbought": {"label": "超买线", "type": "int", "default": 70, "min": 50, "max": 95},
    }

    def generate(self, df: pd.DataFrame) -> pd.DataFrame:
        period = int(self.params["rsi_period"])
        oversold = int(self.params["rsi_oversold"])
        overbought = int(self.params["rsi_overbought"])
        out = df.copy()

        delta = out["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / loss.replace(0, 1e-9)
        out["rsi"] = 100 - (100 / (1 + rs))

        out["position"] = 0
        out.loc[out["rsi"] < oversold, "position"] = 1
        out.loc[out["rsi"] > overbought, "position"] = 0
        return out[["date", "close", "position"]].dropna().reset_index(drop=True)