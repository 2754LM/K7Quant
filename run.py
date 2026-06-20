"""K7Quant 一键启动"""
import os
import sys
import time
import threading
import webbrowser

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

# 从配置读取端口
try:
    import yaml
    with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    PORT = int(cfg.get("server", {}).get("port", 8765))
    AUTO_OPEN = bool(cfg.get("server", {}).get("auto_open_browser", True))
except Exception:
    PORT = 8765
    AUTO_OPEN = True


def open_browser():
    if not AUTO_OPEN:
        return
    time.sleep(1.5)
    webbrowser.open(f"http://127.0.0.1:{PORT}")


if __name__ == "__main__":
    threading.Thread(target=open_browser, daemon=True).start()

    import uvicorn
    from backend.app import app

    print(f"\n{'='*50}")
    print(f"  K7Quant - 币安量化回测系统 v3.0")
    print(f"  访问地址: http://127.0.0.1:{PORT}")
    print(f"  按 Ctrl+C 退出")
    print(f"{'='*50}\n")

    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")