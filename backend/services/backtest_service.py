"""K7Quant 回测服务"""
import os
import sys
import base64
import numpy as np
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from quant_core import config
from quant_core.data.fetcher import fetch_all, fetch_one
from quant_core.backtest import (
    Backtester, plot_equity,
    signal_ma_cross, signal_rsi, signal_macd, signal_momentum,
)


STRATEGY_REGISTRY = {
    "ma_cross": {
        "name": "双均线交叉", "icon": "📏",
        "desc": "MA 短上穿长做多，下穿做空。经典趋势策略",
        "params": ["ma_short", "ma_long"],
        "signal": lambda df, p: signal_ma_cross(df, p["ma_short"], p["ma_long"]),
    },
    "momentum_rotation": {
        "name": "动量轮动", "icon": "🚀",
        "desc": "周期选过去 N 根涨幅最高 Top K。强者恒强",
        "params": ["top_n", "hold", "lookback"],
        "signal": None,
    },
    "rsi": {
        "name": "RSI 超买超卖", "icon": "📊",
        "desc": "RSI<超卖线买入，RSI>超买线卖出。震荡市友好",
        "params": ["rsi_period", "rsi_oversold", "rsi_overbought"],
        "signal": lambda df, p: signal_rsi(df, p["rsi_period"], p["rsi_oversold"], p["rsi_overbought"]),
    },
    "macd": {
        "name": "MACD 金叉死叉", "icon": "📈",
        "desc": "MACD 上穿信号线做多，下穿做空",
        "params": ["macd_fast", "macd_slow", "macd_signal"],
        "signal": lambda df, p: signal_macd(df, p["macd_fast"], p["macd_slow"], p["macd_signal"]),
    },
}


def _df_dates(df, start, end):
    if df.empty:
        return df
    if isinstance(start, str):
        start = pd.to_datetime(start)
    if isinstance(end, str):
        end = pd.to_datetime(end)
    return df[(df["date"] >= start) & (df["date"] <= end)].reset_index(drop=True)


def _to_records(df, cols=None):
    if df is None or df.empty:
        return []
    cols = cols or [c for c in df.columns]
    out = []
    for _, r in df.iterrows():
        rec = {}
        for c in cols:
            v = r[c]
            if isinstance(v, (pd.Timestamp,)):
                rec[c] = v.strftime("%Y-%m-%d %H:%M:%S") if v.hour or v.minute else v.strftime("%Y-%m-%d")
            elif isinstance(v, (np.floating, np.integer)):
                rec[c] = float(v) if not np.isnan(v) else None
            elif isinstance(v, float) and np.isnan(v):
                rec[c] = None
            else:
                rec[c] = v
        out.append(rec)
    return out


def _safe(v):
    if v is None:
        return None
    if isinstance(v, (np.floating, np.integer)):
        v = float(v)
        if np.isnan(v) or np.isinf(v):
            return None
    return v


def _sanitize(metrics):
    return {k: _safe(v) for k, v in (metrics or {}).items()}


# ============ 核心: 跑一个币种 ============

def run_one(symbol: str, strategy: str, params: dict, timeframe: str = "4h",
            initial_capital: float = None, commission: float = None,
            leverage: float = 1, start: str = None, end: str = None) -> dict:
    """单标的回测"""
    start = start or config.START_DATE
    end = end or config.END_DATE
    initial_capital = initial_capital or config.DEFAULT_CAPITAL
    commission = commission or config.DEFAULT_COMMISSION

    cache_dir = os.path.join(config.DATA_DIR, timeframe)
    cache_path = os.path.join(cache_dir, f"{symbol}.csv")
    if os.path.exists(cache_path):
        df = pd.read_csv(cache_path, parse_dates=["date"])
    else:
        df = fetch_one(symbol, timeframe, start, end)
        if not df.empty:
            os.makedirs(cache_dir, exist_ok=True)
            df.to_csv(cache_path, index=False)

    if df.empty:
        return {"error": f"无 {symbol} 数据"}

    df = _df_dates(df, start, end)

    if strategy not in STRATEGY_REGISTRY:
        return {"error": f"未知策略: {strategy}"}

    sig_fn = STRATEGY_REGISTRY[strategy]["signal"]
    if sig_fn is None:
        return {"error": f"{strategy} 是池子策略，不支持单标的"}

    sig = sig_fn(df, params)
    bt = Backtester(initial_capital=initial_capital, commission=commission)
    result = bt.run_single(sig, leverage=leverage)
    metrics = bt.metrics(result, timeframe=timeframe)

    bench = _get_benchmark(timeframe, start, end)

    chart_path = os.path.join(config.OUTPUT_DIR, f"bt_{strategy}_{symbol}_{timeframe}.png")
    title = f"{STRATEGY_REGISTRY[strategy]['name']} - {symbol} ({timeframe})"
    plot_equity(result, bench, title, chart_path)

    with open(chart_path, "rb") as f:
        chart_b64 = base64.b64encode(f.read()).decode("utf-8")

    return {
        "title": title,
        "symbol": symbol, "strategy": strategy, "timeframe": timeframe,
        "metrics": _sanitize(metrics),
        "equity": _to_records(result),
        "benchmark": _to_records(bench.assign(nav=bench["close"] / bench["close"].iloc[0]), ["date", "nav"]) if not bench.empty else [],
        "chart_base64": chart_b64,
    }


# ============ 核心: 扫多个币种 ============

def scan_pool(params: dict) -> dict:
    strategy = params["strategy"]
    timeframe = params.get("timeframe", "4h")
    start = params.get("start_date", config.START_DATE)
    end = params.get("end_date", config.END_DATE)
    initial_capital = float(params.get("initial_capital", config.DEFAULT_CAPITAL))
    commission = float(params.get("commission", config.DEFAULT_COMMISSION))
    leverage = float(params.get("leverage", 1))
    symbols = params.get("symbols") or config.SYMBOL_POOL

    data = fetch_all(symbols=symbols, timeframe=timeframe,
                     start=start, end=end, use_cache=True)
    if not data:
        return {"error": "无数据"}

    bt = Backtester(initial_capital=initial_capital, commission=commission)
    ranking = []

    if strategy == "momentum_rotation":
        for sym, df in data.items():
            try:
                sig = signal_momentum(df, int(params.get("lookback", 24)))
                r = bt.run_single(sig, leverage=leverage)
                if r.empty:
                    continue
                m = bt.metrics(r, timeframe=timeframe)
                ranking.append(_ranking_row(sym, m))
            except Exception as e:
                print(f"[scan] {sym}: {e}")
    else:
        sig_fn = STRATEGY_REGISTRY[strategy]["signal"]
        for sym, df in data.items():
            try:
                sig = sig_fn(df, params)
                r = bt.run_single(sig, leverage=leverage)
                if r.empty:
                    continue
                m = bt.metrics(r, timeframe=timeframe)
                ranking.append(_ranking_row(sym, m))
            except Exception as e:
                print(f"[scan] {sym}: {e}")

    ranking.sort(key=lambda x: x["sharpe"] if x["sharpe"] is not None else -999, reverse=True)

    # 组合曲线
    combined_df = pd.DataFrame()
    if strategy == "momentum_rotation":
        combined_df = bt.run_pool_momentum(
            data,
            top_n=int(params.get("top_n", 3)),
            hold=int(params.get("hold", 12)),
            lookback=int(params.get("lookback", 24)),
        )
    else:
        all_eq = []
        for sym, df in data.items():
            sig = STRATEGY_REGISTRY[strategy]["signal"](df, params)
            r = bt.run_single(sig, leverage=leverage)
            all_eq.append(r.set_index("date")["equity"].rename(sym))
        if all_eq:
            tmp = pd.concat(all_eq, axis=1).ffill().bfill()
            combined_df = pd.DataFrame({"date": tmp.index, "equity": tmp.mean(axis=1).values})
            combined_df["ret"] = combined_df["equity"].pct_change().fillna(0)
            combined_df["strategy_ret"] = combined_df["ret"]

    bench = _get_benchmark(timeframe, start, end)
    chart_b64 = ""
    combined_metrics = {}
    if not combined_df.empty:
        chart_path = os.path.join(config.OUTPUT_DIR, f"scan_{strategy}_{timeframe}.png")
        title = f"币圈组合 - {STRATEGY_REGISTRY[strategy]['name']} ({len(data)} 个币)"
        plot_equity(combined_df, bench, title, chart_path)
        with open(chart_path, "rb") as f:
            chart_b64 = base64.b64encode(f.read()).decode("utf-8")
        combined_metrics = bt.metrics(combined_df, bench, timeframe=timeframe)

    return {
        "ranking": ranking, "count": len(ranking),
        "strategy": strategy, "timeframe": timeframe,
        "combined_metrics": _sanitize(combined_metrics),
        "combined_equity": _to_records(combined_df),
        "benchmark": _to_records(bench.assign(nav=bench["close"] / bench["close"].iloc[0]), ["date", "nav"]) if not bench.empty else [],
        "chart_base64": chart_b64,
    }


def _ranking_row(sym, m):
    return {
        "symbol": sym,
        "total_return": _safe(m.get("total_return")),
        "annual_return": _safe(m.get("annual_return")),
        "sharpe": _safe(m.get("sharpe")),
        "max_drawdown": _safe(m.get("max_drawdown")),
        "annual_volatility": _safe(m.get("annual_volatility")),
        "trade_bars": int(m.get("trade_bars", 0)),
    }


def _get_benchmark(timeframe: str, start: str, end: str) -> pd.DataFrame:
    cache_path = os.path.join(config.DATA_DIR, timeframe, "BTCUSDT.csv")
    if os.path.exists(cache_path):
        df = pd.read_csv(cache_path, parse_dates=["date"])
    else:
        df = fetch_one("BTCUSDT", timeframe, start, end)
        if not df.empty:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            df.to_csv(cache_path, index=False)
    return _df_dates(df, start, end) if not df.empty else df


# ============ K 线 ============

def get_kline(symbol: str, timeframe: str = "1d",
              start: str = None, end: str = None) -> dict:
    start = start or config.START_DATE
    end = end or datetime.now().strftime("%Y%m%d")

    cache_path = os.path.join(config.DATA_DIR, timeframe, f"{symbol}.csv")
    if os.path.exists(cache_path):
        df = pd.read_csv(cache_path, parse_dates=["date"])
    else:
        df = fetch_one(symbol, timeframe, start, end)
        if not df.empty:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            df.to_csv(cache_path, index=False)

    if df.empty:
        return {"error": f"无 {symbol} 数据"}

    df = _df_dates(df, start, end)
    df["ma7"] = df["close"].rolling(7).mean()
    df["ma25"] = df["close"].rolling(25).mean()
    df["ma99"] = df["close"].rolling(99).mean()
    df = df.dropna(subset=["close"]).reset_index(drop=True)

    return {
        "symbol": symbol, "timeframe": timeframe,
        "kline": _to_records(df, ["date", "open", "high", "low", "close", "volume", "ma7", "ma25", "ma99"]),
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


# ============ 筛选 ============

def filter_stocks(params: dict) -> dict:
    timeframe = params.get("timeframe", "1d")
    start = params.get("start_date", config.START_DATE)
    end = params.get("end_date", config.END_DATE)
    min_ret = float(params.get("min_return", -1.0))
    max_ret = float(params.get("max_return", 100.0))
    min_price = float(params.get("min_price", 0))
    max_price = float(params.get("max_price", 1e12))
    min_sharpe = float(params.get("min_sharpe", -10))
    strategy = params.get("strategy", "ma_cross")
    symbols = params.get("symbols") or config.SYMBOL_POOL

    data = fetch_all(symbols=symbols, timeframe=timeframe,
                     start=start, end=end, use_cache=True)
    if not data:
        return {"results": [], "count": 0}

    bt = Backtester(initial_capital=10000, commission=0.0004)
    results = []
    sig_fn = STRATEGY_REGISTRY.get(strategy, {}).get("signal")

    for sym, df in data.items():
        if df.empty:
            continue
        df = _df_dates(df, start, end)
        if len(df) < 50:
            continue
        period_ret = df["close"].iloc[-1] / df["close"].iloc[0] - 1
        last_close = float(df["close"].iloc[-1])
        if not (min_ret <= period_ret <= max_ret):
            continue
        if not (min_price <= last_close <= max_price):
            continue

        sharpe = 0
        try:
            if sig_fn:
                sig = sig_fn(df, params)
                r = bt.run_single(sig)
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


# ============ 配置 ============

def get_config() -> dict:
    strategies = []
    for sid, info in STRATEGY_REGISTRY.items():
        strategies.append({
            "id": sid, "name": info["name"], "icon": info["icon"],
            "desc": info["desc"], "params": info["params"],
        })
    return {
        "symbols": config.SYMBOL_POOL,
        "timeframes": config.TIMEFRAMES,
        "default_timeframe": config.DEFAULT_TIMEFRAME,
        "strategies": strategies,
        "default_params": {
            "initial_capital": config.DEFAULT_CAPITAL,
            "commission": config.DEFAULT_COMMISSION,
            "leverage": 1,
            "start_date": config.START_DATE,
            "end_date": config.END_DATE,
            **config.DEFAULT_PARAMS,
        },
    }


def list_data() -> dict:
    if not os.path.isdir(config.DATA_DIR):
        return {"files": []}
    files = []
    for root, _, fns in os.walk(config.DATA_DIR):
        for fn in fns:
            if fn.endswith(".csv"):
                p = os.path.join(root, fn)
                rel = os.path.relpath(p, config.DATA_DIR).replace("\\", "/")
                files.append({
                    "name": rel,
                    "size_kb": round(os.path.getsize(p) / 1024, 1),
                    "mtime": int(os.path.getmtime(p)),
                })
    return {"files": files}