"""純 RSI 震盪策略：永遠在場（多空互斥），在超賣/超買兩條 RSI 帶之間反手。

規則：
- RSI 跌破 oversold（預設 30）→ 進場/翻多，持有直到 RSI 站上 overbought
- RSI 站上 overbought（預設 70）→ 進場/翻空，持有直到 RSI 跌破 oversold
- 30~70 之間維持原方向不動作（純粹在兩條帶之間「上下刷」反手，無 ATR 停損/加碼）

每次翻手都用當下全部權益重新開倉（無槓桿、無停損，故意保持極簡）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import StrategyParams
from .engine import BacktestResult, Trade
from .indicators import rsi


def run_rsi_backtest(
    df: pd.DataFrame,
    rsi_period: int = 14,
    oversold: float = 30.0,
    overbought: float = 70.0,
    initial_equity: float = 100_000.0,
    fee_rate: float = 0.0004,
    slippage_bps: float = 2.0,
    timeframe: str = "1D",
) -> BacktestResult:
    params = StrategyParams(
        timeframe=timeframe,
        initial_equity=initial_equity,
        fee_rate=fee_rate,
        slippage_bps=slippage_bps,
    )

    if len(df) < rsi_period + 2:
        return BacktestResult(params=params, equity_curve=pd.Series(dtype=float), trades=[])

    rsi_series = rsi(df["close"], rsi_period)
    slip = slippage_bps / 10_000.0

    cash = initial_equity
    direction = 0  # 0=flat, 1=long, -1=short
    qty = 0.0
    avg_entry_price = 0.0
    entry_time = None

    closes = df["close"].values
    idx = df.index
    equity_curve = pd.Series(index=idx, dtype=float)
    trades: list[Trade] = []

    for i in range(len(df)):
        close = closes[i]
        r = rsi_series.iloc[i]

        target = direction
        if not np.isnan(r):
            if r <= oversold:
                target = 1
            elif r >= overbought:
                target = -1

        if target != direction:
            # 平掉現有部位
            if direction == 1:
                fill_price = close * (1 - slip)
                proceeds = qty * fill_price * (1 - fee_rate)
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
                        exit_reason="rsi_flip",
                        num_units=1,
                    )
                )
                cash += proceeds
            elif direction == -1:
                fill_price = close * (1 + slip)
                cost = qty * fill_price * (1 + fee_rate)
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
                        exit_reason="rsi_flip",
                        num_units=1,
                    )
                )
                cash -= cost

            # 開新部位（全部權益）
            if target == 1:
                fill_price = close * (1 + slip)
                effective_price = fill_price * (1 + fee_rate)
                qty = cash / effective_price
                cash -= qty * effective_price
                avg_entry_price = effective_price
            elif target == -1:
                fill_price = close * (1 - slip)
                effective_price = fill_price * (1 - fee_rate)
                qty = cash / effective_price
                cash += qty * effective_price
                avg_entry_price = effective_price
            else:
                qty = 0.0
                avg_entry_price = 0.0

            direction = target
            entry_time = idx[i]

        equity_curve.iloc[i] = cash + direction * qty * close

    return BacktestResult(params=params, equity_curve=equity_curve, trades=trades)
