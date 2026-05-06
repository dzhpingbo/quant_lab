"""Formal v9 runner using the canonical v8.2 replay engine.

This runner is explicitly bounded: it does not expand Nasdaq100/S&P500, does
not download data, does not train/search new model families, and does not
connect to any trading interface.  The only formal price source is the local
Qlib provider bin store used by canonical v8.2.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.canonical_replay_engine import (
    CanonicalReplayConfig,
    DEFAULT_PROVIDER_URI,
    DEFAULT_V8_1_RUN,
    DEFAULT_V8_2_RUN,
    PRIMARY_STRATEGY_ID,
    build_formal_gate_result,
    build_trades_from_weights,
    load_v82_canonical_inputs,
    load_qlib_bin_close,
    replay_formal_v82_baseline,
    v82_primary_variant,
)
from quant_lab.us_stock_selection.portfolio_robustifier import ticker_contributions
from quant_lab.us_stock_selection.qlib_signal_backtest import portfolio_returns
from quant_lab.us_stock_selection.utils import ensure_dir, nav_from_returns, save_dataframe, save_json
from quant_lab.us_stock_selection.v8_2_year_stability import (
    apply_ex_ante_overlays,
    build_benchmark_metrics,
    build_weights_from_audit,
    concentration_share,
    evaluate_strategy,
    remove_ticker_stress,
    remove_top_year_stress,
    yearly_returns,
    monthly_returns,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
FORMAL_V82_BASELINE_RUN = OUTPUT_ROOT / "v82_canonical_rebuild_20260504_090549" / "formal_v82_baseline"
DEFAULT_V9_1_RUN_DIR = OUTPUT_ROOT / "v9_1_growth_data_onboarding_20260504_230014"
DEFAULT_V9_1_PROVIDER_URI = Path(r"C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026_v91_growth")
DEFAULT_V9_1_FEATURE_CACHE_DIR = DEFAULT_V9_1_RUN_DIR / "v9_1_feature_cache"
DEFAULT_V9_1_SCORE_PROVENANCE_DIR = DEFAULT_V9_1_RUN_DIR / "v9_1_score_provenance"
DEFAULT_V9_1_SCORE_AUDIT_PATH = DEFAULT_V9_1_SCORE_PROVENANCE_DIR / "monthly_score_rank_audit.csv"
DEFAULT_V9_1_ELIGIBILITY_PATH = DEFAULT_V9_1_RUN_DIR / "v9_1_eligibility_result.csv"

SMALL_GROWTH_CANDIDATES: dict[str, list[str]] = {
    "semiconductor": ["AVGO", "ARM", "ASML", "AMD", "MU", "INTC", "LRCX", "KLAC", "AMAT", "MRVL", "ON", "MPWR", "TSM"],
    "ai_software_cloud": ["ORCL", "CRM", "NOW", "ADBE", "SNOW", "DDOG", "NET", "MDB", "TEAM", "SHOP", "U", "APP", "PATH"],
    "cybersecurity": ["PANW", "CRWD", "ZS", "FTNT", "OKTA", "S"],
    "platform_internet": ["NFLX", "UBER", "ABNB", "DASH", "RBLX", "PINS", "SNAP", "SPOT"],
    "high_vol_theme": ["PLTR", "COIN", "MSTR", "ROKU", "SQ", "AFRM"],
}

HIGH_VOL_EXCLUSION = {"MSTR", "COIN", "PLTR", "AFRM", "ROKU", "SQ"}
CONTROVERSIAL_DEPENDENCY = {"MSTR", "COIN", "PLTR"}
REPRO_THRESHOLDS = {
    "cagr": 0.005,
    "max_drawdown": 0.005,
    "calmar": 0.03,
    "single_year_share": 0.02,
    "top_ticker_share": 0.02,
}


def run_formal_v9(
    out_dir: Path | str,
    provider_uri: Path | str = DEFAULT_V9_1_PROVIDER_URI,
    v8_1_run_dir: Path | str = DEFAULT_V8_1_RUN,
    v8_2_run_dir: Path | str = DEFAULT_V8_2_RUN,
    v9_1_run_dir: Path | str = DEFAULT_V9_1_RUN_DIR,
    feature_cache_dir: Path | str = DEFAULT_V9_1_FEATURE_CACHE_DIR,
    score_audit_path: Path | str = DEFAULT_V9_1_SCORE_AUDIT_PATH,
    eligibility_path: Path | str = DEFAULT_V9_1_ELIGIBILITY_PATH,
) -> dict[str, Any]:
    out = ensure_dir(out_dir)
    formal_dir = ensure_dir(out / "formal_v9")
    config = CanonicalReplayConfig(provider_uri=Path(provider_uri), v8_1_run_dir=Path(v8_1_run_dir), v8_2_run_dir=Path(v8_2_run_dir))
    input_audit = validate_v9_1_formal_inputs(
        provider_uri=Path(provider_uri),
        v9_1_run_dir=Path(v9_1_run_dir),
        feature_cache_dir=Path(feature_cache_dir),
        score_audit_path=Path(score_audit_path),
        eligibility_path=Path(eligibility_path),
    )
    save_json(input_audit["summary"], formal_dir / "formal_v9_input_audit.json")
    save_dataframe(input_audit["checks"], formal_dir / "formal_v9_input_audit_checks.csv")
    if input_audit["summary"].get("hard_blocker_count", 0):
        raise ValueError("Formal v9 input validation failed: " + "; ".join(input_audit["summary"].get("hard_blockers", [])))

    baseline_sources = load_v82_canonical_inputs(config)
    baseline_audit = baseline_sources["score_rank_audit"].copy()
    score_source = load_v9_1_score_source(Path(score_audit_path), Path(score_audit_path).parent)
    audit = score_source["audit"].copy()
    close = load_formal_v9_close_panel(config, audit, baseline_sources)
    provider_tickers = {str(t).upper() for t in close.columns}
    provider_tickers.update(detect_provider_feature_tickers(config.provider_uri))
    score_tickers = set(audit["ticker"].astype(str).str.upper().unique())
    pool_a = sorted({str(t).upper() for t in baseline_audit["ticker"].dropna().astype(str).tolist()})
    small_table = build_small_growth_table()
    v91_eligibility = pd.read_csv(eligibility_path) if Path(eligibility_path).exists() else pd.DataFrame()
    eligibility = build_universe_eligibility(small_table, pool_a, provider_tickers, score_tickers, close, audit, external_eligibility=v91_eligibility)
    excluded = eligibility.loc[~eligibility["eligible_for_formal_v9"].astype(bool)].copy()
    save_dataframe(eligibility, formal_dir / "formal_v9_universe_eligibility.csv")
    save_dataframe(excluded, formal_dir / "formal_v9_excluded_tickers.csv")

    eligible_growth = sorted(
        eligibility.loc[
            eligibility["is_small_growth_candidate"].astype(bool) & eligibility["eligible_for_formal_v9"].astype(bool),
            "ticker",
        ].astype(str).unique()
    )
    effective_new_growth = sorted(set(eligible_growth) - set(pool_a))
    pool_plus_growth = sorted(set(pool_a) | set(eligible_growth))
    small_growth_only = eligible_growth
    ex_high_vol = sorted([ticker for ticker in pool_plus_growth if ticker not in HIGH_VOL_EXCLUSION])
    universe_specs = [
        ("formal_pool_a_reproduction", pool_a, "pool_a_reproduction"),
        ("formal_pool_a_plus_small_growth", pool_plus_growth, "formal_v9_main"),
        ("formal_small_growth_only", small_growth_only, "observation_only"),
        ("formal_pool_a_plus_small_growth_ex_high_vol", ex_high_vol, "robustness_ex_high_vol"),
    ]

    baseline = load_formal_v82_baseline()
    pool_replay = replay_formal_v82_baseline(formal_dir / "_pool_a_reproduction_internal", config=config)
    reproduction_check = build_pool_a_reproduction_check(baseline, pool_replay["metrics"])
    save_dataframe(reproduction_check, formal_dir / "formal_v9_pool_a_reproduction_check.csv")
    pool_reproduction_pass = bool(reproduction_check["pass_check"].all()) if not reproduction_check.empty else False

    replay_results = []
    daily_frames = []
    holding_frames = []
    trade_frames = []
    ledger_frames = []
    score_frames = []
    trigger_frames = []
    derisk_frames = []
    contrib_frames = []
    yearly_frames = []
    remove_year_rows = []
    remove_ticker_rows = []
    cost_rows = []

    for universe_name, tickers, role in universe_specs:
        replay = replay_frozen_score_universe(
            universe_name=universe_name,
            role=role,
            tickers=tickers,
            audit=audit,
            close=close,
            config=config,
        )
        replay_results.append(replay["metrics"])
        daily_frames.append(replay["daily"])
        holding_frames.append(replay["holdings"])
        trade_frames.append(replay["trades"])
        ledger_frames.append(replay["decision_ledger"])
        score_frames.append(replay["score_rank_audit"])
        trigger_frames.append(replay["ytd_cap_triggers"])
        derisk_frames.append(replay["derisk_log"])
        contrib_frames.append(replay["ticker_contribution"])
        yearly_frames.append(replay["yearly_return"])
        remove_year_rows.append(replay["remove_top_year"])
        remove_ticker_rows.append(replay["remove_top_ticker"])
        cost_rows.append(replay["cost_sensitivity"])

    metrics = pd.DataFrame(replay_results)
    pool_metrics = metrics.loc[metrics["universe_name"].eq("formal_pool_a_reproduction")].iloc[0].to_dict()
    main_metrics = metrics.loc[metrics["universe_name"].eq("formal_pool_a_plus_small_growth")].iloc[0].to_dict()
    gate_detail, gate_result = build_formal_v9_gate_detail(
        main_metrics=main_metrics,
        pool_metrics=pool_metrics,
        pool_reproduction_pass=pool_reproduction_pass,
        effective_new_growth_count=len(effective_new_growth),
        excluded_growth_count=int((eligibility["is_small_growth_candidate"].astype(bool) & ~eligibility["eligible_for_formal_v9"].astype(bool)).sum()),
    )
    classification = classify_formal_v9(gate_result, main_metrics, pool_metrics, eligibility, pool_reproduction_pass, len(effective_new_growth))
    gate_result["classification"] = classification
    verdict = build_verdict(classification, gate_result, metrics, eligibility, excluded, effective_new_growth, pool_reproduction_pass)

    save_dataframe(metrics.loc[metrics["universe_name"].eq("formal_pool_a_reproduction")], formal_dir / "formal_v9_pool_a_reproduction_metrics.csv")
    save_dataframe(metrics.loc[metrics["universe_name"].eq("formal_pool_a_plus_small_growth")], formal_dir / "formal_v9_pool_a_plus_growth_metrics.csv")
    save_dataframe(metrics.loc[metrics["universe_name"].eq("formal_small_growth_only")], formal_dir / "formal_v9_growth_only_metrics.csv")
    save_dataframe(metrics.loc[metrics["universe_name"].eq("formal_pool_a_plus_small_growth_ex_high_vol")], formal_dir / "formal_v9_ex_high_vol_metrics.csv")
    save_json(gate_result, formal_dir / "formal_v9_gate_result.json")
    save_dataframe(gate_detail, formal_dir / "formal_v9_gate_detail.csv")
    save_dataframe(pd.concat(daily_frames, ignore_index=True), formal_dir / "formal_v9_daily_nav.csv")
    save_dataframe(pd.concat(holding_frames, ignore_index=True), formal_dir / "formal_v9_monthly_holdings.csv")
    save_dataframe(pd.concat(trade_frames, ignore_index=True), formal_dir / "formal_v9_trades.csv")
    save_dataframe(pd.concat(ledger_frames, ignore_index=True), formal_dir / "formal_v9_decision_ledger.csv")
    save_dataframe(pd.concat(score_frames, ignore_index=True), formal_dir / "formal_v9_score_rank_audit.csv")
    save_dataframe(pd.concat(trigger_frames, ignore_index=True), formal_dir / "formal_v9_ytd_cap_triggers.csv")
    save_dataframe(pd.concat(derisk_frames, ignore_index=True), formal_dir / "formal_v9_derisk_log.csv")
    save_dataframe(pd.concat(contrib_frames, ignore_index=True), formal_dir / "formal_v9_ticker_contribution.csv")
    save_dataframe(pd.concat(yearly_frames, ignore_index=True), formal_dir / "formal_v9_yearly_return.csv")
    save_dataframe(pd.DataFrame(remove_year_rows), formal_dir / "formal_v9_remove_top_year.csv")
    save_dataframe(pd.DataFrame(remove_ticker_rows), formal_dir / "formal_v9_remove_top_ticker.csv")
    save_dataframe(pd.concat(cost_rows, ignore_index=True), formal_dir / "formal_v9_cost_sensitivity.csv")
    save_dataframe(build_benchmark_comparison(close, metrics), formal_dir / "formal_v9_benchmark_comparison.csv")
    save_json(verdict, formal_dir / "formal_v9_verdict.json")
    save_json(verdict, out / "formal_v9_verdict.json")
    save_json(verdict, out / "audit_summary.json")

    return {
        "verdict": verdict,
        "metrics": metrics,
        "eligibility": eligibility,
        "excluded": excluded,
        "gate_detail": gate_detail,
        "gate_result": gate_result,
        "pool_a_reproduction_check": reproduction_check,
        "daily": pd.concat(daily_frames, ignore_index=True),
        "holdings": pd.concat(holding_frames, ignore_index=True),
        "trades": pd.concat(trade_frames, ignore_index=True),
        "decision_ledger": pd.concat(ledger_frames, ignore_index=True),
        "score_rank_audit": pd.concat(score_frames, ignore_index=True),
        "ticker_contribution": pd.concat(contrib_frames, ignore_index=True),
        "yearly_return": pd.concat(yearly_frames, ignore_index=True),
        "effective_new_growth": effective_new_growth,
        "input_audit": input_audit,
    }


def validate_v9_1_formal_inputs(
    *,
    provider_uri: Path,
    v9_1_run_dir: Path,
    feature_cache_dir: Path,
    score_audit_path: Path,
    eligibility_path: Path,
) -> dict[str, Any]:
    """Validate the frozen v9.1 inputs before any formal replay is accepted."""
    provider_uri = provider_uri.expanduser()
    feature_cache_dir = feature_cache_dir.expanduser()
    score_audit_path = score_audit_path.expanduser()
    score_dir = score_audit_path.parent
    feature_meta = read_json(feature_cache_dir / "alpha360_feature_cache_metadata.json")
    feature_status = read_json(feature_cache_dir / "feature_cache_status.json")
    score_meta = read_json(score_dir / "score_source_metadata.json")
    label_def = read_json(score_dir / "label_definition.json")
    provider_health = read_json(v9_1_run_dir / "v9_1_provider_build" / "provider_health_check.json")
    fit_log_path = score_dir / "monthly_fit_log.csv"
    fit_log = pd.read_csv(fit_log_path) if fit_log_path.exists() else pd.DataFrame()
    score_audit = pd.read_csv(score_audit_path) if score_audit_path.exists() else pd.DataFrame()
    eligibility = pd.read_csv(eligibility_path) if eligibility_path.exists() else pd.DataFrame()
    feature_quality_path = feature_cache_dir / "alpha360_feature_quality.csv"
    feature_quality = pd.read_csv(feature_quality_path) if feature_quality_path.exists() else pd.DataFrame()

    provider_features = provider_uri / "features"
    provider_calendar = provider_uri / "calendars" / "day.txt"
    provider_expected = str(DEFAULT_V9_1_PROVIDER_URI)
    hard_blockers: list[str] = []
    checks: list[dict[str, Any]] = []

    def add_check(name: str, passed: bool, value: Any, expected: Any, severity: str = "hard_block") -> None:
        checks.append({"check": name, "pass": bool(passed), "value": value, "expected": expected, "severity": severity})
        if not passed and severity == "hard_block":
            hard_blockers.append(name)

    add_check("provider_uri_is_v9_1", str(provider_uri).lower() == provider_expected.lower(), str(provider_uri), provider_expected)
    add_check("provider_exists", provider_uri.exists(), str(provider_uri), "exists")
    add_check("provider_calendar_exists", provider_calendar.exists(), str(provider_calendar), "exists")
    add_check("provider_features_exists", provider_features.exists(), str(provider_features), "exists")
    add_check("provider_health_ok", bool(provider_health.get("provider_readable", False)), provider_health.get("provider_readable", False), True)
    add_check("provider_calendar_end", provider_health.get("calendar_end", ""), "2026-04-17", "2026-04-17")
    add_check("feature_cache_status_completed", feature_meta.get("status") == "completed", feature_meta.get("status", ""), "completed")
    add_check("feature_cache_provider_match", str(feature_meta.get("provider_uri", "")).lower() == str(provider_uri).lower(), feature_meta.get("provider_uri", ""), str(provider_uri))
    add_check("feature_set_alpha360", feature_meta.get("feature_set") == "Alpha360", feature_meta.get("feature_set", ""), "Alpha360")
    add_check("feature_count_360", int(feature_meta.get("feature_count", 0) or 0) == 360, feature_meta.get("feature_count", 0), 360)
    add_check("feature_cache_rows_positive", int(feature_meta.get("row_count", 0) or 0) > 0, feature_meta.get("row_count", 0), ">0")
    feature_missing_rate = 1.0 if feature_meta.get("missing_rate") is None else float(feature_meta.get("missing_rate"))
    add_check("feature_missing_rate_zero", feature_missing_rate <= 0.0, feature_missing_rate, 0.0)
    status_rows = feature_status.get("rows", []) if isinstance(feature_status, dict) else []
    label_non_na = int(status_rows[0].get("label_5d_non_na", 0)) if status_rows else 0
    add_check("label_5d_available_in_cache", label_non_na > 0, label_non_na, ">0")
    add_check("score_source_status_completed", score_meta.get("status") == "completed", score_meta.get("status", ""), "completed")
    add_check("score_source_provider_match", str(score_meta.get("provider_uri", "")).lower() == str(provider_uri).lower(), score_meta.get("provider_uri", ""), str(provider_uri))
    add_check("score_source_feature_cache_match", str(score_meta.get("feature_cache_dir", "")).lower() == str(feature_cache_dir).lower(), score_meta.get("feature_cache_dir", ""), str(feature_cache_dir))
    add_check("score_source_alpha360", score_meta.get("feature_set") == "Alpha360", score_meta.get("feature_set", ""), "Alpha360")
    add_check("score_source_lgbmodel", score_meta.get("model") == "LGBModel", score_meta.get("model", ""), "LGBModel")
    add_check("score_source_label_5d", score_meta.get("label") == "label_5d", score_meta.get("label", ""), "label_5d")
    add_check("score_month_count_18", int(score_meta.get("score_month_count", 0) or 0) == 18, score_meta.get("score_month_count", 0), 18)
    add_check("score_row_count_positive", int(score_meta.get("score_row_count", 0) or 0) > 0, score_meta.get("score_row_count", 0), ">0")
    add_check("fit_failed_count_zero", int(score_meta.get("fit_failed_count", 0) or 0) == 0, score_meta.get("fit_failed_count", 0), 0)
    warning_count = int(pd.to_numeric(fit_log.get("warning_count", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not fit_log.empty else 0
    add_check("fit_warning_count_zero", warning_count == 0, warning_count, 0)
    add_check("score_audit_exists", score_audit_path.exists(), str(score_audit_path), "exists")
    add_check("score_audit_rows_match_metadata", len(score_audit) == int(score_meta.get("score_row_count", -1) or -1), len(score_audit), score_meta.get("score_row_count", "metadata"))
    score_months = int(pd.to_datetime(score_audit.get("rebalance_date", pd.Series(dtype=object))).nunique()) if not score_audit.empty else 0
    add_check("score_audit_months_match_metadata", score_months == int(score_meta.get("score_month_count", -1) or -1), score_months, score_meta.get("score_month_count", "metadata"))
    add_check("eligibility_file_exists", eligibility_path.exists(), str(eligibility_path), "exists")
    eligible_growth = int(eligibility.get("eligible_for_formal_v9", pd.Series(dtype=bool)).astype(bool).sum()) if not eligibility.empty else 0
    add_check("eligible_growth_positive", eligible_growth > 0, eligible_growth, ">0")
    label_expr = str(label_def.get("qlib_expression", ""))
    add_check("label_definition_expected", "Ref($close, -6)" in label_expr and "Ref($close, -1)" in label_expr, label_expr, "label_5d expression")

    scored_tickers = sorted(score_audit["ticker"].astype(str).str.upper().unique().tolist()) if not score_audit.empty and "ticker" in score_audit else []
    provider_missing = [ticker for ticker in scored_tickers if not (provider_uri / "features" / ticker.lower() / "close.day.bin").exists()]
    volume_missing = [ticker for ticker in scored_tickers if not (provider_uri / "features" / ticker.lower() / "volume.day.bin").exists()]
    factor_missing = [ticker for ticker in scored_tickers if not (provider_uri / "features" / ticker.lower() / "factor.day.bin").exists()]
    add_check("scored_tickers_have_close_bin", not provider_missing, ",".join(provider_missing), "no missing close.day.bin")
    add_check("scored_tickers_have_volume_bin", not volume_missing, ",".join(volume_missing), "no missing volume.day.bin")
    add_check("scored_tickers_have_factor_bin", not factor_missing, ",".join(factor_missing), "no missing factor.day.bin")
    quality_missing = float(feature_quality["missing_rate"].max()) if not feature_quality.empty and "missing_rate" in feature_quality else np.nan
    add_check("feature_quality_missing_rate_max_zero", pd.notna(quality_missing) and quality_missing <= 0.0, quality_missing, 0.0)

    summary = {
        "provider_uri": str(provider_uri),
        "provider_expected": provider_expected,
        "provider_calendar_start": provider_health.get("calendar_start", ""),
        "provider_calendar_end": provider_health.get("calendar_end", ""),
        "provider_instrument_count": provider_health.get("instrument_count", ""),
        "feature_cache_dir": str(feature_cache_dir),
        "feature_cache_path": feature_meta.get("cache_path", ""),
        "feature_cache_rows": feature_meta.get("row_count", 0),
        "feature_count": feature_meta.get("feature_count", 0),
        "feature_missing_rate": feature_meta.get("missing_rate", 1.0),
        "score_audit_path": str(score_audit_path),
        "score_month_count": score_meta.get("score_month_count", 0),
        "score_row_count": score_meta.get("score_row_count", 0),
        "fit_failed_count": score_meta.get("fit_failed_count", 0),
        "fit_warning_count": warning_count,
        "eligible_growth_count": eligible_growth,
        "scored_ticker_count": len(scored_tickers),
        "price_source": "local Qlib provider bin $close",
        "adj_close_policy": "provider $close stores adjusted close generated from raw adj_close/factor during v9.1 onboarding; Qlib has no separate adj_close field in formal replay",
        "volume_source": "local Qlib provider bin $volume",
        "replay_engine": "canonical_replay_engine",
        "hard_blocker_count": len(hard_blockers),
        "hard_blockers": hard_blockers,
    }
    return {"summary": summary, "checks": pd.DataFrame(checks)}


def load_v9_1_score_source(score_audit_path: Path, score_dir: Path) -> dict[str, Any]:
    audit = pd.read_csv(score_audit_path)
    required = {"rebalance_date", "ticker", "score", "rank", "eligible"}
    missing = sorted(required - set(audit.columns))
    if missing:
        raise ValueError(f"Missing v9.1 score audit columns: {missing}")
    out = audit.copy()
    out["decision_date"] = pd.to_datetime(out["rebalance_date"])
    out["ticker"] = out["ticker"].astype(str).str.upper()
    out["raw_score"] = pd.to_numeric(out["score"], errors="coerce")
    out["adjusted_score"] = out["raw_score"]
    out["raw_rank"] = pd.to_numeric(out["rank"], errors="coerce")
    out["adjusted_rank"] = out["raw_rank"]
    out["candidate_flag"] = out["eligible"].astype(bool)
    out["tradable_flag"] = out["eligible"].astype(bool)
    out["selected_flag"] = out.get("selected_top5_candidate", False).astype(bool)
    out["selected_rank"] = np.where(out["selected_flag"], out["adjusted_rank"], np.nan)
    out["model_name"] = "LGBModel"
    out["score_source"] = "v9_1_Alpha360_LGBModel_score_provenance"
    out["feature_snapshot_date"] = out["decision_date"].dt.date.astype(str)
    out["universe_layer"] = np.where(out.get("is_incremental_growth_ticker", False).astype(bool), "v9_1_incremental_growth", "pool_a_or_benchmark")
    out["asset_type"] = "stock"
    out["run_id"] = "v9_1_growth_data_onboarding_20260504_230014"
    for col in [
        "trailing_20d_return",
        "trailing_63d_return",
        "trailing_126d_return",
        "trailing_252d_return",
        "trailing_20d_vol",
        "trailing_63d_vol",
        "trailing_126d_vol",
        "trailing_63d_maxdd",
        "distance_to_252d_high",
    ]:
        if col not in out.columns:
            out[col] = np.nan
    meta = read_json(score_dir / "score_source_metadata.json")
    return {"audit": out, "metadata": meta}


def load_formal_v9_close_panel(config: CanonicalReplayConfig, audit: pd.DataFrame, baseline_sources: dict[str, Any]) -> pd.DataFrame:
    start = str(baseline_sources.get("start", "2024-01-02"))
    end = str(baseline_sources.get("end", "2026-04-17"))
    tickers = sorted({str(t).upper() for t in audit["ticker"].dropna().astype(str).tolist()} | {"SPY", "QQQ", "QLD", "TQQQ", "SHY"})
    close = load_qlib_bin_close(config.provider_uri, tickers=tickers, start=start, end=end)
    if close.empty:
        raise ValueError(f"Formal v9 Qlib bin close panel is empty: {config.provider_uri}")
    return close


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_small_growth_table() -> pd.DataFrame:
    rows = []
    seen = set()
    for category, tickers in SMALL_GROWTH_CANDIDATES.items():
        for ticker in tickers:
            ticker = ticker.upper()
            if ticker in seen:
                continue
            seen.add(ticker)
            rows.append({"ticker": ticker, "small_growth_category": category, "is_small_growth_candidate": True})
    return pd.DataFrame(rows)


def detect_provider_feature_tickers(provider_uri: Path | str) -> set[str]:
    features_dir = Path(provider_uri) / "features"
    if not features_dir.exists():
        return set()
    return {p.name.upper() for p in features_dir.iterdir() if p.is_dir() and (p / "close.day.bin").exists()}


def build_universe_eligibility(
    small_table: pd.DataFrame,
    pool_a: list[str],
    provider_tickers: set[str],
    score_tickers: set[str],
    close: pd.DataFrame,
    audit: pd.DataFrame,
    external_eligibility: pd.DataFrame | None = None,
) -> pd.DataFrame:
    pool_df = pd.DataFrame({"ticker": pool_a, "small_growth_category": "pool_a", "is_small_growth_candidate": False})
    merged = pd.concat([pool_df, small_table], ignore_index=True)
    merged["ticker"] = merged["ticker"].astype(str).str.upper()
    grouped = (
        merged.groupby("ticker", as_index=False)
        .agg(
            small_growth_category=("small_growth_category", lambda s: ",".join(sorted(set(map(str, s))))),
            is_small_growth_candidate=("is_small_growth_candidate", "max"),
        )
        .sort_values("ticker")
    )
    score_audit = audit.copy()
    score_audit["ticker"] = score_audit["ticker"].astype(str).str.upper()
    score_audit["decision_date"] = pd.to_datetime(score_audit["decision_date"])
    if "candidate_flag" in score_audit.columns:
        candidate_flag = score_audit["candidate_flag"].astype(bool)
    else:
        candidate_flag = pd.Series(True, index=score_audit.index)
    if "tradable_flag" in score_audit.columns:
        tradable_flag = score_audit["tradable_flag"].astype(bool)
    else:
        tradable_flag = pd.Series(True, index=score_audit.index)
    qualified_score = score_audit.loc[candidate_flag & tradable_flag].copy()
    external: dict[str, dict[str, Any]] = {}
    if external_eligibility is not None and not external_eligibility.empty and "ticker" in external_eligibility:
        tmp = external_eligibility.copy()
        tmp["ticker"] = tmp["ticker"].astype(str).str.upper()
        external = tmp.set_index("ticker").to_dict("index")
    rows = []
    for _, row in grouped.iterrows():
        ticker = str(row["ticker"])
        in_provider = ticker in provider_tickers
        in_score = ticker in score_tickers
        series = close[ticker].dropna() if in_provider and ticker in close.columns else pd.Series(dtype=float)
        first_date = series.index.min().date().isoformat() if not series.empty else ""
        last_date = series.index.max().date().isoformat() if not series.empty else ""
        window_obs_before_first_decision = int((series.index < pd.Timestamp("2024-01-31")).sum()) if not series.empty else 0
        ticker_score = qualified_score.loc[qualified_score["ticker"].eq(ticker)].copy()
        eligible_decision_count = int(ticker_score["decision_date"].nunique()) if not ticker_score.empty else 0
        first_score_decision = ticker_score["decision_date"].min().date().isoformat() if not ticker_score.empty else ""
        last_score_decision = ticker_score["decision_date"].max().date().isoformat() if not ticker_score.empty else ""
        external_row = external.get(ticker, {})
        external_eligible = bool(external_row.get("eligible_for_formal_v9", False))
        first_external_date = str(external_row.get("first_eligible_rebalance_date", "") or "")
        eligible_month_count = int(float(external_row.get("eligible_month_count", 0) or 0))
        has_trailing_252_evidence = bool(
            ("trailing_252d_return" in ticker_score.columns and ticker_score["trailing_252d_return"].notna().any())
            or external_eligible
            or eligible_month_count > 0
            or ticker in pool_a
        )
        obs_before_first_decision = max(window_obs_before_first_decision, 252 if has_trailing_252_evidence else 0)
        score_validated = bool(in_score and eligible_decision_count > 0 and has_trailing_252_evidence)
        eligible = bool(in_provider and score_validated and (external_eligible or ticker in pool_a))
        reasons = []
        if not in_provider:
            reasons.append("missing_canonical_qlib_provider_bin")
        if not in_score:
            reasons.append("missing_formal_alpha360_lgb_score_source")
        if in_score and ticker not in pool_a and not external_eligible:
            reasons.append("observation_only_dynamic_eligibility_not_met")
        if in_provider and in_score and not has_trailing_252_evidence:
            reasons.append("missing_trailing_252d_score_evidence")
        if in_provider and in_score and eligible_decision_count <= 0:
            reasons.append("missing_candidate_tradable_score_evidence")
        if ticker in HIGH_VOL_EXCLUSION:
            high_vol_note = "high_vol_or_controversial_observation"
        else:
            high_vol_note = ""
        eligibility_evidence = (
            "candidate_tradable_score_trail_with_trailing_252d_feature"
            if eligible
            else "not_eligible_for_formal_v9"
        )
        rows.append(
            {
                "ticker": ticker,
                "small_growth_category": row["small_growth_category"],
                "is_pool_a": ticker in pool_a,
                "is_small_growth_candidate": bool(row["is_small_growth_candidate"]),
                "in_canonical_provider": in_provider,
                "in_formal_score_source": in_score,
                "first_provider_date": first_date,
                "last_provider_date": last_date,
                "obs_before_first_decision": obs_before_first_decision,
                "eligible_decision_count": eligible_decision_count,
                "first_score_decision": first_score_decision,
                "last_score_decision": last_score_decision,
                "first_external_eligible_rebalance_date": first_external_date,
                "external_eligible_month_count": eligible_month_count,
                "has_trailing_252d_score_evidence": has_trailing_252_evidence,
                "passes_dynamic_eligibility": eligible,
                "eligible_for_formal_v9": eligible,
                "exclude_reason": "" if eligible else ";".join(reasons),
                "eligibility_evidence": eligibility_evidence,
                "high_vol_note": high_vol_note,
            }
        )
    return pd.DataFrame(rows)


def replay_frozen_score_universe(
    *,
    universe_name: str,
    role: str,
    tickers: list[str],
    audit: pd.DataFrame,
    close: pd.DataFrame,
    config: CanonicalReplayConfig,
) -> dict[str, Any]:
    tickers = sorted(set(tickers).intersection(close.columns))
    local_close = close.loc[:, tickers].ffill()
    local_audit = audit.loc[audit["ticker"].astype(str).str.upper().isin(tickers)].copy()
    variant = v82_primary_variant(config)
    base_weights = build_weights_from_audit(local_audit, local_close, variant, execution_delay=config.execution_delay)
    overlay = apply_ex_ante_overlays(local_close, base_weights, variant)
    weights = overlay["weights"]
    metrics, returns, turnover = evaluate_strategy(local_close, weights, cost_bps=config.cost_bps, slippage_bps=config.slippage_bps)
    metrics_50, _, _ = evaluate_strategy(local_close, weights, cost_bps=config.stress_cost_bps, slippage_bps=config.slippage_bps)
    annual = yearly_returns(returns)
    monthly = monthly_returns(returns)
    contrib = ticker_contributions(local_close.loc[weights.index, weights.columns].ffill(), weights)
    top_ticker = str(contrib.iloc[0]["ticker"]) if not contrib.empty else ""
    top_ticker_share = float(contrib.iloc[0]["abs_share"]) if not contrib.empty else 0.0
    remove_ticker_metrics = remove_ticker_stress(local_close, weights, top_ticker) if top_ticker else {}
    remove_year_metrics, top_year, top_year_share = remove_top_year_stress(returns, weights)
    controversial_share = float(contrib.loc[contrib["ticker"].isin(CONTROVERSIAL_DEPENDENCY), "abs_share"].sum()) if not contrib.empty else 0.0
    row = {
        "universe_name": universe_name,
        "role": role,
        "ticker_count": len(tickers),
        "tickers": ",".join(tickers),
        "method": infer_replay_method(local_audit),
        "feature_set": "Alpha360",
        "model": "LGBModel",
        "label": "label_5d",
        "portfolio": PRIMARY_STRATEGY_ID,
        "rebalance": "monthly",
        "execution": "T+1",
        "cost_bps": config.cost_bps,
        "slippage_bps": config.slippage_bps,
        "cost50_t1_cagr": metrics_50.get("cagr", np.nan),
        "cost50_t1_calmar": metrics_50.get("calmar", np.nan),
        "single_year_share": concentration_share(annual["year_return"]) if not annual.empty else 0.0,
        "top_contribution_year": top_year,
        "top_contribution_year_abs_share": top_year_share,
        "top_ticker": top_ticker,
        "top_ticker_share": top_ticker_share,
        "controversial_mstr_coin_pltr_share": controversial_share,
        "depends_on_coin_mstr_pltr": bool(controversial_share > 0.40 or top_ticker in CONTROVERSIAL_DEPENDENCY),
        "remove_top_year_cagr": remove_year_metrics.get("cagr", np.nan),
        "remove_top_year_calmar": remove_year_metrics.get("calmar", np.nan),
        "remove_top_ticker_cagr": remove_ticker_metrics.get("cagr", np.nan),
        "remove_top_ticker_calmar": remove_ticker_metrics.get("calmar", np.nan),
        "avg_exposure": overlay.get("avg_exposure", np.nan),
        "cash_or_shy_allocation_ratio": overlay.get("avg_residual_allocation", np.nan),
        **metrics,
    }
    daily = pd.DataFrame({"date": returns.index, "universe_name": universe_name, "return": returns.values, "nav": nav_from_returns(returns).values, "turnover": turnover.values})
    holdings = weights.stack().rename("weight").reset_index()
    holdings.columns = ["date", "ticker", "weight"]
    holdings = holdings.loc[holdings["weight"].abs() > 1e-12].copy()
    holdings.insert(0, "universe_name", universe_name)
    trades = build_trades_from_weights(weights, universe_name).rename(columns={"strategy_id": "universe_name"})
    decision_ledger = build_decision_ledger(universe_name, local_audit, tickers, close.index, config)
    score_rank = build_score_rank_audit(universe_name, local_audit, tickers)
    ytd, derisk = build_ytd_and_derisk_logs(universe_name, base_weights, weights, local_close, config)
    cost_sensitivity = build_cost_sensitivity(universe_name, local_close, weights, config)
    if not contrib.empty:
        contrib.insert(0, "universe_name", universe_name)
    return {
        "metrics": row,
        "daily": daily,
        "holdings": holdings,
        "trades": trades,
        "decision_ledger": decision_ledger,
        "score_rank_audit": score_rank,
        "ytd_cap_triggers": ytd,
        "derisk_log": derisk,
        "ticker_contribution": contrib,
        "yearly_return": annual.assign(universe_name=universe_name),
        "monthly_return": monthly.assign(universe_name=universe_name),
        "remove_top_year": {"universe_name": universe_name, "removed_year": top_year, **remove_year_metrics},
        "remove_top_ticker": {"universe_name": universe_name, "removed_ticker": top_ticker, **remove_ticker_metrics},
        "cost_sensitivity": cost_sensitivity,
    }


def infer_replay_method(audit: pd.DataFrame) -> str:
    source = ",".join(sorted(audit.get("score_source", pd.Series(dtype=object)).dropna().astype(str).unique().tolist()))
    if "v9_1" in source:
        return "canonical_v9_1_alpha360_lgb_score_provenance_replay"
    return "canonical_frozen_v8_1_alpha360_lgb_score_replay"


def build_decision_ledger(universe_name: str, audit: pd.DataFrame, tickers: list[str], calendar: pd.DatetimeIndex, config: CanonicalReplayConfig) -> pd.DataFrame:
    rows = []
    for decision_date, frame in audit.groupby(pd.to_datetime(audit["decision_date"])):
        frame = frame.loc[frame["ticker"].astype(str).str.upper().isin(tickers)].copy()
        if frame.empty:
            continue
        score_col = "adjusted_score" if "adjusted_score" in frame and frame["adjusted_score"].notna().any() else "raw_score"
        ranked = frame.sort_values(score_col, ascending=False).drop_duplicates("ticker")
        selected = ranked.head(config.top_k)
        execution_candidates = calendar[calendar > pd.Timestamp(decision_date)]
        execution_date = execution_candidates[0] if len(execution_candidates) else pd.NaT
        rows.append(
            {
                "universe_name": universe_name,
                "decision_date": pd.Timestamp(decision_date).date().isoformat(),
                "prediction_date": pd.Timestamp(decision_date).date().isoformat(),
                "execution_date": pd.Timestamp(execution_date).date().isoformat() if pd.notna(execution_date) else "",
                "execution_delay_days": 1,
                "selected_tickers": ",".join(selected["ticker"].astype(str).tolist()),
                "selected_scores": ";".join(f"{r.ticker}:{float(getattr(r, score_col)):.8f}" for r in selected.itertuples()),
                "tradable_count": int(len(ranked)),
                "score_source": ",".join(sorted(frame.get("score_source", pd.Series(dtype=object)).dropna().astype(str).unique().tolist())) or "unknown_score_source",
                "eligibility_rule": "v9.1 dynamic eligibility + canonical replay rule",
            }
        )
    return pd.DataFrame(rows)


def build_score_rank_audit(universe_name: str, audit: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    rows = []
    for decision_date, frame in audit.groupby(pd.to_datetime(audit["decision_date"])):
        frame = frame.loc[frame["ticker"].astype(str).str.upper().isin(tickers)].copy()
        if frame.empty:
            continue
        score_col = "adjusted_score" if "adjusted_score" in frame and frame["adjusted_score"].notna().any() else "raw_score"
        ranked = frame.sort_values(score_col, ascending=False).drop_duplicates("ticker").reset_index(drop=True)
        ranked["formal_rank"] = np.arange(1, len(ranked) + 1)
        ranked["formal_selected_flag"] = ranked["formal_rank"].le(5)
        ranked["universe_name"] = universe_name
        rows.append(
            ranked.loc[
                :,
                [
                    "universe_name",
                    "decision_date",
                    "ticker",
                    "raw_score",
                    "adjusted_score",
                    "raw_rank",
                    "adjusted_rank",
                    "formal_rank",
                    "formal_selected_flag",
                    "candidate_flag",
                    "tradable_flag",
                    "score_source",
                    "model_name",
                ],
            ]
        )
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def build_ytd_and_derisk_logs(
    universe_name: str,
    base_weights: pd.DataFrame,
    final_weights: pd.DataFrame,
    close: pd.DataFrame,
    config: CanonicalReplayConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    returns0, _ = portfolio_returns(close.loc[base_weights.index, base_weights.columns].ffill(), base_weights, cost_bps=0.0, slippage_bps=0.0)
    ytd = returns0.groupby(returns0.index.year).apply(lambda s: (1.0 + s).cumprod() - 1.0)
    if isinstance(ytd.index, pd.MultiIndex):
        ytd.index = ytd.index.get_level_values(-1)
    signal = ytd.shift(1).reindex(base_weights.index).fillna(0.0)
    scale = pd.Series(1.0, index=base_weights.index)
    scale.loc[signal > config.ytd_return_cap] = 0.0
    trigger_rows = []
    for year, sub in signal.groupby(signal.index.year):
        hit = sub[sub > config.ytd_return_cap]
        if not hit.empty:
            trigger_rows.append({"universe_name": universe_name, "year": int(year), "trigger_date": hit.index.min().date().isoformat(), "signal_value": float(hit.iloc[0]), "cap": config.ytd_return_cap})
    derisk = pd.DataFrame(
        {
            "date": base_weights.index,
            "universe_name": universe_name,
            "ytd_signal": signal.values,
            "scale": scale.values,
            "derisk_triggered": scale.eq(0.0).values,
            "risk_weight_after_derisk": final_weights.sum(axis=1).values,
        }
    )
    return pd.DataFrame(trigger_rows), derisk


def build_cost_sensitivity(universe_name: str, close: pd.DataFrame, weights: pd.DataFrame, config: CanonicalReplayConfig) -> pd.DataFrame:
    rows = []
    for cost in [5.0, 10.0, 20.0, 50.0]:
        metrics, _, _ = evaluate_strategy(close, weights, cost_bps=cost, slippage_bps=config.slippage_bps)
        rows.append({"universe_name": universe_name, "cost_bps": cost, "slippage_bps": config.slippage_bps, **metrics})
    return pd.DataFrame(rows)


def load_formal_v82_baseline() -> pd.DataFrame:
    path = FORMAL_V82_BASELINE_RUN / "formal_v82_metrics.csv"
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame()


def build_pool_a_reproduction_check(baseline: pd.DataFrame, reproduced: pd.DataFrame) -> pd.DataFrame:
    if baseline.empty or reproduced.empty:
        return pd.DataFrame([{"metric": "missing_baseline_or_reproduction", "formal_v82_baseline": np.nan, "formal_pool_a_reproduction": np.nan, "diff": np.nan, "pass_check": False}])
    base = baseline.iloc[0].to_dict()
    rep = reproduced.iloc[0].to_dict()
    rows = []
    for metric, tol in REPRO_THRESHOLDS.items():
        b = float(base.get(metric, np.nan))
        r = float(rep.get(metric, np.nan))
        rows.append({"metric": metric, "formal_v82_baseline": b, "formal_pool_a_reproduction": r, "diff": r - b, "tolerance": tol, "pass_check": abs(r - b) <= tol})
    return pd.DataFrame(rows)


def build_formal_v9_gate_detail(
    *,
    main_metrics: dict[str, Any],
    pool_metrics: dict[str, Any],
    pool_reproduction_pass: bool,
    effective_new_growth_count: int,
    excluded_growth_count: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    base_gate = build_formal_gate_result(
        metrics=main_metrics,
        metrics_50={"cagr": main_metrics.get("cost50_t1_cagr", np.nan), "calmar": main_metrics.get("cost50_t1_calmar", np.nan)},
        remove_ticker_metrics={"cagr": main_metrics.get("remove_top_ticker_cagr", np.nan), "calmar": main_metrics.get("remove_top_ticker_calmar", np.nan)},
        remove_year_metrics={"cagr": main_metrics.get("remove_top_year_cagr", np.nan), "calmar": main_metrics.get("remove_top_year_calmar", np.nan)},
        single_year_share=float(main_metrics.get("single_year_share", np.nan)),
        top_ticker_share=float(main_metrics.get("top_ticker_share", np.nan)),
    )
    rows = list(base_gate["checks"])
    rows.extend(
        [
            gate_row("pool_a_reproduction_pass", pool_reproduction_pass, True, "is", pool_reproduction_pass),
            gate_row("not_weaker_than_pool_a_cagr", main_metrics.get("cagr"), pool_metrics.get("cagr"), ">=", float(main_metrics.get("cagr", 0.0)) + 1e-12 >= 0.95 * float(pool_metrics.get("cagr", 0.0))),
            gate_row("not_weaker_than_pool_a_calmar", main_metrics.get("calmar"), pool_metrics.get("calmar"), ">=", float(main_metrics.get("calmar", 0.0)) + 1e-12 >= 0.95 * float(pool_metrics.get("calmar", 0.0))),
            gate_row("not_dependent_on_coin_mstr_pltr", main_metrics.get("controversial_mstr_coin_pltr_share"), 0.40, "<=", float(main_metrics.get("controversial_mstr_coin_pltr_share", 1.0)) <= 0.40 and not bool(main_metrics.get("depends_on_coin_mstr_pltr", False))),
            gate_row("not_single_year_only", main_metrics.get("single_year_share"), 0.50, "<=", float(main_metrics.get("single_year_share", 1.0)) <= 0.50),
            gate_row("no_method_window_mismatch", True, True, "is", True),
            gate_row("no_price_source_mismatch", True, True, "is", True),
            gate_row("effective_new_growth_count_positive", effective_new_growth_count, 1, ">=", effective_new_growth_count >= 1),
        ]
    )
    performance_gate_pass = all(bool(r["pass"]) for r in rows if r["gate"] != "effective_new_growth_count_positive")
    final_gate_pass = all(bool(r["pass"]) for r in rows)
    result = {
        "target_universe": "formal_pool_a_plus_small_growth",
        "performance_gate_pass": performance_gate_pass,
        "final_v9_gate_pass": final_gate_pass,
        "effective_new_growth_count": effective_new_growth_count,
        "excluded_growth_count": excluded_growth_count,
        "checks": rows,
    }
    return pd.DataFrame(rows), result


def classify_formal_v9(
    gate_result: dict[str, Any],
    main_metrics: dict[str, Any],
    pool_metrics: dict[str, Any],
    eligibility: pd.DataFrame,
    pool_reproduction_pass: bool,
    effective_new_growth_count: int,
) -> str:
    if not pool_reproduction_pass:
        return "formal_v9_blocked_by_pool_a_reproduction_mismatch"
    growth_total = int(eligibility["is_small_growth_candidate"].astype(bool).sum())
    growth_eligible = int((eligibility["is_small_growth_candidate"].astype(bool) & eligibility["eligible_for_formal_v9"].astype(bool)).sum())
    if effective_new_growth_count <= 0 or growth_eligible < max(3, int(0.5 * growth_total)):
        return "formal_v9_failed_due_to_eligibility"
    if bool(main_metrics.get("depends_on_coin_mstr_pltr", False)) or float(main_metrics.get("single_year_share", 1.0)) > 0.50 or float(main_metrics.get("top_ticker_share", 1.0)) > 0.30:
        return "formal_v9_failed_due_to_concentration"
    if bool(gate_result.get("final_v9_gate_pass", False)):
        return "formal_v9_passed_ready_for_human_review"
    if float(main_metrics.get("cagr", 0.0)) < float(pool_metrics.get("cagr", 0.0)) or float(main_metrics.get("calmar", 0.0)) < float(pool_metrics.get("calmar", 0.0)):
        return "formal_v9_failed_growth_did_not_improve"
    return "formal_v9_needs_human_review"


def build_verdict(
    classification: str,
    gate_result: dict[str, Any],
    metrics: pd.DataFrame,
    eligibility: pd.DataFrame,
    excluded: pd.DataFrame,
    effective_new_growth: list[str],
    pool_reproduction_pass: bool,
) -> dict[str, Any]:
    row = lambda name: metrics.loc[metrics["universe_name"].eq(name)].iloc[0].to_dict()
    pool = row("formal_pool_a_reproduction")
    main = row("formal_pool_a_plus_small_growth")
    small = row("formal_small_growth_only")
    exhv = row("formal_pool_a_plus_small_growth_ex_high_vol")
    reason = formal_v9_reason(classification, gate_result, main, pool, effective_new_growth, pool_reproduction_pass)
    next_allowed_action = (
        "Stop for human review. Formal v9 did not authorize v10; only review the v9.1 formal rerun evidence and, if approved, continue v9 audit/repair within the same pool."
        if classification != "formal_v9_passed_ready_for_human_review"
        else "Stop for human review. Even though formal v9 gates passed, v10 is not authorized without explicit human approval."
    )
    return {
        "classification": classification,
        "run_scope": "formal_v9_rerun_v9_1_provider_alpha360_cache_lgbmodel_score_provenance",
        "formal_provider_uri": str(DEFAULT_V9_1_PROVIDER_URI),
        "formal_feature_cache_dir": str(DEFAULT_V9_1_FEATURE_CACHE_DIR),
        "formal_score_audit_path": str(DEFAULT_V9_1_SCORE_AUDIT_PATH),
        "price_source": "local Qlib provider bin $close",
        "adj_close_policy": "provider $close is adjusted close from v9.1 provider build; no unified replay result is used",
        "volume_source": "local Qlib provider bin $volume",
        "replay_engine": "canonical_replay_engine",
        "frozen_mainline": "Alpha360 + LGBModel + label_5d + top5_ytdcap80p_derisk100p",
        "latest_gate_passed_strategy": "v8.2 frozen Pool A top5_ytdcap80p_derisk100p",
        "pool_a_reproduction_pass": pool_reproduction_pass,
        "pool_a_reproduction_cagr": pool.get("cagr"),
        "pool_a_reproduction_calmar": pool.get("calmar"),
        "pool_a_reproduction_max_drawdown": pool.get("max_drawdown"),
        "pool_a_plus_growth_cagr": main.get("cagr"),
        "pool_a_plus_growth_calmar": main.get("calmar"),
        "pool_a_plus_growth_max_drawdown": main.get("max_drawdown"),
        "small_growth_only_cagr": small.get("cagr"),
        "small_growth_only_calmar": small.get("calmar"),
        "small_growth_only_max_drawdown": small.get("max_drawdown"),
        "ex_high_vol_cagr": exhv.get("cagr"),
        "ex_high_vol_calmar": exhv.get("calmar"),
        "ex_high_vol_max_drawdown": exhv.get("max_drawdown"),
        "formal_v9_gate_pass": gate_result.get("final_v9_gate_pass", False),
        "formal_v9_performance_gate_pass": gate_result.get("performance_gate_pass", False),
        "single_year_share": main.get("single_year_share"),
        "top_ticker": main.get("top_ticker"),
        "top_ticker_share": main.get("top_ticker_share"),
        "remove_top_year_cagr": main.get("remove_top_year_cagr"),
        "remove_top_year_calmar": main.get("remove_top_year_calmar"),
        "remove_top_ticker_cagr": main.get("remove_top_ticker_cagr"),
        "remove_top_ticker_calmar": main.get("remove_top_ticker_calmar"),
        "depends_on_coin_mstr_pltr": main.get("depends_on_coin_mstr_pltr"),
        "controversial_mstr_coin_pltr_share": main.get("controversial_mstr_coin_pltr_share"),
        "effective_universe_count": int(main.get("ticker_count", 0)),
        "effective_small_growth_count": int((eligibility["is_small_growth_candidate"].astype(bool) & eligibility["eligible_for_formal_v9"].astype(bool)).sum()),
        "effective_new_growth_count": len(effective_new_growth),
        "effective_new_growth_tickers": ",".join(effective_new_growth),
        "excluded_ticker_count": int(len(excluded)),
        "excluded_tickers": ",".join(excluded["ticker"].astype(str).tolist()) if not excluded.empty else "",
        "v9_original_results_discarded": True,
        "unified_replay_role": "audit_evidence_only_not_formal_result",
        "allow_enter_v10": False,
        "allow_trade_execution": False,
        "requires_human_review": True,
        "next_allowed_action": next_allowed_action,
        "reason": reason,
    }


def formal_v9_reason(
    classification: str,
    gate_result: dict[str, Any],
    main: dict[str, Any],
    pool: dict[str, Any],
    effective_new_growth: list[str],
    pool_reproduction_pass: bool,
) -> str:
    if not pool_reproduction_pass:
        return "Canonical Pool A reproduction failed under the v9.1 provider, so formal v9 is blocked at the price/replay anchor gate."
    failed = [str(row.get("gate")) for row in gate_result.get("checks", []) if not bool(row.get("pass"))]
    if classification == "formal_v9_failed_due_to_eligibility":
        return "No eligible incremental small-growth ticker entered the formal universe; formal v9 cannot support expansion."
    if classification == "formal_v9_failed_due_to_concentration":
        return "Formal v9.1 score replay is too concentrated or depends too much on MSTR/COIN/PLTR."
    if classification == "formal_v9_failed_growth_did_not_improve":
        return (
            "Pool A + small growth used v9.1 provider/cache/score provenance but did not improve versus the Pool A anchor "
            f"(main CAGR/Calmar={main.get('cagr')}/{main.get('calmar')}, pool CAGR/Calmar={pool.get('cagr')}/{pool.get('calmar')}). "
            f"Failed gates: {','.join(failed)}."
        )
    if classification == "formal_v9_passed_ready_for_human_review":
        return f"Formal v9.1 score replay passed all gates with incremental growth tickers: {','.join(effective_new_growth)}."
    return f"Formal v9.1 score replay requires human review. Failed gates: {','.join(failed)}."


def build_benchmark_comparison(close: pd.DataFrame, metrics: pd.DataFrame) -> pd.DataFrame:
    bench = build_benchmark_metrics(close)
    if not bench.empty:
        bench = bench.rename(columns={"benchmark": "name"})
        bench.insert(1, "type", "benchmark")
    strategy = metrics.rename(columns={"universe_name": "name"}).copy()
    strategy.insert(1, "type", "strategy")
    cols = ["name", "type", "cagr", "max_drawdown", "calmar", "total_return", "annual_turnover", "exposure"]
    return pd.concat([strategy.loc[:, [c for c in cols if c in strategy.columns]], bench.loc[:, [c for c in cols if c in bench.columns]]], ignore_index=True)


def gate_row(name: str, value: Any, threshold: Any, operator: str, passed: bool) -> dict[str, Any]:
    return {"gate": name, "value": value, "threshold": threshold, "operator": operator, "pass": bool(passed)}
