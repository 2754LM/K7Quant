"""K7Quant 一键启动"""
import os
import sys
import time
import threading
import webbrowser

os.environ["PYTHONIOENCODING"] = "utf-8"
PORT = 8765
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def open_browser():
    time.sleep(1.5)
    webbrowser.open(f"http://127.0.0.1:{PORT}")


if __name__ == "__main__":
    threading.Thread(target=open_browser, daemon=True).start()
    import uvicorn
    from backend.app import app

    print(f"\n{'='*50}")
    print(f"  K7Quant - 币安量化回测系统")
    print(f"  访问地址: http://127.0.0.1:{PORT}")
    print(f"  按 Ctrl+C 退出")
    print(f"{'='*50}\n")

    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")