"""回测业务层: 调度数据访问 + 策略 + 引擎"""
import os
from datetime import datetime
import numpy as np
import pandas as pd

from quant_core.settings import C
from quant_core.data.access import get_kline, get_many
from quant_core.strategies import get as get_strategy, MomentumRotation
from quant_core.backtest import Backtester, plot_equity
from backend.services.helpers import df_dates, to_records, sanitize, safe


def _benchmark(start: str, end: str, timeframe: str) -> pd.DataFrame:
    df = get_kline("BTCUSDT", timeframe, start, end)
    return df_dates(df, start, end) if not df.empty else df


def _save_chart(equity_df, benchmark_df, title, name):
    chart_dir = C.OUTPUT_DIR if hasattr(C, "OUTPUT_DIR") else os.path.join(C.DATA_DIR.parent, "output")
    os.makedirs(chart_dir, exist_ok=True)
    chart_path = os.path.join(chart_dir, f"{name}.png")
    return plot_equity(equity_df, benchmark_df, title, save=True, save_path=chart_path)


# ===== 单标的回测 =====

def backtest_single(symbol, strategy_id, params, timeframe=None, start=None, end=None,
                    initial_capital=None, commission=None, leverage=1):
    timeframe = timeframe or C.default_timeframe()
    start = start or C.start_date()
    end = end or C.end_date()

    df = get_kline(symbol, timeframe, start, end)
    if df.empty:
        return {"error": f"无 {symbol} 数据"}

    strategy = get_strategy(strategy_id)
    if not hasattr(strategy, "generate"):
        return {"error": f"策略 {strategy_id} 需要使用池子模式 (scan)"}

    sig = strategy.generate(df)
    bt = Backtester(initial_capital=initial_capital, commission=commission)
    result = bt.run(sig, leverage=leverage)
    bench = _benchmark(start, end, timeframe)
    metrics = bt.metrics(result, bench, timeframe)

    title = f"{strategy.name} - {symbol} ({timeframe})"
    chart_b64 = _save_chart(result, bench, title, f"bt_{strategy_id}_{symbol}_{timeframe}")

    return {
        "title": title,
        "symbol": symbol, "strategy": strategy_id, "timeframe": timeframe,
        "metrics": sanitize(metrics),
        "equity": to_records(result),
        "benchmark": to_records(bench.assign(nav=bench["close"] / bench["close"].iloc[0]),
                                 ["date", "nav"]) if not bench.empty else [],
        "chart_base64": chart_b64,
    }


# ===== 池子扫描 =====

def scan_pool(strategy_id, symbols, timeframe=None, start=None, end=None,
              initial_capital=None, commission=None, leverage=1, **params):
    timeframe = timeframe or C.default_timeframe()
    start = start or C.start_date()
    end = end or C.end_date()

    data = get_many(symbols, timeframe, start, end)
    if not data:
        return {"error": "无数据"}

    bt = Backtester(initial_capital=initial_capital, commission=commission)
    strategy = get_strategy(strategy_id)

    ranking = []
    if strategy_id == "momentum_rotation":
        for sym, df in data.items():
            try:
                sig = MomentumRotation(**{k: params[k] for k in ["lookback"] if k in params}).generate(df)
                r = bt.run(sig, leverage=leverage)
                m = bt.metrics(r, timeframe=timeframe)
                ranking.append(_ranking_row(sym, m))
            except Exception as e:
                print(f"[scan] {sym}: {e}")
    else:
        for sym, df in data.items():
            try:
                sig = strategy.generate(df)
                r = bt.run(sig, leverage=leverage)
                m = bt.metrics(r, timeframe=timeframe)
                ranking.append(_ranking_row(sym, m))
            except Exception as e:
                print(f"[scan] {sym}: {e}")

    ranking.sort(key=lambda x: x["sharpe"] if x["sharpe"] is not None else -999, reverse=True)

    combined_df = pd.DataFrame()
    if strategy_id == "momentum_rotation":
        combined_df = MomentumRotation.run_pool(
            data,
            top_n=int(params.get("top_n", 3)),
            hold=int(params.get("hold", 12)),
            lookback=int(params.get("lookback", 24)),
            initial_capital=initial_capital or C.initial_capital(),
            commission=commission or C.commission(),
        )
    else:
        all_eq = []
        for sym, df in data.items():
            sig = strategy.generate(df)
            r = bt.run(sig, leverage=leverage)
            all_eq.append(r.set_index("date")["equity"].rename(sym))
        if all_eq:
            tmp = pd.concat(all_eq, axis=1).ffill().bfill()
            combined_df = pd.DataFrame({"date": tmp.index, "equity": tmp.mean(axis=1).values})
            combined_df["ret"] = combined_df["equity"].pct_change().fillna(0)
            combined_df["strategy_ret"] = combined_df["ret"]

    bench = _benchmark(start, end, timeframe)
    chart_b64 = ""
    combined_metrics = {}
    if not combined_df.empty:
        title = f"币池组合 - {strategy.name} ({len(data)} 个币种)"
        chart_b64 = _save_chart(combined_df, bench, title, f"scan_{strategy_id}_{timeframe}")
        combined_metrics = bt.metrics(combined_df, bench, timeframe)

    return {
        "ranking": ranking, "count": len(ranking),
        "strategy": strategy_id, "timeframe": timeframe,
        "combined_metrics": sanitize(combined_metrics),
        "combined_equity": to_records(combined_df),
        "benchmark": to_records(bench.assign(nav=bench["close"] / bench["close"].iloc[0]),
                                 ["date", "nav"]) if not bench.empty else [],
        "chart_base64": chart_b64,
    }


def _ranking_row(sym, m):
    return {
        "symbol": sym,
        "total_return": safe(m.get("total_return")),
        "annual_return": safe(m.get("annual_return")),
        "sharpe": safe(m.get("sharpe")),
        "calmar": safe(m.get("calmar")),
        "max_drawdown": safe(m.get("max_drawdown")),
        "annual_volatility": safe(m.get("annual_volatility")),
        "win_rate": safe(m.get("win_rate")),
        "trade_bars": int(m.get("trade_bars", 0)),
    }


def safe(v):
    if v is None:
        return None
    if isinstance(v, (np.floating, np.integer)):
        v = float(v)
        if np.isnan(v) or np.isinf(v):
            return None
    return v


# ===== K线 =====

def get_kline_data(symbol, timeframe=None, start=None, end=None):
    import numpy as np
    timeframe = timeframe or C.default_timeframe()
    start = start or C.start_date()
    end = end or datetime.now().strftime("%Y%m%d")

    df = get_kline(symbol, timeframe, start, end)
    if df.empty:
        return {"error": f"无 {symbol} 数据"}

    df = df_dates(df, start, end)
    df["ma7"] = df["close"].rolling(7).mean()
    df["ma25"] = df["close"].rolling(25).mean()
    df["ma99"] = df["close"].rolling(99).mean()
    df = df.dropna(subset=["close"]).reset_index(drop=True)

    return {
        "symbol": symbol, "timeframe": timeframe,
        "kline": to_records(df, ["date", "open", "high", "low", "close", "volume", "ma7", "ma25", "ma99"]),
        "stats": {
            "rows": len(df),
            "start": str(df["date"].iloc[0]),
            "end": str(df["date"].iloc[-1]),
            "first_close": float(df["close"].iloc[0]),
            "last_close": float(df["close"].iloc[-1]),
            "period_return": float(df["close"].iloc[-1] / df["close"].iloc[0] - 1),
            "max_price": float(df["high"].max()),
            "min_price": float(df["low"].min()),
            "avg_volume": float(df["volume"].mean()),
        }
    }


# ===== 筛选 =====

def filter_symbols(params):
    import numpy as np
    timeframe = params.get("timeframe", "1d")
    start = params.get("start_date", C.start_date())
    end = params.get("end_date", C.end_date())
    min_ret = float(params.get("min_return", -1.0))
    max_ret = float(params.get("max_return", 100.0))
    min_price = float(params.get("min_price", 0))
    max_price = float(params.get("max_price", 1e12))
    min_sharpe = float(params.get("min_sharpe", -10))
    strategy_id = params.get("strategy", "ma_cross")
    symbols = params.get("symbols") or C.active_symbols()

    data = get_many(symbols, timeframe, start, end)
    if not data:
        return {"results": [], "count": 0}

    bt = Backtester(initial_capital=10000, commission=0.0004)
    results = []
    strategy = get_strategy(strategy_id)

    for sym, df in data.items():
        if df.empty or len(df) < 50:
            continue
        df = df_dates(df, start, end)
        period_ret = df["close"].iloc[-1] / df["close"].iloc[0] - 1
        last_close = float(df["close"].iloc[-1])
        if not (min_ret <= period_ret <= max_ret):
            continue
        if not (min_price <= last_close <= max_price):
            continue

        sharpe = 0
        try:
            sig = strategy.generate(df)
            r = bt.run(sig)
            m = bt.metrics(r, timeframe=timeframe)
            sharpe = m.get("sharpe", 0) or 0
        except Exception:
            pass

        if sharpe < min_sharpe:
            continue

        results.append({
            "symbol": sym,
            "last_close": round(last_close, 4),
            "period_return": round(period_ret * 100, 2),
            "sharpe": round(sharpe, 2),
        })

    results.sort(key=lambda x: x["sharpe"], reverse=True)
    return {"results": results, "count": len(results)}