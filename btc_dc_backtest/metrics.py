"""績效指標計算。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .engine import BacktestResult


def max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    running_max = equity.cummax()
    dd = equity / running_max - 1.0
    return dd.min()


def compute_metrics(result: BacktestResult, bars_per_year: float) -> dict:
    equity = result.equity_curve.dropna()
    trades = result.trades_df

    if equity.empty or len(equity) < 2:
        return {
            "final_equity": result.params.initial_equity,
            "total_return_pct": 0.0,
            "cagr_pct": 0.0,
            "ann_vol_pct": 0.0,
            "sharpe": 0.0,
            "max_drawdown_pct": 0.0,
            "num_trades": 0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "avg_trade_pnl": 0.0,
            "expectancy": 0.0,
        }

    initial_equity = result.params.initial_equity
    final_equity = equity.iloc[-1]
    total_return = final_equity / initial_equity - 1.0

    n_bars = len(equity)
    years = n_bars / bars_per_year
    cagr = (final_equity / initial_equity) ** (1 / years) - 1 if years > 0 and final_equity > 0 else 0.0

    rets = equity.pct_change().dropna()
    ann_vol = rets.std() * np.sqrt(bars_per_year) if len(rets) > 1 else 0.0
    sharpe = (rets.mean() * bars_per_year) / ann_vol if ann_vol > 0 else 0.0

    mdd = max_drawdown(equity)

    num_trades = len(trades)
    if num_trades > 0:
        wins = trades[trades["pnl"] > 0]
        losses = trades[trades["pnl"] <= 0]
        win_rate = len(wins) / num_trades
        gross_profit = wins["pnl"].sum()
        gross_loss = -losses["pnl"].sum()
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf
        avg_trade_pnl = trades["pnl"].mean()
        expectancy = avg_trade_pnl
    else:
        win_rate = 0.0
        profit_factor = 0.0
        avg_trade_pnl = 0.0
        expectancy = 0.0

    return {
        "final_equity": final_equity,
        "total_return_pct": total_return * 100,
        "cagr_pct": cagr * 100,
        "ann_vol_pct": ann_vol * 100,
        "sharpe": sharpe,
        "max_drawdown_pct": mdd * 100,
        "num_trades": num_trades,
        "win_rate_pct": win_rate * 100,
        "profit_factor": profit_factor,
        "avg_trade_pnl": avg_trade_pnl,
        "expectancy": expectancy,
    }
