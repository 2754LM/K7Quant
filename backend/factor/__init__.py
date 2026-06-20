"""因子库: 30+ 预置技术/成交量因子"""
import numpy as np
import pandas as pd


# 因子注册表: name -> (function, params_schema, category)
FACTOR_REGISTRY: dict = {}


def register_factor(factor_id: str, name_zh: str, name_en: str, category: str,
                     formula: str, description: str, params_schema: dict = None):
    """注册一个因子定义"""
    FACTOR_REGISTRY[factor_id] = {
        "id": factor_id,
        "name_zh": name_zh,
        "name_en": name_en,
        "category": category,
        "formula": formula,
        "description": description,
        "params_schema": params_schema or {},
    }


# ============ 因子函数定义 ============
# 每个函数签名: (df, **params) -> pd.Series

def f_ma(df, period: int = 20) -> pd.Series:
    """简单移动平均"""
    return df["close"].rolling(period).mean()

def f_ema(df, period: int = 20) -> pd.Series:
    """指数移动平均"""
    return df["close"].ewm(span=period, adjust=False).mean()

def f_sma(df, period: int = 20) -> pd.Series:
    """简单移动平均 (别名)"""
    return df["close"].rolling(period).mean()

def f_wma(df, period: int = 20) -> pd.Series:
    """加权移动平均"""
    weights = np.arange(1, period + 1)
    return df["close"].rolling(period).apply(
        lambda x: np.dot(x, weights) / weights.sum(), raw=True
    )

def f_rsi(df, period: int = 14) -> pd.Series:
    """RSI 相对强弱指数"""
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))

def f_macd(df, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD 三件套"""
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "hist": hist})

def f_boll(df, period: int = 20, std: float = 2.0) -> pd.DataFrame:
    """布林带"""
    mid = df["close"].rolling(period).mean()
    sd = df["close"].rolling(period).std()
    return pd.DataFrame({"upper": mid + std * sd, "mid": mid, "lower": mid - std * sd})

def f_kdj(df, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
    """KDJ 随机指标"""
    low_n = df["low"].rolling(n).min()
    high_n = df["high"].rolling(n).max()
    rsv = (df["close"] - low_n) / (high_n - low_n).replace(0, 1e-9) * 100
    k = rsv.ewm(alpha=1/m1, adjust=False).mean()
    d = k.ewm(alpha=1/m2, adjust=False).mean()
    j = 3 * k - 2 * d
    return pd.DataFrame({"k": k, "d": d, "j": j})

def f_atr(df, period: int = 14) -> pd.Series:
    """ATR 平均真实波幅"""
    high = df["high"]
    low = df["low"]
    close_prev = df["close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - close_prev).abs(),
        (low - close_prev).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def f_adx(df, period: int = 14) -> pd.Series:
    """ADX 趋势强度"""
    high = df["high"]
    low = df["low"]
    plus_dm = (high.diff()).where((high.diff() > low.diff()) & (high.diff() > 0), 0)
    minus_dm = (-low.diff()).where((-low.diff() > high.diff()) & (-low.diff() > 0), 0)
    atr = f_atr(df, period)
    plus_di = 100 * plus_dm.rolling(period).mean() / atr.replace(0, 1e-9)
    minus_di = 100 * minus_dm.rolling(period).mean() / atr.replace(0, 1e-9)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9)
    return dx.rolling(period).mean()

def f_cci(df, period: int = 20) -> pd.Series:
    """CCI 顺势指标"""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    sma_tp = tp.rolling(period).mean()
    md = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (tp - sma_tp) / (0.015 * md.replace(0, 1e-9))

def f_obv(df) -> pd.Series:
    """OBV 能量潮"""
    sign = np.sign(df["close"].diff()).fillna(0)
    return (sign * df["volume"]).cumsum()

def f_vwap(df, period: int = 20) -> pd.Series:
    """VWAP 成交量加权均价"""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    pv = tp * df["volume"]
    return pv.rolling(period).sum() / df["volume"].rolling(period).sum().replace(0, 1e-9)

def f_mfi(df, period: int = 14) -> pd.Series:
    """MFI 资金流量指标"""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    mf = tp * df["volume"]
    pos_mf = mf.where(tp > tp.shift(1), 0).rolling(period).sum()
    neg_mf = mf.where(tp < tp.shift(1), 0).rolling(period).sum()
    return 100 - (100 / (1 + pos_mf / neg_mf.replace(0, 1e-9)))

def f_momentum(df, period: int = 20) -> pd.Series:
    """动量: N 根涨幅"""
    return df["close"].pct_change(periods=period)

def f_roc(df, period: int = 20) -> pd.Series:
    """ROC 变化率"""
    return (df["close"] / df["close"].shift(period) - 1) * 100

def f_volatility(df, period: int = 20) -> pd.Series:
    """波动率 (年化)"""
    return df["close"].pct_change().rolling(period).std() * np.sqrt(252)

def f_zscore(df, period: int = 20) -> pd.Series:
    """Z-Score (标准化)"""
    mean = df["close"].rolling(period).mean()
    std = df["close"].rolling(period).std()
    return (df["close"] - mean) / std.replace(0, 1e-9)

def f_drawdown(df, period: int = 60) -> pd.Series:
    """滚动回撤"""
    cummax = df["close"].rolling(period).max()
    return (df["close"] - cummax) / cummax

def f_high_break(df, period: int = 20) -> pd.Series:
    """突破 N 日新高"""
    return (df["close"] > df["high"].rolling(period).max().shift(1)).astype(int)

def f_low_break(df, period: int = 20) -> pd.Series:
    """跌破 N 日新低"""
    return (df["close"] < df["low"].rolling(period).min().shift(1)).astype(int)

def f_volume_ma(df, period: int = 20) -> pd.Series:
    """成交量均线"""
    return df["volume"].rolling(period).mean()

def f_volume_ratio(df, period: int = 20) -> pd.Series:
    """量比 (当前量 / 均量)"""
    avg = df["volume"].rolling(period).mean()
    return df["volume"] / avg.replace(0, 1e-9)

def f_amount_ma(df, period: int = 20) -> pd.Series:
    """成交额均线"""
    return df["amount"].rolling(period).mean()

def f_skew(df, period: int = 60) -> pd.Series:
    """收益率偏度"""
    return df["close"].pct_change().rolling(period).skew()

def f_kurt(df, period: int = 60) -> pd.Series:
    """收益率峰度"""
    return df["close"].pct_change().rolling(period).kurt()

def f_position_pct(df, period: int = 252) -> pd.Series:
    """当前价格在 N 日区间内的位置 (0-1)"""
    low_n = df["low"].rolling(period).min()
    high_n = df["high"].rolling(period).max()
    return (df["close"] - low_n) / (high_n - low_n).replace(0, 1e-9)

def f_pivot(df) -> pd.Series:
    """Pivot Point 经典轴心点"""
    return (df["high"].shift(1) + df["low"].shift(1) + df["close"].shift(1)) / 3

def f_supertrend(df, period: int = 10, multiplier: float = 3.0) -> pd.Series:
    """SuperTrend 趋势线"""
    atr = f_atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2
    upper = hl2 + multiplier * atr
    lower = hl2 - multiplier * atr
    direction = pd.Series(0, index=df.index)
    for i in range(1, len(df)):
        if df["close"].iloc[i] > upper.iloc[i-1]:
            direction.iloc[i] = 1
        elif df["close"].iloc[i] < lower.iloc[i-1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i-1]
    return direction

def f_ichimoku_signal(df) -> pd.Series:
    """一目均衡表信号 (1=上升, -1=下降)"""
    high9 = df["high"].rolling(9).max()
    low9 = df["low"].rolling(9).min()
    tenkan = (high9 + low9) / 2
    high26 = df["high"].rolling(26).max()
    low26 = df["low"].rolling(26).min()
    kijun = (high26 + low26) / 2
    return (tenkan > kijun).astype(int) - (tenkan < kijun).astype(int)

def f_donchian(df, period: int = 20) -> pd.DataFrame:
    """Donchian Channel 海龟通道"""
    return pd.DataFrame({
        "upper": df["high"].rolling(period).max().shift(1),
        "lower": df["low"].rolling(period).min().shift(1),
        "mid": (df["high"].rolling(period).max().shift(1) +
                df["low"].rolling(period).min().shift(1)) / 2
    })

def f_chaikin_mf(df, period: int = 20) -> pd.Series:
    """Chaikin Money Flow 资金流"""
    mfv = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / \
          (df["high"] - df["low"]).replace(0, 1e-9) * df["volume"]
    return mfv.rolling(period).sum() / df["volume"].rolling(period).sum().replace(0, 1e-9)

def f_williams_r(df, period: int = 14) -> pd.Series:
    """Williams %R 威廉指标"""
    high_n = df["high"].rolling(period).max()
    low_n = df["low"].rolling(period).min()
    return (high_n - df["close"]) / (high_n - low_n).replace(0, 1e-9) * -100

def f_trix(df, period: int = 15) -> pd.Series:
    """TRIX 三重指数平滑"""
    ema1 = df["close"].ewm(span=period, adjust=False).mean()
    ema2 = ema1.ewm(span=period, adjust=False).mean()
    ema3 = ema2.ewm(span=period, adjust=False).mean()
    return ema3.pct_change() * 100


# ============ 注册所有因子 ============

_FACTORS = [
    ("ma", "ma", "MA", "均线类", "close.rolling({period}).mean()",
     "过去 N 根 K 线收盘价的平均值", {"period": {"label": "周期", "type": "int", "default": 20, "min": 2, "max": 250}}),

    ("ema", "ema", "EMA", "均线类", "close.ewm(span={period}).mean()",
     "指数加权移动平均, 近期权重更高", {"period": {"label": "周期", "type": "int", "default": 20, "min": 2, "max": 250}}),

    ("wma", "wma", "WMA", "均线类", "weighted MA",
     "加权移动平均, 近期权重线性递增", {"period": {"label": "周期", "type": "int", "default": 20, "min": 2, "max": 250}}),

    ("rsi", "rsi", "RSI", "震荡类", "100 - 100 / (1 + avg_gain / avg_loss)",
     "相对强弱指数, >70 超买, <30 超卖", {"period": {"label": "周期", "type": "int", "default": 14, "min": 2, "max": 50}}),

    ("macd", "macd", "MACD", "趋势类", "EMA12 - EMA26",
     "指数平滑异同移动平均, 含主线/信号/柱", {"fast": {"label": "快线", "type": "int", "default": 12, "min": 2, "max": 60},
                                                  "slow": {"label": "慢线", "type": "int", "default": 26, "min": 5, "max": 120},
                                                  "signal": {"label": "信号线", "type": "int", "default": 9, "min": 2, "max": 50}}),

    ("boll", "boll", "布林带", "趋势类", "MA ± 2*STD",
     "布林带, 价格突破上下轨为极值信号", {"period": {"label": "周期", "type": "int", "default": 20, "min": 5, "max": 100},
                                             "std": {"label": "标准差倍数", "type": "float", "default": 2.0, "min": 0.5, "max": 4.0}}),

    ("kdj", "kdj", "KDJ", "震荡类", "RSV -> K, D, J",
     "随机指标, K<20 买入, K>80 卖出", {"n": {"label": "RSV 周期", "type": "int", "default": 9, "min": 3, "max": 50},
                                          "m1": {"label": "K 平滑", "type": "int", "default": 3, "min": 1, "max": 10},
                                          "m2": {"label": "D 平滑", "type": "int", "default": 3, "min": 1, "max": 10}}),

    ("atr", "atr", "ATR", "波动类", "TR 的 N 周期均值",
     "平均真实波幅, 衡量波动大小", {"period": {"label": "周期", "type": "int", "default": 14, "min": 5, "max": 50}}),

    ("adx", "adx", "ADX", "趋势类", "DX 的 N 周期均值",
     "平均趋向指数, >25 强趋势, <20 弱趋势", {"period": {"label": "周期", "type": "int", "default": 14, "min": 5, "max": 50}}),

    ("cci", "cci", "CCI", "震荡类", "(TP-MA)/(0.015*MD)",
     "顺势指标, >100 超买, <-100 超卖", {"period": {"label": "周期", "type": "int", "default": 20, "min": 5, "max": 100}}),

    ("obv", "obv", "OBV", "成交量类", "sign(Δclose) * volume 的累计",
     "能量潮, 价升量增为真涨", {}),

    ("vwap", "vwap", "VWAP", "成交量类", "Σ(TP*V) / ΣV",
     "成交量加权均价, 机构常用基准", {"period": {"label": "周期", "type": "int", "default": 20, "min": 5, "max": 100}}),

    ("mfi", "mfi", "MFI", "成交量类", "类似 RSI 但用成交量",
     "资金流量指标, >80 超买, <20 超卖", {"period": {"label": "周期", "type": "int", "default": 14, "min": 5, "max": 50}}),

    ("momentum", "momentum", "动量", "动量类", "close / close.shift(N) - 1",
     "N 根涨幅", {"period": {"label": "周期", "type": "int", "default": 20, "min": 1, "max": 250}}),

    ("roc", "roc", "ROC", "动量类", "(close/close.shift(N) - 1) * 100",
     "变化率百分比", {"period": {"label": "周期", "type": "int", "default": 20, "min": 1, "max": 250}}),

    ("volatility", "volatility", "波动率", "波动类", "std * sqrt(252)",
     "年化波动率", {"period": {"label": "周期", "type": "int", "default": 20, "min": 5, "max": 100}}),

    ("zscore", "zscore", "Z-Score", "统计类", "(close - MA) / STD",
     "标准化分数, |z|>2 为异常", {"period": {"label": "周期", "type": "int", "default": 20, "min": 5, "max": 100}}),

    ("drawdown", "drawdown", "滚动回撤", "风险类", "(close - max) / max",
     "N 周期内相对最高点的跌幅", {"period": {"label": "周期", "type": "int", "default": 60, "min": 5, "max": 250}}),

    ("high_break", "high_break", "突破新高", "形态类", "close > high.rolling(N).max().shift(1)",
     "突破 N 日新高", {"period": {"label": "周期", "type": "int", "default": 20, "min": 5, "max": 250}}),

    ("low_break", "low_break", "跌破新低", "形态类", "close < low.rolling(N).min().shift(1)",
     "跌破 N 日新低", {"period": {"label": "周期", "type": "int", "default": 20, "min": 5, "max": 250}}),

    ("volume_ma", "volume_ma", "成交量均线", "成交量类", "volume.rolling(N).mean()",
     "N 周期成交量均值", {"period": {"label": "周期", "type": "int", "default": 20, "min": 5, "max": 100}}),

    ("volume_ratio", "volume_ratio", "量比", "成交量类", "volume / MA(volume)",
     "当前量 / 均量, >1.5 放量", {"period": {"label": "周期", "type": "int", "default": 20, "min": 5, "max": 100}}),

    ("amount_ma", "amount_ma", "成交额均线", "成交量类", "amount.rolling(N).mean()",
     "N 周期成交额均值", {"period": {"label": "周期", "type": "int", "default": 20, "min": 5, "max": 100}}),

    ("skew", "skew", "偏度", "统计类", "rolling skew",
     "收益率偏度, 正=右偏(大涨更多)", {"period": {"label": "周期", "type": "int", "default": 60, "min": 10, "max": 250}}),

    ("kurt", "kurt", "峰度", "统计类", "rolling kurtosis",
     "收益率峰度, 高=极端事件多", {"period": {"label": "周期", "type": "int", "default": 60, "min": 10, "max": 250}}),

    ("position_pct", "position_pct", "区间位置", "统计类", "(close - low) / (high - low)",
     "价格在 N 日区间内的位置 (0-1)", {"period": {"label": "周期", "type": "int", "default": 252, "min": 20, "max": 500}}),

    ("pivot", "pivot", "轴心点", "形态类", "(H+L+C)/3 (前日)",
     "经典轴心点, 价格围绕它波动", {}),

    ("supertrend", "supertrend", "SuperTrend", "趋势类", "ATR-based trend",
     "海龟改良版, 1=上升 -1=下降", {"period": {"label": "周期", "type": "int", "default": 10, "min": 5, "max": 50},
                                            "multiplier": {"label": "倍数", "type": "float", "default": 3.0, "min": 1.0, "max": 5.0}}),

    ("ichimoku_signal", "ichimoku_signal", "一目均衡", "趋势类", "(Tenkan > Kijun) ? 1 : -1",
     "一目均衡表信号, 1=上升趋势", {}),

    ("donchian", "donchian", "海龟通道", "趋势类", "high/low N 周期",
     "海龟交易法通道, 突破上轨做多", {"period": {"label": "周期", "type": "int", "default": 20, "min": 5, "max": 100}}),

    ("chaikin_mf", "chaikin_mf", "CMF 资金流", "成交量类", "ΣMFV / ΣV",
     "蔡金资金流, >0.05 资金流入", {"period": {"label": "周期", "type": "int", "default": 20, "min": 5, "max": 100}}),

    ("williams_r", "williams_r", "Williams %R", "震荡类", "(Hn-C)/(Hn-Ln)*-100",
     "威廉指标, >-20 超买, <-80 超卖", {"period": {"label": "周期", "type": "int", "default": 14, "min": 5, "max": 50}}),

    ("trix", "trix", "TRIX", "趋势类", "三重 EMA 的变化率",
     "三重指数平滑, 过滤噪音", {"period": {"label": "周期", "type": "int", "default": 15, "min": 5, "max": 50}}),
]

# 注册
for fid, fname_zh, fname_en, fcat, fformula, fdesc, fschema in _FACTORS:
    fn = globals().get(f"f_{fid}")
    if fn is None:
        continue
    # 深拷贝 params_schema 避免共享
    import copy
    FACTOR_REGISTRY[fid] = {
        "id": fid,
        "name_zh": fname_zh,
        "name_en": fname_en,
        "category": fcat,
        "formula": fformula,
        "description": fdesc,
        "params_schema": copy.deepcopy(fschema) if fschema else {},
        "function": fn,
    }


def get_factor_func(factor_id: str):
    info = FACTOR_REGISTRY.get(factor_id)
    return info["function"] if info else None


def list_factors(category: str = None) -> list:
    out = []
    for f in FACTOR_REGISTRY.values():
        if category and f["category"] != category:
            continue
        out.append({
            "id": f["id"], "name_zh": f["name_zh"], "name_en": f["name_en"],
            "category": f["category"], "formula": f["formula"],
            "description": f["description"], "params_schema": f["params_schema"],
        })
    return out


def compute_factor(df: pd.DataFrame, factor_id: str, params: dict = None):
    """计算单个因子, 返回 Series 或 DataFrame"""
    info = FACTOR_REGISTRY.get(factor_id)
    if not info:
        raise ValueError(f"未知因子: {factor_id}")
    return info["function"](df, **(params or {}))


# ============ 因子分类 ============

CATEGORIES = ["均线类", "趋势类", "震荡类", "动量类", "波动类", "成交量类",
              "形态类", "风险类", "统计类"]


# ============ 相关性分析 ============

def factor_correlation(df: pd.DataFrame, factor_ids: list, params_list: list = None,
                       period: int = None) -> dict:
    """计算多个因子之间的相关性"""
    if not factor_ids:
        return {"columns": [], "matrix": []}

    series_dict = {}
    for i, fid in enumerate(factor_ids):
        params = (params_list[i] if params_list else None) or {}
        try:
            result = compute_factor(df, fid, params)
            if isinstance(result, pd.DataFrame):
                for col in result.columns:
                    series_dict[f"{fid}_{col}"] = result[col]
            else:
                series_dict[fid] = result
        except Exception as e:
            continue

    if not series_dict:
        return {"columns": [], "matrix": []}

    sdf = pd.DataFrame(series_dict)
    if period:
        sdf = sdf.tail(period)
    corr = sdf.corr()

    return {
        "columns": list(corr.columns),
        "matrix": corr.values.tolist(),
    }


def factor_summary(df: pd.DataFrame, factor_id: str, params: dict = None) -> dict:
    """计算因子统计摘要"""
    result = compute_factor(df, factor_id, params)
    if isinstance(result, pd.DataFrame):
        result = result.iloc[:, 0]  # 取第一列
    s = result.dropna()
    if s.empty:
        return {}
    return {
        "current": float(s.iloc[-1]) if len(s) else None,
        "min": float(s.min()),
        "max": float(s.max()),
        "mean": float(s.mean()),
        "std": float(s.std()),
        "percentile_25": float(s.quantile(0.25)),
        "percentile_50": float(s.quantile(0.5)),
        "percentile_75": float(s.quantile(0.75)),
    }