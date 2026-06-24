"""FastAPI 应用入口

启动流程:
1. lifespan: load_config → init_schema → migrations → 注册内置币种/策略/因子
2. 注册 CORS + TrustedHost middleware
3. 注册请求日志 middleware
4. 注册全局异常 handler (在 exceptions/handlers.py)
5. 注册 controllers 路由
6. 静态前端 serve (frontend/dist)
"""
import os
import sys
import time as _time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.config.paths import ROOT
from backend.config.settings import load_config
from backend.core.logging import log
from backend.exceptions.handlers import register_exception_handlers
from backend.repositories import crud, models  # noqa: 触发 ORM 建表
from backend.services import strategy_service, symbol_service, factor_service
# 延迟 import controllers 内的子模块, 避免循环引用
from backend.controllers import backtest_controller  # noqa
from backend.controllers import config_controller  # noqa
from backend.controllers import data_controller  # noqa
from backend.controllers import factor_controller  # noqa
from backend.controllers import rule_controller  # noqa
from backend.controllers import strategy_controller  # noqa
from backend.controllers import symbol_controller  # noqa
from backend.controllers import trade_controller  # noqa
from backend.controllers import verify_controller  # noqa


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=" * 60)
    log.info("K7Quant starting...")
    cfg = load_config()
    log.info(f"[init] config.yaml 加载: port={cfg.get('server', {}).get('port')}, "
             f"tf默认={cfg.get('backtest', {}).get('default_timeframe')}")
    models.get_engine()  # ORM 自动建表
    log.info("[init] ORM 表结构就绪")
    _run_migrations()
    symbol_service.init_default_symbols()
    log.info("[init] 默认币种注册完成")
    strategy_service.init_builtin_strategies()
    log.info("[init] 内置策略注册完成")
    factor_service.load_custom_factors_from_db()
    log.info("Config loaded, DB initialized, builtin strategies registered")
    log.info("=" * 60)
    yield
    log.info("K7Quant shutting down...")
    try:
        from backend.services.live_trader import get_live_trader
        get_live_trader().stop()
    except Exception as e:
        log.warning(f"[shutdown] 停止实盘运行器失败: {e}")


def _run_migrations():
    """轻量迁移: 给已有表加新列 (SQLAlchemy create_all 不会 ALTER)"""
    from sqlalchemy import text
    with models.get_engine().begin() as conn:
        # factors 表: 新增 is_custom / dsl_code / created_at
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(factors)")).fetchall()}
        if "is_custom" not in cols:
            conn.execute(text("ALTER TABLE factors ADD COLUMN is_custom BOOLEAN DEFAULT 0"))
            log.info("[migrate] factors.is_custom 已添加")
        if "dsl_code" not in cols:
            conn.execute(text("ALTER TABLE factors ADD COLUMN dsl_code TEXT"))
            log.info("[migrate] factors.dsl_code 已添加")
        if "created_at" not in cols:
            conn.execute(text("ALTER TABLE factors ADD COLUMN created_at DATETIME"))
            log.info("[migrate] factors.created_at 已添加")
        # strategies 表: 新增 code_type (dsl/python)
        s_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(strategies)")).fetchall()}
        if "code_type" not in s_cols:
            conn.execute(text("ALTER TABLE strategies ADD COLUMN code_type VARCHAR(16) DEFAULT 'dsl'"))
            log.info("[migrate] strategies.code_type 已添加")
        if "context_timeframes" not in s_cols:
            conn.execute(text("ALTER TABLE strategies ADD COLUMN context_timeframes TEXT"))
            log.info("[migrate] strategies.context_timeframes 已添加")
        if "context_lookback" not in s_cols:
            conn.execute(text("ALTER TABLE strategies ADD COLUMN context_lookback INTEGER DEFAULT 20"))
            log.info("[migrate] strategies.context_lookback 已添加")


app = FastAPI(
    title="K7Quant",
    description="加密货币量化回测系统 - 因子库 + 自定义策略 + 模拟/实盘",
    version="4.0",
    lifespan=lifespan,
)

# 本地单机应用: 仅允许本机来源跨域 (含 vite dev 端口), 不再对全网开放
_port = load_config().get("server", {}).get("port", 8765)
_allowed_origins = [
    f"http://127.0.0.1:{_port}", f"http://localhost:{_port}",
    "http://127.0.0.1:5173", "http://localhost:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 请求日志中间件: 记录每个 HTTP 请求的耗时和状态
@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = _time.time()
    response = await call_next(request)
    ms = (_time.time() - t0) * 1000
    if request.url.path.startswith("/api"):
        log.info(f"[HTTP] {request.method} {request.url.path} → {response.status_code} ({ms:.0f}ms)")
    return response


# ============ 全局异常处理 (在 exceptions/handlers.py 集中定义) ============
register_exception_handlers(app)


# ============ 路由注册 ============
app.include_router(backtest_controller.router, prefix="/api/backtest", tags=["回测"])
app.include_router(config_controller.router, prefix="/api/config", tags=["配置"])
app.include_router(data_controller.router, prefix="/api/data", tags=["数据"])
app.include_router(factor_controller.router, prefix="/api/factor", tags=["因子"])
app.include_router(rule_controller.router, prefix="/api/rule", tags=["自定义规则"])
app.include_router(strategy_controller.router, prefix="/api/strategy", tags=["策略"])
app.include_router(symbol_controller.router, prefix="/api/symbol", tags=["币种"])
app.include_router(trade_controller.router, prefix="/api/trade", tags=["交易"])
app.include_router(verify_controller.router)  # 自带 prefix="/api/verify"


@app.get("/api/health")
def health():
    from backend.repositories.binance_fetcher import BinanceFetcher
    info = BinanceFetcher().test_connectivity()
    return {
        "status": "ok" if info["reachable"] else "degraded",
        "binance": info,
    }


# ============ 静态前端 ============
FRONTEND_DIST = ROOT / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/")
    def serve_index():
        return FileResponse(str(FRONTEND_DIST / "index.html"))

    @app.get("/{path:path}")
    def serve_spa(path: str):
        base = FRONTEND_DIST.resolve()
        full = (base / path).resolve()
        # 防目录穿越
        if full.is_file() and (full == base or full.is_relative_to(base)):
            return FileResponse(str(full))
        return FileResponse(str(base / "index.html"))


if __name__ == "__main__":
    import uvicorn
    port = int(load_config().get("server", {}).get("port", 8765))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")