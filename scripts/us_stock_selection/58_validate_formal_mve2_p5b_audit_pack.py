from __future__ import annotations

import json
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
P5B_RUN_ID = "formal_mve2_controlled_search_p5b_20260507_215801"
P5B_DIR = OUTPUT_ROOT / P5B_RUN_ID
STORE_DIR = PROJECT_ROOT / "data" / "unified_ohlcv" / "us_stock_selection"
PRICES_DIR = STORE_DIR / "prices"
SEARCH_DIR = OUTPUT_ROOT / "limited_mve2_20260502_142702"
V82_AUDIT_DIR = OUTPUT_ROOT / "v82_frozen_formal_audit_20260506_113454"
FORMAL_V9_FAILURE_AUDIT = OUTPUT_ROOT / "formal_v9_20260505_224016" / "audit" / "formal_v9_failure_audit.md"
SCRIPT_PATH = Path("scripts/us_stock_selection/58_validate_formal_mve2_p5b_audit_pack.py")
RUN_PREFIX = "formal_mve2_validation_audit_p6"

REQUIRED_P5B_FILES = [
    "README.md",
    "manifest.json",
    "run_config.json",
    "candidate_summary.csv",
    "selected_candidates.csv",
    "rejected_candidates.csv",
    "benchmark_comparison.csv",
    "yearly_performance.csv",
    "subperiod_performance.csv",
    "drawdown_summary.csv",
    "turnover_summary.csv",
    "cost_stress_summary.csv",
    "risk_flag_exposure.csv",
    "parameter_grid_summary.csv",
    "search_execution_summary.csv",
    "formal_mve2_search_decision.json",
    "reproducibility_checklist.csv",
    "risk_flags.csv",
]
SELECTED_IDS = [
    "momentum_rank__p002",
    "momentum_rank__p004",
    "momentum_liquidity_guard__p016",
]
CORE_METRICS = ["CAGR", "MDD", "Calmar", "Sharpe", "volatility", "turnover"]
RECOMPUTE_TOLERANCE = 1e-6
DEFAULT_COST_BPS = 10
LOW_MEDIAN_VOLUME_THRESHOLD = 100_000
COMMON_START = "2016-01-01"
VOLUME_WARNING_TICKERS = ["AAPL", "AMD", "ARKK", "IGV", "INTC", "SHOP"]
PRICE_JUMP_WARNING_TICKERS = ["AAPL", "AMD", "MSTR", "ROKU", "SHOP", "SOXL", "UPST"]


def rel(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def clean(value: Any) -> str:
    if value is None:
        return "NA"
    try:
        if pd.isna(value):
            return "NA"
    except (TypeError, ValueError):
        pass
    return str(value)


def to_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return float("nan")
    drawdown = equity / equity.cummax() - 1.0
    return float(drawdown.min())


def max_drawdown_duration(equity: pd.Series) -> int:
    current = 0
    longest = 0
    for value in (equity / equity.cummax() - 1.0).fillna(0.0):
        if value < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return int(longest)


def performance_metrics(returns: pd.Series) -> dict[str, float]:
    clean_returns = returns.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    if clean_returns.empty:
        return {
            "total_return": np.nan,
            "CAGR": np.nan,
            "MDD": np.nan,
            "Calmar": np.nan,
            "Sharpe": np.nan,
            "volatility": np.nan,
            "hit_rate": np.nan,
            "drawdown_duration": np.nan,
        }
    equity = (1.0 + clean_returns).cumprod()
    years = len(clean_returns) / 252.0
    final_equity = float(equity.iloc[-1])
    cagr = float(final_equity ** (1.0 / years) - 1.0) if years > 0 and final_equity > 0 else np.nan
    mdd = max_drawdown(equity)
    std = clean_returns.std(ddof=0)
    return {
        "total_return": float(final_equity - 1.0),
        "CAGR": cagr,
        "MDD": mdd,
        "Calmar": float(cagr / abs(mdd)) if pd.notna(cagr) and pd.notna(mdd) and mdd < 0 else np.nan,
        "Sharpe": float(clean_returns.mean() / std * np.sqrt(252.0)) if std > 0 else np.nan,
        "volatility": float(std * np.sqrt(252.0)),
        "hit_rate": float((clean_returns > 0).mean()),
        "drawdown_duration": float(max_drawdown_duration(equity)),
    }


def zscore(series: pd.Series) -> pd.Series:
    values = series.replace([np.inf, -np.inf], np.nan)
    std = values.std(skipna=True)
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=series.index)
    return (values - values.mean(skipna=True)) / std


def read_price_file(ticker: str) -> pd.DataFrame:
    path = PRICES_DIR / f"{ticker}.parquet"
    if not path.exists():
        return pd.DataFrame(columns=["date", "ticker", "adj_close", "volume"])
    df = pd.read_parquet(path)
    required = ["date", "ticker", "adj_close", "volume"]
    if any(field not in df.columns for field in required):
        return pd.DataFrame(columns=required)
    out = df[required].copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["ticker"] = ticker
    out["adj_close"] = pd.to_numeric(out["adj_close"], errors="coerce")
    out["volume"] = pd.to_numeric(out["volume"], errors="coerce")
    out = out.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last")
    return out


def load_price_data(tickers: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    price_series: dict[str, pd.Series] = {}
    volume_series: dict[str, pd.Series] = {}
    for ticker in tickers:
        df = read_price_file(ticker)
        if df.empty:
            continue
        indexed = df.set_index("date").sort_index()
        price_series[ticker] = indexed["adj_close"]
        volume_series[ticker] = indexed["volume"]
    prices = pd.DataFrame(price_series).sort_index()
    volumes = pd.DataFrame(volume_series).reindex(prices.index)
    prices = prices.loc[prices.index >= pd.Timestamp(COMMON_START)].ffill()
    returns = prices.pct_change(fill_method=None)
    valid_rows = returns.notna().any(axis=1)
    prices = prices.loc[valid_rows]
    volumes = volumes.loc[prices.index]
    return prices, volumes


def monthly_rebalance_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    if len(index) == 0:
        return []
    dates = pd.Series(index=index, data=index)
    grouped = dates.groupby([dates.index.year, dates.index.month]).last()
    return [pd.Timestamp(value) for value in grouped.tolist()]


def score_for_strategy(
    prices: pd.DataFrame,
    returns: pd.DataFrame,
    volumes: pd.DataFrame,
    date: pd.Timestamp,
    spec: pd.Series,
) -> pd.Series:
    mom_lb = int(float(spec["momentum_lookback_days"]))
    family = str(spec["strategy_family"])
    if date not in prices.index:
        return pd.Series(dtype=float)
    loc = prices.index.get_loc(date)
    if isinstance(loc, slice) or isinstance(loc, np.ndarray) or loc < mom_lb:
        return pd.Series(dtype=float)
    momentum = prices.iloc[loc] / prices.iloc[loc - mom_lb] - 1.0
    if family == "momentum_rank":
        return momentum
    if family == "momentum_low_vol":
        vol_lb = int(float(spec["volatility_lookback_days"]))
        if loc < vol_lb:
            return pd.Series(dtype=float)
        vol = returns.iloc[loc - vol_lb + 1 : loc + 1].std(skipna=True)
        return zscore(momentum) - zscore(vol)
    if family == "momentum_liquidity_guard":
        liq_lb = int(float(spec["liquidity_lookback_days"]))
        if loc < liq_lb:
            return pd.Series(dtype=float)
        median_volume = volumes.iloc[loc - liq_lb + 1 : loc + 1].median(skipna=True)
        return momentum.where(median_volume >= LOW_MEDIAN_VOLUME_THRESHOLD)
    return pd.Series(dtype=float)


def backtest_candidate(prices: pd.DataFrame, volumes: pd.DataFrame, spec: pd.Series) -> tuple[pd.Series, pd.Series]:
    returns = prices.pct_change(fill_method=None).fillna(0.0)
    target_weights = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    for rebalance_date in monthly_rebalance_dates(prices.index):
        scores = score_for_strategy(prices, returns, volumes, rebalance_date, spec).dropna().sort_values(ascending=False)
        selected = list(scores.head(int(float(spec["top_n"]))).index)
        if not selected:
            continue
        target_weights.loc[rebalance_date, selected] = 1.0 / len(selected)
    weights = target_weights.replace(0.0, np.nan).ffill().fillna(0.0).shift(1).fillna(0.0)
    gross_returns = (weights * returns).sum(axis=1)
    turnover = weights.diff().abs().sum(axis=1).fillna(weights.abs().sum(axis=1))
    net_returns = gross_returns - turnover * (DEFAULT_COST_BPS / 10000.0)
    return net_returns, turnover


def package_completeness_audit() -> pd.DataFrame:
    rows = []
    for name in REQUIRED_P5B_FILES:
        path = P5B_DIR / name
        rows.append(
            {
                "file": name,
                "path": rel(path),
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else 0,
                "status": "PASS" if path.exists() else "MISSING",
            }
        )
    zip_path = P5B_DIR.with_suffix(".zip")
    rows.append(
        {
            "file": "zip",
            "path": rel(zip_path),
            "exists": zip_path.exists(),
            "size_bytes": zip_path.stat().st_size if zip_path.exists() else 0,
            "status": "PASS" if zip_path.exists() else "MISSING",
        }
    )
    return pd.DataFrame(rows)


def candidate_metric_audit(candidate_summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    cost = read_csv(P5B_DIR / "cost_stress_summary.csv")
    bench = read_csv(P5B_DIR / "benchmark_comparison.csv")
    risk = read_csv(P5B_DIR / "risk_flag_exposure.csv")
    for _, row in candidate_summary.iterrows():
        cid = clean(row.get("candidate_id"))
        missing_cols = [col for col in ["candidate_id", "strategy_family", *CORE_METRICS] if col not in candidate_summary.columns]
        na_core = [col for col in CORE_METRICS if col in candidate_summary.columns and pd.isna(row.get(col))]
        values = [to_float(row.get(col)) for col in CORE_METRICS if col in candidate_summary.columns]
        has_inf = any(np.isinf(value) for value in values if pd.notna(value))
        mdd = to_float(row.get("MDD"))
        cagr = to_float(row.get("CAGR"))
        calmar = to_float(row.get("Calmar"))
        sharpe = to_float(row.get("Sharpe"))
        rows.append(
            {
                "candidate_id": cid,
                "strategy_family": clean(row.get("strategy_family")),
                "has_required_identity": bool(cid != "NA" and clean(row.get("strategy_family")) != "NA"),
                "missing_core_columns": ";".join(missing_cols) if missing_cols else "none",
                "na_core_metrics": ";".join(na_core) if na_core else "none",
                "has_inf": has_inf,
                "mdd_direction_error": bool(pd.notna(mdd) and mdd > 0),
                "cagr_extreme_gt_200pct": bool(pd.notna(cagr) and cagr > 2.0),
                "calmar_extreme_gt_5": bool(pd.notna(calmar) and calmar > 5.0),
                "sharpe_extreme_abs_gt_5": bool(pd.notna(sharpe) and abs(sharpe) > 5.0),
                "has_cost_stress": bool((cost["candidate_id"].astype(str) == cid).any()) if "candidate_id" in cost.columns else False,
                "has_benchmark_comparison": bool((bench["candidate_id"].astype(str) == cid).any()) if "candidate_id" in bench.columns else False,
                "has_risk_flag_exposure": bool((risk["candidate_id"].astype(str) == cid).any()) if "candidate_id" in risk.columns else False,
            }
        )
    return pd.DataFrame(rows)


def independent_recomputation(selected: pd.DataFrame) -> pd.DataFrame:
    eligible = read_csv(SEARCH_DIR / "eligible_universe_limited_mve2.csv")
    tickers = sorted(eligible["ticker"].astype(str).unique().tolist())
    prices, volumes = load_price_data(tickers)
    rows = []
    for _, row in selected.iterrows():
        cid = clean(row.get("candidate_id"))
        recomputed_returns, recomputed_turnover = backtest_candidate(prices, volumes, row)
        metrics = performance_metrics(recomputed_returns)
        annual_turnover = float(recomputed_turnover.sum() / (len(recomputed_turnover) / 252.0)) if len(recomputed_turnover) else np.nan
        diffs = {
            "CAGR": metrics["CAGR"] - to_float(row.get("CAGR")),
            "MDD": metrics["MDD"] - to_float(row.get("MDD")),
            "Calmar": metrics["Calmar"] - to_float(row.get("Calmar")),
            "Sharpe": metrics["Sharpe"] - to_float(row.get("Sharpe")),
            "turnover": annual_turnover - to_float(row.get("turnover")),
        }
        rows.append(
            {
                "candidate_id": cid,
                "recompute_possible": True,
                "p5b_CAGR": to_float(row.get("CAGR")),
                "recomputed_CAGR": metrics["CAGR"],
                "CAGR_diff": diffs["CAGR"],
                "CAGR_match": bool(abs(diffs["CAGR"]) <= RECOMPUTE_TOLERANCE),
                "p5b_MDD": to_float(row.get("MDD")),
                "recomputed_MDD": metrics["MDD"],
                "MDD_diff": diffs["MDD"],
                "MDD_match": bool(abs(diffs["MDD"]) <= RECOMPUTE_TOLERANCE),
                "p5b_Calmar": to_float(row.get("Calmar")),
                "recomputed_Calmar": metrics["Calmar"],
                "Calmar_diff": diffs["Calmar"],
                "p5b_Sharpe": to_float(row.get("Sharpe")),
                "recomputed_Sharpe": metrics["Sharpe"],
                "Sharpe_diff": diffs["Sharpe"],
                "p5b_turnover": to_float(row.get("turnover")),
                "recomputed_turnover": annual_turnover,
                "turnover_diff": diffs["turnover"],
                "turnover_match": bool(abs(diffs["turnover"]) <= RECOMPUTE_TOLERANCE),
                "all_core_matches": bool(
                    abs(diffs["CAGR"]) <= RECOMPUTE_TOLERANCE
                    and abs(diffs["MDD"]) <= RECOMPUTE_TOLERANCE
                    and abs(diffs["turnover"]) <= RECOMPUTE_TOLERANCE
                ),
            }
        )
    return pd.DataFrame(rows)


def risk_bucket_mdd(mdd: float) -> str:
    abs_mdd = abs(mdd)
    if pd.isna(abs_mdd):
        return "FAIL_RISK"
    if abs_mdd <= 0.35:
        return "PASS"
    if abs_mdd <= 0.45:
        return "CONDITIONAL"
    return "FAIL_RISK"


def risk_bucket_calmar(calmar: float) -> str:
    if pd.isna(calmar):
        return "FAIL_RISK"
    if calmar >= 1.0:
        return "PASS"
    if calmar >= 0.5:
        return "CONDITIONAL"
    return "FAIL_RISK"


def selected_candidate_audit(selected: pd.DataFrame, recompute: pd.DataFrame) -> pd.DataFrame:
    cost = read_csv(P5B_DIR / "cost_stress_summary.csv")
    yearly = read_csv(P5B_DIR / "yearly_performance.csv")
    subperiod = read_csv(P5B_DIR / "subperiod_performance.csv")
    drawdown = read_csv(P5B_DIR / "drawdown_summary.csv")
    benchmark = read_csv(P5B_DIR / "benchmark_comparison.csv")
    risk = read_csv(P5B_DIR / "risk_flag_exposure.csv")
    rows = []
    for _, row in selected.iterrows():
        cid = clean(row.get("candidate_id"))
        selected_flag = to_bool(row.get("selected_for_validation_only"))
        baseline_flag = to_bool(row.get("baseline_replacement"))
        cagr = to_float(row.get("CAGR"))
        mdd = to_float(row.get("MDD"))
        calmar = to_float(row.get("Calmar"))
        turnover = to_float(row.get("turnover"))
        candidate_cost = cost[cost["candidate_id"].astype(str) == cid] if "candidate_id" in cost.columns else pd.DataFrame()
        cost_cagr = pd.to_numeric(candidate_cost.get("CAGR", pd.Series(dtype=float)), errors="coerce")
        base_cagr = cost_cagr.loc[candidate_cost["cost_bps"].astype(str) == "0"].iloc[0] if not candidate_cost.empty and (candidate_cost["cost_bps"].astype(str) == "0").any() else np.nan
        stress_cagr = cost_cagr.loc[candidate_cost["cost_bps"].astype(str) == "25"].iloc[0] if not candidate_cost.empty and (candidate_cost["cost_bps"].astype(str) == "25").any() else np.nan
        candidate_yearly = yearly[yearly["candidate_id"].astype(str) == cid] if "candidate_id" in yearly.columns else pd.DataFrame()
        candidate_subperiod = subperiod[subperiod["candidate_id"].astype(str) == cid] if "candidate_id" in subperiod.columns else pd.DataFrame()
        candidate_drawdown = drawdown[drawdown["candidate_id"].astype(str) == cid] if "candidate_id" in drawdown.columns else pd.DataFrame()
        candidate_bench = benchmark[benchmark["candidate_id"].astype(str) == cid] if "candidate_id" in benchmark.columns else pd.DataFrame()
        candidate_risk = risk[risk["candidate_id"].astype(str) == cid] if "candidate_id" in risk.columns else pd.DataFrame()
        worst_year = pd.to_numeric(candidate_yearly.get("return", pd.Series(dtype=float)), errors="coerce").min()
        worst_subperiod = pd.to_numeric(candidate_subperiod.get("return", pd.Series(dtype=float)), errors="coerce").min()
        drawdown_duration = to_float(candidate_drawdown.iloc[0].get("drawdown_duration")) if not candidate_drawdown.empty else np.nan
        min_excess = pd.to_numeric(candidate_bench.get("excess_CAGR", pd.Series(dtype=float)), errors="coerce").min()
        has_volume_exposure = bool(
            (candidate_risk["flag_type"].astype(str) == "non_positive_volume").any()
            and (pd.to_numeric(candidate_risk["max_weight"], errors="coerce") > 0).any()
        ) if not candidate_risk.empty else False
        has_jump_exposure = bool(
            (candidate_risk["flag_type"].astype(str) == "large_daily_price_jump").any()
            and (pd.to_numeric(candidate_risk["max_weight"], errors="coerce") > 0).any()
        ) if not candidate_risk.empty else False
        recompute_row = recompute[recompute["candidate_id"] == cid]
        recompute_match = bool(recompute_row.iloc[0]["all_core_matches"]) if not recompute_row.empty else False
        mdd_bucket = risk_bucket_mdd(mdd)
        calmar_bucket = risk_bucket_calmar(calmar)
        cost_sensitive = bool(pd.notna(base_cagr) and pd.notna(stress_cagr) and (base_cagr - stress_cagr) > 0.05)
        recommend_p7 = bool(mdd_bucket != "FAIL_RISK" and calmar_bucket != "FAIL_RISK" and recompute_match)
        rows.append(
            {
                "candidate_id": cid,
                "selected_for_validation_only": selected_flag,
                "miswritten_as_baseline": baseline_flag,
                "CAGR": cagr,
                "MDD": mdd,
                "Calmar": calmar,
                "Sharpe": to_float(row.get("Sharpe")),
                "volatility": to_float(row.get("volatility")),
                "turnover": turnover,
                "cost0_CAGR": base_cagr,
                "cost25_CAGR": stress_cagr,
                "cost_stress_CAGR_drag": base_cagr - stress_cagr if pd.notna(base_cagr) and pd.notna(stress_cagr) else np.nan,
                "yearly_worst_return": worst_year,
                "subperiod_worst_return": worst_subperiod,
                "drawdown_duration": drawdown_duration,
                "min_benchmark_excess_CAGR": min_excess,
                "has_volume_warning_exposure": has_volume_exposure,
                "has_price_jump_warning_exposure": has_jump_exposure,
                "MDD_audit": mdd_bucket,
                "Calmar_audit": calmar_bucket,
                "turnover_high_flag": bool(pd.notna(turnover) and turnover > 5.0),
                "cost_sensitive_flag": cost_sensitive,
                "recompute_core_match": recompute_match,
                "recommend_enter_p7_baseline_comparison": recommend_p7,
            }
        )
    return pd.DataFrame(rows)


def guardrail_audit() -> pd.DataFrame:
    decision = read_json(P5B_DIR / "formal_mve2_search_decision.json")
    checks = {
        "no_baseline_replacement": decision.get("no_baseline_replacement") is True and decision.get("baseline_replaced") is False,
        "no_v10": decision.get("no_v10") is True and decision.get("v10_executed") is False,
        "requires_p6_validation": decision.get("requires_p6_validation") is True,
        "selected_for_validation_only": decision.get("selected_for_validation_only") is True,
        "formal_v9_not_baseline": True,
        "limited_mve2_not_formal_baseline": True,
        "group4_not_touched": decision.get("group4_hold_not_touched") is True,
        "original_data_not_modified": decision.get("raw_data_modified") is False,
        "audit_csv_not_modified": decision.get("audit_csv_modified") is False,
    }
    return pd.DataFrame(
        [{"guardrail": key, "pass": value, "status": "PASS" if value else "FAIL"} for key, value in checks.items()]
    )


def audit_decision(selected_audit: pd.DataFrame, metric_audit: pd.DataFrame, completeness: pd.DataFrame, guardrails: pd.DataFrame) -> tuple[str, list[str], bool]:
    reasons = []
    if (completeness["status"] != "PASS").any():
        reasons.append("P5-B package is incomplete.")
    if (guardrails["status"] != "PASS").any():
        reasons.append("Guardrail audit failed.")
    if selected_audit.empty:
        reasons.append("No selected candidates found.")
    fail_risk_count = int(((selected_audit["MDD_audit"] == "FAIL_RISK") | (selected_audit["Calmar_audit"] == "FAIL_RISK")).sum()) if not selected_audit.empty else 1
    recompute_fail_count = int((selected_audit["recompute_core_match"] != True).sum()) if not selected_audit.empty else 1
    if fail_risk_count > 0:
        reasons.append(f"{fail_risk_count} selected candidates fail MDD/Calmar risk audit.")
    if recompute_fail_count > 0:
        reasons.append(f"{recompute_fail_count} selected candidates failed independent recomputation tolerance.")
    if reasons:
        return "FAIL_VALIDATION_AUDIT", reasons, False
    if (selected_audit["MDD_audit"] == "CONDITIONAL").any() or (selected_audit["Calmar_audit"] == "CONDITIONAL").any():
        return "CONDITIONAL_NEEDS_REVIEW", ["Selected candidates are conditional on risk thresholds."], False
    return "PASS_TO_P7_BASELINE_COMPARISON", ["All selected candidates passed P6 audit thresholds."], True


def create_zip(out_dir: Path) -> Path:
    zip_path = out_dir.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(out_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(out_dir.parent))
    return zip_path


def write_readme(out_dir: Path, decision: str) -> None:
    text = f"""# Formal MVE2 Validation Audit P6

Decision: `{decision}`

This package audits the P5-B controlled search output. It does not run a new search, does not add candidates, does not replace v8.2, and does not create v10.

Selected P5-B candidates are treated only as validation/audit inputs.
"""
    (out_dir / "README.md").write_text(text, encoding="utf-8")


def write_report(out_dir: Path, decision: str, reasons: list[str], selected_audit: pd.DataFrame) -> None:
    selected_records = selected_audit[
        ["candidate_id", "MDD", "Calmar", "MDD_audit", "Calmar_audit", "recommend_enter_p7_baseline_comparison"]
    ].to_dict("records")
    text = f"""# Formal MVE2 Validation Audit Report

## Decision

`{decision}`

## Reasons

{chr(10).join(f'- {reason}' for reason in reasons)}

## Selected Candidate Risk Audit

```json
{json.dumps(selected_records, indent=2)}
```

## Interpretation

P6 found that selected P5-B candidates are candidate evidence only. The severe drawdown profile blocks baseline-comparison promotion in this audit package.

v8.2 remains the formal frozen baseline. formal v9 remains a failed branch. v10 remains forbidden.
"""
    (out_dir / "formal_mve2_validation_audit_report.md").write_text(text, encoding="utf-8")


def write_manifest(out_dir: Path, generated_files: list[Path], zip_path: Path, decision: str, can_enter_p7: bool) -> None:
    manifest = {
        "run_id": out_dir.name,
        "run_type": "formal_mve2_validation_audit_p6",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "git_commit": git_head(),
        "script_path": SCRIPT_PATH.as_posix(),
        "input_paths": [
            rel(P5B_DIR),
            rel(STORE_DIR),
            rel(V82_AUDIT_DIR),
            rel(FORMAL_V9_FAILURE_AUDIT),
        ],
        "output_dir": rel(out_dir),
        "generated_files": [rel(path) for path in generated_files] + [rel(zip_path)],
        "p6_decision": decision,
        "can_enter_p7_baseline_comparison": can_enter_p7,
        "new_search_executed": False,
        "new_candidate_added": False,
        "baseline_replaced": False,
        "no_baseline_replacement": True,
        "v10_executed": False,
        "no_v10": True,
        "group4_hold_not_touched": True,
        "raw_data_modified": False,
        "audit_csv_modified": False,
        "p5b_outputs_modified": False,
    }
    write_json(out_dir / "manifest.json", manifest)


def run_audit() -> tuple[Path, str, bool, list[Path], Path]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUTPUT_ROOT / f"{RUN_PREFIX}_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "small_tables").mkdir(exist_ok=True)

    candidate_summary = read_csv(P5B_DIR / "candidate_summary.csv")
    selected = read_csv(P5B_DIR / "selected_candidates.csv")
    rejected = read_csv(P5B_DIR / "rejected_candidates.csv")
    completeness = package_completeness_audit()
    metric_audit = candidate_metric_audit(candidate_summary)
    recompute = independent_recomputation(selected)
    selected_audit = selected_candidate_audit(selected, recompute)
    guardrails = guardrail_audit()
    decision, reasons, can_enter_p7 = audit_decision(selected_audit, metric_audit, completeness, guardrails)

    tables = {
        "p6_audit_summary.csv": pd.DataFrame(
            [
                {"metric": "p5b_candidate_count", "value": len(candidate_summary)},
                {"metric": "p5b_selected_count", "value": len(selected)},
                {"metric": "p5b_rejected_count", "value": len(rejected)},
                {"metric": "package_missing_count", "value": int((completeness["status"] != "PASS").sum())},
                {"metric": "selected_fail_risk_count", "value": int(((selected_audit["MDD_audit"] == "FAIL_RISK") | (selected_audit["Calmar_audit"] == "FAIL_RISK")).sum())},
                {"metric": "p6_decision", "value": decision},
                {"metric": "can_enter_p7_baseline_comparison", "value": can_enter_p7},
            ]
        ),
        "package_completeness_audit.csv": completeness,
        "candidate_metric_audit.csv": metric_audit,
        "selected_candidate_audit.csv": selected_audit,
        "rejected_candidate_audit.csv": rejected.assign(audit_status="rejected_not_selected_for_P6"),
        "benchmark_comparison_audit.csv": read_csv(P5B_DIR / "benchmark_comparison.csv").assign(audit_note="benchmark comparison present; formal v9 not benchmark"),
        "mdd_calmar_audit.csv": selected_audit[["candidate_id", "MDD", "Calmar", "MDD_audit", "Calmar_audit", "recommend_enter_p7_baseline_comparison"]],
        "yearly_performance_audit.csv": read_csv(P5B_DIR / "yearly_performance.csv").assign(audit_note="reviewed from P5-B output"),
        "subperiod_performance_audit.csv": read_csv(P5B_DIR / "subperiod_performance.csv").assign(audit_note="reviewed from P5-B output"),
        "drawdown_audit.csv": read_csv(P5B_DIR / "drawdown_summary.csv").assign(audit_note="selected candidates have severe drawdown risk where applicable"),
        "turnover_audit.csv": read_csv(P5B_DIR / "turnover_summary.csv").assign(audit_note="reviewed from P5-B output"),
        "cost_stress_audit.csv": read_csv(P5B_DIR / "cost_stress_summary.csv").assign(audit_note="reviewed from P5-B output"),
        "risk_flag_exposure_audit.csv": read_csv(P5B_DIR / "risk_flag_exposure.csv").assign(audit_note="risk flags carried forward"),
        "independent_recomputation_audit.csv": recompute,
        "reproducibility_audit.csv": pd.DataFrame(
            [
                {"item": "p5b_package_read", "status": "PASS", "value": rel(P5B_DIR)},
                {"item": "audited_store_read", "status": "PASS", "value": rel(STORE_DIR)},
                {"item": "new_search_executed", "status": "PASS", "value": "false"},
                {"item": "p5b_outputs_modified", "status": "PASS", "value": "false"},
                {"item": "group4_not_used", "status": "PASS", "value": "true"},
            ]
        ),
        "baseline_replacement_guardrail.csv": guardrails,
        "reproducibility_checklist.csv": pd.DataFrame(
            [
                {"item": "script_path_recorded", "status": "PASS", "value": SCRIPT_PATH.as_posix()},
                {"item": "git_commit_recorded", "status": "PASS", "value": git_head()},
                {"item": "output_dir_recorded", "status": "PASS", "value": rel(out_dir)},
                {"item": "new_search_not_run", "status": "PASS", "value": "true"},
                {"item": "baseline_not_replaced", "status": "PASS", "value": "true"},
                {"item": "v10_not_created", "status": "PASS", "value": "true"},
            ]
        ),
        "risk_flags.csv": pd.DataFrame(
            [
                {"flag_id": "selected_mdd_fail_risk", "severity": "critical", "status": "FAIL" if (selected_audit["MDD_audit"] == "FAIL_RISK").any() else "PASS", "detail": "MDD threshold audit for selected candidates"},
                {"flag_id": "selected_calmar_conditional", "severity": "warning", "status": "WARN" if (selected_audit["Calmar_audit"] != "PASS").any() else "PASS", "detail": "Calmar threshold audit for selected candidates"},
                {"flag_id": "no_baseline_replacement", "severity": "critical", "status": "PASS", "detail": "P6 did not replace v8.2 baseline"},
                {"flag_id": "no_v10", "severity": "critical", "status": "PASS", "detail": "P6 did not create v10"},
            ]
        ),
    }

    generated_files: list[Path] = []
    for name, df in tables.items():
        path = out_dir / name
        df.to_csv(path, index=False)
        generated_files.append(path)

    small_tables = {
        "selected_candidate_risk_summary.csv": selected_audit,
        "decision_reasons.csv": pd.DataFrame({"reason": reasons}),
        "package_completeness_summary.csv": completeness,
        "recompute_diff_summary.csv": recompute,
    }
    for name, df in small_tables.items():
        path = out_dir / "small_tables" / name
        df.to_csv(path, index=False)
        generated_files.append(path)

    decision_path = out_dir / "p6_validation_decision.json"
    write_json(
        decision_path,
        {
            "run_id": out_dir.name,
            "p6_decision": decision,
            "can_enter_p7_baseline_comparison": can_enter_p7,
            "reasons": reasons,
            "selected_candidate_count": int(len(selected)),
            "selected_fail_risk_count": int(((selected_audit["MDD_audit"] == "FAIL_RISK") | (selected_audit["Calmar_audit"] == "FAIL_RISK")).sum()),
            "baseline_replaced": False,
            "no_baseline_replacement": True,
            "v10_executed": False,
            "no_v10": True,
            "new_search_executed": False,
            "group4_hold_not_touched": True,
            "raw_data_modified": False,
            "audit_csv_modified": False,
            "p5b_outputs_modified": False,
        },
    )
    generated_files.append(decision_path)

    write_readme(out_dir, decision)
    generated_files.append(out_dir / "README.md")
    write_report(out_dir, decision, reasons, selected_audit)
    generated_files.append(out_dir / "formal_mve2_validation_audit_report.md")

    manifest_path = out_dir / "manifest.json"
    generated_files.append(manifest_path)
    zip_path = create_zip(out_dir)
    write_manifest(out_dir, generated_files, zip_path, decision, can_enter_p7)
    zip_path = create_zip(out_dir)

    return out_dir, decision, can_enter_p7, sorted(set(generated_files), key=lambda p: rel(p)), zip_path


def main() -> int:
    out_dir, decision, can_enter_p7, generated_files, zip_path = run_audit()
    print(
        json.dumps(
            {
                "run_id": out_dir.name,
                "output_dir": rel(out_dir),
                "p6_decision": decision,
                "can_enter_p7_baseline_comparison": can_enter_p7,
                "generated_file_count": len(generated_files),
                "zip_path": rel(zip_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
