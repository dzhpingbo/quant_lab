# Codex User Switch Handoff - quant_lab - 2026-04-18

This file is a local recovery/handoff note for continuing the same quant_lab work
with another Codex user/account. It intentionally does not rely on chat history.

## Workspace

- Project root: `E:\dzhwork\quant\quant_lab`
- Shell: PowerShell on Windows
- Current local date in the session: 2026-04-18, Asia/Shanghai
- Relevant Codex skill used: `588200-pool`
- Git status note: this workspace is not a git repository, so use filesystem files/checkpoints as the source of truth.

## High-Level User Goals In This Thread

1. Update US equity/ETF data to the latest available daily bars.
2. Use all reusable local strategy/factor resources, including downloaded external factor/strategy libraries and quant_lab libraries.
3. Build reusable factor/strategy adapters instead of leaving downloaded repos unused.
4. Research and backtest QQQ/QLD/TQQQ strategies using vectorbt.
5. Improve weak QLD/TQQQ strategies by deeper momentum-factor combinations.
6. Add TD9/神奇九转 signals and combine them with other factors/signals.
7. Backtest on US Magnificent 7 stocks plus available US funds/ETFs/indices, rank the best 5 instruments/strategies, and separately report QLD/TQQQ best strategies.
8. Checkpoint long tasks locally after each stage so another Codex run can resume without chat context.

## Important Local Data

- Main US daily CSV directory:
  - `E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404`
- After recent runs, core US symbols and context ETFs/VIX were updated to latest complete local bar `2026-04-17`.
- Example updated core symbols:
  - `TQQQ`, `QLD`, `QQQ`, `_VIX`, `SPY`, `TLT`, `SHY`, `XLK`, `SOXX`, `SQQQ`, `PSQ`
- Some of the full local stock universe files are older (`2026-04-04`) unless explicitly updated by a later script.

## External Factor/Strategy Library Reuse Work Completed

The user previously complained that only a small subset of downloaded factor/strategy repos had been made reusable. A pass was completed to expand the local reuse layer.

Key files created/updated:

- `src/factors/external_adapters.py`
- `src/factors/external_resource_catalog.py`
- `src/factors/__init__.py`
- `src/strategies/external_strategy_catalog.py`
- `src/strategies/__init__.py`
- `docs/external_factor_adapters.md`
- `docs/external_resource_reuse.md`

Key checkpoint/snapshot files:

- `outputs/factor_library_imports/full_reuse_checkpoint_20260416.md`
- `outputs/factor_library_imports/full_reuse_catalog_snapshot_20260416.json`
- `outputs/factor_library_imports/full_reuse_catalog_snapshot_20260416.md`
- `outputs/factor_library_imports/worldquant_source_alpha101_runtime_status_20260416.csv`
- `outputs/factor_library_imports/worldquant_source_alpha101_runtime_status_20260416.md`

Reusable surface reported in that pass:

- 452 direct external panel factor names.
- 82 executable WorldQuant Alpha101 names from the downloaded public source.
- 360 executable Qlib Alpha360 names.
- 10 local executable GTJA Alpha191 names.
- 101 JoinQuant Alpha101 API entries discoverable through archived SDK.
- 191 JoinQuant Alpha191 API entries discoverable through archived SDK.
- 18 reusable external resource records.
- 9 external strategy/model template records.

Verification reported:

- `python -m compileall src\factors src\strategies src\backtest\vbt_engine.py`: passed.
- VectorBT engine `_compute_factor_panel` smoke test with `wq_alpha018`, `qlib360_CLOSE59`, `gtja_alpha004`: passed.
- WorldQuant source-backed runtime probe: 82 ok, 0 failed.

## US Leveraged ETF Full Strategy Work

Script:

- `scripts/research_us_leveraged_etf_full_strategy.py`

Output:

- `outputs/us_leveraged_etf_full_strategy/full_us_20260416_010500/`

Key result at that stage:

- Latest complete data then: `2026-04-15`.
- Coverage: 452 external panel factors, WQ 82, Qlib Alpha360 360, GTJA 10, local 38, Fama-French 84, ML 24.
- TQQQ best: `qqq_underlying_dual_thrust_w40_k0.3`
  - Signal: `HOLD_OR_BUY`
  - Test annual: 51.33%, maxDD: -31.04%
  - Full annual: 12.71%, maxDD: -58.25%
- QLD best: `alpha_ret_skew_60_cs_high_top0.35`
  - Signal: `SELL_NEXT_OPEN`
  - Test annual: 37.95%, maxDD: -19.32%
  - Full annual: 9.57%, maxDD: -63.13%

The user rejected these as too weak because full-period return was low and drawdown was high.

## Walk-Forward Stability Work

Script:

- `scripts/walk_forward_us_leveraged_etf_stability.py`

Output:

- `outputs/us_leveraged_etf_walk_forward/wf_us_20260417_5y/`

Key findings:

- TQQQ QQQ DualThrust fixed current best:
  - 10 folds, positive years 40%
  - stitched annual 19.37%, total 415.25%, Sharpe 0.6873, maxDD -37.81%
- QLD ReturnSkew CS fixed current best:
  - 11 folds, positive years 81.82%
  - stitched annual 17.74%, total 433.85%, Sharpe 1.032, maxDD -19.32%
- Selected per fold variants had worse drawdown for QLD.

## Online-Inspired VectorBT Strategy Work

Script:

- `scripts/vbt_us_leverage_online.py`

Final output:

- `outputs/us_leveraged_etf_vectorbt_online_strategies/vbt_online_20260418_001937/`

Notes:

- vectorbt import initially hung because numba cache was trying system temp. Fix: set local env vars:
  - `$env:NUMBA_CACHE_DIR='e:\dzhwork\quant\quant_lab\.numba_cache'`
  - `$env:TMP='e:\dzhwork\quant\quant_lab\.tmp'`
  - `$env:TEMP='e:\dzhwork\quant\quant_lab\.tmp'`
- Pandas `to_markdown()` failed because local `tabulate` is old; script was patched to use a custom markdown table writer.
- Data in final run updated to `2026-04-17`.

Final online-inspired vectorbt result:

- TQQQ strategy: `qqq_sma150_band0.005`
  - Rule: buy/hold TQQQ when QQQ close > QQQ SMA150 * 1.005; sell when QQQ close < QQQ SMA150 * 0.995.
  - Test annual: 37.01%, maxDD: -41.94%, Sharpe: 0.872.
  - Full annual: 36.23%, maxDD: -47.54%, Sharpe: 0.865.
  - Next open action for 2026-04-20: `HOLD_OR_KEEP_LONG`.
- QLD strategy: `qqq_sma180_band0.005`
  - Rule: buy/hold QLD when QQQ close > QQQ SMA180 * 1.005; sell when QQQ close < QQQ SMA180 * 0.995.
  - Test annual: 30.38%, maxDD: -29.72%, Sharpe: 1.000.
  - Full annual: 21.94%, maxDD: -42.19%, Sharpe: 0.793.
  - Next open action for 2026-04-20: `HOLD_OR_KEEP_LONG`.

Important files:

- `outputs/us_leveraged_etf_vectorbt_online_strategies/vbt_online_20260418_001937/report.md`
- `outputs/us_leveraged_etf_vectorbt_online_strategies/vbt_online_20260418_001937/best_strategy_summary.csv`
- `outputs/us_leveraged_etf_vectorbt_online_strategies/vbt_online_20260418_001937/TQQQ_operation_points.csv`
- `outputs/us_leveraged_etf_vectorbt_online_strategies/vbt_online_20260418_001937/QLD_operation_points.csv`

## Momentum-Factor Combo Work

The user again rejected the prior strategies as not good enough and specifically asked for deeper momentum-factor combinations, including MA cross examples like 5-day MA crossing 60-day MA.

Script:

- `scripts/vbt_us_leverage_momentum_combo.py`

Final output:

- `outputs/us_leveraged_etf_momentum_combo/momentum_combo_20260418_084322/`

Candidate families included:

- SMA/EMA crossovers including `5/60`, `3/40`, `3/120`, `3/180`, etc.
- Triple MA alignment.
- MACD + trend confirmation.
- ADX/+DI trend strength.
- ROC20/60/120 weighted momentum.
- QQQ vs SHY/TLT relative momentum.
- VIX and realized-volatility filters.
- Multi-factor momentum score.
- Cooldown and trailing-stop variants.

Score-first result:

- TQQQ: `qqq_ema3_40_band0.0050`
  - Test annual 34.09%, maxDD -41.90%.
  - Full annual 28.22%, maxDD -52.27%.
  - Action for 2026-04-20: `HOLD_OR_KEEP_LONG`.
- QLD: `asset_sma3_200_band0.0050`
  - Test annual 28.03%, maxDD -29.72%.
  - Full annual 20.41%, maxDD -42.58%.
  - Action for 2026-04-20: `HOLD_OR_KEEP_LONG`.

Because TQQQ score-first full drawdown remained high, a stricter drawdown recommendation was separately exported:

- `outputs/us_leveraged_etf_momentum_combo/momentum_combo_20260418_084322/recommended_strategy_summary.csv`

Recommended robust strategies:

- TQQQ: `qqq_score_e11_x9_cool3`
  - Rule: QQQ 19-feature momentum score; enter >= 11, exit <= 9, 3-day cooldown after exit.
  - Test annual 24.30%, maxDD -43.33%.
  - Full annual 28.42%, maxDD -43.33%, Sharpe 0.754.
  - Next open action: `HOLD_OR_KEEP_LONG`.
- QLD: `qqq_ema3_120_band0.0025`
  - Rule: QQQ EMA3 crosses EMA120 with 0.25% hysteresis.
  - Test annual 27.25%, maxDD -29.72%.
  - Full annual 22.07%, maxDD -41.93%, Sharpe 0.799.
  - Next open action: `HOLD_OR_KEEP_LONG`.

Important files:

- `outputs/us_leveraged_etf_momentum_combo/momentum_combo_20260418_084322/report.md`
- `outputs/us_leveraged_etf_momentum_combo/momentum_combo_20260418_084322/recommended_strategy_summary.csv`
- `outputs/us_leveraged_etf_momentum_combo/momentum_combo_20260418_084322/TQQQ_recommended_operation_points.csv`
- `outputs/us_leveraged_etf_momentum_combo/momentum_combo_20260418_084322/QLD_recommended_operation_points.csv`

## Current In-Progress Task: TD9 + All Assets

Latest user request before this handoff:

1. Based on all available strategy/factor libraries, add 神奇九转/TD9 signals.
2. Combine TD9 with other signals/factors to seek optimal effect.
3. Use vectorbt to backtest on:
   - US Magnificent 7 stocks.
   - All available US funds, ETFs, and indices.
4. Report the top 5 instruments/strategies by effect.
5. Separately report QLD and TQQQ best strategies and explain them in detail.

Work started:

- New script added: `scripts/vbt_us_td9_all_assets.py`
- Current status: compiles successfully via `python -m py_compile scripts\vbt_us_td9_all_assets.py`.
- Important: script is not finished yet. It currently has:
  - workspace constants and universe definitions,
  - MAG7 list,
  - curated ETF/fund/index symbol list,
  - local data reading/writing,
  - yfinance batch update,
  - checkpoint writer,
  - TD9 count functions,
  - factor-score functions,
  - TD9 pullback/exit/reentry overlay signal functions,
  - candidate generation combining:
    - buy-and-hold,
    - QQQ EMA crosses,
    - asset SMA crosses,
    - MACD/MA200/VIX,
    - ROC stack/vol filter,
    - relative momentum,
    - factor-score + TD9,
    - TD9 pullback trend,
    - TD9 exit overlay,
    - TD9 reentry overlay,
    - cross-market VIX/SPY/QQQ risk-on filters with TD9 exit.
- Missing and should be implemented next:
  - evaluation scoring function,
  - per-symbol vectorbt evaluation loop,
  - operation/trade CSV export,
  - top-5 overall ranking,
  - MAG7/fund ETF index separated summaries,
  - QLD/TQQQ specific output,
  - final report/checkpoint/main function.

Suggested next implementation approach:

- Reuse helper functions from:
  - `scripts/vbt_us_leverage_online.py`
  - `scripts/vbt_us_leverage_momentum_combo.py`
- Use `base.run_vbt`, `base.metrics_from`, `base.operations`, `base.next_action`, and `base.md_table`.
- Keep the universe manageable and honest:
  - MAG7: `AAPL`, `MSFT`, `NVDA`, `AMZN`, `META`, `GOOGL`, `TSLA`.
  - Funds/ETF/index: symbols in `ETF_FUND_INDEX_CANDIDATES` that have local CSVs.
  - Treat this as “all available locally recognized ETF/fund/index candidates,” not every stock in the huge local stock directory.
- Output under `outputs/us_td9_all_assets/td9_all_assets_<timestamp>/`.
- Include checkpoint files:
  - `checkpoint_00_universe`
  - `checkpoint_01_data_update`
  - `checkpoint_02_candidates`
  - `checkpoint_03_evaluation`
  - `checkpoint_04_final_report`
- Important scoring preference:
  - Do not pick only highest CAGR if max drawdown is huge.
  - Penalize full max drawdown, test max drawdown, very low exposure, too few trades, and very low full-period annual return.
  - Include buy-and-hold benchmark for every winning instrument.

## Environment Commands

Use these env vars before any vectorbt scripts:

```powershell
$env:NUMBA_CACHE_DIR='e:\dzhwork\quant\quant_lab\.numba_cache'
$env:TMP='e:\dzhwork\quant\quant_lab\.tmp'
$env:TEMP='e:\dzhwork\quant\quant_lab\.tmp'
```

Existing scripts can be rerun like:

```powershell
python scripts\vbt_us_leverage_online.py --today 2026-04-21 --next-open-date 2026-04-20
python scripts\vbt_us_leverage_momentum_combo.py --today 2026-04-21 --next-open-date 2026-04-20
```

The in-progress TD9 all-assets script should be completed first, then run with something like:

```powershell
python scripts\vbt_us_td9_all_assets.py --today 2026-04-21 --next-open-date 2026-04-20
```

## Complete Prompt For New Codex User

Paste the following to the new Codex user/account:

```text
你正在接手 Windows/PowerShell 工作区 `E:\dzhwork\quant\quant_lab` 的量化研究任务。请先读取本地交接文档：

`docs/codex_user_switch_handoff_20260418.md`

重要要求：
1. 不要依赖旧聊天上下文，以本地文件/checkpoint 为准。
2. 继续完成当前进行中的任务：在所有可用策略和因子库基础上，加入 TD9/神奇九转信号，把 TD9 与动量、均线交叉、MACD/ADX、ROC、多因子分数、VIX/波动过滤、相对动量等信号组合。
3. 使用 vectorbt 回测：
   - 美股七巨头：AAPL、MSFT、NVDA、AMZN、META、GOOGL、TSLA；
   - 本地可用且已识别的美股基金/ETF/指数；
   - 单独给出 QLD 和 TQQQ。
4. 当前脚本 `scripts/vbt_us_td9_all_assets.py` 已经写了一半且可以编译，但缺少 evaluation/report/main。请继续补完它，不要重头另起炉灶。
5. 长任务每个阶段写 checkpoint 到 `outputs/us_td9_all_assets/td9_all_assets_<timestamp>/`，避免依赖聊天上下文。
6. 回测口径继续保持：收盘后生成信号，下一交易日开盘成交；设置单边费用/滑点 0.1%。
7. 评分不能只看收益，要同时惩罚最大回撤、低 Sharpe、过低全样本年化、过少交易、过低暴露。必须包含 buy-and-hold benchmark。
8. 输出：
   - 全部标的最优结果表；
   - 效果最好的前 5 名，按效果排序；
   - MAG7 结果表；
   - ETF/fund/index 结果表；
   - QLD 和 TQQQ 的最优策略、效果、历史买卖点和详细策略说明；
   - final `report.md`、`best_config.json`、各标的 trades/operation CSV。
9. vectorbt 运行前设置：
   `$env:NUMBA_CACHE_DIR='e:\dzhwork\quant\quant_lab\.numba_cache'`
   `$env:TMP='e:\dzhwork\quant\quant_lab\.tmp'`
   `$env:TEMP='e:\dzhwork\quant\quant_lab\.tmp'`

请先检查 `scripts/vbt_us_td9_all_assets.py` 和最近输出目录，然后补完脚本、运行回测、读取结果，最后用中文总结。
```

## Answer To User's Screenshot Question

If multiple historical tasks are separate Codex task records, their hidden chat contexts are not automatically available to a new Codex user from this one handoff. One handoff here is enough only for:

- this current thread's context, and
- facts/results that have been written into local files in `E:\dzhwork\quant\quant_lab`.

For each separate historical task shown in the screenshot, if there are important decisions/prompts/results that were not saved into local files, ask Codex in that specific historical task to create a similar local handoff summary. If the important outputs from those historical tasks are already saved in the repo under `docs/`, `outputs/`, or scripts, then one consolidated local handoff can reference those files and may be enough.

