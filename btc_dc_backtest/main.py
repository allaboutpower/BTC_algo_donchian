"""CLI 入口：讀取 CSV、跑單次回測或參數掃描。

範例：

    # 單次回測（用預設參數）
    python -m btc_dc_backtest.main --csv btc_daily.csv --mode single

    # 掃描不同時間級別 / DC 週期 / 停損倍數
    python -m btc_dc_backtest.main --csv btc_daily.csv --mode sweep \
        --timeframes 1D 2D 3D --dc-periods 20 55 100 \
        --init-stop-mults 1.5 2 2.5 --trail-stop-mults 2.5 3 3.5 \
        --out sweep_results.csv
"""
from __future__ import annotations

import argparse

from .config import StrategyParams
from .data import load_csv, resample_ohlcv
from .engine import run_backtest, _infer_bars_per_year
from .metrics import compute_metrics
from .plotting import plot_cumulative_pnl
from .rsi_strategy import run_rsi_backtest
from .sweep import run_sweep


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="K-BTC-DC 唐奇安突破策略回測 pipeline")
    p.add_argument("--csv", required=True, help="OHLCV CSV 檔案路徑")
    p.add_argument("--mode", choices=["single", "sweep", "rsi"], default="single")

    # rsi 模式專用：純 RSI 震盪反手策略
    p.add_argument("--rsi-period", type=int, default=14)
    p.add_argument("--rsi-oversold", type=float, default=30.0)
    p.add_argument("--rsi-overbought", type=float, default=70.0)

    # single 模式參數（同時也是 sweep 模式未指定維度時的預設值）
    p.add_argument("--timeframe", default="4h")
    p.add_argument("--dc-period", type=int, default=20)
    p.add_argument("--atr-period", type=int, default=20)
    p.add_argument("--init-stop-mult", type=float, default=1.5)
    p.add_argument("--trail-stop-mult", type=float, default=3.5)
    p.add_argument("--pyramid-atr-mult", type=float, default=0.5)
    p.add_argument("--max-pyramids", type=int, default=3)
    p.add_argument("--risk-pct", type=float, default=0.01)
    p.add_argument("--vol-target", type=float, default=0.60)
    p.add_argument("--no-vol-target", action="store_true")
    p.add_argument("--no-reentry", action="store_true", help="停用重進場（預設允許重進場）")

    # 空單（做空）：純唐奇安通道突破，無其他濾網。預設開啟（多空都做），
    # 加 --no-short 可關閉只做多方
    p.add_argument("--no-short", action="store_true", help="關閉做空，只做多方")
    p.add_argument("--short-init-stop-mult", type=float, default=1.5)
    p.add_argument("--short-trail-stop-mult", type=float, default=2.5)
    p.add_argument("--short-risk-pct", type=float, default=0.021)

    p.add_argument("--initial-equity", type=float, default=100_000.0)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--slippage-bps", type=float, default=2.0)

    # sweep 模式專用：各維度要掃描的候選值列表
    p.add_argument("--timeframes", nargs="+", default=None, help="例如 1D 2D 3D 或 4H 1D")
    p.add_argument("--dc-periods", type=int, nargs="+", default=None, help="例如 20 55 100")
    p.add_argument("--init-stop-mults", type=float, nargs="+", default=None, help="例如 1.5 2 2.5")
    p.add_argument("--trail-stop-mults", type=float, nargs="+", default=None, help="例如 2.5 3 3.5")

    p.add_argument("--out", default=None, help="sweep 結果輸出 CSV 路徑")
    p.add_argument("--top", type=int, default=20, help="sweep 模式印出前 N 名（依 Sharpe 排序）")
    p.add_argument("--plot", default=None, help="single 模式：輸出累積 PnL 圖的 PNG 路徑")
    return p


def _params_from_args(args: argparse.Namespace) -> StrategyParams:
    return StrategyParams(
        timeframe=args.timeframe,
        dc_period=args.dc_period,
        atr_period=args.atr_period,
        pyramid_atr_mult=args.pyramid_atr_mult,
        max_pyramids=args.max_pyramids,
        init_stop_atr_mult=args.init_stop_mult,
        trail_stop_atr_mult=args.trail_stop_mult,
        risk_pct=args.risk_pct,
        vol_target_enabled=not args.no_vol_target,
        vol_target_annual=args.vol_target,
        allow_reentry=not args.no_reentry,
        short_enabled=not args.no_short,
        short_init_stop_atr_mult=args.short_init_stop_mult,
        short_trail_stop_atr_mult=args.short_trail_stop_mult,
        short_risk_pct=args.short_risk_pct,
        initial_equity=args.initial_equity,
        fee_rate=args.fee_rate,
        slippage_bps=args.slippage_bps,
    )


def main(argv: list[str] | None = None) -> None:
    args = _build_arg_parser().parse_args(argv)
    raw_df = load_csv(args.csv)
    print(f"讀取 {args.csv}: {len(raw_df)} 根原始 K 棒, "
          f"{raw_df.index[0]} ~ {raw_df.index[-1]}")

    base_params = _params_from_args(args)

    if args.mode == "single":
        df_tf = resample_ohlcv(raw_df, base_params.timeframe)
        print(f"resample 至 {base_params.timeframe}: {len(df_tf)} 根 K 棒")
        result = run_backtest(df_tf, base_params)
        bars_per_year = _infer_bars_per_year(base_params.timeframe)
        m = compute_metrics(result, bars_per_year)
        print(f"\n=== 回測結果 ({base_params.label()}) ===")
        for k, v in m.items():
            print(f"{k:>20}: {v:,.4f}" if isinstance(v, float) else f"{k:>20}: {v}")
        if args.out:
            result.trades_df.to_csv(args.out, index=False)
            print(f"\n交易明細已輸出至 {args.out}")
        if args.plot:
            plot_cumulative_pnl(
                {base_params.label(): result.equity_curve},
                args.plot,
                initial_equity=base_params.initial_equity,
                title=f"Cumulative PnL ({base_params.label()})",
            )
            print(f"累積 PnL 圖已輸出至 {args.plot}")
    elif args.mode == "rsi":
        df_tf = resample_ohlcv(raw_df, args.timeframe)
        print(f"resample 至 {args.timeframe}: {len(df_tf)} 根 K 棒")
        result = run_rsi_backtest(
            df_tf,
            rsi_period=args.rsi_period,
            oversold=args.rsi_oversold,
            overbought=args.rsi_overbought,
            initial_equity=args.initial_equity,
            fee_rate=args.fee_rate,
            slippage_bps=args.slippage_bps,
            timeframe=args.timeframe,
        )
        bars_per_year = _infer_bars_per_year(args.timeframe)
        m = compute_metrics(result, bars_per_year)
        label = f"rsi tf={args.timeframe}_period={args.rsi_period}_{args.rsi_oversold:.0f}-{args.rsi_overbought:.0f}"
        print(f"\n=== 回測結果 ({label}) ===")
        for k, v in m.items():
            print(f"{k:>20}: {v:,.4f}" if isinstance(v, float) else f"{k:>20}: {v}")
        if args.out:
            result.trades_df.to_csv(args.out, index=False)
            print(f"\n交易明細已輸出至 {args.out}")
        if args.plot:
            plot_cumulative_pnl(
                {label: result.equity_curve},
                args.plot,
                initial_equity=args.initial_equity,
                title=f"Cumulative PnL ({label})",
            )
            print(f"累積 PnL 圖已輸出至 {args.plot}")
    else:
        results = run_sweep(
            raw_df,
            base_params,
            timeframes=args.timeframes,
            dc_periods=args.dc_periods,
            init_stop_atr_mults=args.init_stop_mults,
            trail_stop_atr_mults=args.trail_stop_mults,
        )
        with __import__("pandas").option_context("display.max_columns", None, "display.width", 200):
            print(results.head(args.top))
        if args.out:
            results.to_csv(args.out, index=False)
            print(f"\n完整掃描結果已輸出至 {args.out}")


if __name__ == "__main__":
    main()
