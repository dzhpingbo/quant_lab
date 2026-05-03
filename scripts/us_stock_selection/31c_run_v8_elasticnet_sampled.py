"""Run a bounded sampled ElasticNet convergence diagnostic for v8."""

from __future__ import annotations

import argparse
import multiprocessing as mp
import queue
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection.feature_cache import load_feature_cache
from quant_lab.us_stock_selection.local_qlib_provider_builder import default_local_provider_uri
from quant_lab.us_stock_selection.qlib_workflow_runner import load_close_from_provider
from quant_lab.us_stock_selection.utils import (
    PROJECT_ROOT as ROOT,
    create_run_artifacts,
    ensure_dir,
    load_yaml,
    make_logger,
    merge_many_dicts,
    save_dataframe,
    save_text,
    save_yaml,
)
from quant_lab.us_stock_selection.v8_model_stability import ELASTICNET_CONFIGS
from quant_lab.us_stock_selection.v8_paper_trading import ModelSpec, fit_model, latest_available_feature_date, rebalance_dates, trading_offset


DEFAULT_SOURCE_RUN = ROOT / "outputs" / "us_stock_selection" / "run_20260426_060824"


def _fit_worker(
    result_queue: mp.Queue,
    cache_dir: str,
    provider_uri: str,
    config_name: str,
    params: dict[str, Any],
    decision_date_text: str,
) -> None:
    # Worker process gives the parent a real timeout boundary on Windows.
    try:
        frame, feature_cols = load_feature_cache(cache_dir, "Alpha360")
        frame["date"] = pd.to_datetime(frame["date"])
        close = load_close_from_provider(provider_uri, start="2020-01-01")
        decision_date = pd.Timestamp(decision_date_text)
        spec = ModelSpec("ElasticNet", feature_set="Alpha360", label="label_5d", params=params)
        feature_date = latest_available_feature_date(frame, decision_date)
        train_end = trading_offset(close.index, decision_date, -6)
        if pd.isna(feature_date) or pd.isna(train_end):
            result_queue.put({"config": config_name, "decision_date": decision_date.date().isoformat(), "fit_status": "skipped_no_feature_or_train_end", "fit_warning_count": 0, "fit_warnings": "", "train_rows": 0, "predict_rows": 0})
            return
        train = frame.loc[(frame["date"] <= train_end) & frame[spec.label].notna()].copy()
        pred = frame.loc[frame["date"] == feature_date].copy()
        if len(train) < 500 or pred.empty:
            result_queue.put({"config": config_name, "decision_date": decision_date.date().isoformat(), "fit_status": "skipped_insufficient_rows", "fit_warning_count": 0, "fit_warnings": "", "train_rows": int(len(train)), "predict_rows": int(len(pred))})
            return
        _, fit_info = fit_model(train, pred, feature_cols, spec)
        result_queue.put({"config": config_name, "decision_date": decision_date.date().isoformat(), **fit_info})
    except Exception as exc:  # pragma: no cover - worker failure is environment dependent
        result_queue.put({"config": config_name, "decision_date": decision_date_text, "fit_status": "failed", "fit_warning_count": 1, "fit_warnings": str(exc), "train_rows": 0, "predict_rows": 0})


def _run_fit_with_timeout(
    cache_dir: Path,
    provider_uri: str,
    config_name: str,
    params: dict[str, Any],
    decision_date: pd.Timestamp,
    timeout_seconds: int,
) -> dict[str, Any]:
    ctx = mp.get_context("spawn")
    result_queue: mp.Queue = ctx.Queue()
    process = ctx.Process(
        target=_fit_worker,
        args=(result_queue, str(cache_dir), provider_uri, config_name, params, decision_date.date().isoformat()),
    )
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(10)
        return {
            "config": config_name,
            "decision_date": decision_date.date().isoformat(),
            "fit_status": "timeout_terminated",
            "fit_warning_count": 1,
            "fit_warnings": f"terminated after {timeout_seconds}s",
            "train_rows": 0,
            "predict_rows": 0,
        }
    try:
        return result_queue.get_nowait()
    except queue.Empty:
        return {
            "config": config_name,
            "decision_date": decision_date.date().isoformat(),
            "fit_status": f"failed_exit_{process.exitcode}",
            "fit_warning_count": 1,
            "fit_warnings": "worker exited without returning a result",
            "train_rows": 0,
            "predict_rows": 0,
        }


def _sample_months(months: list[pd.Timestamp], mode: str, max_count: int) -> list[pd.Timestamp]:
    if max_count <= 0:
        return []
    if mode == "all":
        return months[:max_count]
    if mode == "first":
        return months[:max_count]
    if mode == "last":
        return months[-max_count:]
    if len(months) <= max_count:
        return months
    positions = sorted({round(i * (len(months) - 1) / max(1, max_count - 1)) for i in range(max_count)})
    return [months[pos] for pos in positions]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run v8 stage 31c: sampled ElasticNet convergence with timeouts.")
    parser.add_argument("--config", default="configs/us_stock_selection/validation_config.yaml")
    parser.add_argument("--provider-uri", default=str(default_local_provider_uri()))
    parser.add_argument("--source-run", default=str(DEFAULT_SOURCE_RUN))
    parser.add_argument("--run-dir", default="", help="Existing run dir to reuse; empty creates a new run.")
    parser.add_argument("--sample-mode", choices=["representative", "first", "last", "all"], default="representative")
    parser.add_argument("--max-sample-months", type=int, default=3)
    parser.add_argument("--per-fit-timeout-seconds", type=int, default=900)
    parser.add_argument("--max-seconds", type=int, default=1800)
    parser.add_argument("--dry-run-init", action="store_true", help="Create directories and stop before sampled fits.")
    args = parser.parse_args()

    config = merge_many_dicts(load_yaml("configs/us_stock_selection/factor_groups.yaml"), load_yaml(args.config))
    output_root = ROOT / config.get("paths", {}).get("output_root", "outputs/us_stock_selection")
    if args.run_dir:
        run_dir = ensure_dir(args.run_dir)
        logs_dir = ensure_dir(run_dir / "logs")
        timestamp = run_dir.name.replace("run_", "")
    else:
        artifacts = create_run_artifacts(output_root)
        run_dir = artifacts.run_dir
        logs_dir = artifacts.logs_dir
        timestamp = artifacts.timestamp

    logger = make_logger(logs_dir / "31c_elasticnet_sampled.log", level=str(config.get("logging", {}).get("level", "INFO")))
    save_yaml(config, run_dir / "run_config.yaml")
    cache_dir = ensure_dir(run_dir / "v7_feature_cache")
    model_dir = ensure_dir(run_dir / "v8_model_stability")
    save_text(
        "Stage 31c runs sampled ElasticNet convergence diagnostics with per-fit process timeouts.\n",
        run_dir / "STAGE_31C_ELASTICNET_SAMPLED.md",
    )
    logger.info(f"Prepared v8 stage 31c run_dir={run_dir} timestamp={timestamp}")

    if args.dry_run_init:
        # Operational self-check: stop before cache copy and subprocess fits.
        logger.info("Dry-run init requested; stopping before sampled ElasticNet fits.")
        print({"run_dir": str(run_dir), "stage": "31c", "dry_run_init": True})
        return

    source_cache = Path(args.source_run) / "v7_feature_cache"
    fallback = ROOT / "outputs" / "us_stock_selection" / "run_20260426_035045" / "v7_feature_cache"
    if not (cache_dir / "alpha360_cache.parquet").exists():
        shutil.copytree(source_cache if source_cache.exists() else fallback, cache_dir, dirs_exist_ok=True)

    frame, _ = load_feature_cache(cache_dir, "Alpha360")
    frame["date"] = pd.to_datetime(frame["date"])
    close = load_close_from_provider(args.provider_uri, start="2020-01-01")
    all_months = rebalance_dates(close.index, start="2024-01-01", end="2026-04-17", timing="month_end")
    sample_months = _sample_months(all_months, args.sample_mode, args.max_sample_months)
    logger.info(f"Selected sample months: {[m.date().isoformat() for m in sample_months]}")

    started = time.monotonic()
    rows: list[dict[str, Any]] = []
    for name, params in ELASTICNET_CONFIGS:
        detail_rows: list[dict[str, Any]] = []
        for decision_date in sample_months:
            remaining = args.max_seconds - int(time.monotonic() - started)
            if remaining <= 0:
                logger.info(f"Skipping {name} sampled fit for {decision_date.date()} because global timeout was reached.")
                detail_rows.append(
                    {
                        "config": name,
                        "decision_date": decision_date.date().isoformat(),
                        "fit_status": "global_timeout_not_started",
                        "fit_warning_count": 1,
                        "fit_warnings": f"global timeout {args.max_seconds}s reached",
                        "train_rows": 0,
                        "predict_rows": 0,
                        "elapsed_seconds": 0.0,
                    }
                )
                continue
            timeout = max(1, min(args.per_fit_timeout_seconds, remaining))
            logger.info(f"Running {name} sampled fit for {decision_date.date()} with timeout={timeout}s")
            fit_started = time.monotonic()
            fit_result = _run_fit_with_timeout(cache_dir, args.provider_uri, name, params, decision_date, timeout)
            fit_result["elapsed_seconds"] = round(time.monotonic() - fit_started, 3)
            logger.info(
                f"Finished {name} sampled fit for {decision_date.date()} "
                f"status={fit_result.get('fit_status')} "
                f"elapsed_seconds={fit_result['elapsed_seconds']:.3f} "
                f"warnings={fit_result.get('fit_warning_count')}"
            )
            detail_rows.append(fit_result)
        detail = pd.DataFrame(detail_rows)
        save_dataframe(detail, model_dir / f"{name}_sampled_convergence_detail.csv")
        warning_count = int(detail["fit_warning_count"].sum()) if not detail.empty else 0
        rows.append(
            {
                "config": name,
                "params": str(params),
                "decision_count": int(len(detail)),
                "warning_count": warning_count,
                "warning_decision_rate": float((detail["fit_warning_count"] > 0).mean()) if not detail.empty else 0.0,
                "sample_mode": args.sample_mode,
                "max_sample_months": args.max_sample_months,
                "per_fit_timeout_seconds": args.per_fit_timeout_seconds,
                "max_seconds": args.max_seconds,
                "sample_warning": " | ".join(detail.loc[detail["fit_warning_count"] > 0, "fit_warnings"].dropna().astype(str).head(3)),
            }
        )
    summary = pd.DataFrame(rows)
    save_dataframe(summary, model_dir / "elasticnet_convergence_check.csv")
    logger.info("Completed stage 31c sampled ElasticNet diagnostic.")
    print({"run_dir": str(run_dir), "stage": "31c", "status": "completed", "rows": int(len(summary))})


if __name__ == "__main__":
    mp.freeze_support()
    main()
