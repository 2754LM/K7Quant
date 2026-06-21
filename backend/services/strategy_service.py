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
    """DSL 语法文档 (委托到 strategy 引擎统一维护)"""
    from backend.strategy import get_dsl_docs as _engine_docs
    return _engine_docs()