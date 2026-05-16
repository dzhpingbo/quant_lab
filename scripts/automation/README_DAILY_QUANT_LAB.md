# Daily Quant Lab Automation

This folder contains the local daily runner for quant_lab frozen research jobs.
It now produces three classes of daily output: frozen replay status, latest
signals, and a human-review trading packet with target holdings and order
tickets.

## Python Environment

The automation is pinned to the `aimodel` conda environment and does not depend
on the current shell being activated:

```text
C:\Users\Administrator\.conda\envs\aimodel\python.exe
```

`daily_quant_lab_config.yaml` uses this absolute path as `python_executable`.
The PowerShell wrapper starts the runner with the same path. If this Python path
is missing or dependencies cannot import, the runner fails during preflight.

These are local production paths for this machine. Change them before using the
automation on another machine.

## Jobs

The daily run is now a multi-job runner. Each enabled job has its own directory,
stdout/stderr logs, summary, and artifacts manifest.

1. `us_v82`
   - Refreshes/checks the v8.2 provider.
   - Runs the approved v8.2 frozen formal audit:
     `scripts/us_stock_selection/51_run_v82_frozen_formal_audit.py --skip-bridge`.
   - Runs `scripts/automation/run_us_v82_frozen_live_daily.py` to check whether
     a current-month frozen live target exists for the provider latest date.
   - Current strategy id: `top5_ytdcap80p_derisk100p`.
   - Produces an order packet only from live target holdings. Formal audit
     holdings are historical evidence, not automatically executable live
     targets.

2. `qld_tqqq`
   - Runs fixed QLD/TQQQ frozen replay only.
   - QLD: `core_ma100_turn_b6_t7_trim70` + `gate_adaptive_vt20_tr12_k12`.
   - TQQQ: `core_ma100_turn_b6_t6_trim70` + `gate_loose_vt32_tr20_k18`.
   - It refreshes data and replays these fixed parameters; it does not re-rank
     candidates or call `qldtqqq_vix_strategy_comparison.py`.
   - Produces separate QLD and TQQQ sleeve-level target holdings and order
     tickets.

3. `588200`
   - Runs fixed 588200 frozen replay/latest signal only.
   - Strategy id:
     `factor_overlay__combo2__alpha_intraday_strength_60__alpha_td9_sell_pressure_4_9__mom60__vol20__vp95__fb55__fs45`.
   - It refreshes public daily data and replays the fixed strategy; it does not
     run `longrun_588200_factor_strategy_search.py`.
   - Produces a 588200 sleeve-level target holding and order ticket.

## What It Does Not Do

- No live trading.
- No broker/API connection.
- No broker account read.
- No automatic order placement.
- No automatic commit or push.
- No strategy search.
- No daily re-optimization or daily best selection.
- No v10.
- No pool expansion.
- No replacement of the v8.2 frozen mainline with formal v9, MVE2, P6, or any
  failed/high-risk branch.
- No deletion, restore, cleanup, or staging of dirty hold artifacts.

## Output Layout

Each invocation creates:

```text
outputs/daily_quant_lab_runs/YYYYMMDD_HHMMSS/
  run_summary.md
  run_summary.json
  git_status_before.txt
  git_status_after.txt
  environment.txt
  artifacts_manifest.json
  DAILY_QUANT_TRADING_SUMMARY.md
  all_target_holdings.csv
  all_order_tickets.csv
  all_risk_status.json
  cross_sleeve_symbol_exposure.csv
  cross_sleeve_symbol_conflicts.csv
  cross_sleeve_validation_summary.json
  cross_sleeve_validation_summary.md
  actionable_digest.json
  run_result.zip

  job_us_v82/
    job_summary.md
    job_summary.json
    data_stdout.log
    data_stderr.log
    stdout.log
    stderr.log
    live_signal_stdout.log
    live_signal_stderr.log
    artifacts_manifest.json
    us_v82_live_target_holdings.csv
    us_v82_live_target_holdings.json
    us_v82_live_signal_summary.md
    us_v82_live_manifest.json
    DAILY_TRADING_PACKET.md
    latest_target_holdings.csv
    order_ticket.csv
    risk_status.json
    trading_packet_manifest.json

  job_qld_tqqq/
    job_summary.md
    job_summary.json
    stdout.log
    stderr.log
    qldtqqq_job_summary.json
    qldtqqq_job_summary.md
    qldtqqq_metrics.csv
    qldtqqq_latest_signal.csv
    qldtqqq_artifacts_manifest.json
    DAILY_TRADING_PACKET.md
    latest_target_holdings.csv
    order_ticket.csv
    risk_status.json
    trading_packet_manifest.json

  job_588200/
    job_summary.md
    job_summary.json
    stdout.log
    stderr.log
    588200_job_summary.json
    588200_job_summary.md
    588200_metrics.csv
    588200_latest_signal.csv
    588200_data_status.csv
    588200_tradeable_price.csv
    588200_tradeable_price.json
    588200_artifacts_manifest.json
    DAILY_TRADING_PACKET.md
    latest_target_holdings.csv
    order_ticket.csv
    risk_status.json
    trading_packet_manifest.json
```

The top-level `run_summary.md` and `run_summary.json` summarize every enabled
job with status, data status, strategy status, trading packet status, and
extracted metrics. The daily manual execution files are:

- `DAILY_QUANT_TRADING_SUMMARY.md`
- `all_target_holdings.csv`
- `all_order_tickets.csv`
- `cross_sleeve_symbol_exposure.csv`
- `cross_sleeve_symbol_conflicts.csv`
- `cross_sleeve_validation_summary.md`
- Per-job `DAILY_TRADING_PACKET.md`
- Per-job `order_ticket.csv`

An enabled job is not considered complete unless it has replay output, latest
signal context, target holdings, order ticket, and risk status.

## Current Positions

The automation never reads broker accounts. To generate differential order
tickets, maintain these optional local CSV files:

```text
inputs/current_positions_us_v82.csv
inputs/current_positions_qldtqqq.csv
inputs/current_positions_588200.csv
```

Template files are provided and contain zeros only:

```text
inputs/current_positions_us_v82.template.csv
inputs/current_positions_qldtqqq.template.csv
inputs/current_positions_588200.template.csv
```

Copy a template to the matching `current_positions_*.csv` file and then fill in
real current shares before treating any ticket as a formal manual-order input.
The template files themselves are not live positions.

You can refresh the templates from the latest generated target holdings without
creating real position files:

```powershell
C:\Users\Administrator\.conda\envs\aimodel\python.exe scripts/automation/init_current_positions_templates.py --latest
```

Required columns:

```text
ticker,current_shares
```

If a file is missing, the packet may still show theoretical target holdings, but
order rows are `EXAMPLE_ONLY`, `formal_trade_allowed=false`, and at least
`NEEDS_POSITION_FILE`. If a file exists but has the wrong columns, trading
packet generation fails for that job. After manual fills, update the matching
current positions file yourself.

## Account Notional

The default account sizes in `daily_quant_lab_config.yaml` are examples used to
convert target weights into target shares:

- `trading_packet.sleeves.us_v82.account_notional_usd`
- `trading_packet.sleeves.qld.account_notional_usd`
- `trading_packet.sleeves.tqqq.account_notional_usd`
- `trading_packet.sleeves.etf_588200.account_notional_cny`

Change these values before using the order tickets for manual execution review.
588200 uses `lot_size: 100`; US sleeves use `lot_size: 1`.

## Sleeve Accounting

A sleeve is a strategy/accounting bucket. The daily runner currently has these
sleeves:

- `us_v82`: US stock v8.2 frozen top5 portfolio.
- `qld`: QLD fixed frozen replay.
- `tqqq`: TQQQ fixed frozen replay.
- `etf_588200`: 588200 fixed frozen replay/latest signal.

The default configuration is:

```yaml
trading_packet:
  sleeve_accounting_mode: separate_sleeves
```

`separate_sleeves` means each sleeve has its own notional and current-position
file. The same ticker can still appear in more than one sleeve. For example,
TQQQ can be a us_v82 live Top5 holding while the dedicated TQQQ sleeve is in a
cash/wait state. That is not a strategy error, but it is an execution risk.

The runner writes `cross_sleeve_symbol_exposure.csv`,
`cross_sleeve_symbol_conflicts.csv`, and
`cross_sleeve_validation_summary.md/json`. If these files show duplicate
tickers such as TQQQ, do not mechanically add, net, or offset orders. First
decide whether the sleeves are truly separately funded or whether one broker
account is being shared. If one account is shared, manually confirm net exposure
and order allocation. The system does not implement automatic consolidated
account netting.

`consolidated_account` is reserved for a future explicit netting workflow. It
currently still requires manual review and does not create automatic net
orders.

## Manual Dry Run

From the project root:

```powershell
C:\Users\Administrator\.conda\envs\aimodel\python.exe scripts/automation/daily_quant_lab_runner.py --dry-run
```

Dry-run one job:

```powershell
C:\Users\Administrator\.conda\envs\aimodel\python.exe scripts/automation/daily_quant_lab_runner.py --dry-run --job us_v82
C:\Users\Administrator\.conda\envs\aimodel\python.exe scripts/automation/daily_quant_lab_runner.py --dry-run --job qld_tqqq
C:\Users\Administrator\.conda\envs\aimodel\python.exe scripts/automation/daily_quant_lab_runner.py --dry-run --job 588200
```

Dry-run prints the commands and the trading packet files that would be
generated, but it does not create order tickets.

Validate the latest generated trading packet:

```powershell
C:\Users\Administrator\.conda\envs\aimodel\python.exe scripts/automation/validate_daily_trading_packet.py --latest --strict
```

The validator writes `validation_summary.md` and `validation_summary.json` into
the run directory.

## Manual Single-Job Runs

Run only QLD/TQQQ fixed replay:

```powershell
C:\Users\Administrator\.conda\envs\aimodel\python.exe scripts/automation/daily_quant_lab_runner.py --job qld_tqqq
```

Run only 588200 fixed replay:

```powershell
C:\Users\Administrator\.conda\envs\aimodel\python.exe scripts/automation/daily_quant_lab_runner.py --job 588200
```

Run only the existing v8.2 job:

```powershell
C:\Users\Administrator\.conda\envs\aimodel\python.exe scripts/automation/daily_quant_lab_runner.py --job us_v82
```

`--skip-strategy` skips replay/strategy commands. For `us_v82`, the provider
refresh/check can still run when `--skip-update` is not supplied.

## Manual Execution Notes

- The system does not trade, connect to brokers, or submit orders.
- `order_ticket.csv` is only a manual review aid.
- `order_ticket.csv` is not the same thing as a directly executable order.
- Only rows with `formal_trade_allowed=true` and
  `order_intent=FORMAL_MANUAL_ORDER` may enter the manual order review workflow.
- Rows with `EXAMPLE_ONLY` or `BLOCKED` must not be submitted.
- `reference_price` is not a guaranteed execution price.
- `adj_close`, `qfq`, or other adjusted prices cannot be used directly as
  broker order prices.
- `588200` must use `588200_tradeable_price.csv/json` with
  `price_is_tradeable=true`; otherwise the row remains `NEEDS_MANUAL_PRICE` or
  `BLOCKED`.
- `us_v82` formal audit holdings are not live target holdings. The daily packet
  must use `us_v82_live_target_holdings.csv/json`; if no current-month live
  target is available, `us_v82` remains `BLOCKED_STALE_SIGNAL`.
- `run_us_v82_frozen_live_daily.py` builds the current-month live target by
  reusing the frozen v8.1 Alpha360 LGBModel monthly score/rank path and the
  v8.2 `ytdcap80p_derisk100p` overlay. It does not retrain a new strategy,
  search parameters, expand the pool, or change the formal audit conclusion.
- If `live_formal_consistency_check` is not `PASS`, the packet must not create
  formal manual orders from the us_v82 live target.
- If a packet has any `blocking_warning`, do not place an order until the issue
  is manually resolved.
- If `us_v82` has a `target_holding_date` that differs from
  `reference_price_date`, the packet must prove the holding is still effective;
  otherwise it is `BLOCKED_STALE_SIGNAL`.
- If QLD/TQQQ target cash but the current positions file is missing, do not
  interpret `current_shares=0` as proof that no sell is needed.
- A-share EOD completeness is mandatory. If local Asia/Shanghai time is before
  15:30, today's A-share bar is rejected. From 15:30 to 16:30, today's bar is
  accepted only with an explicit final-EOD source flag; otherwise the runner
  falls back to the previous complete trading day. `DAILY_ACTION_GUIDE.md`
  must show `data_completeness` as `EOD_CONFIRMED`, `INTRADAY_REJECTED`, or
  `UNKNOWN_FALLBACK_PREVIOUS_EOD`.
- US EOD completeness is mandatory. The 06:30 Asia/Shanghai run can use the
  prior completed US trading day; before the configured post-close buffer, the
  runner must not accept a same-day or otherwise unconfirmed US bar.
- Confirm ticker, market, price, company actions, dividends, halts, liquidity,
  and market open status before placing any manual order.
- Confirm the same order was not already entered elsewhere.
- After fills, update the relevant `inputs/current_positions_*.csv` file.

## Trading Packet Safety States

`execution_readiness` can be:

- `READY_FOR_MANUAL_REVIEW`: all required inputs are present and the row can
  enter manual review. It still does not trade automatically.
- `NEEDS_POSITION_FILE`: the current positions file is missing, so the row is
  example-only.
- `NEEDS_MANUAL_PRICE`: the reference price is adjusted, qfq, or otherwise not
  a verified raw tradable close.
- `BLOCKED_STALE_SIGNAL`: the signal/holding effective date cannot be proven
  current for the reference price date.
- `BLOCKED_MISSING_PRICE`: no usable reference price exists.
- `BLOCKED_UNKNOWN_ACTION`: the strategy action could not be mapped safely.
- `NO_BUYING_POWER`: the strategy wants to buy/increase, but the sleeve has no
  available USD cash. Do not use CNY cash for USD sleeves.
- `NEEDS_MANUAL_REVIEW`: summary status used when any warning or non-ready row
  exists.

`order_intent` can be:

- `FORMAL_MANUAL_ORDER`: eligible for manual review only when
  `formal_trade_allowed=true`.
- `EXAMPLE_ONLY`: theoretical order math, usually because positions are
  missing.
- `BLOCKED`: do not place the order until the blocker is resolved.
- `NO_ACTION`: no manual order is implied.

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

For a scheduled dry run, add `-DryRun`.

## Failure Triage

1. Open `run_summary.md`.
2. Open the failed job's `job_summary.md`.
3. Check the job `stdout.log` and `stderr.log`.
4. For `us_v82`, check `refresh_v82_provider_safe.md` and provider check JSON.
5. For `qld_tqqq`, check `qldtqqq_job_summary.md`, `qldtqqq_metrics.csv`, and
   `latest_data_status.csv`.
6. For `588200`, check `588200_job_summary.md`, `588200_data_status.csv`, and
   `588200_metrics.csv`.
7. Compare `git_status_before.txt` and `git_status_after.txt`.
8. If the replay succeeded but the total run failed, check whether the trading
   packet files or order tickets are missing.

Any enabled job failure makes the total run status `FAILED`.
