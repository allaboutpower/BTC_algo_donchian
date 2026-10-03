"""事件驅動回測引擎：唐奇安通道突破 + ATR 加碼 + 初始停損/Chandelier 追蹤停損。

多空都是純唐奇安通道突破，無其他濾網：
- 多方：收盤價突破 dc_period 根K棒的唐奇安上軌做多
- 空方：收盤價跌破 dc_period 根K棒的唐奇安下軌做空

同一時間只能持有一個部位（多空互斥）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import StrategyParams
from .indicators import atr, donchian_channel, realized_vol_annualized

_BARS_PER_YEAR = {
    "min": 365 * 24 * 60,
    "H": 365 * 24,
    "D": 365,
    "W": 52,
}


def _infer_bars_per_year(timeframe: str) -> float:
    """依 pandas offset alias 粗估年化用的 bar 數（用於實現波動年化）。"""
    import re

    m = re.match(r"(\d*)\s*([A-Za-z]+)", timeframe)
    if not m:
        return 365.0
    n = int(m.group(1)) if m.group(1) else 1
    unit = m.group(2)
    if unit.lower().startswith("min") or unit.lower() == "t":
        base = _BARS_PER_YEAR["min"]
    elif unit.upper().startswith("H"):
        base = _BARS_PER_YEAR["H"]
    elif unit.upper().startswith("W"):
        base = _BARS_PER_YEAR["W"]
    else:
        base = _BARS_PER_YEAR["D"]
    return base / n


@dataclass
class Trade:
    direction: str  # "long" or "short"
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    qty: float
    avg_entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    exit_reason: str
    num_units: int


@dataclass
class BacktestResult:
    params: StrategyParams
    equity_curve: pd.Series
    trades: list[Trade] = field(default_factory=list)

    @property
    def trades_df(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame(
                columns=[
                    "direction",
                    "entry_time",
                    "exit_time",
                    "qty",
                    "avg_entry_price",
                    "exit_price",
                    "pnl",
                    "pnl_pct",
                    "exit_reason",
                    "num_units",
                ]
            )
        return pd.DataFrame([t.__dict__ for t in self.trades])


def run_backtest(
    df: pd.DataFrame,
    params: StrategyParams,
) -> BacktestResult:
    """對已經 resample 成目標時間級別的 OHLCV 資料執行回測。

    決策時點：使用「不含當前 K 棒」的過去 N 根高/低點作為突破基準
    (見 indicators.donchian_channel)，於當前 K 棒收盤價判斷是否突破 /
    加碼 / 觸發停損，成交同樣假設發生在當前 K 棒收盤價（並附加
    slippage_bps 滑價與 fee_rate 手續費），停損若被當根最低/最高價觸及則
    以停損價成交，若開盤即跳空穿過停損價則以開盤價成交。

    若 params.short_enabled=True，另外允許放空：收盤價跌破過去 dc_period
    根K棒（與做多同一條唐奇安通道，同一交易週期）的最低點即觸發放空，
    無其他濾網。多空互斥：同一時間只能持有一個方向的部位。
    """
    required = max(params.atr_period, params.dc_period)
    if len(df) < required + 2:
        return BacktestResult(params=params, equity_curve=pd.Series(dtype=float), trades=[])

    atr_series = atr(df, params.atr_period)
    bars_per_year = _infer_bars_per_year(params.timeframe)
    vol_series = realized_vol_annualized(df["close"], params.vol_lookback, bars_per_year)

    dc = donchian_channel(df, params.dc_period)
    dc_upper_series = dc["dc_upper"]
    dc_lower_series = dc["dc_lower"]

    slip = params.slippage_bps / 10_000.0

    cash = params.initial_equity
    direction = 0  # 0=flat, 1=long, -1=short
    qty = 0.0
    avg_entry_price = 0.0  # 手續費內含的有效成本/收入價
    entry_time = None
    num_units = 0
    extreme_since_entry = 0.0  # long: 期間最高收盤價；short: 期間最低收盤價
    trail_stop = 0.0
    initial_stop = 0.0
    last_add_price = 0.0
    long_had_entry = False
    short_had_entry = False

    equity_curve = pd.Series(index=df.index, dtype=float)
    trades: list[Trade] = []

    closes = df["close"].values
    opens = df["open"].values
    lows = df["low"].values
    highs = df["high"].values
    idx = df.index

    for i in range(len(df)):
        close = closes[i]
        open_ = opens[i]
        low = lows[i]
        high = highs[i]
        cur_atr = atr_series.iloc[i]
        cur_dc_upper = dc_upper_series.iloc[i]
        cur_dc_lower = dc_lower_series.iloc[i]
        cur_vol = vol_series.iloc[i]
        equity_mark = cash + direction * qty * close

        exited_this_bar = False

        # ---- 管理現有多單：追蹤停損 / 停損出場 ----
        if direction == 1:
            extreme_since_entry = max(extreme_since_entry, close)
            if not np.isnan(cur_atr):
                new_trail = extreme_since_entry - params.trail_stop_atr_mult * cur_atr
                trail_stop = max(trail_stop, new_trail)
            effective_stop = max(initial_stop, trail_stop)

            if low <= effective_stop:
                fill_price = (open_ if open_ < effective_stop else effective_stop) * (1 - slip)
                proceeds = qty * fill_price * (1 - params.fee_rate)
                cost_basis = qty * avg_entry_price
                pnl = proceeds - cost_basis
                trades.append(
                    Trade(
                        direction="long",
                        entry_time=entry_time,
                        exit_time=idx[i],
                        qty=qty,
                        avg_entry_price=avg_entry_price,
                        exit_price=fill_price,
                        pnl=pnl,
                        pnl_pct=pnl / cost_basis if cost_basis else 0.0,
                        exit_reason="stop",
                        num_units=num_units,
                    )
                )
                cash += proceeds
                direction, qty, avg_entry_price, num_units = 0, 0.0, 0.0, 0
                exited_this_bar = True

        # ---- 管理現有空單：追蹤停損 / 停損出場 ----
        elif direction == -1:
            extreme_since_entry = min(extreme_since_entry, close)
            if not np.isnan(cur_atr):
                new_trail = extreme_since_entry + params.short_trail_stop_atr_mult * cur_atr
                trail_stop = min(trail_stop, new_trail)
            effective_stop = min(initial_stop, trail_stop)

            if high >= effective_stop:
                fill_price = (open_ if open_ > effective_stop else effective_stop) * (1 + slip)
                cost = qty * fill_price * (1 + params.fee_rate)
                proceeds_basis = qty * avg_entry_price
                pnl = proceeds_basis - cost
                trades.append(
                    Trade(
                        direction="short",
                        entry_time=entry_time,
                        exit_time=idx[i],
                        qty=qty,
                        avg_entry_price=avg_entry_price,
                        exit_price=fill_price,
                        pnl=pnl,
                        pnl_pct=pnl / proceeds_basis if proceeds_basis else 0.0,
                        exit_reason="stop",
                        num_units=num_units,
                    )
                )
                cash -= cost
                direction, qty, avg_entry_price, num_units = 0, 0.0, 0.0, 0
                exited_this_bar = True

        # ---- 多單加碼 ----
        if (
            direction == 1
            and not exited_this_bar
            and num_units - 1 < params.max_pyramids
            and not np.isnan(cur_atr)
            and close >= last_add_price + params.pyramid_atr_mult * cur_atr
        ):
            scale = 1.0
            if params.vol_target_enabled and not np.isnan(cur_vol) and cur_vol > 0:
                scale = min(1.0, params.vol_target_annual / cur_vol)
            add_qty = (equity_mark * params.risk_pct * scale) / (params.init_stop_atr_mult * cur_atr)
            if add_qty > 0:
                fill_price = close * (1 + slip)
                effective_price = fill_price * (1 + params.fee_rate)
                cost = add_qty * effective_price
                if cost <= cash:
                    cash -= cost
                    avg_entry_price = (avg_entry_price * qty + effective_price * add_qty) / (qty + add_qty)
                    qty += add_qty
                    num_units += 1
                    last_add_price = close
                    initial_stop = max(initial_stop, fill_price - params.init_stop_atr_mult * cur_atr)

        # ---- 空單加碼 ----
        if (
            direction == -1
            and not exited_this_bar
            and num_units - 1 < params.short_max_pyramids
            and not np.isnan(cur_atr)
            and close <= last_add_price - params.short_pyramid_atr_mult * cur_atr
        ):
            scale = 1.0
            if params.vol_target_enabled and not np.isnan(cur_vol) and cur_vol > 0:
                scale = min(1.0, params.vol_target_annual / cur_vol)
            add_qty = (equity_mark * params.short_risk_pct * scale) / (
                params.short_init_stop_atr_mult * cur_atr
            )
            if add_qty > 0:
                fill_price = close * (1 - slip)
                effective_price = fill_price * (1 - params.fee_rate)
                proceeds = add_qty * effective_price
                cash += proceeds
                avg_entry_price = (avg_entry_price * qty + effective_price * add_qty) / (qty + add_qty)
                qty += add_qty
                num_units += 1
                last_add_price = close
                initial_stop = min(initial_stop, fill_price + params.short_init_stop_atr_mult * cur_atr)

        # ---- 進場（多空互斥，僅在空手時判斷）----
        if direction == 0 and not exited_this_bar:
            can_enter_long = (
                not np.isnan(cur_atr)
                and not np.isnan(cur_dc_upper)
                and close > cur_dc_upper
                and (params.allow_reentry or not long_had_entry)
            )
            can_enter_short = (
                params.short_enabled
                and not np.isnan(cur_atr)
                and not np.isnan(cur_dc_lower)
                and close < cur_dc_lower
                and (params.short_allow_reentry or not short_had_entry)
            )

            if can_enter_long:
                scale = 1.0
                if params.vol_target_enabled and not np.isnan(cur_vol) and cur_vol > 0:
                    scale = min(1.0, params.vol_target_annual / cur_vol)
                entry_qty = (equity_mark * params.risk_pct * scale) / (params.init_stop_atr_mult * cur_atr)
                if entry_qty > 0:
                    fill_price = close * (1 + slip)
                    effective_price = fill_price * (1 + params.fee_rate)
                    cost = entry_qty * effective_price
                    if cost <= cash:
                        cash -= cost
                        direction = 1
                        qty = entry_qty
                        avg_entry_price = effective_price
                        entry_time = idx[i]
                        num_units = 1
                        last_add_price = close
                        extreme_since_entry = close
                        initial_stop = fill_price - params.init_stop_atr_mult * cur_atr
                        trail_stop = fill_price - params.trail_stop_atr_mult * cur_atr
                        long_had_entry = True

            elif can_enter_short:
                scale = 1.0
                if params.vol_target_enabled and not np.isnan(cur_vol) and cur_vol > 0:
                    scale = min(1.0, params.vol_target_annual / cur_vol)
                entry_qty = (equity_mark * params.short_risk_pct * scale) / (
                    params.short_init_stop_atr_mult * cur_atr
                )
                if entry_qty > 0:
                    fill_price = close * (1 - slip)
                    effective_price = fill_price * (1 - params.fee_rate)
                    proceeds = entry_qty * effective_price
                    cash += proceeds
                    direction = -1
                    qty = entry_qty
                    avg_entry_price = effective_price
                    entry_time = idx[i]
                    num_units = 1
                    last_add_price = close
                    extreme_since_entry = close
                    initial_stop = fill_price + params.short_init_stop_atr_mult * cur_atr
                    trail_stop = fill_price + params.short_trail_stop_atr_mult * cur_atr
                    short_had_entry = True

        equity_curve.iloc[i] = cash + direction * qty * close

    if direction == 1:
        final_price = closes[-1]
        proceeds = qty * final_price * (1 - params.fee_rate)
        cost_basis = qty * avg_entry_price
        trades.append(
            Trade(
                direction="long",
                entry_time=entry_time,
                exit_time=idx[-1],
                qty=qty,
                avg_entry_price=avg_entry_price,
                exit_price=final_price,
                pnl=proceeds - cost_basis,
                pnl_pct=(proceeds - cost_basis) / cost_basis if cost_basis else 0.0,
                exit_reason="end_of_data",
                num_units=num_units,
            )
        )
    elif direction == -1:
        final_price = closes[-1]
        cost = qty * final_price * (1 + params.fee_rate)
        proceeds_basis = qty * avg_entry_price
        trades.append(
            Trade(
                direction="short",
                entry_time=entry_time,
                exit_time=idx[-1],
                qty=qty,
                avg_entry_price=avg_entry_price,
                exit_price=final_price,
                pnl=proceeds_basis - cost,
                pnl_pct=(proceeds_basis - cost) / proceeds_basis if proceeds_basis else 0.0,
                exit_reason="end_of_data",
                num_units=num_units,
            )
        )

    return BacktestResult(params=params, equity_curve=equity_curve, trades=trades)
