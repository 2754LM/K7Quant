"""策略层: 内置策略 + DSL 解释器 + 自定义策略
DSL 语法 (单行表达式, 类似 Excel 函数):
  signal = <表达式>
  止损/止盈/仓位: 单行赋值
支持函数: 所有因子 (MA/EMA/RSI/MACD/boll/KDJ/...)
支持操作: AND OR NOT > < >= <= == CROSS_UP CROSS_DOWN
注: signal 必须单行表达式, 不支持 tuple 解包 (如 a, b = MACD(...))
"""
import re
import numpy as np
import pandas as pd
from typing import Optional

from backend.factor import compute_factor, FACTOR_REGISTRY


class StrategyEngine:
    """策略解释器"""

    @staticmethod
    def compile(code: str, params: dict = None):
        """编译策略代码, 返回 (signal_fn, rules)"""
        params = params or {}
        rules = StrategyEngine._parse(code)
        if "signal" not in rules or not rules["signal"]:
            raise ValueError("策略必须定义: signal = <表达式>")
        return StrategyEngine._build_signal_fn(rules["signal"]), rules

    @staticmethod
    def _parse(code: str) -> dict:
        """解析 DSL"""
        rules = {"stop_loss": 0.0, "take_profit": 0.0,
                 "position_size": 1.0, "rebalance": "every_bar"}

        for raw in code.split("\n"):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            # signal = <expr>
            m = re.match(r"signal\s*=\s*(.+)$", line)
            if m:
                rules["signal"] = m.group(1).strip()
                continue
            # 止损 = 0.05
            m = re.match(r"止损\s*=\s*([\d.]+)", line)
            if m:
                rules["stop_loss"] = float(m.group(1)); continue
            # 止盈
            m = re.match(r"止盈\s*=\s*([\d.]+)", line)
            if m:
                rules["take_profit"] = float(m.group(1)); continue
            # 仓位
            m = re.match(r"仓位\s*=\s*([\d.]+)", line)
            if m:
                rules["position_size"] = float(m.group(1)); continue
        return rules

    @staticmethod
    def _build_signal_fn(expr: str):
        """将表达式编译成可调用函数
        支持语法: 因子函数 + 比较/AND/OR/NOT + CROSS_UP/CROSS_DOWN
        关键列名 (close/open/high/low/volume/amount) 自动替换为 df[col]
        """
        from backend.factor import FACTOR_REGISTRY as FR
        user_to_id = {f["name_zh"].lower(): fid for fid, f in FR.items()}
        user_to_id.update({f["name_zh"]: fid for fid, f in FR.items()})

        for m in re.finditer(r"(\w+)\(", expr):
            name = m.group(1)
            if name in {"AND", "OR", "NOT", "CROSS_UP", "CROSS_DOWN", "_get"}:
                continue
            if name not in FR and name.lower() not in FR and name not in user_to_id:
                raise ValueError(f"未知因子: {name}")

        COLS = ["close", "open", "high", "low", "volume", "amount"]

        def replace_calls(s):
            """NAME(args) -> _get("NAME", "args")
            列名保持原样, 在 _get 内部按 COLS 解析
            """
            OPERATORS = {"AND", "OR", "NOT", "CROSS_UP", "CROSS_DOWN", "_get"}
            result = []
            i = 0
            while i < len(s):
                if s[i].isspace():
                    result.append(s[i]); i += 1; continue
                m = re.match(r"(\w+)\(", s[i:])
                if not m:
                    result.append(s[i]); i += 1; continue
                name = m.group(1)
                if name in OPERATORS:
                    result.append(name); i += len(name); continue
                depth = 1
                j = i + len(m.group(0))
                while j < len(s) and depth > 0:
                    if s[j] == "(": depth += 1
                    elif s[j] == ")": depth -= 1
                    j += 1
                args = s[i + len(m.group(0)):j - 1]
                # 用单引号包 args 避免与 close 转的 _df["close"] 嵌套
                result.append(f"_get('{name}', '{args}')")
                i = j
            return "".join(result)

        def replace_cols(s):
            """close -> _df["close"]"""
            for col in COLS:
                s = re.sub(rf"(?<![A-Za-z0-9_]){col}(?![A-Za-z0-9_(])", f'_df["{col}"]', s)
            return s

        def replace_logic(s):
            """把 AND/OR/NOT 关键字替换成 Python 操作符 (& | ~)
            NOT 替换: 正确处理嵌套括号
            """
            def find_matching_paren(text, start):
                """从 start 位置的 ( 开始找匹配的 ), 返回结束位置 (含右括号)"""
                assert text[start] == "("
                depth = 1
                k = start + 1
                in_str = None
                while k < len(text):
                    ch = text[k]
                    if in_str:
                        if ch == in_str and text[k-1] != "\\":
                            in_str = None
                    elif ch in ("'", '"'):
                        in_str = ch
                    elif ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                        if depth == 0:
                            return k
                    k += 1
                return len(text) - 1

            OPERATORS_NOT = {"CROSS_UP", "CROSS_DOWN", "AND", "OR"}

            def replace_not(text):
                result = []
                i = 0
                while i < len(text):
                    m = re.match(r"\bNOT\s+", text[i:])
                    if not m:
                        result.append(text[i]); i += 1; continue
                    j = i + m.end()
                    # 检查是否跟了 OPERATOR (如 NOT CROSS_DOWN(...))
                    op_matched = None
                    for op in OPERATORS_NOT:
                        if (text[j:].startswith(op) and
                            (j + len(op) == len(text) or
                             (not text[j+len(op)].isalnum() and text[j+len(op)] != "_"))):
                            op_matched = op
                            j += len(op)
                            while j < len(text) and text[j].isspace():
                                j += 1
                            break
                    if j < len(text) and text[j] == "(":
                        k = find_matching_paren(text, j)
                        expr = text[j:k+1]
                        if op_matched:
                            # NOT CROSS_DOWN(...) -> (~CROSS_DOWN(...))
                            result.append("(~" + op_matched + expr + ")")
                        else:
                            result.append("(~" + expr + ")")
                        i = k + 1
                    else:
                        k = j
                        while k < len(text) and text[k] not in " \t\n":
                            k += 1
                        result.append("(~" + text[j:k] + ")")
                        i = k
                return "".join(result)

            s = replace_not(s)
            prev = None
            while prev != s:
                prev = s
                s = re.sub(r"\s+AND\s+", " & ", s)
            prev = None
            while prev != s:
                prev = s
                s = re.sub(r"\s+OR\s+", " | ", s)
            return s

        def signal_fn(df: pd.DataFrame) -> pd.Series:
            cache = {}

            def get_factor_result(name: str, args_str: str):
                key = f"{name}({args_str})"
                if key in cache:
                    return cache[key]
                factor_id = name if name in FR else (
                    name.lower() if name.lower() in FR else user_to_id.get(name)
                )
                if factor_id is None:
                    raise ValueError(f"未知因子: {name}")
                # 解析参数: 列名 (close, _df["close"]) 直接跳过, 数字作为参数
                args = [a.strip() for a in args_str.split(",") if a.strip()]
                schema = FR[factor_id].get("params_schema", {})
                kwargs = {}
                positional_idx = 0
                for arg in args:
                    # 列名判定: close, _df["close"]
                    is_col = (arg in COLS or
                              arg in {f'_df["{c}"]' for c in COLS})
                    if is_col:
                        positional_idx += 1; continue
                    try:
                        val = float(arg)
                    except ValueError:
                        val = arg
                    keys = list(schema.keys())
                    while positional_idx < len(keys) and keys[positional_idx] in kwargs:
                        positional_idx += 1
                    if positional_idx < len(keys):
                        kwargs[keys[positional_idx]] = val
                        positional_idx += 1
                result = compute_factor(df, factor_id, kwargs)
                cache[key] = result
                return result

            processed = replace_cols(expr)
            processed = replace_calls(processed)
            processed = replace_logic(processed)

            def _get(name, args):
                return get_factor_result(name, args)

            local_env = {
                "__builtins__": {},
                "_df": df,
                "_get": _get,
                "CROSS_UP": lambda a, b: ((a > b) & (a.shift(1) <= b.shift(1))),
                "CROSS_DOWN": lambda a, b: ((a < b) & (a.shift(1) >= b.shift(1))),
            }
            try:
                result = eval(processed, local_env)
            except Exception as e:
                raise ValueError(f"表达式求值失败: {e}\n表达式: {expr}\n处理后: {processed}")
            return result.astype(int) if hasattr(result, "astype") else result

        return signal_fn


# ============ 预置策略 (DSL 单行表达式形式) ============

BUILTIN_STRATEGIES = [
    {
        "name": "双均线交叉",
        "description": "短均线上穿长均线做多, 下穿做空。最经典趋势策略。",
        "category": "trend",
        "code": """# 双均线交叉策略
signal = CROSS_UP(MA(close, 7), MA(close, 25)) AND NOT CROSS_DOWN(MA(close, 7), MA(close, 25))
止损 = 0.05
止盈 = 0.15
仓位 = 1.0
""",
        "params_schema": {
            "ma_short": {"label": "短均线", "type": "int", "default": 7, "min": 2, "max": 60},
            "ma_long": {"label": "长均线", "type": "int", "default": 25, "min": 5, "max": 250},
        },
    },
    {
        "name": "RSI 超买超卖",
        "description": "RSI < 30 买入, RSI > 70 卖出。震荡市友好。",
        "category": "mean_reversion",
        "code": """# RSI 超买超卖策略
signal = (RSI(close, 14) < 30) AND NOT (RSI(close, 14) > 70)
止损 = 0.05
止盈 = 0.10
仓位 = 1.0
""",
        "params_schema": {
            "rsi_period": {"label": "RSI 周期", "type": "int", "default": 14, "min": 2, "max": 50},
            "oversold": {"label": "超卖线", "type": "int", "default": 30, "min": 5, "max": 50},
            "overbought": {"label": "超买线", "type": "int", "default": 70, "min": 50, "max": 95},
        },
    },
    {
        "name": "MACD 金叉死叉",
        "description": "MACD 上穿信号线做多, 下穿做空。",
        "category": "trend",
        "code": """# MACD 金叉死叉策略
# EMA 上穿 EMA 做多
signal = EMA(close, 12) > EMA(close, 26)
止损 = 0.05
止盈 = 0.15
仓位 = 1.0
""",
        "params_schema": {
            "macd_fast": {"label": "快 EMA", "type": "int", "default": 12, "min": 2, "max": 60},
            "macd_slow": {"label": "慢 EMA", "type": "int", "default": 26, "min": 5, "max": 120},
            "macd_signal": {"label": "信号线", "type": "int", "default": 9, "min": 2, "max": 50},
        },
    },
    {
        "name": "动量轮动",
        "description": "过去 N 根涨就买, 跌就空仓。趋势市利器。",
        "category": "momentum",
        "code": """# 动量策略
signal = momentum(close, 20) > 0
止损 = 0.08
止盈 = 0.20
仓位 = 1.0
""",
        "params_schema": {
            "lookback": {"label": "回看周期", "type": "int", "default": 20, "min": 1, "max": 200},
        },
    },
    {
        "name": "突破新高",
        "description": "突破 N 日新高买入, 跌破均线卖出。海龟交易法简化版。",
        "category": "breakout",
        "code": """# 突破策略
signal = high_break(close, 20) AND NOT (close < MA(close, 20))
止损 = 0.10
止盈 = 0.30
仓位 = 1.0
""",
        "params_schema": {
            "break_period": {"label": "突破周期", "type": "int", "default": 20, "min": 5, "max": 100},
        },
    },
    {
        "name": "布林带均值回归",
        "description": "跌破下轨买入, 涨破中轨卖出。",
        "category": "mean_reversion",
        "code": """# 布林带策略 (用 zscore 简化)
signal = zscore(close, 20) < -2.0
止损 = 0.05
止盈 = 0.10
仓位 = 1.0
""",
        "params_schema": {
            "period": {"label": "周期", "type": "int", "default": 20, "min": 5, "max": 100},
            "std": {"label": "标准差倍数", "type": "float", "default": 2.0, "min": 0.5, "max": 4.0},
        },
    },
    {
        "name": "量价齐升",
        "description": "放量上涨时买入, 缩量下跌时卖出。",
        "category": "volume",
        "code": """# 量价策略
# 放量 + 不在均线下方
signal = (volume > volume_ma(volume, 20) * 1.5) AND NOT (close < MA(close, 10))
止损 = 0.05
止盈 = 0.12
仓位 = 1.0
""",
        "params_schema": {
            "vol_mult": {"label": "放量倍数", "type": "float", "default": 1.5, "min": 1.0, "max": 5.0},
        },
    },
    {
        "name": "ADX 趋势跟随",
        "description": "ADX > 25 时按 MA 交叉, ADX < 20 时空仓。",
        "category": "trend",
        "code": """# ADX 趋势过滤 + MA 交叉
signal = CROSS_UP(MA(close, 7), MA(close, 25)) AND (adx(close, 14) > 25)
止损 = 0.05
止盈 = 0.15
仓位 = 1.0
""",
        "params_schema": {
            "adx_threshold": {"label": "ADX 阈值", "type": "int", "default": 25, "min": 15, "max": 50},
        },
    },
]


def get_builtin_strategies() -> list:
    return BUILTIN_STRATEGIES


def get_strategy_dsl_template() -> str:
    return """# 策略模板 - 双均线
# 买入: 短均线上穿长均线
# 卖出: 短均线下穿长均线

signal = CROSS_UP(MA(close, 7), MA(close, 25)) AND NOT CROSS_DOWN(MA(close, 7), MA(close, 25))
止损 = 0.05
止盈 = 0.15
仓位 = 1.0
"""


def get_dsl_docs() -> dict:
    return {
        "syntax": """
DSL 语法 (类 Excel 公式):

# 注释以 # 开头
signal = <表达式>          # 必需, 返回 0/1
止损 = 0.05                # 可选, 5% 止损
止盈 = 0.15                # 可选, 15% 止盈
仓位 = 1.0                 # 可选, 满仓 (0-1)

# 支持函数 (来自因子库):
MA(close, N) / EMA(close, N) / RSI(close, N)
momentum(close, N) / volatility(close, N)
zscore(close, N) / drawdown(close, N)
high_break(close, N) / low_break(close, N)
volume_ma(volume, N) / volume_ratio(volume, N)
MACD(close, fast, slow, signal) / boll(close, N, std) / KDJ(close, N, m1, m2)
ATR(close, N) / ADX(close, N) / CCI(close, N)
OBV(close) / VWAP(close, N) / MFI(close, N)
...

# 支持操作符:
> < >= <= == !=
AND  OR  NOT
CROSS_UP(a, b)   # a 上穿 b
CROSS_DOWN(a, b) # a 下穿 b
""",
        "examples": [
            {"name": "双均线", "code": "signal = CROSS_UP(MA(close, 7), MA(close, 25)) AND NOT CROSS_DOWN(MA(close, 7), MA(close, 25))"},
            {"name": "RSI 阈值", "code": "signal = (RSI(close, 14) < 30) AND NOT (RSI(close, 14) > 70)"},
            {"name": "多条件", "code": "signal = (RSI(close, 14) < 30) AND (volume > volume_ma(volume, 20))"},
            {"name": "突破", "code": "signal = high_break(close, 20) AND NOT (close < MA(close, 20))"},
            {"name": "动量", "code": "signal = momentum(close, 20) > 0"},
        ]
    }