"""Score provenance alignment audit for v8.2 frozen Pool A vs v9 local replay.

This audit is intentionally local-only.  It reads existing run artifacts,
feature cache metadata, local price parquet files, and bridge manifests.  It
does not download data, expand universes, search strategies, connect brokers,
or touch credentials.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.qlib_signal_backtest import compute_portfolio_metrics, portfolio_returns
from quant_lab.us_stock_selection.utils import ensure_dir, save_dataframe, save_json


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
V82_RUN = OUTPUT_ROOT / "run_20260502_220641"
V82_DIR = V82_RUN / "v8_2_year_stability"
V81_SCORE_DIR = OUTPUT_ROOT / "run_20260502_210856" / "v8_1_model_switch" / "Alpha360_LGBModel"
V9_REVERSE_RUN = OUTPUT_ROOT / "run_20260503_172054"
V9_REVERSE_DIR = V9_REVERSE_RUN / "v9_reverse_audit"
V82_V9_AUDIT_RUN = OUTPUT_ROOT / "v82_v9_replay_diff_audit_20260503_232513"
FEATURE_CACHE_DIR = PROJECT_ROOT / "data" / "features_cache" / "us_stock_selection"
PRICE_DIR = PROJECT_ROOT / "data" / "unified_ohlcv" / "us_stock_selection" / "prices"
BRIDGE_MANIFEST = PROJECT_ROOT / "docs" / "chatgpt_bridge" / "latest_run_manifest.json"
BRIDGE_LATEST = PROJECT_ROOT / "docs" / "chatgpt_bridge" / "LATEST.md"

PRIMARY_TOP5 = "top5_ytdcap80p_derisk100p"
TOP10_CONTROL = "top10_ytdcap80p_derisk100p"
UNIFIED_START = pd.Timestamp("2024-01-02")


@dataclass(frozen=True)
class AuditTables:
    v82_results: pd.DataFrame
    v82_holdings: pd.DataFrame
    v82_daily: pd.DataFrame
    v82_variant_config: pd.DataFrame
    v81_score: pd.DataFrame
    v81_ledger: pd.DataFrame
    v9_holdings: pd.DataFrame
    v9_daily: pd.DataFrame
    v9_score: pd.DataFrame
    v9_time: pd.DataFrame
    diff_active: pd.DataFrame
    diff_candidate: pd.DataFrame
    diff_monthly: pd.DataFrame
    diff_by_ticker: pd.DataFrame
    diff_method: pd.DataFrame
    baseline_exception: pd.DataFrame
    prior_summary: dict[str, Any]
    missing_files: pd.DataFrame


def run_score_provenance_alignment_audit(out_dir: Path | str) -> dict[str, Any]:
    out = ensure_dir(out_dir)
    tables = load_tables()

    outputs: dict[str, pd.DataFrame] = {}
    outputs["missing_files"] = tables.missing_files
    outputs["run_manifest_alignment"] = build_run_manifest_alignment(tables)
    outputs["universe_alignment"] = build_universe_alignment(tables)
    outputs["score_source_alignment"] = build_score_source_alignment(tables)
    outputs["model_fit_provenance"] = build_model_fit_provenance(tables)
    score_rank_diff, score_rank_summary = build_score_rank_diff(tables)
    outputs["score_rank_diff"] = score_rank_diff
    outputs["score_rank_diff_summary"] = score_rank_summary
    decision, decision_diff = build_portfolio_decision_alignment(tables)
    outputs["portfolio_decision_alignment"] = decision
    outputs["portfolio_decision_diff"] = decision_diff
    outputs["calendar_alignment"] = build_calendar_alignment(tables)
    outputs["return_reconstruction_check"] = build_return_reconstruction_check(tables)
    outputs["gate_recompute_alignment"] = build_gate_recompute_alignment(tables, outputs["return_reconstruction_check"])
    outputs["baseline_exception_pollution_detail"] = build_baseline_exception_pollution_detail(tables)

    verdict = build_verdict(outputs, tables)
    outputs["audit_verdict"] = pd.DataFrame([verdict])
    save_json(verdict, out / "score_provenance_alignment_audit_verdict.json")
    save_json(verdict, out / "audit_summary.json")
    for name, df in outputs.items():
        if name == "audit_verdict":
            continue
        save_dataframe(df, out / f"{name}.csv")
    return {"verdict": verdict, "tables": outputs}


def load_tables() -> AuditTables:
    required = {
        "v82_results": V82_DIR / "v8_2_year_stability_results.csv",
        "v82_holdings": V82_DIR / "v8_2_monthly_holdings_by_strategy.csv",
        "v82_daily": V82_DIR / "v8_2_daily_nav_by_strategy.csv",
        "v82_variant_config": V82_DIR / "v8_2_variant_config.csv",
        "v81_score": V81_SCORE_DIR / "v8_2_score_rank_audit_trail.csv",
        "v81_ledger": V81_SCORE_DIR / "monthly_decision_ledger.csv",
        "v9_holdings": V9_REVERSE_DIR / "monthly_holdings.csv",
        "v9_daily": V9_REVERSE_DIR / "daily_nav.csv",
        "v9_score": V9_REVERSE_DIR / "score_rank_audit.csv",
        "v9_time": V9_REVERSE_DIR / "time_alignment_audit.csv",
        "diff_active": V82_V9_AUDIT_RUN / "active_window_metrics.csv",
        "diff_candidate": V82_V9_AUDIT_RUN / "candidate_replay_diff.csv",
        "diff_monthly": V82_V9_AUDIT_RUN / "monthly_selection_diff.csv",
        "diff_by_ticker": V82_V9_AUDIT_RUN / "candidate_replay_diff_by_ticker.csv",
        "diff_method": V82_V9_AUDIT_RUN / "v82_v9_method_diff.csv",
        "baseline_exception": V82_V9_AUDIT_RUN / "baseline_exception_audit.csv",
        "audit_summary": V82_V9_AUDIT_RUN / "audit_summary.json",
        "bridge_manifest": BRIDGE_MANIFEST,
        "bridge_latest": BRIDGE_LATEST,
    }
    missing_rows = []
    loaded: dict[str, Any] = {}
    for name, path in required.items():
        exists = path.exists()
        missing_rows.append(
            {
                "input_name": name,
                "file_path": str(path),
                "exists": exists,
                "status": "found" if exists else "missing",
            }
        )
        if name == "audit_summary":
            loaded[name] = read_json(path)
        elif name in {"bridge_manifest", "bridge_latest"}:
            continue
        else:
            loaded[name] = read_csv(path)
    return AuditTables(
        v82_results=loaded["v82_results"],
        v82_holdings=loaded["v82_holdings"],
        v82_daily=loaded["v82_daily"],
        v82_variant_config=loaded["v82_variant_config"],
        v81_score=loaded["v81_score"],
        v81_ledger=loaded["v81_ledger"],
        v9_holdings=loaded["v9_holdings"],
        v9_daily=loaded["v9_daily"],
        v9_score=loaded["v9_score"],
        v9_time=loaded["v9_time"],
        diff_active=loaded["diff_active"],
        diff_candidate=loaded["diff_candidate"],
        diff_monthly=loaded["diff_monthly"],
        diff_by_ticker=loaded["diff_by_ticker"],
        diff_method=loaded["diff_method"],
        baseline_exception=loaded["baseline_exception"],
        prior_summary=loaded["audit_summary"],
        missing_files=pd.DataFrame(missing_rows),
    )


def build_run_manifest_alignment(t: AuditTables) -> pd.DataFrame:
    rows = []
    rows.append(
        manifest_row(
            "v8_2_frozen_pool_a",
            V82_RUN,
            V82_RUN / "reports" / "us_stock_selection_v8_2_year_stability_report.md",
            [V82_DIR / "v8_2_year_stability_results.csv", V82_DIR / "v8_2_monthly_holdings_by_strategy.csv"],
            t.v82_daily.loc[t.v82_daily["strategy_id"].eq(PRIMARY_TOP5), "date"],
            "Pool A",
            PRIMARY_TOP5,
            "Alpha360",
            "LGBModel",
            "label_5d",
            "topk_equal_monthly_year_neutral_risk_cap",
            5,
            5,
            "T+1",
            0.8,
            1.0,
            "source frozen v8.2 gate run",
        )
    )
    rows.append(
        manifest_row(
            "v9_reverse_audit_local_replay",
            V9_REVERSE_RUN,
            V9_REVERSE_RUN / "reports" / "us_stock_selection_v9_reverse_audit_report.md",
            [V9_REVERSE_DIR / "v9_local_pool_a_results.csv", V9_REVERSE_DIR / "score_rank_audit.csv"],
            t.v9_daily.loc[t.v9_daily["universe_name"].eq("pool_a_v9_local_replay_top5"), "date"],
            "Pool A local replay",
            "pool_a_v9_local_replay_top5",
            "local Alpha360-compatible",
            "LGBModel",
            "label_5d",
            "top5_ytdcap80p_derisk100p",
            5,
            5,
            "T+1 weights plus one-bar return shift",
            0.8,
            1.0,
            "independent local v9 reverse audit replay",
        )
    )
    rows.append(
        manifest_row(
            "v82_v9_replay_diff_audit",
            V82_V9_AUDIT_RUN,
            V82_V9_AUDIT_RUN / "reports" / "v82_v9_replay_diff_audit_report.md",
            [V82_V9_AUDIT_RUN / "candidate_replay_diff.csv", V82_V9_AUDIT_RUN / "active_window_metrics.csv"],
            t.diff_candidate["window_start"] if "window_start" in t.diff_candidate else pd.Series(dtype=str),
            "Pool A",
            "v82/v9 replay diff",
            "mixed source audit",
            "n/a",
            "label_5d audited",
            "same gate audit",
            5,
            5,
            "audited from loaded artifacts",
            0.8,
            1.0,
            "prior diff audit",
        )
    )
    rows.append(
        manifest_row(
            "github_bridge_latest",
            PROJECT_ROOT / "docs" / "chatgpt_bridge",
            BRIDGE_LATEST,
            [BRIDGE_MANIFEST, BRIDGE_LATEST],
            pd.Series(dtype=str),
            "n/a",
            "bridge packet",
            "n/a",
            "n/a",
            "n/a",
            "n/a",
            np.nan,
            np.nan,
            "n/a",
            np.nan,
            np.nan,
            "bridge metadata only",
        )
    )
    return pd.DataFrame(rows)


def build_universe_alignment(t: AuditTables) -> pd.DataFrame:
    v82_scores = normalize_score_source_v82(t.v81_score, top_k=5)
    v9_scores = normalize_score_source_v9(t.v9_score, top_k=5)
    v82_tickers = set(v82_scores["ticker"].dropna().astype(str))
    v9_tickers = set(v9_scores["ticker"].dropna().astype(str))
    unified_tickers = set(t.v9_holdings["ticker"].dropna().astype(str))
    tickers = sorted(v82_tickers | v9_tickers | unified_tickers)
    exception_map = {
        str(row["ticker"]): row.to_dict()
        for _, row in t.baseline_exception.iterrows()
        if "ticker" in t.baseline_exception
    }
    rows = []
    for ticker in tickers:
        v82_dates = t.v82_holdings.loc[t.v82_holdings["ticker"].eq(ticker), "date"]
        v9_dates = t.v9_holdings.loc[t.v9_holdings["ticker"].eq(ticker), "date"]
        exc = exception_map.get(ticker, {})
        status = "aligned"
        reason = ""
        if ticker not in v82_tickers:
            status, reason = "missing_in_v82_scores", "present in v9 but not v8.2 score universe"
        elif ticker not in v9_tickers:
            status, reason = "missing_in_v9_scores", "present in v8.2 but not v9 local score universe"
        if bool(exc.get("baseline_reproduction_only", False)):
            status = "baseline_exception"
            reason = str(exc.get("v9_exclude_reason") or "baseline-only exception")
        rows.append(
            {
                "ticker": ticker,
                "in_v82": ticker in v82_tickers,
                "in_v9": ticker in v9_tickers,
                "in_unified_replay": ticker in unified_tickers,
                "first_date_v82": min_or_blank(v82_dates),
                "last_date_v82": max_or_blank(v82_dates),
                "first_date_v9": min_or_blank(v9_dates),
                "last_date_v9": max_or_blank(v9_dates),
                "data_quality_status": status,
                "reason_if_missing": reason,
            }
        )
    return pd.DataFrame(rows)


def build_score_source_alignment(t: AuditTables) -> pd.DataFrame:
    rows = [
        score_source_row(
            "v8_2_score_rank_audit_trail",
            V81_SCORE_DIR / "v8_2_score_rank_audit_trail.csv",
            t.v81_score,
            "Alpha360",
            "label_5d = adj_close.shift(-6) / adj_close.shift(-1) - 1",
            "5d forward after one-day lag",
            "2020-01-02 to train_end_label_safe",
            "decision_date candidate scores",
            "Alpha360 feature matrix not exported in score trail",
        ),
        score_source_row(
            "v9_local_score_rank_audit",
            V9_REVERSE_DIR / "score_rank_audit.csv",
            t.v9_score,
            "local Alpha360-compatible",
            "label_5d = adj_close.shift(-6) / adj_close.shift(-1) - 1",
            "5d forward after one-day lag",
            "2020-01-02 to decision-6 trading days",
            "decision_date candidate scores",
            "local refit feature matrix not exported in score trail",
        ),
        feature_cache_row("local_features_cache_directory", FEATURE_CACHE_DIR),
    ]
    return pd.DataFrame(rows)


def build_model_fit_provenance(t: AuditTables) -> pd.DataFrame:
    rows = []
    for _, row in t.v81_ledger.iterrows():
        rows.append(
            {
                "rebalance_date": row.get("decision_date", ""),
                "source_name": "v8_2_frozen_v8_1_score_trail",
                "train_start": row.get("train_start", ""),
                "train_end": row.get("train_end_label_safe", ""),
                "valid_start": "",
                "valid_end": "",
                "test_or_predict_date": row.get("prediction_date", row.get("decision_date", "")),
                "model_name": row.get("model", "LGBModel"),
                "model_params": "not exported in score trail",
                "random_seed": "not exported",
                "sample_count": row.get("train_rows", np.nan),
                "feature_count": "Alpha360",
                "warning_count": row.get("fit_warning_count", np.nan),
                "fit_status": row.get("fit_status", ""),
            }
        )
    v9 = t.v9_time.loc[t.v9_time.get("score_package", "").astype(str).eq("normal_label")].copy()
    for _, row in v9.iterrows():
        rows.append(
            {
                "rebalance_date": row.get("decision_date", ""),
                "source_name": "v9_local_replay",
                "train_start": "2020-01-02",
                "train_end": row.get("train_end_label_safe", ""),
                "valid_start": "",
                "valid_end": "",
                "test_or_predict_date": row.get("decision_date", ""),
                "model_name": "LGBModel",
                "model_params": "v9_reverse_audit.make_lgb_model defaults",
                "random_seed": "fixed in v9 make_lgb_model if exported",
                "sample_count": row.get("train_rows", np.nan),
                "feature_count": row.get("predict_rows", np.nan),
                "warning_count": 0,
                "fit_status": "completed" if bool(row.get("pass", False)) else "audit_issue",
            }
        )
    return pd.DataFrame(rows)


def build_score_rank_diff(t: AuditTables) -> tuple[pd.DataFrame, pd.DataFrame]:
    v82 = normalize_score_source_v82(t.v81_score, top_k=10)
    v9 = normalize_score_source_v9(t.v9_score, top_k=10)
    merged = v82.merge(v9, on=["rebalance_date", "ticker"], how="outer", suffixes=("_v82", "_v9"))
    merged["score_unified"] = merged["score_v9"]
    merged["rank_unified"] = merged["rank_v9"]
    merged["selected_unified"] = merged["selected_v9"]
    merged["score_diff_v9_minus_v82"] = merged["score_v9"] - merged["score_v82"]
    merged["rank_diff_v9_minus_v82"] = merged["rank_v9"] - merged["rank_v82"]
    selected_v82 = merged["selected_v82"].map(lambda value: bool(value) if not pd.isna(value) else False)
    selected_v9 = merged["selected_v9"].map(lambda value: bool(value) if not pd.isna(value) else False)
    merged["selected_changed"] = selected_v82 != selected_v9
    merged["reason"] = np.select(
        [
            merged["score_v82"].isna(),
            merged["score_v9"].isna(),
            merged["selected_changed"],
            merged["rank_diff_v9_minus_v82"].abs() >= 5,
        ],
        [
            "missing_v82_score",
            "missing_v9_score",
            "topk_selection_changed",
            "rank_shift_ge_5",
        ],
        default="common",
    )
    out = merged.rename(
        columns={
            "rebalance_date": "rebalance_date",
            "score_v82": "score_v82",
            "rank_v82": "rank_v82",
            "selected_v82": "selected_v82",
            "score_v9": "score_v9",
            "rank_v9": "rank_v9",
            "selected_v9": "selected_v9",
        }
    )
    cols = [
        "rebalance_date",
        "ticker",
        "score_v82",
        "rank_v82",
        "selected_v82",
        "score_v9",
        "rank_v9",
        "selected_v9",
        "score_unified",
        "rank_unified",
        "selected_unified",
        "score_diff_v9_minus_v82",
        "rank_diff_v9_minus_v82",
        "selected_changed",
        "reason",
    ]
    summary_rows = []
    for date, sub in out.groupby("rebalance_date", dropna=False):
        common = sub.dropna(subset=["score_v82", "score_v9"])
        corr = common["score_v82"].corr(common["score_v9"]) if len(common) >= 3 else np.nan
        top5_v82 = set(sub.loc[sub["rank_v82"].le(5), "ticker"].dropna().astype(str))
        top5_v9 = set(sub.loc[sub["rank_v9"].le(5), "ticker"].dropna().astype(str))
        top10_v82 = set(sub.loc[sub["rank_v82"].le(10), "ticker"].dropna().astype(str))
        top10_v9 = set(sub.loc[sub["rank_v9"].le(10), "ticker"].dropna().astype(str))
        summary_rows.append(
            {
                "rebalance_date": date,
                "rank_correlation": corr,
                "selected_overlap": len(top5_v82 & top5_v9),
                "top5_overlap_ratio": overlap_ratio(top5_v82, top5_v9),
                "top10_overlap_ratio": overlap_ratio(top10_v82, top10_v9),
                "score_missing_count": int(sub[["score_v82", "score_v9"]].isna().any(axis=1).sum()),
                "rank_inversion_count": int((common["rank_diff_v9_minus_v82"].abs() >= 10).sum()) if "rank_diff_v9_minus_v82" in common else 0,
            }
        )
    return out.loc[:, cols].sort_values(["rebalance_date", "rank_v82", "rank_v9", "ticker"]), pd.DataFrame(summary_rows)


def build_portfolio_decision_alignment(t: AuditTables) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for source, df, source_col, strategies in [
        ("v8_2_frozen", t.v82_holdings, "strategy_id", {PRIMARY_TOP5: "top5", TOP10_CONTROL: "top10"}),
        ("v9_local_replay", t.v9_holdings, "universe_name", {"pool_a_v9_local_replay_top5": "top5", "pool_a_v9_local_replay_top10": "top10"}),
    ]:
        for strategy_id, family in strategies.items():
            sub = df.loc[df[source_col].eq(strategy_id)].copy()
            if sub.empty:
                continue
            sub["date"] = pd.to_datetime(sub["date"])
            decision_dates = infer_decision_from_execution(sub["date"])
            for exe_date, group in sub.groupby("date"):
                tickers = group.sort_values(["weight", "ticker"], ascending=[False, True])
                weight_sum = float(tickers["weight"].sum())
                rows.append(
                    {
                        "rebalance_date": decision_dates.get(exe_date, ""),
                        "execution_date": date_str(exe_date),
                        "strategy_family": family,
                        "source_name": source,
                        "selected_tickers": ",".join(tickers["ticker"].astype(str).tolist()),
                        "weights": ";".join(f"{r.ticker}:{float(r.weight):.6f}" for r in tickers.itertuples()),
                        "weight_sum": weight_sum,
                        "ytd_cap_triggered": weight_sum < 0.999,
                        "derisk_status": "derisk_or_cash" if weight_sum < 0.999 else "fully_invested",
                        "cash_or_shy_weight": max(0.0, 1.0 - weight_sum),
                        "turnover": np.nan,
                        "notes": "",
                    }
                )
    decision = pd.DataFrame(rows)
    diff_rows = []
    for (family, date), sub in decision.groupby(["strategy_family", "execution_date"], dropna=False):
        v82 = sub.loc[sub["source_name"].eq("v8_2_frozen")]
        v9 = sub.loc[sub["source_name"].eq("v9_local_replay")]
        if v82.empty or v9.empty:
            continue
        set82 = set(str(v82.iloc[0]["selected_tickers"]).split(","))
        set9 = set(str(v9.iloc[0]["selected_tickers"]).split(","))
        diff_rows.append(
            {
                "strategy_family": family,
                "execution_date": date,
                "v82_selected_tickers": v82.iloc[0]["selected_tickers"],
                "v9_selected_tickers": v9.iloc[0]["selected_tickers"],
                "selected_overlap_count": len(set82 & set9),
                "selected_overlap_ratio": overlap_ratio(set82, set9),
                "weight_sum_v82": v82.iloc[0]["weight_sum"],
                "weight_sum_v9": v9.iloc[0]["weight_sum"],
                "ytd_or_derisk_mismatch": bool(v82.iloc[0]["derisk_status"] != v9.iloc[0]["derisk_status"]),
                "topk_changed": set82 != set9,
            }
        )
    return decision, pd.DataFrame(diff_rows)


def build_calendar_alignment(t: AuditTables) -> pd.DataFrame:
    v82 = t.v81_ledger.copy()
    v9 = t.v9_time.loc[t.v9_time.get("score_package", "").astype(str).eq("normal_label")].copy()
    rows = []
    months = sorted(set(v82["decision_date"].astype(str).str.slice(0, 7)) | set(v9["decision_date"].astype(str).str.slice(0, 7)))
    for month in months:
        r82 = first_row(v82.loc[v82["decision_date"].astype(str).str.startswith(month)])
        r9 = first_row(v9.loc[v9["decision_date"].astype(str).str.startswith(month)])
        rows.append(
            {
                "rebalance_month": month,
                "signal_date_v82": r82.get("decision_date", ""),
                "execution_date_v82": r82.get("execution_date", ""),
                "first_return_date_v82": next_date_after(t.v82_daily["date"], r82.get("execution_date", "")),
                "signal_date_v9": r9.get("decision_date", ""),
                "execution_date_v9": r9.get("execution_date", ""),
                "first_return_date_v9": next_date_after(t.v9_daily["date"], r9.get("execution_date", "")),
                "signal_date_unified": r9.get("decision_date", ""),
                "execution_date_unified": r9.get("execution_date", ""),
                "first_return_date_unified": next_date_after(t.v9_daily["date"], r9.get("execution_date", "")),
                "calendar_mismatch": bool(r82.get("decision_date", "") != r9.get("decision_date", "") or r82.get("execution_date", "") != r9.get("execution_date", "")),
                "notes": "",
            }
        )
    return pd.DataFrame(rows)


def build_return_reconstruction_check(t: AuditTables) -> pd.DataFrame:
    close = load_close_matrix()
    rows = []
    specs = [
        ("v8_2_top5", "v8_2_frozen", t.v82_holdings, "strategy_id", PRIMARY_TOP5, t.v82_daily, "strategy_id", PRIMARY_TOP5, "original_report"),
        ("v8_2_top10", "v8_2_frozen", t.v82_holdings, "strategy_id", TOP10_CONTROL, t.v82_daily, "strategy_id", TOP10_CONTROL, "original_report"),
        ("v9_local_top5_original", "v9_local_replay", t.v9_holdings, "universe_name", "pool_a_v9_local_replay_top5", t.v9_daily, "universe_name", "pool_a_v9_local_replay_top5", "v9_local_original_2020_01_02"),
        ("v9_local_top5_unified", "v9_local_replay", t.v9_holdings, "universe_name", "pool_a_v9_local_replay_top5", t.v9_daily, "universe_name", "pool_a_v9_local_replay_top5", "v9_local_unified_2024_01_02"),
        ("v9_local_top10_original", "v9_local_replay", t.v9_holdings, "universe_name", "pool_a_v9_local_replay_top10", t.v9_daily, "universe_name", "pool_a_v9_local_replay_top10", "v9_local_original_2020_01_02"),
        ("v9_local_top10_unified", "v9_local_replay", t.v9_holdings, "universe_name", "pool_a_v9_local_replay_top10", t.v9_daily, "universe_name", "pool_a_v9_local_replay_top10", "v9_local_unified_2024_01_02"),
    ]
    active = t.diff_active.copy()
    for source_name, source_family, holdings, hcol, hval, daily, dcol, dval, window_type in specs:
        h = holdings.loc[holdings[hcol].eq(hval)].copy()
        d = daily.loc[daily[dcol].eq(dval)].copy()
        if h.empty or d.empty:
            rows.append(cannot_recompute_row(source_name, "missing holdings or daily nav"))
            continue
        start = pd.Timestamp("2020-01-02") if "original_2020" in window_type else UNIFIED_START
        end = pd.to_datetime(d["date"]).max()
        weights = holdings_to_weights(h)
        tickers = [c for c in weights.columns if c in close.columns]
        if not tickers:
            rows.append(cannot_recompute_row(source_name, "missing local price data for holdings tickers"))
            continue
        local_close = close.loc[start:end, tickers].ffill()
        local_weights = weights.reindex(local_close.index).ffill().fillna(0.0).loc[:, tickers]
        returns, turnover = portfolio_returns(local_close, local_weights, cost_bps=5.0, slippage_bps=5.0)
        metrics = compute_portfolio_metrics(returns, turnover, local_weights)
        reported = find_reported_metrics(active, source_family, hval, window_type, d)
        rows.append(
            {
                "source_name": source_name,
                "start_date": date_str(start),
                "end_date": date_str(end),
                "reported_cagr": reported.get("cagr", np.nan),
                "recomputed_cagr": metrics.get("cagr", np.nan),
                "reported_maxdd": reported.get("max_drawdown", np.nan),
                "recomputed_maxdd": metrics.get("max_drawdown", np.nan),
                "reported_calmar": reported.get("calmar", np.nan),
                "recomputed_calmar": metrics.get("calmar", np.nan),
                "diff_cagr": metrics.get("cagr", np.nan) - reported.get("cagr", np.nan),
                "diff_maxdd": metrics.get("max_drawdown", np.nan) - reported.get("max_drawdown", np.nan),
                "diff_calmar": metrics.get("calmar", np.nan) - reported.get("calmar", np.nan),
                "pass_recalc": bool(
                    abs(metrics.get("cagr", np.nan) - reported.get("cagr", np.nan)) < 0.02
                    and abs(metrics.get("calmar", np.nan) - reported.get("calmar", np.nan)) < 0.1
                ),
                "recompute_status": "recomputed_from_local_price_and_holdings",
            }
        )
    return pd.DataFrame(rows)


def build_gate_recompute_alignment(t: AuditTables, reconstruction: pd.DataFrame) -> pd.DataFrame:
    active = t.diff_active.copy()
    rows = []
    for _, row in active.iterrows():
        cagr = safe_float(row.get("cagr"))
        calmar = safe_float(row.get("calmar"))
        maxdd = safe_float(row.get("max_drawdown"))
        source = row.get("source", "")
        window_type = row.get("window_type", "")
        cost50 = cost50_metrics(t, source, row.get("strategy_id", ""))
        single_year = safe_float(row.get("single_year_share"))
        top_ticker_share = top_ticker_share_for(t, source, row.get("strategy_id", ""))
        remove_top_year = stress_metric(t, source, row.get("strategy_id", ""), "remove_top_contribution_year")
        remove_top_ticker = stress_metric(t, source, row.get("strategy_id", ""), "remove_top_ticker")
        final_gate = (
            cagr >= 0.20
            and calmar >= 1.0
            and cost50.get("cagr", np.nan) >= 0.20
            and cost50.get("calmar", np.nan) >= 1.0
            and (math.isnan(single_year) or single_year <= 0.50)
            and (math.isnan(top_ticker_share) or top_ticker_share <= 0.30)
            and remove_top_year.get("cagr", np.nan) >= 0.20
            and remove_top_year.get("calmar", np.nan) >= 1.0
            and remove_top_ticker.get("cagr", np.nan) >= 0.20
            and remove_top_ticker.get("calmar", np.nan) >= 1.0
        )
        rows.append(
            {
                "source_name": f"{row.get('strategy_family')}_{source}_{window_type}",
                "cagr": cagr,
                "calmar": calmar,
                "maxdd": maxdd,
                "cost50_t1_cagr": cost50.get("cagr", np.nan),
                "cost50_t1_calmar": cost50.get("calmar", np.nan),
                "single_year_share": single_year,
                "top_ticker_share": top_ticker_share,
                "remove_top_year_cagr": remove_top_year.get("cagr", np.nan),
                "remove_top_year_calmar": remove_top_year.get("calmar", np.nan),
                "remove_top_ticker_cagr": remove_top_ticker.get("cagr", np.nan),
                "remove_top_ticker_calmar": remove_top_ticker.get("calmar", np.nan),
                "pass_cagr20": cagr >= 0.20,
                "pass_calmar1": calmar >= 1.0,
                "pass_cost50": cost50.get("cagr", np.nan) >= 0.20 and cost50.get("calmar", np.nan) >= 1.0,
                "pass_single_year_share": math.isnan(single_year) or single_year <= 0.50,
                "pass_top_ticker_share": math.isnan(top_ticker_share) or top_ticker_share <= 0.30,
                "pass_remove_top_year": remove_top_year.get("cagr", np.nan) >= 0.20 and remove_top_year.get("calmar", np.nan) >= 1.0,
                "pass_remove_top_ticker": remove_top_ticker.get("cagr", np.nan) >= 0.20 and remove_top_ticker.get("calmar", np.nan) >= 1.0,
                "final_gate_pass": bool(final_gate),
                "gate_validity_note": "original v9 full-window gate invalid for v8.2 comparison" if "original_2020" in str(window_type) else "computed on reported/unified window",
            }
        )
    return pd.DataFrame(rows)


def build_baseline_exception_pollution_detail(t: AuditTables) -> pd.DataFrame:
    rows = []
    for idx, row in t.baseline_exception.iterrows():
        rows.append(
            {
                "file_path": str(V82_V9_AUDIT_RUN / "baseline_exception_audit.csv"),
                "row_id_or_section": idx,
                "exception_type": "baseline_only_ticker_in_pool_a",
                "affected_metric": "Pool A reproduction and local replay ticker contribution",
                "affected_source": row.get("ticker", ""),
                "description": row.get("evidence", ""),
                "severity": "high" if bool(row.get("pollutes_pool_a_reproduction_conclusion", False)) else "medium",
                "fix_recommendation": "separate baseline reproduction from v9-eligible universe and rerun same-window score provenance audit without baseline-only exceptions",
            }
        )
    rows.append(
        {
            "file_path": str(V82_V9_AUDIT_RUN / "active_window_metrics.csv"),
            "row_id_or_section": "v9_local_original_2020_01_02",
            "exception_type": "evaluation_window_mismatch",
            "affected_metric": "v9 original CAGR 12.23% / 10.53%",
            "affected_source": "v9_local_replay",
            "description": "v9 original daily_nav includes 2020-2023 zero-exposure rows; unified 575-day window raises CAGR but still does not match v8.2 frozen.",
            "severity": "high",
            "fix_recommendation": "discard original full-window v9 CAGR for v8.2 comparison; rerun official v9 on explicit 2024-01-02 aligned window",
        }
    )
    rows.append(
        {
            "file_path": str(V82_V9_AUDIT_RUN / "v82_v9_method_diff.csv"),
            "row_id_or_section": "v9_loaded_reproduction",
            "exception_type": "loaded_reproduction_not_independent",
            "affected_metric": "v9 loaded reproduction mirrors v8.2 frozen",
            "affected_source": "v9_loaded_reproduction",
            "description": "loaded reproduction reads historical v8.2 artifacts and is not independent score/model/feature reconstruction.",
            "severity": "high",
            "fix_recommendation": "do not use loaded reproduction as evidence of v9 score provenance alignment",
        }
    )
    return pd.DataFrame(rows)


def build_verdict(outputs: dict[str, pd.DataFrame], t: AuditTables) -> dict[str, Any]:
    score_summary = outputs["score_rank_diff_summary"]
    avg_top5_overlap = safe_float(score_summary["top5_overlap_ratio"].mean()) if not score_summary.empty else np.nan
    avg_corr = safe_float(score_summary["rank_correlation"].mean()) if not score_summary.empty else np.nan
    reconstruction = outputs["return_reconstruction_check"]
    recalc_ok = bool(reconstruction["pass_recalc"].fillna(False).all()) if not reconstruction.empty else False
    method_mismatch = bool(t.prior_summary.get("method_mismatch_found", True))
    window_mismatch = bool(t.prior_summary.get("evaluation_window_mismatch_found", True))
    baseline_pollution = bool(t.prior_summary.get("baseline_exception_pollution_found", True))
    score_provenance_consistent = bool(avg_top5_overlap >= 0.8 and avg_corr >= 0.8 and not method_mismatch)
    unified_gate = outputs["gate_recompute_alignment"].loc[
        outputs["gate_recompute_alignment"]["source_name"].astype(str).str.contains("v9_local_replay_v9_local_unified", na=False)
    ]
    unified_gate_pass = bool(unified_gate["final_gate_pass"].any()) if not unified_gate.empty else False
    if not recalc_ok:
        classification = "invalid_due_to_backtest_or_alignment_bug"
    elif not score_provenance_consistent:
        classification = "score_provenance_mismatch"
    elif method_mismatch or window_mismatch:
        classification = "method_mismatch_invalidates_v9"
    elif unified_gate_pass and not baseline_pollution:
        classification = "valid_after_unified_replay_only"
    else:
        classification = "needs_human_review"
    if method_mismatch and not score_provenance_consistent:
        classification = "score_provenance_mismatch"
    return {
        "classification": classification,
        "score_provenance_consistent": score_provenance_consistent,
        "method_window_consistent": bool(not method_mismatch and not window_mismatch),
        "return_reconstruction_consistent": recalc_ok,
        "baseline_exception_pollution_found": baseline_pollution,
        "evaluation_window_mismatch_found": window_mismatch,
        "method_mismatch_found": method_mismatch,
        "avg_top5_overlap_ratio": avg_top5_overlap,
        "avg_score_rank_correlation": avg_corr,
        "v9_original_results_should_be_discarded": True,
        "unified_replay_usable": False,
        "allow_continue_v9": False,
        "allow_enter_v10": False,
        "allow_expand_nasdaq100": False,
        "allow_expand_sp500": False,
        "allow_trade_execution": False,
        "requires_human_review": True,
        "next_allowed_action": "Stop and review score provenance evidence; if continuing, rerun same Pool A strategy with v8.2 score source and explicit aligned window.",
        "reason": "v8.2 frozen scores come from v8.1 Alpha360 runtime score trail, while v9 local replay refits a local Alpha360-compatible score chain; score/rank overlap is insufficient and baseline-only PLTR/SNOW pollution remains.",
    }


def normalize_score_source_v82(df: pd.DataFrame, top_k: int = 5) -> pd.DataFrame:
    out = pd.DataFrame()
    if df.empty:
        return out
    out["rebalance_date"] = df["decision_date"].astype(str)
    out["ticker"] = df["ticker"].astype(str)
    out["score"] = pd.to_numeric(df.get("adjusted_score", df.get("raw_score")), errors="coerce")
    out["rank"] = pd.to_numeric(df.get("adjusted_rank", df.get("raw_rank")), errors="coerce")
    out["selected"] = out["rank"].le(top_k)
    return out


def normalize_score_source_v9(df: pd.DataFrame, top_k: int = 5) -> pd.DataFrame:
    out = pd.DataFrame()
    if df.empty:
        return out
    out["rebalance_date"] = df["decision_date"].astype(str)
    out["ticker"] = df["ticker"].astype(str)
    out["score"] = pd.to_numeric(df["score"], errors="coerce")
    out["rank"] = pd.to_numeric(df["raw_rank"], errors="coerce")
    out["selected"] = out["rank"].le(top_k)
    return out


def load_close_matrix() -> pd.DataFrame:
    frames = {}
    if not PRICE_DIR.exists():
        return pd.DataFrame()
    for path in sorted(PRICE_DIR.glob("*.parquet")):
        try:
            df = pd.read_parquet(path, columns=["date", "adj_close", "close"])
        except Exception:
            try:
                df = pd.read_parquet(path)
            except Exception:
                continue
        if "date" not in df:
            continue
        price_col = "adj_close" if "adj_close" in df else "close"
        frames[path.stem] = pd.Series(pd.to_numeric(df[price_col], errors="coerce").values, index=pd.to_datetime(df["date"]))
    return pd.DataFrame(frames).sort_index().ffill()


def holdings_to_weights(holdings: pd.DataFrame) -> pd.DataFrame:
    h = holdings.copy()
    h["date"] = pd.to_datetime(h["date"])
    pivot = h.pivot_table(index="date", columns="ticker", values="weight", aggfunc="sum")
    return pivot.sort_index().fillna(0.0)


def find_reported_metrics(active: pd.DataFrame, source: str, strategy_id: str, window_type: str, daily: pd.DataFrame) -> dict[str, float]:
    family = "top10" if "top10" in str(strategy_id).lower() else "top5"
    source_key = "v8_2_frozen" if source == "v8_2_frozen" else "v9_local_replay"
    row = active.loc[
        active["strategy_family"].astype(str).eq(family)
        & active["source"].astype(str).eq(source_key)
        & active["window_type"].astype(str).eq(window_type)
    ]
    if row.empty and source_key == "v8_2_frozen":
        row = active.loc[
            active["strategy_family"].astype(str).eq(family)
            & active["source"].astype(str).eq(source_key)
            & active["window_type"].astype(str).str.contains("v8_2_frozen_reference", na=False)
        ]
    if not row.empty:
        r = row.iloc[0]
        return {"cagr": safe_float(r.get("cagr")), "max_drawdown": safe_float(r.get("max_drawdown")), "calmar": safe_float(r.get("calmar"))}
    d = daily.copy()
    return {"cagr": np.nan, "max_drawdown": np.nan, "calmar": np.nan}


def manifest_row(source_name: str, run_dir: Path, report_path: Path, key_csv_paths: list[Path], date_series: pd.Series, universe_name: str, strategy_name: str, feature_set: str, model_name: str, label_name: str, portfolio_template: str, cost_bps: float, slippage_bps: float, execution_lag: str, ytd_cap: float, derisk_ratio: float, status: str) -> dict[str, Any]:
    dates = pd.to_datetime(date_series, errors="coerce").dropna()
    return {
        "source_name": source_name,
        "run_dir": str(run_dir),
        "report_path": str(report_path),
        "key_csv_paths": ";".join(str(p) for p in key_csv_paths),
        "date_start": date_str(dates.min()) if len(dates) else "",
        "date_end": date_str(dates.max()) if len(dates) else "",
        "universe_name": universe_name,
        "strategy_name": strategy_name,
        "feature_set": feature_set,
        "model_name": model_name,
        "label_name": label_name,
        "portfolio_template": portfolio_template,
        "cost_bps": cost_bps,
        "slippage_bps": slippage_bps,
        "execution_lag": execution_lag,
        "ytd_cap": ytd_cap,
        "derisk_ratio": derisk_ratio,
        "status": status,
    }


def score_source_row(
    source_name: str,
    path: Path,
    df: pd.DataFrame,
    feature_set: str,
    label_definition: str,
    label_shift: str,
    fit_window: str,
    prediction_window: str,
    feature_count_hint: Any = "",
) -> dict[str, Any]:
    dates = pd.to_datetime(df.get("decision_date", df.get("date", pd.Series(dtype=str))), errors="coerce").dropna()
    return {
        "source_name": source_name,
        "feature_cache_path": str(path),
        "feature_set": feature_set,
        "feature_count": feature_count_hint if feature_count_hint else int(len([c for c in df.columns if c.startswith("f")])) if not df.empty else 0,
        "row_count": int(len(df)),
        "date_min": date_str(dates.min()) if len(dates) else "",
        "date_max": date_str(dates.max()) if len(dates) else "",
        "instruments_count": int(df["ticker"].nunique()) if "ticker" in df else 0,
        "hash_or_fingerprint": file_fingerprint(path),
        "label_definition": label_definition,
        "label_shift": label_shift,
        "fit_window_definition": fit_window,
        "prediction_window_definition": prediction_window,
    }


def feature_cache_row(source_name: str, path: Path) -> dict[str, Any]:
    files = sorted(path.glob("*_features.parquet")) if path.exists() else []
    row_count = 0
    col_count = 0
    dates = []
    instruments = set()
    for fp in files:
        try:
            df = pd.read_parquet(fp, columns=["date", "ticker"])
            row_count += len(df)
            dates.extend(pd.to_datetime(df["date"], errors="coerce").dropna().tolist())
            instruments.update(df["ticker"].dropna().astype(str).unique().tolist())
            if col_count == 0:
                col_count = len(pd.read_parquet(fp).columns)
        except Exception:
            continue
    return {
        "source_name": source_name,
        "feature_cache_path": str(path),
        "feature_set": "legacy feature_builder cache, not Alpha360",
        "feature_count": col_count,
        "row_count": row_count,
        "date_min": date_str(min(dates)) if dates else "",
        "date_max": date_str(max(dates)) if dates else "",
        "instruments_count": len(instruments),
        "hash_or_fingerprint": directory_fingerprint(files),
        "label_definition": "contains forward_return labels, not v8.2 Alpha360 cache",
        "label_shift": "various forward labels",
        "fit_window_definition": "metadata only",
        "prediction_window_definition": "metadata only",
    }


def infer_decision_from_execution(dates: pd.Series) -> dict[pd.Timestamp, str]:
    unique = sorted(pd.to_datetime(dates).dropna().unique())
    mapping = {}
    for d in unique:
        ts = pd.Timestamp(d)
        if ts.day <= 3:
            mapping[ts] = ""
    return mapping


def cost50_metrics(t: AuditTables, source: Any, strategy_id: Any) -> dict[str, float]:
    if str(source) == "v8_2_frozen":
        r = t.v82_results.loc[t.v82_results["strategy_id"].astype(str).eq(str(strategy_id))]
        if not r.empty:
            row = r.iloc[0]
            return {"cagr": safe_float(row.get("cost50_t1_cagr")), "calmar": safe_float(row.get("cost50_t1_calmar"))}
    stress = read_csv(V9_REVERSE_DIR / "stress_test.csv")
    family = "top10" if "top10" in str(strategy_id).lower() else "top5"
    scope = f"v9_local_pool_a_{family}"
    r = stress.loc[stress["strategy_scope"].astype(str).eq(scope) & stress["stress_type"].astype(str).eq("cost_slippage_bps") & pd.to_numeric(stress["cost_bps"], errors="coerce").eq(50.0)]
    if not r.empty:
        row = r.iloc[0]
        return {"cagr": safe_float(row.get("cagr")), "calmar": safe_float(row.get("calmar"))}
    return {"cagr": np.nan, "calmar": np.nan}


def top_ticker_share_for(t: AuditTables, source: Any, strategy_id: Any) -> float:
    if str(source) == "v8_2_frozen":
        r = t.v82_results.loc[t.v82_results["strategy_id"].astype(str).eq(str(strategy_id))]
        return safe_float(r.iloc[0].get("top_ticker_share")) if not r.empty else np.nan
    family = "top10" if "top10" in str(strategy_id).lower() else "top5"
    r = t.diff_by_ticker.loc[t.diff_by_ticker["strategy_family"].astype(str).eq(family) & t.diff_by_ticker["source"].astype(str).eq("v9_local_replay")]
    return safe_float(r["abs_share"].max()) if not r.empty else np.nan


def stress_metric(t: AuditTables, source: Any, strategy_id: Any, stress_type: str) -> dict[str, float]:
    if str(source) == "v8_2_frozen":
        r = t.v82_results.loc[t.v82_results["strategy_id"].astype(str).eq(str(strategy_id))]
        if not r.empty:
            row = r.iloc[0]
            if "year" in stress_type:
                return {"cagr": safe_float(row.get("remove_top_year_cagr")), "calmar": safe_float(row.get("remove_top_year_calmar"))}
            return {"cagr": safe_float(row.get("remove_top_ticker_cagr")), "calmar": safe_float(row.get("remove_top_ticker_calmar"))}
    stress = read_csv(V9_REVERSE_DIR / "stress_test.csv")
    family = "top10" if "top10" in str(strategy_id).lower() else "top5"
    scope = f"v9_local_pool_a_{family}"
    r = stress.loc[stress["strategy_scope"].astype(str).eq(scope) & stress["stress_type"].astype(str).eq(stress_type)]
    if not r.empty:
        row = r.iloc[0]
        return {"cagr": safe_float(row.get("cagr")), "calmar": safe_float(row.get("calmar"))}
    return {"cagr": np.nan, "calmar": np.nan}


def first_row(df: pd.DataFrame) -> dict[str, Any]:
    return df.iloc[0].to_dict() if df is not None and not df.empty else {}


def next_date_after(dates: pd.Series, date_value: Any) -> str:
    if not date_value:
        return ""
    all_dates = pd.to_datetime(dates, errors="coerce").dropna().sort_values()
    target = pd.Timestamp(date_value)
    later = all_dates[all_dates > target]
    return date_str(later.iloc[0]) if len(later) else ""


def cannot_recompute_row(source_name: str, reason: str) -> dict[str, Any]:
    return {
        "source_name": source_name,
        "start_date": "",
        "end_date": "",
        "reported_cagr": np.nan,
        "recomputed_cagr": np.nan,
        "reported_maxdd": np.nan,
        "recomputed_maxdd": np.nan,
        "reported_calmar": np.nan,
        "recomputed_calmar": np.nan,
        "diff_cagr": np.nan,
        "diff_maxdd": np.nan,
        "diff_calmar": np.nan,
        "pass_recalc": False,
        "recompute_status": f"cannot_recompute: {reason}",
    }


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def min_or_blank(values: pd.Series) -> str:
    dates = pd.to_datetime(values, errors="coerce").dropna()
    return date_str(dates.min()) if len(dates) else ""


def max_or_blank(values: pd.Series) -> str:
    dates = pd.to_datetime(values, errors="coerce").dropna()
    return date_str(dates.max()) if len(dates) else ""


def overlap_ratio(a: set[str], b: set[str]) -> float:
    denom = max(len(a), len(b), 1)
    return len(a & b) / denom


def file_fingerprint(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    h = hashlib.sha256()
    h.update(str(path.stat().st_size).encode())
    with path.open("rb") as handle:
        h.update(handle.read(1024 * 1024))
    return h.hexdigest()[:16]


def directory_fingerprint(files: list[Path]) -> str:
    h = hashlib.sha256()
    for path in files[:200]:
        if path.exists():
            h.update(path.name.encode())
            h.update(str(path.stat().st_size).encode())
    return h.hexdigest()[:16] if files else ""


def safe_float(value: Any) -> float:
    try:
        if value is None or pd.isna(value):
            return float("nan")
        return float(value)
    except Exception:
        return float("nan")


def date_str(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    try:
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    except Exception:
        return str(value)
