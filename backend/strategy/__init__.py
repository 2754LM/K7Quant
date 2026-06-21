"""策略层: 内置策略 + DSL 解释器 + 自定义策略
DSL 语法 (单行表达式, 类似 Excel 函数):
  signal = <表达式>
  止损/止盈/仓位: 单行赋值
支持函数: 所有因子 (MA/EMA/RSI/MACD/boll/KDJ/...)
支持操作: AND OR NOT > < >= <= == CROSS_UP CROSS_DOWN
注: signal 必须单行表达式, 不支持 tuple 解包 (如 a, b = MACD(...))
"""
import re
import ast
import numpy as np
import pandas as pd
from typing import Optional

from backend.factor import compute_factor, FACTOR_REGISTRY


def _const_number(node):
    """从 AST 节点取数字常量 (支持 -2.0 这种一元负号), 否则返回 None"""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
            and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        inner = _const_number(node.operand)
        if inner is not None:
            return -inner if isinstance(node.op, ast.USub) else inner
    return None


def _apply_cmp(op, left, right):
    if isinstance(op, ast.Lt):
        return left < right
    if isinstance(op, ast.Gt):
        return left > right
    if isinstance(op, ast.LtE):
        return left <= right
    if isinstance(op, ast.GtE):
        return left >= right
    if isinstance(op, ast.Eq):
        return left == right
    if isinstance(op, ast.NotEq):
        return left != right
    raise ValueError("不支持的比较运算符")


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
                 "position_size": 1.0}

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
            # 频率 / 调仓 / 调仓周期 = N (每 N 根 K 线才允许换仓, 默认 1)
            m = re.match(r"(?:频率|调仓|调仓周期)\s*=\s*(\d+)", line)
            if m:
                rules["rebalance_bars"] = max(1, int(m.group(1))); continue
        return rules

    @staticmethod
    def _build_signal_fn(expr: str):
        """把 DSL 表达式编译成可调用函数。

        安全实现: **不使用 eval**。先把 AND/OR/NOT 关键字转成位运算符, 再用
        ``ast`` 解析, 经白名单校验 (禁止属性访问/下标/任意名称) 后由解释器求值。
        支持: 因子函数 + 比较 + AND/OR/NOT + CROSS_UP/CROSS_DOWN + 列名/数字。
        """
        from backend.factor import FACTOR_REGISTRY as FR
        user_to_id = {f["name_zh"].lower(): fid for fid, f in FR.items()}
        user_to_id.update({f["name_zh"]: fid for fid, f in FR.items()})

        COLS = {"close", "open", "high", "low", "volume", "amount"}
        CROSS = {"CROSS_UP", "CROSS_DOWN"}

        def resolve_factor_id(name):
            if name in FR:
                return name
            if name.lower() in FR:
                return name.lower()
            return user_to_id.get(name)

        # 友好错误: 提前检查函数名 (真正的安全保证在 _validate_ast)
        for m in re.finditer(r"(\w+)\s*\(", expr):
            name = m.group(1)
            if name in {"AND", "OR", "NOT"} or name in CROSS:
                continue
            if resolve_factor_id(name) is None:
                raise ValueError(f"未知因子: {name}")

        transformed = StrategyEngine._logic_to_operators(expr)
        try:
            tree = ast.parse(transformed, mode="eval")
        except SyntaxError as e:
            raise ValueError(f"表达式语法错误: {e}")

        StrategyEngine._validate_ast(tree, COLS, CROSS, resolve_factor_id)

        def signal_fn(df: pd.DataFrame) -> pd.Series:
            cache = {}

            def factor_series(name, arg_nodes):
                factor_id = resolve_factor_id(name)
                schema_keys = list(FR[factor_id].get("params_schema", {}).keys())
                kwargs = {}
                pi = 0  # 只有数字参数推进 schema 位置: 列(close/...)是数据, 不占参数位
                for node in arg_nodes:
                    num = _const_number(node)
                    if num is None:
                        continue
                    if pi < len(schema_keys):
                        kwargs[schema_keys[pi]] = num
                        pi += 1
                key = (factor_id, tuple(sorted(kwargs.items())))
                if key in cache:
                    return cache[key]
                res = compute_factor(df, factor_id, kwargs)
                cache[key] = res
                return res

            def ev(node):
                if isinstance(node, ast.Expression):
                    return ev(node.body)
                if isinstance(node, ast.BinOp):
                    left, right = ev(node.left), ev(node.right)
                    op = node.op
                    if isinstance(op, ast.BitAnd):
                        return left & right
                    if isinstance(op, ast.BitOr):
                        return left | right
                    if isinstance(op, ast.Add):
                        return left + right
                    if isinstance(op, ast.Sub):
                        return left - right
                    if isinstance(op, ast.Mult):
                        return left * right
                    if isinstance(op, ast.Div):
                        return left / right
                    if isinstance(op, ast.Mod):
                        return left % right
                    raise ValueError("不支持的运算符")
                if isinstance(node, ast.UnaryOp):
                    val = ev(node.operand)
                    if isinstance(node.op, ast.Invert):
                        return ~val
                    if isinstance(node.op, ast.USub):
                        return -val
                    if isinstance(node.op, ast.UAdd):
                        return +val
                    raise ValueError("不支持的一元运算符")
                if isinstance(node, ast.Compare):
                    left = ev(node.left)
                    result = None
                    for op, comp in zip(node.ops, node.comparators):
                        right = ev(comp)
                        piece = _apply_cmp(op, left, right)
                        result = piece if result is None else (result & piece)
                        left = right
                    return result
                if isinstance(node, ast.Call):
                    fname = node.func.id
                    if fname in CROSS:
                        a, b = ev(node.args[0]), ev(node.args[1])
                        if fname == "CROSS_UP":
                            return (a > b) & (a.shift(1) <= b.shift(1))
                        return (a < b) & (a.shift(1) >= b.shift(1))
                    return factor_series(fname, node.args)
                if isinstance(node, ast.Name):
                    if node.id in COLS:
                        return df[node.id]
                    raise ValueError(f"未知标识符: {node.id}")
                if isinstance(node, ast.Constant):
                    return node.value
                raise ValueError(f"不支持的表达式: {type(node).__name__}")

            try:
                result = ev(tree)
            except ValueError:
                raise
            except Exception as e:
                raise ValueError(f"表达式求值失败: {e}\n表达式: {expr}")
            return result.astype(int) if hasattr(result, "astype") else result

        return signal_fn

    # ---- DSL 安全解析辅助 ----

    @staticmethod
    def _logic_to_operators(s: str) -> str:
        """把 AND/OR/NOT 关键字转成 Python 位运算符 (& | ~), 供 ast 解析。"""
        def find_matching_paren(text, start):
            depth = 1
            k = start + 1
            while k < len(text):
                if text[k] == "(":
                    depth += 1
                elif text[k] == ")":
                    depth -= 1
                    if depth == 0:
                        return k
                k += 1
            return len(text) - 1

        def replace_not(text):
            result = []
            i = 0
            while i < len(text):
                m = re.match(r"\bNOT\b\s*", text[i:])
                if not m:
                    result.append(text[i]); i += 1; continue
                j = i + m.end()
                op_matched = ""
                for op in ("CROSS_UP", "CROSS_DOWN"):
                    if (text[j:].startswith(op) and
                            (j + len(op) == len(text) or
                             not (text[j + len(op)].isalnum() or text[j + len(op)] == "_"))):
                        op_matched = op
                        j += len(op)
                        while j < len(text) and text[j].isspace():
                            j += 1
                        break
                if j < len(text) and text[j] == "(":
                    k = find_matching_paren(text, j)
                    result.append("(~" + op_matched + text[j:k + 1] + ")")
                    i = k + 1
                else:
                    k = j
                    while k < len(text) and not (text[k].isspace() or text[k] in "()&|"):
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

    @staticmethod
    def _validate_ast(tree, COLS, CROSS, resolve):
        """白名单校验 AST: 只允许数值/比较/逻辑运算 + 因子调用 + 列名。

        关键: 不在白名单内的节点 (尤其 Attribute / Subscript) 一律拒绝, 从根本上
        杜绝 ``_df.__class__.__init__.__globals__[...]`` 之类的沙箱逃逸。
        """
        allowed = (
            ast.Expression, ast.BinOp, ast.UnaryOp, ast.Compare, ast.Call,
            ast.Name, ast.Constant, ast.Load,
            ast.BitAnd, ast.BitOr, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod,
            ast.Invert, ast.USub, ast.UAdd,
            ast.Lt, ast.Gt, ast.LtE, ast.GtE, ast.Eq, ast.NotEq,
        )
        for node in ast.walk(tree):
            if not isinstance(node, allowed):
                raise ValueError(f"非法或不支持的语法: {type(node).__name__}")
            if isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Name) or node.keywords:
                    raise ValueError("只允许直接调用因子函数 (不支持关键字参数)")
                if node.func.id not in CROSS and resolve(node.func.id) is None:
                    raise ValueError(f"未知因子: {node.func.id}")
            if isinstance(node, ast.Name):
                if node.id not in COLS and node.id not in CROSS and resolve(node.id) is None:
                    raise ValueError(f"未知标识符: {node.id}")
            if isinstance(node, ast.Constant):
                if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                    raise ValueError("仅支持数字常量")


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
            "ma_short": {"label": "短均线", "type": "int", "default": 7, "min": 2, "max": 60, "unit": "周期", "hint": "短期均线计算的 K 线根数, 值越小越敏感"},
            "ma_long": {"label": "长均线", "type": "int", "default": 25, "min": 5, "max": 250, "unit": "周期", "hint": "长期均线计算的 K 线根数, 需大于短均线"},
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
            "rsi_period": {"label": "RSI 周期", "type": "int", "default": 14, "min": 2, "max": 50, "unit": "周期", "hint": "RSI 指标的回看 K 线数"},
            "oversold": {"label": "超卖线", "type": "int", "default": 30, "min": 5, "max": 50, "unit": "阈值", "hint": "RSI 跌到此值以下认为超卖 (买入信号)"},
            "overbought": {"label": "超买线", "type": "int", "default": 70, "min": 50, "max": 95, "unit": "阈值", "hint": "RSI 涨到此值以上认为超买 (卖出信号)"},
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
            "macd_fast": {"label": "快 EMA", "type": "int", "default": 12, "min": 2, "max": 60, "unit": "周期", "hint": "MACD 中快速 EMA 的回看 K 线数"},
            "macd_slow": {"label": "慢 EMA", "type": "int", "default": 26, "min": 5, "max": 120, "unit": "周期", "hint": "MACD 中慢速 EMA 的回看 K 线数, 需大于快 EMA"},
            "macd_signal": {"label": "信号线", "type": "int", "default": 9, "min": 2, "max": 50, "unit": "周期", "hint": "MACD 信号线 (DIF 的 EMA) 的回看 K 线数"},
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
            "lookback": {"label": "回看周期", "type": "int", "default": 20, "min": 1, "max": 200, "unit": "周期", "hint": "计算动量时回看的 K 线根数"},
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
            "break_period": {"label": "突破周期", "type": "int", "default": 20, "min": 5, "max": 100, "unit": "周期", "hint": "突破 N 根 K 线的新高即触发买入"},
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
            "period": {"label": "周期", "type": "int", "default": 20, "min": 5, "max": 100, "unit": "周期", "hint": "布林带/均值计算的回看 K 线数"},
            "std": {"label": "标准差倍数", "type": "float", "default": 2.0, "min": 0.5, "max": 4.0, "unit": "σ", "hint": "上下轨与中轨的距离 (N 倍标准差)"},
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
            "vol_mult": {"label": "放量倍数", "type": "float", "default": 1.5, "min": 1.0, "max": 5.0, "unit": "倍", "hint": "成交量超过均量 N 倍即视为放量"},
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
            "adx_threshold": {"label": "ADX 阈值", "type": "int", "default": 25, "min": 15, "max": 50, "unit": "阈值", "hint": "ADX 大于此值认为有趋势, 才发出信号"},
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