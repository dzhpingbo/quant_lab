"""True Qlib US provider preparation and lab utilities for v5."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.qlib_model_lab import QlibModelLab
from quant_lab.us_stock_selection.qlib_signal_backtest import (
    build_weights,
    compute_portfolio_metrics,
    portfolio_returns,
)
from quant_lab.us_stock_selection.utils import (
    compact_params,
    ensure_dir,
    save_dataframe,
    save_json,
    save_parquet,
    save_text,
)


POOL_A = [
    "QQQ",
    "QLD",
    "TQQQ",
    "SPY",
    "SSO",
    "UPRO",
    "IWM",
    "SOXX",
    "SMH",
    "XLK",
    "GLD",
    "TLT",
    "SHY",
    "AAPL",
    "MSFT",
    "NVDA",
    "GOOGL",
    "AMZN",
    "META",
    "TSLA",
    "AMD",
    "AVGO",
    "MU",
    "CRM",
    "ORCL",
    "NOW",
    "ADBE",
    "NFLX",
    "PANW",
    "CRWD",
    "PLTR",
    "NET",
    "SNOW",
    "UBER",
]


def default_true_provider_uri() -> Path:
    return Path.home() / ".qlib" / "qlib_data" / "us_data"


def locate_pyqlib_scripts() -> dict[str, Any]:
    """Locate pyqlib and check whether pip wheel contains source scripts."""
    result: dict[str, Any] = {
        "python_executable": sys.executable,
        "qlib_import_ok": False,
        "qlib_package_dir": "",
        "get_data_py": "",
        "dump_bin_py": "",
        "get_data_py_exists": False,
        "dump_bin_py_exists": False,
        "pip_wheel_note": "",
    }
    try:
        qlib = importlib.import_module("qlib")
        qlib_dir = Path(qlib.__file__).resolve().parent
        result["qlib_import_ok"] = True
        result["qlib_package_dir"] = str(qlib_dir)
        candidates = [
            qlib_dir / "scripts" / "get_data.py",
            qlib_dir.parent / "scripts" / "get_data.py",
            Path.cwd() / "scripts" / "get_data.py",
        ]
        dump_candidates = [
            qlib_dir / "scripts" / "dump_bin.py",
            qlib_dir.parent / "scripts" / "dump_bin.py",
            Path.cwd() / "scripts" / "dump_bin.py",
        ]
        get_data = next((path for path in candidates if path.exists()), None)
        dump_bin = next((path for path in dump_candidates if path.exists()), None)
        result["get_data_py"] = str(get_data or candidates[0])
        result["dump_bin_py"] = str(dump_bin or dump_candidates[0])
        result["get_data_py_exists"] = bool(get_data)
        result["dump_bin_py_exists"] = bool(dump_bin)
        if not get_data or not dump_bin:
            result["pip_wheel_note"] = "pyqlib pip wheel does not include qlib/scripts/get_data.py or dump_bin.py; use qlib.cli.data or clone microsoft/qlib."
    except Exception as exc:
        result["error"] = str(exc)
    return result


def official_download_attempt(
    out_dir: Path | str,
    target_dir: Path | str | None = None,
    execute: bool = False,
    timeout_sec: int = 1800,
) -> dict[str, Any]:
    """Attempt or document the official Qlib US data download path."""
    out_path = ensure_dir(out_dir)
    target = Path(target_dir).expanduser() if target_dir else default_true_provider_uri()
    script_info = locate_pyqlib_scripts()
    commands = {
        "preferred_get_data_command": f"{sys.executable} scripts/get_data.py qlib_data --target_dir {target} --region us",
        "pip_cli_command": f"{sys.executable} -m qlib.cli.data qlib_data --target_dir {target} --region us --exists_skip True",
        "clone_fallback_commands": [
            "git clone https://github.com/microsoft/qlib.git",
            "cd qlib",
            f"{sys.executable} scripts/get_data.py qlib_data --target_dir {target} --region us",
        ],
    }
    status: dict[str, Any] = {
        "target_dir": str(target),
        "execute": bool(execute),
        **script_info,
        **commands,
        "returncode": None,
        "stdout_tail": "",
        "stderr_tail": "",
        "provider_exists_after": target.exists(),
    }
    log_lines = [json.dumps(status, indent=2, ensure_ascii=False)]
    if execute and not target.exists():
        cmd = [sys.executable, "-m", "qlib.cli.data", "qlib_data", "--target_dir", str(target), "--region", "us", "--exists_skip", "True"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec, check=False)
            status["returncode"] = int(proc.returncode)
            status["stdout_tail"] = proc.stdout[-8000:]
            status["stderr_tail"] = proc.stderr[-8000:]
            status["provider_exists_after"] = target.exists()
            log_lines.extend(["\nCOMMAND:", " ".join(cmd), "\nSTDOUT:", proc.stdout, "\nSTDERR:", proc.stderr])
        except Exception as exc:
            status["returncode"] = -1
            status["stderr_tail"] = str(exc)
            log_lines.append(f"\nEXCEPTION:\n{exc}")
    save_text("\n".join(log_lines), out_path / "official_download_attempt.log")
    save_json(status, out_path / "official_download_status.json")
    return status


def qlib_provider_health_check(
    out_dir: Path | str,
    provider_uri: Path | str | None = None,
    tickers: list[str] | None = None,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Validate provider calendar, instruments, OHLCV fields, and a sample read."""
    out_path = ensure_dir(out_dir)
    provider = Path(provider_uri).expanduser() if provider_uri else default_true_provider_uri()
    tickers = [ticker.lower() for ticker in (tickers or POOL_A)]
    status: dict[str, Any] = {
        "provider_uri": str(provider),
        "provider_exists": provider.exists(),
        "provider_readable": False,
        "calendar_start": None,
        "calendar_end": None,
        "calendar_count": 0,
        "instrument_count": 0,
        "pool_a_available_count": 0,
        "pool_a_missing": [],
        "sample_rows": 0,
        "error": "",
    }
    sample = pd.DataFrame()
    if not provider.exists():
        save_json(status, out_path / "qlib_provider_health_check.json")
        save_dataframe(sample, out_path / "qlib_data_sample.csv")
        return status, sample
    try:
        import qlib
        from qlib.config import REG_US
        from qlib.data import D

        qlib.init(provider_uri=str(provider), region=REG_US, expression_cache=None, dataset_cache=None)
        cal = D.calendar(freq="day")
        status["calendar_count"] = int(len(cal))
        status["calendar_start"] = pd.Timestamp(cal[0]).date().isoformat() if len(cal) else None
        status["calendar_end"] = pd.Timestamp(cal[-1]).date().isoformat() if len(cal) else None
        instruments_path = provider / "instruments" / "all.txt"
        if instruments_path.exists():
            inst = pd.read_csv(instruments_path, sep="\t", header=None, names=["symbol", "start", "end"])
            inst["symbol_lower"] = inst["symbol"].str.lower()
            status["instrument_count"] = int(len(inst))
            available = sorted(set(tickers).intersection(set(inst["symbol_lower"])))
            missing = sorted(set(tickers).difference(set(inst["symbol_lower"])))
            status["pool_a_available_count"] = int(len(available))
            status["pool_a_missing"] = [item.upper() for item in missing]
        else:
            available = tickers
        sample_tickers = available[:8] if available else tickers[:8]
        fields = ["$open", "$high", "$low", "$close", "$volume", "$factor"]
        sample = D.features(sample_tickers, fields, start_time=status["calendar_start"], end_time=status["calendar_end"], freq="day")
        sample = sample.dropna(how="all").tail(500).reset_index()
        status["sample_rows"] = int(len(sample))
        status["provider_readable"] = status["sample_rows"] > 0
    except Exception as exc:
        status["error"] = str(exc)
    save_json(status, out_path / "qlib_provider_health_check.json")
    save_dataframe(sample, out_path / "qlib_data_sample.csv")
    return status, sample


def run_true_provider_lab(
    out_dir: Path | str,
    provider_uri: Path | str | None = None,
    tickers: list[str] | None = None,
    max_model_runs: int = 36,
    feature_sets: list[str] | None = None,
    model_names: list[str] | None = None,
    labels: list[str] | None = None,
) -> dict[str, pd.DataFrame]:
    """Train Alpha158/Alpha360/custom models on the true provider and backtest simple TopK portfolios."""
    out_path = ensure_dir(out_dir)
    pred_dir = ensure_dir(out_path / "predictions")
    holdings_dir = ensure_dir(out_path / "holdings")
    daily_dir = ensure_dir(out_path / "daily_returns")
    provider = Path(provider_uri).expanduser() if provider_uri else default_true_provider_uri()
    tickers = [ticker.lower() for ticker in (tickers or POOL_A)]
    if not provider.exists():
        empty = pd.DataFrame()
        save_dataframe(empty, out_path / "true_provider_model_runs.csv")
        save_dataframe(empty, out_path / "true_provider_signal_quality.csv")
        save_dataframe(empty, out_path / "true_provider_backtest_results.csv")
        return {"model_runs": empty, "signal_quality": empty, "backtest_results": empty}

    import qlib
    from qlib.config import REG_US

    qlib.init(provider_uri=str(provider), region=REG_US, expression_cache=None, dataset_cache=None)
    close = _load_true_close_panel(tickers)
    label_df = _load_true_labels(tickers)
    if close.empty or label_df.empty:
        empty = pd.DataFrame()
        save_dataframe(empty, out_path / "true_provider_model_runs.csv")
        save_dataframe(empty, out_path / "true_provider_signal_quality.csv")
        save_dataframe(empty, out_path / "true_provider_backtest_results.csv")
        return {"model_runs": empty, "signal_quality": empty, "backtest_results": empty}

    models = _build_true_models()
    if model_names:
        allowed_models = set(model_names)
        models = {name: model for name, model in models.items() if name in allowed_models}
    feature_sets = feature_sets or ["Alpha158", "Alpha360", "Alpha158_custom"]
    labels = labels or ["forward_return_5d", "forward_return_10d", "forward_return_20d"]
    split = _true_split(close.index)
    run_rows: list[dict[str, Any]] = []
    quality_rows: list[dict[str, Any]] = []
    backtest_rows: list[dict[str, Any]] = []
    completed = 0
    lab = QlibModelLab({"qlib_v4": {}}, _SilentLogger())

    for feature_set in feature_sets:
        feature_df = _load_true_feature_set(feature_set, tickers)
        if feature_df.empty:
            continue
        for label in labels:
            if completed >= max_model_runs:
                break
            panel = feature_df.join(label_df[[label]], how="inner").replace([np.inf, -np.inf], np.nan).dropna(subset=[label])
            for model_name, model in models.items():
                if completed >= max_model_runs:
                    break
                run_id = f"true_{feature_set}_{model_name}_{label}"
                train = panel.loc[(panel.index.get_level_values("datetime") >= split["train_start"]) & (panel.index.get_level_values("datetime") <= split["train_end"])]
                valid = panel.loc[(panel.index.get_level_values("datetime") >= split["valid_start"]) & (panel.index.get_level_values("datetime") <= split["valid_end"])]
                test = panel.loc[(panel.index.get_level_values("datetime") >= split["test_start"]) & (panel.index.get_level_values("datetime") <= split["test_end"])]
                feature_cols = [col for col in panel.columns if col != label and pd.api.types.is_numeric_dtype(panel[col])]
                if len(train) < 1000 or len(test) < 100:
                    continue
                try:
                    model.fit(train[feature_cols], train[label])
                    pred_parts = []
                    for segment, segment_df in [("train", train), ("valid", valid), ("test", test)]:
                        if segment_df.empty:
                            continue
                        pred_parts.append(
                            pd.DataFrame(
                                {
                                    "date": segment_df.index.get_level_values("datetime"),
                                    "ticker": segment_df.index.get_level_values("instrument").str.upper(),
                                    "score": model.predict(segment_df[feature_cols]),
                                    "label_value": segment_df[label].to_numpy(dtype=float),
                                    "segment": segment,
                                }
                            )
                        )
                    pred_df = pd.concat(pred_parts, ignore_index=True)
                    save_parquet(pred_df, pred_dir / f"{run_id}.parquet")
                    quality = lab._signal_quality(pred_df, label, run_id)
                    quality.update({"run_id": run_id, "feature_set": feature_set, "model": model_name, "label": label})
                    quality_rows.append(quality)
                    run_rows.append(
                        {
                            "run_id": run_id,
                            "feature_set": feature_set,
                            "model": model_name,
                            "label": label,
                            "train_rows": len(train),
                            "valid_rows": len(valid),
                            "test_rows": len(test),
                            "prediction_file": str(pred_dir / f"{run_id}.parquet"),
                            "provider_uri": str(provider),
                        }
                    )
                    bt = _backtest_true_predictions(pred_df, close, run_id, holdings_dir, daily_dir)
                    backtest_rows.extend(bt)
                    completed += 1
                except Exception as exc:
                    run_rows.append({"run_id": run_id, "feature_set": feature_set, "model": model_name, "label": label, "error": str(exc)})
                    completed += 1
        if completed >= max_model_runs:
            break

    model_runs = pd.DataFrame(run_rows)
    quality_df = pd.DataFrame(quality_rows).sort_values(["test_rank_ic_mean", "test_ic_mean"], ascending=[False, False]) if quality_rows else pd.DataFrame()
    backtest_df = pd.DataFrame(backtest_rows).sort_values(["calmar", "cagr"], ascending=[False, False]) if backtest_rows else pd.DataFrame()
    save_dataframe(model_runs, out_path / "true_provider_model_runs.csv")
    save_dataframe(quality_df, out_path / "true_provider_signal_quality.csv")
    save_dataframe(backtest_df, out_path / "true_provider_backtest_results.csv")
    return {"model_runs": model_runs, "signal_quality": quality_df, "backtest_results": backtest_df}


def _load_true_feature_sets(tickers: list[str]) -> dict[str, pd.DataFrame]:
    return {name: _load_true_feature_set(name, tickers) for name in ["Alpha158", "Alpha360", "Alpha158_custom"]}


def _load_true_feature_set(name: str, tickers: list[str]) -> pd.DataFrame:
    from qlib.data import D

    start, end = "2012-01-01", "2020-11-10"
    if name == "Alpha158":
        fields = [
            "$close/Ref($close, 1) - 1",
            "$close/Ref($close, 5) - 1",
            "$close/Ref($close, 10) - 1",
            "$close/Ref($close, 20) - 1",
            "$close/Ref($close, 60) - 1",
            "$close/Mean($close, 5) - 1",
            "$close/Mean($close, 10) - 1",
            "$close/Mean($close, 20) - 1",
            "$close/Mean($close, 60) - 1",
            "Std($close, 5)/Mean($close, 5)",
            "Std($close, 10)/Mean($close, 10)",
            "Std($close, 20)/Mean($close, 20)",
            "Std($close, 60)/Mean($close, 60)",
            "($high - $low)/$close",
            "($close - $open)/$open",
            "$volume/Mean($volume, 20) - 1",
            "Mean($volume, 20)/Mean($volume, 60) - 1",
            "Corr($close, $volume, 20)",
            "Max($close, 20)/$close - 1",
            "$close/Min($close, 20) - 1",
        ]
        names = [f"A158_EXPR_{idx:03d}" for idx in range(len(fields))]
        frame = D.features(tickers, fields, start_time=start, end_time=end, freq="day")
        frame.columns = names
        return _flatten_qlib_frame(frame)
    if name == "Alpha360":
        fields = [f"Ref($close, {i})/$close" for i in range(60)]
        names = [f"A360_CLOSE_REF_{i:03d}" for i in range(60)]
        frame = D.features(tickers, fields, start_time=start, end_time=end, freq="day")
        frame.columns = names
        return _flatten_qlib_frame(frame)
    if name == "Alpha158_custom":
        alpha158 = _load_true_feature_set("Alpha158", tickers)
        custom_fields = [
            "Ref($close, 5)/$close - 1",
            "Ref($close, 20)/$close - 1",
            "$close/Mean($close, 20) - 1",
            "$close/Mean($close, 60) - 1",
            "Std($close, 20)/Mean($close, 20)",
            "Corr($close, $volume, 20)",
            "Mean($volume, 20)/Mean($volume, 60) - 1",
            "($high - $low)/$close",
        ]
        custom_names = ["ret_ref5", "ret_ref20", "ma20_gap", "ma60_gap", "std20_mean20", "corr_close_volume20", "volume20_60", "hl_range"]
        custom = D.features(tickers, custom_fields, start_time=start, end_time=end, freq="day")
        custom.columns = custom_names
        custom = _flatten_qlib_frame(custom)
        return alpha158.join(custom, how="left", rsuffix="_custom")
    return pd.DataFrame()


def _load_true_labels(tickers: list[str]) -> pd.DataFrame:
    from qlib.data import D

    fields = ["Ref($close, -5)/$close - 1", "Ref($close, -10)/$close - 1", "Ref($close, -20)/$close - 1"]
    labels = D.features(tickers, fields, start_time="2012-01-01", end_time="2020-11-10", freq="day")
    labels.columns = ["forward_return_5d", "forward_return_10d", "forward_return_20d"]
    return _flatten_qlib_frame(labels)


def _load_true_close_panel(tickers: list[str]) -> pd.DataFrame:
    from qlib.data import D

    frame = D.features(tickers, ["$close"], start_time="2012-01-01", end_time="2020-11-10", freq="day")
    frame.columns = ["close"]
    flat = _flatten_qlib_frame(frame).reset_index()
    close = flat.pivot(index="datetime", columns="instrument", values="close").sort_index()
    close.columns = [str(col).upper() for col in close.columns]
    return close.ffill()


def _flatten_qlib_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [str(col[-1]) for col in out.columns]
    out = out.replace([np.inf, -np.inf], np.nan)
    out = out.reset_index()
    index_cols = [col for col in out.columns[:2]]
    parsed = {}
    for col in index_cols:
        parsed[col] = pd.to_datetime(out[col], errors="coerce")
    datetime_col = max(parsed, key=lambda col: int(parsed[col].notna().sum()))
    instrument_col = [col for col in index_cols if col != datetime_col][0]
    out["datetime"] = parsed[datetime_col]
    out["instrument"] = out[instrument_col].astype(str)
    out = out.drop(columns=[col for col in index_cols if col not in {"datetime", "instrument"}], errors="ignore")
    out = out.set_index(["datetime", "instrument"]).sort_index()
    return out


def _build_true_models() -> dict[str, Any]:
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import ElasticNet, Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    models: dict[str, Any] = {
        "Ridge": Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler()), ("model", Ridge(alpha=5.0))]),
        "ElasticNet": Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler()), ("model", ElasticNet(alpha=0.001, l1_ratio=0.2, max_iter=5000))]),
    }
    try:
        from lightgbm import LGBMRegressor

        models["LightGBM"] = LGBMRegressor(n_estimators=120, learning_rate=0.05, num_leaves=31, random_state=42, verbose=-1)
    except Exception:
        pass
    try:
        from xgboost import XGBRegressor

        models["XGBoost"] = XGBRegressor(n_estimators=120, learning_rate=0.05, max_depth=4, random_state=42, n_jobs=2, objective="reg:squarederror")
    except Exception:
        pass
    return models


def _true_split(index: pd.DatetimeIndex | pd.Index) -> dict[str, pd.Timestamp]:
    return {
        "train_start": pd.Timestamp("2012-01-01"),
        "train_end": pd.Timestamp("2016-12-31"),
        "valid_start": pd.Timestamp("2017-01-01"),
        "valid_end": pd.Timestamp("2018-12-31"),
        "test_start": pd.Timestamp("2019-01-01"),
        "test_end": pd.Timestamp("2020-11-10"),
    }


def _backtest_true_predictions(
    pred_df: pd.DataFrame,
    close: pd.DataFrame,
    run_id: str,
    holdings_dir: Path,
    daily_dir: Path,
) -> list[dict[str, Any]]:
    score = pred_df.loc[pred_df["segment"] == "test"].pivot_table(index="date", columns="ticker", values="score", aggfunc="last")
    score.index = pd.to_datetime(score.index)
    close = close.loc[(close.index >= score.index.min()) & (close.index <= score.index.max()), close.columns.intersection(score.columns)].ffill()
    score = score.reindex(close.index).loc[:, close.columns].ffill(limit=3)
    specs = [
        ("Top1_monthly_safe_switch", "M", {"top_k": 1, "max_weight": 1.0, "safe_asset": "SHY"}),
        ("Top3_monthly_equal_weight", "M", {"top_k": 3, "max_weight": 0.34}),
        ("Top5_monthly_equal_weight", "M", {"top_k": 5, "max_weight": 0.2}),
        ("Top3_weekly_equal_weight", "W", {"top_k": 3, "max_weight": 0.34}),
        ("TopKDropout_monthly", "M", {"top_k": 5, "max_weight": 0.2, "n_drop": 1}),
    ]
    rows: list[dict[str, Any]] = []
    for template, rebalance, params in specs:
        strategy_name = "safe_switch" if "safe_switch" in template else "topk_dropout" if "Dropout" in template else "topk_equal_weight"
        weights = build_weights(close, score, strategy_name=strategy_name, rebalance=rebalance, params=params)
        returns, turnover = portfolio_returns(close, weights, cost_bps=5.0, slippage_bps=5.0)
        strategy_id = f"{run_id}_{template}"
        holdings = weights.stack().rename("weight").reset_index()
        holdings.columns = ["date", "ticker", "weight"]
        holdings.insert(0, "strategy_id", strategy_id)
        save_parquet(holdings, holdings_dir / f"{strategy_id}.parquet")
        save_dataframe(pd.DataFrame({"date": returns.index, "strategy_id": strategy_id, "return": returns.to_numpy()}), daily_dir / f"{strategy_id}.csv")
        rows.append(
            {
                "strategy_id": strategy_id,
                "run_id": run_id,
                "portfolio": template,
                "params": compact_params({"rebalance": rebalance, **params}),
                **compute_portfolio_metrics(returns, turnover, weights),
                "passes_cagr_20": bool(compute_portfolio_metrics(returns, turnover, weights)["cagr"] >= 0.20),
                "passes_calmar_1": bool(compute_portfolio_metrics(returns, turnover, weights)["calmar"] > 1.0),
            }
        )
    return rows


class _SilentLogger:
    def info(self, *_args, **_kwargs):
        return None

    def warning(self, *_args, **_kwargs):
        return None
