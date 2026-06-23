"""通用工具"""
import numpy as np
import pandas as pd


def df_dates(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    if df.empty:
        return df
    return df[(df["date"] >= start) & (df["date"] <= end)].reset_index(drop=True)


def to_records(df: pd.DataFrame, cols: list = None) -> list:
    if df is None or df.empty:
        return []
    cols = cols or [c for c in df.columns]
    out = []
    for _, r in df.iterrows():
        rec = {}
        for c in cols:
            v = r[c]
            if isinstance(v, (pd.Timestamp,)):
                rec[c] = v.strftime("%Y-%m-%d %H:%M:%S") if v.hour or v.minute else v.strftime("%Y-%m-%d")
            elif isinstance(v, (np.floating, np.integer)):
                rec[c] = float(v) if not np.isnan(v) else None
            elif isinstance(v, float) and np.isnan(v):
                rec[c] = None
            else:
                rec[c] = v
        out.append(rec)
    return out


def safe(v):
    if v is None:
        return None
    if isinstance(v, (np.floating, np.integer)):
        v = float(v)
        if np.isnan(v) or np.isinf(v):
            return None
    return v


def fmt(v, spec=".4f", na="N/A"):
    """safe + format: None/NaN/inf 返回 na, 否则 format(spec)."""
    v = safe(v)
    if v is None:
        return na
    try:
        return format(v, spec)
    except (TypeError, ValueError):
        return na


def sanitize(metrics: dict) -> dict:
    return {k: safe(v) for k, v in (metrics or {}).items()}