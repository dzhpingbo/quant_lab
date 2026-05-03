# US Stock Selection v8.2 Stock-Selection Layer Diagnostic

## Scope

This is not v9. No universe expansion, no 31b, no model retraining, no new long full replay, and no continuation of v8.1 overlays.

## 1. File And Field Inventory

|   files_checked |   usable_for_attribution |   usable_for_ranking_diagnostic | score_rank_available   |
|----------------:|-------------------------:|--------------------------------:|:-----------------------|
|              31 |                        8 |                               8 | False                  |

Key finding: v8 persists selected holdings and selected scores, but does not persist full monthly candidate score/rank rows for unselected tradable names.

## 2. Stock-Selection Attribution

Monthly attribution sample:

| month   |   monthly_return |   monthly_profit |   selected_ticker_count |   high_beta_weight_share | top_weight_ticker   | best_contributing_ticker   | worst_contributing_ticker   |   turnover |
|:--------|-----------------:|-----------------:|------------------------:|-------------------------:|:--------------------|:---------------------------|:----------------------------|-----------:|
| 2024-01 |        0         |        0         |                       0 |                      0   |                     | AAPL                       | XLK                         |        0   |
| 2024-02 |        0.168394  |        0.168394  |                       5 |                      0.2 | AAPL                | MSTR                       | ORCL                        |        1   |
| 2024-03 |        0.148005  |        0.172928  |                       5 |                      0.2 | AVGO                | MSTR                       | AVGO                        |        1.6 |
| 2024-04 |       -0.144402  |       -0.19369   |                       5 |                      0.2 | AVGO                | AAPL                       | MSTR                        |        0   |
| 2024-05 |        0.149367  |        0.171418  |                       5 |                      0.2 | AMD                 | MSTR                       | AVGO                        |        1.2 |
| 2024-06 |        0.154517  |        0.203816  |                       5 |                      0.2 | CRM                 | CRWD                       | AMD                         |        1.6 |
| 2024-07 |       -0.144599  |       -0.220206  |                       5 |                      0.2 | CRM                 | CRM                        | CRWD                        |        0   |
| 2024-08 |       -0.0325222 |       -0.0423654 |                       5 |                      0.2 | AMD                 | CRWD                       | MU                          |        1.2 |
| 2024-09 |        0.0973145 |        0.122645  |                       5 |                      0.2 | AMD                 | MSTR                       | XLK                         |        0   |
| 2024-10 |        0.0215163 |        0.0297558 |                       5 |                      0   | AVGO                | NVDA                       | SNOW                        |        2   |
| 2024-11 |        0.347773  |        0.491298  |                       5 |                      0.2 | AMD                 | MSTR                       | AMD                         |        2   |
| 2024-12 |       -0.0381881 |       -0.07271   |                       5 |                      0.2 | AMD                 | TSLA                       | MSTR                        |        0   |
| 2025-01 |        0.0331642 |        0.0607332 |                       5 |                      0   | INTC                | SHOP                       | TSLA                        |        2   |
| 2025-02 |       -0.0411099 |       -0.0777807 |                       5 |                      0.2 | AAPL                | UBER                       | MSTR                        |        1.6 |
| 2025-03 |       -0.128318  |       -0.232799  |                       5 |                      0.2 | AVGO                | XLK                        | TQQQ                        |        2   |
| 2025-04 |        0.178816  |        0.282787  |                       5 |                      0.2 | MSTR                | PLTR                       | XLK                         |        2   |
| 2025-05 |        0.157961  |        0.294474  |                       5 |                      0.6 | MSTR                | TQQQ                       | MSTR                        |        1.2 |
| 2025-06 |        0.0924556 |        0.199584  |                       5 |                      0.6 | MSTR                | TQQQ                       | TSLA                        |        0   |
| 2025-07 |        0.0174601 |        0.0411759 |                       5 |                      0   | CRWD                | PLTR                       | MSTR                        |        2   |
| 2025-08 |        0.0399702 |        0.0959069 |                       5 |                      0   | ADBE                | MU                         | NET                         |        1.6 |
| 2025-09 |        0.102933  |        0.256857  |                       5 |                      0   | ADBE                | MU                         | CRM                         |        0   |
| 2025-10 |        0.218031  |        0.600071  |                       5 |                      0   | AMD                 | AMD                        | ADBE                        |        2   |
| 2025-11 |       -0.0668089 |       -0.223963  |                       5 |                      0   | ADBE                | AVGO                       | ORCL                        |        1.6 |
| 2025-12 |        0.0178634 |        0.0558825 |                       5 |                      0   | ADBE                | MU                         | AVGO                        |        0   |
| 2026-01 |        0.0483816 |        0.154057  |                       5 |                      0   | AMD                 | MU                         | CRM                         |        1.6 |
| 2026-02 |       -0.0599191 |       -0.200026  |                       5 |                      0   | AMD                 | MU                         | AMD                         |        0   |
| 2026-03 |       -0.0458722 |       -0.143958  |                       5 |                      0   | AMD                 | AMD                        | MU                          |        0   |
| 2026-04 |        0.0525444 |        0.157333  |                       5 |                      0.2 | AMD                 | INTC                       | MSTR                        |        0.8 |

Ticker attribution top rows:

| ticker   |   selected_month_count |   avg_weight |   max_weight |   approximate_return_contribution |   positive_month_count |   negative_month_count | high_beta_flag   |   concentration_share |
|:---------|-----------------------:|-------------:|-------------:|----------------------------------:|-----------------------:|-----------------------:|:-----------------|----------------------:|
| MSTR     |                      9 |          0.2 |          0.2 |                         0.454965  |                      5 |                      4 | True             |             0.165248  |
| PLTR     |                      4 |          0.2 |          0.2 |                         0.216353  |                      4 |                      0 | False            |             0.0570385 |
| AMD      |                      6 |          0.2 |          0.2 |                         0.173627  |                      5 |                      1 | False            |             0.0489663 |
| MU       |                      7 |          0.2 |          0.2 |                         0.125807  |                      6 |                      1 | False            |             0.0455166 |
| NET      |                      6 |          0.2 |          0.2 |                         0.13405   |                      5 |                      1 | False            |             0.0381369 |
| TSLA     |                      3 |          0.2 |          0.2 |                         0.133151  |                      3 |                      0 | False            |             0.0351034 |
| TQQQ     |                      3 |          0.2 |          0.2 |                         0.0445467 |                      2 |                      1 | True             |             0.0299603 |
| CRWD     |                      4 |          0.2 |          0.2 |                         0.0776896 |                      3 |                      1 | False            |             0.0284737 |
| SHOP     |                      5 |          0.2 |          0.2 |                         0.0102408 |                      3 |                      2 | False            |             0.0239499 |
| UPRO     |                      4 |          0.2 |          0.2 |                         0.0844776 |                      4 |                      0 | False            |             0.0222714 |

## 3. Weakest 12M Root Cause

| root_cause_type                          | severity   | evidence                                                                                                                                                                                                                                                    | whether_actionable_ex_ante   | recommended_fix                                                                                                                                               |
|:-----------------------------------------|:-----------|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:-----------------------------|:--------------------------------------------------------------------------------------------------------------------------------------------------------------|
| top_month_concentration                  | high       | weakest 12M top3 positive month profit share is 0.803; top months=2024-11,2024-06,2024-05                                                                                                                                                                   | partly                       | Add top-month and ticker concentration penalties to stock-selection ranking, not a post-selection overlay.                                                    |
| score_rank_audit_gap                     | high       | Existing v8 artifacts keep selected tickers and selected scores only; full monthly candidate scores/ranks and unselected flags are not persisted.                                                                                                           | yes                          | First add score/rank audit trail output to v8/v8.2 replay: one row per decision_date x tradable ticker with score, rank, selected_flag, lagged risk features. |
| high_beta_style_exposure                 | medium     | weakest high-beta avg weight share=0.166; strongest high-beta avg weight share=0.180; cycle 03-05 overlays lowered exposure but did not create a strong candidate.                                                                                          | yes                          | Move beta/volatility controls into ranking: lower high-beta names only when their score edge does not compensate for lagged risk.                             |
| dominant_ticker_dependency               | medium     | top full-period contribution concentration ticker=MSTR, abs contribution share=0.165; weak-window dominant tickers=MSTR,MU,CRWD,AMD,TQQQ.                                                                                                                   | yes                          | Use rolling selected-count/contribution proxy and same-ticker repeat penalty in cross-sectional reranking.                                                    |
| market_regime_not_sufficient_explanation | medium     | QQQ weak-window return=0.060 and SPY weak-window return=0.085 when available; cycle 05 market regime overlay improved drawdown but not strong-candidate gates.                                                                                              | yes                          | Use regime as a ranking conditioner, not a portfolio-level scale. Penalize high-vol/high-beta candidates under weak QQQ/SPY regimes.                          |
| existing_score_reranking_blocked         | high       | can_do_ex_ante_reranking=False; missing=monthly_candidate_universe_with_unselected_tickers;raw_monthly_prediction_scores_for_all_tradable_tickers;rank_before_selection_for_all_tradable_tickers;selected_flag_and_forward_return_for_unselected_candidates | yes                          | Do not run reranking replay yet. Patch v8/v8.2 replay to persist monthly candidate score/rank audit trail before any stock-selection reranking simulation.    |

## 4. Strongest 12M Comparison

| window_name                 | start      | end        |       CAGR |    Calmar |     MaxDD |   selected_ticker_count |   top5_ticker_exposure_share |   high_beta_weight_share |   top_month_contribution_share | dominant_ticker_list   |
|:----------------------------|:-----------|:-----------|-----------:|----------:|----------:|------------------------:|-----------------------------:|-------------------------:|-------------------------------:|:-----------------------|
| full_period                 | 2024-01-02 | 2026-04-17 |  0.653818  |  1.99153  | -0.3283   |                      27 |                     0.376173 |                0.140522  |                       0.168601 | MSTR,MU,AMD,TSLA,PLTR  |
| weakest_12m                 | 2024-04-01 | 2025-03-31 |  0.179788  |  0.636101 | -0.282641 |                      23 |                     0.434263 |                0.165737  |                       0.455046 | MSTR,MU,CRWD,AMD,TQQQ  |
| rolling_min_12m_observation | 2024-04-01 | 2025-03-31 |  0.179788  |  0.636101 | -0.282641 |                      23 |                     0.434263 |                0.165737  |                       0.455046 | MSTR,MU,CRWD,AMD,TQQQ  |
| strongest_12m               | 2024-11-01 | 2025-10-31 |  1.38944   |  4.23221  | -0.3283   |                      24 |                     0.3848   |                0.18      |                       0.25833  | MSTR,TSLA,PLTR,MU,TQQQ |
| 2024                        | 2024-01-01 | 2024-12-31 |  0.831285  |  2.94113  | -0.282641 |                      20 |                     0.490043 |                0.165079  |                       0.361181 | MSTR,CRWD,MU,AMD,NET   |
| 2025                        | 2025-01-01 | 2025-12-31 |  0.746498  |  2.28939  | -0.326069 |                      24 |                     0.3512   |                0.1472    |                       0.317923 | MU,MSTR,TSLA,PLTR,AVGO |
| 2026                        | 2026-01-01 | 2026-12-31 | -0.0348947 | -0.18365  | -0.190006 |                       7 |                     0.934247 |                0.0328767 |                       0.50526  | MU,INTC,SHOP,AMD,CRM   |

## 5. Existing-Score Reranking Feasibility

```json
{
  "has_monthly_candidate_universe": false,
  "has_raw_prediction_score": false,
  "has_rank_before_selection": false,
  "has_selected_flag": false,
  "has_forward_return": true,
  "has_selected_only_scores": true,
  "selected_score_source": "E:\\dzhwork\\quant\\quant_lab\\outputs\\us_stock_selection\\run_20260426_095958\\v8_paper_trading\\monthly_decision_ledger.csv",
  "can_do_ex_post_reranking": false,
  "can_do_ex_ante_reranking": false,
  "missing_files": [
    "monthly_candidate_universe_with_unselected_tickers",
    "raw_monthly_prediction_scores_for_all_tradable_tickers",
    "rank_before_selection_for_all_tradable_tickers",
    "selected_flag_and_forward_return_for_unselected_candidates"
  ],
  "recommended_next_action": "Do not run reranking replay yet. Patch v8/v8.2 replay to persist monthly candidate score/rank audit trail before any stock-selection reranking simulation."
}
```

## 6. Light Reranking Simulation

```json
{
  "light_reranking_simulation_run": false,
  "reason": "本轮未做 reranking simulation，原因是缺少 ex-ante monthly score/rank 留痕。",
  "lookahead_risk_if_forced": "high",
  "required_before_simulation": [
    "monthly_candidate_universe_with_unselected_tickers",
    "raw_monthly_prediction_scores_for_all_tradable_tickers",
    "rank_before_selection_for_all_tradable_tickers",
    "selected_flag_and_forward_return_for_unselected_candidates"
  ]
}
```

## 7. v8.2 Ranking Improvement Design

| proposal_name                   | required_inputs                                                                                       | ex_ante_feasible   | expected_benefit                                                                          | expected_cost                                                                               | implementation_complexity   | lookahead_risk                                                 |   recommended_priority | suggested_next_script                                    |
|:--------------------------------|:------------------------------------------------------------------------------------------------------|:-------------------|:------------------------------------------------------------------------------------------|:--------------------------------------------------------------------------------------------|:----------------------------|:---------------------------------------------------------------|-----------------------:|:---------------------------------------------------------|
| A_concentration_aware_reranking | monthly full candidate score/rank, selected history through t-1, ticker exposure/contribution proxies | True               | Reduce dominant ticker and top-month dependence without changing model training.          | May give up some explosive winners and lower full-period CAGR.                              | medium                      | low if selected history and realized returns are lagged to t-1 |                      1 | 39_add_v8_2_score_rank_audit_trail_then_rerank_replay.py |
| B_risk_adjusted_score           | monthly full scores plus trailing volatility/downside volatility/beta computed up to t-1              | True               | Prefer score per unit of risk and target weakest-window drawdown/cost fragility.          | Can underweight high-conviction momentum names during strong tapes.                         | medium                      | low if all risk features are lagged                            |                      2 | 39_add_v8_2_score_rank_audit_trail_then_rerank_replay.py |
| C_regime_conditional_ranking    | monthly scores, QQQ/SPY lagged regime state, candidate beta/volatility through t-1                    | True               | Use market regime to choose different stocks rather than bluntly lowering total exposure. | More degrees of freedom; needs strict parameter limits.                                     | medium_high                 | medium unless regime and candidate risk are explicitly shifted |                      3 | 40_v8_2_regime_conditional_ranking_sample.py             |
| D_stability_ensemble_ranking    | monthly scores across horizons/models or saved challenger scores, score volatility across recent fits | True               | Lower reliance on one unstable ElasticNet score and reduce single-month bursts.           | Needs score audit trail from multiple models/horizons; may require extra computation later. | high                        | low if only historical score dispersion is used                |                      4 | 41_v8_2_score_stability_audit.py                         |
| E_longer_history_training_split | longer clean daily history, consistent features, explicit train/valid/test chronology                 | True               | Expose model to more regimes and reduce overfit to 2024-2026 behavior.                    | Not a light diagnostic; may require data work before any v9-like expansion.                 | high                        | medium if validation split is not frozen before search         |                      5 | research_design_only_until_user_approval                 |

## 8. Final Judgment

- Overlay line stopped: `True`
- v8 baseline remains current best: `True`
- v8 verdict remains: `credible_but_execution_sensitive`
- allow_enter_v9: `False`
- Recommended next action: `Patch v8/v8.2 to persist monthly candidate score/rank audit trail, then run a bounded gate-aware reranking replay before any v9 or universe expansion.`

## 9. Outputs

- Output directory: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v8_2_stock_selection_layer_diagnostic_20260430_225000`
- Zip: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_quant_lab_v8_2_stock_selection_layer_diagnostic_20260430_225000.zip`
