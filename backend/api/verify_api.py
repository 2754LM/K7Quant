"""验证测试模块 API

独立的小数据回测验证工具: 让用户用已知的小数据集/自定义数据集跑策略,
逐步回显每根 bar 的信号/仓位/成交/费用/净值变化, 用来核对回测引擎运算是否正确。

设计原则:
- 不依赖 DB / 缓存 / 远端 API, 完全本地纯函数
- 内置 4 个典型数据集 (单调上涨/下跌/V型/震荡), 数据已知便于手算核对
- 支持自定义 CSV (粘贴 date/open/high/low/close/volume)
- 每根 bar 完整 trace: ohlcv + signal + action + qty/cash/equity 变化
- 日志式输出每步 "bar N: signal=X -> action=Y (qty_before=Z -> qty_after=W)"
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.backtest import Backtester, compute_metrics
from backend.strategy import StrategyEngine
from backend.strategy.sandbox import PythonStrategy


router = APIRouter(prefix="/api/verify", tags=["verify"])


_DATASET_DESCRIPTIONS = {
    "uptrend":   "单调上涨: 100 → +2%/根 × 10, 验证'买并持有'策略",
    "downtrend": "单调下跌: 100 → -2%/根 × 10, 验证'止损/做空'策略 (现货只能空仓)",
    "vshape":    "V 型: 前 5 根 -3%/根, 后 5 根 +5%/根, 验证 martingale 抄底",
    "sideways":  "震荡: 100 ±3, 验证 mean_reversion 高抛低吸",
}


def _make_dataset(dates, closes) -> pd.DataFrame:
    """把日期+收盘价序列转标准 OHLCV (OHL 围绕 close, volume 固定 1000)"""
    closes = np.array(closes, dtype=float)
    return pd.DataFrame({
        "date": pd.to_datetime(dates),
        "open": closes,
        "high": closes * 1.005,
        "low": closes * 0.995,
        "close": closes,
        "volume": np.full(len(closes), 1000.0),
    })


_DATASETS = {
    "uptrend": _make_dataset(
        [f"2024-01-{i+1:02d}" for i in range(10)],
        # +2% 每根
        [round(100 * (1.02 ** i), 4) for i in range(10)],
    ),
    "downtrend": _make_dataset(
        [f"2024-01-{i+1:02d}" for i in range(10)],
        # -2% 每根
        [round(100 * (0.98 ** i), 4) for i in range(10)],
    ),
    "vshape": _make_dataset(
        [f"2024-01-{i+1:02d}" for i in range(10)],
        # 前 5 根 -3%/根, 后 5 根 +5%/根
        [round(100 * (0.97 ** i), 4) if i < 5
         else round(100 * (0.97 ** 4) * (1.05 ** (i - 4)), 4)
         for i in range(10)],
    ),
    "sideways": _make_dataset(
        [f"2024-01-{i+1:02d}" for i in range(10)],
        # 100 ± 2~6 振荡
        [round(100 + (3 if i % 2 == 0 else -3) * (1 + i % 3), 4)
         for i in range(10)],
    ),
}


def _dataset_summary(df: pd.DataFrame) -> dict:
    """数据集的元信息 (用来前端展示)"""
    return {
        "rows": len(df),
        "start": str(df["date"].iloc[0])[:10],
        "end": str(df["date"].iloc[-1])[:10],
        "first_close": float(df["close"].iloc[0]),
        "last_close": float(df["close"].iloc[-1]),
        "buy_hold_return": float(df["close"].iloc[-1] / df["close"].iloc[0] - 1),
        "max_high": float(df["high"].max()),
        "min_low": float(df["low"].min()),
    }


# ============ Request / Response ============


class VerifyRunRequest(BaseModel):
    code_type: str = Field("dsl", description="dsl | python")
    code: str = Field(..., description="策略代码")
    dataset: str = Field("uptrend", description="内置数据集名: uptrend/downtrend/vshape/sideways/custom")
    custom_data: Optional[dict] = Field(None, description="dataset='custom' 时必填: {dates,open,high,low,close,volume}")
    initial_capital: float = Field(10000.0, ge=0)
    commission_rate: float = Field(0.0004, ge=0)
    slippage: float = Field(0.0005, ge=0)
    position_size: float = Field(1.0, ge=0, le=1)


# ============ 工具: 完整 trace (独立模拟, 每根 bar 精确记录) ============
# 不复用 Backtester.run 的细节, 自己跑一次逐步模拟, 保证 trace 准确可校验
# 与 Backtester.run 同语义: position.shift(1) 避免未来函数, trade = (position 变化), fee = trade * (cr+sl)


def _simulate_trace(df: pd.DataFrame, signal: np.ndarray, *, capital: float,
                    cr: float, sl: float, position_size: float) -> tuple:
    """逐步模拟回测, 返回 (trace, equity_df)

    会计模型 (与 Backtester.run 语义一致, 但显式跟踪 cash/qty):
    - position_size: 仓位比例 (0-1), 表示"花多少现金占总现金的比例"
    - 总花费 = cash * position_size (含手续费, 所以不会让 cash 变负)
    - 买入: cost = cash * position_size, buy_usdt = cost / (1+cr), fee = cost - buy_usdt
            qty = buy_usdt / (price * (1+sl))
            cash -= cost
    - 卖出: proceeds = qty * (price * (1-sl)) * (1-cr), fee = qty * price * (1-sl) * cr
            cash += proceeds, qty = 0
    - 调仓只在前一根 → 当前根的 position 变化时发生

    trace: 每根 bar {bar, date, ohlcv, signal, position_before, position_after, action,
                    trade, qty_before, qty_after, cash_before, cash_after, fee_paid,
                    equity, ret, strategy_ret}
    equity_df: 给 compute_metrics 用的标准 DataFrame
    """
    cash = float(capital)
    qty = 0.0
    avg_price = 0.0
    trace = []
    prev_pos = 0

    for i in range(len(df)):
        row = df.iloc[i]
        date = str(row["date"])[:10]
        price = float(row["close"])
        sig = int(signal[i])
        # shift(1): 用上一根的 signal 当根建仓 (避免未来函数)
        if i == 0:
            pos = 0
        else:
            pos = int(signal[i - 1])
            if pos < 0:
                pos = 0  # 现货只做多, 负数压成空仓

        is_trade = 1 if pos != prev_pos else 0
        fee_paid = 0.0
        action = "hold"
        cash_before = cash
        qty_before = qty

        if is_trade:
            # 先全部卖出 (如果之前持仓)
            if prev_pos == 1 and qty > 0:
                sell_price = price * (1 - sl)
                gross = qty * sell_price
                fee_paid += gross * cr
                proceeds = gross - fee_paid
                cash += proceeds
                qty = 0.0
                avg_price = 0.0
            # 再按 position_size 买入
            if pos == 1:
                cost = cash * position_size          # 总花费 (含手续费)
                if cost > 0:
                    fee = cost * cr / (1 + cr)       # 等价: 手续费 = cost - buy_usdt
                    buy_usdt = cost - fee            # 实际用于买资产的钱
                    buy_price = price * (1 + sl)
                    qty = buy_usdt / buy_price
                    cash -= cost
                    avg_price = buy_price
                    fee_paid += fee
            action = "buy" if pos == 1 else "sell"

        equity = cash + qty * price
        ret = 0.0 if i == 0 else (price / float(df["close"].iloc[i - 1])) - 1
        # 策略收益: 持仓时吃 ret, 否则 0; 调仓时扣 (cr+sl)
        strategy_ret = pos * ret - is_trade * (cr + sl)
        trace.append({
            "bar": i,
            "date": date,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": price,
            "volume": float(row["volume"]),
            "signal": sig,
            "position_before": prev_pos,
            "position_after": pos,
            "action": action,
            "trade": is_trade,
            "qty_before": round(qty_before, 6),
            "qty_after": round(qty, 6),
            "cash_before": round(cash_before, 2),
            "cash_after": round(cash, 2),
            "fee_paid": round(fee_paid, 4),
            "equity": round(equity, 2),
            "ret": round(ret, 6),
            "strategy_ret": round(strategy_ret, 6),
            "avg_price": round(avg_price, 4),
        })
        prev_pos = pos

    equity_df = pd.DataFrame({
        "date": [t["date"] for t in trace],
        "close": [t["close"] for t in trace],
        "equity": [t["equity"] for t in trace],
        "strategy_ret": [t["strategy_ret"] for t in trace],
    })
    return trace, equity_df


def _python_trace(df: pd.DataFrame, result: dict) -> list:
    """Python 沙箱: 把 equity_curve + trades 合并成 trace"""
    eq_curve = result["equity_curve"]
    trades_by_date = {}
    for t in result["trades"]:
        d = str(t["date"])[:10]
        # 同一日期可能多次成交, 按时间顺序
        trades_by_date.setdefault(d, []).append(t)
    out = []
    for i, eq in enumerate(eq_curve):
        row = df.iloc[i]
        d = str(eq["date"])[:10]
        day_trades = trades_by_date.get(d, [])
        # 取最后一笔作为本 bar 主导 action
        if day_trades:
            # 同日 buy + sell: 简化取最后一笔
            last_trade = day_trades[-1]
            action = last_trade["side"]
            fee = float(last_trade["qty"]) * float(last_trade["price"]) * 0.0004
        else:
            action = "hold"
            fee = 0
        out.append({
            "bar": i,
            "date": d,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(eq["price"]),
            "volume": float(row["volume"]),
            "signal": 1 if float(eq["position_qty"]) > 0 else 0,
            "position_before": 1 if day_trades and day_trades[0]["side"] == "sell"
                              and float(eq["position_qty"]) < float(day_trades[0]["qty"]) else 0,
            "position_after": 1 if float(eq["position_qty"]) > 0 else 0,
            "action": action,
            "trade": 1 if day_trades else 0,
            "qty_after": round(float(eq["position_qty"]), 6),
            "cash_after": round(float(eq["cash"]), 2),
            "equity": round(float(eq["equity"]), 2),
            "fee_paid": round(fee, 4),
        })
    return out


# ============ 端点 ============


@router.get("/datasets")
def list_datasets():
    """列出所有内置数据集 + 各自摘要"""
    out = []
    for name, df in _DATASETS.items():
        out.append({
            "id": name,
            "description": _DATASET_DESCRIPTIONS.get(name, ""),
            **_dataset_summary(df),
        })
    return {"datasets": out}


@router.post("/run")
def verify_run(req: VerifyRunRequest):
    """跑验证回测, 返回每根 bar 完整 trace"""
    # 1) 选数据集
    if req.dataset == "custom":
        if not req.custom_data:
            return {"error": "dataset='custom' 必须传 custom_data"}
        try:
            df = pd.DataFrame({
                "date": pd.to_datetime(req.custom_data["dates"]),
                "open":  [float(x) for x in req.custom_data["open"]],
                "high":  [float(x) for x in req.custom_data["high"]],
                "low":   [float(x) for x in req.custom_data["low"]],
                "close": [float(x) for x in req.custom_data["close"]],
                "volume":[float(x) for x in req.custom_data.get("volume",
                                                                [1000]*len(req.custom_data["close"]))],
            })
        except Exception as e:
            return {"error": f"custom_data 格式错误: {e}"}
    else:
        if req.dataset not in _DATASETS:
            return {"error": f"未知数据集: {req.dataset}, 可选 {list(_DATASETS.keys())}"}
        df = _DATASETS[req.dataset].copy()
    if df.empty:
        return {"error": "数据集为空"}
    if len(df) < 2:
        return {"error": "数据集至少需要 2 根 bar 才能跑回测"}

    # 2) 编译策略 + 跑回测
    try:
        if req.code_type == "python":
            py = PythonStrategy(req.code)
            py.compile()
            result = py.run(df, capital=req.initial_capital,
                            commission_rate=req.commission_rate,
                            slippage=req.slippage,
                            primary_symbol="VERIFY", primary_timeframe="1d")
            eq_rows = result["equity_curve"]
            eq_df = pd.DataFrame({
                "date": [r["date"] for r in eq_rows],
                "close": [r["price"] for r in eq_rows],
                "equity": [r["equity"] for r in eq_rows],
                "strategy_ret": pd.Series([r["equity"] for r in eq_rows]).pct_change().fillna(0).tolist(),
            })
            metrics = compute_metrics(eq_df, timeframe="1d")
            trace = _python_trace(df, result)
            trades = result["trades"]
        else:
            # DSL
            signal_fn, rules = StrategyEngine.compile(req.code, {})
            signal = signal_fn(df)
            # 调 simulate_trace 自己逐步模拟 (保证 trace 与 equity 一致)
            signal_arr = signal.values.astype(int)
            trace, equity_df = _simulate_trace(
                df, signal_arr,
                capital=req.initial_capital,
                cr=req.commission_rate, sl=req.slippage,
                position_size=req.position_size,
            )
            metrics = compute_metrics(equity_df, timeframe="1d")
            trades = []
    except Exception as e:
        import traceback
        return {"error": f"策略执行失败: {e}", "traceback": traceback.format_exc()}

    # 3) 组装逐步 log (人类可读)
    log = []
    for t in trace:
        if t["action"] == "hold":
            log.append(
                f"[bar {t['bar']:>2}] {t['date']} close={t['close']:.4f} "
                f"signal={t['signal']} → hold | "
                f"qty={t['qty_after']:.6f} cash={t['cash_after']:.2f} equity={t['equity']:.2f}"
            )
        else:
            log.append(
                f"[bar {t['bar']:>2}] {t['date']} close={t['close']:.4f} "
                f"signal={t['signal']} → {t['action']} "
                f"(pos {t['position_before']}→{t['position_after']}) "
                f"fee={t['fee_paid']:.4f} | "
                f"qty={t['qty_after']:.6f} cash={t['cash_after']:.2f} equity={t['equity']:.2f}"
            )

    # 4) summary
    total_fee = sum(t.get("fee_paid", 0) for t in trace)
    summary = {
        "bars": len(trace),
        "trades": sum(t["trade"] for t in trace),
        "final_equity": trace[-1]["equity"] if trace else req.initial_capital,
        "total_return": metrics.get("total_return", 0),
        "buy_hold_return": float(df["close"].iloc[-1] / df["close"].iloc[0] - 1),
        "fees_paid": round(total_fee, 4),
        "max_drawdown": metrics.get("max_drawdown", 0),
        "sharpe": metrics.get("sharpe", 0),
        "win_rate": metrics.get("win_rate", 0),
    }

    return {
        "dataset": req.dataset,
        "code_type": req.code_type,
        "summary": summary,
        "metrics": {k: round(v, 6) if isinstance(v, float) else v
                    for k, v in metrics.items()},
        "trace": trace,
        "trades": trades,
        "log": log,
        "data_meta": _dataset_summary(df),
    }