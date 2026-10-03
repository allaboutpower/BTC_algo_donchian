"""參數掃描：測試不同時間級別 (timeframe)、唐奇安週期 (dc_period)、
止損設定 (init_stop_atr_mult / trail_stop_atr_mult) 對 PnL 的影響。
"""
from __future__ import annotations

import copy
import dataclasses
import itertools

import pandas as pd

from .config import StrategyParams
from .data import resample_ohlcv
from .engine import run_backtest, _infer_bars_per_year
from .metrics import compute_metrics


def run_sweep(
    raw_df: pd.DataFrame,
    base_params: StrategyParams,
    timeframes: list[str] | None = None,
    dc_periods: list[int] | None = None,
    init_stop_atr_mults: list[float] | None = None,
    trail_stop_atr_mults: list[float] | None = None,
) -> pd.DataFrame:
    """對 raw_df（原始頻率 OHLCV）在給定的參數組合上跑回測，回傳每組合
    一列的績效總表（依 Sharpe 由高到低排序）。

    未被指定要掃描的參數維度沿用 base_params 對應欄位的單一值。
    """
    timeframes = timeframes or [base_params.timeframe]
    dc_periods = dc_periods or [base_params.dc_period]
    init_stop_atr_mults = init_stop_atr_mults or [base_params.init_stop_atr_mult]
    trail_stop_atr_mults = trail_stop_atr_mults or [base_params.trail_stop_atr_mult]

    resample_cache: dict[str, pd.DataFrame] = {}
    rows = []

    combos = list(
        itertools.product(timeframes, dc_periods, init_stop_atr_mults, trail_stop_atr_mults)
    )
    for tf, dc_period, init_mult, trail_mult in combos:
        if tf not in resample_cache:
            resample_cache[tf] = resample_ohlcv(raw_df, tf)
        df_tf = resample_cache[tf]

        params = dataclasses.replace(
            base_params,
            timeframe=tf,
            dc_period=dc_period,
            init_stop_atr_mult=init_mult,
            trail_stop_atr_mult=trail_mult,
        )

        result = run_backtest(df_tf, params)
        bars_per_year = _infer_bars_per_year(tf)
        m = compute_metrics(result, bars_per_year)

        row = {
            "timeframe": tf,
            "dc_period": dc_period,
            "init_stop_atr_mult": init_mult,
            "trail_stop_atr_mult": trail_mult,
            "n_bars": len(df_tf),
            **m,
        }
        rows.append(row)

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("sharpe", ascending=False).reset_index(drop=True)
    return out
