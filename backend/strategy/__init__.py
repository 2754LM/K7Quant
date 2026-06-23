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
    def compile(code: str, params: dict = None, mode: str = "strategy"):
        """编译代码, 返回 (signal_fn, rules)

        mode: "strategy" (默认) 把结果转 0/1 int, 用于回测
              "factor"  保留浮点原值, 用于自定义因子
        """
        params = params or {}
        rules = StrategyEngine._parse(code)
        if "signal" in rules and rules["signal"]:
            return StrategyEngine._build_signal_fn(rules["signal"], mode=mode), rules
        # 因子模式: 整段代码 = 单个表达式
        lines = [ln.strip() for ln in code.split("\n")
                 if ln.strip() and not ln.strip().startswith("#")]
        expr = " ".join(lines)
        if not expr:
            raise ValueError("策略/因子代码不能为空")
        return StrategyEngine._build_signal_fn(expr, mode=mode), {"signal": expr, "stop_loss": 0, "take_profit": 0, "position_size": 1.0}

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
    def _build_signal_fn(expr: str, mode: str = "strategy"):
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
            # 策略模式: 转 int (0/1); 因子模式: 保留浮点
            if mode == "strategy" and hasattr(result, "astype"):
                return result.astype(int)
            return result

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
    {
        "name": "Martingale 网格",
        "description": "Python 脚本: 跌 1% 翻倍加仓, 涨 0.5% 全平, 限制最大层数。有爆仓风险, 谨慎使用。",
        "category": "martingale",
        "code_type": "python",
        "code": '''# Martingale 网格策略 (Python)
# 跌 1% 翻倍加仓, 涨 0.5% 全部止盈; 限制最大层数
# 风险提示: 极端行情可能爆仓, 实盘务必设置最大层数

def init():
    return {
        "entry": 0,           # 上次加仓价
        "qty": 0,             # 当前持仓 USDT 价值
        "base_qty": 100,      # 基础仓 (USDT)
        "grid_count": 0,      # 当前网格层数
        "max_grid": 5,        # 最大层数
        "drop_pct": 0.99,     # 跌幅阈值 (0.99 = 跌 1%)
        "rise_pct": 1.005,    # 涨幅阈值 (1.005 = 涨 0.5%)
    }

def on_bar(state):
    p = ctx.now()
    if p <= 0:
        return

    # 首次建仓
    if state["entry"] == 0:
        state["entry"] = p
        state["qty"] = state["base_qty"]
        buy(state["qty"])
        return

    # 跌到阈值 → 翻倍加仓
    if p < state["entry"] * state["drop_pct"] and state["grid_count"] < state["max_grid"]:
        state["entry"] = p
        state["qty"] *= 2
        state["grid_count"] += 1
        buy(state["qty"])
        return

    # 涨到阈值 → 全平 + 重置
    if p > state["entry"] * state["rise_pct"]:
        sell_all()
        state["entry"] = 0
        state["qty"] = state["base_qty"]
        state["grid_count"] = 0
        return
''',
        "params_schema": {
            "max_grid": {"label": "最大层数", "type": "int", "default": 5, "min": 1, "max": 20, "unit": "层", "hint": "最多加仓几次, 防止极端行情无限翻倍"},
            "drop_pct": {"label": "跌幅阈值", "type": "float", "default": 0.99, "min": 0.90, "max": 0.999, "unit": "比率", "hint": "相对上次加仓价跌到此比率才加仓 (0.99 = 跌 1%)"},
            "rise_pct": {"label": "止盈阈值", "type": "float", "default": 1.005, "min": 1.001, "max": 1.10, "unit": "比率", "hint": "相对上次加仓价涨到此比率就全平 (1.005 = 涨 0.5%)"},
            "base_qty": {"label": "基础仓", "type": "float", "default": 100, "min": 10, "max": 10000, "unit": "USDT", "hint": "首次建仓 / 止盈重置后的基础下单金额"},
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
    """DSL 详细文档 - 分类整理, 配示例"""
    return {
        "overview": (
            "DSL 是一套类 Excel 公式的策略描述语言, 一行式表达式。\n"
            "编译时只做 AST 白名单校验, 禁止属性访问/下标, 无 eval。"
        ),
        "structure": [
            {"syntax": "signal = <表达式>", "required": True,
             "desc": "买卖信号表达式, 返回 0/1 (或 -1/0/1 表示做空)。每根 K 线都会被求值。"},
            {"syntax": "止损 = 0.05", "required": False, "desc": "浮亏达 5% 强制平仓。范围 0-1。"},
            {"syntax": "止盈 = 0.15", "required": False, "desc": "浮盈达 15% 强制平仓。范围 0-1。"},
            {"syntax": "仓位 = 1.0", "required": False, "desc": "每笔投入资金比例 (0-1)。"},
            {"syntax": "频率 = 5", "required": False, "desc": "调仓频率, 每 N 根 K 线才允许换仓 (默认 1)。"},
        ],
        "columns": [
            {"name": "close", "desc": "收盘价, 最常用的输入"},
            {"name": "open", "desc": "开盘价"},
            {"name": "high", "desc": "最高价"},
            {"name": "low", "desc": "最低价"},
            {"name": "volume", "desc": "成交量 (基础币种, 如 BTC)"},
            {"name": "amount", "desc": "成交额 (计价币种, 如 USDT)"},
        ],
        "operators": [
            {"op": "a > b", "desc": "a 大于 b"},
            {"op": "a < b", "desc": "a 小于 b"},
            {"op": "a >= b", "desc": "a 大于等于 b"},
            {"op": "a <= b", "desc": "a 小于等于 b"},
            {"op": "a == b", "desc": "a 等于 b (基本用不上, 因为是连续值)"},
            {"op": "a AND b", "desc": "逻辑与, 两侧必须是 Series (布尔)"},
            {"op": "a OR b", "desc": "逻辑或"},
            {"op": "NOT a", "desc": "逻辑非 (前缀)"},
            {"op": "CROSS_UP(a, b)", "desc": "a 上穿 b: 当前 a>b 且上一根 a≤b。仅作用于两根 K 线。"},
            {"op": "CROSS_DOWN(a, b)", "desc": "a 下穿 b: 当前 a<b 且上一根 a≥b。"},
            {"op": "a + b / a - b", "desc": "加减, 两侧都是 Series 时按位运算"},
            {"op": "a * b / a / b", "desc": "乘除"},
        ],
        "functions": [
            {"cat": "均线类", "items": [
                {"id": "MA", "sig": "MA(close, 20)", "desc": "简单移动平均线。常用 5/10/20/60/120 周期。"},
                {"id": "EMA", "sig": "EMA(close, 20)", "desc": "指数加权均线, 对近期更敏感。"},
                {"id": "WMA", "sig": "WMA(close, 20)", "desc": "线性加权均线。"},
                {"id": "SMA", "sig": "SMA(close, 20)", "desc": "MA 的别名。"},
            ]},
            {"cat": "趋势类", "items": [
                {"id": "MACD", "sig": "MACD(close, 12, 26, 9)", "desc": "返回 3 列: macd/signal/hist。金叉=macd 上穿 signal。"},
                {"id": "ADX", "sig": "ADX(close, 14)", "desc": "趋势强度, >25 有趋势, <20 震荡。"},
                {"id": "supertrend", "sig": "supertrend(close, 10, 3.0)", "desc": "海龟改良趋势, 返回 1/-1。"},
                {"id": "ichimoku_signal", "sig": "ichimoku_signal(close)", "desc": "一目均衡表, 1=上升 -1=下降。"},
                {"id": "donchian", "sig": "donchian(close, 20)", "desc": "海龟通道, 返回 upper/lower/mid 三列。"},
                {"id": "trix", "sig": "trix(close, 15)", "desc": "三重 EMA 的变化率。"},
            ]},
            {"cat": "震荡类", "items": [
                {"id": "RSI", "sig": "RSI(close, 14)", "desc": ">70 超买, <30 超卖, 50 中轴。"},
                {"id": "KDJ", "sig": "KDJ(close, 9, 3, 3)", "desc": "返回 K/D/J 三列。K<20 买, K>80 卖。"},
                {"id": "CCI", "sig": "CCI(close, 20)", "desc": ">100 超买, <-100 超卖。"},
                {"id": "williams_r", "sig": "williams_r(close, 14)", "desc": ">-20 超买, <-80 超卖。"},
            ]},
            {"cat": "波动类", "items": [
                {"id": "boll", "sig": "boll(close, 20, 2.0)", "desc": "布林带, 返回 upper/mid/lower 三列。"},
                {"id": "ATR", "sig": "ATR(close, 14)", "desc": "平均真实波幅, 衡量波动大小。"},
                {"id": "volatility", "sig": "volatility(close, 20)", "desc": "年化波动率。"},
            ]},
            {"cat": "动量类", "items": [
                {"id": "momentum", "sig": "momentum(close, 20)", "desc": "N 根涨幅 (小数, 0.1=10%)。"},
                {"id": "roc", "sig": "roc(close, 20)", "desc": "N 根变化率 (百分比)。"},
            ]},
            {"cat": "成交量类", "items": [
                {"id": "OBV", "sig": "OBV(close)", "desc": "能量潮, 价升量增累计。"},
                {"id": "VWAP", "sig": "VWAP(close, 20)", "desc": "成交量加权均价。"},
                {"id": "MFI", "sig": "MFI(close, 14)", "desc": "资金流量, 类似 RSI 但带成交量。"},
                {"id": "volume_ma", "sig": "volume_ma(volume, 20)", "desc": "成交量均线。"},
                {"id": "volume_ratio", "sig": "volume_ratio(volume, 20)", "desc": "量比, >1.5 算放量。"},
                {"id": "amount_ma", "sig": "amount_ma(amount, 20)", "desc": "成交额均线。"},
                {"id": "chaikin_mf", "sig": "chaikin_mf(close, 20)", "desc": "CMF 资金流, >0 净流入。"},
            ]},
            {"cat": "形态类", "items": [
                {"id": "high_break", "sig": "high_break(close, 20)", "desc": "突破 N 日新高, 返回 0/1。"},
                {"id": "low_break", "sig": "low_break(close, 20)", "desc": "跌破 N 日新低。"},
                {"id": "pivot", "sig": "pivot(close)", "desc": "前日轴心点 (H+L+C)/3。"},
            ]},
            {"cat": "统计/风险类", "items": [
                {"id": "zscore", "sig": "zscore(close, 20)", "desc": "标准化分数, |z|>2 异常。"},
                {"id": "drawdown", "sig": "drawdown(close, 60)", "desc": "N 周期内相对最高点的跌幅。"},
                {"id": "skew", "sig": "skew(close, 60)", "desc": "收益率偏度, 正=大涨更多。"},
                {"id": "kurt", "sig": "kurt(close, 60)", "desc": "收益率峰度, 高=极端事件多。"},
                {"id": "position_pct", "sig": "position_pct(close, 252)", "desc": "价格在 N 日区间内的位置 (0-1)。"},
            ]},
        ],
        "examples": [
            {"name": "双均线交叉 (经典)", "code": "signal = CROSS_UP(MA(close, 7), MA(close, 25)) AND NOT CROSS_DOWN(MA(close, 7), MA(close, 25))\n止损 = 0.05\n止盈 = 0.15\n仓位 = 1.0"},
            {"name": "RSI 超卖反弹", "code": "signal = (RSI(close, 14) < 30) AND NOT (RSI(close, 14) > 70)"},
            {"name": "MACD 金叉 + 量能", "code": "signal = CROSS_UP(MACD(close, 12, 26, 9), MACD(close, 12, 26, 9)) AND (volume > volume_ma(volume, 20) * 1.5)"},
            {"name": "布林带回归", "code": "signal = (close < boll(close, 20, 2.0)) AND (RSI(close, 14) < 35)"},
            {"name": "突破新高", "code": "signal = high_break(close, 20) AND (close > MA(close, 60))\n止盈 = 0.20"},
            {"name": "动量轮动", "code": "signal = momentum(close, 20) > 0.05\n频率 = 5"},
            {"name": "ADX 趋势 + 双均线", "code": "signal = (ADX(close, 14) > 25) AND CROSS_UP(MA(close, 7), MA(close, 25))"},
            {"name": "量价齐升", "code": "signal = (close > MA(close, 5)) AND (volume_ratio(volume, 10) > 1.5)"},
        ],
        "tips": [
            "✓ 函数第一个参数是数据列 (close/volume/...), 后面是数字参数 (周期等)",
            "✓ 函数名大小写不敏感 (MA = ma = Ma)",
            "✓ 比较运算返回 bool Series, 可以直接 AND/OR",
            "✓ 想做空: 让 signal 返回 -1 (例: signal = -1 * (RSI > 70))",
            "✗ 不要写赋值 (如 x = MA(...)), 表达式必须单行无副作用",
            "✗ 不要调用 Python 内置 (如 sum/abs/len 都没暴露)",
            "✗ 不要下标访问 (df['close'] 这种是不允许的, 直接用 close 列名)",
        ],
    }