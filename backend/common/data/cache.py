"""本地缓存: 按 timeframes/{symbol}.csv 存储"""
import pandas as pd
from pathlib import Path
from typing import Optional

from backend.core import CACHE_DIR


class DataCache:
    def __init__(self, root: Path = None):
        self.root = root or CACHE_DIR

    def path(self, symbol: str, timeframe: str) -> Path:
        d = self.root / timeframe
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{symbol}.csv"

    def has(self, symbol: str, timeframe: str) -> bool:
        return self.path(symbol, timeframe).exists()

    def read(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        p = self.path(symbol, timeframe)
        if not p.exists():
            return None
        try:
            return pd.read_csv(p, parse_dates=["date"])
        except Exception:
            return None

    def write(self, symbol: str, timeframe: str, df: pd.DataFrame):
        if df.empty:
            return
        df.to_csv(self.path(symbol, timeframe), index=False)

    def list(self, timeframe: str = None) -> dict:
        if timeframe:
            d = self.root / timeframe
            if not d.exists():
                return {}
            return {f.stem: f for f in d.glob("*.csv")}
        out = {}
        for tf_dir in self.root.iterdir():
            if tf_dir.is_dir():
                out[tf_dir.name] = {f.stem: f for f in tf_dir.glob("*.csv")}
        return out

    def clear(self, timeframe: str = None, symbol: str = None):
        if symbol and timeframe:
            p = self.path(symbol, timeframe)
            if p.exists():
                p.unlink()
        elif timeframe:
            d = self.root / timeframe
            if d.exists():
                for f in d.glob("*.csv"):
                    f.unlink()
        else:
            for tf_dir in self.root.iterdir():
                if tf_dir.is_dir():
                    for f in tf_dir.glob("*.csv"):
                        f.unlink()

    def stats(self) -> dict:
        # files[] 给前端 DataPanel 用 (name="{tf}/{symbol}.csv", size_kb, mtime 秒)
        out = {"files": [], "by_timeframe": {}, "total_size_kb": 0, "total_files": 0}
        if not self.root.exists():
            return out
        for tf_dir in sorted(self.root.iterdir()):
            if not tf_dir.is_dir():
                continue
            files = sorted(tf_dir.glob("*.csv"))
            sz = 0
            for f in files:
                st = f.stat()
                sz += st.st_size
                out["files"].append({
                    "name": f"{tf_dir.name}/{f.name}",
                    "size_kb": round(st.st_size / 1024, 1),
                    "mtime": st.st_mtime,
                })
            out["by_timeframe"][tf_dir.name] = {
                "count": len(files), "size_kb": round(sz / 1024, 1)
            }
            out["total_size_kb"] += sz / 1024
            out["total_files"] += len(files)
        out["total_size_kb"] = round(out["total_size_kb"], 1)
        return out


_cache: Optional[DataCache] = None


def get_cache() -> DataCache:
    global _cache
    if _cache is None:
        _cache = DataCache()
    return _cache