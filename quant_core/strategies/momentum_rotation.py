"""动量轮动策略 (多标的池)"""
import numpy as np
import pandas as pd
from quant_core.strategies.base import Strategy


class MomentumRotation(Strategy):
    """
    单标的：过去 N 根涨就买，跌就空仓
    池子模式：在 run_pool_momentum 里调用
    """
    id = "momentum_rotation"
    name = "动量轮动"
    icon = "🚀"
    description = "选过去 N 根涨幅最高 Top K 持有。强者恒强，适合牛市/震荡市。"
    category = "momentum"

    params_schema = {
        "top_n":    {"label": "选 N 个", "type": "int", "default": 3, "min": 1, "max": 20},
        "hold":     {"label": "持仓(根)", "type": "int", "default": 12, "min": 1, "max": 100},
        "lookback": {"label": "回看(根)", "type": "int", "default": 24, "min": 1, "max": 200},
    }

    def generate(self, df: pd.DataFrame) -> pd.DataFrame:
        lookback = int(self.params["lookback"])
        out = df.copy()
        out["momentum"] = out["close"].pct_change(periods=lookback)
        out["position"] = (out["momentum"] > 0).astype(int).shift(1).fillna(0)
        return out[["date", "close", "position"]].reset_index(drop=True)

    @staticmethod
    def run_pool(data: dict, top_n: int, hold: int, lookback: int,
                 initial_capital: float, commission: float) -> pd.DataFrame:
        """池子动量轮动"""
        price_panel = pd.DataFrame(
            {sym: df.set_index("date")["close"] for sym, df in data.items()}
        ).sort_index()

        cash = initial_capital
        holdings = {}
        history = []
        last_rebalance = None

        for date in price_panel.index:
            prices = price_panel.loc[date]
            need = last_rebalance is None or (date - last_rebalance).total_seconds() >= hold * 3600

            if need:
                if len(price_panel.loc[:date]) < lookback + 1:
                    history.append({"date": date, "equity": cash, "holdings": 0})
                    last_rebalance = date
                    continue
                past = price_panel.loc[:date].iloc[-(lookback + 1)]
                if isinstance(past, pd.DataFrame):
                    past = past.iloc[0]
                momentum = (prices / past - 1).dropna()
                if momentum.empty:
                    history.append({"date": date, "equity": cash, "holdings": 0})
                    last_rebalance = date
                    continue
                targets = momentum.sort_values(ascending=False).head(top_n).index.tolist()
                targets = [s for s in targets if pd.notna(prices.get(s)) and prices[s] > 0]

                sym_value = cash / max(len(targets), 1) if targets else 0
                for sym in list(holdings.keys()):
                    if sym not in targets and holdings[sym] > 0:
                        px = prices.get(sym, np.nan)
                        if pd.notna(px):
                            cash += holdings[sym] * px * (1 - commission)
                        del holdings[sym]
                for sym in targets:
                    px = prices[sym]
                    cost = sym_value * (1 + commission)
                    if cost <= cash:
                        shares = sym_value / px
                        holdings[sym] = holdings.get(sym, 0) + shares
                        cash -= cost
                last_rebalance = date

            equity = cash + sum(holdings.get(s, 0) * prices.get(s, 0) for s in holdings)
            history.append({"date": date, "equity": equity, "holdings": len(holdings)})

        edf = pd.DataFrame(history)
        if edf.empty:
            return edf
        edf["ret"] = edf["equity"].pct_change().fillna(0)
        edf["strategy_ret"] = edf["ret"]
        return edf