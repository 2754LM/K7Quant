@echo off
cd /d D:\Desktop\lh
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8765 --log-level info