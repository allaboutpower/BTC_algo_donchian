# BTC Donchian Channel Backtest (K-BTC-DC)

BTC 唐奇安通道（Donchian Channel）突破策略的事件驅動回測框架，支援多空對稱交易、ATR 金字塔加碼、Chandelier 追蹤停損、波動率目標化部位控管，以及參數掃描。

## 策略概要

預設為 **4H 唐奇安通道突破，多空對稱，無其他濾網**。

| 項目 | 多方 | 空方 |
|---|---|---|
| 進場 | 收盤價 > 過去 20 根 K 棒最高價 | 收盤價 < 過去 20 根 K 棒最低價 |
| 初始停損 | 進場價 − 1.5 × ATR | 進場價 + 1.5 × ATR |
| 追蹤停損 | 期間最高收盤價 − 3.5 × ATR（只上移） | 期間最低收盤價 + 2.5 × ATR（只下移） |
| 加碼 | 每有利 0.5 × ATR 加碼一次，最多 3 次（共 4 單位） | 同左 |
| 單位風險 | 權益 × 1% | 權益 × 2.1% |

- **多空互斥**：同一時間只持有一個方向的部位。
- **部位大小**：`(權益 × risk_pct × scale) / (init_stop_atr_mult × ATR)`
- **波動率目標化**：`scale = min(1, 目標年化波動 60% / 實現波動)`，高波動時自動縮小部位。
- **重進場**：被停損洗出後，價格再次突破可重新進場。
- **無前視偏誤**：通道上下軌使用「不含當前 K 棒」的過去 N 根高低點（`shift(1).rolling(N)`）。
- **成交假設**：訊號與成交皆在 K 棒收盤價；停損若被當根高/低點觸及則以停損價成交，跳空穿越則以開盤價成交。
- **成本**：單邊手續費 0.04%（幣安 taker）＋ 單邊滑價 2 bps。

另附一個對照用的 **純 RSI 震盪反手策略**（`--mode rsi`）：RSI ≤ 30 翻多、RSI ≥ 70 翻空，永遠在場、無停損。

## 專案結構

```
.
├── requirements.txt
└── btc_dc_backtest/
    ├── config.py        # StrategyParams：所有策略與回測參數
    ├── data.py          # CSV 讀取（自動辨識欄名）與 resample
    ├── indicators.py    # 唐奇安通道、ATR、RMA、實現波動、RSI
    ├── engine.py        # 回測引擎（進出場、加碼、停損）
    ├── rsi_strategy.py  # 純 RSI 反手對照策略
    ├── metrics.py       # 績效指標
    ├── sweep.py         # 參數網格掃描
    ├── plotting.py      # 累積 PnL 圖
    ├── main.py          # CLI 入口
    └── price data/      # BTC OHLCV 資料（2018–2025，15m / 1h / 4h / 1d）
```

## 安裝

需要 Python 3.10 以上。

```bash
pip install -r requirements.txt
```

## 使用方式

在專案根目錄執行。

### 單次回測（預設參數）

```bash
python -m btc_dc_backtest.main --csv "btc_dc_backtest/price data/btc_1h_data_2018_to_2025.csv" --mode single --plot pnl.png --out trades.csv
```

`--out` 輸出交易明細 CSV，`--plot` 輸出累積 PnL 圖。

### 只做多

```bash
python -m btc_dc_backtest.main --csv "btc_dc_backtest/price data/btc_1h_data_2018_to_2025.csv" --mode single --no-short
```

### 參數掃描

```bash
python -m btc_dc_backtest.main --csv "btc_dc_backtest/price data/btc_1h_data_2018_to_2025.csv" --mode sweep --timeframes 4h 1D --dc-periods 20 55 100 --init-stop-mults 1.5 2 2.5 --trail-stop-mults 2.5 3 3.5 --out sweep_results.csv
```

結果依 Sharpe 由高到低排序，`--top N` 控制印出筆數。

### RSI 對照策略

```bash
python -m btc_dc_backtest.main --csv "btc_dc_backtest/price data/btc_1h_data_2018_to_2025.csv" --mode rsi --timeframe 4h --rsi-period 14 --rsi-oversold 30 --rsi-overbought 70
```

## 主要 CLI 參數

| 參數 | 預設 | 說明 |
|---|---|---|
| `--timeframe` | `4h` | resample 週期（pandas offset alias，如 `1h`、`4h`、`1D`） |
| `--dc-period` | `20` | 唐奇安通道週期 |
| `--atr-period` | `20` | ATR 週期（Wilder 平滑） |
| `--init-stop-mult` | `1.5` | 多單初始停損 ATR 倍數 |
| `--trail-stop-mult` | `3.5` | 多單追蹤停損 ATR 倍數 |
| `--pyramid-atr-mult` | `0.5` | 加碼間距 ATR 倍數 |
| `--max-pyramids` | `3` | 最多加碼次數 |
| `--risk-pct` | `0.01` | 多單每單位風險比例 |
| `--vol-target` | `0.60` | 年化波動目標；`--no-vol-target` 關閉 |
| `--no-reentry` | – | 停用重進場 |
| `--no-short` | – | 關閉做空 |
| `--short-init-stop-mult` | `1.5` | 空單初始停損 ATR 倍數 |
| `--short-trail-stop-mult` | `2.5` | 空單追蹤停損 ATR 倍數 |
| `--short-risk-pct` | `0.021` | 空單每單位風險比例 |
| `--initial-equity` | `100000` | 初始資金 |
| `--fee-rate` | `0.0004` | 單邊手續費率 |
| `--slippage-bps` | `2.0` | 單邊滑價（bps） |

完整參數請執行 `python -m btc_dc_backtest.main --help`。

## 績效指標

`final_equity`、`total_return_pct`、`cagr_pct`、`ann_vol_pct`、`sharpe`、`max_drawdown_pct`、`num_trades`、`win_rate_pct`、`profit_factor`、`avg_trade_pnl`、`expectancy`。

## 資料格式

CSV 需包含時間欄與 OHLC 欄位，欄名不分大小寫，支援常見別名：

- 時間：`Open time` / `timestamp` / `date` / `datetime` / `time`
- 價格：`Open`/`o`、`High`/`h`、`Low`/`l`、`Close`/`c`/`Adj Close`
- 成交量：`Volume`/`vol`/`v`（可省略）

內附資料為幣安 BTC 現貨 K 線格式。由於 resample 只能由細往粗轉換，建議使用 1h 或 15m 資料作為輸入。

## 免責聲明

本專案僅供研究與教育用途，回測結果不代表未來績效，亦不構成任何投資建議。
