# Codex Handoff - quant_lab Full Audit - 2026-04-18 17:50 CST

This is a local handoff document for moving the whole historical quant_lab task to another Codex user/account. It is written as an audit trail, not only a final summary. It consolidates the visible chat history, previous local handoff files, and local code/docs/outputs checked on 2026-04-18.

## Workspace / 工作区信息

- Project root: `E:\dzhwork\quant\quant_lab`
- Shell: Windows PowerShell
- Current handoff date/time: `2026-04-18 17:50 CST`
- Important skill: `C:\Users\Administrator\.codex\skills\588200-pool\SKILL.md`
- Git status: this directory is not a git repository. Local files, reports, checkpoints, and docs are the source of truth.
- Data mirror:
  - Original legacy data requested by user: `D:\dzhwork\quant`
  - QuantLab mirror: `E:\dzhwork\quant\quant_lab\data\external\legacy_quant`
  - Mapping doc: `docs/data_migration_map.md`
  - Verification recorded there: 18,545 files, 9.977 GB mirrored from D to E without deleting original D drive files.
- Main data roots found:
  - `data/external/legacy_quant`
  - `data/external/legacy_quant/AStock`
  - `data/external/legacy_quant/NSDQStock/19800101_20260404`
  - `data/qlib_bin`
  - `data/features_cache`
- Current validation checked during this handoff:
  - `$env:PYTHONPATH='.'; pytest` -> `18 passed`
  - `$env:PYTHONPATH='.'; python -m compileall -q src tests scripts\export_qlib_workflow_config.py` -> passed
- Background tasks:
  - `Get-CimInstance Win32_Process -Filter "name = 'python.exe'"` returned no active Python process during this handoff.

## Original User Request / 原始需求

The original user goal was:

1. The user wanted to do quant analysis.
2. The user had already built a local quant framework under `E:\dzhwork\quant\quant_lab\configs`.
3. The project was expected to use `qlib + vectorbt`.
4. The user had downloaded factor libraries.
5. Stock/fund data was originally under `D:\dzhwork\quant`.
6. The user asked Codex to comprehensively analyze the framework and factor libraries and suggest improvements because current backtest results were not satisfactory.

The task then expanded into a broad program:

- Mirror D-drive quant data into the `quant_lab` workspace.
- Build a 588200Pool research workflow and generalize beyond one ETF.
- Search online for high-quality safe stock strategies and high-quality factor libraries.
- Add factor combinations, TD9/神奇九转, moving-average crossovers, sideways-market filters, and robust strategy search.
- Download/use AutoResearch-style ideas.
- Create a dedicated `588200Pool` skill.
- Extend beyond 588200 into US QQQ/QLD/TQQQ research.
- Download and adapt external factor libraries.
- Add better strategy construction so 4000+ factors are not wasted by weak strategy logic.
- Land the strategy/factor library into both `vectorbt` and `Qlib` reuse paths.
- Create local handoff files so a new Codex user can continue without the current chat.

## User Corrections And Preferences / 用户后续修正和偏好

1. Data migration:
   - User agreed to mirror `D:\dzhwork\quant` into `E:\dzhwork\quant\quant_lab`.
   - Implementation preserved original D-drive files and mirrored into `data/external/legacy_quant`.

2. 588200 vs generalized pool:
   - User clarified the goal was not to overfit one short-history ETF (`588200` / typo variants like `58820` appeared).
   - Correct approach: build a stock/ETF pool so the strategy has better generalization.
   - Later 588200 recommendations must compare training pool, similar ETF OOS pool, and 588200 target OOS.

3. Long runs and timeout:
   - User asked why Codex could not run all strategies/factors for hours and where the 10-minute timeout came from.
   - Codex explained foreground tool calls can time out; broad grids should use `Start-Process`, stdout/stderr logs, checkpoint CSVs, and resumable phases.
   - User explicitly required: "后台长跑 + 日志 + 断点保存，必要时分阶段跑完后继续汇总".

4. Report quality:
   - User required every `report*.md` to explain strategy meaning, every indicator, exact buy points, exact sell points, and usage.
   - `docs/report_generation_standard.md` was created for this rule.
   - Future reports must not only print strategy IDs or metrics.

5. Factor combinations:
   - User asked whether factor mining used only single factors.
   - User required factor combinations and TD9/神奇九转 signal inclusion.
   - Multi-factor z-score breadth combinations were added.

6. Skill:
   - User asked whether Codex has skills and whether a skill could be installed.
   - User requested a dedicated `588200Pool` skill so "跑588200Pool量化策略" automatically follows the workflow.

7. Momentum interpretation:
   - User asked whether momentum strategies are like "5-day MA crosses above 60-day MA buy, crosses below sell".
   - Codex clarified MA cross is one momentum family, not the whole concept.

8. User dissatisfaction:
   - User said the actual 588200 switch points "简直烂透了" and "根本不可能有你宣传的收益".
   - Codex audited signal date vs next-open execution and explained high returns mainly came from a small number of trend trades.
   - This led to stricter reporting of signal day, execution day, signal close, and next-open execution price.

9. MA cross requirement:
   - User explicitly asked to add `5MA/20MA/60MA/120MA` crossover strategy families and separately run "均线交叉动量策略".

10. Sideways-market problem:
   - User observed trend strategies catch big trends but perform poorly in sideways/choppy markets.
   - User asked to search online and solve this using `588200POOL` skill.
   - Sideways filters were added: ADX, Kaufman ER, Choppiness Index, MA gap / ATR, min-hold, cooldown.

11. AutoResearch:
   - User asked to download the AutoResearch GitHub project and use it for factor/strategy exploration.
   - Likely repo: `https://github.com/karpathy/autoresearch`.
   - Shell clone failed due GitHub 443/DNS issues; `SOURCE.md` was created and AutoResearch ideas were mapped into the local experimental harness.

12. External factor libraries:
   - User wanted the project to have high-quality factor libraries.
   - Later they pushed for all downloaded factor/strategy resources to be made reusable instead of sitting in `external_repos`.

13. Strategy library weakness:
   - User later said they had 4000+ factors but strategy logic was weak, so factor effects were not expressed.
   - They asked Codex to search for and implement stronger strategy structures beyond simple MA cross/factor crosses.

14. Dual framework:
   - User corrected that strategy and factor libraries must land in both `qlib` and `vectorbt`, not only vectorbt.
   - Result: `src/qlib_ext/strategy_bridge.py`, Qlib YAML export script, and dual-framework strategy pool.

15. Current handoff request:
   - User requested a complete local handoff doc plus a separate prompt file.
   - User required checking local files, not relying only on memory.
   - User required including task background, files, outputs, commands, errors, rejected results, unfinished tasks, and recovery instructions.

## Completed Work / 已完成工作

### 1. Data migration/mapping

- `D:\dzhwork\quant` was mirrored into `E:\dzhwork\quant\quant_lab\data\external\legacy_quant`.
- Mapping and verification were recorded in `docs/data_migration_map.md`.
- New code should use `configs/env/local.yaml` path keys such as `legacy_quant_root`, not hardcoded D-drive paths.

### 2. 588200Pool skill and workflow

- Local skill created: `C:\Users\Administrator\.codex\skills\588200-pool\SKILL.md`
- Skill defaults:
  - repo: `E:\dzhwork\quant\quant_lab`
  - data root: `data\external\legacy_quant`
  - target: `588200.SS`
  - train: `2022-10-26` to `2024-12-31`
  - OOS: `2025-01-01` to latest target data
  - run style: background long-run with logs and checkpoint CSV
  - selection: training-pool score + similar ETF OOS + 588200 OOS
  - reports must explain strategy meaning and buy/sell points.

### 3. 588200 safety factors and strategy families

Completed source changes:

- `src/factors/safety.py`
  - TD9/神奇九转 factors:
    - `alpha_td9_buy_setup_4_9`
    - `alpha_td9_sell_pressure_4_9`
  - Additional safety/formula factors:
    - downside volatility
    - rolling max drawdown
    - CVaR
    - Amihud liquidity
    - price-volume correlation
    - trend stability
    - momentum/reversal family

- `src/strategies/safety.py`
  - `MovingAverageCrossoverSpec`
  - `moving_average_crossover_signal`
  - `RegimeFilteredMASpec`
  - `regime_filtered_ma_signal`
  - `average_true_range`
  - `average_directional_index`
  - `efficiency_ratio`
  - `choppiness_index`

- `src/strategies/etf_588200.py`
  - Reusable 588200 ETF strategy specs and signal builders.
  - This avoids keeping all strategy definitions in one-off scripts.

### 4. 588200 research scripts

Completed scripts:

- `scripts/longrun_588200_factor_strategy_search.py`
  - Single factors and multi-factor combinations.
  - Cross-sectional z-score factor combinations.
  - Checkpoint CSV support.
- `scripts/research_588200_ma_crossover_strategy.py`
  - 5/20/60/120 MA cross family.
- `scripts/research_588200_sideways_filtered_strategy.py`
  - MA cross plus ADX/ER/Choppiness/ATR gap/min-hold/cooldown.
- `scripts/research_588200_td9_indicator_combo.py`
  - TD9 indicator combo strategy search.
  - Stage 1 target-only scan + Stage 2 pool robustness scan.
- `scripts/validate_588200_safety_upgrade.py`
  - Validation helper for safety upgrade.

### 5. 588200 report standard

- `docs/report_generation_standard.md` created.
- Required fields include strategy target, one-sentence meaning, strategy ID decoding, indicator object/calculation, buy/sell conditions, execution timing, risk controls, train/OOS/full metrics, usage, and limitations.

### 6. AutoResearch source handling

- Directory: `external_repos\karpathy_autoresearch`
- Source note: `external_repos\karpathy_autoresearch\SOURCE.md`
- Attempted clone:
  ```powershell
  git clone --depth 1 https://github.com/karpathy/autoresearch.git external_repos\karpathy_autoresearch
  ```
- Error:
  - `Failed to connect to github.com port 443`
  - raw GitHub also failed due `raw.githubusercontent.com` DNS/resolve issue in shell.
- Recovered by using web-reading plus local `SOURCE.md`.
- Adopted idea: fixed evaluator, fixed data loader, fixed execution model, fixed validation split, experiment logs, keep improvements and discard weak/crashing candidates.

### 7. External factor/resource download and reuse layer

Completed source changes:

- `src/factors/external_libraries.py`
- `src/factors/external_adapters.py`
- `src/factors/external_resource_catalog.py`
- `src/factors/__init__.py`
- `src/strategies/external_factor_strategies.py`
- `src/strategies/external_strategy_catalog.py`
- `src/strategies/__init__.py`

Completed docs:

- `docs/external_factor_adapters.md`
- `docs/external_resource_reuse.md`

Completed outputs:

- `outputs/factor_library_imports/download_status_20260416_172755.md`
- `outputs/factor_library_imports/download_retry_status_20260416_173052.md`
- `outputs/factor_library_imports/download_crypto_retry_status_20260416_173627.md`
- `outputs/factor_library_imports/final_report_20260416_173822.md`
- `outputs/factor_library_imports/full_reuse_checkpoint_20260416.md`
- `outputs/factor_library_imports/full_reuse_catalog_snapshot_20260416.json`
- `outputs/factor_library_imports/full_reuse_catalog_snapshot_20260416.md`
- `outputs/factor_library_imports/worldquant_source_alpha101_runtime_status_20260416.csv`
- `outputs/factor_library_imports/worldquant_source_alpha101_runtime_status_20260416.md`

Reusable surface recorded:

- 452 direct external panel factor names.
- 82 executable WorldQuant Alpha101 names from public source.
- 360 executable Qlib Alpha360 features.
- 10 local executable GTJA Alpha191 factors.
- 101 JoinQuant Alpha101 API entries discoverable through archived SDK.
- 191 JoinQuant Alpha191 API entries discoverable through archived SDK.
- 18 reusable external resource records.
- 9 external strategy/model template records.

Downloaded/archived resources include:

- `external_repos/factor_libraries/worldquant_alpha101_yli188`
- `external_repos/factor_libraries/worldquant_alpha101_sthsf`
- `external_repos/factor_libraries/alpha360_microsoft_qlib`
- `external_repos/factor_libraries/gtja_alpha191_selenama`
- `external_repos/factor_libraries/fama_french`
- `external_repos/factor_libraries/barra_msci`
- `external_repos/factor_libraries/joinquant_jqfactor_analyzer`
- `external_repos/factor_libraries/joinquant_jqdatasdk`
- `external_repos/factor_libraries/ricequant_rqalpha`
- `external_repos/factor_libraries/ricequant_rqalpha_mod_rqdata`
- `external_repos/factor_libraries/huatai_multifactor_framework_public_alt`
- `external_repos/factor_libraries/crypto_factors`
- `external_repos/factor_libraries/crypto_panda_public_alt`
- `external_repos/factor_libraries/pead_earnings_trade_backtest`
- `external_repos/factor_libraries/pead_harikumar_ganesh`
- `external_repos/factor_libraries/python_package_archives`
- `external_repos/factor_libraries/FAILED_DOWNLOADS.md`

Important limitations:

- Complete Tonglian/DataYes 424 factors need authorized account/data.
- Official Barra engine/data need license.
- JoinQuant/RiceQuant complete factor data need credentials.
- Some downloaded repos are archived references, not automatically executed.

### 8. US leveraged ETF / QQQ / QLD / TQQQ strategy work

Completed scripts:

- `scripts/research_us_leveraged_etf_full_strategy.py`
- `scripts/walk_forward_us_leveraged_etf_stability.py`
- `scripts/vbt_us_leverage_online.py`
- `scripts/vbt_us_leverage_momentum_combo.py`
- `scripts/vbt_us_td9_all_assets.py`

Important environment fix for vectorbt/numba:

```powershell
$env:NUMBA_CACHE_DIR='e:\dzhwork\quant\quant_lab\.numba_cache'
$env:TMP='e:\dzhwork\quant\quant_lab\.tmp'
$env:TEMP='e:\dzhwork\quant\quant_lab\.tmp'
```

Important script fix:

- Pandas `to_markdown()` failed because local `tabulate` was old.
- VectorBT report scripts were patched to use a custom Markdown table writer.

### 9. TD9 all-assets US run

- Script: `scripts/vbt_us_td9_all_assets.py`
- Final run directory: `outputs/us_td9_all_assets/td9_all_assets_20260418_095256`
- This supersedes the older handoff statement that TD9 all-assets was unfinished.
- No background Python process is currently running.

### 10. Enhanced factor strategy library and dual framework

Completed source changes:

- `src/strategies/factor_enhanced.py`
  - Factor blending, winsorization, z-score/rank normalization, group neutralization.
  - Quantile portfolios, Alphalens-style factor weights, Qlib-style TopKDropout.
  - Rolling IC weights, IC-weighted composite, time-series overlay, volatility targeting, strategy grid helper.
- `src/backtest/portfolio_factory.py`
  - `_rebalance_mask`
  - `_prepare_target_weight_row`
  - `run_weighted_portfolio_simple`
- `src/backtest/signal_factory.py`
  - `time_series_momentum_signal`
  - `dual_momentum_signal`
  - `donchian_trend_signal`
  - `zscore_mean_reversion_signal`
  - `macd_trend_signal`
  - `dual_thrust_signal`
- `src/backtest/vbt_engine.py`
  - `run_enhanced_factor_strategy`
  - external factor name panel computation support
  - quantile / alphalens / topk_dropout methods
- `src/qlib_ext/__init__.py`
- `src/qlib_ext/strategy_bridge.py`
- `scripts/export_qlib_workflow_config.py`
- `configs/qlib/dual_framework_alpha360_lgb_topk50_drop5.yaml`
- `configs/research/dual_framework_strategy_pool.yaml`
- `docs/dual_framework_strategy_reuse.md`

Test files:

- `tests/test_factor_enhanced_strategies.py`
- `tests/test_qlib_strategy_bridge.py`

Shared strategy specs:

- `topk_dropout_50_5`
- `topk_dropout_100_10`
- `quantile_20_long_only`
- `quantile_20_long_short`
- `ic_weighted_topk_dropout_50_5`

## Files Created Or Modified / 创建或修改的文件

### Handoff files created by earlier runs

- `docs/588200pool_context_handoff_20260415.md`
- `docs/codex_user_switch_handoff_20260418.md`
- `docs/codex_user_switch_prompt_20260418.txt`
- `docs/codex_handoff_strategy_factor_dual_framework_20260418_173351.md`
- `docs/codex_prompt_strategy_factor_dual_framework_20260418_173351.txt`

### Handoff files created by this handoff run

- `docs/codex_handoff_quant_lab_full_audit_20260418_175017.md`
- `docs/codex_prompt_quant_lab_full_audit_20260418_175017.txt`

### Docs/configs

- `docs/data_migration_map.md`
- `docs/report_generation_standard.md`
- `docs/quant_lab_strategy_factor_upgrade_plan_20260412.md`
- `docs/external_factor_adapters.md`
- `docs/external_resource_reuse.md`
- `docs/dual_framework_strategy_reuse.md`
- `configs/research/safe_strategy_pool.yaml`
- `configs/research/factor_catalog_plan.yaml`
- `configs/research/dual_framework_strategy_pool.yaml`
- `configs/qlib/dual_framework_alpha360_lgb_topk50_drop5.yaml`
- `configs/env/local.yaml`

### Source files

- `src/factors/safety.py`
- `src/factors/external_libraries.py`
- `src/factors/external_adapters.py`
- `src/factors/external_resource_catalog.py`
- `src/factors/__init__.py`
- `src/strategies/safety.py`
- `src/strategies/etf_588200.py`
- `src/strategies/external_factor_strategies.py`
- `src/strategies/external_strategy_catalog.py`
- `src/strategies/factor_enhanced.py`
- `src/strategies/__init__.py`
- `src/backtest/portfolio_factory.py`
- `src/backtest/signal_factory.py`
- `src/backtest/vbt_engine.py`
- `src/qlib_ext/__init__.py`
- `src/qlib_ext/strategy_bridge.py`

### Scripts

- `scripts/longrun_588200_factor_strategy_search.py`
- `scripts/research_588200_ma_crossover_strategy.py`
- `scripts/research_588200_sideways_filtered_strategy.py`
- `scripts/research_588200_td9_indicator_combo.py`
- `scripts/research_588200_generalized_strategy.py`
- `scripts/validate_588200_safety_upgrade.py`
- `scripts/evaluate_factor_library.py`
- `scripts/research_us_leveraged_etf_full_strategy.py`
- `scripts/walk_forward_us_leveraged_etf_stability.py`
- `scripts/vbt_us_leverage_online.py`
- `scripts/vbt_us_leverage_momentum_combo.py`
- `scripts/vbt_us_td9_all_assets.py`
- `scripts/export_qlib_workflow_config.py`

### Tests

- `tests/test_safety_upgrade.py`
- `tests/test_momentum_and_execution.py`
- `tests/test_factor_enhanced_strategies.py`
- `tests/test_qlib_strategy_bridge.py`

## Important Outputs / 重要输出

### 1. 588200 generalized and safety upgrade outputs

- `outputs/588200_strategy_optimization/20260412_064816`
- `outputs/588200_generalized_strategy/full_20260412_132729`
- `outputs/588200_generalized_strategy/full_20260412_132729/report_20260412_133846.md`
- `outputs/588200_safety_upgrade`
- `outputs/factor_library_eval`

These are early/older phases and are mostly superseded by later factor-combo and TD9 runs, but they contain the initial 588200 optimization history.

### 2. 588200 longrun factor combo

Run:

- `outputs/588200_longrun_factor_strategy/combo_20260412_224013`

Important files:

- `strategy_summary_checkpoint.csv`
- `strategy_summary_20260412_234101.csv`
- `factor_spearman_corr_20260412_234101.csv`
- `target_588200_signal_20260412_234101.csv`
- `best_config_20260412_234101.json`
- `report_20260412_234101.md`
- `combo_longrun.stdout.log`
- `combo_longrun.stderr.log` (0 bytes)
- `recommended_combo_config_20260412_235335.json`
- `target_588200_signal_recommended_combo_20260412_235335.csv`
- `report_recommended_combo_20260412_235515.md`
- `audit_switch_points_20260413.md`

Scope:

- 222 factor breadth signals.
- 16,066 strategy specs.
- Completed.

### 3. 588200 MA crossover

Run:

- `outputs/588200_ma_crossover_strategy/ma_cross_20260413_152740`

Important files:

- `strategy_summary_checkpoint.csv`
- `strategy_summary_20260413_152913.csv`
- `target_588200_signal_20260413_152913.csv`
- `target_588200_trades_20260413_152913.csv`
- `best_config_20260413_152913.json`
- `report_20260413_152913.md`

Scope:

- 276 specs.
- Completed.

### 4. 588200 sideways-filtered trend

Run:

- `outputs/588200_sideways_filtered_strategy/sideways_20260413_164557`

Important files:

- `sideways.stdout.log`
- `sideways.stderr.log` (0 bytes)
- `strategy_summary_checkpoint.csv`
- `strategy_summary_20260413_181213.csv`
- `target_588200_signal_20260413_181213.csv`
- `target_588200_trades_20260413_181213.csv`
- `best_config_20260413_181213.json`
- `report_20260413_181213.md`

Scope:

- 11,988 specs.
- Completed.

### 5. 588200 TD9 indicator combo

Older incomplete attempt:

- `outputs/588200_td9_indicator_combo/td9_combo_20260415_212607`
- `strategy_summary_checkpoint.csv` had 500 rows.
- `td9_combo.stderr.log` empty.
- Superseded by stage2 run below.

Final stage2 run:

- `outputs/588200_td9_indicator_combo/td9_combo_stage2_20260415_213550`

Important files:

- `td9_combo.stdout.log`
- `td9_combo.stderr.log` (0 bytes)
- `target_only_stage.csv`
- `strategy_summary_checkpoint.csv`
- `strategy_summary_20260415_215226.csv`
- `target_588200_signal_20260415_215226.csv`
- `target_588200_trades_20260415_215226.csv`
- `best_config_20260415_215226.json`

Scope:

- Candidate count: 18,144.
- Stage 1 target-only scan completed.
- Stage 2 pool robustness scan evaluated 1,610 candidates.
- Completed. The 2026-04-15 handoff saying it was in progress is stale.
- Missing: a detailed final Chinese `report.md` was not found in this directory.

### 6. 588200 TD9 MA simple/fast

Runs:

- `outputs/588200_td9_ma_simple/td9_ma_20260415_233546`
- `outputs/588200_td9_ma_simple/td9_ma_fast_20260415_234750`

Important files in fast run:

- `latest_588200_sina.csv`
- `strategy_summary.csv`
- `target_588200_signal.csv`
- `target_588200_trades.csv`
- `best_config.json`
- `complex_constituent_latest_status.csv`
- `complex_best_latest_signal.csv`
- `complex_best_latest_state.json`

Fast run latest data:

- Data source: Sina via `akshare fund_etf_hist_sina(sh588200)`.
- Latest local 588200 bar: `2026-04-15`.

Missing:

- No detailed final `report.md` found; needs explanatory report if this candidate is used.

### 7. External factor library import outputs

Run directory:

- `outputs/factor_library_imports`

Important files:

- `download_status_20260416_172755.md/json`
- `download_retry_status_20260416_173052.md/json`
- `download_crypto_retry_status_20260416_173627.md/json`
- `final_report_20260416_173822.md`
- `external_factor_library_catalog_snapshot_20260416_173822.json`
- `full_reuse_checkpoint_20260416.md`
- `full_reuse_catalog_snapshot_20260416.json/md`
- `worldquant_source_alpha101_runtime_status_20260416.csv/md`
- `logs\*.log`

### 8. US leveraged ETF / all-assets outputs

US full strategy:

- `outputs/us_leveraged_etf_full_strategy/full_us_20260416_010500`

Walk-forward:

- `outputs/us_leveraged_etf_walk_forward/wf_us_20260417_5y`

Online-inspired vectorbt:

- `outputs/us_leveraged_etf_vectorbt_online_strategies/vbt_online_20260418_001937`

Momentum combo:

- `outputs/us_leveraged_etf_momentum_combo/momentum_combo_20260418_084322`

TD9 all-assets final:

- `outputs/us_td9_all_assets/td9_all_assets_20260418_095256`

Important files in TD9 all-assets:

- `report.md`
- `best_config.json`
- `top5_overall.csv`
- `qld_tqqq_best.csv`
- `instrument_best_summary.csv`
- `candidate_summary.csv`
- `candidate_summary_checkpoint.csv`
- `best_summary_checkpoint.csv`
- `universe.csv`
- `latest_data_status.csv`
- `checkpoint_00_start.json/md`
- `checkpoint_01_universe.json/md`
- `checkpoint_02_data.json/md`
- `checkpoint_03_final.json/md`
- per-symbol `*_operation_points.csv`
- per-symbol `*_signal_nav.csv`
- per-symbol `*_trades.csv`
- `updated_data\*.csv`

## Commands Run / 执行过的重要命令

### Project/data inspection

```powershell
Get-Location
Test-Path 'E:\dzhwork\quant\quant_lab'
Get-ChildItem 'E:\dzhwork\quant\quant_lab' -Force
Get-ChildItem -Path 'E:\dzhwork\quant\quant_lab\docs' -File | Sort-Object LastWriteTime -Descending
Get-ChildItem -Path 'E:\dzhwork\quant\quant_lab\outputs' -Directory | Sort-Object LastWriteTime -Descending
Get-ChildItem -Path 'E:\dzhwork\quant\quant_lab\scripts' -File | Sort-Object LastWriteTime -Descending
Get-ChildItem -Recurse -File -Path 'E:\dzhwork\quant\quant_lab\src' | Sort-Object LastWriteTime -Descending
Get-ChildItem -Path 'E:\dzhwork\quant\quant_lab\data' -Force
Get-ChildItem -Path 'E:\dzhwork\quant\quant_lab\external_repos' -Force
```

### Skill / handoff reads

```powershell
Get-Content -Raw 'C:\Users\Administrator\.codex\skills\588200-pool\SKILL.md'
Get-Content -Raw 'C:\Users\Administrator\.codex\skills\588200-pool\references\quant-lab-588200-workflow.md'
Get-Content -Raw 'docs\588200pool_context_handoff_20260415.md'
Get-Content -Raw 'docs\codex_user_switch_handoff_20260418.md'
Get-Content -Raw 'docs\codex_handoff_strategy_factor_dual_framework_20260418_173351.md'
Get-Content -Raw 'docs\dual_framework_strategy_reuse.md'
Get-Content -Raw 'docs\external_factor_adapters.md'
Get-Content -Raw 'docs\external_resource_reuse.md'
Get-Content -Raw 'docs\data_migration_map.md'
```

### Background process check

```powershell
Get-CimInstance Win32_Process -Filter "name = 'python.exe'" |
  Select-Object ProcessId,CommandLine | Format-List
```

No active Python process was found during this handoff.

### Historical long-run commands/patterns

```powershell
$runDir = "E:\dzhwork\quant\quant_lab\outputs\588200_longrun_factor_strategy\combo_$(Get-Date -Format yyyyMMdd_HHmmss)"
New-Item -ItemType Directory -Path $runDir -Force | Out-Null
$stdout = Join-Path $runDir "combo_longrun.stdout.log"
$stderr = Join-Path $runDir "combo_longrun.stderr.log"
$argList = @(
  "scripts\longrun_588200_factor_strategy_search.py",
  "--start", "2022-10-26",
  "--train-end", "2024-12-31",
  "--end", "2026-04-08",
  "--run-dir", $runDir,
  "--checkpoint-every", "100"
)
Start-Process -FilePath python -ArgumentList $argList -WorkingDirectory "E:\dzhwork\quant\quant_lab" -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
```

TD9 stage2 historical command:

```powershell
python scripts\research_588200_td9_indicator_combo.py --start 2022-10-26 --train-end 2024-12-31 --end 2026-04-08 --run-dir E:\dzhwork\quant\quant_lab\outputs\588200_td9_indicator_combo\td9_combo_stage2_20260415_213550 --checkpoint-every 250
```

US vectorbt env setup:

```powershell
$env:NUMBA_CACHE_DIR='e:\dzhwork\quant\quant_lab\.numba_cache'
$env:TMP='e:\dzhwork\quant\quant_lab\.tmp'
$env:TEMP='e:\dzhwork\quant\quant_lab\.tmp'
```

US scripts:

```powershell
python scripts\vbt_us_leverage_online.py --today 2026-04-21 --next-open-date 2026-04-20
python scripts\vbt_us_leverage_momentum_combo.py --today 2026-04-21 --next-open-date 2026-04-20
python scripts\vbt_us_td9_all_assets.py --today 2026-04-21 --next-open-date 2026-04-20
```

Qlib config export:

```powershell
$env:PYTHONPATH='.'
python scripts\export_qlib_workflow_config.py --strategy topk_dropout_50_5 --output configs\qlib\generated_topk50.yaml
```

### Validation commands

```powershell
$env:PYTHONPATH='.'; pytest
$env:PYTHONPATH='.'; python -m compileall -q src tests scripts\export_qlib_workflow_config.py
```

Current handoff run result:

- `18 passed`
- compileall passed.

### Commands that produced errors / gotchas

`rg` issue:

```powershell
rg --files
rg -n "strategy|vectorbt|qlib|factor"
```

Observed earlier:

- `rg.exe` exists but PowerShell got `Access is denied`.
- Workaround: use `Get-ChildItem` and `Select-String`.

Bash heredoc in PowerShell:

```powershell
python - <<'PY'
...
PY
```

Error:

- `Missing file specification after redirection operator.`
- `The '<' operator is reserved for future use.`

Workaround:

```powershell
@'
print("hello")
'@ | python -
```

Qlib probe:

```powershell
$env:PYTHONPATH='.'; @'
try:
    import qlib
    print(qlib.__version__)
except Exception as e:
    print(type(e).__name__, e)
'@ | python -
```

Observed:

- `ModuleNotFoundError No module named 'qlib'`

Pytest without PYTHONPATH:

- `ModuleNotFoundError: No module named 'src'`
- Workaround: `$env:PYTHONPATH='.'; pytest`

AutoResearch clone:

```powershell
git clone --depth 1 https://github.com/karpathy/autoresearch.git external_repos\karpathy_autoresearch
```

Observed:

- `Failed to connect to github.com port 443`
- raw GitHub DNS/resolve also failed from shell.

ChatGPT compact error reported by user:

- `Error running remote compact task: unexpected status 503 Service Unavailable... url: https://chatgpt.com/backend-api/codex/responses/compact`
- This was a remote ChatGPT service/compaction error, not a local quant_lab bug.
- Local mitigation: create handoff docs and new-session prompts.

## Key Results / 关键结果

### 1. 588200 current robust recommendation before TD9 MA simple

All completed strategy families were merged/analyzed earlier. The robust winner across factor-combo / MA-cross / sideways, requiring positive training pool, OOS pool, 588200 train, and 588200 OOS, was:

`factor_overlay__combo2__alpha_pv_corr_20__safe_low_vol_60__mom120__vol120__vp90__fb50__fs40__poolmom`

Meaning:

- `mom120`: 588200 own 120-day momentum must be positive.
- `vol120__vp90`: 588200 120-day volatility percentile must not exceed 90%.
- `poolmom`: constituent pool 20-day median return must be positive.
- `fb50__fs40`: factor breadth buy threshold 50%, sell threshold 40%.
- `alpha_pv_corr_20`: negative 20-day price-volume correlation; higher means less adverse price-volume pressure.
- `safe_low_vol_60`: negative 60-day realized volatility; higher means safer/lower volatility.

588200 OOS metrics:

- Annual return: 61.83%
- Sharpe: 2.529
- Max drawdown: -12.62%
- Exposure: 27.72%
- Pool train median Sharpe: 0.449
- Pool OOS median Sharpe: 2.546
- 588200 train Sharpe: 0.549

This remains the best documented robust 588200Pool-style recommendation.

### 2. 588200 highest OOS but high overfit risk

Strategy:

`factor_overlay__combo3__alpha_pv_corr_20__alpha_reversal_20__safe_liquidity_amihud_60__mom120__vol120__vp90__fb50__fs40__poolmom`

588200 OOS:

- Annual return: 83.50%
- Sharpe: 2.928
- Max drawdown: -12.62%
- Exposure: 30.03%

Warning:

- Training pool median Sharpe and target train Sharpe were weak/negative.
- Treat as aggressive OOS winner, not final robust recommendation.

### 3. 588200 TD9 indicator combo completed result

Run:

- `outputs/588200_td9_indicator_combo/td9_combo_stage2_20260415_213550`

Best/robust strategy in `best_config_20260415_215226.json`:

`td9_combo__alpha_td9_sell_pressure_4_9__mom120__td50_40__bb55_bs45__vol120_vp90__poolmom__none__vix_below_ma20`

Meaning:

- TD9 factor: `alpha_td9_sell_pressure_4_9`
- TD9 breadth buy threshold: 50%
- TD9 breadth sell threshold: 40%
- Trend rule: 588200 120-day momentum positive.
- Constituent MA breadth: buy 55%, sell 45%.
- Vol filter: 588200 120-day vol percentile <= 90%.
- `poolmom`: constituent 20-day median return positive.
- Bollinger rule: none.
- VIX filter: VIX below its 20-day moving average.

588200 OOS metrics from `strategy_summary_20260415_215226.csv`:

- Annual return: 46.46%
- Sharpe: 2.531
- Max drawdown: -4.53%
- Exposure: 20.79%
- Pool train median Sharpe: 0.487
- Pool OOS median Sharpe: 2.518
- 588200 train Sharpe: 0.549

Latest signal from best config:

- Signal date: `2026-04-08`
- Close: `2.514`
- Next action: `EMPTY_OR_SELL_588200`

Interpretation:

- This strategy has lower annual return than the factor-combo robust winner but much lower OOS drawdown.
- It is a strong defensive candidate, but needs a detailed Chinese final report because no `report.md` was found in this run directory.

### 4. 588200 TD9 MA simple/fast result

Run:

- `outputs/588200_td9_ma_simple/td9_ma_fast_20260415_234750`

Recommended in `best_config.json`:

`td9_buy_ma__ma13_20__buy2_r1__exit7`

Meaning:

- Family: `td9_buy_ma`
- MA trend: MA13 vs MA20.
- Buy when TD9 buy setup count is at least 2 and occurred/recent condition `r1`.
- Exit when TD9 sell setup reaches 7.
- Latest desired after close: 0.0, i.e. empty/sell after latest 2026-04-15 Sina bar.

Metrics:

- Train annual: 9.75%
- Train Sharpe: 0.343
- Train max drawdown: -24.79%
- OOS annual: 63.79%
- OOS Sharpe: 3.176
- OOS max drawdown: -5.08%
- Full annual: 27.14%
- Full Sharpe: 1.168
- Full max drawdown: -24.79%
- Full exposure: 36.03%
- Train trades: 17
- Test trades: 13

Warning:

- This is primarily a target/single-ETF run and not as pool-robust as the 588200Pool strategy selection rule.
- It looks attractive on 588200 but needs a final explanatory report and overfit warning.

### 5. 588200 MA cross result

Run:

- `outputs/588200_ma_crossover_strategy/ma_cross_20260413_152740`

Best OOS strategy:

`ma_cross_pool_vol__ma5_60__bb55__bs45__vol120__vp90__poolmom`

588200 OOS:

- Annual return: 65.09%
- Sharpe: 2.095
- Max drawdown: -12.62%
- Exposure: 37.29%

Warning:

- Training pool metrics were weak.
- Use as "MA crossover family OOS best", not robust final.

### 6. 588200 sideways-filtered result

Run:

- `outputs/588200_sideways_filtered_strategy/sideways_20260413_164557`

Best OOS strategy:

`sideways_filter__ma20_60__bb55__bs45__vol120__vp90__adx14_15_gap_20__poolmom`

588200 OOS:

- Annual return: 64.53%
- Sharpe: 2.109
- Max drawdown: -12.62%
- Exposure: 32.67%
- OOS trades: 4
- OOS gross losing trades: 0

Warning:

- Training period and training-pool results were weak/negative.
- More like 2025-2026 588200-specific OOS fit than robust final.

### 7. External factor library result

Current usable factor surface:

- 452 external panel factor names.
- 82 executable WQ Alpha101 factors.
- 360 Qlib Alpha360 features.
- 10 local GTJA Alpha191 factors.
- JoinQuant/RiceQuant/vendor data needs credentials.

Recommended next use:

- Feed these factor panels into `VBTBacktestEngine.run_enhanced_factor_strategy`.
- For Qlib, Alpha360 is ready through Qlib handler config; WQ/GTJA need exported feature table/custom handler for Qlib execution.

### 8. US leveraged ETF full strategy result rejected by user

Run:

- `outputs/us_leveraged_etf_full_strategy/full_us_20260416_010500`

TQQQ earlier best:

- `qqq_underlying_dual_thrust_w40_k0.3`
- Test annual: 51.33%
- Test maxDD: -31.04%
- Full annual: 12.71%
- Full maxDD: -58.25%

QLD earlier best:

- `alpha_ret_skew_60_cs_high_top0.35`
- Test annual: 37.95%
- Test maxDD: -19.32%
- Full annual: 9.57%
- Full maxDD: -63.13%

User rejected these as too weak due low full-period return and huge drawdown.

### 9. US walk-forward stability result

Run:

- `outputs/us_leveraged_etf_walk_forward/wf_us_20260417_5y`

Findings:

- TQQQ QQQ DualThrust fixed current best:
  - 10 folds
  - positive years 40%
  - stitched annual 19.37%
  - total 415.25%
  - Sharpe 0.687
  - maxDD -37.81%
- QLD ReturnSkew CS fixed current best:
  - 11 folds
  - positive years 81.82%
  - stitched annual 17.74%
  - total 433.85%
  - Sharpe 1.032
  - maxDD -19.32%

### 10. US online-inspired vectorbt result

Run:

- `outputs/us_leveraged_etf_vectorbt_online_strategies/vbt_online_20260418_001937`

TQQQ:

- Strategy: `qqq_sma150_band0.005`
- Rule: buy/hold TQQQ when QQQ close > QQQ SMA150 * 1.005; sell when QQQ close < QQQ SMA150 * 0.995.
- Test annual: 37.01%
- Test maxDD: -41.94%
- Full annual: 36.23%
- Full maxDD: -47.54%
- Latest action for 2026-04-20: `HOLD_OR_KEEP_LONG`

QLD:

- Strategy: `qqq_sma180_band0.005`
- Test annual: 30.38%
- Test maxDD: -29.72%
- Full annual: 21.94%
- Full maxDD: -42.19%
- Latest action for 2026-04-20: `HOLD_OR_KEEP_LONG`

### 11. US momentum combo result

Run:

- `outputs/us_leveraged_etf_momentum_combo/momentum_combo_20260418_084322`

Score-first result:

- TQQQ: `qqq_ema3_40_band0.0050`
  - Test annual 34.09%
  - Test maxDD -41.90%
  - Full annual 28.22%
  - Full maxDD -52.27%
  - Latest action: `HOLD_OR_KEEP_LONG`
- QLD: `asset_sma3_200_band0.0050`
  - Test annual 28.03%
  - Test maxDD -29.72%
  - Full annual 20.41%
  - Full maxDD -42.58%
  - Latest action: `HOLD_OR_KEEP_LONG`

Recommended robust summary:

- TQQQ: `qqq_score_e11_x9_cool3`
  - QQQ 19-feature momentum score; enter >= 11, exit <= 9, 3-day cooldown.
  - Test annual 24.30%
  - Test maxDD -43.33%
  - Full annual 28.42%
  - Full maxDD -43.33%
  - Sharpe 0.754
- QLD: `qqq_ema3_120_band0.0025`
  - QQQ EMA3 crosses EMA120 with 0.25% hysteresis.
  - Test annual 27.25%
  - Test maxDD -29.72%
  - Full annual 22.07%
  - Full maxDD -41.93%
  - Sharpe 0.799

### 12. US TD9 all-assets result

Run:

- `outputs/us_td9_all_assets/td9_all_assets_20260418_095256`

Universe:

- 43 symbols evaluated.
- MAG7: AAPL, MSFT, NVDA, AMZN, META, GOOGL, TSLA.
- Fund/ETF/index candidates: 36.
- Latest date in output: 2026-04-17 for current updated symbols.

Top 5 overall:

1. `NVDA` / `td9_pullback_macd_ma200_b6_s9`
   - Family: `td9_pullback_trend`
   - Score: 1.0771
   - Test annual: 3.70%
   - Test maxDD: -0.85%
   - Full annual: 1.57%
   - Full maxDD: -13.79%
   - Full exposure: 0.92%
   - Full trades: 5
   - Warning: very low exposure/very few trades.
2. `_VIX` / `qqq_ema3_120_vix22_td9safe`
   - Family: `cross_market_td9_safe`
   - Score: 1.0380
   - Test annual: 96.21%
   - Test maxDD: -45.94%
   - Full annual: 73.37%
   - Full maxDD: -53.77%
   - Warning: `_VIX` is index-like and not directly tradable.
3. `GOOGL` / `qqq_ema3_120_b0.0025`
   - Test annual: 34.97%
   - Test maxDD: -22.76%
   - Full annual: 23.04%
   - Full maxDD: -31.65%
4. `META` / `qqq_ema3_120_td9_exit_s9`
   - Test annual: 35.09%
   - Full annual: 21.84%
   - Full maxDD: -45.59%
5. `MAIN` / `qqq_ema3_120_b0.0025`
   - Test annual: 19.71%
   - Full annual: 15.36%
   - Full maxDD: -30.67%

QLD/TQQQ from `qld_tqqq_best.csv`:

- `QLD`
  - Strategy: `qqq_ema3_120_b0.0025`
  - Family: `qqq_ema_cross`
  - Test annual: 27.25%
  - Test maxDD: -29.72%
  - Full annual: 22.07%
  - Full maxDD: -41.93%
  - Full Sharpe: 0.799
  - Full trades: 41
  - Latest date: 2026-04-17
  - Latest close: 76.73
- `TQQQ`
  - Strategy: `qqq_ema3_40_b0.0050`
  - Family: `qqq_ema_cross`
  - Test annual: 34.09%
  - Test maxDD: -41.90%
  - Full annual: 28.22%
  - Full maxDD: -52.27%
  - Full Sharpe: 0.771
  - Full trades: 66
  - Latest date: 2026-04-17
  - Latest close: 58.59

Conclusion:

- TD9 all-assets completed, but top score can be misleading due low exposure or non-tradable `_VIX`.
- QLD/TQQQ still have high full-period drawdowns; do not call them final "safe" strategies.

### 13. Dual-framework strategy/factor library result

Current recommended reusable architecture:

1. Use `VBTBacktestEngine.run_enhanced_factor_strategy(...)` for vectorbt/local research.
2. Use `src.qlib_ext.strategy_bridge` for shared strategy configs and Qlib workflow generation.
3. Use `configs/research/dual_framework_strategy_pool.yaml` as the strategy inventory.
4. Use `configs/qlib/dual_framework_alpha360_lgb_topk50_drop5.yaml` as the ready Qlib template.

Tests:

- 18 passed.

Qlib caveat:

- Config generation exists.
- Actual Qlib execution was not run because current environment does not have `qlib` installed.

## Rejected Or Superseded Results / 被否定或已被后续替代的结果

1. Early "single 588200 best" approach:
   - Superseded because user clarified a single short-history ETF does not generalize.

2. Reports that only printed strategy IDs/metrics:
   - User rejected this style.
   - `docs/report_generation_standard.md` exists to prevent it.

3. 588200 switch-point explanation:
   - User said the posted switch points looked "烂透了".
   - Audit clarified signal-vs-execution timing and that gains came from a small number of trend trades.

4. Training-pool first result in factor combo:
   - `factor_overlay__alpha_td9_sell_pressure_4_9__mom60__vol20__vp95__fb60__fs50`
   - Failed 588200 OOS: annual about -4.79%, Sharpe -0.374.
   - Do not recommend.

5. 588200 OOS absolute champion:
   - Very strong OOS but weak train/pool robustness.
   - Can be shown but must be labeled high overfit risk.

6. MA-cross and sideways OOS champions:
   - Good 588200 OOS but weak train/pool robustness.
   - Use only as family-specific best, not final robust strategy.

7. US leveraged ETF full strategy early results:
   - TQQQ full annual 12.71%, maxDD -58.25%.
   - QLD full annual 9.57%, maxDD -63.13%.
   - User considered these too weak.

8. Old `docs/codex_user_switch_handoff_20260418.md` TD9 status:
   - It said `scripts/vbt_us_td9_all_assets.py` was unfinished.
   - This is now superseded. Current output `td9_all_assets_20260418_095256` is complete.

9. `docs/codex_user_switch_prompt_20260418.txt`:
   - Contains mojibake/encoding damage.
   - Use this new handoff and prompt instead.

## Current State / 当前状态

- No Python background process was detected during this handoff.
- Tests pass: 18 passed.
- Compile check passes.
- 588200 TD9 indicator combo stage2 completed.
- 588200 TD9 MA simple/fast completed but lacks a final explanatory report.
- US TD9 all-assets completed.
- External factor libraries have been cataloged and partially made executable/reusable.
- Dual framework strategy library exists for vectorbt and Qlib config generation.
- Qlib itself is not installed in the active Python environment, so actual Qlib run remains unfinished.
- Several older Markdown files display mojibake in PowerShell output. The content may be UTF-8 but terminal decoding is poor. Prefer newer handoff files for clean recovery.

## Known Issues / 已知问题

1. No git repository:
   - Cannot rely on git status/diff.
   - Preserve user files; do not delete outputs.

2. `qlib` not installed:
   - `ModuleNotFoundError No module named 'qlib'`.
   - Qlib config generation works, actual Qlib workflow execution needs environment setup.

3. `rg.exe` access denied:
   - Use PowerShell `Get-ChildItem` and `Select-String` if `rg` fails.

4. PowerShell is not Bash:
   - Do not use `python - <<'PY'`.
   - Use here-string piped to Python.

5. Foreground command timeout:
   - Long factor/strategy grids should use background `Start-Process`, stdout/stderr logs, and checkpoint CSV.

6. ChatGPT remote compact 503:
   - User saw `unexpected status 503 Service Unavailable` for compact task.
   - This is not fixable in repo; mitigation is local handoff docs and new-session prompts.

7. AutoResearch clone incomplete:
   - Shell could not clone GitHub due 443/DNS.
   - `external_repos\karpathy_autoresearch\SOURCE.md` records this.

8. Some output reports are mojibake in console:
   - Several earlier Chinese reports render garbled in PowerShell.
   - Do not treat garbled terminal display as failed strategy output; inspect files in UTF-8-aware editor if needed.

9. Survivorship / static pool risk:
   - 588200Pool constituent list and similar ETF pool are static, not full point-in-time historical membership.

10. Data freshness:
   - 588200 core runs use target data through 2026-04-08 or 2026-04-15 depending on run.
   - US runs use updated symbols through 2026-04-17.
   - Some local stock universe files remain older unless updated.

11. Overfit risk:
   - 588200 has short history.
   - Single-target TD9/MA results are attractive but not necessarily robust.
   - Top US results can be low exposure or non-tradable.

12. QLD/TQQQ drawdowns:
   - Latest bests still have large full-period max drawdowns.
   - Do not present them as "safe" final strategies.

13. Python version:
   - Current environment is Python 3.11.
   - Project says `requires-python >=3.9`, but some code uses modern typing; if strict 3.9 is needed, audit type hints.

## Next Steps / 下一步

Priority next steps for a new Codex:

1. Read this handoff first.
2. Read:
   - `docs/dual_framework_strategy_reuse.md`
   - `docs/external_factor_adapters.md`
   - `docs/external_resource_reuse.md`
   - `docs/report_generation_standard.md`
   - `C:\Users\Administrator\.codex\skills\588200-pool\SKILL.md`
3. Validate current code:
   ```powershell
   cd E:\dzhwork\quant\quant_lab
   $env:PYTHONPATH='.'
   pytest
   python -m compileall -q src tests scripts\export_qlib_workflow_config.py
   ```
4. Do not rerun completed long searches before reading existing outputs.
5. For 588200:
   - Generate a final consolidated Chinese report comparing robust factor combo, TD9 indicator combo, TD9 MA simple/fast, MA crossover OOS best, and sideways-filtered OOS best.
   - Explicitly label robust vs target-only vs overfit-risk.
   - Include exact buy/sell rules and latest action.
6. For 4000+ factors:
   - Use `src/factors/external_adapters.py` and `src/strategies/factor_enhanced.py`.
   - Run a real vectorbt enhanced factor strategy backtest using a concrete universe and factor set.
   - Output checkpointed CSV + Markdown report.
7. For Qlib:
   - Install/configure `pyqlib` if user wants actual Qlib execution.
   - Verify `data/qlib_bin`.
   - Generate workflow config using `scripts/export_qlib_workflow_config.py`.
   - Later add custom feature export/handler for WQ Alpha101 and GTJA Alpha191 if needed.
8. For US QLD/TQQQ:
   - Treat existing results as research baselines.
   - If user demands safer strategies, optimize for drawdown/exposure/trade count, not only annual return.

## Recovery Instructions / 新 Codex 如何恢复继续

Start:

```powershell
cd E:\dzhwork\quant\quant_lab
$env:PYTHONPATH='.'
```

Read:

```powershell
Get-Content docs\codex_handoff_quant_lab_full_audit_20260418_175017.md
Get-Content docs\dual_framework_strategy_reuse.md
Get-Content docs\external_factor_adapters.md
Get-Content docs\external_resource_reuse.md
Get-Content docs\report_generation_standard.md
Get-Content src\strategies\factor_enhanced.py
Get-Content src\qlib_ext\strategy_bridge.py
Get-Content src\backtest\vbt_engine.py
```

Validate:

```powershell
$env:PYTHONPATH='.'
pytest
python -m compileall -q src tests scripts\export_qlib_workflow_config.py
```

Inspect 588200 latest outputs:

```powershell
Get-ChildItem outputs\588200_td9_indicator_combo\td9_combo_stage2_20260415_213550
Get-Content outputs\588200_td9_indicator_combo\td9_combo_stage2_20260415_213550\best_config_20260415_215226.json
Get-ChildItem outputs\588200_td9_ma_simple\td9_ma_fast_20260415_234750
Get-Content outputs\588200_td9_ma_simple\td9_ma_fast_20260415_234750\best_config.json
```

Inspect US TD9:

```powershell
Get-Content outputs\us_td9_all_assets\td9_all_assets_20260418_095256\report.md
Get-Content outputs\us_td9_all_assets\td9_all_assets_20260418_095256\qld_tqqq_best.csv
Get-Content outputs\us_td9_all_assets\td9_all_assets_20260418_095256\top5_overall.csv
```

Use vectorbt enhanced strategy:

```python
from src.backtest.vbt_engine import VBTBacktestEngine

engine = VBTBacktestEngine(
    data_dir="data/external/legacy_quant/NSDQStock/19800101_20260404",
    market="us",
)

result = engine.run_enhanced_factor_strategy(
    symbols=["QQQ", "QLD", "TQQQ"],
    factor_names=["qlib360_CLOSE59", "qlib360_VOLUME0"],
    start_date="2021-01-01",
    end_date="2026-04-17",
    rebalance_freq="W",
    portfolio_method="topk_dropout",
    top_k=2,
    n_drop=1,
)
```

Generate Qlib config:

```powershell
$env:PYTHONPATH='.'
python scripts\export_qlib_workflow_config.py --strategy topk_dropout_50_5 --output configs\qlib\generated_topk50.yaml
```

Avoid repeating:

- Do not recreate `588200-pool` skill; it already exists.
- Do not rerun 16k/18k/21k+ strategy grids before reading existing outputs.
- Do not treat old "TD9 unfinished" handoff as current fact.
- Do not rewrite `factor_enhanced.py` from scratch.
- Do not present `_VIX` as tradable without mapping to a real instrument.
- Do not recommend single-target OOS winners without overfit caveat.

## Full Prompt For New Codex / 给新 Codex 的完整提示词

See also separate prompt file:

`docs/codex_prompt_quant_lab_full_audit_20260418_175017.txt`

```text
你正在接手 Windows / PowerShell 工作区：

E:\dzhwork\quant\quant_lab

请先读取本地完整交接审计文档：

docs/codex_handoff_quant_lab_full_audit_20260418_175017.md

不要依赖旧聊天历史。以本地文件、checkpoint、summary CSV、best_config、report 和这个 handoff 为准。

历史任务核心：

用户有一个 qlib + vectorbt 双框架量化项目，原始数据从 D:\dzhwork\quant 镜像到了 E:\dzhwork\quant\quant_lab\data\external\legacy_quant。用户最初不满意 588200/股票基金回测效果，要求系统分析框架和因子库，补充更好的安全策略、因子库和策略挖掘方法。任务后来扩展为 588200Pool 策略研究、TD9/神奇九转、因子组合、均线交叉、横盘过滤、AutoResearch 思路、外部因子库下载和适配、US QQQ/QLD/TQQQ/vectorbt 回测、TD9 all-assets，以及把策略/因子库落入 qlib + vectorbt 双框架。

重要本地规范：

- 使用 588200Pool 任务时读取 skill：
  C:\Users\Administrator\.codex\skills\588200-pool\SKILL.md
- 报告规范：
  docs/report_generation_standard.md
- 数据迁移说明：
  docs/data_migration_map.md
- 双框架说明：
  docs/dual_framework_strategy_reuse.md
- 外部因子说明：
  docs/external_factor_adapters.md
  docs/external_resource_reuse.md

当前已完成的重点：

1. 数据已从 D:\dzhwork\quant 镜像到 data/external/legacy_quant。
2. 588200Pool skill 已创建。
3. 588200 已完成多轮策略搜索：
   - factor combo: outputs/588200_longrun_factor_strategy/combo_20260412_224013
   - MA cross: outputs/588200_ma_crossover_strategy/ma_cross_20260413_152740
   - sideways filter: outputs/588200_sideways_filtered_strategy/sideways_20260413_164557
   - TD9 indicator combo: outputs/588200_td9_indicator_combo/td9_combo_stage2_20260415_213550
   - TD9 MA simple/fast: outputs/588200_td9_ma_simple/td9_ma_fast_20260415_234750
4. 外部因子库已下载/索引/部分适配：
   - 452 external panel factors
   - 82 WorldQuant Alpha101
   - 360 Qlib Alpha360
   - 10 local GTJA Alpha191
5. US leveraged ETF / TD9 all-assets 已完成：
   outputs/us_td9_all_assets/td9_all_assets_20260418_095256
6. vectorbt + Qlib 双框架策略层已落地：
   - src/strategies/factor_enhanced.py
   - src/backtest/portfolio_factory.py
   - src/backtest/signal_factory.py
   - src/backtest/vbt_engine.py
   - src/qlib_ext/strategy_bridge.py
   - configs/research/dual_framework_strategy_pool.yaml
   - configs/qlib/dual_framework_alpha360_lgb_topk50_drop5.yaml
   - scripts/export_qlib_workflow_config.py

当前验证命令：

cd E:\dzhwork\quant\quant_lab
$env:PYTHONPATH='.'
pytest
python -m compileall -q src tests scripts\export_qlib_workflow_config.py

最近验证结果：18 passed，compileall passed。

重要结论：

- 588200Pool 当前稳健冠军仍优先看：
  factor_overlay__combo2__alpha_pv_corr_20__safe_low_vol_60__mom120__vol120__vp90__fb50__fs40__poolmom
  OOS annual 61.83%, Sharpe 2.529, maxDD -12.62%, exposure 27.72%.
- TD9 indicator combo 防守型候选：
  td9_combo__alpha_td9_sell_pressure_4_9__mom120__td50_40__bb55_bs45__vol120_vp90__poolmom__none__vix_below_ma20
  OOS annual 46.46%, Sharpe 2.531, maxDD -4.53%, exposure 20.79%, latest EMPTY_OR_SELL_588200 on 2026-04-08.
- TD9 MA fast target-only candidate：
  td9_buy_ma__ma13_20__buy2_r1__exit7
  OOS annual 63.79%, Sharpe 3.176, maxDD -5.08%, but it is more single-target and needs overfit warning.
- US QLD/TQQQ latest TD9 all-assets:
  QLD qqq_ema3_120_b0.0025, full annual 22.07%, maxDD -41.93%.
  TQQQ qqq_ema3_40_b0.0050, full annual 28.22%, maxDD -52.27%.
  These are research baselines, not safe final strategies.

Known issues:

- qlib is not installed in current Python env. Qlib config generation works, actual workflow execution requires installing/configuring pyqlib and data/qlib_bin.
- rg.exe may fail with Access denied; use Get-ChildItem/Select-String.
- PowerShell cannot use Bash heredoc; use here-string piped to python.
- Some older Chinese reports display mojibake in PowerShell.
- AutoResearch git clone failed due GitHub 443/DNS; see external_repos/karpathy_autoresearch/SOURCE.md.
- Do not rely on old handoff saying TD9 all-assets is unfinished; latest output is complete.

Next best task:

If user asks to continue 588200, generate a final consolidated Chinese report comparing robust factor combo, TD9 indicator combo, TD9 MA fast, MA cross, and sideways filter. Follow docs/report_generation_standard.md: explain every indicator, buy point, sell point, execution timing, latest action, train/OOS/full metrics, buy-and-hold benchmark, and overfit limitations.

If user asks to use the 4000+ factors, do not rewrite the strategy library. Use src/factors/external_adapters.py and src/strategies/factor_enhanced.py, then run a checkpointed real-data vectorbt enhanced factor strategy search with summary CSV/report.

请用中文回复用户，并明确你基于本地 handoff 和项目文件继续，不需要旧聊天历史。
```
