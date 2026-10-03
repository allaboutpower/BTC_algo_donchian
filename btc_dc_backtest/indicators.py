"""技術指標：唐奇安通道 (Donchian Channel)、ATR、RMA、實現波動、RSI。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def donchian_channel(df: pd.DataFrame, period: int) -> pd.DataFrame:
    """計算唐奇安通道上下軌。

    為避免前視偏誤 (lookahead bias)，突破判斷用的上軌是「不含當前這根
    K 棒」的過去 period 根最高價 (shift(1).rolling(period).max())，
    也就是說當根 K 棒收盤時，我們拿「前 period 根」的高點來判斷是否突破，
    這是站在該根 K 棒收盤當下即可取得的資訊。
    """
    upper = df["high"].shift(1).rolling(period).max()
    lower = df["low"].shift(1).rolling(period).min()
    return pd.DataFrame({"dc_upper": upper, "dc_lower": lower}, index=df.index)


def atr(df: pd.DataFrame, period: int) -> pd.Series:
    """Average True Range，使用 Wilder's 平滑 (等同 EMA alpha=1/period)。"""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def rma(series: pd.Series, period: int) -> pd.Series:
    """Wilder's Running Moving Average (RMA)，等同 EMA alpha=1/period。"""
    return series.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def realized_vol_annualized(close: pd.Series, lookback: int, bars_per_year: float) -> pd.Series:
    """以過去 lookback 根 K 棒的對數報酬標準差估計年化實現波動率。"""
    log_ret = np.log(close / close.shift(1))
    return log_ret.rolling(lookback).std() * np.sqrt(bars_per_year)


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI：以 RMA 平滑上漲/下跌幅度，0~100。"""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = rma(gain, period)
    avg_loss = rma(loss, period)
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
