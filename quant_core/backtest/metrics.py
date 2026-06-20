"""绩效指标计算"""
import numpy as np
import pandas as pd


# 不同 K 线周期的年化系数
BARS_PER_YEAR = {
    "1m": 525600, "3m": 175200, "5m": 105120, "15m": 35040,
    "30m": 17520, "1h": 8760, "2h": 4380, "4h": 2190, "6h": 1460,
    "8h": 1095, "12h": 730, "1d": 365, "1w": 52, "1M": 12,
}


def compute_metrics(equity_df: pd.DataFrame, benchmark_df: pd.DataFrame = None,
                    timeframe: str = "1d") -> dict:
    if equity_df.empty:
        return {}
    if "ret" not in equity_df.columns:
        equity_df = equity_df.copy()
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

    # 胜率
    wins = (rets > 0).sum()
    win_rate = float(wins / max(len(rets[rets != 0]), 1)) if len(rets) else 0

    # 最大连续亏损天数
    losing_streak = 0
    max_losing = 0
    for r in rets:
        if r < 0:
            losing_streak += 1
            max_losing = max(max_losing, losing_streak)
        else:
            losing_streak = 0

    # Calmar
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
            out["benchmark_return"] = float(bench.loc[common, "close"].iloc[-1] / bench.loc[common, "close"].iloc[0] - 1)
            out["excess_return"] = total_ret - out["benchmark_return"]
            out["alpha"] = float(ann_ret - bm.mean() * bars)
    return out


def format_metric(value, fmt: str = "pct") -> str:
    if value is None:
        return "-"
    if fmt == "pct":
        return f"{value * 100:.2f}%"
    if fmt == "num":
        return f"{float(value):.2f}"
    return str(value)