"""回测引擎"""
import io
import base64
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from quant_core.settings import C
from quant_core.backtest.metrics import compute_metrics


class Backtester:
    def __init__(self, initial_capital: float = None, commission: float = None):
        self.initial_capital = initial_capital or C.initial_capital()
        self.commission = commission or C.commission()

    def run(self, signal_df: pd.DataFrame, leverage: float = 1) -> pd.DataFrame:
        """
        输入: 包含 date/close/position 的 df
        输出: 包含 equity/strategy_ret 的完整回测结果
        """
        df = signal_df.copy().reset_index(drop=True)
        df["ret"] = df["close"].pct_change().fillna(0)
        df["position"] = df["position"].shift(1).fillna(0)
        df["trade"] = df["position"].diff().abs().fillna(0)
        df["strategy_ret"] = df["position"] * df["ret"] * leverage - df["trade"] * self.commission
        df["equity"] = self.initial_capital * (1 + df["strategy_ret"]).cumprod()
        return df

    def metrics(self, result_df: pd.DataFrame, benchmark_df: pd.DataFrame = None,
                timeframe: str = "1d") -> dict:
        return compute_metrics(result_df, benchmark_df, timeframe)


def plot_equity(equity_df: pd.DataFrame, benchmark_df: pd.DataFrame = None,
                title: str = "策略回测", save: bool = True, save_path: str = None) -> str:
    """绘净值曲线，返回 base64 图片"""
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax = plt.subplots(figsize=(12, 6))
    eq_norm = equity_df["equity"] / equity_df["equity"].iloc[0]
    ax.plot(equity_df["date"], eq_norm, label="Strategy", linewidth=2, color="#f0b90b")
    ax.fill_between(equity_df["date"], eq_norm, alpha=0.1, color="#f0b90b")

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
    ax.set_facecolor("#181a20")
    fig.patch.set_facecolor("#181a20")
    plt.tight_layout()

    if save and save_path:
        plt.savefig(save_path, dpi=120, bbox_inches="tight", facecolor="#181a20")
        plt.close(fig)
        with open(save_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor="#181a20")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")