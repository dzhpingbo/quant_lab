# Codex Handoff - Strategy / Factor Library Dual Framework - 2026-04-18 17:33 CST

This is a local handoff document for continuing the current quant_lab work with another Codex user/account. It is written as an audit trail, not only a final summary. It includes the visible chat context from this task, important local files discovered during handoff preparation, prior local handoff files that were found, code changes, commands, errors, outputs, and recovery instructions.

## Workspace / 工作区信息

- Workspace root: `E:\dzhwork\quant\quant_lab`
- Shell: PowerShell on Windows
- Local timezone/date observed in this handoff run: `2026-04-18 17:33:51 +08:00`
- User project description: self-built quant analysis framework based on `qlib + vectorbt`.
- Repository status: Codex app reports this is not a git workspace. Treat local files, docs, outputs, and checkpoints as source of truth.
- Important environment detail:
  - `rg.exe` exists but PowerShell attempts to run it failed with `Access is denied`, so searches were done with `Get-ChildItem` and `Select-String`.
  - `pyqlib` / `qlib` is not installed in the current Python environment. `import qlib` returned `ModuleNotFoundError No module named 'qlib'`.
  - Tests require `PYTHONPATH=.` in this environment. Running pytest without it caused `ModuleNotFoundError: No module named 'src'`.

## Original User Request / 原始需求

The user said the current project is their own quant analysis framework based on `qlib + vectorbt`, with more than 4000 factors, but strategies are too weak so factor effects are not being expressed. The user asked Codex to:

- Seriously search the internet for all available/useful strategies.
- Find more excellent strategies beyond simple factor cross-combinations like momentum factor crossovers such as 5-day MA crossing above 60-day MA.
- Implement and land the strategies into the framework's strategy module, not just list ideas.
- Goal: make the existing large factor library actually usable through stronger portfolio construction, timing, and risk-control strategies.

## User Corrections And Preferences / 用户后续修正和偏好

The user then clarified an important architecture requirement:

- The collected strategy library and factor library must land into the user's `qlib + vectorbt` dual framework.
- Future backtests and analyses should be able to reuse these strategy and factor libraries.
- The work should not be vectorbt-only; there must be a Qlib bridge / workflow path.

Current handoff request:

- Create a complete local handoff document and a separate prompt file for a new Codex user.
- Include original request, corrections, decisions, commands, errors, completed work, unfinished work, outputs, rejected results, recovery instructions, and a full prompt.
- Check local files instead of relying only on memory.
- Write files under `docs/` using filenames like `docs/codex_handoff_<task>_<datetime>.md` and `docs/codex_prompt_<task>_<datetime>.txt`.

## Completed Work / 已完成工作

### 1. Local project exploration

Initial exploration:

- Listed project root with `Get-ChildItem -Force`.
- Tried `rg --files` and `rg -n ...`; both failed because `rg.exe` was denied by the OS.
- Switched to PowerShell native search with `Get-ChildItem -Recurse -File` and `Select-String`.
- Found relevant modules:
  - `src/backtest/signal_factory.py`
  - `src/backtest/portfolio_factory.py`
  - `src/backtest/vbt_engine.py`
  - `src/strategies/external_factor_strategies.py`
  - `src/strategies/external_strategy_catalog.py`
  - `src/strategies/safety.py`
  - `src/factors/external_adapters.py`
  - `configs/research/safe_strategy_pool.yaml`
  - `configs/research/factor_catalog_plan.yaml`

Important observation:

- Existing strategy layer had basic factor rank signals, long/short rank signals, momentum, breakout, moving-average crossover, RSI, simple filters, and equal-weight portfolio simulation.
- It lacked a reusable, weight-aware strategy layer for factor strength, IC weighting, TopKDropout, quantile portfolios, Alphalens-style factor weights, and Qlib workflow reuse.

### 2. Internet strategy research performed

Web search was performed because the user explicitly asked to search online. Sources used in design:

- Qlib strategy docs / TopkDropoutStrategy:
  - `https://qlib.readthedocs.io/en/latest/component/strategy.html`
- vectorbt portfolio docs:
  - `https://vectorbt.dev/api/portfolio/base/`
- Alphalens factor weights / quantile analysis:
  - `https://quantopian.github.io/alphalens/alphalens.html`
- Cross-sectional momentum:
  - Jegadeesh & Titman paper, local URL used in code metadata: `https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf`
- Time-series momentum:
  - Moskowitz/Ooi/Pedersen paper, URL used in code metadata: `https://pages.stern.nyu.edu/~lpederse/papers/TimeSeriesMomentum.pdf`
- Fama-French factor families:
  - `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html`
- Other strategy families searched or considered:
  - Dual Thrust
  - Turtle / Donchian breakout
  - MACD trend
  - z-score mean reversion
  - pairs/stat-arb concepts
  - sector/group neutralization
  - low volatility / quality / value / momentum factor construction

Decision:

- Implement only the parts that can be stably reused in the current data shape: date x asset factor panels and OHLCV panels.
- Avoid a detached research script; place strategy logic into `src/strategies`, `src/backtest`, and Qlib integration helpers.

### 3. Enhanced factor strategy library landed

Created `src/strategies/factor_enhanced.py`.

Implemented:

- `STRATEGY_RESEARCH_SOURCES`
- `FactorBlendSpec`
- `QuantilePortfolioSpec`
- `TopKDropoutSpec`
- `TimeSeriesOverlaySpec`
- Factor panel alignment and normalization:
  - `align_factor_panels`
  - `winsorize_panel`
  - `cross_section_zscore`
  - `rank_normalize_panel`
  - `neutralize_panel_by_group`
  - `normalize_factor_panel`
- Composite factor construction:
  - `combine_enhanced_factor_panels`
  - factor directions like `"low"` / inverse
- IC-based dynamic weighting:
  - `factor_ic_series`
  - `rolling_ic_weights`
  - `ic_weighted_composite`
- Portfolio construction from scores:
  - `quantile_weights_from_score`
  - `alphalens_style_factor_weights`
  - `topk_dropout_weights`
- Timing / risk overlays:
  - `apply_time_series_overlay`
  - `volatility_target_weights`
- Search grid helper:
  - `make_factor_strategy_grid`

Important implementation details:

- Quantile selection was corrected to select exact top/bottom counts by effective row universe size instead of relying on percentile boundary comparisons. This avoids over-selecting boundary assets in small universes and ETF pools.
- TopKDropout is Qlib-inspired: keep top-k holdings and limit number of dropped names per rebalance.
- IC weights are lagged before use so forward-return IC cannot leak into same-date decisions.

### 4. VectorBT / local backtest engine enhanced

Modified `src/backtest/portfolio_factory.py`.

Added:

- `_rebalance_mask`
- `_prepare_target_weight_row`
- `run_weighted_portfolio_simple`

Capabilities added:

- Run from target weight matrices, not only binary selected holdings.
- Supports long-only and long/short weights.
- Supports max positions, max absolute weight, gross exposure normalization, and turnover-proportional cost.
- Maintains close-signal / next-bar execution convention by shifting target weights one row before returns are applied.

Modified `src/backtest/signal_factory.py`.

Added reusable signal templates:

- `time_series_momentum_signal`
- `dual_momentum_signal`
- `donchian_trend_signal`
- `zscore_mean_reversion_signal`
- `macd_trend_signal`
- `dual_thrust_signal`

Modified `src/backtest/vbt_engine.py`.

Added:

- `run_enhanced_factor_strategy(...)`
- `_compute_factor_panels_by_name(...)`
- Updated `_compute_factor_panel(...)` to reuse named factor panel computation and average standardized panels.

Supported methods in `run_enhanced_factor_strategy`:

- `portfolio_method="quantile"`
- `portfolio_method="alphalens"`
- `portfolio_method="topk_dropout"`
- Optional `use_ic_weights=True`
- Optional `time_series_overlay`
- Optional `target_annual_vol`

Returned objects include:

- `nav`
- `returns`
- `weights`
- `target_weights`
- `benchmark_nav`
- `benchmark_returns`
- `metrics`
- `factor_panels`
- `factor_panel` / `score`
- `ic_weights`
- `leverage`
- `config`

### 5. Strategy exports updated

Modified `src/strategies/__init__.py`.

Exported the new enhanced strategy classes and functions so downstream scripts can import them from `src.strategies`.

### 6. Qlib bridge landed for dual-framework reuse

Created `src/qlib_ext/`.

Created `src/qlib_ext/strategy_bridge.py`.

Created `src/qlib_ext/__init__.py`.

Implemented Qlib bridge without importing Qlib at runtime. This is deliberate because the current environment does not have `qlib` installed, but config generation and tests should still work.

Key constructs:

- `DualFrameworkStrategySpec`
- `QlibWorkflowSpec`
- `DUAL_FRAMEWORK_STRATEGIES`
- `get_dual_framework_strategy`
- `list_dual_framework_strategies`
- `qlib_topk_dropout_strategy_config`
- `qlib_alpha360_field_config`
- `build_qlib_workflow_config`
- `dump_qlib_workflow_config`

Shared strategy specs now registered:

- `topk_dropout_50_5`
- `topk_dropout_100_10`
- `quantile_20_long_only`
- `quantile_20_long_short`
- `ic_weighted_topk_dropout_50_5`

Important design:

- Same strategy name can expose:
  - vectorbt config via `spec.vectorbt_config()`
  - qlib strategy config via `spec.qlib_strategy_config()`
- Qlib execution uses `qlib.contrib.strategy.TopkDropoutStrategy` and expects predictions as `<PRED>`.
- Qlib workflow template uses:
  - `qlib.contrib.data.handler.Alpha360`
  - `qlib.contrib.model.gbdt.LGBModel`
  - `SignalRecord`
  - `SigAnaRecord`
  - `PortAnaRecord`

Created Qlib export script:

- `scripts/export_qlib_workflow_config.py`

Purpose:

- Export reusable Qlib workflow YAML from a dual-framework strategy spec.

Example:

```powershell
$env:PYTHONPATH='.'
python scripts/export_qlib_workflow_config.py --strategy topk_dropout_50_5 --output configs/qlib/generated_topk50.yaml
```

Created ready Qlib config:

- `configs/qlib/dual_framework_alpha360_lgb_topk50_drop5.yaml`

Created dual-framework strategy pool manifest:

- `configs/research/dual_framework_strategy_pool.yaml`

Created reuse documentation:

- `docs/dual_framework_strategy_reuse.md`

### 7. Tests added and passed

Created `tests/test_factor_enhanced_strategies.py`.

Tests cover:

- Exact top/bottom quantile selection counts.
- TopKDropout limited turnover behavior.
- Weighted portfolio does not capture same-day return.
- IC weighted composite uses lagged IC weights.
- New signal factory timing templates produce expected bullish signals on rising sample data.
- Volatility target scales down high-vol portfolio.
- Factor direction handling reverses score correctly.

Created `tests/test_qlib_strategy_bridge.py`.

Tests cover:

- Dual framework strategy exposes both vectorbt and qlib configs.
- Qlib workflow config contains model, dataset, records, and strategy.
- Qlib TopkDropout config validates parameters.
- Strategy catalog is YAML serializable.

Verification results:

- First `pytest tests\test_factor_enhanced_strategies.py tests\test_momentum_and_execution.py tests\test_safety_upgrade.py` failed with `ModuleNotFoundError: No module named 'src'`.
- Re-ran with `$env:PYTHONPATH='.'`; 14 tests passed.
- Full test run after Qlib bridge:
  - `$env:PYTHONPATH='.'; pytest`
  - Result: 18 passed.
- Compile check:
  - `$env:PYTHONPATH='.'; python -m compileall -q src tests scripts\export_qlib_workflow_config.py`
  - Result: passed.

## Files Created Or Modified / 创建或修改的文件

### Created in current visible task

- `src/strategies/factor_enhanced.py`
- `src/qlib_ext/__init__.py`
- `src/qlib_ext/strategy_bridge.py`
- `scripts/export_qlib_workflow_config.py`
- `configs/qlib/dual_framework_alpha360_lgb_topk50_drop5.yaml`
- `configs/research/dual_framework_strategy_pool.yaml`
- `docs/dual_framework_strategy_reuse.md`
- `tests/test_factor_enhanced_strategies.py`
- `tests/test_qlib_strategy_bridge.py`
- This handoff file:
  - `docs/codex_handoff_strategy_factor_dual_framework_20260418_173351.md`
- New prompt file:
  - `docs/codex_prompt_strategy_factor_dual_framework_20260418_173351.txt`

### Modified in current visible task

- `src/backtest/portfolio_factory.py`
- `src/backtest/signal_factory.py`
- `src/backtest/vbt_engine.py`
- `src/strategies/__init__.py`

### Existing files read and referenced

- `configs/research/safe_strategy_pool.yaml`
- `configs/research/factor_catalog_plan.yaml`
- `docs/codex_user_switch_handoff_20260418.md`
- `docs/codex_user_switch_prompt_20260418.txt`
- `outputs/us_td9_all_assets/td9_all_assets_20260418_095256/report.md`
- `outputs/us_td9_all_assets/td9_all_assets_20260418_095256/top5_overall.csv`
- `outputs/us_td9_all_assets/td9_all_assets_20260418_095256/qld_tqqq_best.csv`
- `outputs/us_td9_all_assets/td9_all_assets_20260418_095256/best_config.json`

### Existing local pycache side effects

Running tests and compileall created or updated `__pycache__` files under `src/`, `tests/`, and `scripts/`. These are not source artifacts and should not be treated as important handoff content.

## Important Outputs / 重要输出

### Outputs generated by the visible strategy-library task

No new backtest report/checkpoint/csv output directories were generated by the current visible coding task. It was a library/framework integration task. Important outputs were source files, configs, docs, tests, and successful test results.

### Existing outputs found during handoff audit

These outputs are important context from earlier local work and prior handoff files. They are not newly generated by the current visible coding task, but they matter for recovery.

#### TD9 all-assets run

Run directory:

- `outputs/us_td9_all_assets/td9_all_assets_20260418_095256/`

Files found:

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
- `checkpoint_00_start.json`
- `checkpoint_00_start.md`
- `checkpoint_01_universe.json`
- `checkpoint_01_universe.md`
- `checkpoint_02_data.json`
- `checkpoint_02_data.md`
- `checkpoint_03_final.json`
- `checkpoint_03_final.md`
- Per-symbol operations/trades/nav files for at least:
  - `_VIX_operation_points.csv`
  - `_VIX_signal_nav.csv`
  - `_VIX_trades.csv`
  - `GOOGL_operation_points.csv`
  - `GOOGL_signal_nav.csv`
  - `GOOGL_trades.csv`
  - `MAIN_operation_points.csv`
  - `MAIN_signal_nav.csv`
  - `MAIN_trades.csv`
  - `META_operation_points.csv`
  - `META_signal_nav.csv`
  - `META_trades.csv`
  - `NVDA_operation_points.csv`
  - `NVDA_signal_nav.csv`
  - `NVDA_trades.csv`
  - `QLD_operation_points.csv`
  - `QLD_signal_nav.csv`
  - `QLD_trades.csv`
  - `TQQQ_operation_points.csv`
  - `TQQQ_signal_nav.csv`
  - `TQQQ_trades.csv`

Important TD9 results read from report / CSV:

- Universe evaluated: 43 symbols.
- MAG7: AAPL, MSFT, NVDA, AMZN, META, GOOGL, TSLA.
- Fund/ETF/index symbols: 36.
- Top 5 overall:
  1. `NVDA` / `td9_pullback_macd_ma200_b6_s9`
     - Family: `td9_pullback_trend`
     - Score: 1.0770666740250594
     - Test annual return: 3.70%
     - Test max drawdown: -0.85%
     - Full annual return: 1.57%
     - Full max drawdown: -13.79%
     - Warning: very low full exposure, about 0.92%, only 5 trades. This may score well on drawdown but may be too inactive for practical use.
  2. `_VIX` / `qqq_ema3_120_vix22_td9safe`
     - Score: 1.038002560699539
     - Full annual return: 73.37%
     - Full max drawdown: -53.77%
     - Warning: `_VIX` itself may not be directly tradable like an ETF. Treat as research/index result, not necessarily executable.
  3. `GOOGL` / `qqq_ema3_120_b0.0025`
     - Full annual return: 23.04%
     - Full max drawdown: -31.65%
  4. `META` / `qqq_ema3_120_td9_exit_s9`
     - Full annual return: 21.84%
     - Full max drawdown: -45.59%
  5. `MAIN` / `qqq_ema3_120_b0.0025`
     - Full annual return: 15.36%
     - Full max drawdown: -30.67%

QLD and TQQQ from `qld_tqqq_best.csv`:

- `QLD`
  - Strategy: `qqq_ema3_120_b0.0025`
  - Family: `qqq_ema_cross`
  - Test annual return: 27.25%
  - Test max drawdown: -29.72%
  - Full annual return: 22.07%
  - Full max drawdown: -41.93%
  - Full Sharpe: 0.7992
  - Full trades: 41
  - Latest date: 2026-04-17
  - Latest close: 76.73
- `TQQQ`
  - Strategy: `qqq_ema3_40_b0.0050`
  - Family: `qqq_ema_cross`
  - Test annual return: 34.09%
  - Test max drawdown: -41.90%
  - Full annual return: 28.22%
  - Full max drawdown: -52.27%
  - Full Sharpe: 0.7705
  - Full trades: 66
  - Latest date: 2026-04-17
  - Latest close: 58.59

#### Existing earlier handoff files

Found in `docs/`:

- `docs/codex_user_switch_handoff_20260418.md`
- `docs/codex_user_switch_prompt_20260418.txt`

These files contain earlier context for US leveraged ETF and TD9 tasks. The old prompt text is mojibake/encoding-garbled in places but still carries paths and task intent. The old handoff said the TD9 script was unfinished at that time; local outputs now show TD9 run completed later.

#### Other important existing output directories

Found under `outputs/`:

- `outputs/us_td9_all_assets/`
- `outputs/us_leveraged_etf_momentum_combo/`
- `outputs/us_leveraged_etf_vectorbt_online_strategies/`
- `outputs/us_leveraged_etf_full_strategy/`
- `outputs/us_leveraged_etf_walk_forward/`
- `outputs/factor_library_imports/`
- `outputs/588200_td9_ma_simple/`
- `outputs/588200_td9_indicator_combo/`
- `outputs/588200_sideways_filtered_strategy/`
- `outputs/588200_ma_crossover_strategy/`
- `outputs/factor_library_eval/`
- `outputs/588200_longrun_factor_strategy/`
- `outputs/588200_safety_upgrade/`
- `outputs/588200_generalized_strategy/`
- `outputs/588200_strategy_optimization/`

## Commands Run / 执行过的重要命令

### Exploration commands

```powershell
Get-ChildItem -Force
rg --files
rg -n "strategy|策略|vectorbt|qlib|factor|因子|backtest|Portfolio|Signal|Alpha|select|rank|topk|top_k" .
Get-ChildItem -Recurse -File | Select-Object -ExpandProperty FullName
Get-ChildItem -Recurse -File -Include *.py,*.md,*.toml,*.yaml,*.yml | Select-String -Pattern 'strategy','策略','vectorbt','qlib','factor','因子','backtest','Portfolio','Signal','Alpha','topk','top_k','rank' -CaseSensitive:$false
Get-ChildItem -Recurse -File -Path src,configs,tests,scripts -Include *.py,*.yaml,*.yml,*.md,*.toml | Select-Object -ExpandProperty FullName
Get-Content -Path configs\research\safe_strategy_pool.yaml
Get-Content -Path src\backtest\signal_factory.py
Get-Content -Path src\backtest\portfolio_factory.py
Get-Content -Path src\backtest\vbt_engine.py
Get-Content -Path src\strategies\external_factor_strategies.py
Get-Content -Path src\strategies\external_strategy_catalog.py
Get-Content -Path tests\test_momentum_and_execution.py
Get-Content -Path src\strategies\__init__.py
Get-Content -Path pyproject.toml
```

### Web searches / online lookups

Performed through the web tool:

- `Microsoft Qlib TopkDropoutStrategy documentation`
- `vectorbt Portfolio.from_signals stop loss take profit documentation`
- `quant factor investing multi factor ranking long short portfolio construction top quantile sector neutral`
- `trend following moving average crossover time series momentum cross sectional momentum research paper`
- Additional searches around:
  - Qlib TopkDropoutStrategy
  - vectorbt stop-loss/take-profit and order sizing
  - Jegadeesh/Titman momentum
  - Moskowitz/Ooi/Pedersen time-series momentum
  - Fama-French factor model
  - Dual Thrust
  - Turtle trading
  - RSRS
  - pairs/stat-arb
  - Alphalens factor weights

### Test and validation commands

```powershell
pytest tests\test_factor_enhanced_strategies.py tests\test_momentum_and_execution.py tests\test_safety_upgrade.py
$env:PYTHONPATH='.'; pytest tests\test_factor_enhanced_strategies.py tests\test_momentum_and_execution.py tests\test_safety_upgrade.py
$env:PYTHONPATH='.'; pytest
$env:PYTHONPATH='.'; python -c "from src.backtest.vbt_engine import VBTBacktestEngine; from src.strategies import STRATEGY_RESEARCH_SOURCES, QuantilePortfolioSpec; print('imports-ok', len(STRATEGY_RESEARCH_SOURCES))"
$env:PYTHONPATH='.'; python -m compileall -q src tests
$env:PYTHONPATH='.'; pytest tests\test_qlib_strategy_bridge.py tests\test_factor_enhanced_strategies.py
$env:PYTHONPATH='.'; python -m compileall -q src tests scripts\export_qlib_workflow_config.py
```

### Qlib environment probe

First attempted a Bash-style heredoc in PowerShell, which failed:

```powershell
$env:PYTHONPATH='.'; python - <<'PY'
...
PY
```

PowerShell error:

- `Missing file specification after redirection operator.`
- `The '<' operator is reserved for future use.`

Corrected by using PowerShell here-string piped to Python:

```powershell
$env:PYTHONPATH='.'; @'
import inspect
try:
    import qlib
    print('qlib', getattr(qlib, '__version__', 'unknown'), qlib.__file__)
    from qlib.contrib.strategy import TopkDropoutStrategy
    print('TopkDropoutStrategy', inspect.signature(TopkDropoutStrategy.__init__))
except Exception as e:
    print(type(e).__name__, e)
'@ | python -
```

Result:

- `ModuleNotFoundError No module named 'qlib'`

### Handoff audit commands

```powershell
Get-Date -Format 'yyyy-MM-dd HH:mm:ss K'
Get-ChildItem -Path docs -Force | Sort-Object LastWriteTime -Descending | Select-Object LastWriteTime,Length,Name,FullName
Get-ChildItem -Path outputs -Force | Sort-Object LastWriteTime -Descending | Select-Object -First 80 LastWriteTime,Length,Name,FullName
Get-ChildItem -Recurse -File -Path src,configs,scripts,tests,docs | Sort-Object LastWriteTime -Descending | Select-Object -First 80 LastWriteTime,Length,FullName
Get-ChildItem -Path data -Force | Sort-Object LastWriteTime -Descending | Select-Object -First 80 LastWriteTime,Length,Name,FullName
Get-Content -Path docs\codex_user_switch_handoff_20260418.md
Get-Content -Path docs\codex_user_switch_prompt_20260418.txt
Get-ChildItem -Recurse -File -Path outputs\us_td9_all_assets,outputs\us_leveraged_etf_momentum_combo,outputs\us_leveraged_etf_vectorbt_online_strategies -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 80 LastWriteTime,Length,FullName
Get-ChildItem -File -Path outputs\us_td9_all_assets\td9_all_assets_20260418_095256 | Sort-Object Name | Select-Object Name,Length,LastWriteTime
Get-Content -Path outputs\us_td9_all_assets\td9_all_assets_20260418_095256\report.md -TotalCount 220
Get-Content -Path outputs\us_td9_all_assets\td9_all_assets_20260418_095256\top5_overall.csv
Get-Content -Path outputs\us_td9_all_assets\td9_all_assets_20260418_095256\qld_tqqq_best.csv
Get-Content -Path outputs\us_td9_all_assets\td9_all_assets_20260418_095256\best_config.json
```

## Key Results / 关键结果

### Current visible task final recommendation

For the user's original "4000+ factors but weak strategies" request, the final recommended reusable framework is:

1. Use `run_enhanced_factor_strategy(...)` as the vectorbt-side strategy harness for:
   - robust factor blending,
   - quantile portfolios,
   - TopKDropout,
   - Alphalens-style factor weights,
   - IC dynamic weighting,
   - time-series overlays,
   - volatility targeting.
2. Use `src.qlib_ext.strategy_bridge` to keep the same strategy names reusable in Qlib workflow configs.
3. Use `configs/qlib/dual_framework_alpha360_lgb_topk50_drop5.yaml` as the starting Qlib template.
4. Use `configs/research/dual_framework_strategy_pool.yaml` as the strategy inventory / mapping manifest.

### Tests

- Full current test suite: 18 passed.
- Compile check: passed.

### Qlib status

- Qlib config generation is implemented and tested.
- Actual Qlib workflow execution was not run because `qlib` is not installed in this environment.

## Rejected Or Superseded Results / 被否定或已被后续替代的结果

### User dissatisfaction visible in current conversation

The user said the existing strategies in their framework were weak and did not express the value of the 4000+ factors. The examples of simple momentum crosses were explicitly considered insufficient.

The user then corrected the implementation direction: strategy and factor collection must be landed into both Qlib and vectorbt, not only a local/vectorbt module.

### Prior local handoff context: rejected ETF strategy results

Existing `docs/codex_user_switch_handoff_20260418.md` records that previous TQQQ/QLD results were considered too weak because full-period return was low or drawdown too high.

Examples from that prior handoff:

- TQQQ `qqq_underlying_dual_thrust_w40_k0.3`
  - Full annual 12.71%, maxDD -58.25%.
  - User rejected as too weak.
- QLD `alpha_ret_skew_60_cs_high_top0.35`
  - Full annual 9.57%, maxDD -63.13%.
  - User rejected as too weak.

These are superseded by later online-inspired / momentum-combo / TD9 runs, but still useful as negative examples.

### Superseded handoff state

The earlier local handoff stated `scripts/vbt_us_td9_all_assets.py` was unfinished. Current local output shows a completed run in:

- `outputs/us_td9_all_assets/td9_all_assets_20260418_095256/`

So new Codex should not assume TD9 all-assets is still incomplete without first reading that output and the script.

## Current State / 当前状态

Current visible task state:

- Enhanced factor strategy library exists and is exported.
- VectorBT backtest engine has a reusable enhanced strategy entry point.
- Qlib bridge exists and can generate workflow configs without requiring Qlib installed.
- Qlib ready YAML template exists.
- Dual-framework strategy manifest exists.
- Documentation exists for dual-framework reuse.
- Tests pass.

Current local project state beyond visible task:

- Older and broader US leveraged ETF / TD9 outputs exist under `outputs/`.
- A previous handoff exists but contains some stale "TD9 unfinished" information that has since been superseded by the completed TD9 run directory.

No background processes, long-running tasks, automations, or active shell sessions are known to be running for this current task.

## Known Issues / 已知问题

- `qlib` is not installed in the active Python environment. Actual Qlib workflow execution still requires installing/configuring `pyqlib` and a valid Qlib data bundle.
- Current Qlib bridge covers Qlib Alpha360 + LGBModel + TopkDropout workflow generation. It does not yet implement a custom Qlib handler for WorldQuant Alpha101 or GTJA Alpha191 feature tables.
- `docs/codex_user_switch_prompt_20260418.txt` and the embedded prompt in the older handoff show mojibake/encoding problems. Use this new handoff and prompt instead.
- `rg.exe` cannot be used in this Windows environment due to access denial; use PowerShell `Get-ChildItem` / `Select-String` or fix permissions.
- The project `pyproject.toml` says `requires-python >=3.9`, but some pre-existing code uses Python 3.10+ union type syntax. Current visible additions also use some modern typing in `src/qlib_ext/strategy_bridge.py` (`list[...]`, `tuple[...]`, and `str | Path`). Current environment is Python 3.11, so tests pass. If strict Python 3.9 support is required, audit and modernize/compat these type hints across the project.
- TD9 output top result `NVDA` has very low exposure and only 5 trades; although it scored #1, it may be too inactive. Treat it as a drawdown-protected tactical result, not necessarily a practical best strategy.
- `_VIX` result is an index-like series and may not be directly tradable. Do not present it as an executable strategy without mapping to an instrument.
- QLD/TQQQ still have large full max drawdowns in TD9/all-assets output:
  - QLD full maxDD about -41.93%.
  - TQQQ full maxDD about -52.27%.
- The current enhanced strategy library has tests on synthetic data, but no real-data backtest was run in this visible task after landing the library. Run an actual `run_enhanced_factor_strategy` smoke/backtest before relying on production results.

## Next Steps / 下一步

Recommended order for new Codex:

1. Read this handoff file.
2. Read:
   - `docs/dual_framework_strategy_reuse.md`
   - `src/strategies/factor_enhanced.py`
   - `src/backtest/vbt_engine.py`
   - `src/qlib_ext/strategy_bridge.py`
   - `configs/research/dual_framework_strategy_pool.yaml`
   - `configs/qlib/dual_framework_alpha360_lgb_topk50_drop5.yaml`
3. Run validation:
   ```powershell
   $env:PYTHONPATH='.'
   pytest
   python -m compileall -q src tests scripts\export_qlib_workflow_config.py
   ```
4. If the user wants Qlib execution:
   - Install/configure `pyqlib`.
   - Verify `data/qlib_bin` contains a valid Qlib data bundle.
   - Export or edit workflow config:
     ```powershell
     $env:PYTHONPATH='.'
     python scripts\export_qlib_workflow_config.py --strategy topk_dropout_50_5 --output configs/qlib/generated_topk50.yaml
     ```
   - Then run through Qlib's workflow command/API in an environment with Qlib installed.
5. If the user wants real vectorbt validation of the new strategy library:
   - Pick a known universe and factors, e.g. Qlib Alpha360 local factor names and WQ/GTJA adapters.
   - Use `VBTBacktestEngine.run_enhanced_factor_strategy`.
   - Compare:
     - quantile long-only,
     - quantile long/short,
     - alphalens continuous weights,
     - topk_dropout,
     - IC weighted topk_dropout,
     - overlays / vol target.
6. For TD9 context:
   - Read `outputs/us_td9_all_assets/td9_all_assets_20260418_095256/report.md`.
   - Avoid rerunning unless data updates or the user asks; it already completed.
   - If rerunning, preserve run directory/checkpoint pattern.

## Recovery Instructions / 新 Codex 如何恢复继续

Start from project root:

```powershell
cd E:\dzhwork\quant\quant_lab
$env:PYTHONPATH='.'
```

Read files:

```powershell
Get-Content docs\codex_handoff_strategy_factor_dual_framework_20260418_173351.md
Get-Content docs\dual_framework_strategy_reuse.md
Get-Content src\strategies\factor_enhanced.py
Get-Content src\qlib_ext\strategy_bridge.py
Get-Content src\backtest\vbt_engine.py
Get-Content configs\research\dual_framework_strategy_pool.yaml
```

Validate:

```powershell
$env:PYTHONPATH='.'
pytest
python -m compileall -q src tests scripts\export_qlib_workflow_config.py
```

Use vectorbt enhanced strategy:

```python
from src.backtest.vbt_engine import VBTBacktestEngine

engine = VBTBacktestEngine(data_dir="data/external/legacy_quant/NSDQStock/19800101_20260404", market="us")
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

- Do not re-implement TopKDropout/quantile/IC weighting from scratch; use `src/strategies/factor_enhanced.py`.
- Do not create another detached Qlib config generator; use `src/qlib_ext/strategy_bridge.py`.
- Do not assume TD9 all-assets is unfinished; verify `outputs/us_td9_all_assets/td9_all_assets_20260418_095256/`.
- Do not use `rg` unless permission issue is fixed.

## Full Prompt For New Codex / 给新 Codex 的完整提示词

```text
You are taking over work in the Windows/PowerShell workspace:

E:\dzhwork\quant\quant_lab

First read the local handoff file:

docs/codex_handoff_strategy_factor_dual_framework_20260418_173351.md

Context:

The user owns a quant analysis framework based on qlib + vectorbt. They said the project has 4000+ factors but the strategies were too weak, so factor effects were not being expressed. They asked Codex to seriously search for better strategies and land reusable strategy code into the framework. They later corrected the requirement: the strategy library and factor library must be reusable in the qlib + vectorbt dual framework, not only in vectorbt.

Important current source files:

- src/strategies/factor_enhanced.py
- src/backtest/portfolio_factory.py
- src/backtest/signal_factory.py
- src/backtest/vbt_engine.py
- src/strategies/__init__.py
- src/qlib_ext/strategy_bridge.py
- src/qlib_ext/__init__.py
- scripts/export_qlib_workflow_config.py
- configs/research/dual_framework_strategy_pool.yaml
- configs/qlib/dual_framework_alpha360_lgb_topk50_drop5.yaml
- docs/dual_framework_strategy_reuse.md
- tests/test_factor_enhanced_strategies.py
- tests/test_qlib_strategy_bridge.py

What is already done:

- Enhanced factor strategy library is implemented.
- VectorBT enhanced backtest entry point exists: VBTBacktestEngine.run_enhanced_factor_strategy(...).
- Weight-matrix portfolio simulation exists: PortfolioFactory.run_weighted_portfolio_simple(...).
- Reusable signal templates exist for time-series momentum, dual momentum, Donchian/Turtle, z-score mean reversion, MACD, and Dual Thrust.
- Qlib bridge exists and can generate Qlib workflow dict/YAML without importing qlib.
- Shared strategy specs include topk_dropout_50_5, topk_dropout_100_10, quantile_20_long_only, quantile_20_long_short, and ic_weighted_topk_dropout_50_5.
- Tests pass in current environment with PYTHONPATH set.

Validation commands:

$env:PYTHONPATH='.'
pytest
python -m compileall -q src tests scripts\export_qlib_workflow_config.py

Known constraints/issues:

- qlib is not installed in the active environment. Qlib workflow generation is tested, but actual Qlib execution still requires installing/configuring pyqlib and a valid data/qlib_bin bundle.
- rg.exe is denied by OS; use PowerShell Get-ChildItem and Select-String unless fixed.
- pytest without PYTHONPATH=. fails with ModuleNotFoundError: No module named 'src'.
- Some older docs/prompt files have mojibake; use this handoff and docs/dual_framework_strategy_reuse.md as the clean recovery context.

Important existing outputs:

- outputs/us_td9_all_assets/td9_all_assets_20260418_095256/report.md
- outputs/us_td9_all_assets/td9_all_assets_20260418_095256/best_config.json
- outputs/us_td9_all_assets/td9_all_assets_20260418_095256/top5_overall.csv
- outputs/us_td9_all_assets/td9_all_assets_20260418_095256/qld_tqqq_best.csv

TD9 current local output says QLD best is qqq_ema3_120_b0.0025 and TQQQ best is qqq_ema3_40_b0.0050, but drawdowns remain large. Treat those as research outputs, not necessarily final production choices.

Next likely tasks:

1. If asked to continue strategy/factor integration, extend src/qlib_ext to support custom Qlib handlers/exported feature tables for WorldQuant Alpha101 and GTJA Alpha191, not only Alpha360.
2. If asked for real validation, run VBTBacktestEngine.run_enhanced_factor_strategy on a concrete universe/factor set and compare quantile, alphalens, topk_dropout, IC-weighted, overlay, and volatility-target variants.
3. If asked for Qlib run, first install/configure pyqlib and verify data/qlib_bin; then generate a config with scripts/export_qlib_workflow_config.py.
4. Do not redo the existing strategy library from scratch; build on the listed files.

Answer the user in Chinese unless they ask otherwise.
```
