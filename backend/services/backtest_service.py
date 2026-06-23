"""回测业务: 调度数据 + 策略引擎 + 回测器"""
import os
from concurrent.futures import ThreadPoolExecutor
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
from backend.strategy.sandbox import PythonStrategy
from backend.strategy.context import build_ctx_series
from backend.services.helpers import df_dates, to_records, sanitize, safe, fmt


# 并行池大小: 数据读取是 IO bound + pandas 计算 CPU bound, 8 线程足够覆盖小池子
_BT_POOL_WORKERS = min(8, max(2, (os.cpu_count() or 4)))


# ============ 因子查询 ============

def get_kline_data(symbol: str, timeframe: str, start: str, end: str) -> dict:
    """K线 + MA + 统计

    如果用户请求区间超过缓存, 自动 clamp 到缓存范围 (并标记 clamped=True),
    避免「无数据」误报。fetch 失败时直接用缓存。
    """
    df = get_kline(symbol, timeframe, start, end)
    if df.empty:
        return {"error": f"无 {symbol} 数据 (缓存和远端都没有)", "kline": [], "stats": {}}

    # 检测是否需要 clamp: 请求区间超出 df 实际范围
    actual_start = str(df["date"].iloc[0])[:10]
    actual_end = str(df["date"].iloc[-1])[:10]
    clamped = False
    clamp_msg = ""
    if actual_start > start or actual_end < end:
        clamped = True
        clamp_msg = f"缓存仅覆盖 {actual_start}~{actual_end}, 自动截取实际范围"

    df["ma7"] = df["close"].rolling(7).mean()
    df["ma25"] = df["close"].rolling(25).mean()
    df["ma99"] = df["close"].rolling(99).mean()
    df = df.dropna(subset=["close"]).reset_index(drop=True)
    if df.empty:
        return {"error": f"{symbol} 数据全为空", "kline": [], "stats": {}}
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
        },
        "clamped": clamped,
        "clamp_msg": clamp_msg,
        "requested_range": {"start": start, "end": end},
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

    code_type = strategy.get("code_type", "dsl")
    leverage = float(params.get("leverage", 1))
    ctx_tfs = strategy.get("context_timeframes") or []
    ctx_lookback = int(strategy.get("context_lookback") or 20)

    # 构建多 timeframe 上下文 (Python 和 DSL 都用)
    ctx_info = build_ctx_series(df, symbol, timeframe, ctx_tfs, ctx_lookback)
    log.info(f"[backtest_single] context: tfs={ctx_tfs} lookback={ctx_lookback} "
             f"series={len(ctx_info['ctx_series'])}")

    if code_type == "python":
        # Python 策略: 走沙箱 + 自管理仓位
        try:
            py = PythonStrategy(strategy["code"])
            capital = float(params.get("capital") or
                            float(sys_config.get("backtest.initial_capital", 10000)))
            result = py.run(df, capital=capital,
                            primary_symbol=symbol, primary_timeframe=timeframe,
                            ctx_data=ctx_info["ctx_data"])
            # 适配 backtest 引擎的 equity 序列格式
            result_df = _python_result_to_df(df, result, capital=capital)
            rules = {"stop_loss": 0, "take_profit": 0, "position_size": 1.0,
                     "rebalance_bars": 1, "mode": "python",
                     "context_timeframes": ctx_tfs, "context_lookback": ctx_lookback}
        except Exception as e:
            log.error(f"[backtest_single] Python 策略执行失败: {symbol} sid={strategy_id} err={e}")
            return {"error": f"Python 策略执行失败: {e}"}
    else:
        # DSL 策略: 走 signal/position 路径
        try:
            signal_fn, rules = StrategyEngine.compile(
                strategy["code"], params,
                ctx_series=ctx_info["ctx_series"],
                ctx_extra_cols=ctx_info["ctx_extra_cols"],
            )
            # 附加 context 信息到 rules (返回给前端)
            if ctx_tfs:
                rules["context_timeframes"] = ctx_tfs
                rules["context_lookback"] = ctx_lookback
            signal = signal_fn(df)
            if signal.min() < 0:
                position = signal.clip(-1, 1).astype(int)
            else:
                position = (signal > 0).astype(int)
            sig_df = pd.DataFrame({"date": df["date"].values, "close": df["close"].values,
                                   "position": position})
            bt = Backtester()
            result = bt.run(sig_df, leverage=leverage,
                            position_size=rules.get("position_size", 1.0),
                            rebalance_bars=_rebalance_bars(rules))
            result_df = result
        except Exception as e:
            log.error(f"[backtest_single] 策略执行失败: {symbol} sid={strategy_id} err={e}")
            return {"error": f"策略执行失败: {e}"}

    bench = _benchmark(start, end, timeframe)
    metrics = compute_metrics(result_df, bench, timeframe)

    title = f"{strategy['name']} - {symbol} ({timeframe})"
    chart_b64 = _save_chart(result_df, bench, title, f"bt_{strategy_id}_{symbol}_{timeframe}")

    # 保存记录
    try:
        crud.save_backtest_run(strategy["name"], params, metrics)
    except Exception as e:
        log.warning(f"保存回测记录失败: {e}")

    log.info(f"[backtest_single] 完成: {symbol} ({code_type}) ret={fmt(metrics.get('total_return'))} sharpe={fmt(metrics.get('sharpe'), '.2f')}")

    # Python 策略附 trades 给前端展示
    extra = {}
    if code_type == "python":
        extra["trades"] = result["trades"]
        extra["final_state"] = result["final_state"]
        extra["equity_detail"] = result["equity_curve"]

    return {
        "title": title,
        "symbol": symbol, "strategy_id": strategy_id, "timeframe": timeframe,
        "code_type": code_type,
        "metrics": sanitize(metrics),
        "equity": to_records(result_df),
        "benchmark": to_records(bench.assign(nav=bench["close"] / bench["close"].iloc[0]),
                                 ["date", "nav"]) if not bench.empty else [],
        "chart_base64": chart_b64,
        "rules": rules,
        **extra,
    }


def backtest_with_code(symbol: str, code: str, params: dict,
                       timeframe: str = None, start: str = None, end: str = None,
                       code_type: str = "dsl") -> dict:
    """用传入的策略代码临时跑 (不存 DB)"""
    timeframe = timeframe or sys_config.get("backtest.default_timeframe", "4h")
    start = start or sys_config.get("backtest.start_date", "20240101")
    end = end or _resolve_end()
    leverage = float(params.get("leverage", 1))

    df = get_kline(symbol, timeframe, start, end)
    if df.empty:
        return {"error": f"无 {symbol} 数据"}

    if code_type == "python":
        try:
            py = PythonStrategy(code)
            capital = float(params.get("capital") or
                            float(sys_config.get("backtest.initial_capital", 10000)))
            # code 模式下没有 strategy 记录, 接受参数 context_tfs (前端可传)
            ctx_tfs = params.get("context_timeframes") or []
            ctx_lookback = int(params.get("context_lookback") or 20)
            ctx_info = build_ctx_series(df, symbol, timeframe, ctx_tfs, ctx_lookback)
            result = py.run(df, capital=capital,
                            primary_symbol=symbol, primary_timeframe=timeframe,
                            ctx_data=ctx_info["ctx_data"])
            result_df = _python_result_to_df(df, result, capital=capital)
            rules = {"stop_loss": 0, "take_profit": 0, "position_size": 1.0,
                     "rebalance_bars": 1, "mode": "python",
                     "context_timeframes": ctx_tfs, "context_lookback": ctx_lookback}
        except Exception as e:
            import traceback
            log.error(f"[backtest_with_code python] {e}\n{traceback.format_exc()}")
            return {"error": f"Python 策略执行失败: {e}"}
    else:
        try:
            ctx_tfs = params.get("context_timeframes") or []
            ctx_lookback = int(params.get("context_lookback") or 20)
            ctx_info = build_ctx_series(df, symbol, timeframe, ctx_tfs, ctx_lookback)
            signal_fn, rules = StrategyEngine.compile(
                code, params,
                ctx_series=ctx_info["ctx_series"],
                ctx_extra_cols=ctx_info["ctx_extra_cols"],
            )
            signal = signal_fn(df)
            if signal.min() < 0:
                position = signal.clip(-1, 1).astype(int)
            else:
                position = (signal > 0).astype(int)
            sig_df = pd.DataFrame({"date": df["date"].values, "close": df["close"].values,
                                   "position": position})
            bt = Backtester()
            result_df = bt.run(sig_df, leverage=leverage,
                               position_size=rules.get("position_size", 1.0),
                               rebalance_bars=_rebalance_bars(rules))
        except Exception as e:
            return {"error": f"策略执行失败: {e}"}

    bench = _benchmark(start, end, timeframe)
    metrics = compute_metrics(result_df, bench, timeframe)

    title = f"自定义策略 - {symbol} ({timeframe})"
    chart_b64 = _save_chart(result_df, bench, title, f"bt_custom_{symbol}_{timeframe}")

    extra = {}
    if code_type == "python":
        extra["trades"] = result["trades"]
        extra["final_state"] = result["final_state"]
        extra["equity_detail"] = result["equity_curve"]
        extra["code_type"] = "python"

    return {
        "title": title,
        "symbol": symbol, "timeframe": timeframe,
        "code_type": code_type,
        "metrics": sanitize(metrics),
        "equity": to_records(result_df),
        "benchmark": to_records(bench.assign(nav=bench["close"] / bench["close"].iloc[0]),
                                 ["date", "nav"]) if not bench.empty else [],
        "chart_base64": chart_b64,
        "rules": rules,
        **extra,
    }


# ============ 池子扫描 ============

def _backtest_one_symbol(sym: str, df: pd.DataFrame, code: str, params: dict,
                         timeframe: str, position_size: float, leverage: float,
                         rebalance_bars: int, code_type: str = "dsl",
                         ctx_tfs: list = None, ctx_lookback: int = 20) -> Optional[dict]:
    """单币回测 (线程安全, 无副作用)。
    返回: {"symbol", "metrics": {...}, "equity": pd.Series(dtype=float)} 或 None(失败)
    """
    try:
        if code_type == "python":
            py = PythonStrategy(code)
            capital = float(params.get("capital") or
                            float(sys_config.get("backtest.initial_capital", 10000)))
            ctx_info = build_ctx_series(df, sym, timeframe, ctx_tfs or [], ctx_lookback)
            result = py.run(df, capital=capital,
                            primary_symbol=sym, primary_timeframe=timeframe,
                            ctx_data=ctx_info["ctx_data"])
            r = _python_result_to_df(df, result, capital=capital)
        else:
            ctx_info = build_ctx_series(df, sym, timeframe, ctx_tfs or [], ctx_lookback)
            signal_fn, rules = StrategyEngine.compile(
                code, params,
                ctx_series=ctx_info["ctx_series"],
                ctx_extra_cols=ctx_info["ctx_extra_cols"],
            )
            signal = signal_fn(df)
            if hasattr(signal, "min") and signal.min() < 0:
                position = signal.clip(-1, 1).astype(int)
            else:
                position = (signal > 0).astype(int)
            sig_df = pd.DataFrame({
                "date": df["date"].values,
                "close": df["close"].values,
                "position": position,
            })
            bt = Backtester()
            r = bt.run(sig_df, leverage=leverage, position_size=position_size,
                       rebalance_bars=rebalance_bars)
        m = compute_metrics(r, timeframe=timeframe)
        return {
            "symbol": sym,
            "metrics": m,
            "equity": r.set_index("date")["equity"],
        }
    except Exception as e:
        log.warning(f"[backtest_one] {sym} 失败: {e}")
        return None


def _python_result_to_df(df: pd.DataFrame, result: dict, capital: float) -> pd.DataFrame:
    """把 PythonStrategy.run() 的输出转成跟 Backtester 一致的 equity DataFrame,
    让 compute_metrics 可以无缝处理。
    """
    eq = result["equity_curve"]
    out = pd.DataFrame({
        "date": [e["date"] for e in eq],
        "close": [e["price"] for e in eq],
        "equity": [e["equity"] for e in eq],
    })
    out["ret"] = out["equity"].pct_change().fillna(0)
    out["strategy_ret"] = out["ret"]
    out["position"] = 0
    out["trade"] = 0
    return out


def scan_pool(strategy_id: int, symbols: list = None, weights: dict = None,
              timeframe: str = None, start: str = None, end: str = None,
              params: dict = None) -> dict:
    """对所有币种跑同一策略, 返回排名 + 组合
    weights: {symbol: weight}, None 或空 = 等权
    优化: 每币种只跑一次回测, ThreadPoolExecutor 并行
    """
    from backend.storage import crud
    params = params or {}
    import time as _time
    t0 = _time.time()

    timeframe = timeframe or sys_config.get("backtest.default_timeframe", "4h")
    start = start or sys_config.get("backtest.start_date", "20240101")
    end = end or _resolve_end()

    if not symbols:
        symbols = _active_symbols()
    # 解析权重: 没填的币种 = 等权(1.0)
    weights = weights or {}
    norm_weights = {s: float(weights.get(s, 1.0)) for s in symbols}
    total_w = sum(norm_weights.values()) or 1.0
    norm_weights = {s: w / total_w for s, w in norm_weights.items()}
    weight_label = "等权" if not weights or all(v == 1.0 for v in weights.values()) else "自定义权重"

    log.info(f"[scan_pool] 开始: sid={strategy_id} tf={timeframe} range={start}..{end} pool={len(symbols)} symbols ({weight_label})")
    data = get_many(symbols, timeframe, start, end)
    if not data:
        log.warning(f"[scan_pool] 无数据: pool={len(symbols)}")
        return {"error": "无数据"}
    log.info(f"[scan_pool] 数据就绪: {len(data)}/{len(symbols)} 个币种")

    strategy = crud.get_strategy(strategy_id)
    if not strategy:
        log.warning(f"[scan_pool] 策略不存在: id={strategy_id}")
        return {"error": f"策略 ID {strategy_id} 不存在"}

    try:
        position_size = float(params.get("position_size", 1.0)) or 1.0
        leverage = float(params.get("leverage", 1))
        rebalance_bars = sys_config.get("backtest.rebalance_bars", 1) or 1
    except Exception:
        position_size, leverage, rebalance_bars = 1.0, 1.0, 1

    # 并行回测 (每币种只跑一次, 同时拿到 metrics + equity)
    items = list(data.items())
    results = [None] * len(items)
    code_type = strategy.get("code_type", "dsl")
    ctx_tfs = strategy.get("context_timeframes") or []
    ctx_lookback = int(strategy.get("context_lookback") or 20)
    with ThreadPoolExecutor(max_workers=_BT_POOL_WORKERS) as ex:
        futures = {
            ex.submit(
                _backtest_one_symbol, sym, df, strategy["code"], params, timeframe,
                position_size, leverage, rebalance_bars, code_type,
                ctx_tfs, ctx_lookback,
            ): i
            for i, (sym, df) in enumerate(items)
        }
        for fut in futures:
            results[futures[fut]] = fut.result()

    # 汇总
    ranking = []
    all_eq = []
    success = fail = 0
    for i, r in enumerate(results):
        if r is None:
            fail += 1
            continue
        success += 1
        ranking.append(_ranking_row(r["symbol"], r["metrics"]))
        w = norm_weights.get(r["symbol"], 1.0 / len(items))
        all_eq.append((r["equity"] * w).rename(r["symbol"]))

    ranking.sort(key=lambda x: x["sharpe"] if x["sharpe"] is not None else -999, reverse=True)
    log.info(f"[scan_pool] 单币回测完成: 成功 {success}, 失败 {fail}, 线程={_BT_POOL_WORKERS}")

    combined_df = pd.DataFrame()
    if all_eq:
        tmp = pd.concat(all_eq, axis=1).ffill().bfill()
        combined_df = pd.DataFrame({"date": tmp.index, "equity": tmp.sum(axis=1).values})
        combined_df["ret"] = combined_df["equity"].pct_change().fillna(0)
        combined_df["strategy_ret"] = combined_df["ret"]

    bench = _benchmark(start, end, timeframe)
    chart_b64 = ""
    combined_metrics = {}
    if not combined_df.empty:
        title = f"币池组合 - {strategy['name']} ({len(data)} 个币种, {weight_label})"
        chart_b64 = _save_chart(combined_df, bench, title, f"scan_{strategy_id}_{timeframe}")
        combined_metrics = compute_metrics(combined_df, bench, timeframe)

    elapsed = _time.time() - t0
    log.info(f"[scan_pool] 完成: {len(ranking)} 个排名, 组合收益={fmt(combined_metrics.get('total_return'))}, 耗时 {elapsed:.2f}s")

    return {
        "ranking": ranking, "count": len(ranking),
        "strategy_id": strategy_id, "strategy_name": strategy["name"],
        "timeframe": timeframe, "weight_mode": weight_label,
        "weights": norm_weights,
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

    strategy = None
    strategy_code = ""
    strategy_code_type = "dsl"
    strategy_ctx_tfs = []
    strategy_ctx_lookback = 20
    if strategy_id:
        from backend.storage import crud
        strategy = crud.get_strategy(strategy_id)
        if not strategy:
            return {"error": f"策略 ID {strategy_id} 不存在"}
        strategy_code = strategy["code"]
        strategy_code_type = strategy.get("code_type", "dsl")
        strategy_ctx_tfs = strategy.get("context_timeframes") or []
        strategy_ctx_lookback = int(strategy.get("context_lookback") or 20)

    items = list(data.items())
    results = []

    def _eval_one(sym_df):
        sym, df = sym_df
        if df.empty or len(df) < 30:
            return None
        dff = df_dates(df, start, end)
        if len(dff) < 2:
            return None
        period_ret = dff["close"].iloc[-1] / dff["close"].iloc[0] - 1
        last_close = float(dff["close"].iloc[-1])
        if not (min_ret <= period_ret <= max_ret):
            return None
        if not (min_price <= last_close <= max_price):
            return None

        if strategy:
            r = _backtest_one_symbol(
                sym, dff, strategy_code, params, timeframe,
                float(params.get("position_size", 1.0) or 1.0),
                float(params.get("leverage", 1)),
                _rebalance_bars({"rebalance_bars": sys_config.get("backtest.rebalance_bars", 1)}),
                strategy_code_type,
                strategy_ctx_tfs, strategy_ctx_lookback,
            )
            if r is None:
                return None
            sharpe = r["metrics"].get("sharpe") or 0
            if sharpe < min_sharpe:
                return None
            return {
                "symbol": sym, "last_close": round(last_close, 4),
                "period_return": round(period_ret * 100, 2),
                "sharpe": round(float(sharpe), 2),
            }
        return {
            "symbol": sym, "last_close": round(last_close, 4),
            "period_return": round(period_ret * 100, 2),
            "sharpe": None,
        }

    # 1) 简单过滤 (无策略) 直接顺序处理, 避免线程开销
    if not strategy:
        for it in items:
            r = _eval_one(it)
            if r:
                results.append(r)
    else:
        # 2) 有策略时并行回测
        with ThreadPoolExecutor(max_workers=_BT_POOL_WORKERS) as ex:
            for r in ex.map(_eval_one, items):
                if r:
                    results.append(r)

    results.sort(key=lambda x: (x.get("sharpe") is None, -(x.get("sharpe") or -999)))
    return {"results": results, "count": len(results)}


# ============ helpers ============

def _benchmark(start, end, timeframe):
    df = get_kline("BTCUSDT", timeframe, start, end)
    return df_dates(df, start, end) if not df.empty else df


def _save_chart(equity_df, benchmark_df, title, name):
    """生成净值图 base64; matplotlib 失败不影响回测主流程"""
    os.makedirs(EXPORT_DIR, exist_ok=True)
    chart_path = os.path.join(EXPORT_DIR, f"{name}.png")
    try:
        return plot_equity(equity_df, benchmark_df, title, save_path=chart_path)
    except Exception as e:
        log.warning(f"[_save_chart] matplotlib 失败 (不影响回测): {e}")
        return ""


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