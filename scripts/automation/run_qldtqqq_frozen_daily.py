"""Frozen daily replay for QLD/TQQQ turning-point strategies.

This wrapper reuses the existing QLD/TQQQ lab data, feature, probability, and
backtest functions, but it only replays fixed approved parameter pairs. It does
not rank candidates, search parameters, call the VIX comparison script, trade,
or connect to brokers.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime, timedelta, time as dt_time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import qldtqqq_turning_point_lab as lab


FROZEN_PARAMS = {
    "QLD": {
        "core": "core_ma100_turn_b6_t7_trim70",
        "gate": "gate_adaptive_vt20_tr12_k12",
    },
    "TQQQ": {
        "core": "core_ma100_turn_b6_t6_trim70",
        "gate": "gate_loose_vt32_tr20_k18",
    },
}
TEST_START = "2021-01-01"
WF_START = lab.WF_START
COST = 0.002
US_EOD_BUFFER_TIME = dt_time(6, 30)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay fixed QLD/TQQQ frozen daily strategies.")
    parser.add_argument("--output-dir", default="", help="Output directory for this job.")
    parser.add_argument("--dry-run", action="store_true", help="Print the replay plan without running.")
    parser.add_argument("--skip-download", action="store_true", help="Use the latest existing qldtqqq updated_data snapshot.")
    parser.add_argument("--json-out", default="", help="Optional JSON summary path.")
    parser.add_argument("--md-out", default="", help="Optional Markdown summary path.")
    return parser.parse_args()


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def pct_or_none(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def next_weekday(value: pd.Timestamp) -> str:
    current = value.date() + timedelta(days=1)
    while current.weekday() >= 5:
        current += timedelta(days=1)
    return current.isoformat()


def today_exclusive_end() -> str:
    return (date.today() + timedelta(days=1)).isoformat()


def us_eod_completeness_for_latest(latest_date: pd.Timestamp, *, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now()
    latest_day = pd.Timestamp(latest_date).date()
    today = current.date()
    if latest_day >= today:
        accepted = today - timedelta(days=1)
        return {
            "data_completeness": "INTRADAY_REJECTED",
            "raw_latest_data_date": latest_day.isoformat(),
            "accepted_latest_data_date": accepted.isoformat(),
            "checked_at": current.isoformat(timespec="seconds"),
            "rule": "us_bar_date_not_before_asia_local_today",
            "reason": "US daily bar date is not before the Asia/Shanghai run date, so it cannot be treated as a completed US EOD bar.",
        }
    if current.time() < US_EOD_BUFFER_TIME and latest_day >= today - timedelta(days=1):
        accepted = today - timedelta(days=2)
        return {
            "data_completeness": "UNKNOWN_FALLBACK_PREVIOUS_EOD",
            "raw_latest_data_date": latest_day.isoformat(),
            "accepted_latest_data_date": accepted.isoformat(),
            "checked_at": current.isoformat(timespec="seconds"),
            "rule": "asia_local_time_before_06_30_buffer",
            "reason": "Run time is before the configured US EOD buffer, so the most recent US bar is not accepted without explicit final-EOD confirmation.",
        }
    return {
        "data_completeness": "EOD_CONFIRMED",
        "raw_latest_data_date": latest_day.isoformat(),
        "accepted_latest_data_date": latest_day.isoformat(),
        "checked_at": current.isoformat(timespec="seconds"),
        "rule": "us_date_before_asia_local_today_after_buffer",
        "reason": "Latest US bar is before the Asia/Shanghai run date and the run is after the configured 06:30 buffer.",
    }


def apply_us_eod_filter(data: dict[str, pd.DataFrame], latest: pd.Timestamp) -> tuple[dict[str, pd.DataFrame], pd.Timestamp, dict[str, Any]]:
    meta = us_eod_completeness_for_latest(latest)
    accepted_limit = pd.Timestamp(meta["accepted_latest_data_date"])
    latest_by_essential = []
    for symbol in lab.ESSENTIAL:
        frame = data.get(symbol, pd.DataFrame())
        if frame.empty:
            continue
        eligible = frame.loc[frame.index <= accepted_limit]
        if not eligible.empty:
            latest_by_essential.append(pd.Timestamp(eligible.index.max()))
    if not latest_by_essential:
        return data, latest, meta
    accepted_actual = min(latest_by_essential)
    if accepted_actual.date().isoformat() != meta["accepted_latest_data_date"]:
        meta["accepted_latest_data_date"] = accepted_actual.date().isoformat()
        meta["reason"] = (
            f"{meta['reason']} Requested fallback date was not aligned across essential symbols; "
            f"using latest common prior row {accepted_actual.date().isoformat()}."
        )
    filtered = {symbol: frame.loc[frame.index <= accepted_actual].copy() for symbol, frame in data.items()}
    return filtered, accepted_actual, meta


def read_ohlcv_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [str(col).strip().lower() for col in df.columns]
    date_col = next((col for col in df.columns if col in {"date", "datetime"}), df.columns[0])
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).set_index(date_col).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[[col for col in ["open", "high", "low", "close", "volume"] if col in df.columns]].copy()


def load_latest_snapshot(output_dir: Path) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.Timestamp]:
    runs = sorted(
        [path for path in (ROOT / "outputs" / "qldtqqq_turning_points").glob("qldtqqq_turning_*") if (path / "updated_data").is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not runs:
        raise RuntimeError("No existing qldtqqq updated_data snapshot found.")
    source = runs[0]
    data: dict[str, pd.DataFrame] = {}
    for csv_path in (source / "updated_data").glob("*.csv"):
        data[csv_path.stem] = read_ohlcv_csv(csv_path)
    missing = [symbol for symbol in lab.ESSENTIAL if symbol not in data or data[symbol].empty]
    if missing:
        raise RuntimeError(f"Latest qldtqqq snapshot is missing essential symbols: {missing}")
    latest = min(data[symbol].index.max() for symbol in lab.ESSENTIAL)
    for key in list(data):
        data[key] = data[key].loc[data[key].index <= latest].copy()
    status_path = source / "latest_data_status.csv"
    status = pd.read_csv(status_path) if status_path.exists() else pd.DataFrame()
    status.to_csv(output_dir / "latest_data_status.csv", index=False, encoding="utf-8-sig")
    return data, status, latest


def fixed_replay_for_target(
    target: str,
    data: dict[str, pd.DataFrame],
    features: pd.DataFrame,
    scores: pd.DataFrame,
    probs: pd.DataFrame,
    events: pd.DataFrame,
    output_dir: Path,
    next_open_date: str,
) -> dict[str, Any]:
    frozen = FROZEN_PARAMS[target]
    asset = data[target].copy()
    index = asset.index.intersection(features.index)
    asset = asset.reindex(index).dropna(subset=["open", "close"])
    index = asset.index
    target_features = features.reindex(index).ffill()
    target_scores = scores.reindex(index).ffill()
    target_probs = probs.reindex(index).ffill().fillna(0.0)

    candidates = lab.build_candidates(index, target_features, target_scores, target_probs)
    candidate = next((item for item in candidates if item.name == frozen["core"]), None)
    if candidate is None:
        raise RuntimeError(f"Frozen core candidate not found for {target}: {frozen['core']}")
    spec = next((item for item in lab.risk_specs(target) if item.name == frozen["gate"]), None)
    if spec is None:
        raise RuntimeError(f"Frozen risk gate not found for {target}: {frozen['gate']}")

    result = lab.weighted_backtest(asset, candidate.signal, target_features, target_scores, spec, COST)
    wf = lab.metrics_from(result, WF_START, None)
    test = lab.metrics_from(result, TEST_START, None)
    full = lab.metrics_from(result, None, None)
    cycles = lab.cycle_metrics(result)
    capture = lab.event_capture_metrics(events, result)
    buy_hold = lab.buy_hold_metrics(asset, WF_START, None)
    action = lab.next_action(asset, result, next_open_date)
    strategy_id = f"{candidate.name}__{spec.name}"

    nav = pd.DataFrame(
        {
            "open": asset["open"],
            "close": asset["close"],
            "desired_weight_after_close": result["desired"],
            "position_weight_at_open": result["position"],
            "entry_at_open": result["entries"].astype(int),
            "exit_at_open": result["exits"].astype(int),
            "portfolio_value": result["value"],
            "portfolio_return": result["returns"],
            "bottom_prob": target_probs["bottom_prob"],
            "top_prob": target_probs["top_prob"],
            "bottom_score": target_scores["bottom_score"],
            "top_score": target_scores["top_score"],
            "trend_score": target_scores["trend_score"],
        }
    )
    nav_path = output_dir / f"{target}_frozen_signal_nav.csv"
    nav.to_csv(nav_path, encoding="utf-8-sig")

    return {
        "symbol": target,
        "frozen_core": candidate.name,
        "frozen_gate": spec.name,
        "strategy_id": strategy_id,
        "status": "PASS",
        "metric_scope": "test_start_to_latest",
        "CAGR": pct_or_none(test.get("annual_return")),
        "Calmar": pct_or_none(test.get("calmar")),
        "Max Drawdown": pct_or_none(test.get("max_drawdown")),
        "latest_data_date": asset.index.max().strftime("%Y-%m-%d"),
        "latest_signal": action,
        "wf_metrics": wf,
        "test_metrics": test,
        "full_metrics": full,
        "cycle_metrics": cycles,
        "turning_capture": capture,
        "buy_hold_wf_metrics": buy_hold,
        "output_dir": str(output_dir),
        "signal_nav": str(nav_path),
        "error_message": "",
    }


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# QLD/TQQQ Frozen Daily Replay",
        "",
        f"- Status: `{payload.get('status')}`",
        f"- Output directory: `{payload.get('output_dir')}`",
        f"- Data download performed: `{payload.get('data_download_performed')}`",
        f"- Search performed: `False`",
        f"- Latest data date: `{payload.get('latest_data_date')}`",
        "",
        "| Symbol | Frozen core | Frozen gate | Status | CAGR | Calmar | Max Drawdown | Latest action | Latest weight |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: |",
    ]
    for row in payload.get("results", []):
        signal = row.get("latest_signal") or {}
        lines.append(
            "| {symbol} | `{core}` | `{gate}` | `{status}` | {cagr} | {calmar} | {dd} | `{action}` | {weight} |".format(
                symbol=row.get("symbol"),
                core=row.get("frozen_core"),
                gate=row.get("frozen_gate"),
                status=row.get("status"),
                cagr="" if row.get("CAGR") is None else f"{row.get('CAGR'):.2%}",
                calmar="" if row.get("Calmar") is None else f"{row.get('Calmar'):.3f}",
                dd="" if row.get("Max Drawdown") is None else f"{row.get('Max Drawdown'):.2%}",
                action=signal.get("action", ""),
                weight="" if signal.get("position_weight_at_latest_open") is None else f"{float(signal.get('position_weight_at_latest_open')):.3f}",
            )
        )
    if payload.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        lines.extend([f"- {item}" for item in payload["warnings"]])
    if payload.get("errors"):
        lines.extend(["", "## Errors", ""])
        lines.extend([f"- {item}" for item in payload["errors"]])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_manifest(output_dir: Path) -> Path:
    rows = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file():
            stat = path.stat()
            rows.append({"path": str(path), "size_bytes": stat.st_size, "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")})
    manifest_path = output_dir / "qldtqqq_artifacts_manifest.json"
    write_json(manifest_path, {"files": rows, "count": len(rows)})
    return manifest_path


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir) if args.output_dir else ROOT / "outputs" / "qldtqqq_turning_points" / f"qldtqqq_frozen_daily_{stamp()}"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_out = Path(args.json_out) if args.json_out else output_dir / "qldtqqq_job_summary.json"
    md_out = Path(args.md_out) if args.md_out else output_dir / "qldtqqq_job_summary.md"

    payload: dict[str, Any] = {
        "job": "qld_tqqq",
        "status": "DRY_RUN" if args.dry_run else "RUNNING",
        "output_dir": str(output_dir),
        "frozen_params": FROZEN_PARAMS,
        "data_download_performed": False,
        "search_performed": False,
        "vix_comparison_called": False,
        "results": [],
        "warnings": [],
        "errors": [],
    }

    if args.dry_run:
        payload["status"] = "DRY_RUN"
        payload["planned_command"] = "Replay fixed QLD/TQQQ params using qldtqqq_turning_point_lab functions."
        write_json(json_out, payload)
        write_markdown(md_out, payload)
        write_manifest(output_dir)
        print(json.dumps(jsonable({"status": "DRY_RUN", "output_dir": output_dir}), indent=2))
        return 0

    try:
        if args.skip_download:
            data, status, latest = load_latest_snapshot(output_dir)
            payload["warnings"].append("skip-download enabled; used latest existing qldtqqq updated_data snapshot.")
        else:
            data, status, latest = lab.prepare_data(output_dir, today_exclusive_end())
            payload["data_download_performed"] = True
        data, latest, eod_meta = apply_us_eod_filter(data, latest)
        payload["data_completeness"] = eod_meta
        payload["latest_data_date"] = latest.strftime("%Y-%m-%d")
        next_open_date = next_weekday(latest)

        labels, events = lab.label_turning_points(data["QQQ"])
        labels.to_csv(output_dir / "turning_labels.csv", encoding="utf-8-sig")
        events.to_csv(output_dir / "turning_events.csv", index=False, encoding="utf-8-sig")
        features, scores, feature_meta = lab.build_feature_frame(data, data["QQQ"].index, output_dir)
        features.to_csv(output_dir / "feature_frame.csv", encoding="utf-8-sig")
        scores.to_csv(output_dir / "turning_scores.csv", encoding="utf-8-sig")
        probs, folds = lab.walk_forward_probabilities(features, labels, lab.feature_columns(features), output_dir)

        rows = []
        latest_rows = []
        for target in ("QLD", "TQQQ"):
            result = fixed_replay_for_target(target, data, features, scores, probs, events, output_dir, next_open_date)
            payload["results"].append(result)
            rows.append(
                {
                    "symbol": result["symbol"],
                    "frozen_core": result["frozen_core"],
                    "frozen_gate": result["frozen_gate"],
                    "strategy_id": result["strategy_id"],
                    "CAGR": result["CAGR"],
                    "Calmar": result["Calmar"],
                    "Max Drawdown": result["Max Drawdown"],
                    "latest_data_date": result["latest_data_date"],
                    "latest_action": result["latest_signal"]["action"],
                    "latest_weight": result["latest_signal"]["position_weight_at_latest_open"],
                    "test_annual_return": result["test_metrics"]["annual_return"],
                    "test_calmar": result["test_metrics"]["calmar"],
                    "test_max_drawdown": result["test_metrics"]["max_drawdown"],
                    "wf_annual_return": result["wf_metrics"]["annual_return"],
                    "wf_calmar": result["wf_metrics"]["calmar"],
                    "wf_max_drawdown": result["wf_metrics"]["max_drawdown"],
                    "full_annual_return": result["full_metrics"]["annual_return"],
                    "full_calmar": result["full_metrics"]["calmar"],
                    "full_max_drawdown": result["full_metrics"]["max_drawdown"],
                }
            )
            latest = result["latest_signal"]
            latest_rows.append({"symbol": target, **latest})
        pd.DataFrame(rows).to_csv(output_dir / "qldtqqq_metrics.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame(latest_rows).to_csv(output_dir / "qldtqqq_latest_signal.csv", index=False, encoding="utf-8-sig")
        write_json(output_dir / "feature_meta.json", feature_meta)
        folds.to_csv(output_dir / "walk_forward_model_folds.csv", index=False, encoding="utf-8-sig")
        payload["status"] = "PASS"
    except Exception as exc:
        payload["status"] = "FAIL"
        payload["errors"].append(f"{type(exc).__name__}: {exc}")

    manifest = write_manifest(output_dir)
    payload["artifacts_manifest"] = str(manifest)
    write_json(json_out, payload)
    write_markdown(md_out, payload)
    print(json.dumps(jsonable({"status": payload["status"], "output_dir": output_dir, "json": json_out}), indent=2))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
