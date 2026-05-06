# v8.2 Frozen Formal Audit Review Packet

Run ID: `v82_frozen_formal_audit_20260506_113454`

Audit directory: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v82_frozen_formal_audit_20260506_113454`

## Verdict

```json
{
  "run_id": "v82_frozen_formal_audit_20260506_113454",
  "audit_dir": "E:\\dzhwork\\quant\\quant_lab\\outputs\\us_stock_selection\\v82_frozen_formal_audit_20260506_113454",
  "classification": "v82_formal_replay_audit_passed_formal_frozen_baseline",
  "conclusion": "A",
  "conclusion_text": "v8.2 formal replay audit passed; it can be upgraded to / retained as formal frozen baseline.",
  "gate_result": "PASS",
  "formal_replay_completed": true,
  "formal_replay_provider": "C:\\Users\\Administrator\\.qlib\\qlib_data\\us_data_local_2026_v91_growth",
  "price_source": "local Qlib provider bin $close",
  "adj_close_policy": "provider $close adjusted-close policy from v9.1 provider; unified replay not used as formal result",
  "volume_source": "local Qlib provider bin $volume",
  "replay_engine": "canonical_replay_engine",
  "strategy_id": "top5_ytdcap80p_derisk100p",
  "feature_set": "Alpha360",
  "model": "LGBModel",
  "label": "label_5d",
  "portfolio": "top5_ytdcap80p_derisk100p",
  "rebalance": "monthly",
  "execution": "T+1",
  "cost_bps": 5.0,
  "slippage_bps": 5.0,
  "cost50_cagr": 0.5406128633202154,
  "cost50_calmar": 1.3453478263901464,
  "cagr": 0.6421262430680639,
  "calmar": 1.6339698829869318,
  "max_drawdown": -0.39298536022845376,
  "single_year_share": 0.4968386021801039,
  "top_contribution_year": 2024,
  "top_ticker": "INTC",
  "top_ticker_share": 0.137939380670818,
  "remove_top_year_cagr": 0.5215872877272436,
  "remove_top_year_calmar": 1.3272435579382131,
  "remove_top_ticker_cagr": 0.4896538831502253,
  "remove_top_ticker_calmar": 1.3265102205318462,
  "coin_mstr_pltr_share": 0.1750111368026543,
  "depends_on_coin_mstr_pltr": false,
  "fatal_evidence_gap": false,
  "score_provenance_gap": false,
  "historical_evidence_found": true,
  "formal_v9_pool_a_cagr": 0.2322248622855247,
  "formal_v9_pool_a_calmar": 0.5584103684950428,
  "formal_v9_growth_cagr": 0.0797791017483375,
  "formal_v9_growth_calmar": 0.1866013926654182,
  "frozen_mainline_changed": false,
  "current_frozen_mainline": "v8.2 frozen Pool A top5_ytdcap80p_derisk100p",
  "next_allowed_action": "Stop for human review; v8.2 can be treated as the formal frozen baseline evidence packet. Do not enter v10.",
  "forbidden_next_actions": [
    "v10",
    "Nasdaq100/S&P500/full-market expansion",
    "new strategy search",
    "parameter search",
    "trading/broker/API workflow",
    "gate lowering",
    "using old v9 or unified replay as formal result",
    "automatic commit/push"
  ],
  "commit_push": "No",
  "zip_path": "E:\\dzhwork\\quant\\quant_lab\\outputs\\us_stock_selection\\us_stock_selection_v82_frozen_formal_audit_20260506_113454.zip"
}
```

## Required Review Focus

1. Whether the v8.2 frozen formal replay evidence supports conclusion `A`.
2. Whether the score provenance trail is sufficient for a frozen baseline.
3. Whether the v8.2 baseline should remain frozen after formal v9 failed.
4. Confirm no v10, no expansion, no trading, no parameter search.

## Formal v9 Failed Branch

- `formal_v9_20260505_224016` did not pass the formal gate.
- Failure reasons include v9.1 score/rank drift, small-growth dilution, cost fragility, elevated single-year contribution, and PLTR/MSTR/COIN dependency.
- formal v9 is not allowed as the frozen baseline.
- Old v9 and unified replay must not be used as formal results.

## Baseline Scope Caveat

- v8.2 score provenance is a v8.1 frozen runtime prediction trail.
- It is not a newly trained v9.1 score source.
- The current conclusion is limited to formal replay / formal evidence audit PASS.
- It does not mean v9.1 retrain can reproduce v8.2 score/rank.

## Forbidden Actions

- Do not enter v10.
- Do not expand Nasdaq100, S&P500, or full-market pools.
- Do not run new strategy search or parameter search.
- Do not trade, connect brokers/APIs, or place real orders.
- Do not lower gates.
- Do not commit or push automatically.

## Primary Files

- `outputs/us_stock_selection/v82_frozen_formal_audit_20260506_113454/v82_frozen_formal_audit.md`
- `outputs/us_stock_selection/v82_frozen_formal_audit_20260506_113454/v82_frozen_formal_replay_summary.xlsx`
- `outputs/us_stock_selection/v82_frozen_formal_audit_20260506_113454/v82_frozen_evidence_availability.csv`
- `outputs/us_stock_selection/v82_frozen_formal_audit_20260506_113454/v82_frozen_gate_check.csv`
- `outputs/us_stock_selection/v82_frozen_formal_audit_20260506_113454/v82_vs_formal_v9_comparison.xlsx`

## Current Allowed Next Action

Stop for human review; v8.2 can be treated as the formal frozen baseline evidence packet. Do not enter v10.
