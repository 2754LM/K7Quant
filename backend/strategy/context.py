"""多 timeframe 上下文数据: 给 Python 沙箱和 DSL 编译用

ctx_series 设计:
  - 对每个 context timeframe (如 "15m", "1h"), 拉取主图区间内的 K 线
  - 对每根主图 bar, 计算截至该 bar 时间的最近 1 根 + 最近 N 根的统计
  - 输出 dict {name: Series (与主图 df 等长, 等索引)}

可用变量名 (DSL):
  - ctx_15m_close      最新 15m 收盘价 (截至主 bar 时间)
  - ctx_15m_open       最新 15m 开盘价
  - ctx_15m_high       最新 15m 最高价
  - ctx_15m_low        最新 15m 最低价
  - ctx_15m_volume     最新 15m 成交量
  - ctx_15m_ma20       最近 20 根 15m close 均值 (n = context_lookback)
  - ctx_15m_max20      最近 20 根 15m close 最大值
  - ctx_15m_min20      最近 20 根 15m close 最小值
  - ctx_15m_std20      最近 20 根 15m close 标准差
  - ctx_15m_sum20      最近 20 根 15m volume 总和 (用 vol 列计算)
"""
from __future__ import annotations
import pandas as pd
from typing import Optional


def build_ctx_series(
    main_df: pd.DataFrame,
    symbol: str,
    primary_timeframe: str,
    context_timeframes: list,
    context_lookback: int = 20,
) -> dict:
    """构建多 timeframe 上下文 Series 字典

    Returns:
        {
            "ctx_series": {name: pd.Series},  # 注入 DSL 沙箱
            "ctx_extra_cols": {name, ...},     # 名字集合, 给 AST 校验
            "ctx_data": {timeframe: pd.DataFrame},  # 给 Python 沙箱 (raw K 线)
        }
    """
    ctx_series: dict = {}
    ctx_extra_cols: set = set()
    ctx_data: dict = {}

    if not context_timeframes:
        return {"ctx_series": ctx_series, "ctx_extra_cols": ctx_extra_cols,
                "ctx_data": ctx_data}

    # 拉主图区间
    if len(main_df) == 0:
        return {"ctx_series": ctx_series, "ctx_extra_cols": ctx_extra_cols,
                "ctx_data": ctx_data}
    start = str(main_df["date"].iloc[0])[:10].replace("-", "")
    end = str(main_df["date"].iloc[-1])[:10].replace("-", "")

    from backend.data.access import get_kline
    from backend.core.logger import log

    for tf in context_timeframes:
        if tf == primary_timeframe:
            # 跳过主图
            continue
        try:
            tdf = get_kline(symbol, tf, start, end)
        except Exception as e:
            log.warning(f"[ctx_series] 加载 {symbol} {tf} 失败: {e}")
            tdf = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])
        if tdf is None or tdf.empty:
            tdf = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])
        ctx_data[tf] = tdf
        # 计算 context Series
        _compute_ctx_for_tf(main_df, tdf, tf, context_lookback, ctx_series, ctx_extra_cols)

    return {"ctx_series": ctx_series, "ctx_extra_cols": ctx_extra_cols,
            "ctx_data": ctx_data}


def _compute_ctx_for_tf(
    main_df: pd.DataFrame,
    ctx_df: pd.DataFrame,
    tf: str,
    n: int,
    out_series: dict,
    out_cols: set,
):
    """对单个 context timeframe 计算各种 ctx_* Series"""
    if ctx_df is None or ctx_df.empty:
        # 全部 NaN
        for col in ("close", "open", "high", "low", "volume"):
            name = f"ctx_{_tf_name(tf)}_{col}"
            out_series[name] = pd.Series([float("nan")] * len(main_df), index=main_df.index)
            out_cols.add(name)
        for stat in ("ma", "max", "min", "std", "sum"):
            name = f"ctx_{_tf_name(tf)}_{stat}{n}"
            out_series[name] = pd.Series([float("nan")] * len(main_df), index=main_df.index)
            out_cols.add(name)
        return

    # 主图时间是字符串, 转 datetime 排序
    main_times = pd.to_datetime(main_df["date"].astype(str))
    ctx_times = pd.to_datetime(ctx_df["date"].astype(str))
    ctx_df_sorted = ctx_df.assign(_t=ctx_times).sort_values("_t").reset_index(drop=True)
    ctx_close = ctx_df_sorted["close"].values
    ctx_high = ctx_df_sorted["high"].values
    ctx_low = ctx_df_sorted["low"].values
    ctx_open = ctx_df_sorted["open"].values
    ctx_volume = ctx_df_sorted["volume"].values
    ctx_t = ctx_df_sorted["_t"].values

    tf_n = _tf_name(tf)

    # 1) 单值 Series (最新一根)
    latest_close = []
    latest_open = []
    latest_high = []
    latest_low = []
    latest_volume = []
    for mt in main_times:
        # 找 ctx 中时间 <= mt 的最后一行
        idx = _search_right(ctx_t, mt) - 1
        if idx < 0:
            latest_close.append(float("nan"))
            latest_open.append(float("nan"))
            latest_high.append(float("nan"))
            latest_low.append(float("nan"))
            latest_volume.append(float("nan"))
        else:
            latest_close.append(float(ctx_close[idx]))
            latest_open.append(float(ctx_open[idx]))
            latest_high.append(float(ctx_high[idx]))
            latest_low.append(float(ctx_low[idx]))
            latest_volume.append(float(ctx_volume[idx]))

    for col, vals in (("close", latest_close), ("open", latest_open),
                       ("high", latest_high), ("low", latest_low),
                       ("volume", latest_volume)):
        name = f"ctx_{tf_n}_{col}"
        out_series[name] = pd.Series(vals, index=main_df.index)
        out_cols.add(name)

    # 2) 统计 Series (MA/Max/Min/Std/Sum over last n)
    for stat, func in (("ma", "mean"), ("max", "max"), ("min", "min"),
                        ("std", "std"), ("sum", "sum")):
        vals = []
        for mt in main_times:
            end_idx = _search_right(ctx_t, mt)
            if end_idx == 0:
                vals.append(float("nan"))
                continue
            start_idx = max(0, end_idx - n)
            window = ctx_close[start_idx:end_idx]
            if len(window) == 0:
                vals.append(float("nan"))
                continue
            try:
                if func == "mean":
                    vals.append(float(window.mean()))
                elif func == "std":
                    vals.append(float(window.std()) if len(window) > 1 else 0.0)
                else:
                    vals.append(float(getattr(window, func)()))
            except Exception:
                vals.append(float("nan"))
        name = f"ctx_{tf_n}_{stat}{n}"
        out_series[name] = pd.Series(vals, index=main_df.index)
        out_cols.add(name)


def _search_right(arr, val) -> int:
    """二分找 arr 中第一个 > val 的位置 (arr 单调递增)"""
    import numpy as np
    arr_np = np.asarray(arr)
    # 统一为 datetime64 避免 int vs Timestamp 类型不匹配
    if np.issubdtype(arr_np.dtype, np.datetime64) or hasattr(val, 'timestamp'):
        try:
            val_ts = np.datetime64(pd.Timestamp(val))
        except Exception:
            val_ts = val
    else:
        val_ts = val
    try:
        idx = np.searchsorted(arr_np, val_ts, side="right")
    except TypeError:
        # 类型不匹配时回退线性扫描
        idx = 0
        for i, v in enumerate(arr_np):
            try:
                if v > val:
                    idx = i
                    break
            except TypeError:
                continue
            idx = i + 1
    return int(idx)


def _tf_name(tf: str) -> str:
    """把 '15m' -> '15m', '1h' -> '1h', '1d' -> '1d' (合法标识符)"""
    return tf.replace("/", "_")
