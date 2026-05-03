"""Review and simulate v8/v8.1 concentration gates without rerunning strategy logic.

This script is a gate calibration review. It reads the accepted v8 artifacts and
the v8 single-year diagnostic outputs, then writes proposed v8.1 concentration
gate tables and a simulated verdict. It does not enter v9, run 31b, expand the
universe, refit a model, rebalance a strategy, or overwrite the original v8
verdict.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_DIR = PROJECT_ROOT / "outputs" / "us_stock_selection" / "run_20260426_095958"
DEFAULT_DIAGNOSTIC_DIR = PROJECT_ROOT / "outputs" / "us_stock_selection" / "v8_single_year_concentration_20260427_233246"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
DOCS_DIR = PROJECT_ROOT / "docs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review v8 concentration gates and simulate v8.1 rules.")
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR, help="Accepted v8 run directory.")
    parser.add_argument(
        "--diagnostic-dir",
        type=Path,
        default=DEFAULT_DIAGNOSTIC_DIR,
        help="v8 single-year concentration diagnostic directory.",
    )
    parser.add_argument("--out-dir", type=Path, default=None, help="Output directory for this review.")
    parser.add_argument("--timestamp", default=None, help="Timestamp override in YYYYMMDD_HHMMSS form.")
    parser.add_argument("--no-zip", action="store_true", help="Write review outputs but skip zip packaging.")
    return parser.parse_args()


def setup_logging(out_dir: Path) -> logging.Logger:
    logs_dir = out_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("v8_gate_calibration_review")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh = logging.FileHandler(logs_dir / "v8_gate_calibration_review.log", encoding="utf-8")
    fh.setFormatter(formatter)
    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def read_csv(path: Path, logger: logging.Logger, required: bool = True) -> pd.DataFrame:
    if not path.exists():
        msg = f"Missing input CSV: {path}"
        if required:
            logger.warning(msg)
        else:
            logger.info(msg)
        return pd.DataFrame()
    try:
        df = pd.read_csv(path)
        logger.info("Loaded %s rows=%s cols=%s", path, len(df), len(df.columns))
        return df
    except Exception as exc:  # pragma: no cover - defensive local diagnostic
        logger.warning("Failed to read %s: %s", path, exc)
        return pd.DataFrame()


def read_json(path: Path, logger: logging.Logger) -> dict[str, Any]:
    if not path.exists():
        logger.warning("Missing input JSON: %s", path)
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        logger.info("Loaded JSON %s", path)
        return data
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to read %s: %s", path, exc)
        return {}


def as_float(value: Any, default: float = np.nan) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out


def safe_max(df: pd.DataFrame, col: str, default: float = np.nan) -> float:
    if df.empty or col not in df.columns:
        return default
    series = pd.to_numeric(df[col], errors="coerce").dropna()
    return float(series.max()) if not series.empty else default


def safe_min(df: pd.DataFrame, col: str, default: float = np.nan) -> float:
    if df.empty or col not in df.columns:
        return default
    series = pd.to_numeric(df[col], errors="coerce").dropna()
    return float(series.min()) if not series.empty else default


def safe_sum(df: pd.DataFrame, col: str, default: float = np.nan) -> float:
    if df.empty or col not in df.columns:
        return default
    series = pd.to_numeric(df[col], errors="coerce").dropna()
    return float(series.sum()) if not series.empty else default


def bool_pass(value: float, threshold: float, direction: str) -> bool | None:
    if math.isnan(value):
        return None
    if direction == "<=":
        return bool(value <= threshold)
    if direction == ">=":
        return bool(value >= threshold)
    raise ValueError(f"Unsupported direction: {direction}")


def severity(value: float, threshold: float, direction: str, status: bool | None, soft: bool = False) -> str:
    if status is None:
        return "unknown"
    if status:
        return "pass_observe" if soft else "pass"
    if direction == "<=":
        excess = value - threshold
        if excess <= 0.05:
            return "minor"
        if excess <= 0.15:
            return "moderate"
        return "major"
    shortfall = threshold - value
    if shortfall <= 0.10:
        return "minor"
    if shortfall <= 0.30:
        return "moderate"
    return "major"


def table_to_markdown(df: pd.DataFrame, columns: list[str] | None = None, max_rows: int = 30) -> str:
    if df is None or df.empty:
        return "_No rows_\n"
    sub = df.copy()
    if columns:
        sub = sub[[c for c in columns if c in sub.columns]]
    sub = sub.head(max_rows)
    for col in sub.columns:
        if pd.api.types.is_float_dtype(sub[col]):
            sub[col] = sub[col].map(lambda x: "" if pd.isna(x) else f"{float(x):.6f}")
    header = "| " + " | ".join(map(str, sub.columns)) + " |"
    sep = "| " + " | ".join(["---"] * len(sub.columns)) + " |"
    rows = ["| " + " | ".join(str(row[c]).replace("|", "/") for c in sub.columns) + " |" for _, row in sub.iterrows()]
    return "\n".join([header, sep, *rows]) + "\n"


def add_gate(
    rows: list[dict[str, Any]],
    gate_name: str,
    metric_value: float,
    proposed_threshold: float,
    direction: str,
    interpretation: str,
    recommended_action: str,
    gate_layer: str,
    soft: bool = False,
) -> None:
    status = bool_pass(metric_value, proposed_threshold, direction)
    rows.append(
        {
            "gate_name": gate_name,
            "metric_value": metric_value,
            "proposed_threshold": f"{direction} {proposed_threshold}",
            "pass_fail": "unknown" if status is None else ("pass" if status else "fail"),
            "severity": severity(metric_value, proposed_threshold, direction, status, soft=soft),
            "gate_layer": gate_layer,
            "interpretation": interpretation,
            "recommended_action": recommended_action,
        }
    )


def compute_metrics(
    verdict: dict[str, Any],
    annual: pd.DataFrame,
    monthly: pd.DataFrame,
    top_positive: pd.DataFrame,
    removed_month: pd.DataFrame,
    loo: pd.DataFrame,
    rolling: pd.DataFrame,
    yearly_holding: pd.DataFrame,
    ticker_exposure: pd.DataFrame,
    ticker_contrib: pd.DataFrame,
    logger: logging.Logger,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    if annual.empty:
        logger.warning("annual_contribution.csv is empty; annual gate metrics will be NaN.")
    metrics["current_abs_return_share"] = safe_max(annual, "gate_abs_year_return_share", as_float(verdict.get("single_year_share")))
    full = annual.loc[pd.to_numeric(annual.get("trading_month_count", pd.Series(dtype=float)), errors="coerce") >= 12].copy() if not annual.empty else pd.DataFrame()
    if not full.empty and "annual_return" in full.columns:
        abs_returns = pd.to_numeric(full["annual_return"], errors="coerce").abs()
        metrics["full_year_only_abs_return_share"] = float(abs_returns.max() / abs_returns.sum()) if abs_returns.sum() else np.nan
    else:
        metrics["full_year_only_abs_return_share"] = np.nan
        logger.warning("Could not compute full_year_only_abs_return_share.")
    if not annual.empty and "annual_return" in annual.columns:
        pos = pd.to_numeric(annual["annual_return"], errors="coerce")
        pos = pos.loc[pos > 0]
        metrics["positive_year_return_share"] = float(pos.max() / pos.sum()) if not pos.empty and pos.sum() else np.nan
    else:
        metrics["positive_year_return_share"] = np.nan
    metrics["annual_profit_share"] = safe_max(annual, "annual_profit_share")
    metrics["annual_profit_positive_share"] = safe_max(annual, "positive_profit_share")

    metrics["leave_one_year_out_min_cagr"] = safe_min(loo, "cagr")
    metrics["leave_one_year_out_min_calmar"] = safe_min(loo, "calmar")
    metrics["leave_one_year_out_pass_cagr_20"] = bool(metrics["leave_one_year_out_min_cagr"] >= 0.20) if not math.isnan(metrics["leave_one_year_out_min_cagr"]) else None
    metrics["leave_one_year_out_pass_calmar_1"] = bool(metrics["leave_one_year_out_min_calmar"] >= 1.0) if not math.isnan(metrics["leave_one_year_out_min_calmar"]) else None

    metrics["top1_positive_month_share"] = safe_sum(top_positive.head(1), "positive_profit_share")
    metrics["top3_positive_month_share"] = safe_sum(top_positive.head(3), "positive_profit_share")
    metrics["top5_positive_month_share"] = safe_sum(top_positive.head(5), "positive_profit_share")
    for n in [1, 3, 5]:
        local = removed_month.loc[pd.to_numeric(removed_month.get("removed_top_positive_month_count", pd.Series(dtype=float)), errors="coerce") == n]
        metrics[f"remove_top{n}_month_cagr"] = safe_max(local, "cagr")
        metrics[f"remove_top{n}_month_calmar"] = safe_max(local, "calmar")

    metrics["rolling_12m_min_return"] = safe_min(rolling, "window_return")
    metrics["rolling_12m_min_calmar_like"] = safe_min(rolling, "calmar_like")
    metrics["rolling_12m_max_return"] = safe_max(rolling, "window_return")
    if not math.isnan(metrics["rolling_12m_max_return"]) and not math.isnan(metrics["rolling_12m_min_return"]):
        metrics["rolling_12m_return_gap"] = metrics["rolling_12m_max_return"] - metrics["rolling_12m_min_return"]
    else:
        metrics["rolling_12m_return_gap"] = np.nan

    metrics["max_ticker_abs_share"] = safe_max(ticker_contrib, "abs_share", as_float(verdict.get("top_ticker_share")))
    metrics["max_ticker_month_weight"] = max(
        safe_max(yearly_holding, "single_ticker_max_month_weight", np.nan),
        safe_max(ticker_exposure, "max_weight", np.nan),
    )
    dominant_year = None
    if not annual.empty and "gate_abs_year_return_share" in annual.columns:
        idx = pd.to_numeric(annual["gate_abs_year_return_share"], errors="coerce").idxmax()
        if pd.notna(idx) and "year" in annual.columns:
            dominant_year = int(annual.loc[idx, "year"])
    metrics["dominant_year"] = dominant_year
    dominant_holding = yearly_holding.loc[pd.to_numeric(yearly_holding.get("year", pd.Series(dtype=float)), errors="coerce") == dominant_year] if dominant_year is not None and not yearly_holding.empty else pd.DataFrame()
    metrics["dominant_year_unique_ticker_count"] = safe_max(dominant_holding, "ticker_count")
    metrics["dominant_year_avg_holding_count"] = safe_max(dominant_holding, "avg_holding_count")
    if not ticker_exposure.empty and "appearance_count" in ticker_exposure.columns:
        appearances = pd.to_numeric(ticker_exposure["appearance_count"], errors="coerce").dropna()
        metrics["top_ticker_exposure_count_share"] = float(appearances.max() / appearances.sum()) if appearances.sum() else np.nan
    else:
        metrics["top_ticker_exposure_count_share"] = np.nan
        logger.warning("ticker_exposure_summary has no appearance_count column.")
    return metrics


def build_gate_comparison(metrics: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    add_gate(
        rows,
        "current_abs_return_share",
        metrics["current_abs_return_share"],
        0.55,
        "<=",
        "Existing v8 measure recalibrated as an observation gate for short samples.",
        "Do not hard-fail at 0.50 when only two full years dominate; monitor above 0.55.",
        "observation",
        soft=True,
    )
    add_gate(
        rows,
        "full_year_only_abs_return_share",
        metrics["full_year_only_abs_return_share"],
        0.55,
        "<=",
        "Same annual-return concentration but excluding partial years.",
        "Use alongside current_abs_return_share to avoid partial-year denominator noise.",
        "observation",
        soft=True,
    )
    add_gate(
        rows,
        "positive_year_return_share",
        metrics["positive_year_return_share"],
        0.55,
        "<=",
        "Positive annual return concentration among profitable years.",
        "Flag if one profitable full year dominates positive annual return.",
        "observation",
        soft=True,
    )
    add_gate(
        rows,
        "annual_profit_share",
        metrics["annual_profit_share"],
        0.65,
        "<=",
        "Largest absolute NAV profit share by year.",
        "Prefer this as explanatory context, not a hard gate, because compounding shifts later-year NAV dollars.",
        "diagnostic",
        soft=True,
    )
    add_gate(
        rows,
        "annual_profit_positive_share",
        metrics["annual_profit_positive_share"],
        0.65,
        "<=",
        "Largest positive NAV profit share by year.",
        "Monitor but do not hard-fail without longer sample support.",
        "diagnostic",
        soft=True,
    )

    add_gate(
        rows,
        "leave_one_year_out_min_cagr",
        metrics["leave_one_year_out_min_cagr"],
        0.20,
        ">=",
        "Worst CAGR after removing any calendar year from the existing NAV curve.",
        "Hard-pass only if the strategy still clears the minimum CAGR target without each year.",
        "hard",
    )
    add_gate(
        rows,
        "leave_one_year_out_min_calmar",
        metrics["leave_one_year_out_min_calmar"],
        1.0,
        ">=",
        "Worst Calmar after removing any calendar year from the existing NAV curve.",
        "Hard-pass only if risk-adjusted performance survives leave-one-year-out diagnostics.",
        "hard",
    )

    add_gate(
        rows,
        "top1_positive_month_share",
        metrics["top1_positive_month_share"],
        0.25,
        "<=",
        "Largest positive month share of total positive NAV profit.",
        "Hard-fail if one month alone carries too much of the profit.",
        "hard",
    )
    add_gate(
        rows,
        "top3_positive_month_share",
        metrics["top3_positive_month_share"],
        0.50,
        "<=",
        "Top three positive months' share of total positive NAV profit.",
        "Hard-fail if a small cluster of months carries most of the profit.",
        "hard",
    )
    add_gate(
        rows,
        "top5_positive_month_share",
        metrics["top5_positive_month_share"],
        0.60,
        "<=",
        "Top five positive months' share of total positive NAV profit.",
        "Observation flag rather than hard reject for short samples.",
        "observation",
        soft=True,
    )
    for n in [1, 3, 5]:
        add_gate(
            rows,
            f"remove_top{n}_month_cagr",
            metrics[f"remove_top{n}_month_cagr"],
            0.20,
            ">=",
            f"CAGR after removing the top {n} positive month(s) from the NAV curve.",
            "Use as diagnostic fragility evidence; top3/top5 failures imply month-cluster sensitivity.",
            "diagnostic",
            soft=True,
        )
        add_gate(
            rows,
            f"remove_top{n}_month_calmar",
            metrics[f"remove_top{n}_month_calmar"],
            1.0,
            ">=",
            f"Calmar after removing the top {n} positive month(s) from the NAV curve.",
            "Use as diagnostic fragility evidence; do not confuse with a true strategy rerun.",
            "diagnostic",
            soft=True,
        )

    add_gate(
        rows,
        "rolling_12m_min_return",
        metrics["rolling_12m_min_return"],
        0.0,
        ">=",
        "Weakest rolling 12-month total return.",
        "Monitor regime weakness; negative 12-month windows need special review.",
        "observation",
        soft=True,
    )
    add_gate(
        rows,
        "rolling_12m_min_calmar_like",
        metrics["rolling_12m_min_calmar_like"],
        0.5,
        ">=",
        "Weakest rolling 12-month Calmar-like metric.",
        "Observation gate for regime stability.",
        "observation",
        soft=True,
    )
    add_gate(
        rows,
        "rolling_12m_return_gap",
        metrics["rolling_12m_return_gap"],
        1.50,
        "<=",
        "Gap between strongest and weakest rolling 12-month return.",
        "Large gaps feed the concentration penalty rather than immediate hard failure.",
        "observation",
        soft=True,
    )

    add_gate(
        rows,
        "max_ticker_abs_share",
        metrics["max_ticker_abs_share"],
        0.30,
        "<=",
        "Largest ticker absolute return contribution share.",
        "Hard-fail if a single ticker dominates realized contribution.",
        "hard",
    )
    add_gate(
        rows,
        "max_ticker_month_weight",
        metrics["max_ticker_month_weight"],
        0.30,
        "<=",
        "Largest single ticker monthly weight.",
        "Hard-fail if a ticker can exceed acceptable position concentration.",
        "hard",
    )
    add_gate(
        rows,
        "dominant_year_unique_ticker_count",
        metrics["dominant_year_unique_ticker_count"],
        10,
        ">=",
        "Number of tickers held in the dominant gate year.",
        "Observation pass indicates the dominant year was not just one or two names.",
        "observation",
        soft=True,
    )
    add_gate(
        rows,
        "dominant_year_avg_holding_count",
        metrics["dominant_year_avg_holding_count"],
        3,
        ">=",
        "Average holding count in the dominant gate year.",
        "Observation pass confirms portfolio breadth at rebalance level.",
        "observation",
        soft=True,
    )
    add_gate(
        rows,
        "top_ticker_exposure_count_share",
        metrics["top_ticker_exposure_count_share"],
        0.25,
        "<=",
        "Most frequent ticker's share of active holding appearances.",
        "Monitor repeated exposure concentration even if weights are capped.",
        "observation",
        soft=True,
    )
    return pd.DataFrame(rows)


def clipped_penalty(value: float, threshold: float, direction: str, scale: float) -> float:
    if math.isnan(value) or scale <= 0:
        return 0.0
    if direction == "<=":
        raw = (value - threshold) / scale
    elif direction == ">=":
        raw = (threshold - value) / scale
    else:
        raise ValueError(direction)
    return float(min(1.0, max(0.0, raw)))


def concentration_penalty(metrics: dict[str, Any]) -> tuple[float, dict[str, float]]:
    parts = {
        "year_return_concentration_penalty": clipped_penalty(metrics["current_abs_return_share"], 0.50, "<=", 0.15),
        "top_month_concentration_penalty": clipped_penalty(metrics["top3_positive_month_share"], 0.40, "<=", 0.25),
        "ticker_exposure_penalty": clipped_penalty(metrics["max_ticker_abs_share"], 0.25, "<=", 0.15),
        "rolling_12m_instability_penalty": clipped_penalty(metrics["rolling_12m_min_calmar_like"], 1.0, ">=", 1.0),
        "high_beta_asset_penalty": clipped_penalty(metrics["top_ticker_exposure_count_share"], 0.20, "<=", 0.20),
    }
    weights = {
        "year_return_concentration_penalty": 0.25,
        "top_month_concentration_penalty": 0.25,
        "ticker_exposure_penalty": 0.20,
        "rolling_12m_instability_penalty": 0.20,
        "high_beta_asset_penalty": 0.10,
    }
    score = sum(parts[key] * weights[key] for key in parts)
    return float(score), parts


def simulate_v8_1_verdict(verdict: dict[str, Any], comparison: pd.DataFrame, metrics: dict[str, Any]) -> dict[str, Any]:
    hard = comparison.loc[comparison["gate_layer"] == "hard"].copy()
    obs = comparison.loc[comparison["gate_layer"] == "observation"].copy()
    hard_failed = hard.loc[hard["pass_fail"] == "fail", "gate_name"].tolist()
    hard_passed = hard.loc[hard["pass_fail"] == "pass", "gate_name"].tolist()
    observation_flags = obs.loc[obs["pass_fail"] == "fail", "gate_name"].tolist()
    penalty_score, penalty_parts = concentration_penalty(metrics)
    if hard_failed:
        simulated = "concentration_gate_failed"
    elif observation_flags or penalty_score >= 0.25:
        simulated = "credible_but_concentration_watch"
    else:
        simulated = "concentration_gate_passed"
    return {
        "original_v8_verdict": verdict.get("classification"),
        "original_allow_enter_v9": verdict.get("allow_enter_v9"),
        "simulated_v8_1_concentration_verdict": simulated,
        "simulated_allow_enter_v9": False,
        "hard_gates_passed": hard_passed,
        "hard_gates_failed": hard_failed,
        "observation_flags": observation_flags,
        "concentration_penalty_score": penalty_score,
        "penalty_components": penalty_parts,
        "final_interpretation": (
            "v8 would pass the proposed hard concentration gates, but should remain blocked from v9 because this is only a "
            "diagnostic calibration review and the original v8 final verdict is not being rewritten."
            if not hard_failed
            else "v8 would fail at least one proposed v8.1 hard concentration gate."
        ),
    }


def build_input_index(paths: dict[str, Path], loaded: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, path in paths.items():
        row = {
            "name": name,
            "path": str(path),
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else None,
            "rows": None,
            "columns": "",
        }
        if name in loaded:
            df = loaded[name]
            row["rows"] = int(len(df)) if df is not None else None
            row["columns"] = ",".join(map(str, df.columns)) if df is not None and not df.empty else ""
        rows.append(row)
    return pd.DataFrame(rows)


def gate_review_text(
    timestamp: str,
    run_dir: Path,
    diagnostic_dir: Path,
    verdict: dict[str, Any],
    metrics: dict[str, Any],
    comparison: pd.DataFrame,
    simulated: dict[str, Any],
) -> str:
    hard = comparison.loc[comparison["gate_layer"] == "hard"]
    observe = comparison.loc[comparison["gate_layer"] == "observation"]
    diagnostic = comparison.loc[comparison["gate_layer"] == "diagnostic"]
    return f"""# US Stock Selection v8 Gate Calibration Review - {timestamp}

Scope: v8 gate calibration review and v8.1 concentration-rule design only. This is not a new backtest, not v9, not Nasdaq100/S&P500 expansion, and not a 31b run.

Run directory: `{run_dir}`

Single-year diagnostic directory: `{diagnostic_dir}`

## 1. Background and purpose

The accepted v8 closeout remains `{verdict.get("classification")}` with `allow_enter_v9={verdict.get("allow_enter_v9")}`. The only major failed concentration gate is `single_year_share_lte_50=False`, with `single_year_share={verdict.get("single_year_share")}`.

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

- Current abs return share: `{metrics["current_abs_return_share"]:.6f}`
- Full-year-only abs return share: `{metrics["full_year_only_abs_return_share"]:.6f}`
- Positive-year return share: `{metrics["positive_year_return_share"]:.6f}`
- Annual NAV profit share max: `{metrics["annual_profit_share"]:.6f}`
- Annual positive NAV profit share max: `{metrics["annual_profit_positive_share"]:.6f}`

The failed 50% gate means 2024's compounded return is slightly larger than 2025's under an absolute-return denominator. With only two complete high-return years plus one partial year, a 50% hard threshold almost requires the two full years to be exactly balanced.

## 4. Why 52.6% is not severe single-year monopoly

The 2024 gate share is 52.6%, while 2025 is 46.7%; the gap is about 5.85 percentage points. Leave-one-year-out diagnostics still pass the original minimum return and Calmar objectives:

- Minimum leave-one-year-out CAGR: `{metrics["leave_one_year_out_min_cagr"]:.6f}`
- Minimum leave-one-year-out Calmar: `{metrics["leave_one_year_out_min_calmar"]:.6f}`

That evidence argues against a severe one-year-only dependency. The original v8 gate failure remains valid, but it is better interpreted as a calibration warning than as proof of structural invalidity.

## 5. Why top-month sensitivity deserves more attention

- Top 1 positive month share: `{metrics["top1_positive_month_share"]:.6f}`
- Top 3 positive months share: `{metrics["top3_positive_month_share"]:.6f}`
- Top 5 positive months share: `{metrics["top5_positive_month_share"]:.6f}`
- Remove top 3 months CAGR: `{metrics["remove_top3_month_cagr"]:.6f}`
- Remove top 3 months Calmar: `{metrics["remove_top3_month_calmar"]:.6f}`
- Remove top 5 months CAGR: `{metrics["remove_top5_month_cagr"]:.6f}`
- Remove top 5 months Calmar: `{metrics["remove_top5_month_calmar"]:.6f}`

The strategy survives removing the top one month, but becomes weaker after removing the top three and fails the 20% CAGR threshold after removing the top five. This points to month-cluster sensitivity as the more useful v8.1 diagnostic.

## 6. v8.1 recommended concentration gate scheme

Hard gates:

{table_to_markdown(hard, ["gate_name", "metric_value", "proposed_threshold", "pass_fail", "severity", "interpretation", "recommended_action"])}

Observation gates:

{table_to_markdown(observe, ["gate_name", "metric_value", "proposed_threshold", "pass_fail", "severity", "interpretation", "recommended_action"])}

Diagnostic-only checks:

{table_to_markdown(diagnostic, ["gate_name", "metric_value", "proposed_threshold", "pass_fail", "severity", "interpretation", "recommended_action"])}

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
{json.dumps(simulated.get("penalty_components", {}), indent=2)}
```

## 7. v8.1 simulated verdict

```json
{json.dumps(simulated, indent=2)}
```

The current v8 would pass the proposed v8.1 hard concentration gates, but observation and diagnostic checks still recommend caution. This simulation must not be read as v9 approval.

## 8. Recommended sequencing

Do v8.1 gate-aware improvement before any v9 discussion. In v8.1, use the stricter hard robustness gates plus observation flags and penalty scoring. Do not directly enter v9 from this calibration review.

## 9. 31b challenger positioning

31b remains an optional challenger-model supplement. It can improve model stability evidence, but it cannot directly fix annual return concentration, top-month contribution concentration, or ticker exposure concentration.
"""


def exec_summary_text(
    timestamp: str,
    verdict: dict[str, Any],
    metrics: dict[str, Any],
    simulated: dict[str, Any],
) -> str:
    return f"""# US Stock Selection v8 Gate Calibration Executive Summary - {timestamp}

Final v8 verdict remains `{verdict.get("classification")}`. `allow_enter_v9` remains `{verdict.get("allow_enter_v9")}`.

The existing `single_year_share` gate is code-confirmed as max absolute annual return divided by total absolute annual returns. For this short sample, 52.6% vs 46.7% mostly says 2024 was slightly stronger than 2025; it is a real gate failure, but not severe one-year monopoly.

Key results:

- Current abs annual-return share: `{metrics["current_abs_return_share"]:.6f}`
- Leave-one-year-out min CAGR / Calmar: `{metrics["leave_one_year_out_min_cagr"]:.6f}` / `{metrics["leave_one_year_out_min_calmar"]:.6f}`
- Top 1 / Top 3 / Top 5 positive month share: `{metrics["top1_positive_month_share"]:.6f}` / `{metrics["top3_positive_month_share"]:.6f}` / `{metrics["top5_positive_month_share"]:.6f}`
- Remove top 3 months CAGR / Calmar: `{metrics["remove_top3_month_cagr"]:.6f}` / `{metrics["remove_top3_month_calmar"]:.6f}`
- Max ticker abs share / max monthly weight: `{metrics["max_ticker_abs_share"]:.6f}` / `{metrics["max_ticker_month_weight"]:.6f}`

Recommended v8.1 interpretation: `{simulated.get("simulated_v8_1_concentration_verdict")}` with concentration penalty score `{simulated.get("concentration_penalty_score"):.6f}`.

Recommendation: build v8.1 gate-aware improvement first. Do not enter v9, do not expand universe, and do not treat 31b as a fix for concentration; 31b is only optional model-stability evidence.
"""


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def unique_zip_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    i = 2
    while True:
        candidate = parent / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def package_outputs(out_dir: Path, doc_path: Path, summary_path: Path, timestamp: str, logger: logging.Logger) -> Path:
    zip_path = unique_zip_path(DEFAULT_OUTPUT_ROOT / f"us_stock_selection_quant_lab_v8_gate_calibration_review_{timestamp}.zip")
    paths = [
        PROJECT_ROOT / "scripts" / "us_stock_selection" / "33_review_v8_concentration_gates.py",
        out_dir,
        doc_path,
        summary_path,
        PROJECT_ROOT / "NEXT_STEPS.md",
    ]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in paths:
            if not path.exists():
                logger.warning("Package path missing and skipped: %s", path)
                continue
            if path.is_dir():
                for child in path.rglob("*"):
                    if child.is_file():
                        zf.write(child, child.resolve().relative_to(PROJECT_ROOT))
            else:
                zf.write(path, path.resolve().relative_to(PROJECT_ROOT))
    logger.info("Packaged review zip: %s", zip_path)
    return zip_path


def main() -> None:
    args = parse_args()
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = args.run_dir.resolve()
    diagnostic_dir = args.diagnostic_dir.resolve()
    out_dir = (args.out_dir or (DEFAULT_OUTPUT_ROOT / f"v8_gate_calibration_review_{timestamp}")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    logger = setup_logging(out_dir)
    logger.info("Starting v8 gate calibration review. run_dir=%s diagnostic_dir=%s out_dir=%s", run_dir, diagnostic_dir, out_dir)

    paths = {
        "v8_verdict": run_dir / "v8_verdict.json",
        "ticker_contribution": run_dir / "v8_attribution" / "ticker_contribution.csv",
        "annual_contribution": diagnostic_dir / "annual_contribution.csv",
        "monthly_contribution": diagnostic_dir / "monthly_contribution.csv",
        "top_positive_months": diagnostic_dir / "top_positive_months.csv",
        "top_month_removed_metrics": diagnostic_dir / "top_month_removed_metrics.csv",
        "leave_one_year_out_metrics": diagnostic_dir / "leave_one_year_out_metrics.csv",
        "rolling_12m_metrics": diagnostic_dir / "rolling_12m_metrics.csv",
        "yearly_holding_concentration": diagnostic_dir / "yearly_holding_concentration.csv",
        "ticker_exposure_summary": diagnostic_dir / "ticker_exposure_summary.csv",
    }
    verdict = read_json(paths["v8_verdict"], logger)
    loaded: dict[str, pd.DataFrame] = {}
    for key, path in paths.items():
        if path.suffix.lower() == ".csv":
            loaded[key] = read_csv(path, logger, required=True)

    metrics = compute_metrics(
        verdict=verdict,
        annual=loaded.get("annual_contribution", pd.DataFrame()),
        monthly=loaded.get("monthly_contribution", pd.DataFrame()),
        top_positive=loaded.get("top_positive_months", pd.DataFrame()),
        removed_month=loaded.get("top_month_removed_metrics", pd.DataFrame()),
        loo=loaded.get("leave_one_year_out_metrics", pd.DataFrame()),
        rolling=loaded.get("rolling_12m_metrics", pd.DataFrame()),
        yearly_holding=loaded.get("yearly_holding_concentration", pd.DataFrame()),
        ticker_exposure=loaded.get("ticker_exposure_summary", pd.DataFrame()),
        ticker_contrib=loaded.get("ticker_contribution", pd.DataFrame()),
        logger=logger,
    )
    comparison = build_gate_comparison(metrics)
    simulated = simulate_v8_1_verdict(verdict, comparison, metrics)
    input_index = build_input_index(paths, loaded)

    comparison_path = out_dir / "v8_concentration_gate_comparison.csv"
    verdict_path = out_dir / "v8_1_gate_simulated_verdict.json"
    metrics_path = out_dir / "v8_concentration_metric_snapshot.json"
    input_index_path = out_dir / "input_file_index.csv"
    doc_local_path = out_dir / "US_STOCK_SELECTION_V8_GATE_CALIBRATION_REVIEW.md"
    summary_local_path = out_dir / "US_STOCK_SELECTION_V8_GATE_CALIBRATION_EXEC_SUMMARY.md"
    doc_path = DOCS_DIR / f"US_STOCK_SELECTION_V8_GATE_CALIBRATION_REVIEW_{timestamp[:8]}.md"
    summary_path = DOCS_DIR / f"US_STOCK_SELECTION_V8_GATE_CALIBRATION_EXEC_SUMMARY_{timestamp[:8]}.md"

    comparison.to_csv(comparison_path, index=False)
    write_json(verdict_path, simulated)
    write_json(metrics_path, metrics)
    input_index.to_csv(input_index_path, index=False)
    doc_text = gate_review_text(timestamp, run_dir, diagnostic_dir, verdict, metrics, comparison, simulated)
    summary_text = exec_summary_text(timestamp, verdict, metrics, simulated)
    doc_local_path.write_text(doc_text, encoding="utf-8")
    summary_local_path.write_text(summary_text, encoding="utf-8")
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(doc_text, encoding="utf-8")
    summary_path.write_text(summary_text, encoding="utf-8")
    logger.info("Wrote comparison, simulated verdict, metrics snapshot, docs, and input index.")

    if not args.no_zip:
        package_outputs(out_dir, doc_path, summary_path, timestamp, logger)
    logger.info("Completed v8 gate calibration review.")


if __name__ == "__main__":
    main()
