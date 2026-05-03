# US Stock Selection in quant_lab

本模块用于研究“当前数据、因子与策略能力范围内最容易被挖掘的美股标的/组合”，而不是简单寻找历史涨幅最大的股票。

## v4 Qlib-First Mode

当前 `configs/us_stock_selection/validation_config.yaml` 默认启用：

```yaml
research_mode: qlib_first_v4
```

一键运行：

```powershell
conda run -n aimodel python scripts/us_stock_selection/run_all_us_stock_selection.py --config configs/us_stock_selection/validation_config.yaml
```

单独阶段：

```powershell
conda run -n aimodel python scripts/us_stock_selection/11_qlib_env_check.py
conda run -n aimodel python scripts/us_stock_selection/12_prepare_qlib_us_data.py --config configs/us_stock_selection/validation_config.yaml
conda run -n aimodel python scripts/us_stock_selection/13_run_qlib_model_lab.py --config configs/us_stock_selection/validation_config.yaml
conda run -n aimodel python scripts/us_stock_selection/14_backtest_qlib_signals_vectorbt.py --config configs/us_stock_selection/validation_config.yaml
```

如果默认 `python` 指向 base 环境，请使用上面的 `conda run -n aimodel python ...`。

## v4 输出

每次运行输出到：

```text
outputs/us_stock_selection/run_YYYYMMDD_HHMMSS/
```

核心文件：

- `qlib_env/qlib_env_status.json`
- `qlib_data/qlib_data_status.json`
- `qlib_model_lab/model_runs.csv`
- `qlib_model_lab/metrics/signal_quality_by_model.csv`
- `qlib_signal_backtest/qlib_signal_strategy_results.csv`
- `qlib_signal_backtest/qlib_signal_portfolio_daily.csv`
- `qlib_walk_forward/qlib_walk_forward_detail.csv`
- `qlib_overfit/overfit_check_summary.csv`
- `benchmark/comparison_v4.csv`
- `ranking/final_ticker_ranking.csv`
- `reports/us_stock_selection_v4_qlib_first_report.md`
- `reports/us_stock_selection_v4_qlib_first_summary.xlsx`

打包文件：

```text
outputs/us_stock_selection/us_stock_selection_quant_lab_v4_qlib_first_YYYYMMDD_HHMMSS.zip
```

## Qlib Provider Note

`pyqlib` runtime 安装成功不等于 Qlib US provider 数据已经存在。若 `~/.qlib/qlib_data/us_data` 缺失，v4 会明确输出 `fallback_qlib_like_panel`，使用 quant_lab 本地 OHLCV/因子缓存跑横截面模型，不会假装执行了 true Qlib provider 训练。

## v5 True Qlib Provider + Audit

v5 adds a true-provider preparation lane and an audit lane for the v4 fallback winner.

Main command:

```powershell
conda run -n aimodel python scripts/us_stock_selection/19_run_v5_true_qlib_audit.py --config configs/us_stock_selection/validation_config.yaml --max-true-model-runs 12 --true-feature-sets Alpha158,Alpha360,Alpha158_custom --true-models Ridge,LightGBM --true-labels forward_return_5d,forward_return_20d
```

Optional stages:

```powershell
conda run -n aimodel python scripts/us_stock_selection/15_download_true_qlib_us_data.py --execute
conda run -n aimodel python scripts/us_stock_selection/16_convert_local_yfinance_to_qlib_bin.py --run-dir outputs/us_stock_selection/run_YYYYMMDD_HHMMSS
conda run -n aimodel python scripts/us_stock_selection/17_run_true_qlib_provider_lab.py --run-dir outputs/us_stock_selection/run_YYYYMMDD_HHMMSS --max-runs 12
conda run -n aimodel python scripts/us_stock_selection/18_audit_v4_best_strategy.py --run-dir outputs/us_stock_selection/run_YYYYMMDD_HHMMSS --v4-run-dir outputs/us_stock_selection/run_20260425_114504
```

Key v5 outputs:

- `qlib_data_true_provider/qlib_provider_health_check.json`
- `qlib_true_provider_lab/true_provider_backtest_results.csv`
- `v5_audit/leakage_check.json`
- `v5_audit/return_attribution.csv`
- `v5_walk_forward/wf_summary.csv`
- `v5_stress_test/*.csv`
- `reports/us_stock_selection_v5_true_qlib_and_audit_report.md`
- `reports/us_stock_selection_v5_summary.xlsx`

Important limitation: the downloaded pyqlib US provider sample used in v5 is readable but ends at 2020-11-10. It is a true-provider sanity check, not a direct replacement for the v4 2022-2026 fallback test.

## v6 Local Qlib Bin Provider + Native Workflow

v6 builds a local Qlib bin provider from quant_lab US OHLCV files, then runs Qlib native Alpha158/Alpha360 Handler workflows and exports signals to vectorbt-style robust Top3/Top5 portfolio validation.

Main command:

```powershell
conda run -n aimodel python scripts/us_stock_selection/24_run_v6_local_qlib_provider.py --config configs/us_stock_selection/validation_config.yaml --max-workflow-runs 12 --feature-sets Alpha158,Alpha360 --models LGBModel,Ridge,ElasticNet --labels label_5d,label_20d
```

Stage commands:

```powershell
conda run -n aimodel python scripts/us_stock_selection/20_clone_qlib_source.py
conda run -n aimodel python scripts/us_stock_selection/21_build_local_qlib_provider.py --config configs/us_stock_selection/validation_config.yaml
conda run -n aimodel python scripts/us_stock_selection/22_run_local_qlib_workflow.py --max-runs 12
conda run -n aimodel python scripts/us_stock_selection/23_backtest_robust_portfolios.py
```

Key v6 outputs:

- `qlib_source/qlib_source_status.json`
- `qlib_local_provider/provider_health_check.json`
- `qlib_local_provider/alpha_handler_check.json`
- `qlib_workflow/model_runs.csv`
- `qlib_workflow/signal_quality.csv`
- `v6_portfolio_backtest/robust_portfolio_results.csv`
- `v6_walk_forward/wf_summary.csv`
- `v6_walk_forward/wf_strict_retrain_status.json`
- `v6_overfit/robustness_verdict.json`
- `reports/us_stock_selection_v6_local_qlib_workflow_report.md`
- `reports/us_stock_selection_v6_summary.xlsx`

Important limitation: strict Handler retrain walk-forward can be very slow on Windows. The v6 run records whether strict retraining completed or timed out; calendar-forward WF should be treated as weak evidence only.
