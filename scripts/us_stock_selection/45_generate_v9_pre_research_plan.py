"""Generate v9 pre-research universe and stock-selection rebuild design pack.

This is not formal v9. It does not expand the universe, train models, run 31b,
continue v8.1 overlay, continue v8.2 reranking, run new backtests, or start MVE 1.
It only reads existing evidence and writes pre-research design artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
DOCS_DIR = PROJECT_ROOT / "docs"
MEISTOCK_ROOT = Path("E:/dzhwork/obsydian/quant_lab/MeiStock")

FINAL_CLOSEOUT_ZIP = OUTPUT_ROOT / "us_stock_selection_quant_lab_v8_v8_2_final_closeout_20260501_190000.zip"
FINAL_CLOSEOUT_DIR = OUTPUT_ROOT / "v8_v8_2_final_closeout_20260501_190000"
BASELINE_RUN_DIR = OUTPUT_ROOT / "run_20260426_095958"
BOUNDED_AUDIT_DIR = OUTPUT_ROOT / "v8_2_bounded_audit_replay_20260501_113100"
FINAL_0P05_ZIP = OUTPUT_ROOT / "us_stock_selection_quant_lab_v8_2_0p05_final_validation_20260501_183000.zip"
NEXT_STEPS = PROJECT_ROOT / "NEXT_STEPS.md"
MEISTOCK_CONTEXT = MEISTOCK_ROOT / "docs" / "context" / "MeiStock_current_context.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate v9 pre-research design pack.")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args()


def setup_logger(out_dir: Path) -> logging.Logger:
    log_dir = out_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("v9_pre_research_plan")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh = logging.FileHandler(log_dir / "run.log", encoding="utf-8")
    fh.setFormatter(formatter)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def zip_count(path: Path) -> int | None:
    if not path.is_file() or path.suffix.lower() != ".zip":
        return None
    with zipfile.ZipFile(path, "r") as zf:
        return len(zf.infolist())


def write_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_final_decision() -> dict[str, Any]:
    path = FINAL_CLOSEOUT_DIR / "us_stock_selection_final_decision.json"
    return read_json(path)


def read_strategy_comparison() -> pd.DataFrame:
    return pd.read_csv(FINAL_CLOSEOUT_DIR / "us_stock_selection_final_strategy_comparison.csv")


def bounded_audit_stats() -> dict[str, Any]:
    audit = pd.read_csv(BOUNDED_AUDIT_DIR / "v8_2_full_score_rank_audit_trail.csv")
    quality = pd.read_csv(BOUNDED_AUDIT_DIR / "v8_2_full_audit_quality.csv")
    tickers = sorted(audit["ticker"].astype(str).str.upper().unique().tolist())
    return {
        "candidate_ticker_count": len(tickers),
        "tickers": tickers,
        "decision_dates": int(audit["decision_date"].nunique()),
        "min_decision_date": str(pd.to_datetime(audit["decision_date"]).min().date()),
        "max_decision_date": str(pd.to_datetime(audit["decision_date"]).max().date()),
        "candidate_count_per_month_min": int(quality["candidate_count"].min()) if "candidate_count" in quality else None,
        "candidate_count_per_month_max": int(quality["candidate_count"].max()) if "candidate_count" in quality else None,
        "selected_count_per_month_min": int(quality["selected_count"].min()) if "selected_count" in quality else None,
        "selected_count_per_month_max": int(quality["selected_count"].max()) if "selected_count" in quality else None,
    }


def evidence_index(final_decision: dict[str, Any]) -> pd.DataFrame:
    items = [
        {
            "evidence_name": "v8_v8_2_final_closeout_zip",
            "path": str(FINAL_CLOSEOUT_ZIP),
            "evidence_type": "zip",
            "used_for": "final strategy decision and route closeout",
            "key_findings": "v8 baseline remains current best; 0p05 is risk-control variant; no v9.",
            "limitations": "closeout summary only; no new data or experiments.",
        },
        {
            "evidence_name": "v8_baseline_run",
            "path": str(BASELINE_RUN_DIR),
            "evidence_type": "run_dir",
            "used_for": "baseline run status and existing v8 artifacts",
            "key_findings": "v8 baseline is return-priority current best.",
            "limitations": "short 2024-2026 window and 36-candidate universe.",
        },
        {
            "evidence_name": "v8_2_bounded_audit_replay",
            "path": str(BOUNDED_AUDIT_DIR),
            "evidence_type": "run_dir",
            "used_for": "full candidate score/rank evidence",
            "key_findings": "18 decision dates, 36 candidates each, full candidate score/rank audit available.",
            "limitations": "still limited to original 36-candidate universe.",
        },
        {
            "evidence_name": "v8_2_0p05_final_validation_zip",
            "path": str(FINAL_0P05_ZIP),
            "evidence_type": "zip",
            "used_for": "risk-control variant decision",
            "key_findings": "0p05 validated as risk_control_variant; not baseline replacement.",
            "limitations": "cost safety margin thin and top-month concentration remains high.",
        },
        {
            "evidence_name": "NEXT_STEPS",
            "path": str(NEXT_STEPS),
            "evidence_type": "markdown",
            "used_for": "current project checkpoint state",
            "key_findings": "v8/v8.2 closed; next stage requires new pre-research.",
            "limitations": "narrative checkpoint, not source data.",
        },
        {
            "evidence_name": "MeiStock_current_context",
            "path": str(MEISTOCK_CONTEXT),
            "evidence_type": "markdown/context",
            "used_for": "knowledge-base checkpoint synchronization",
            "key_findings": "MeiStock context reflects final closeout and no-v9 status.",
            "limitations": "context summary only.",
        },
    ]
    rows = []
    for item in items:
        path = Path(item["path"])
        rows.append(
            {
                **item,
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.is_file() else "",
                "sha256": sha256(path),
                "zip_entry_count": zip_count(path),
                "read_status": "read/indexed" if path.exists() else "missing",
            }
        )
    return pd.DataFrame(rows)


def boundary_review(stats: dict[str, Any]) -> pd.DataFrame:
    tickers = set(stats["tickers"])
    seven = {"AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"}
    rows = [
        {
            "boundary_category": "current_universe",
            "boundary_item": "candidate_ticker_count",
            "current_state": stats["candidate_ticker_count"],
            "finding": "Current v8/v8.2 candidate pool is narrow.",
            "limitation": "36 candidates likely constrain strategy upper bound and diversification.",
            "next_stage_implication": "Universe redesign is required before formal v9.",
        },
        {
            "boundary_category": "current_universe",
            "boundary_item": "only_36_candidates",
            "current_state": stats["candidate_ticker_count"] == 36,
            "finding": "Bounded audit replay confirms 36 candidates per decision month.",
            "limitation": "Small universe increases concentration and top-month dependency.",
            "next_stage_implication": "Do not tune inside same 36 names; redesign layers first.",
        },
        {
            "boundary_category": "current_universe",
            "boundary_item": "contains_seven_majors",
            "current_state": bool(seven & tickers),
            "finding": f"Observed seven-major overlap: {','.join(sorted(seven & tickers))}",
            "limitation": "Mega-cap tech exposure may dominate style regime.",
            "next_stage_implication": "Separate mega-cap layer and style exposure audit.",
        },
        {
            "boundary_category": "current_universe",
            "boundary_item": "contains_QLD_TQQQ",
            "current_state": {"QLD", "TQQQ"}.issubset(tickers),
            "finding": "Leveraged ETF proxies exist in same selection pool.",
            "limitation": "Leveraged ETFs do not share ordinary-stock risk assumptions.",
            "next_stage_implication": "Use separate leveraged ETF bucket.",
        },
        {
            "boundary_category": "current_universe",
            "boundary_item": "contains_sector_or_style_etf",
            "current_state": bool({"XLK", "IWM", "UPRO", "SSO"} & tickers),
            "finding": "ETF/style proxies are mixed with single names.",
            "limitation": "ETF and stock signals have different volatility and diversification behavior.",
            "next_stage_implication": "Evaluate sector/theme ETF layer separately.",
        },
        {
            "boundary_category": "current_universe",
            "boundary_item": "contains_high_beta_single_names",
            "current_state": bool({"MSTR", "TSLA", "PLTR"} & tickers),
            "finding": "High-beta names are present and materially affect results.",
            "limitation": "High-beta dependence was central to v8/v8.2 tradeoff.",
            "next_stage_implication": "Pre-register high-beta concentration gate.",
        },
        {
            "boundary_category": "current_universe",
            "boundary_item": "survivorship_bias_risk",
            "current_state": "material_risk",
            "finding": "Current curated pool may embed ex-post survivor/leader bias.",
            "limitation": "Can overstate robustness if weak delisted/failed names are absent.",
            "next_stage_implication": "Need historical membership and survivorship-aware universe construction.",
        },
        {
            "boundary_category": "history_length",
            "boundary_item": "date_range",
            "current_state": f"{stats['min_decision_date']} to {stats['max_decision_date']}",
            "finding": f"{stats['decision_dates']} decision dates in bounded audit replay.",
            "limitation": "Too short for durable cycle inference.",
            "next_stage_implication": "Need 10-15 years price history before model rebuild.",
        },
        {
            "boundary_category": "history_length",
            "boundary_item": "complete_years",
            "current_state": "about 2 full years",
            "finding": "2024-2026 window is short.",
            "limitation": "Insufficient bear/rate/regime coverage.",
            "next_stage_implication": "Run data audit first, not model training.",
        },
        {
            "boundary_category": "history_length",
            "boundary_item": "decision_dates_count",
            "current_state": stats["decision_dates"],
            "finding": "Bounded audit replay covers the known v8 decision dates.",
            "limitation": "Eighteen monthly decisions are too few for robust model selection.",
            "next_stage_implication": "Formal v9 requires materially longer monthly decision history.",
        },
        {
            "boundary_category": "history_length",
            "boundary_item": "bear_market_coverage",
            "current_state": "not_sufficiently_covered",
            "finding": "The 2024-2026 sample does not provide a full independent bear-market cycle.",
            "limitation": "Drawdown and weak-window behavior may be under-tested.",
            "next_stage_implication": "Require longer history and explicit regime split before strategy rebuild.",
        },
        {
            "boundary_category": "history_length",
            "boundary_item": "rate_cycle_coverage",
            "current_state": "incomplete",
            "finding": "Current sample is too short to isolate rising-rate, falling-rate, and steady-rate regimes.",
            "limitation": "Regime-conditioned stock selection cannot be validated yet.",
            "next_stage_implication": "Regime fields are optional until data audit confirms long history.",
        },
        {
            "boundary_category": "history_length",
            "boundary_item": "large_tech_regime_coverage",
            "current_state": "limited",
            "finding": "Large-cap technology leadership is present but over a narrow regime window.",
            "limitation": "Mega-cap style dependence may be mistaken for persistent stock-selection skill.",
            "next_stage_implication": "Separate mega-cap layer and validate across multiple technology cycles.",
        },
        {
            "boundary_category": "model",
            "boundary_item": "score_source",
            "current_state": "v8 paper replay model.predict score",
            "finding": "Full candidate score/rank now exists only after bounded audit replay.",
            "limitation": "Objective did not explicitly optimize concentration or risk-adjusted ranking.",
            "next_stage_implication": "Rebuild ranking label/objective.",
        },
        {
            "boundary_category": "model",
            "boundary_item": "selected_unselected_comparison",
            "current_state": "available_after_v8_2_bounded_audit",
            "finding": "Full audit trail supports selected/unselected comparison for v8.2 only.",
            "limitation": "Original v8 artifacts were selected-only.",
            "next_stage_implication": "Formal v9 must persist full audit from inception.",
        },
        {
            "boundary_category": "model",
            "boundary_item": "full_candidate_ranking",
            "current_state": "available_after_replay_not_original_baseline",
            "finding": "v8.2 bounded audit recovered decision_date x candidate score/rank without changing v8 logic.",
            "limitation": "The original baseline run did not natively store unselected candidates.",
            "next_stage_implication": "New pipeline must treat full candidate ranking as a first-class output.",
        },
        {
            "boundary_category": "model",
            "boundary_item": "feature_cache",
            "current_state": "available_for_v8_path",
            "finding": "Feature cache supported replay and diagnostics.",
            "limitation": "Cache coverage is tied to the current 36-name universe and short sample.",
            "next_stage_implication": "Long-history layer data audit must include feature coverage by ticker/date.",
        },
        {
            "boundary_category": "model",
            "boundary_item": "forward_audit_fields",
            "current_state": "available_and_isolated_in_v8_2",
            "finding": "v8.2 enforced audit_forward fields as audit-only.",
            "limitation": "The isolation rule must be rebuilt into any new v9 prototype from day one.",
            "next_stage_implication": "Add automatic feature-usage audits to future ranking scripts.",
        },
        {
            "boundary_category": "model",
            "boundary_item": "walk_forward_model_selection",
            "current_state": "not_sufficient_for_formal_v9",
            "finding": "v8/v8.2 did not establish a long-history purged/embargoed WF model-selection framework.",
            "limitation": "Parameter/model confidence is limited without stronger out-of-sample protocol.",
            "next_stage_implication": "Validation framework upgrade is a blocking prerequisite.",
        },
        {
            "boundary_category": "validation",
            "boundary_item": "existing_gates",
            "current_state": "LOO, rolling 12M, top-month stress, ticker concentration, cost stress",
            "finding": "Robustness gates exist but are post-hoc around a short sample.",
            "limitation": "No PBO/DSR and no future paper trading yet.",
            "next_stage_implication": "Upgrade validation framework before formal v9.",
        },
        {
            "boundary_category": "validation",
            "boundary_item": "leave_one_year_out",
            "current_state": "available_but_short_sample",
            "finding": "LOO was used in v8/v8.2 analysis.",
            "limitation": "Few complete years reduce statistical meaning.",
            "next_stage_implication": "Keep LOO, but only as one gate within longer-history validation.",
        },
        {
            "boundary_category": "validation",
            "boundary_item": "rolling_12m",
            "current_state": "available_but_short_sample",
            "finding": "Rolling 12M and weakest-window checks identified fragility.",
            "limitation": "Short sample leaves too few independent rolling windows.",
            "next_stage_implication": "Require longer rolling-window distribution before acceptance.",
        },
        {
            "boundary_category": "validation",
            "boundary_item": "top_month_stress",
            "current_state": "available_and_material",
            "finding": "Top-month sensitivity remains a core risk for both baseline and 0p05.",
            "limitation": "Performance depends heavily on a small number of positive months.",
            "next_stage_implication": "Pre-register top1/top3/top5 month gates in future experiments.",
        },
        {
            "boundary_category": "validation",
            "boundary_item": "ticker_concentration",
            "current_state": "available_and_material",
            "finding": "High-beta ticker concentration was reduced by 0p05 but not eliminated as a research risk.",
            "limitation": "Small universe mechanically raises repeated ticker exposure.",
            "next_stage_implication": "Use layer-aware ticker and high-beta exposure gates.",
        },
        {
            "boundary_category": "validation",
            "boundary_item": "cost_stress",
            "current_state": "available",
            "finding": "50bps and higher cost stress separated return-priority vs risk-control tradeoffs.",
            "limitation": "0p05 had thin 50bps safety margin and weakened above 50bps.",
            "next_stage_implication": "Formal v9 must fix cost/slippage ladder before model testing.",
        },
        {
            "boundary_category": "validation",
            "boundary_item": "PBO_DSR",
            "current_state": "not_implemented",
            "finding": "No formal Probability of Backtest Overfitting or Deflated Sharpe Ratio gate yet.",
            "limitation": "Backtest selection risk is not quantified.",
            "next_stage_implication": "Assess feasibility after MVE 1/2 define data and experiment count.",
        },
        {
            "boundary_category": "validation",
            "boundary_item": "post_freeze_paper_trading",
            "current_state": "not_started",
            "finding": "No frozen future-sample paper trading for the next-generation system yet.",
            "limitation": "Historical replay cannot prove live robustness.",
            "next_stage_implication": "Require freeze plan before production/paper-trading candidate status.",
        },
        {
            "boundary_category": "unresolved_problem",
            "boundary_item": "top_month_concentration",
            "current_state": "material",
            "finding": "v8 and 0p05 both rely heavily on a small set of positive months.",
            "limitation": "Weakens confidence in long-term repeatability.",
            "next_stage_implication": "Add top-month and concentration-aware objectives/gates.",
        },
        {
            "boundary_category": "unresolved_problem",
            "boundary_item": "short_sample",
            "current_state": "material",
            "finding": "Current evidence is strong for the explored window, not for durable multi-cycle inference.",
            "limitation": "Raises overfit and regime-dependence risk.",
            "next_stage_implication": "MVE 1 is the correct next step.",
        },
        {
            "boundary_category": "unresolved_problem",
            "boundary_item": "high_beta_dependence",
            "current_state": "material",
            "finding": "High-beta exposure drove both opportunity and fragility.",
            "limitation": "Risk-control variant sacrifices return and still has concentration risk.",
            "next_stage_implication": "Treat high-beta stocks and leveraged ETFs as explicit buckets.",
        },
        {
            "boundary_category": "unresolved_problem",
            "boundary_item": "small_universe",
            "current_state": "material",
            "finding": "The 36-name universe restricts diversification and learning capacity.",
            "limitation": "Further tuning inside the same pool has rising overfit risk.",
            "next_stage_implication": "Do not expand blindly; design and audit layered universe first.",
        },
        {
            "boundary_category": "unresolved_problem",
            "boundary_item": "ranking_objective_not_concentration_aware",
            "current_state": "material",
            "finding": "v8 score/rank did not explicitly penalize concentration, high-beta dependence, or top-month sensitivity.",
            "limitation": "Reranking patches helped diagnostics but did not produce a replacement strategy.",
            "next_stage_implication": "Rebuild labels/objectives rather than continue post-hoc reranking.",
        },
        {
            "boundary_category": "unresolved_problem",
            "boundary_item": "true_out_of_sample_validation",
            "current_state": "missing",
            "finding": "No future frozen-sample paper trading exists for a rebuilt system.",
            "limitation": "Live deployment confidence remains limited.",
            "next_stage_implication": "Paper trading comes after MVE 1/2/3 and candidate freeze.",
        },
    ]
    return pd.DataFrame(rows)


def universe_design() -> pd.DataFrame:
    rows = [
        {
            "layer_name": "Layer 1 - Core mega-cap tech",
            "inclusion_rule": "Seven majors and core liquid technology leaders with long adjusted history.",
            "exclusion_rule": "Exclude insufficient history, poor liquidity, non-primary share classes unless explicitly mapped.",
            "expected_size": "10-20",
            "required_data": "OHLCV, adjusted close, corporate actions, fundamentals, beta/volatility.",
            "liquidity_filter": "Very high ADV and tight spread proxy.",
            "history_length_filter": "Prefer 10-15 years where listing history allows.",
            "survivorship_bias_risk": "medium",
            "expected_benefit": "Stable, liquid, high-quality anchor layer.",
            "expected_risk": "Crowding, valuation, growth-style regime dependence.",
            "recommended_priority": 1,
            "whether_ready_for_next_stage": "design_ready_data_audit_needed",
        },
        {
            "layer_name": "Layer 2 - Nasdaq100 liquid subset",
            "inclusion_rule": "Select from Nasdaq100 by liquidity, history length, data completeness, sector balance.",
            "exclusion_rule": "Do not include full Nasdaq100 automatically; exclude short-history and low-liquidity names.",
            "expected_size": "50-80",
            "required_data": "OHLCV, adjusted close, membership history if available, liquidity, fundamentals.",
            "liquidity_filter": "ADV threshold and missing-data limit.",
            "history_length_filter": "At least 7-10 years preferred; shorter names flagged separately.",
            "survivorship_bias_risk": "high_without_membership_history",
            "expected_benefit": "Broader alpha search without uncontrolled full-pool expansion.",
            "expected_risk": "Survivorship bias and sector crowding.",
            "recommended_priority": 2,
            "whether_ready_for_next_stage": "requires_membership_and_data_audit",
        },
        {
            "layer_name": "Layer 3 - S&P500 growth / quality subset",
            "inclusion_rule": "Growth/quality/liquid S&P500 names selected by pre-registered filters.",
            "exclusion_rule": "Avoid blind low-alpha broad S&P500 expansion.",
            "expected_size": "50-100",
            "required_data": "OHLCV, fundamentals, quality/growth metrics, liquidity.",
            "liquidity_filter": "Large-cap ADV and spread proxy.",
            "history_length_filter": "10-15 years preferred.",
            "survivorship_bias_risk": "high_without_historical_constituents",
            "expected_benefit": "Diversifies away from pure Nasdaq growth.",
            "expected_risk": "Dilutes alpha if filters are weak.",
            "recommended_priority": 3,
            "whether_ready_for_next_stage": "concept_ready_filters_needed",
        },
        {
            "layer_name": "Layer 4 - Sector/theme ETF",
            "inclusion_rule": "Semiconductor, software, cloud, AI, cybersecurity, biotech, growth-style ETFs.",
            "exclusion_rule": "Exclude illiquid or too-short-history ETFs.",
            "expected_size": "10-30",
            "required_data": "Adjusted OHLCV, inception date, expense/leverage flag.",
            "liquidity_filter": "ETF ADV and spread proxy.",
            "history_length_filter": "Inception-aware; 10 years where possible.",
            "survivorship_bias_risk": "medium",
            "expected_benefit": "Smoother thematic exposure than single names.",
            "expected_risk": "Theme overlap and hidden concentration.",
            "recommended_priority": 2,
            "whether_ready_for_next_stage": "design_ready_data_audit_needed",
        },
        {
            "layer_name": "Layer 5 - Leveraged ETF separate bucket",
            "inclusion_rule": "QLD, TQQQ, SOXL and similar leveraged ETFs in a separate risk bucket.",
            "exclusion_rule": "Do not mix with ordinary stocks under same risk assumptions.",
            "expected_size": "3-10",
            "required_data": "Adjusted OHLCV, inception date, leverage factor, volatility decay diagnostics.",
            "liquidity_filter": "High liquidity only.",
            "history_length_filter": "Use from inception; flag short/structurally changed periods.",
            "survivorship_bias_risk": "medium",
            "expected_benefit": "Explicitly controls leveraged exposure rather than accidental selection.",
            "expected_risk": "Path dependency, volatility decay, crash sensitivity.",
            "recommended_priority": 1,
            "whether_ready_for_next_stage": "must_be_separate_bucket",
        },
        {
            "layer_name": "Layer 6 - High-beta single names",
            "inclusion_rule": "MSTR, TSLA, PLTR and other high beta/high volatility leaders with explicit gate.",
            "exclusion_rule": "Exclude if liquidity/history/audit insufficient or if concentration gate cannot be enforced.",
            "expected_size": "10-30",
            "required_data": "Adjusted OHLCV, beta/volatility/drawdown, liquidity, event/gap risk proxy.",
            "liquidity_filter": "High ADV and tradability only.",
            "history_length_filter": "Long enough for multiple regimes where possible.",
            "survivorship_bias_risk": "high",
            "expected_benefit": "Keeps high alpha/high beta expression available but controlled.",
            "expected_risk": "Dominates returns and drawdowns if not gated.",
            "recommended_priority": 1,
            "whether_ready_for_next_stage": "requires_pre_registered_high_beta_gate",
        },
    ]
    return pd.DataFrame(rows)


def data_requirements() -> pd.DataFrame:
    rows = [
        ("OHLCV", "required", "check local qlib fields/open/high/low/close/volume coverage by ticker-date", "local Qlib provider or approved vendor", "daily", "adjustment and survivorship risk", 1, True),
        ("adjusted close", "required", "validate adjusted close continuity and split/dividend adjustment", "local Qlib provider", "daily", "bad adjustment can create false returns", 1, True),
        ("corporate actions", "required", "audit split/dividend adjustment metadata or adjusted price reliability", "provider metadata", "event-driven", "incorrect adjustment leaks/warps labels", 1, True),
        ("ETF inception/listing date", "required", "compare first valid date by ETF", "local price history", "static/daily", "using pre-inception synthetic data is invalid", 1, True),
        ("revenue growth", "optional", "local fundamentals availability matrix", "fundamental vendor if approved", "quarterly", "report date lag/lookahead risk", 3, False),
        ("EPS growth", "optional", "local fundamentals availability matrix", "fundamental vendor if approved", "quarterly", "report date lag/lookahead risk", 3, False),
        ("gross margin", "optional", "local fundamentals availability matrix", "fundamental vendor if approved", "quarterly", "report date lag/lookahead risk", 3, False),
        ("ROE/ROIC", "optional", "local fundamentals availability matrix", "fundamental vendor if approved", "quarterly", "report date lag/lookahead risk", 3, False),
        ("FCF and valuation", "optional", "local fundamentals availability matrix", "fundamental vendor if approved", "quarterly", "report date lag/lookahead risk", 3, False),
        ("trailing volatility", "required", "derive from adjusted close using decision-date lag", "computed local feature", "daily/monthly", "must use only data <= decision_date", 1, True),
        ("beta/downside vol/max drawdown", "required", "derive from local returns vs QQQ/SPY using lagged windows", "computed local feature", "daily/monthly", "must use only data <= decision_date", 1, True),
        ("liquidity ADV/spread proxy", "required", "derive ADV from volume/dollar volume; spread proxy if available", "local OHLCV or vendor", "daily/monthly", "stale liquidity can bias tradability", 1, True),
        ("QQQ/SPY/Nasdaq100/VIX/rates regime", "optional_required_for_regime", "local availability check for index/ETF/regime series", "local provider; approved macro source if needed", "daily", "publication lag and revised data risk", 2, False),
        ("decision_date/candidate universe", "required", "assert persisted monthly universe snapshot", "pipeline audit trail", "monthly", "missing snapshot prevents ex-ante audit", 1, True),
        ("raw/adjusted score/rank/selected flag", "required", "assert decision_date x candidate score/rank trail", "pipeline audit trail", "monthly", "future score contamination risk", 1, True),
        ("forward returns/drawdown audit", "required_audit_only", "assert audit_forward prefix and blocked from ranking", "post-decision audit", "monthly", "must never enter ranking", 1, True),
        ("cost/slippage audit", "required", "store turnover and cost stress assumptions", "backtest/paper pipeline", "per run", "inconsistent costs distort comparisons", 1, True),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "data_name",
            "required_or_optional",
            "local_available_check_method",
            "source_candidate",
            "update_frequency",
            "lookahead_risk",
            "implementation_priority",
            "blocking_for_v9",
        ],
    )


def model_design() -> pd.DataFrame:
    rows = [
        {
            "design_name": "A - cross-sectional ranking baseline",
            "hypothesis": "A unified monthly cross-sectional ranker across full candidates beats selected-only heuristics.",
            "required_inputs": "full candidate universe, lagged features, 21/42/63D forward audit labels",
            "label_definition": "future 1M/2M/3M return or risk-adjusted return with strict decision-date lag",
            "model_candidate": "LightGBM ranker, Ridge/ElasticNet baseline, simple z-score ensemble",
            "validation_method": "purged/embargoed walk-forward with full audit trail",
            "expected_benefit": "transparent ranking baseline with selected/unselected comparison",
            "overfit_risk": "medium",
            "implementation_complexity": "medium",
            "recommended_priority": 1,
            "minimum_viable_experiment": "small layered universe, long history, no optimization, full audit trail",
        },
        {
            "design_name": "B - risk-adjusted target",
            "hypothesis": "Risk-adjusted labels reduce high-beta dependence and improve weakest-window robustness.",
            "required_inputs": "returns, vol, drawdown, downside vol, liquidity",
            "label_definition": "forward return / vol, return / drawdown, Calmar-like forward label",
            "model_candidate": "cross-sectional regression/ranking with robust labels",
            "validation_method": "rolling WF, weakest-12M gate, cost stress",
            "expected_benefit": "model naturally favors high risk-adjusted reward",
            "overfit_risk": "medium_high if labels are over-engineered",
            "implementation_complexity": "medium",
            "recommended_priority": 1,
            "minimum_viable_experiment": "compare return label vs risk-adjusted label on frozen feature set",
        },
        {
            "design_name": "C - concentration-aware objective",
            "hypothesis": "Explicit concentration and high-beta constraints reduce top-month/ticker dependence.",
            "required_inputs": "ticker exposure history, high-beta flags, sector/layer tags, monthly contribution audit",
            "label_definition": "ranking score plus pre-registered concentration penalty or portfolio construction gate",
            "model_candidate": "post-score optimizer or constrained topK selector",
            "validation_method": "top-month stress, ticker concentration, high-beta exposure gates",
            "expected_benefit": "controls the failure mode seen in v8/v8.2",
            "overfit_risk": "high if penalties are tuned repeatedly",
            "implementation_complexity": "medium_high",
            "recommended_priority": 2,
            "minimum_viable_experiment": "one pre-registered concentration penalty, no grid search",
        },
        {
            "design_name": "D - multi-horizon ensemble",
            "hypothesis": "Combining 21D/42D/63D horizons reduces single-window noise.",
            "required_inputs": "multi-horizon forward labels and lagged features",
            "label_definition": "weighted average or rank aggregation of multiple horizon labels",
            "model_candidate": "separate horizon rankers plus rank aggregation",
            "validation_method": "parameter-neighborhood stability and LOO",
            "expected_benefit": "less brittle monthly selection",
            "overfit_risk": "medium_high",
            "implementation_complexity": "medium_high",
            "recommended_priority": 3,
            "minimum_viable_experiment": "fixed 21/42/63D equal-weight rank blend",
        },
        {
            "design_name": "E - regime-conditional stock selection",
            "hypothesis": "Regime should alter which stocks are selected, not simply total exposure.",
            "required_inputs": "QQQ/SPY/VIX/rate regime features, high-beta flags, layer tags",
            "label_definition": "rank within regime-aware constraints; no future regime fields",
            "model_candidate": "rule-gated ranker or regime-conditioned model family",
            "validation_method": "regime split and post-freeze paper trading",
            "expected_benefit": "keeps growth exposure in strong regimes while reducing weak-regime beta",
            "overfit_risk": "high",
            "implementation_complexity": "high",
            "recommended_priority": 4,
            "minimum_viable_experiment": "only after MVE 1/2 and baseline ranker pass",
        },
    ]
    return pd.DataFrame(rows)


def validation_framework() -> pd.DataFrame:
    rows = [
        ("expanding walk-forward", "test increasing training window stability", "long history, full features", "all folds positive risk-adjusted performance", "hard_gate", 1, "baseline validation mode"),
        ("rolling walk-forward", "test recency-focused robustness", "long history", "fold pass rate above pre-registered threshold", "hard_gate", 1, "compare to expanding WF"),
        ("purged / embargoed split", "prevent label overlap leakage", "label horizon calendar", "no train/test leakage", "hard_gate", 1, "mandatory for multi-horizon labels"),
        ("regime split", "check bull/bear/rate sensitivity", "regime tags", "no catastrophic regime failure", "observation_then_gate", 2, "do not overfit regime definitions"),
        ("leave-one-year-out", "detect year dependence", "daily returns", "min CAGR >= 20%, min Calmar >= 1 where appropriate", "hard_gate", 1, "already useful in v8.2"),
        ("post-freeze paper trading", "future sample verification", "frozen strategy", "predefined paper period metrics", "hard_gate_for_production", 1, "no historical retuning"),
        ("full-period CAGR", "return adequacy", "daily NAV", ">= 20% minimum", "hard_gate", 1, "not sufficient alone"),
        ("50bps cost CAGR", "execution sensitivity", "turnover/cost", ">= 20%; strategy-specific higher gate", "hard_gate", 1, "v8/0p05 showed sensitivity"),
        ("Calmar / MaxDD", "risk-adjusted return", "daily NAV", "Calmar >= 1 and MaxDD not excessive", "hard_gate", 1, "primary metric remains Calmar"),
        ("rolling 12M min Calmar", "weak-window resilience", "daily/monthly NAV", ">= 1 where feasible", "hard_gate", 1, "must include weakest window"),
        ("top1/top3/top5 month share", "top-month concentration", "monthly contribution", "top3 <= 0.50, top5 monitored/limited", "hard_gate_or_observation", 1, "v8 failure mode"),
        ("remove top months stress", "dependence on best months", "monthly returns", "remove-top5 CAGR not near zero", "observation_then_gate", 1, "0p05 weak here"),
        ("ticker concentration", "single-name dependence", "holdings/contributions", "max ticker share <= pre-registered threshold", "hard_gate", 1, "MSTR risk observed"),
        ("high-beta exposure", "beta crash sensitivity", "high-beta flags/weights", "avg/max high-beta exposure below threshold", "hard_gate", 1, "separate leveraged ETF bucket"),
        ("turnover/cost stress", "execution feasibility", "trades/weights", "pass 0/10/25/50/75/100bps ladder", "hard_gate", 1, "cost model must be fixed"),
        ("limited pre-registered candidates", "overfit control", "experiment registry", "no broad grid search", "hard_gate", 1, "required before formal v9"),
        ("PBO/DSR", "overfit probability/stat confidence", "candidate results matrix", "implement if feasible", "observation", 3, "optional but valuable"),
        ("parameter neighborhood stability", "avoid knife-edge params", "nearby pre-registered params", "no single-point miracle", "observation_then_gate", 2, "0p05 had thin margin"),
        ("candidate freeze", "avoid history retuning", "frozen config", "freeze before paper trading", "hard_gate_for_paper", 1, "paper trading entry requirement"),
        ("acceptance tiering", "clear decision language", "all metrics", "research/risk-control/accepted/strong/paper tiers", "hard_gate", 1, "prevents best replacement drift"),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "validation_item",
            "purpose",
            "required_inputs",
            "pass_threshold_suggestion",
            "hard_gate_or_observation",
            "implementation_priority",
            "notes",
        ],
    )


def go_no_go() -> pd.DataFrame:
    rows = [
        ("10+ years history available", "not_verified", "available and quality-audited", True, "coverage report by ticker/layer", "Run MVE 1 first"),
        ("universe layering finalized", "draft_design_only", "approved layered universe spec", True, "universe layer CSV and data coverage", "Run MVE 2 after MVE 1"),
        ("full candidate score/rank audit available", "available_for_v8_2_only", "implemented from inception for new pipeline", True, "decision_date x candidate audit trail", "Make audit schema mandatory"),
        ("selected/unselected comparison", "available_for_v8_2_only", "available for all formal v9 experiments", True, "full candidate predictions and selected_flag", "Do not run selected-only experiments"),
        ("forward audit isolation", "validated_in_v8_2", "enforced in code and docs", True, "feature usage audit", "Keep audit_forward prefix and blocking checks"),
        ("cost/slippage policy", "partially_defined", "fixed ladder and production assumption", True, "cost policy doc", "Pre-register cost ladder"),
        ("walk-forward framework", "needs_upgrade", "purged/embargoed expanding and rolling WF", True, "WF runner and fold audit", "Build before MVE 3"),
        ("concentration gate", "draft_from_v8_2", "pre-registered gates by layer", True, "gate config", "Formalize before model tests"),
        ("paper trading plan", "not_defined", "frozen paper plan", True, "paper trading protocol", "Define after MVE 3"),
        ("broad grid tuning ban", "policy_defined", "explicit experiment guardrails", True, "experiment registry and code guard", "Keep narrow pre-registration"),
    ]
    return pd.DataFrame(rows, columns=["checklist_item", "status_now", "required_before_v9", "blocking", "evidence_needed", "recommended_action"])


def mve_plan() -> pd.DataFrame:
    rows = [
        {
            "mve_name": "MVE 1 - longer-history data audit",
            "objective": "Check whether local/provider data can support 10-15 year adjusted OHLCV and core risk features.",
            "input_needed": "candidate seed lists, local provider paths, adjusted OHLCV requirements",
            "output_expected": "coverage matrix, missing data report, listing/inception date table, no model/no backtest",
            "estimated_complexity": "low_medium",
            "risk": "data gaps, adjustment errors, ETF inception constraints",
            "success_criteria": ">=10 years clean history for core layers or explicit listing-date exceptions",
            "recommended_order": 1,
        },
        {
            "mve_name": "MVE 2 - universe layer prototype",
            "objective": "Build 3-layer small universe prototype for data completeness and feature coverage.",
            "input_needed": "MVE 1 coverage, mega-cap tech list, Nasdaq100 liquid subset, sector ETF list",
            "output_expected": "layered universe CSV and feature availability audit, no strategy optimization",
            "estimated_complexity": "medium",
            "risk": "survivorship bias and arbitrary filters",
            "success_criteria": "approved layer spec with liquidity/history filters and survivorship notes",
            "recommended_order": 2,
        },
        {
            "mve_name": "MVE 3 - cross-sectional ranking baseline prototype",
            "objective": "Prototype simple long-history full-candidate ranker with walk-forward and audit trail.",
            "input_needed": "MVE 1/2 pass, frozen small universe, lagged features, label definitions",
            "output_expected": "baseline ranker, full audit trail, WF diagnostics, not optimized for max return",
            "estimated_complexity": "medium_high",
            "risk": "overfit if too many candidates/labels are tried",
            "success_criteria": "reproducible full audit trail and WF sanity pass without broad grid search",
            "recommended_order": 3,
        },
    ]
    return pd.DataFrame(rows)


def md_table(df: pd.DataFrame, max_rows: int = 20) -> str:
    sub = df.head(max_rows).copy()
    return sub.to_markdown(index=False)


def write_docs(
    timestamp: str,
    out_dir: Path,
    zip_path: Path,
    evidence: pd.DataFrame,
    boundary: pd.DataFrame,
    universe: pd.DataFrame,
    data_req: pd.DataFrame,
    model: pd.DataFrame,
    validation: pd.DataFrame,
    checklist: pd.DataFrame,
    mve: pd.DataFrame,
) -> list[Path]:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = DOCS_DIR / f"US_STOCK_SELECTION_V9_PRE_RESEARCH_PLAN_{timestamp}.md"
    exec_path = DOCS_DIR / f"US_STOCK_SELECTION_V9_PRE_RESEARCH_EXEC_SUMMARY_{timestamp}.md"
    report = f"""# US Stock Selection v9 Pre-Research Plan

## 1. 为什么不能直接进入 v9

v8/v8.2 已收口，但当前样本短、universe 仅 36 个候选、top-month concentration 和 high-beta dependence 仍是核心风险。正式 v9 前必须先做数据、universe、模型目标和验证框架预研。

## 2. v8/v8.2 已验证的内容

- v8 baseline 是当前 return-priority best。
- 0p05 是 risk-control variant，不替代 baseline。
- v8.2 bounded audit replay 已证明 full candidate score/rank audit trail 可行。
- audit_forward 字段隔离和 selected/unselected 对比已在 v8.2 中验证。

## 3. v8/v8.2 主要限制

{md_table(boundary, max_rows=15)}

## 4. 下一阶段 Universe 设计

{md_table(universe, max_rows=10)}

## 5. 数据需求

{md_table(data_req, max_rows=25)}

## 6. Stock Selection Model 重构方案

{md_table(model, max_rows=10)}

## 7. Validation Framework 升级方案

{md_table(validation, max_rows=25)}

## 8. v9 Go/No-Go Checklist

{md_table(checklist, max_rows=20)}

## 9. 最小可执行任务建议

{md_table(mve, max_rows=10)}

## 10. 是否建议现在启动正式 v9

不建议。当前只建议先做预研 MVE，优先 MVE 1：longer-history data audit。MVE 1/2 通过后，才考虑 MVE 3。正式 v9 需要用户/ChatGPT 另行批准。

## 11. Evidence Index

{md_table(evidence, max_rows=10)}
"""
    exec_summary = """# US Stock Selection v9 Pre-Research Exec Summary

- 本轮不是正式 v9。
- 不扩 universe，不训练模型，不跑回测，不启动 MVE 1。
- v8 baseline 仍是 current best；0p05 仍是 risk-control variant。
- 下一阶段应先做 MVE 1：longer-history data audit。
- MVE 1/2 通过后，才考虑 MVE 3 cross-sectional ranking baseline prototype。
- 正式 v9 必须另行批准。
"""
    report_path.write_text(report, encoding="utf-8")
    exec_path.write_text(exec_summary, encoding="utf-8")
    reports_dir = out_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(report_path, reports_dir / report_path.name)
    shutil.copy2(exec_path, reports_dir / exec_path.name)
    return [report_path, exec_path]


def update_next_steps(out_dir: Path, zip_path: Path) -> None:
    path = NEXT_STEPS
    text = path.read_text(encoding="utf-8") if path.exists() else "# NEXT_STEPS\n"
    header = "## v9 pre-research universe and stock selection rebuild"
    section = f"""

{header}

- 执行状态：completed，随后按要求暂停，不启动 MVE 1。
- 输出目录：`{out_dir}`
- zip：`{zip_path}`
- v8/v8.2 是否已最终收口：`True`
- 当前是否进入正式 v9：`False`
- 本轮性质：`pre-research design pack only`
- 下一步建议：先执行 `MVE 1 - longer-history data audit`
- MVE 顺序：`MVE 1/2 通过后，才考虑 MVE 3`
- 正式 v9 是否需要另行批准：`True`
- 本轮边界：未进入正式 v9，未扩 universe，未训练模型，未跑回测，未启动 MVE。
"""
    pattern = re.compile(r"\n\n## v9 pre-research universe and stock selection rebuild\n.*?(?=\n\n## |\Z)", re.S)
    text = pattern.sub(lambda _: section, text) if pattern.search(text) else text.rstrip() + section
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def write_run_summary(out_dir: Path, zip_path: Path) -> None:
    text = f"""# RUN_SUMMARY

本轮目标：v9_pre_research_universe_and_stock_selection_rebuild。

新 run 目录：`{out_dir}`

zip：`{zip_path}`

是否正式进入 v9：`False`

是否扩 universe：`False`

是否训练模型：`False`

是否运行 31b：`False`

是否跑新回测：`False`

是否启动 MVE 1：`False`

下一步建议：`MVE 1 - longer-history data audit`，但需用户/ChatGPT 另行批准。
"""
    (PROJECT_ROOT / "RUN_SUMMARY.md").write_text(text, encoding="utf-8")
    (out_dir / "RUN_SUMMARY.md").write_text(text, encoding="utf-8")


def write_reports_workbook(out_dir: Path, timestamp: str, frames: dict[str, pd.DataFrame]) -> Path:
    reports_dir = out_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    workbook = reports_dir / f"v9_pre_research_design_tables_{timestamp}.xlsx"
    sheet_names = {
        "evidence_index": "evidence_index",
        "boundary_review": "boundary_review",
        "universe_design": "universe_design",
        "data_requirements": "data_requirements",
        "model_design": "model_design",
        "validation_framework": "validation",
        "go_no_go_checklist": "go_no_go",
        "next_mve_plan": "next_mve",
        "prior_strategy_comparison": "strategy_compare",
    }
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        for key, frame in frames.items():
            frame.to_excel(writer, sheet_name=sheet_names.get(key, key[:31]), index=False)
    return workbook


def sync_meistock(timestamp: str, out_dir: Path, zip_path: Path, docs: list[Path]) -> pd.DataFrame:
    rows = []
    if not MEISTOCK_ROOT.exists():
        return pd.DataFrame([{"target": str(MEISTOCK_ROOT), "status": "warning", "note": "MeiStock root missing"}])
    dirs = {
        "checkpoint": MEISTOCK_ROOT / "01_对话沉淀" / "Codex",
        "reports": MEISTOCK_ROOT / "02_项目文档" / "报告章节底稿",
        "evidence": MEISTOCK_ROOT / "06_证据链",
        "attachments": MEISTOCK_ROOT / "07_附件索引",
        "control": MEISTOCK_ROOT / "00_项目总控",
        "context": MEISTOCK_ROOT / "docs" / "context",
        "roadmap": MEISTOCK_ROOT / "04_文件地图",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    for doc in docs:
        dest = dirs["reports"] / doc.name
        shutil.copy2(doc, dest)
        rows.append({"target": str(dest), "status": "copied", "note": "report"})
    for source in out_dir.glob("v9_pre_research_*.csv"):
        dest = dirs["evidence"] / f"{timestamp}_{source.name}"
        shutil.copy2(source, dest)
        rows.append({"target": str(dest), "status": "copied", "note": "csv"})
    shutil.copy2(NEXT_STEPS, dirs["control"] / "NEXT_STEPS.md")
    rows.append({"target": str(dirs["control"] / "NEXT_STEPS.md"), "status": "copied", "note": "NEXT_STEPS"})
    if zip_path.exists():
        dest = dirs["attachments"] / zip_path.name
        shutil.copy2(zip_path, dest)
        rows.append({"target": str(dest), "status": "copied", "note": "zip"})
    checkpoint = f"""# Codex Checkpoint - v9 Pre-Research {timestamp}

- This is not formal v9.
- No universe expansion, no model training, no backtest, no MVE started.
- Next recommended task: MVE 1 longer-history data audit, pending approval.
- Zip: `{zip_path}`
"""
    cp = dirs["checkpoint"] / f"{timestamp}_v9_pre_research_checkpoint.md"
    cp.write_text(checkpoint, encoding="utf-8")
    rows.append({"target": str(cp), "status": "written", "note": "checkpoint"})
    roadmap = f"""# v9 Pre-Research Roadmap Index {timestamp}

Pre-research plan generated. Next recommended MVE is longer-history data audit. Formal v9 requires separate approval.
"""
    rp = dirs["roadmap"] / f"{timestamp}_v9_pre_research_roadmap_index.md"
    rp.write_text(roadmap, encoding="utf-8")
    rows.append({"target": str(rp), "status": "written", "note": "roadmap"})
    context = f"""# MeiStock Current Context

Last updated: {timestamp}

Latest checkpoint: v9 pre-research universe and stock selection rebuild design pack.

This is not formal v9. No universe expansion, no model training, no backtest, and no MVE was started.

Next recommended task: MVE 1 longer-history data audit, pending user/ChatGPT approval.

Latest zip: `{zip_path}`.
"""
    ctx = dirs["context"] / "MeiStock_current_context.md"
    ctx.write_text(context, encoding="utf-8")
    rows.append({"target": str(ctx), "status": "written", "note": "context"})
    return pd.DataFrame(rows)


def package(out_dir: Path, docs: list[Path], zip_path: Path) -> None:
    files = [
        PROJECT_ROOT / "scripts" / "us_stock_selection" / "45_generate_v9_pre_research_plan.py",
        NEXT_STEPS,
        PROJECT_ROOT / "RUN_SUMMARY.md",
        *docs,
    ]
    files.extend([p for p in out_dir.rglob("*") if p.is_file()])
    if zip_path.exists():
        zip_path.unlink()
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        seen = set()
        for path in files:
            if not path.exists():
                continue
            arc = str(path.relative_to(PROJECT_ROOT)) if path.is_relative_to(PROJECT_ROOT) else path.name
            if arc in seen:
                continue
            seen.add(arc)
            zf.write(path, arc)


def main() -> None:
    args = parse_args()
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = (args.out_dir or OUTPUT_ROOT / f"v9_pre_research_universe_stock_selection_rebuild_{timestamp}").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    logger = setup_logger(out_dir)
    logger.info("Starting v9 pre-research design pack. No v9, no training, no backtest.")

    final_decision = read_final_decision()
    comparison = read_strategy_comparison()
    stats = bounded_audit_stats()
    evidence = evidence_index(final_decision)
    boundary = boundary_review(stats)
    universe = universe_design()
    data_req = data_requirements()
    model = model_design()
    validation = validation_framework()
    checklist = go_no_go()
    mve = mve_plan()

    evidence.to_csv(out_dir / "v9_pre_research_evidence_index.csv", index=False, encoding="utf-8-sig")
    boundary.to_csv(out_dir / "v9_pre_research_v8_boundary_review.csv", index=False, encoding="utf-8-sig")
    universe.to_csv(out_dir / "v9_pre_research_universe_design.csv", index=False, encoding="utf-8-sig")
    data_req.to_csv(out_dir / "v9_pre_research_data_requirements.csv", index=False, encoding="utf-8-sig")
    model.to_csv(out_dir / "v9_pre_research_stock_selection_model_design.csv", index=False, encoding="utf-8-sig")
    validation.to_csv(out_dir / "v9_pre_research_validation_framework.csv", index=False, encoding="utf-8-sig")
    checklist.to_csv(out_dir / "v9_pre_research_go_no_go_checklist.csv", index=False, encoding="utf-8-sig")
    mve.to_csv(out_dir / "v9_pre_research_next_mve_plan.csv", index=False, encoding="utf-8-sig")
    comparison.to_csv(out_dir / "v9_pre_research_prior_strategy_comparison.csv", index=False, encoding="utf-8-sig")
    write_json({"formal_v9_recommended_now": False, "next_recommended_task": "MVE 1 - longer-history data audit", "requires_user_approval": True}, out_dir / "v9_pre_research_decision.json")

    zip_path = OUTPUT_ROOT / f"us_stock_selection_quant_lab_v9_pre_research_universe_stock_selection_rebuild_{timestamp}.zip"
    docs = write_docs(timestamp, out_dir, zip_path, evidence, boundary, universe, data_req, model, validation, checklist, mve)
    update_next_steps(out_dir, zip_path)
    write_run_summary(out_dir, zip_path)
    write_reports_workbook(
        out_dir,
        timestamp,
        {
            "evidence_index": evidence,
            "boundary_review": boundary,
            "universe_design": universe,
            "data_requirements": data_req,
            "model_design": model,
            "validation_framework": validation,
            "go_no_go_checklist": checklist,
            "next_mve_plan": mve,
            "prior_strategy_comparison": comparison,
        },
    )
    package(out_dir, docs, zip_path)
    sync_index = sync_meistock(timestamp, out_dir, zip_path, docs)
    sync_index.to_csv(out_dir / "v9_pre_research_meistock_sync_index.csv", index=False, encoding="utf-8-sig")
    package(out_dir, docs, zip_path)
    if MEISTOCK_ROOT.exists() and zip_path.exists():
        shutil.copy2(zip_path, MEISTOCK_ROOT / "07_附件索引" / zip_path.name)
    logger.info("Packaged v9 pre-research zip: %s", zip_path)


if __name__ == "__main__":
    main()
