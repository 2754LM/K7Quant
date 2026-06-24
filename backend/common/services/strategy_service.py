"""策略业务: CRUD + 编译验证 + 模板生成"""
from typing import List

from backend.common.storage import crud
from backend.core.strategy import (
    StrategyEngine,
    get_builtin_strategies,
    get_strategy_dsl_template,
    BUILTIN_STRATEGIES,
)
from backend.core.factor import list_factors as _list_factors


def _code_looks_like_python(code: str) -> bool:
    """简单检测 code 是不是 Python (有 def 关键字 / 缩进函数体)"""
    return ("def init" in code or "def on_bar" in code
            or "import " in code.split("\n")[0])


def init_builtin_strategies():
    """启动时把预置策略写入 DB (如果还没有); 已存在则同步 params_schema / description / code

    内置策略 code 总是从 BUILTIN_STRATEGIES 重置 (避免被前端的 switchCodeType 流程覆盖成 Python 模板)
    用户想改 builtin 应该用"另存为新策略"
    """
    existing = {s["name"]: s for s in crud.list_strategies()}
    for s in get_builtin_strategies():
        ct = s.get("code_type", "dsl")
        ctx_tfs = s.get("context_timeframes") or []
        ctx_n = int(s.get("context_lookback") or 20)
        if s["name"] in existing:
            old = existing[s["name"]]
            sid = old["id"]
            # 检测 code 是否需要重置 (旧 code 与模板不一致, 或 code_type/code 不匹配)
            code_mismatch = old.get("code") != s["code"]
            type_mismatch = old.get("code_type", "dsl") != ct
            # 检测 type 与 code 实际语言不一致 (例如 dsl type 但代码是 Python)
            type_code_mismatch = (
                (ct == "dsl" and _code_looks_like_python(old.get("code", ""))) or
                (ct == "python" and not _code_looks_like_python(old.get("code", "")))
            )
            schema_changed = old.get("params_schema") != s["params_schema"]
            desc_changed = old.get("description") != s["description"]
            ctx_changed = (old.get("context_timeframes") or []) != ctx_tfs
            ctx_n_changed = int(old.get("context_lookback") or 20) != ctx_n

            need_update = (type_mismatch or type_code_mismatch or
                           schema_changed or desc_changed or
                           ctx_changed or ctx_n_changed)
            if need_update:
                try:
                    crud.update_strategy(
                        strategy_id=sid,
                        name=old["name"],
                        description=s["description"],
                        category=old.get("category") or s["category"],
                        # 内置策略 code 总是从模板重置 (修复用户切换 code_type 时被覆盖的 bug)
                        code=s["code"],
                        code_type=ct,
                        params_schema=s["params_schema"],
                        context_timeframes=ctx_tfs,
                        context_lookback=ctx_n,
                    )
                    if type_code_mismatch or type_mismatch:
                        print(f"[init_builtin_strategies] {s['name']} (id={sid}) "
                              f"code 已重置 (之前 type={old.get('code_type','dsl')}/code 错配)")
                except Exception as e:
                    print(f"[init_builtin_strategies] update {s['name']} 失败: {e}")
            continue
        crud.create_strategy(
            name=s["name"], description=s["description"],
            category=s["category"], code=s["code"],
            code_type=ct,
            params_schema=s["params_schema"],
            context_timeframes=ctx_tfs,
            context_lookback=ctx_n,
            is_builtin=1,
        )


def list_strategies() -> List[dict]:
    return crud.list_strategies()


def get_strategy(strategy_id: int) -> dict:
    return crud.get_strategy(strategy_id)


def create_strategy(data: dict) -> dict:
    """用户自定义策略"""
    code = data.get("code", "")
    code_type = data.get("code_type", "dsl")
    ctx_tfs = data.get("context_timeframes") or []
    ctx_lookback = int(data.get("context_lookback") or 20)
    # 验证代码可编译
    if code_type == "python":
        from backend.core.strategy.sandbox import validate_python_strategy
        r = validate_python_strategy(code)
        if not r["ok"]:
            return {"error": f"Python 策略校验失败: {r['error']}"}
    else:
        r = validate_code(code, code_type=code_type,
                          context_timeframes=ctx_tfs, context_lookback=ctx_lookback)
        if not r.get("ok"):
            return {"error": f"策略代码无法编译: {r.get('error', '未知错误')}"}
    sid = crud.create_strategy(
        name=data["name"], description=data.get("description", ""),
        category=data.get("category", "custom"),
        code=code, code_type=code_type,
        params_schema=data.get("params_schema", {}),
        context_timeframes=ctx_tfs,
        context_lookback=ctx_lookback,
        is_builtin=0,
    )
    return {"id": sid, "ok": True}


def update_strategy(strategy_id: int, data: dict) -> dict:
    code = data.get("code", "")
    code_type = data.get("code_type", "dsl")
    ctx_tfs = data.get("context_timeframes")
    ctx_lookback = data.get("context_lookback")
    if code:
        if code_type == "python":
            from backend.core.strategy.sandbox import validate_python_strategy
            r = validate_python_strategy(code)
            if not r["ok"]:
                return {"error": f"Python 策略校验失败: {r['error']}"}
        else:
            r = validate_code(code, code_type=code_type,
                              context_timeframes=ctx_tfs or [],
                              context_lookback=int(ctx_lookback or 20))
            if not r.get("ok"):
                return {"error": f"策略代码无法编译: {r.get('error', '未知错误')}"}
    crud.update_strategy(
        strategy_id=strategy_id,
        name=data["name"], description=data.get("description", ""),
        category=data.get("category", "custom"),
        code=code, code_type=code_type,
        params_schema=data.get("params_schema", {}),
        context_timeframes=ctx_tfs,
        context_lookback=ctx_lookback,
    )
    return {"ok": True}


def delete_strategy(strategy_id: int) -> dict:
    crud.delete_strategy(strategy_id)
    return {"ok": True}


def validate_code(code: str, code_type: str = "dsl",
                   context_timeframes: list = None,
                   context_lookback: int = 20) -> dict:
    """实时校验策略代码

    DSL 模式下, 如果传了 context_timeframes, 会预生成 ctx_* 变量名让 AST 校验通过
    (不会真的拉 K 线, 只为了让 validator 认识这些名字)
    """
    if code_type == "python":
        from backend.core.strategy.sandbox import validate_python_strategy
        return validate_python_strategy(code)
    ctx_extra_cols = set()
    if context_timeframes:
        from backend.core.strategy.context import _tf_name
        from backend.core.strategy.context import _compute_ctx_for_tf  # noqa
        # 生成所有可能的 ctx_<tf>_<col>_<stat><n> 名字
        cols = ("close", "open", "high", "low", "volume")
        stats = ("ma", "max", "min", "std", "sum")
        for tf in context_timeframes:
            tfn = _tf_name(tf)
            for c in cols:
                ctx_extra_cols.add(f"ctx_{tfn}_{c}")
            for s in stats:
                ctx_extra_cols.add(f"ctx_{tfn}_{s}{context_lookback}")
    try:
        signal_fn, rules = StrategyEngine.compile(
            code, {}, ctx_extra_cols=ctx_extra_cols,
        )
        return {"ok": True, "rules": rules}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def validate_python(code: str) -> dict:
    """Python 策略编译测试"""
    from backend.core.strategy.sandbox import validate_python_strategy
    return validate_python_strategy(code)


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
    from backend.core.strategy import get_dsl_docs as _engine_docs
    return _engine_docs()