"""Run formal v9 with canonical replay engine.

Explicitly approved scope: execute formal v9 only.  This script does not enter
v10, does not expand Nasdaq100/S&P500/full-market, does not trade, and does
not commit or push.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection.chatgpt_bridge import publish_for_chatgpt
from quant_lab.us_stock_selection.formal_v9_reporting import (
    build_formal_v9_excel,
    build_formal_v9_report,
    package_formal_v9_run,
)
from quant_lab.us_stock_selection.formal_v9_runner import (
    DEFAULT_V9_1_FEATURE_CACHE_DIR,
    DEFAULT_V9_1_PROVIDER_URI,
    DEFAULT_V9_1_RUN_DIR,
    DEFAULT_V9_1_SCORE_AUDIT_PATH,
    DEFAULT_V9_1_ELIGIBILITY_PATH,
)
from quant_lab.us_stock_selection.formal_v9_runner import run_formal_v9
from quant_lab.us_stock_selection.utils import ensure_dir, make_logger, save_json, save_text


OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
AGENT_LOOP_DIR = PROJECT_ROOT / "scripts" / "agent_loop"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run formal v9; no v10, no Nasdaq100/S&P500, no trading.")
    parser.add_argument("--timestamp", default="", help="Optional YYYYMMDD_HHMMSS timestamp.")
    parser.add_argument("--provider-uri", default=str(DEFAULT_V9_1_PROVIDER_URI))
    parser.add_argument("--v9-1-run-dir", default=str(DEFAULT_V9_1_RUN_DIR))
    parser.add_argument("--feature-cache-dir", default=str(DEFAULT_V9_1_FEATURE_CACHE_DIR))
    parser.add_argument("--score-audit-path", default=str(DEFAULT_V9_1_SCORE_AUDIT_PATH))
    parser.add_argument("--eligibility-path", default=str(DEFAULT_V9_1_ELIGIBILITY_PATH))
    parser.add_argument("--v8-1-run-dir", default=str(OUTPUT_ROOT / "run_20260502_210856"))
    parser.add_argument("--v8-2-run-dir", default=str(OUTPUT_ROOT / "run_20260502_220641"))
    parser.add_argument("--skip-bridge", action="store_true")
    parser.add_argument("--skip-github-issue", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_ROOT / f"formal_v9_{timestamp}"
    if run_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing formal v9 directory: {run_dir}")

    logs_dir = ensure_dir(run_dir / "logs")
    reports_dir = ensure_dir(run_dir / "reports")
    logger = make_logger(logs_dir / "run.log", level="INFO")
    logger.info("Starting formal v9.")
    save_text(
        "\n".join(
            [
                "# Formal v9 scope",
                "",
                "Explicit approval: execute formal v9 only.",
                "No Nasdaq100/S&P500/full-market expansion.",
                "No v10 entry.",
                "No model/strategy search, no parameter retuning, no broker API, no real trading.",
                f"Formal price source is the v9.1 local Qlib provider bin store: {args.provider_uri}.",
                f"Formal Alpha360 cache: {args.feature_cache_dir}.",
                f"Formal LGBModel score provenance: {args.score_audit_path}.",
                "Replay engine: canonical_replay_engine.",
                "",
            ]
        ),
        run_dir / "SCOPE.md",
    )

    result = run_formal_v9(
        run_dir,
        provider_uri=args.provider_uri,
        v8_1_run_dir=args.v8_1_run_dir,
        v8_2_run_dir=args.v8_2_run_dir,
        v9_1_run_dir=args.v9_1_run_dir,
        feature_cache_dir=args.feature_cache_dir,
        score_audit_path=args.score_audit_path,
        eligibility_path=args.eligibility_path,
    )
    build_formal_v9_report(reports_dir / "formal_v9_report.md", result)
    build_formal_v9_excel(reports_dir / "formal_v9_summary.xlsx", result)
    write_summaries(run_dir, result, zip_path="")

    zip_path = package_formal_v9_run(run_dir, timestamp)
    verdict = dict(result["verdict"])
    verdict["zip_path"] = str(zip_path)
    verdict["run_dir"] = str(run_dir)
    result["verdict"] = verdict
    save_json(verdict, run_dir / "formal_v9" / "formal_v9_verdict.json")
    save_json(verdict, run_dir / "audit_summary.json")
    write_summaries(run_dir, result, zip_path=str(zip_path))
    build_formal_v9_report(reports_dir / "formal_v9_report.md", result, zip_path=zip_path)
    build_formal_v9_excel(reports_dir / "formal_v9_summary.xlsx", result)
    zip_path = package_formal_v9_run(run_dir, timestamp)
    verdict["zip_path"] = str(zip_path)
    save_json(verdict, run_dir / "formal_v9" / "formal_v9_verdict.json")
    save_json(verdict, run_dir / "audit_summary.json")
    logger.info(f"Packaged formal v9 zip: {zip_path}")

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

    pool = row(result["metrics"], "formal_pool_a_reproduction")
    main = row(result["metrics"], "formal_pool_a_plus_small_growth")
    small = row(result["metrics"], "formal_small_growth_only")
    exhv = row(result["metrics"], "formal_pool_a_plus_small_growth_ex_high_vol")
    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "zip_path": str(zip_path),
                "classification": verdict.get("classification"),
                "pool_a_reproduction_pass": verdict.get("pool_a_reproduction_pass"),
                "pool_a_reproduction": compact_metrics(pool),
                "pool_a_plus_small_growth": compact_metrics(main),
                "small_growth_only": compact_metrics(small),
                "ex_high_vol": compact_metrics(exhv),
                "effective_universe_count": verdict.get("effective_universe_count"),
                "excluded_ticker_count": verdict.get("excluded_ticker_count"),
                "formal_v9_gate_pass": verdict.get("formal_v9_gate_pass"),
                "single_year_share": verdict.get("single_year_share"),
                "top_ticker_share": verdict.get("top_ticker_share"),
                "depends_on_coin_mstr_pltr": verdict.get("depends_on_coin_mstr_pltr"),
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


def write_summaries(run_dir: Path, result: dict[str, Any], zip_path: str) -> None:
    verdict = dict(result["verdict"])
    pool = row(result["metrics"], "formal_pool_a_reproduction")
    main = row(result["metrics"], "formal_pool_a_plus_small_growth")
    small = row(result["metrics"], "formal_small_growth_only")
    exhv = row(result["metrics"], "formal_pool_a_plus_small_growth_ex_high_vol")
    text = f"""# RUN_SUMMARY

本轮目标：执行 formal v9；仅小幅科技成长池，不扩 Nasdaq100/S&P500，不进入 v10，不交易化。

新 run 目录：`{run_dir}`
zip 路径：`{zip_path}`

核心结论：
- classification: `{verdict.get("classification")}`
- Pool A reproduction pass: `{verdict.get("pool_a_reproduction_pass")}`
- Formal v9 gate pass: `{verdict.get("formal_v9_gate_pass")}`
- Performance gate pass: `{verdict.get("formal_v9_performance_gate_pass")}`
- Effective universe count: `{verdict.get("effective_universe_count")}`
- Effective small-growth count: `{verdict.get("effective_small_growth_count")}`
- Effective new growth count: `{verdict.get("effective_new_growth_count")}`
- Excluded ticker count: `{verdict.get("excluded_ticker_count")}`
- Allow enter v10: `{verdict.get("allow_enter_v10")}`

Pool A reproduction CAGR/Calmar/MaxDD：`{pool.get("cagr")}` / `{pool.get("calmar")}` / `{pool.get("max_drawdown")}`
Pool A + growth CAGR/Calmar/MaxDD：`{main.get("cagr")}` / `{main.get("calmar")}` / `{main.get("max_drawdown")}`
Small growth only CAGR/Calmar/MaxDD：`{small.get("cagr")}` / `{small.get("calmar")}` / `{small.get("max_drawdown")}`
Ex-high-vol CAGR/Calmar/MaxDD：`{exhv.get("cagr")}` / `{exhv.get("calmar")}` / `{exhv.get("max_drawdown")}`

原因：{verdict.get("reason")}

本轮没有扩 Nasdaq100/S&P500，没有进入 v10，没有下载行情，没有连接券商，没有自动 commit/push。
"""
    save_text(text, run_dir / "RUN_SUMMARY.md")
    save_text(text, PROJECT_ROOT / "RUN_SUMMARY.md")

    next_steps = f"""# NEXT_STEPS

当前状态：`{verdict.get("classification")}`。

下一步只允许：
- 审阅 formal v9 结果和 eligibility 缺口。
- 若要继续 v9，先补 canonical provider/score evidence 或缩小为当前有证据 universe。

禁止：
- 不进入 v10。
- 不扩 Nasdaq100/S&P500/全市场。
- 不交易化，不连接券商，不下单。
- 不复用旧 v9 original metrics 或 unified replay 作为正式结果。
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
        "mode": "local_formal_v9_research_only",
        "notes": "Explicit formal v9 approval only. No broker, no order, no credential access, no push, no external market-data download, no v10.",
    }
    summary = {
        "run_dir": str(run_dir),
        "zip_path": str(zip_path),
        "classification": verdict.get("classification"),
        "pool_a_reproduction_pass": verdict.get("pool_a_reproduction_pass"),
        "pool_a_plus_growth_cagr": verdict.get("pool_a_plus_growth_cagr"),
        "pool_a_plus_growth_calmar": verdict.get("pool_a_plus_growth_calmar"),
        "formal_v9_gate_pass": verdict.get("formal_v9_gate_pass"),
        "effective_universe_count": verdict.get("effective_universe_count"),
        "effective_new_growth_count": verdict.get("effective_new_growth_count"),
        "excluded_ticker_count": verdict.get("excluded_ticker_count"),
        "allow_enter_v10": verdict.get("allow_enter_v10"),
        "reason": verdict.get("reason"),
    }
    body = "\n\n".join(
        [
            "# Formal v9 Summary",
            section("FORMAL_V9_SUMMARY", f"```json\n{json.dumps(summary, ensure_ascii=False, indent=2)}\n```"),
            section("FORMAL_V9_GATE_RESULT", f"```json\n{json.dumps(result.get('gate_result', {}), ensure_ascii=False, indent=2, default=str)}\n```"),
            section("FORMAL_V9_CLASSIFICATION", str(verdict.get("classification", ""))),
            section("NEXT_ALLOWED_ACTION", str(verdict.get("next_allowed_action", ""))),
            section("SAFETY_GATE_RESULT", f"```json\n{json.dumps(safety, ensure_ascii=False, indent=2)}\n```"),
        ]
    )
    return post_issue_comment(config, body)


def row(df, universe_name: str) -> dict[str, Any]:
    if df is None or df.empty:
        return {}
    rows = df.loc[df["universe_name"].astype(str).eq(universe_name)]
    return rows.iloc[0].to_dict() if not rows.empty else {}


def compact_metrics(data: dict[str, Any]) -> dict[str, Any]:
    return {k: data.get(k) for k in ["cagr", "calmar", "max_drawdown", "cost50_t1_cagr", "cost50_t1_calmar", "single_year_share", "top_ticker", "top_ticker_share"]}


def section(name: str, content: str) -> str:
    return f"<!-- codex-bridge:section {name} -->\n## {name}\n\n{content.rstrip()}\n<!-- /codex-bridge:section {name} -->"


if __name__ == "__main__":
    main()
