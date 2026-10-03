"""累積 PnL / 權益曲線繪圖。"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def plot_cumulative_pnl(
    curves: dict[str, pd.Series],
    out_path: str,
    initial_equity: float = 100_000.0,
    title: str = "Cumulative PnL",
) -> None:
    """將多條 equity curve 轉成累積 PnL（equity - initial_equity）疊圖比較。

    curves: {label: equity_curve(Series, index=時間, values=權益)}

    註：圖上文字一律使用英文，避免預設字型缺少 CJK 字元導致中文顯示成方框。
    """
    fig, ax = plt.subplots(figsize=(12, 6))
    for label, equity in curves.items():
        equity = equity.dropna()
        if equity.empty:
            continue
        cum_pnl = equity - initial_equity
        ax.plot(cum_pnl.index, cum_pnl.values, label=label, linewidth=1.3)

    ax.axhline(0, color="gray", linewidth=0.8, linestyle="--")
    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel("Cumulative PnL (USD)")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
