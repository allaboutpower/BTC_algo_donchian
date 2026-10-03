"""策略與回測參數定義。

策略：4H 唐奇安通道突破，多空對稱，無其他濾網。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StrategyParams:
    """K-BTC-DC 策略參數（對應 K-BTC-DC.md 第2節指標與參數）。"""

    # 時間級別：原始資料要 resample 成的 K 棒週期，pandas offset alias，
    # 例如 "1D"（日線）、"4h"、"1h" 等。實測最佳為 "4h"。
    timeframe: str = "4h"

    # 唐奇安通道週期（過去 N 根 K 棒最高價）。實測最佳為 20。
    dc_period: int = 20

    # ATR 週期
    atr_period: int = 20

    # 加碼間距：每有利 pyramid_atr_mult × ATR 加碼一次
    pyramid_atr_mult: float = 0.5
    max_pyramids: int = 3  # 最多加碼 3 次（總計最多 4 單位）

    # 初始停損倍數：進場價 - init_stop_atr_mult × ATR
    init_stop_atr_mult: float = 1.5

    # 追蹤停損倍數（Chandelier Exit）：期間最高收盤價 - trail_stop_atr_mult × ATR
    trail_stop_atr_mult: float = 3.5

    # 單筆風險 %（每一單位的風險），部位大小 = (權益 × risk_pct) / (init_stop_atr_mult × ATR)
    risk_pct: float = 0.01

    # 波動率目標化
    vol_target_enabled: bool = True
    vol_target_annual: float = 0.60  # 年化實現波動目標，例如 60%
    vol_lookback: int = 20  # 用於估計實現波動的天數/根數

    # 是否允許重進場（被停損洗出後，價格再次突破可重新進場）
    allow_reentry: bool = True

    # 初始資金與手續費/滑價設定
    initial_equity: float = 100_000.0
    fee_rate: float = 0.0004  # 單邊手續費率（例如幣安 taker 0.04%）
    slippage_bps: float = 2.0  # 單邊滑價（basis points）

    # 空單（做空）：純唐奇安通道突破，無其他濾網。收盤價跌破過去 dc_period
    # 根K棒（與做多同一條通道、同一交易週期）的最低價即觸發放空。多空互斥，
    # 同一時間只能持有一個方向。
    short_enabled: bool = True
    short_init_stop_atr_mult: float = 1.5  # 初始停損：進場價 + 1.5×ATR
    short_trail_stop_atr_mult: float = 2.5  # 追蹤停損（鏡射 Chandelier）：期間最低收盤價 + trail×ATR，只下移
    short_pyramid_atr_mult: float = 0.5
    short_max_pyramids: int = 3
    short_risk_pct: float = 0.021
    short_allow_reentry: bool = True

    def label(self) -> str:
        return (
            f"tf={self.timeframe}_dc={self.dc_period}_atr={self.atr_period}_"
            f"init={self.init_stop_atr_mult}_trail={self.trail_stop_atr_mult}_"
            f"short={self.short_enabled}"
        )
