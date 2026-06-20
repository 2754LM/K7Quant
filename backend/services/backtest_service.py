"""回测业务: 调度数据 + 策略引擎 + 回测器"""
import os
from datetime import datetime
from typing import Optional
import numpy as np
import pandas as pd

from backend.core import EXPORT_DIR
from backend.core import config as sys_config
from backend.core.logger import log
from backend.data.access import get_kline, get_many
from backend.backtest import Backtester, compute_metrics, plot_equity
from backend.strategy import StrategyEngine
from backend.services.helpers import df_dates, to_records, sanitize, safe


# ============ 因子查询 ============

def get_kline_data(symbol: str, timeframe: str, start: str, end: str) -> dict:
    """K线 + MA + 统计"""
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
        "kline": to_records(df, ["date", "open", "high", "low", "close", "volume",
                                  "ma7", "ma25", "ma99"]),
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


# ============ 单标的回测 ============

def backtest_single(symbol: str, strategy_id: int, params: dict,
                    timeframe: str = None, start: str = None, end: str = None) -> dict:
    """根据 strategy_id 从 DB 加载策略, 跑单标的"""
    from backend.storage import crud

    timeframe = timeframe or sys_config.get("backtest.default_timeframe", "4h")
    start = start or sys_config.get("backtest.start_date", "20240101")
    end = end or _resolve_end()

    log.info(f"[backtest_single] 开始: symbol={symbol} tf={timeframe} range={start}..{end} sid={strategy_id}")

    df = get_kline(symbol, timeframe, start, end)
    if df.empty:
        log.warning(f"[backtest_single] 无数据: {symbol} {timeframe}")
        return {"error": f"无 {symbol} 数据"}

    strategy = crud.get_strategy(strategy_id)
    if not strategy:
        log.warning(f"[backtest_single] 策略不存在: id={strategy_id}")
        return {"error": f"策略 ID {strategy_id} 不存在"}

    try:
        signal_fn, rules = StrategyEngine.compile(strategy["code"], params)
        signal = signal_fn(df)
        # 把 signal 转成 position 0/1
        if signal.min() < 0:
            # 允许做空: -1/0/1
            position = signal.clip(-1, 1).astype(int)
        else:
            position = (signal > 0).astype(int)

        sig_df = pd.DataFrame({"date": df["date"].values, "close": df["close"].values,
                               "position": position})
    except Exception as e:
        log.error(f"[backtest_single] 策略执行失败: {symbol} sid={strategy_id} err={e}")
        return {"error": f"策略执行失败: {e}"}

    bt = Backtester()
    leverage = float(params.get("leverage", 1))
    position_size = rules.get("position_size", 1.0)
    result = bt.run(sig_df, leverage=leverage, position_size=position_size,
                    rebalance_bars=_rebalance_bars(rules))
    bench = _benchmark(start, end, timeframe)
    metrics = compute_metrics(result, bench, timeframe)

    title = f"{strategy['name']} - {symbol} ({timeframe})"
    chart_b64 = _save_chart(result, bench, title, f"bt_{strategy_id}_{symbol}_{timeframe}")

    # 保存记录
    try:
        crud.save_backtest_run(strategy["name"], params, metrics)
    except Exception as e:
        log.warning(f"保存回测记录失败: {e}")

    log.info(f"[backtest_single] 完成: {symbol} ret={safe(metrics.get('total_return')):.4f} sharpe={safe(metrics.get('sharpe')):.2f}")

    return {
        "title": title,
        "symbol": symbol, "strategy_id": strategy_id, "timeframe": timeframe,
        "metrics": sanitize(metrics),
        "equity": to_records(result),
        "benchmark": to_records(bench.assign(nav=bench["close"] / bench["close"].iloc[0]),
                                 ["date", "nav"]) if not bench.empty else [],
        "chart_base64": chart_b64,
        "rules": rules,
    }


def backtest_with_code(symbol: str, code: str, params: dict,
                       timeframe: str = None, start: str = None, end: str = None) -> dict:
    """用传入的策略代码临时跑 (不存 DB)"""
    timeframe = timeframe or sys_config.get("backtest.default_timeframe", "4h")
    start = start or sys_config.get("backtest.start_date", "20240101")
    end = end or _resolve_end()

    df = get_kline(symbol, timeframe, start, end)
    if df.empty:
        return {"error": f"无 {symbol} 数据"}

    try:
        signal_fn, rules = StrategyEngine.compile(code, params)
        signal = signal_fn(df)
        if signal.min() < 0:
            position = signal.clip(-1, 1).astype(int)
        else:
            position = (signal > 0).astype(int)
        sig_df = pd.DataFrame({"date": df["date"].values, "close": df["close"].values,
                               "position": position})
    except Exception as e:
        return {"error": f"策略执行失败: {e}"}

    bt = Backtester()
    leverage = float(params.get("leverage", 1))
    position_size = rules.get("position_size", 1.0)
    result = bt.run(sig_df, leverage=leverage, position_size=position_size,
                    rebalance_bars=_rebalance_bars(rules))
    bench = _benchmark(start, end, timeframe)
    metrics = compute_metrics(result, bench, timeframe)

    title = f"自定义策略 - {symbol} ({timeframe})"
    chart_b64 = _save_chart(result, bench, title, f"bt_custom_{symbol}_{timeframe}")

    return {
        "title": title,
        "symbol": symbol, "timeframe": timeframe,
        "metrics": sanitize(metrics),
        "equity": to_records(result),
        "benchmark": to_records(bench.assign(nav=bench["close"] / bench["close"].iloc[0]),
                                 ["date", "nav"]) if not bench.empty else [],
        "chart_base64": chart_b64,
        "rules": rules,
    }


# ============ 池子扫描 ============

def scan_pool(strategy_id: int, symbols: list = None, timeframe: str = None,
              start: str = None, end: str = None, params: dict = None) -> dict:
    """对所有币种跑同一策略, 返回排名 + 组合"""
    from backend.storage import crud
    params = params or {}
    import time as _time
    t0 = _time.time()

    timeframe = timeframe or sys_config.get("backtest.default_timeframe", "4h")
    start = start or sys_config.get("backtest.start_date", "20240101")
    end = end or _resolve_end()

    if not symbols:
        symbols = _active_symbols()
    log.info(f"[scan_pool] 开始: sid={strategy_id} tf={timeframe} range={start}..{end} pool={len(symbols)} symbols")
    data = get_many(symbols, timeframe, start, end)
    if not data:
        log.warning(f"[scan_pool] 无数据: pool={len(symbols)}")
        return {"error": "无数据"}
    log.info(f"[scan_pool] 数据就绪: {len(data)}/{len(symbols)} 个币种")

    strategy = crud.get_strategy(strategy_id)
    if not strategy:
        log.warning(f"[scan_pool] 策略不存在: id={strategy_id}")
        return {"error": f"策略 ID {strategy_id} 不存在"}

    bt = Backtester()
    ranking = []

    try:
        signal_fn, rules = StrategyEngine.compile(strategy["code"], params)
        position_size = rules.get("position_size", 1.0)
        leverage = float(params.get("leverage", 1))
    except Exception as e:
        log.error(f"[scan_pool] 策略编译失败: {e}")
        return {"error": f"策略编译失败: {e}"}

    success_count = 0
    fail_count = 0
    for sym, df in data.items():
        try:
            signal = signal_fn(df)
            if signal.min() < 0:
                position = signal.clip(-1, 1).astype(int)
            else:
                position = (signal > 0).astype(int)
            sig_df = pd.DataFrame({"date": df["date"].values, "close": df["close"].values,
                                   "position": position})
            r = bt.run(sig_df, leverage=leverage, position_size=position_size,
                       rebalance_bars=_rebalance_bars(rules))
            m = compute_metrics(r, timeframe=timeframe)
            ranking.append(_ranking_row(sym, m))
            success_count += 1
        except Exception as e:
            log.warning(f"[scan_pool] {sym} 失败: {e}")
            fail_count += 1

    ranking.sort(key=lambda x: x["sharpe"] if x["sharpe"] is not None else -999, reverse=True)
    log.info(f"[scan_pool] 单币回测完成: 成功 {success_count}, 失败 {fail_count}")

    # 组合曲线 (等权平均)
    combined_df = pd.DataFrame()
    all_eq = []
    for sym, df in data.items():
        try:
            signal = signal_fn(df)
            if signal.min() < 0:
                position = signal.clip(-1, 1).astype(int)
            else:
                position = (signal > 0).astype(int)
            sig_df = pd.DataFrame({"date": df["date"].values, "close": df["close"].values,
                                   "position": position})
            r = bt.run(sig_df, leverage=leverage, position_size=position_size,
                       rebalance_bars=_rebalance_bars(rules))
            all_eq.append(r.set_index("date")["equity"].rename(sym))
        except Exception:
            continue
    if all_eq:
        tmp = pd.concat(all_eq, axis=1).ffill().bfill()
        combined_df = pd.DataFrame({"date": tmp.index, "equity": tmp.mean(axis=1).values})
        combined_df["ret"] = combined_df["equity"].pct_change().fillna(0)
        combined_df["strategy_ret"] = combined_df["ret"]

    bench = _benchmark(start, end, timeframe)
    chart_b64 = ""
    combined_metrics = {}
    if not combined_df.empty:
        title = f"币池组合 - {strategy['name']} ({len(data)} 个币种)"
        chart_b64 = _save_chart(combined_df, bench, title, f"scan_{strategy_id}_{timeframe}")
        combined_metrics = compute_metrics(combined_df, bench, timeframe)

    elapsed = _time.time() - t0
    log.info(f"[scan_pool] 完成: {len(ranking)} 个排名, 组合收益={safe(combined_metrics.get('total_return')):.4f}, 耗时 {elapsed:.2f}s")

    return {
        "ranking": ranking, "count": len(ranking),
        "strategy_id": strategy_id, "strategy_name": strategy["name"],
        "timeframe": timeframe,
        "combined_metrics": sanitize(combined_metrics),
        "combined_equity": to_records(combined_df),
        "benchmark": to_records(bench.assign(nav=bench["close"] / bench["close"].iloc[0]),
                                 ["date", "nav"]) if not bench.empty else [],
        "chart_base64": chart_b64,
    }


# ============ 筛选 ============

def filter_symbols(params: dict) -> dict:
    timeframe = params.get("timeframe", "1d")
    start = params.get("start_date", sys_config.get("backtest.start_date", "20240101"))
    end = params.get("end_date", _resolve_end())
    min_ret = float(params.get("min_return", -1.0))
    max_ret = float(params.get("max_return", 100.0))
    min_price = float(params.get("min_price", 0))
    max_price = float(params.get("max_price", 1e12))
    min_sharpe = float(params.get("min_sharpe", -10))
    strategy_id = params.get("strategy_id")
    symbols = params.get("symbols") or _active_symbols()

    data = get_many(symbols, timeframe, start, end)
    if not data:
        return {"results": [], "count": 0}

    results = []
    strategy = None
    if strategy_id:
        from backend.storage import crud
        strategy = crud.get_strategy(strategy_id)

    if strategy:
        try:
            signal_fn, rules = StrategyEngine.compile(strategy["code"], params)
        except Exception as e:
            return {"error": f"策略编译失败: {e}"}
        bt = Backtester()
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
                signal = signal_fn(df)
                if signal.min() < 0:
                    position = signal.clip(-1, 1).astype(int)
                else:
                    position = (signal > 0).astype(int)
                sig_df = pd.DataFrame({"date": df["date"].values, "close": df["close"].values,
                                       "position": position})
                r = bt.run(sig_df, position_size=rules.get("position_size", 1.0),
                           rebalance_bars=_rebalance_bars(rules))
                m = compute_metrics(r, timeframe=timeframe)
                sharpe = m.get("sharpe", 0) or 0
            except Exception:
                pass
            if sharpe < min_sharpe:
                continue
            results.append({
                "symbol": sym, "last_close": round(last_close, 4),
                "period_return": round(period_ret * 100, 2),
                "sharpe": round(sharpe, 2),
            })
    else:
        # 不跑策略, 只按价格/涨幅过滤
        for sym, df in data.items():
            if df.empty or len(df) < 30:
                continue
            df = df_dates(df, start, end)
            period_ret = df["close"].iloc[-1] / df["close"].iloc[0] - 1
            last_close = float(df["close"].iloc[-1])
            if not (min_ret <= period_ret <= max_ret):
                continue
            if not (min_price <= last_close <= max_price):
                continue
            results.append({
                "symbol": sym, "last_close": round(last_close, 4),
                "period_return": round(period_ret * 100, 2),
                "sharpe": None,
            })

    results.sort(key=lambda x: x.get("sharpe") or -999, reverse=True)
    return {"results": results, "count": len(results)}


# ============ helpers ============

def _benchmark(start, end, timeframe):
    df = get_kline("BTCUSDT", timeframe, start, end)
    return df_dates(df, start, end) if not df.empty else df


def _save_chart(equity_df, benchmark_df, title, name):
    os.makedirs(EXPORT_DIR, exist_ok=True)
    chart_path = os.path.join(EXPORT_DIR, f"{name}.png")
    return plot_equity(equity_df, benchmark_df, title, save_path=chart_path)


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


def _resolve_end():
    v = sys_config.get("backtest.end_date", "auto")
    if v == "auto":
        return datetime.now().strftime("%Y%m%d")
    return v


def _rebalance_bars(rules: dict) -> int:
    """调仓频率: 优先用策略 DSL 的 `频率=N`, 否则回退到配置中心 backtest.rebalance_bars"""
    return int(rules.get("rebalance_bars") or sys_config.get("backtest.rebalance_bars", 1) or 1)


def _active_symbols():
    from backend.storage import crud
    syms = [s["symbol"] for s in crud.list_symbols(active_only=True)]
    return syms or ["BTCUSDT", "ETHUSDT"]