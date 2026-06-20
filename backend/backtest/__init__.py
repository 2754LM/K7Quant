"""回测引擎"""
import numpy as np
import pandas as pd

from backend.core import config as sys_config


# 不同 K 线年化系数
BARS_PER_YEAR = {
    "1m": 525600, "3m": 175200, "5m": 105120, "15m": 35040,
    "30m": 17520, "1h": 8760, "2h": 4380, "4h": 2190, "6h": 1460,
    "8h": 1095, "12h": 730, "1d": 365, "1w": 52, "1M": 12,
}


class Backtester:
    def __init__(self, initial_capital: float = None,
                 commission_rate: float = None,
                 slippage: float = None):
        # 用 is None 判断, 否则显式传入的 0 (零本金/零手续费/零滑点) 会被默认值覆盖
        self.initial_capital = (initial_capital if initial_capital is not None
                                else float(sys_config.get("backtest.initial_capital", 10000)))
        self.commission_rate = (commission_rate if commission_rate is not None
                                else float(sys_config.get("backtest.commission_rate", 0.0004)))
        self.slippage = (slippage if slippage is not None
                         else float(sys_config.get("backtest.slippage", 0.0005)))
        self.position_mode = sys_config.get("backtest.position_mode", "all_in")
        self.fixed_amount = float(sys_config.get("backtest.fixed_amount", 1000))

    def run(self, signal_df: pd.DataFrame, leverage: float = 1,
            position_size: float = 1.0, rebalance_bars: int = 1) -> pd.DataFrame:
        """
        signal_df: 包含 date/close/position (0/1) 的 df
        position_size: 仓位比例 (0-1)
        rebalance_bars: 调仓频率, 每 N 根 K 线才允许换一次仓 (默认 1=每根)
        """
        df = signal_df.copy().reset_index(drop=True)
        # 调仓频率: 只在每 N 根的整数倍上采用新信号, 其余沿用上一次仓位
        if rebalance_bars and rebalance_bars > 1 and len(df):
            raw = df["position"].tolist()
            held = raw[0]
            locked = []
            for i, v in enumerate(raw):
                if i % rebalance_bars == 0:
                    held = v
                locked.append(held)
            df["position"] = locked
        df["ret"] = df["close"].pct_change().fillna(0)
        # 次根 K 线才按信号建仓, 避免未来函数
        df["position"] = df["position"].shift(1).fillna(0)
        df["target_size"] = position_size
        # 仓位变化才算一次交易; 首行没有前值, 不应被记为交易/收费
        df["trade"] = (df["position"] != df["position"].shift(1)).fillna(False).astype(int)
        if len(df):
            df.loc[df.index[0], "trade"] = 0
        # 实际仓位 = 信号 * 比例 * 杠杆
        df["actual_pos"] = df["position"] * df["target_size"] * leverage
        # 收益
        df["strategy_ret"] = df["actual_pos"] * df["ret"] - df["trade"] * (self.commission_rate + self.slippage)
        df["equity"] = self.initial_capital * (1 + df["strategy_ret"]).cumprod()
        return df

    def run_pool_momentum(self, data: dict, top_n: int, hold: int, lookback: int) -> pd.DataFrame:
        """动量轮动 (池子)"""
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
                            cash += holdings[sym] * px * (1 - self.commission_rate - self.slippage)
                        del holdings[sym]
                for sym in targets:
                    px = prices[sym]
                    cost = sym_value * (1 + self.commission_rate)
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


def compute_metrics(equity_df: pd.DataFrame, benchmark_df: pd.DataFrame = None,
                    timeframe: str = "1d") -> dict:
    if equity_df.empty:
        return {}
    equity_df = equity_df.copy()
    # 用策略净值推导收益; 不复用 run() 里残留的标的价格 ret 列,
    # 否则 Sharpe/波动率/胜率算的是标的而非策略 (见 issue #5)
    if "strategy_ret" in equity_df.columns:
        equity_df["ret"] = equity_df["strategy_ret"].fillna(0)
    else:
        equity_df["ret"] = equity_df["equity"].pct_change().fillna(0)

    equity = equity_df["equity"].values
    rets = equity_df["ret"].values
    bars = BARS_PER_YEAR.get(timeframe, 365)

    total_ret = float(equity[-1] / equity[0] - 1)
    n = len(equity)
    ann_ret = float((1 + total_ret) ** (bars / max(n, 1)) - 1)
    ann_vol = float(rets.std() * np.sqrt(bars))
    sharpe = float(ann_ret / ann_vol) if ann_vol > 0 else 0.0

    cummax = np.maximum.accumulate(equity)
    dd = (equity - cummax) / cummax
    mdd = float(dd.min())

    wins = (rets > 0).sum()
    win_rate = float(wins / max(len(rets[rets != 0]), 1)) if len(rets) else 0

    losing_streak = 0
    max_losing = 0
    for r in rets:
        if r < 0:
            losing_streak += 1
            max_losing = max(max_losing, losing_streak)
        else:
            losing_streak = 0

    calmar = float(ann_ret / abs(mdd)) if mdd != 0 else 0

    out = {
        "total_return": total_ret,
        "annual_return": ann_ret,
        "annual_volatility": ann_vol,
        "sharpe": sharpe,
        "calmar": calmar,
        "max_drawdown": mdd,
        "win_rate": win_rate,
        "max_losing_streak": max_losing,
        "trade_bars": n,
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
            ann_excess = float(excess.mean() * bars)
            te = float(excess.std() * np.sqrt(bars))
            out["information_ratio"] = ann_excess / te if te > 0 else 0
            out["beta"] = float(np.cov(strat, bm)[0, 1] / np.var(bm)) if np.var(bm) > 0 else 0
            out["benchmark_return"] = float(
                bench.loc[common, "close"].iloc[-1] / bench.loc[common, "close"].iloc[0] - 1
            )
            out["excess_return"] = total_ret - out["benchmark_return"]
            out["alpha"] = float(ann_ret - bm.mean() * bars)

    return out


def plot_equity(equity_df: pd.DataFrame, benchmark_df: pd.DataFrame = None,
                title: str = "回测", save_path: str = None) -> str:
    """生成净值曲线图, 返回 base64 编码 PNG"""
    import io, base64
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor("#181a20")
    ax.set_facecolor("#181a20")

    eq_norm = equity_df["equity"] / equity_df["equity"].iloc[0]
    ax.plot(equity_df["date"], eq_norm, label="策略", linewidth=2, color="#f0b90b")
    ax.fill_between(equity_df["date"], eq_norm, alpha=0.08, color="#f0b90b")

    if benchmark_df is not None and not benchmark_df.empty:
        bm = benchmark_df.copy()
        bm["norm"] = bm["close"] / bm["close"].iloc[0]
        ax.plot(bm["date"], bm["norm"], label="BTC", linewidth=1.5, alpha=0.6, color="#f7931a")

    ax.set_title(title, fontsize=14, color="#eaecef")
    ax.set_xlabel("Date", color="#b7bdc6")
    ax.set_ylabel("NAV", color="#b7bdc6")
    ax.tick_params(colors="#b7bdc6")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.2, color="#474d57")
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=120, bbox_inches="tight", facecolor="#181a20")
        plt.close(fig)
        with open(save_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor="#181a20")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")