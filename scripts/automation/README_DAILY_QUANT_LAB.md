# Daily Quant Lab Automation

This folder adds a local daily runner for the quant_lab research project.

## Python Environment

The daily automation is pinned to the `aimodel` conda environment and does not depend on the current shell being activated:

```text
C:\Users\Administrator\.conda\envs\aimodel\python.exe
```

`daily_quant_lab_config.yaml` uses this absolute path as `python_executable`, and the PowerShell wrapper starts the runner with the same path. If this Python path is missing or the environment cannot import required dependencies, the runner fails fast during preflight.

## What It Does

- Creates a timestamped run directory under `outputs/daily_quant_lab_runs/`.
- Records git status, environment details, preflight checks, command logs, data sanity checks, artifact manifests, summaries, and a zip package.
- Runs only configured commands.
- Runs a safe v8.2 provider refresh before the strategy step:
  `python scripts/automation/refresh_v82_provider_safe.py --provider-dir C:/Users/Administrator/.qlib/qlib_data/us_data_local_2026_v91_growth`
- Uses the current approved frozen strategy command when enabled:
  `python scripts/us_stock_selection/51_run_v82_frozen_formal_audit.py --skip-bridge`
- Performs directory-based data sanity checks after the provider refresh.

## What It Does Not Do

- No live trading.
- No broker/API connection.
- No automatic commit or push.
- No strategy search.
- No v10.
- No pool expansion.
- No replacement of the v8.2 frozen mainline with formal v9, MVE2, P6, or any failed/high-risk branch.
- No deletion, restore, cleanup, or staging of dirty hold artifacts.
- No data download beyond the v8.2 required ticker universe.
- No refresh of the provider's extra non-v8.2 tickers.

## Current Command Selection

The daily task has two layers:

1. v8.2 provider safe refresh plus post-refresh freshness / coverage check.
2. v8.2 frozen formal audit strategy run.

`data_update_command` is enabled as a safe refresh for the current frozen provider:

```text
C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026_v91_growth
```

The command writes `refresh_v82_provider_safe.json` and `refresh_v82_provider_safe.md` into each daily run directory. It refreshes only the 36 v8.2 required tickers derived from the frozen v8.1 score audit used by v8.2. It uses the existing project yfinance/Yahoo source with `auto_adjust=False`, computes the same adjusted OHLC factor policy (`Adj Close / Close`), preserves raw volume, writes a temp provider first, validates the temp provider, backs up the current provider, syncs only the required ticker bin files plus calendar/instruments, and then runs the provider check again.

This is not daily re-optimization. It does not recompute scores, change `strategy_id`, run formal v9, enter MVE/v10, search parameters, expand pools, trade, connect brokers, or commit/push.

Runtime dependency: the refresh command uses the already adopted project `yfinance` path, so `yfinance` and its runtime dependencies such as `websockets` and `protobuf` must be importable by the configured Python.

The standalone check remains available:

```powershell
python scripts/automation/daily_v82_provider_check.py --dry-run
```

`strategy_run_command` is enabled and points to the v8.2 frozen formal replay audit entrypoint. The upstream strategy script writes `RUN_SUMMARY.md` and `NEXT_STEPS.md` in the project root by design, so this runner records git status before and after every run.

## Manual Dry Run

From the project root:

```powershell
C:\Users\Administrator\.conda\envs\aimodel\python.exe scripts/automation/refresh_v82_provider_safe.py --dry-run
C:\Users\Administrator\.conda\envs\aimodel\python.exe scripts/automation/daily_quant_lab_runner.py --dry-run
```

PowerShell wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/automation/run_daily_quant_lab.ps1 -DryRun
```

## Manual Full Run

This runs the provider refresh, data sanity checks, and the frozen v8.2 strategy replay:

```powershell
C:\Users\Administrator\.conda\envs\aimodel\python.exe scripts/automation/daily_quant_lab_runner.py
```

To skip the strategy and only test wrapper/reporting behavior:

```powershell
C:\Users\Administrator\.conda\envs\aimodel\python.exe scripts/automation/daily_quant_lab_runner.py --skip-strategy
```

With `--skip-strategy`, the provider refresh still runs unless `--skip-update` is also supplied.

To override the per-step timeout:

```powershell
C:\Users\Administrator\.conda\envs\aimodel\python.exe scripts/automation/daily_quant_lab_runner.py --max-runtime-minutes 180
```

## Windows Task Scheduler

Create a daily task that runs:

```text
powershell.exe
```

Arguments:

```text
-NoProfile -ExecutionPolicy Bypass -File E:\dzhwork\quant\quant_lab\scripts\automation\run_daily_quant_lab.ps1
```

Set "Start in" to:

```text
E:\dzhwork\quant\quant_lab
```

For a scheduled dry run, add `-DryRun` to the arguments.

## Result Location

Each invocation creates:

```text
outputs/daily_quant_lab_runs/YYYYMMDD_HHMMSS/
```

Important files:

- `run_summary.md`
- `run_summary.json`
- `git_status_before.txt`
- `git_status_after.txt`
- `environment.txt`
- `data_update_stdout.log`
- `data_update_stderr.log`
- `refresh_v82_provider_safe.json`
- `refresh_v82_provider_safe.md`
- `v82_provider_check_after_refresh.json`
- `v82_provider_check_after_refresh.md`
- `strategy_stdout.log`
- `strategy_stderr.log`
- `data_sanity_summary.json`
- `artifacts_manifest.json`
- `run_result.zip`

The PowerShell wrapper also writes:

- `outputs/daily_quant_lab_runs/latest_scheduler_stdout.log`
- `outputs/daily_quant_lab_runs/latest_scheduler_stderr.log`

## Failure Triage

1. Open `run_summary.md` first.
2. Check `preflight.json` for missing Python, config, or imports.
3. Check `refresh_v82_provider_safe.md` and `refresh_v82_provider_safe.json` for provider refresh, backup, replacement, freshness, or ticker coverage failures.
4. Check `data_update_stderr.log` and `strategy_stderr.log`.
5. Check `data_sanity_summary.json` for stale or missing data directories.
6. Compare `git_status_before.txt` and `git_status_after.txt` to see what changed.
7. Open `artifacts_manifest.json` to find files generated during the run.

If no approved best strategy command is available in a future state, disable `strategy_run_command` and record the blocker in the config instead of inventing a strategy.
