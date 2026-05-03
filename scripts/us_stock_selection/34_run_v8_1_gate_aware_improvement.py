"""Run v8.1 gate-aware evolution cycles.

Cycle 01 is score/gate-layer only and never changes trading results.
Cycle 02 is a small sample replay using existing v8 holdings plus simple
high-beta soft-cap overlays. It does not refit models, run 31b, enter v9, or
expand the universe.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection.local_qlib_provider_builder import default_local_provider_uri
from quant_lab.us_stock_selection.qlib_workflow_runner import load_close_from_provider
from quant_lab.us_stock_selection.v8_1_gate_aware import (
    apply_high_beta_softcap,
    build_weights_from_holdings,
    evaluate_replay_variant,
    score_weight_grid,
)
from quant_lab.us_stock_selection.v8_1_gate_metrics import concentration_penalty_score, gate_results_from_metrics
from quant_lab.us_stock_selection.v8_1_reporting import package_cycle, write_cycle_report, write_json


DEFAULT_RUN_DIR = PROJECT_ROOT / "outputs" / "us_stock_selection" / "run_20260426_095958"
DEFAULT_DIAGNOSTIC_DIR = PROJECT_ROOT / "outputs" / "us_stock_selection" / "v8_single_year_concentration_20260427_233246"
DEFAULT_CALIBRATION_DIR = PROJECT_ROOT / "outputs" / "us_stock_selection" / "v8_gate_calibration_review_20260428_111439"
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
DOCS_DIR = PROJECT_ROOT / "docs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run v8.1 gate-aware evolution cycles.")
    parser.add_argument("--cycle", choices=["01", "02", "all"], default="01")
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--diagnostic-dir", type=Path, default=DEFAULT_DIAGNOSTIC_DIR)
    parser.add_argument("--calibration-dir", type=Path, default=DEFAULT_CALIBRATION_DIR)
    parser.add_argument("--provider-uri", type=Path, default=default_local_provider_uri())
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--timestamp", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def setup_logger(out_dir: Path) -> logging.Logger:
    logs_dir = out_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("v8_1_evolution")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh = logging.FileHandler(logs_dir / "run.log", encoding="utf-8")
    fh.setFormatter(formatter)
    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def read_csv(path: Path, required: bool = True) -> pd.DataFrame:
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return pd.DataFrame()
    return pd.read_csv(path)


def baseline_from_v8(run_dir: Path) -> dict[str, Any]:
    verdict = read_json(run_dir / "v8_verdict.json")
    metrics = read_csv(run_dir / "v8_paper_trading" / "paper_trading_metrics.csv")
    row = metrics.iloc[0].to_dict() if not metrics.empty else {}
    return {
        "classification": verdict.get("classification"),
        "allow_enter_v9": verdict.get("allow_enter_v9"),
        "cagr": row.get("cagr", verdict.get("paper_cagr")),
        "calmar": row.get("calmar", verdict.get("paper_calmar")),
        "max_drawdown": row.get("max_drawdown"),
        "annual_turnover": row.get("annual_turnover"),
        "cost50_cagr": verdict.get("cost50_cagr"),
        "cost50_calmar": None,
    }


def ensure_inputs(args: argparse.Namespace) -> list[str]:
    required = [
        args.run_dir / "v8_verdict.json",
        args.run_dir / "v8_paper_trading" / "paper_trading_metrics.csv",
        args.diagnostic_dir / "annual_contribution.csv",
        args.diagnostic_dir / "top_month_removed_metrics.csv",
        args.calibration_dir / "v8_concentration_metric_snapshot.json",
        args.calibration_dir / "v8_concentration_gate_comparison.csv",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing required v8.1 input(s): " + "; ".join(missing))
    return [str(p) for p in required]


def write_best_index(path: Path, data: dict[str, Any]) -> Path:
    return write_json(path, data)


def run_cycle01(args: argparse.Namespace, out_dir: Path, logger: logging.Logger, timestamp: str) -> dict[str, Any]:
    logger.info("Running cycle 01 score/gate-layer diagnostic.")
    baseline = baseline_from_v8(args.run_dir)
    metric_snapshot = read_json(args.calibration_dir / "v8_concentration_metric_snapshot.json")
    if "concentration_penalty_score" not in metric_snapshot:
        penalty_score, penalty_parts = concentration_penalty_score(metric_snapshot)
        metric_snapshot["concentration_penalty_score"] = penalty_score
        metric_snapshot.update(penalty_parts)
    v8_verdict = read_json(args.run_dir / "v8_verdict.json")
    merged = {**metric_snapshot, **v8_verdict, "paper_cagr": baseline.get("cagr"), "paper_calmar": baseline.get("calmar")}
    score_grid = score_weight_grid(merged)
    gate_results = gate_results_from_metrics(metric_snapshot)
    hard_failed = gate_results.loc[(gate_results["gate_layer"] == "hard") & (gate_results["pass_fail"] == "fail"), "gate_name"].tolist()
    verdict = {
        "cycle_id": "01",
        "cycle_type": "score_layer_only",
        "hypothesis": "A concentration penalty can be attached to ranking without changing the accepted v8 trading result.",
        "baseline_v8_verdict": baseline.get("classification"),
        "baseline_allow_enter_v9": baseline.get("allow_enter_v9"),
        "hard_gates_failed": hard_failed,
        "concentration_penalty_score": metric_snapshot.get("concentration_penalty_score"),
        "execution_stress_summary": "No new execution replay; inherited v8 execution stress and 50bps CAGR.",
        "accepted_candidate": False,
        "replace_best": False,
        "pause_triggered": False,
        "pause_reason": "",
        "final_cycle_verdict": "diagnostic_passed_score_layer_only",
    }
    cycle_metrics = score_grid.copy()
    cycle_metrics["baseline_cagr"] = baseline.get("cagr")
    cycle_metrics["baseline_calmar"] = baseline.get("calmar")
    cycle_metrics["delta_cagr"] = 0.0
    cycle_metrics["delta_calmar"] = 0.0
    cycle_metrics.to_csv(out_dir / "cycle_metrics.csv", index=False)
    gate_results.to_csv(out_dir / "gate_results.csv", index=False)
    write_json(out_dir / "cycle_verdict.json", verdict)
    best = {
        "best_candidate_id": "v8_baseline",
        "best_source": str(args.run_dir),
        "last_cycle_id": "01",
        "last_cycle_status": "diagnostic_only_not_replacing_best",
        "allow_enter_v9": False,
    }
    write_best_index(out_dir / "best_candidate_index.json", best)
    doc = DOCS_DIR / f"US_STOCK_SELECTION_V8_1_EVOLUTION_CYCLE_{timestamp}.md"
    local_doc = out_dir / f"US_STOCK_SELECTION_V8_1_EVOLUTION_CYCLE_{timestamp}.md"
    for path in [doc, local_doc]:
        write_cycle_report(
            path=path,
            cycle_id="01",
            objective="新增 v8.1 gate-aware score 层，基于既有 v8 输出计算 concentration_penalty_score 并模拟 penalty weight 对排名分数的影响。",
            changed_files=[
                "quant_lab/us_stock_selection/v8_1_gate_metrics.py",
                "quant_lab/us_stock_selection/v8_1_gate_aware.py",
                "quant_lab/us_stock_selection/v8_1_reporting.py",
                "scripts/us_stock_selection/34_run_v8_1_gate_aware_improvement.py",
            ],
            rerun_scope="否。cycle 01 不重跑策略、不训练模型、不改交易结果，只复算 gate/score。",
            inputs=ensure_inputs(args),
            output_dir=out_dir,
            baseline=baseline,
            cycle_metrics=cycle_metrics,
            gate_results=gate_results,
            verdict=verdict,
            next_plan="自动进入 cycle 02：在既有持仓基础上，对高 beta 暴露做 soft-cap 小样本 replay。",
        )
    zip_path = package_cycle(
        OUTPUT_ROOT / f"us_stock_selection_quant_lab_v8_1_cycle_{timestamp}.zip",
        [
            PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v8_1_gate_metrics.py",
            PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v8_1_gate_aware.py",
            PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v8_1_reporting.py",
            PROJECT_ROOT / "scripts" / "us_stock_selection" / "34_run_v8_1_gate_aware_improvement.py",
            out_dir,
            doc,
            PROJECT_ROOT / "NEXT_STEPS.md",
        ],
    )
    logger.info("Cycle 01 packaged: %s", zip_path)
    return {"verdict": verdict, "zip_path": str(zip_path), "doc": str(doc)}


def run_cycle02(args: argparse.Namespace, out_dir: Path, logger: logging.Logger, timestamp: str) -> dict[str, Any]:
    logger.info("Running cycle 02 sample replay with high-beta soft-cap overlays.")
    baseline = baseline_from_v8(args.run_dir)
    holdings = read_csv(args.run_dir / "v8_paper_trading" / "monthly_holdings.csv")
    rolling = read_csv(args.diagnostic_dir / "rolling_12m_metrics.csv")
    tickers = sorted(holdings["ticker"].astype(str).str.upper().unique().tolist())
    logger.info("Loading close panel for %s existing v8 tickers only.", len(tickers))
    close = load_close_from_provider(args.provider_uri, tickers=tickers, start="2024-01-01", end="2026-04-17")
    if close.empty:
        raise RuntimeError("Close panel is empty; cannot run cycle 02 sample replay.")
    weights = build_weights_from_holdings(close, holdings)
    variants = {
        "baseline_rebuilt": weights,
        "high_beta_softcap_15": apply_high_beta_softcap(weights, cap=0.15, max_other_weight=0.30),
        "high_beta_softcap_10": apply_high_beta_softcap(weights, cap=0.10, max_other_weight=0.30),
    }
    strongest = rolling.sort_values("window_return", ascending=False).head(1).iloc[0]
    weakest = rolling.sort_values("window_return", ascending=True).head(1).iloc[0]
    windows = [
        ("strongest_12m", str(strongest["start_month"]), str(strongest["end_month"])),
        ("weakest_12m", str(weakest["start_month"]), str(weakest["end_month"])),
    ]
    rows: list[dict[str, Any]] = []
    gate_frames: list[pd.DataFrame] = []
    for window_name, start_month, end_month in windows:
        start = pd.Period(start_month, freq="M").to_timestamp(how="start").date().isoformat()
        end = pd.Period(end_month, freq="M").to_timestamp(how="end").date().isoformat()
        baseline_row: dict[str, Any] | None = None
        for variant_id, variant_weights in variants.items():
            result = evaluate_replay_variant(variant_id, close, variant_weights, start=start, end=end)
            daily = result.pop("daily_nav")
            contrib = result.pop("ticker_contribution")
            safe_window = f"{window_name}_{variant_id}"
            daily.to_csv(out_dir / f"{safe_window}_daily_nav.csv", index=False)
            contrib.to_csv(out_dir / f"{safe_window}_ticker_contribution.csv", index=False)
            row = {"window_name": window_name, **{k: v for k, v in result.items() if not isinstance(v, (pd.DataFrame, pd.Series))}}
            if variant_id == "baseline_rebuilt":
                baseline_row = row
            if baseline_row:
                row["delta_cagr_vs_window_baseline"] = float(row["cagr"]) - float(baseline_row["cagr"])
                row["delta_calmar_vs_window_baseline"] = float(row["calmar"]) - float(baseline_row["calmar"])
                row["delta_penalty_vs_window_baseline"] = float(row["concentration_penalty_score"]) - float(baseline_row["concentration_penalty_score"])
            rows.append(row)
            gates = gate_results_from_metrics(row)
            gates.insert(0, "variant_id", variant_id)
            gates.insert(0, "window_name", window_name)
            gate_frames.append(gates)
    cycle_metrics = pd.DataFrame(rows)
    gate_results = pd.concat(gate_frames, ignore_index=True) if gate_frames else pd.DataFrame()
    cycle_metrics.to_csv(out_dir / "cycle_metrics.csv", index=False)
    gate_results.to_csv(out_dir / "gate_results.csv", index=False)
    sample_candidates = cycle_metrics.loc[
        (cycle_metrics["variant_id"] != "baseline_rebuilt")
        & (cycle_metrics["delta_penalty_vs_window_baseline"] < 0)
        & (cycle_metrics["delta_cagr_vs_window_baseline"] > -0.10)
    ].copy()
    accepted = bool(not sample_candidates.empty)
    best_sample = sample_candidates.sort_values(["delta_penalty_vs_window_baseline", "calmar"], ascending=[True, False]).head(1)
    verdict = {
        "cycle_id": "02",
        "cycle_type": "sample_replay_existing_holdings_overlay",
        "hypothesis": "Soft-capping high-beta holdings can reduce concentration penalty without severe sample-window performance damage.",
        "baseline_v8_verdict": baseline.get("classification"),
        "baseline_allow_enter_v9": baseline.get("allow_enter_v9"),
        "sample_windows": [w[0] for w in windows],
        "accepted_candidate": accepted,
        "replace_best": False,
        "best_sample_candidate": best_sample.iloc[0].to_dict() if not best_sample.empty else {},
        "concentration_penalty_score": float(best_sample["concentration_penalty_score"].iloc[0]) if not best_sample.empty else None,
        "execution_stress_summary": "Sample replay evaluated 5bps+5bps and 50bps+5bps cost on existing holdings overlays.",
        "pause_triggered": True,
        "pause_reason": "Cycle 03 would require broader/full replay or accepting a stability-vs-return tradeoff, which is a research decision.",
        "final_cycle_verdict": "sample_candidate_needs_human_review" if accepted else "sample_overlay_rejected_no_improvement",
    }
    write_json(out_dir / "cycle_verdict.json", verdict)
    best = {
        "best_candidate_id": "v8_baseline",
        "best_source": str(args.run_dir),
        "last_cycle_id": "02",
        "last_cycle_status": verdict["final_cycle_verdict"],
        "best_sample_candidate": verdict["best_sample_candidate"],
        "allow_enter_v9": False,
        "replace_best": False,
    }
    write_best_index(out_dir / "best_candidate_index.json", best)
    doc = DOCS_DIR / f"US_STOCK_SELECTION_V8_1_EVOLUTION_CYCLE_{timestamp}.md"
    local_doc = out_dir / f"US_STOCK_SELECTION_V8_1_EVOLUTION_CYCLE_{timestamp}.md"
    for path in [doc, local_doc]:
        write_cycle_report(
            path=path,
            cycle_id="02",
            objective="在既有 v8 持仓基础上，对 MSTR/TQQQ/QLD/SOXL 高 beta 暴露做 soft-cap overlay，并在最强/最弱 12M 窗口做小样本 replay。",
            changed_files=[
                "quant_lab/us_stock_selection/v8_1_gate_aware.py",
                "scripts/us_stock_selection/34_run_v8_1_gate_aware_improvement.py",
            ],
            rerun_scope="是，但仅为既有持仓 overlay 的小样本 replay；未训练模型、未重排全量候选、未运行 31b、未扩 universe。",
            inputs=[
                str(args.run_dir / "v8_paper_trading" / "monthly_holdings.csv"),
                str(args.diagnostic_dir / "rolling_12m_metrics.csv"),
                str(args.provider_uri),
            ],
            output_dir=out_dir,
            baseline=baseline,
            cycle_metrics=cycle_metrics,
            gate_results=gate_results,
            verdict=verdict,
            next_plan="暂停：cycle 03 需要决定是否接受 soft-cap 交易假设并批准更接近完整 replay 的验证。",
        )
    zip_path = package_cycle(
        OUTPUT_ROOT / f"us_stock_selection_quant_lab_v8_1_cycle_{timestamp}.zip",
        [
            PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v8_1_gate_metrics.py",
            PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v8_1_gate_aware.py",
            PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v8_1_reporting.py",
            PROJECT_ROOT / "scripts" / "us_stock_selection" / "34_run_v8_1_gate_aware_improvement.py",
            out_dir,
            doc,
            PROJECT_ROOT / "NEXT_STEPS.md",
        ],
    )
    logger.info("Cycle 02 packaged: %s", zip_path)
    return {"verdict": verdict, "zip_path": str(zip_path), "doc": str(doc)}


def main() -> None:
    args = parse_args()
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    cycle_label = "cycle_all" if args.cycle == "all" else f"cycle_{args.cycle}"
    out_dir = (args.out_dir or (OUTPUT_ROOT / f"v8_1_{cycle_label}_{timestamp}")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    logger = setup_logger(out_dir)
    logger.info("Prepared v8.1 evolution cycle=%s out_dir=%s", args.cycle, out_dir)
    inputs = ensure_inputs(args)
    if args.dry_run:
        write_json(
            out_dir / "dry_run_status.json",
            {
                "dry_run": True,
                "cycle": args.cycle,
                "out_dir": str(out_dir),
                "checked_inputs": inputs,
                "stopped_before": "cycle_execution",
            },
        )
        logger.info("Dry-run completed before cycle execution.")
        print({"dry_run": True, "out_dir": str(out_dir), "checked_inputs": len(inputs)})
        return
    results = []
    if args.cycle in {"01", "all"}:
        results.append(run_cycle01(args, out_dir, logger, timestamp))
    if args.cycle in {"02", "all"}:
        results.append(run_cycle02(args, out_dir, logger, timestamp))
    print({"out_dir": str(out_dir), "results": results})


if __name__ == "__main__":
    main()
