# Reviewer Notes

## 最新结果摘要

- Latest run: `run_20260502_222407`
- Run dir: `outputs/us_stock_selection/run_20260502_222407`
- Stage: `v9_growth_pool_pre_research`
- Classification: `not_v10_ready_growth_pool_sensitive`
- `allow_enter_v10`: `false`
- Frozen mainline: `Alpha360 + LGBModel + label_5d + top5_ytdcap80p_derisk100p`
- Execution assumptions: `T+1`, cost/slippage `5bps + 5bps`, max single weight `20%`, YTD cap `80%`, derisk `100%`

Core metrics from the packet:

| Universe | CAGR | Calmar | MaxDD | Cost50 T+1 CAGR | Gate |
| --- | ---: | ---: | ---: | ---: | --- |
| Pool A reproduction | 0.642126 | 1.633969 | -0.392985 | 0.540613 | false |
| Pool A + small growth | 0.072584 | 0.199302 | -0.364192 | 0.039016 | false |
| Small growth only | -0.021140 | -0.048876 | -0.432523 | -0.047269 | false |
| Pool A + small growth ex extreme-vol | 0.116580 | 0.321321 | -0.362814 | 0.081103 | false |

The small growth expansion materially degraded the Pool A reproduction. The latest packet correctly says v10 is not allowed.

## 可信点

- The scope explicitly forbids Nasdaq100/S&P500/full-market expansion, strategy search, and trading claims.
- The reported classification is conservative and consistent with the failed v9 gate.
- The report includes adverse controls: small-growth-only, top10 control, ex-extreme-vol variant, remove-top-year, remove-top-ticker, and cost50 T+1 columns.
- Concentration is not hidden: top ticker shares and single-year shares are reported.
- Excluded ticker list is explicit: `PLTR, SNOW, APP, PATH, U, S, AFRM, COIN, SQ, ABNB, DASH, RBLX, ARM`.

## 风险点

- Pool A reproduction is unusually strong: `64.21%` CAGR and `1.63` Calmar after costs remain high. This must be treated as an audit trigger, not as approval to expand.
- Bridge `small_tables/benchmark.csv` is `not_found`; benchmark evidence against `QQQ/QLD/TQQQ/SPY/Pool A equal-weight` is not independently visible in the packet.
- Bridge `small_tables/stress_test.csv` is `not_found`; cost/stress details are incomplete even though cost50 columns are present.
- The packet does not fully prove score provenance, model training windows, or that v9 ranking scores were generated without training on the evaluated period.
- The packet does not fully prove that `label_5d` is excluded from features and that Alpha360 features are lag-safe at each rebalance.
- The YTD cap and derisk trigger need timestamp audit: trigger calculation must use only information available before the trade effective date.
- Yearly return rows show zero returns for early years in expanded universes, which may indicate inactive-period padding or date-alignment differences. CAGR denominator and benchmark alignment need explicit audit.
- Universe definition may still carry survivorship or ex-post selection risk. Excluded tickers and effective universe construction need a separate audit table with data start/end dates.

## 是否满足 gate

No.

- v9 gate pass is `false` for every reported universe.
- `allow_enter_v10` is `false`.
- Growth-pool expansion did not improve robustness and sharply reduced CAGR/Calmar.
- Missing benchmark/stress bridge tables prevent complete independent review.
- No trading or tradable-candidate claim is allowed.

## 下一步理由

Decision: `CONTINUE`, but only for `v9_reverse_audit_no_expansion`.

The next Worker run must not optimize metrics, search strategies, expand universe, enter v10, or connect to any broker. It should perform a reverse audit of the latest v9 package, especially the abnormal Pool A reproduction, score/training provenance, feature/label leakage, T+1 execution semantics, date alignment, data quality, benchmark exports, and stress-test exports.

If the audit cannot prove score provenance and time-split correctness, the project should move to `NEED_HUMAN` before any further research.
