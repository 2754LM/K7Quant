"""K7Quant FastAPI 主入口"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.routers import backtest as backtest_router
from backend.routers import data as data_router
from backend.routers import config as config_router


app = FastAPI(
    title="K7Quant",
    description="币安加密货币量化回测系统",
    version="3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(backtest_router.router)
app.include_router(data_router.router)
app.include_router(config_router.router)


@app.get("/api/health")
def health():
    from quant_core.settings import C
    from quant_core.data.fetcher import get_fetcher
    try:
        server_time = get_fetcher().server_time()
        return {"status": "ok", "binance_time": server_time}
    except Exception as e:
        return {"status": "ok", "binance_time": None, "warning": str(e)}


# 静态前端
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")
if os.path.isdir(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/")
    def serve_index():
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))

    @app.get("/{path:path}")
    def serve_spa(path: str):
        full = os.path.join(FRONTEND_DIST, path)
        if os.path.isfile(full):
            return FileResponse(full)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))


if __name__ == "__main__":
    import uvicorn
    from quant_core.settings import C
    port = int(C.get("server.port", 8765))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")