"""策略业务: CRUD + 编译验证 + 模板生成"""
from typing import List

from backend.storage import crud
from backend.strategy import (
    StrategyEngine,
    get_builtin_strategies,
    get_strategy_dsl_template,
    BUILTIN_STRATEGIES,
)
from backend.factor import list_factors as _list_factors


def init_builtin_strategies():
    """启动时把预置策略写入 DB (如果还没有); 已存在则同步 params_schema / description / code"""
    existing = {s["name"]: s for s in crud.list_strategies()}
    for s in get_builtin_strategies():
        if s["name"] in existing:
            # 已存在: 同步 params_schema (允许新增 unit/hint 等字段, 不影响用户自定义修改的 name/code)
            old = existing[s["name"]]
            sid = old["id"]
            # 只在 schema 有差异时更新, 避免无谓写库
            if old.get("params_schema") != s["params_schema"] or old.get("description") != s["description"]:
                try:
                    crud.update_strategy(
                        strategy_id=sid,
                        name=old["name"],  # 保留原名
                        description=s["description"],
                        category=old.get("category") or s["category"],
                        code=old["code"],  # 保留原 code (可能用户改过)
                        params_schema=s["params_schema"],
                    )
                except Exception as e:
                    print(f"[init_builtin_strategies] update {s['name']} 失败: {e}")
            continue
        crud.create_strategy(
            name=s["name"], description=s["description"],
            category=s["category"], code=s["code"],
            params_schema=s["params_schema"], is_builtin=1,
        )


def list_strategies() -> List[dict]:
    return crud.list_strategies()


def get_strategy(strategy_id: int) -> dict:
    return crud.get_strategy(strategy_id)


def create_strategy(data: dict) -> dict:
    """用户自定义策略"""
    code = data.get("code", "")
    # 验证代码可编译
    try:
        StrategyEngine.compile(code, {})
    except Exception as e:
        return {"error": f"策略代码无法编译: {e}"}
    sid = crud.create_strategy(
        name=data["name"], description=data.get("description", ""),
        category=data.get("category", "custom"),
        code=code, params_schema=data.get("params_schema", {}),
        is_builtin=0,
    )
    return {"id": sid, "ok": True}


def update_strategy(strategy_id: int, data: dict) -> dict:
    code = data.get("code", "")
    if code:
        try:
            StrategyEngine.compile(code, {})
        except Exception as e:
            return {"error": f"策略代码无法编译: {e}"}
    crud.update_strategy(
        strategy_id=strategy_id,
        name=data["name"], description=data.get("description", ""),
        category=data.get("category", "custom"),
        code=code, params_schema=data.get("params_schema", {}),
    )
    return {"ok": True}


def delete_strategy(strategy_id: int) -> dict:
    crud.delete_strategy(strategy_id)
    return {"ok": True}


def validate_code(code: str) -> dict:
    """实时校验策略代码"""
    try:
        signal_fn, rules = StrategyEngine.compile(code, {})
        return {"ok": True, "rules": rules}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_templates() -> dict:
    """获取 DSL 模板和预置策略代码"""
    return {
        "builtin": [
            {
                "name": s["name"],
                "description": s["description"],
                "category": s["category"],
                "code": s["code"],
                "params_schema": s["params_schema"],
            } for s in BUILTIN_STRATEGIES
        ],
        "blank_template": get_strategy_dsl_template(),
        "factor_list": _list_factors(),
    }


def get_dsl_docs() -> dict:
    """DSL 语法文档"""
    return {
        "syntax": """
策略代码格式 (类 Python 表达式):

# 注释以 # 开头
signal = <表达式>          # 必需, 返回 0/1 (或 -1/0/1 支持做空)
止损 = 0.05                # 可选, 5% 止损
止盈 = 0.15                # 可选, 15% 止盈
仓位 = 1.0                 # 可选, 满仓 (0-1)

支持函数 (来自因子库):
  MA(close, N) / EMA(close, N) / RSI(close, N)
  MACD(close, fast, slow, signal)
  BOLL(close, N, std) / KDJ(close, N, m1, m2)
  momentum(close, N) / volatility(close, N)
  high_break(close, N) / low_break(close, N)
  ...

支持比较: > < >= <= == !=
支持逻辑: AND OR NOT
支持交叉: CROSS_UP(a, b)  CROSS_DOWN(a, b)
""",
        "examples": [
            {
                "name": "双均线",
                "code": "signal = CROSS_UP(MA(close, 7), MA(close, 25)) - CROSS_DOWN(MA(close, 7), MA(close, 25))"
            },
            {
                "name": "RSI 阈值",
                "code": "signal = RSI(close, 14) < 30"
            },
            {
                "name": "多条件",
                "code": "signal = (RSI(close, 14) < 30) AND (volume > volume_ma(volume, 20))"
            },
        ]
    }