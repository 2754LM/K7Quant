"""数据业务层: 缓存查询 + 管理"""
import os

from quant_core.data.cache import DataCache


_cache_instance: DataCache = None


def _get_cache() -> DataCache:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = DataCache()
    return _cache_instance


def list_cache() -> dict:
    cache = _get_cache()
    out = []
    if not cache.root.exists():
        return {"files": [], "total_size_kb": 0, "by_timeframe": {}}

    total = 0
    by_tf = {}
    for tf_dir in sorted(cache.root.iterdir()):
        if not tf_dir.is_dir():
            continue
        files = list(tf_dir.glob("*.csv"))
        tf_size = 0
        for f in files:
            sz = f.stat().st_size
            tf_size += sz
            total += sz
            out.append({
                "name": f"{tf_dir.name}/{f.name}",
                "size_kb": round(sz / 1024, 1),
                "mtime": int(f.stat().st_mtime),
            })
        by_tf[tf_dir.name] = {
            "count": len(files),
            "size_kb": round(tf_size / 1024, 1),
        }

    return {
        "files": sorted(out, key=lambda x: x["name"]),
        "total_size_kb": round(total / 1024, 1),
        "by_timeframe": by_tf,
    }


def clear_cache(timeframe: str = None, symbol: str = None):
    _get_cache().clear(timeframe, symbol)
    return list_cache()