"""FastAPI 应用入口"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.core import ROOT, LOGS_DIR
from backend.core.logger import log
from backend.core.config import load_config
from backend.storage import init_schema, crud  # noqa
from backend.services import strategy_service, symbol_service
from backend.api import (
    backtest_api, factor_api, strategy_api,
    data_api, symbol_api, config_api, trade_api, rule_api,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=" * 60)
    log.info("K7Quant starting...")
    load_config()
    init_schema()  # ORM 自动建表
    symbol_service.init_default_symbols()
    strategy_service.init_builtin_strategies()
    log.info("Config loaded, DB initialized, builtin strategies registered")
    log.info("=" * 60)
    yield


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


# 注册路由
app.include_router(backtest_api.router, prefix="/api/backtest", tags=["回测"])
app.include_router(factor_api.router, prefix="/api/factor", tags=["因子"])
app.include_router(strategy_api.router, prefix="/api/strategy", tags=["策略"])
app.include_router(data_api.router, prefix="/api/data", tags=["数据"])
app.include_router(symbol_api.router, prefix="/api/symbol", tags=["币种"])
app.include_router(config_api.router, prefix="/api/config", tags=["配置"])
app.include_router(trade_api.router, prefix="/api/trade", tags=["交易"])
app.include_router(rule_api.router, prefix="/api/rule", tags=["自定义规则"])


@app.get("/api/health")
def health():
    from backend.data.fetcher import get_fetcher
    info = get_fetcher().test_connectivity()
    return {
        "status": "ok" if info["reachable"] else "degraded",
        "binance": info,
    }


# 静态前端
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
        # 防目录穿越: 解析后必须仍位于 dist 内, 否则一律回退到 index.html
        if full.is_file() and (full == base or full.is_relative_to(base)):
            return FileResponse(str(full))
        return FileResponse(str(base / "index.html"))


if __name__ == "__main__":
    import uvicorn
    port = int(load_config().get("server", {}).get("port", 8765))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")