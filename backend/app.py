"""FastAPI 应用入口"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.core import ROOT, LOGS_DIR
from backend.core.logger import log
from backend.core.config import load_config
from backend.storage import init_schema, get_conn, crud
from backend.services import strategy_service, symbol_service
from backend.api import (
    backtest_api, factor_api, strategy_api,
    data_api, symbol_api, config_api, trade_api,
)


app = FastAPI(
    title="K7Quant",
    description="加密货币量化回测系统 - 因子库 + 自定义策略 + 模拟/实盘",
    version="4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    log.info("=" * 60)
    log.info("K7Quant starting...")
    load_config()
    init_schema(get_conn())
    symbol_service.init_default_symbols()
    strategy_service.init_builtin_strategies()
    log.info("Config loaded, DB initialized, builtin strategies registered")
    log.info("=" * 60)


# 注册路由
app.include_router(backtest_api.router, prefix="/api/backtest", tags=["回测"])
app.include_router(factor_api.router, prefix="/api/factor", tags=["因子"])
app.include_router(strategy_api.router, prefix="/api/strategy", tags=["策略"])
app.include_router(data_api.router, prefix="/api/data", tags=["数据"])
app.include_router(symbol_api.router, prefix="/api/symbol", tags=["币种"])
app.include_router(config_api.router, prefix="/api/config", tags=["配置"])
app.include_router(trade_api.router, prefix="/api/trade", tags=["交易"])


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
        full = FRONTEND_DIST / path
        if full.is_file():
            return FileResponse(str(full))
        return FileResponse(str(FRONTEND_DIST / "index.html"))


if __name__ == "__main__":
    import uvicorn
    port = int(load_config().get("server", {}).get("port", 8765))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")