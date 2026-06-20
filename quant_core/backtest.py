"""回测引擎 + 内置策略"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from quant_core import config


# ============ 指标 ============

def add_moving_average(df: pd.DataFrame, windows=(5, 10, 20, 60)) -> pd.DataFrame:
    df = df.copy()
    for w in windows:
        df[f"ma{w}"] = df["close"].rolling(w).mean()
    return df


def add_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    df = df.copy()
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss.replace(0, 1e-9)
    df["rsi"] = 100 - (100 / (1 + rs))
    return df


def add_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    df = df.copy()
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    df["macd"] = ema_fast - ema_slow
    df["signal_line"] = df["macd"].ewm(span=signal, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["signal_line"]
    return df


# ============ 策略 ============

def signal_ma_cross(df: pd.DataFrame, short: int = 7, long: int = 25) -> pd.DataFrame:
    df = add_moving_average(df, (short, long))
    df["position"] = 0
    df.loc[df[f"ma{short}"] > df[f"ma{long}"], "position"] = 1
    df.loc[df[f"ma{short}"] < df[f"ma{long}"], "position"] = 0
    return df[["date", "close", "position"]]


def signal_rsi(df: pd.DataFrame, period: int = 14, oversold: int = 30, overbought: int = 70) -> pd.DataFrame:
    df = add_rsi(df, period)
    df["position"] = 0
    df.loc[df["rsi"] < oversold, "position"] = 1
    df.loc[df["rsi"] > overbought, "position"] = 0
    return df[["date", "close", "position"]]


def signal_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal_p: int = 9) -> pd.DataFrame:
    df = add_macd(df, fast, slow, signal_p)
    df["position"] = 0
    df.loc[df["macd"] > df["signal_line"], "position"] = 1
    df.loc[df["macd"] < df["signal_line"], "position"] = 0
    return df[["date", "close", "position"]]


def signal_momentum(df: pd.DataFrame, lookback: int = 24) -> pd.DataFrame:
    """单标的动量：正就买，负就空仓"""
    df = df.copy()
    df["momentum"] = df["close"].pct_change(periods=lookback)
    df["position"] = (df["momentum"] > 0).astype(int).shift(1).fillna(0)
    return df[["date", "close", "position"]]


# ============ 回测 ============

class Backtester:
    def __init__(self, initial_capital: float = None, commission: float = None):
        self.initial_capital = initial_capital or config.DEFAULT_CAPITAL
        self.commission = commission or config.DEFAULT_COMMISSION

    def run_single(self, df_with_signal: pd.DataFrame, leverage: float = 1) -> pd.DataFrame:
        """df 必须有 date/close/position 列 (position: 0/1)"""
        df = df_with_signal.copy().reset_index(drop=True)
        df["ret"] = df["close"].pct_change().fillna(0)
        df["position"] = df["position"].shift(1).fillna(0)
        df["trade"] = df["position"].diff().abs().fillna(0)
        df["strategy_ret"] = df["position"] * df["ret"] * leverage - df["trade"] * self.commission
        df["equity"] = self.initial_capital * (1 + df["strategy_ret"]).cumprod()
        return df

    def run_pool_momentum(self, data: dict, top_n: int = 3, hold: int = 12,
                          lookback: int = 24) -> pd.DataFrame:
        """池子动量轮动"""
        price_panel = pd.DataFrame(
            {sym: df.set_index("date")["close"] for sym, df in data.items()}
        ).sort_index()

        cash = self.initial_capital
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
                            cash += holdings[sym] * px * (1 - self.commission)
                        del holdings[sym]
                for sym in targets:
                    px = prices[sym]
                    cost = sym_value * (1 + self.commission)
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

    @staticmethod
    def metrics(equity_df: pd.DataFrame, benchmark_df: pd.DataFrame = None,
                timeframe: str = "1d") -> dict:
        if equity_df.empty:
            return {}
        if "ret" not in equity_df.columns:
            equity_df = equity_df.copy()
            equity_df["ret"] = equity_df["equity"].pct_change().fillna(0)

        equity = equity_df["equity"].values
        rets = equity_df["ret"].values
        bars_per_year = {"1m": 525600, "5m": 105120, "15m": 35040, "30m": 17520,
                         "1h": 8760, "4h": 2190, "1d": 365, "1w": 52}.get(timeframe, 365)

        total_ret = equity[-1] / equity[0] - 1
        n = len(equity)
        ann_ret = (1 + total_ret) ** (bars_per_year / max(n, 1)) - 1
        ann_vol = rets.std() * np.sqrt(bars_per_year)
        sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
        cummax = np.maximum.accumulate(equity)
        dd = (equity - cummax) / cummax
        mdd = dd.min()

        out = {
            "total_return": total_ret, "annual_return": ann_ret,
            "annual_volatility": ann_vol, "sharpe": sharpe,
            "max_drawdown": mdd, "trade_bars": n,
        }

        if benchmark_df is not None and not benchmark_df.empty:
            bench = benchmark_df.copy()
            bench["ret"] = bench["close"].pct_change().fillna(0)
            bench = bench.set_index("date")
            eq_idx = equity_df.set_index("date")
            common = eq_idx.index.intersection(bench.index)
            if len(common) > 1:
                strat = eq_idx.loc[common, "ret"]
                bm = bench.loc[common, "ret"]
                excess = strat - bm
                ann_excess = excess.mean() * bars_per_year
                te = excess.std() * np.sqrt(bars_per_year)
                out["information_ratio"] = ann_excess / te if te > 0 else 0
                out["beta"] = np.cov(strat, bm)[0, 1] / np.var(bm) if np.var(bm) > 0 else 0
                out["benchmark_return"] = bench.loc[common, "close"].iloc[-1] / bench.loc[common, "close"].iloc[0] - 1
                out["excess_return"] = total_ret - out["benchmark_return"]
        return out


def plot_equity(equity_df: pd.DataFrame, benchmark_df: pd.DataFrame = None,
                title: str = "策略回测", save_path: str = None) -> str:
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax = plt.subplots(figsize=(12, 6))
    eq_norm = equity_df["equity"] / equity_df["equity"].iloc[0]
    ax.plot(equity_df["date"], eq_norm, label="Strategy", linewidth=2, color="#f0b90b")

    if benchmark_df is not None and not benchmark_df.empty:
        bm = benchmark_df.copy()
        bm["norm"] = bm["close"] / bm["close"].iloc[0]
        ax.plot(bm["date"], bm["norm"], label="BTC", linewidth=1.5, alpha=0.6, color="#627eea")

    ax.set_title(title, fontsize=14)
    ax.set_xlabel("Date")
    ax.set_ylabel("NAV")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        return save_path
    plt.close(fig)
    return ""