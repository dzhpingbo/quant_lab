"""Run v9.1 small-growth canonical provider and score provenance onboarding.

Scope: only the 29 formal-v9 excluded small-growth tickers.  This script may
download public yfinance OHLCV for missing local tickers, but it does not touch
brokers, credentials, trading APIs, v10, Nasdaq100/S&P500, commits, or pushes.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection.chatgpt_bridge import publish_for_chatgpt
from quant_lab.us_stock_selection.v9_1_growth_data_onboarding import (
    NEW_PROVIDER_URI,
    V9_1_GROWTH_TICKERS,
    build_extended_provider,
    pool_a_tickers_from_v82,
    run_data_inventory,
    run_dynamic_eligibility,
    run_pool_a_reproduction_preflight,
)
from quant_lab.us_stock_selection.v9_1_reporting import build_v9_1_excel, build_v9_1_report, package_v9_1_run
from quant_lab.us_stock_selection.v9_1_score_provenance_builder import build_v9_1_feature_cache, build_v9_1_score_provenance
from quant_lab.us_stock_selection.utils import ensure_dir, make_logger, save_dataframe, save_json, save_text


OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
AGENT_LOOP_DIR = PROJECT_ROOT / "scripts" / "agent_loop"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run v9.1 small-growth data onboarding; no v10, no trading.")
    parser.add_argument("--timestamp", default="", help="Optional YYYYMMDD_HHMMSS timestamp.")
    parser.add_argument("--provider-uri", default=str(NEW_PROVIDER_URI), help="New v9.1 provider URI.")
    parser.add_argument("--no-yfinance", action="store_true", help="Disable allowed public yfinance fallback.")
    parser.add_argument("--skip-bridge", action="store_true")
    parser.add_argument("--skip-github-issue", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_ROOT / f"v9_1_growth_data_onboarding_{timestamp}"
    if run_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing v9.1 directory: {run_dir}")
    logs_dir = ensure_dir(run_dir / "logs")
    reports_dir = ensure_dir(run_dir / "reports")
    logger = make_logger(logs_dir / "run.log", level="INFO")
    logger.info("Starting v9.1 growth data onboarding.")
    save_scope(run_dir, allow_yfinance=not args.no_yfinance)

    pool_tickers = pool_a_tickers_from_v82()
    inventory, loaded = run_data_inventory(
        run_dir,
        tickers=V9_1_GROWTH_TICKERS,
        allow_yfinance_download=not args.no_yfinance,
        logger=logger,
    )
    provider = build_extended_provider(
        run_dir / "v9_1_provider_build",
        loaded=loaded,
        inventory=inventory,
        pool_tickers=pool_tickers,
        new_provider_uri=Path(args.provider_uri),
        logger=logger,
    )
    eligibility = run_dynamic_eligibility(run_dir, provider.provider_uri, tickers=V9_1_GROWTH_TICKERS)

    feature_result: dict[str, Any] = {"status": {"status": "skipped_provider_failed"}}
    score_result: dict[str, Any] = {"status": {"status": "skipped_feature_failed"}, "fit_log": pd.DataFrame(), "scores": pd.DataFrame(), "audit": pd.DataFrame()}
    if provider.provider_success:
        feature_result = build_v9_1_feature_cache(run_dir / "v9_1_feature_cache", provider.provider_uri, logger=logger)
    feature_success = feature_result.get("status", {}).get("status") == "completed"
    if provider.provider_success and feature_success:
        universe = sorted(set(pool_tickers) | set(V9_1_GROWTH_TICKERS) | {"SPY", "QQQ", "QLD", "TQQQ", "SHY"})
        score_result = build_v9_1_score_provenance(
            run_dir / "v9_1_score_provenance",
            cache_dir=run_dir / "v9_1_feature_cache",
            provider_uri=provider.provider_uri,
            universe_tickers=universe,
            growth_tickers=V9_1_GROWTH_TICKERS,
            logger=logger,
        )

    preflight_dir = ensure_dir(run_dir / "v9_1_preflight_replay")
    pool_check = pd.DataFrame()
    pool_aligned = False
    if provider.provider_success:
        try:
            pool_check, pool_aligned = run_pool_a_reproduction_preflight(preflight_dir, provider.provider_uri)
        except Exception as exc:
            pool_check = pd.DataFrame([{"metric": "pool_a_reproduction_error", "pass_check": False, "error": str(exc)}])
            save_dataframe(pool_check, preflight_dir / "preflight_pool_a_reproduction_check.csv")
    coverage, by_month, topk = build_preflight_tables(
        preflight_dir=preflight_dir,
        inventory=inventory,
        eligibility=eligibility,
        scores=score_result.get("scores", pd.DataFrame()),
        audit=score_result.get("audit", pd.DataFrame()),
    )

    verdict = build_verdict(
        run_dir=run_dir,
        provider_success=provider.provider_success,
        feature_status=feature_result.get("status", {}),
        score_status=score_result.get("status", {}),
        inventory=inventory,
        eligibility=eligibility,
        pool_aligned=pool_aligned,
        coverage=coverage,
    )
    result = {
        "verdict": verdict,
        "inventory": inventory,
        "eligibility": eligibility,
        "provider_status": {
            "provider_uri": str(provider.provider_uri),
            "provider_success": provider.provider_success,
            "added_tickers": provider.added_tickers,
            "failed_tickers": provider.failed_tickers,
            "health": provider.health,
        },
        "feature_status": feature_result.get("status", {}),
        "score_status": score_result.get("status", {}),
        "pool_a_reproduction_check": pool_check,
        "candidate_coverage": coverage,
        "score_availability_by_month": by_month,
        "topk_candidate_overlap": topk,
        "fit_log": score_result.get("fit_log", pd.DataFrame()),
        "score_audit": score_result.get("audit", pd.DataFrame()),
    }
    save_json(verdict, run_dir / "v9_1_verdict.json")
    save_json(verdict, run_dir / "audit_summary.json")
    build_v9_1_report(reports_dir / "v9_1_growth_data_onboarding_report.md", result)
    build_v9_1_excel(reports_dir / "v9_1_growth_data_onboarding_summary.xlsx", result)
    write_summaries(run_dir, result, zip_path="")

    zip_path = package_v9_1_run(run_dir, timestamp)
    verdict["zip_path"] = str(zip_path)
    verdict["run_dir"] = str(run_dir)
    result["verdict"] = verdict
    save_json(verdict, run_dir / "v9_1_verdict.json")
    save_json(verdict, run_dir / "audit_summary.json")
    write_summaries(run_dir, result, zip_path=str(zip_path))
    build_v9_1_report(reports_dir / "v9_1_growth_data_onboarding_report.md", result, zip_path=zip_path)
    build_v9_1_excel(reports_dir / "v9_1_growth_data_onboarding_summary.xlsx", result)
    zip_path = package_v9_1_run(run_dir, timestamp)
    verdict["zip_path"] = str(zip_path)
    save_json(verdict, run_dir / "v9_1_verdict.json")
    save_json(verdict, run_dir / "audit_summary.json")

    local_manifest: dict[str, Any] = {}
    if not args.skip_bridge:
        try:
            local_manifest = publish_for_chatgpt(run_dir=run_dir, max_csv_mb=5.0, include_xlsx=False, git_push=False)
            logger.info(f"Published local ChatGPT bridge packet: {local_manifest.get('review_packet', '')}")
        except Exception as exc:
            logger.warning(f"Local ChatGPT bridge publish failed: {exc}")

    github_result: dict[str, Any] = {}
    if not args.skip_github_issue:
        try:
            github_result = publish_github_issue_summary(verdict, result, zip_path, run_dir)
            logger.info(f"Published GitHub Issue summary: {github_result.get('issue_url', '')}")
        except Exception as exc:
            github_result = {"posted": False, "error": str(exc)}
            logger.warning(f"GitHub Issue summary publish failed: {exc}")

    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "zip_path": str(zip_path),
                "classification": verdict.get("classification"),
                "provider_success": verdict.get("provider_success"),
                "feature_cache_success": verdict.get("feature_cache_success"),
                "score_provenance_success": verdict.get("score_provenance_success"),
                "incremental_data_ready_count": verdict.get("incremental_data_ready_count"),
                "incremental_eligible_growth_count": verdict.get("incremental_eligible_growth_count"),
                "growth_topk_candidate_count": verdict.get("growth_topk_candidate_count"),
                "pool_a_reproduction_aligned": verdict.get("pool_a_reproduction_aligned"),
                "allow_formal_v9_rerun": verdict.get("allow_formal_v9_rerun"),
                "allow_enter_v10": verdict.get("allow_enter_v10"),
                "requires_human_review": verdict.get("requires_human_review"),
                "local_bridge_run": local_manifest.get("run_id", "") if isinstance(local_manifest, dict) else "",
                "github_issue_posted": bool(github_result and not github_result.get("error")),
                "github_issue": github_result.get("issue_url", "") if isinstance(github_result, dict) else "",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def build_preflight_tables(
    preflight_dir: Path,
    inventory: pd.DataFrame,
    eligibility: pd.DataFrame,
    scores: pd.DataFrame,
    audit: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    inv = inventory.set_index("ticker").to_dict("index") if not inventory.empty else {}
    elig = eligibility.set_index("ticker").to_dict("index") if not eligibility.empty else {}
    rows = []
    for ticker in V9_1_GROWTH_TICKERS:
        score_rows = scores.loc[scores["ticker"].astype(str).eq(ticker)] if scores is not None and not scores.empty and "ticker" in scores else pd.DataFrame()
        audit_rows = audit.loc[audit["ticker"].astype(str).eq(ticker)] if audit is not None and not audit.empty and "ticker" in audit else pd.DataFrame()
        topk_count = int(audit_rows["selected_top5_candidate"].astype(bool).sum()) if not audit_rows.empty and "selected_top5_candidate" in audit_rows else 0
        rows.append(
            {
                "ticker": ticker,
                "data_quality_status": inv.get(ticker, {}).get("data_quality_status", ""),
                "date_start": inv.get(ticker, {}).get("date_start", ""),
                "date_end": inv.get(ticker, {}).get("date_end", ""),
                "eligible_for_formal_v9": bool(elig.get(ticker, {}).get("eligible_for_formal_v9", False)),
                "first_eligible_rebalance_date": elig.get(ticker, {}).get("first_eligible_rebalance_date", ""),
                "eligible_month_count": int(float(elig.get(ticker, {}).get("eligible_month_count", 0) or 0)),
                "score_month_count": int(score_rows["rebalance_date"].nunique()) if not score_rows.empty else 0,
                "score_row_count": int(len(score_rows)),
                "top5_candidate_count": topk_count,
                "entered_topk_candidate": bool(topk_count > 0),
                "observation_only": not bool(elig.get(ticker, {}).get("eligible_for_formal_v9", False)),
            }
        )
    coverage = pd.DataFrame(rows)
    save_dataframe(coverage, preflight_dir / "preflight_pool_a_plus_growth_candidate_coverage.csv")

    if scores is not None and not scores.empty:
        scores = scores.copy()
        scores["is_growth"] = scores["ticker"].astype(str).isin(V9_1_GROWTH_TICKERS)
        by_month = (
            scores.groupby("rebalance_date", as_index=False)
            .agg(
                total_score_count=("ticker", "nunique"),
                growth_score_count=("is_growth", "sum"),
                growth_top5_count=("selected_top5_candidate", lambda s: int((scores.loc[s.index, "is_growth"] & s.astype(bool)).sum())),
            )
            .sort_values("rebalance_date")
        )
    else:
        by_month = pd.DataFrame(columns=["rebalance_date", "total_score_count", "growth_score_count", "growth_top5_count"])
    save_dataframe(by_month, preflight_dir / "preflight_score_availability_by_month.csv")

    if audit is not None and not audit.empty:
        top_rows = audit.loc[audit["selected_top5_candidate"].astype(bool)].copy()
        top_rows["is_growth"] = top_rows["ticker"].astype(str).isin(V9_1_GROWTH_TICKERS)
        topk = (
            top_rows.groupby("rebalance_date", as_index=False)
            .agg(
                top5_tickers=("ticker", lambda s: ",".join(s.astype(str).tolist())),
                growth_top5_tickers=("ticker", lambda s: ",".join([x for x in s.astype(str).tolist() if x in V9_1_GROWTH_TICKERS])),
                growth_top5_count=("is_growth", "sum"),
            )
            .sort_values("rebalance_date")
        )
    else:
        topk = pd.DataFrame(columns=["rebalance_date", "top5_tickers", "growth_top5_tickers", "growth_top5_count"])
    save_dataframe(topk, preflight_dir / "preflight_topk_candidate_overlap.csv")
    return coverage, by_month, topk


def build_verdict(
    *,
    run_dir: Path,
    provider_success: bool,
    feature_status: dict[str, Any],
    score_status: dict[str, Any],
    inventory: pd.DataFrame,
    eligibility: pd.DataFrame,
    pool_aligned: bool,
    coverage: pd.DataFrame,
) -> dict[str, Any]:
    feature_success = feature_status.get("status") == "completed"
    score_success = score_status.get("status") == "completed"
    data_ready_count = int(inventory["data_quality_status"].astype(str).eq("ready_for_provider").sum()) if not inventory.empty else 0
    eligible_count = int(eligibility["eligible_for_formal_v9"].astype(bool).sum()) if not eligibility.empty else 0
    topk_count = int(coverage["entered_topk_candidate"].astype(bool).sum()) if not coverage.empty else 0
    if not provider_success:
        classification = "v9_1_failed_provider_build"
    elif not feature_success or not score_success:
        classification = "v9_1_failed_score_provenance"
    elif eligible_count == 0:
        classification = "v9_1_failed_no_incremental_eligible_growth"
    elif provider_success and feature_success and score_success and eligible_count >= 5 and pool_aligned:
        classification = "v9_1_ready_for_formal_v9_rerun"
    elif eligible_count > 0:
        classification = "v9_1_partial_data_ready_needs_review"
    else:
        classification = "v9_1_needs_human_review"
    allow_rerun = bool(classification == "v9_1_ready_for_formal_v9_rerun")
    return {
        "classification": classification,
        "run_dir": str(run_dir),
        "provider_success": bool(provider_success),
        "feature_cache_success": bool(feature_success),
        "score_provenance_success": bool(score_success),
        "incremental_data_ready_count": data_ready_count,
        "incremental_eligible_growth_count": eligible_count,
        "growth_topk_candidate_count": topk_count,
        "pool_a_reproduction_aligned": bool(pool_aligned),
        "allow_formal_v9_rerun": allow_rerun,
        "allow_enter_v10": False,
        "allow_trade_execution": False,
        "requires_human_review": not allow_rerun,
        "next_allowed_action": "Run formal v9 rerun with v9.1 provider only after human review." if allow_rerun else "Review v9.1 data/score provenance blockers before any formal v9 rerun.",
        "reason": verdict_reason(classification, eligible_count, topk_count, provider_success, feature_success, score_success, pool_aligned),
    }


def verdict_reason(classification: str, eligible_count: int, topk_count: int, provider: bool, feature: bool, score: bool, pool: bool) -> str:
    if classification == "v9_1_ready_for_formal_v9_rerun":
        return f"Provider, Alpha360 cache, LGBModel scores, and Pool A reproduction passed; {eligible_count} incremental growth tickers are eligible and {topk_count} entered TopK candidates."
    if not provider:
        return "New canonical provider build failed."
    if not feature or not score:
        return "Provider exists, but Alpha360 feature cache or LGBModel score provenance failed."
    if eligible_count == 0:
        return "No incremental small-growth ticker satisfied dynamic eligibility after onboarding."
    if not pool:
        return "Incremental data exists, but Pool A reproduction did not remain aligned under the v9.1 provider."
    return f"Partial readiness: {eligible_count} eligible growth tickers and {topk_count} TopK candidate entrants require human review."


def save_scope(run_dir: Path, allow_yfinance: bool) -> None:
    save_text(
        "\n".join(
            [
                "# v9.1 Scope",
                "",
                "Allowed: onboard only the 29 formal-v9 excluded small-growth tickers.",
                f"Public yfinance fallback enabled: `{allow_yfinance}`.",
                "No Nasdaq100/S&P500/full-market expansion.",
                "No v10 entry.",
                "No retuning, no broker API, no real trading, no credentials.",
                "No automatic commit or push.",
                "",
            ]
        ),
        run_dir / "SCOPE.md",
    )


def write_summaries(run_dir: Path, result: dict[str, Any], zip_path: str) -> None:
    verdict = result["verdict"]
    text = f"""# RUN_SUMMARY

Stage: v9.1 small-growth canonical provider and frozen score provenance onboarding.

Run directory: `{run_dir}`
Zip path: `{zip_path}`

Conclusion:
- classification: `{verdict.get("classification")}`
- new provider success: `{verdict.get("provider_success")}`
- Alpha360 cache success: `{verdict.get("feature_cache_success")}`
- LGBModel score provenance success: `{verdict.get("score_provenance_success")}`
- incremental data ready count: `{verdict.get("incremental_data_ready_count")}`
- incremental eligible growth count: `{verdict.get("incremental_eligible_growth_count")}`
- growth TopK candidate count: `{verdict.get("growth_topk_candidate_count")}`
- Pool A reproduction aligned: `{verdict.get("pool_a_reproduction_aligned")}`
- allow formal v9 rerun: `{verdict.get("allow_formal_v9_rerun")}`
- allow enter v10: `False`

Reason: {verdict.get("reason")}

No Nasdaq100/S&P500/full-market expansion, no v10, no trading, no broker/API/credential access, no automatic commit/push.
"""
    save_text(text, run_dir / "RUN_SUMMARY.md")
    save_text(text, PROJECT_ROOT / "RUN_SUMMARY.md")
    next_steps = f"""# NEXT_STEPS

Current classification: `{verdict.get("classification")}`.

Allowed next action:
- `{verdict.get("next_allowed_action")}`

Still forbidden:
- Do not enter v10.
- Do not expand Nasdaq100/S&P500/full market.
- Do not trade, connect brokers, place orders, or access credentials.
- Do not use observation-only tickers in formal TopK.
"""
    save_text(next_steps, run_dir / "NEXT_STEPS.md")
    save_text(next_steps, PROJECT_ROOT / "NEXT_STEPS.md")


def publish_github_issue_summary(verdict: dict[str, Any], result: dict[str, Any], zip_path: Path, run_dir: Path) -> dict[str, Any]:
    if str(AGENT_LOOP_DIR) not in sys.path:
        sys.path.insert(0, str(AGENT_LOOP_DIR))
    from bridge_io import bridge_mode, initialize_bridge, load_config
    from github_bridge import post_issue_comment

    config_path = PROJECT_ROOT / "scripts" / "agent_loop" / "loop_config_auth.yaml"
    config = load_config(config_path)
    if bridge_mode(config) != "github_issue":
        return {"posted": False, "reason": f"bridge.mode={bridge_mode(config)}"}
    initialize_bridge(config)
    safety = {
        "blocked": False,
        "violations": [],
        "mode": "v9_1_data_onboarding_public_ohlcv_only",
        "notes": "No broker, no order, no credential access, no push, no v10. yfinance limited to the 29 formal-v9 excluded tickers only.",
    }
    summary = {
        "run_dir": str(run_dir),
        "zip_path": str(zip_path),
        "classification": verdict.get("classification"),
        "provider_success": verdict.get("provider_success"),
        "feature_cache_success": verdict.get("feature_cache_success"),
        "score_provenance_success": verdict.get("score_provenance_success"),
        "incremental_data_ready_count": verdict.get("incremental_data_ready_count"),
        "incremental_eligible_growth_count": verdict.get("incremental_eligible_growth_count"),
        "growth_topk_candidate_count": verdict.get("growth_topk_candidate_count"),
        "pool_a_reproduction_aligned": verdict.get("pool_a_reproduction_aligned"),
        "allow_formal_v9_rerun": verdict.get("allow_formal_v9_rerun"),
        "allow_enter_v10": verdict.get("allow_enter_v10"),
        "reason": verdict.get("reason"),
    }
    body = "\n\n".join(
        [
            "# v9.1 Data Onboarding Summary",
            section("V9_1_DATA_ONBOARDING_SUMMARY", f"```json\n{json.dumps(summary, ensure_ascii=False, indent=2)}\n```"),
            section("V9_1_PROVIDER_STATUS", f"```json\n{json.dumps(result.get('provider_status', {}), ensure_ascii=False, indent=2, default=str)}\n```"),
            section("V9_1_SCORE_PROVENANCE_STATUS", f"```json\n{json.dumps(result.get('score_status', {}), ensure_ascii=False, indent=2, default=str)}\n```"),
            section("V9_1_CLASSIFICATION", str(verdict.get("classification", ""))),
            section("NEXT_ALLOWED_ACTION", str(verdict.get("next_allowed_action", ""))),
            section("SAFETY_GATE_RESULT", f"```json\n{json.dumps(safety, ensure_ascii=False, indent=2)}\n```"),
        ]
    )
    return post_issue_comment(config, body)


def section(name: str, content: str) -> str:
    return f"<!-- codex-bridge:section {name} -->\n## {name}\n\n{content.rstrip()}\n<!-- /codex-bridge:section {name} -->"


if __name__ == "__main__":
    main()
