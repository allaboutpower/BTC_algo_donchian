"""OHLCV 資料讀取與時間級別轉換 (resample)。"""
from __future__ import annotations

import pandas as pd

_COL_ALIASES = {
    "timestamp": ["open time", "timestamp", "date", "time", "datetime", "open_time"],
    "open": ["open", "o"],
    "high": ["high", "h"],
    "low": ["low", "l"],
    "close": ["close", "c", "adj close", "adj_close"],
    "volume": ["volume", "vol", "v"],
}


def _find_col(columns: list[str], candidates: list[str]) -> str | None:
    lower_map = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand in lower_map:
            return lower_map[cand]
    return None


def load_csv(path: str) -> pd.DataFrame:
    """讀取使用者提供的 OHLCV CSV，回傳以時間為 index、欄位為
    open/high/low/close/volume 的 DataFrame（依時間升序排列）。

    容許欄名大小寫與常見別名差異（例如 date/timestamp/datetime，
    o/open，adj close/close 等）。volume 欄位若不存在則補 0。
    """
    df = pd.read_csv(path)
    cols = list(df.columns)

    ts_col = _find_col(cols, _COL_ALIASES["timestamp"])
    if ts_col is None:
        raise ValueError(
            f"找不到時間欄位，請確認 CSV 含有 timestamp/date/datetime 之一。現有欄位: {cols}"
        )

    out = {}
    for field in ["open", "high", "low", "close"]:
        col = _find_col(cols, _COL_ALIASES[field])
        if col is None:
            raise ValueError(f"找不到 {field} 欄位，現有欄位: {cols}")
        out[field] = pd.to_numeric(df[col], errors="coerce")

    vol_col = _find_col(cols, _COL_ALIASES["volume"])
    out["volume"] = pd.to_numeric(df[vol_col], errors="coerce") if vol_col else 0.0

    ts = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
    result = pd.DataFrame(out)
    result.index = ts
    result.index.name = "timestamp"
    result = result.dropna(subset=["open", "high", "low", "close"])
    result = result[~result.index.isna()]
    result = result.sort_index()
    result = result[~result.index.duplicated(keep="last")]
    return result


def resample_ohlcv(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """將 OHLCV 資料 resample 成指定時間級別（pandas offset alias，
    例如 '1D'、'2D'、'3D'、'4H'、'1H'、'15min'）。

    若原始資料頻率比目標時間級別粗（例如原始只有日線卻要求 1H），
    resample 後大量列會是 NaN，會被丟棄，等同於沒有效果，使用時應注意。
    """
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    out = df.resample(timeframe).agg(agg)
    out = out.dropna(subset=["open", "high", "low", "close"])
    return out
