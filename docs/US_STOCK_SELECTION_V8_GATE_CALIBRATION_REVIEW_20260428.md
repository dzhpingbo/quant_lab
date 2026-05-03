# US Stock Selection v8 Gate Calibration Review - 20260428_111439

Scope: v8 gate calibration review and v8.1 concentration-rule design only. This is not a new backtest, not v9, not Nasdaq100/S&P500 expansion, and not a 31b run.

Run directory: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260426_095958`

Single-year diagnostic directory: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v8_single_year_concentration_20260427_233246`

## 1. Background and purpose

The accepted v8 closeout remains `credible_but_execution_sensitive` with `allow_enter_v9=False`. The only major failed concentration gate is `single_year_share_lte_50=False`, with `single_year_share=0.5260274868858267`.

This review asks whether the existing gate is calibrated too tightly for the available sample, then proposes v8.1 concentration gates. It does not overwrite `v8_verdict.json`.

## 2. Current single_year_share code definition

The existing v8 code computes:

```python
denom = yearly["year_return"].abs().sum()
single_year_share = yearly["year_return"].abs().max() / denom
single_year_share_lte_50 = single_year_share <= 0.50
```

The numerator is the largest absolute calendar-year compounded return. The denominator is the sum of absolute calendar-year compounded returns. This is not NAV-dollar profit share and not positive-year-only contribution.

## 3. What the current failure means

- Current abs return share: `0.526027`
- Full-year-only abs return share: `0.529457`
- Positive-year return share: `0.529457`
- Annual NAV profit share max: `0.610305`
- Annual positive NAV profit share max: `0.619412`

The failed 50% gate means 2024's compounded return is slightly larger than 2025's under an absolute-return denominator. With only two complete high-return years plus one partial year, a 50% hard threshold almost requires the two full years to be exactly balanced.

## 4. Why 52.6% is not severe single-year monopoly

The 2024 gate share is 52.6%, while 2025 is 46.7%; the gap is about 5.85 percentage points. Leave-one-year-out diagnostics still pass the original minimum return and Calmar objectives:

- Minimum leave-one-year-out CAGR: `0.527392`
- Minimum leave-one-year-out Calmar: `1.617424`

That evidence argues against a severe one-year-only dependency. The original v8 gate failure remains valid, but it is better interpreted as a calibration warning than as proof of structural invalidity.

## 5. Why top-month sensitivity deserves more attention

- Top 1 positive month share: `0.168601`
- Top 3 positive months share: `0.389378`
- Top 5 positive months share: `0.541001`
- Remove top 3 months CAGR: `0.283153`
- Remove top 3 months Calmar: `0.789229`
- Remove top 5 months CAGR: `0.139524`
- Remove top 5 months Calmar: `0.493645`

The strategy survives removing the top one month, but becomes weaker after removing the top three and fails the 20% CAGR threshold after removing the top five. This points to month-cluster sensitivity as the more useful v8.1 diagnostic.

## 6. v8.1 recommended concentration gate scheme

Hard gates:

| gate_name | metric_value | proposed_threshold | pass_fail | severity | interpretation | recommended_action |
| --- | --- | --- | --- | --- | --- | --- |
| leave_one_year_out_min_cagr | 0.527392 | >= 0.2 | pass | pass | Worst CAGR after removing any calendar year from the existing NAV curve. | Hard-pass only if the strategy still clears the minimum CAGR target without each year. |
| leave_one_year_out_min_calmar | 1.617424 | >= 1.0 | pass | pass | Worst Calmar after removing any calendar year from the existing NAV curve. | Hard-pass only if risk-adjusted performance survives leave-one-year-out diagnostics. |
| top1_positive_month_share | 0.168601 | <= 0.25 | pass | pass | Largest positive month share of total positive NAV profit. | Hard-fail if one month alone carries too much of the profit. |
| top3_positive_month_share | 0.389378 | <= 0.5 | pass | pass | Top three positive months' share of total positive NAV profit. | Hard-fail if a small cluster of months carries most of the profit. |
| max_ticker_abs_share | 0.223603 | <= 0.3 | pass | pass | Largest ticker absolute return contribution share. | Hard-fail if a single ticker dominates realized contribution. |
| max_ticker_month_weight | 0.200000 | <= 0.3 | pass | pass | Largest single ticker monthly weight. | Hard-fail if a ticker can exceed acceptable position concentration. |


Observation gates:

| gate_name | metric_value | proposed_threshold | pass_fail | severity | interpretation | recommended_action |
| --- | --- | --- | --- | --- | --- | --- |
| current_abs_return_share | 0.526027 | <= 0.55 | pass | pass_observe | Existing v8 measure recalibrated as an observation gate for short samples. | Do not hard-fail at 0.50 when only two full years dominate; monitor above 0.55. |
| full_year_only_abs_return_share | 0.529457 | <= 0.55 | pass | pass_observe | Same annual-return concentration but excluding partial years. | Use alongside current_abs_return_share to avoid partial-year denominator noise. |
| positive_year_return_share | 0.529457 | <= 0.55 | pass | pass_observe | Positive annual return concentration among profitable years. | Flag if one profitable full year dominates positive annual return. |
| top5_positive_month_share | 0.541001 | <= 0.6 | pass | pass_observe | Top five positive months' share of total positive NAV profit. | Observation flag rather than hard reject for short samples. |
| rolling_12m_min_return | 0.179015 | >= 0.0 | pass | pass_observe | Weakest rolling 12-month total return. | Monitor regime weakness; negative 12-month windows need special review. |
| rolling_12m_min_calmar_like | 0.636101 | >= 0.5 | pass | pass_observe | Weakest rolling 12-month Calmar-like metric. | Observation gate for regime stability. |
| rolling_12m_return_gap | 1.193960 | <= 1.5 | pass | pass_observe | Gap between strongest and weakest rolling 12-month return. | Large gaps feed the concentration penalty rather than immediate hard failure. |
| dominant_year_unique_ticker_count | 20.000000 | >= 10 | pass | pass_observe | Number of tickers held in the dominant gate year. | Observation pass indicates the dominant year was not just one or two names. |
| dominant_year_avg_holding_count | 5.000000 | >= 3 | pass | pass_observe | Average holding count in the dominant gate year. | Observation pass confirms portfolio breadth at rebalance level. |
| top_ticker_exposure_count_share | 0.100000 | <= 0.25 | pass | pass_observe | Most frequent ticker's share of active holding appearances. | Monitor repeated exposure concentration even if weights are capped. |


Diagnostic-only checks:

| gate_name | metric_value | proposed_threshold | pass_fail | severity | interpretation | recommended_action |
| --- | --- | --- | --- | --- | --- | --- |
| annual_profit_share | 0.610305 | <= 0.65 | pass | pass_observe | Largest absolute NAV profit share by year. | Prefer this as explanatory context, not a hard gate, because compounding shifts later-year NAV dollars. |
| annual_profit_positive_share | 0.619412 | <= 0.65 | pass | pass_observe | Largest positive NAV profit share by year. | Monitor but do not hard-fail without longer sample support. |
| remove_top1_month_cagr | 0.543428 | >= 0.2 | pass | pass_observe | CAGR after removing the top 1 positive month(s) from the NAV curve. | Use as diagnostic fragility evidence; top3/top5 failures imply month-cluster sensitivity. |
| remove_top1_month_calmar | 1.655280 | >= 1.0 | pass | pass_observe | Calmar after removing the top 1 positive month(s) from the NAV curve. | Use as diagnostic fragility evidence; do not confuse with a true strategy rerun. |
| remove_top3_month_cagr | 0.283153 | >= 0.2 | pass | pass_observe | CAGR after removing the top 3 positive month(s) from the NAV curve. | Use as diagnostic fragility evidence; top3/top5 failures imply month-cluster sensitivity. |
| remove_top3_month_calmar | 0.789229 | >= 1.0 | fail | moderate | Calmar after removing the top 3 positive month(s) from the NAV curve. | Use as diagnostic fragility evidence; do not confuse with a true strategy rerun. |
| remove_top5_month_cagr | 0.139524 | >= 0.2 | fail | minor | CAGR after removing the top 5 positive month(s) from the NAV curve. | Use as diagnostic fragility evidence; top3/top5 failures imply month-cluster sensitivity. |
| remove_top5_month_calmar | 0.493645 | >= 1.0 | fail | major | Calmar after removing the top 5 positive month(s) from the NAV curve. | Use as diagnostic fragility evidence; do not confuse with a true strategy rerun. |


Proposed penalty score formula for v8.1/v9 ranking:

```text
concentration_penalty_score =
  0.25 * clip((current_abs_return_share - 0.50) / 0.15, 0, 1)
+ 0.25 * clip((top3_positive_month_share - 0.40) / 0.25, 0, 1)
+ 0.20 * clip((max_ticker_abs_share - 0.25) / 0.15, 0, 1)
+ 0.20 * clip((1.00 - rolling_12m_min_calmar_like) / 1.00, 0, 1)
+ 0.10 * clip((top_ticker_exposure_count_share - 0.20) / 0.20, 0, 1)
```

Penalty components from current v8:

```json
{
  "year_return_concentration_penalty": 0.17351657923886007,
  "top_month_concentration_penalty": 0.0,
  "ticker_exposure_penalty": 0.0,
  "rolling_12m_instability_penalty": 0.3638987120298204,
  "high_beta_asset_penalty": 0.0
}
```

## 7. v8.1 simulated verdict

```json
{
  "original_v8_verdict": "credible_but_execution_sensitive",
  "original_allow_enter_v9": false,
  "simulated_v8_1_concentration_verdict": "concentration_gate_passed",
  "simulated_allow_enter_v9": false,
  "hard_gates_passed": [
    "leave_one_year_out_min_cagr",
    "leave_one_year_out_min_calmar",
    "top1_positive_month_share",
    "top3_positive_month_share",
    "max_ticker_abs_share",
    "max_ticker_month_weight"
  ],
  "hard_gates_failed": [],
  "observation_flags": [],
  "concentration_penalty_score": 0.1161588872156791,
  "penalty_components": {
    "year_return_concentration_penalty": 0.17351657923886007,
    "top_month_concentration_penalty": 0.0,
    "ticker_exposure_penalty": 0.0,
    "rolling_12m_instability_penalty": 0.3638987120298204,
    "high_beta_asset_penalty": 0.0
  },
  "final_interpretation": "v8 would pass the proposed hard concentration gates, but should remain blocked from v9 because this is only a diagnostic calibration review and the original v8 final verdict is not being rewritten."
}
```

The current v8 would pass the proposed v8.1 hard concentration gates, but observation and diagnostic checks still recommend caution. This simulation must not be read as v9 approval.

## 8. Recommended sequencing

Do v8.1 gate-aware improvement before any v9 discussion. In v8.1, use the stricter hard robustness gates plus observation flags and penalty scoring. Do not directly enter v9 from this calibration review.

## 9. 31b challenger positioning

31b remains an optional challenger-model supplement. It can improve model stability evidence, but it cannot directly fix annual return concentration, top-month contribution concentration, or ticker exposure concentration.
