"""Formal v9 precheck file generation.

The precheck never executes v9.  It writes the policy and required inputs that
must be satisfied before a separate formal v9 rerun can be approved.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from quant_lab.us_stock_selection.utils import ensure_dir, save_dataframe, save_json, save_text


def build_formal_v9_precheck(out_dir: Path | str, source_definition: dict[str, Any], formal_v82_gate_pass: bool, explicit_allow_run_formal_v9: bool = False) -> dict[str, Any]:
    out = ensure_dir(out_dir)
    blockers = []
    if not formal_v82_gate_pass:
        blockers.append(
            {
                "blocker": "formal_v82_gate_not_passed",
                "severity": "hard_block",
                "description": "Formal v9 cannot be prepared until canonical v8.2 baseline passes all gates.",
                "resolution": "Fix canonical v8.2 replay first.",
            }
        )
    if not explicit_allow_run_formal_v9:
        blockers.append(
            {
                "blocker": "explicit_allow_run_formal_v9_false",
                "severity": "control_block",
                "description": "This round only generates a formal v9 run plan; it does not execute formal v9.",
                "resolution": "Set explicit_allow_run_formal_v9=true in a future controlled run after review.",
            }
        )
    required_inputs = pd.DataFrame(
        [
            required("canonical_replay_engine.py", "must exist and be used for v9", True),
            required("v8_1 Alpha360/LGB score source or formal v9 score source", "must export full score/rank audit trail", True),
            required("local Qlib provider close bin", "same raw price source and calendar as formal v8.2", True),
            required("eligibility rule", "dynamic min-history rule must be identical for v8.2 and v9", True),
            required("formal gate config", "same CAGR/Calmar/cost/concentration/stress gates as formal v8.2", True),
            required("baseline exception isolation", "no loaded reproduction or benchmark-only rows in strategy metrics", True),
        ]
    )
    save_dataframe(required_inputs, out / "formal_v9_required_inputs.csv")
    blocker_df = pd.DataFrame(blockers) if blockers else pd.DataFrame(columns=["blocker", "severity", "description", "resolution"])
    save_dataframe(blocker_df, out / "formal_v9_blockers.csv")

    policy_md = f"""# Formal v9 Allowed Universe Policy

Formal v9 must use the exact same canonical policy as formal v8.2.

## Eligibility Rule

{source_definition.get("eligibility_rule", {}).get("description", "")}

- Dynamic entry is allowed only after the ticker has enough local provider history before the decision date.
- `listed_after_2020_train_start` is not automatically excluded if the ticker has enough history by the relevant decision date.
- PLTR/SNOW may only enter formal v9 if they pass this same rule on the same calendar and are produced by the formal score pipeline, not by loaded baseline reproduction.
- Baseline reproduction only rows must be isolated from formal strategy metrics.

## Hard Boundaries

- No Nasdaq100 expansion.
- No S&P500 expansion.
- No full-market expansion.
- No v10.
- No trading integration.
"""
    save_text(policy_md, out / "formal_v9_allowed_universe_policy.md")

    run_plan = """# Formal v9 Run Plan

This file is a plan only.  It does not authorize execution.

1. Reuse `canonical_replay_engine.py` for raw price loading, calendar, holdings replay, cost/slippage, T+1 execution, YTD cap, derisk, return reconstruction, and gate calculation.
2. Produce an independent formal v9 score/rank audit trail with full selected and unselected candidate rows.
3. Apply the same dynamic eligibility rule as formal v8.2.
4. Exclude all baseline-reproduction-only artifacts from formal v9 metrics.
5. Recompute daily NAV from holdings and Qlib provider close bin; do not reuse v9 original metrics or unified replay metrics.
6. Run formal gate detail and stop for review before any expansion.

Allowed now: generate this plan and wait for review.
Blocked now: execute formal v9, expand universe, enter v10, or trade.
"""
    save_text(run_plan, out / "formal_v9_run_plan.md")

    payload = {
        "formal_v82_gate_pass": bool(formal_v82_gate_pass),
        "explicit_allow_run_formal_v9": bool(explicit_allow_run_formal_v9),
        "formal_v9_execution_allowed_now": bool(formal_v82_gate_pass and explicit_allow_run_formal_v9 and blocker_df.empty),
        "v9_original_results_discarded": True,
        "unified_replay_role": "audit_evidence_only_not_formal_result",
        "must_use_canonical_replay_engine": True,
        "must_use_same_eligibility_rule": True,
        "must_use_same_gate": True,
        "no_baseline_reproduction_only_pollution": True,
        "blocker_count": int(len(blocker_df)),
    }
    save_json(payload, out / "formal_v9_precheck.json")
    return {
        "precheck": payload,
        "required_inputs": required_inputs,
        "blockers": blocker_df,
        "policy_md": str(out / "formal_v9_allowed_universe_policy.md"),
        "run_plan_md": str(out / "formal_v9_run_plan.md"),
    }


def required(name: str, description: str, required_value: bool) -> dict[str, Any]:
    return {"input_name": name, "description": description, "required": bool(required_value), "status": "required"}

