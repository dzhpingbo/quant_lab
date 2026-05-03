"""Shared helpers for the US stock selection pipeline."""

from __future__ import annotations

import html
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import pandas as pd
import yaml
from loguru import logger


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class RunArtifacts:
    """Filesystem locations for one timestamped research run."""

    timestamp: str
    run_dir: Path
    config_snapshot_dir: Path
    benchmark_dir: Path
    data_quality_dir: Path
    factor_screen_dir: Path
    strategy_search_dir: Path
    walk_forward_dir: Path
    regime_validation_dir: Path
    qlib_dir: Path
    qlib_env_dir: Path
    qlib_data_dir: Path
    qlib_model_lab_dir: Path
    qlib_signal_backtest_dir: Path
    qlib_walk_forward_dir: Path
    qlib_overfit_dir: Path
    ranking_dir: Path
    reports_dir: Path
    logs_dir: Path


def now_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_dir(path: Path | str) -> Path:
    out = Path(path)
    out.mkdir(parents=True, exist_ok=True)
    return out


def load_yaml(path: Path | str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return data or {}


def load_env_config() -> dict[str, Any]:
    env_path = PROJECT_ROOT / "configs" / "env" / "local.yaml"
    return load_yaml(env_path)


def merge_many_dicts(*configs: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for config in configs:
        merged = merge_dicts(merged, dict(config))
    return merged


def create_run_artifacts(base_dir: Path | str, timestamp: str | None = None) -> RunArtifacts:
    stamp = timestamp or now_timestamp()
    run_dir = ensure_dir(Path(base_dir) / f"run_{stamp}")
    return RunArtifacts(
        timestamp=stamp,
        run_dir=run_dir,
        config_snapshot_dir=ensure_dir(run_dir / "config_snapshot"),
        benchmark_dir=ensure_dir(run_dir / "benchmark"),
        data_quality_dir=ensure_dir(run_dir / "data_quality"),
        factor_screen_dir=ensure_dir(run_dir / "factor_screen"),
        strategy_search_dir=ensure_dir(run_dir / "strategy_search"),
        walk_forward_dir=ensure_dir(run_dir / "walk_forward"),
        regime_validation_dir=ensure_dir(run_dir / "regime_validation"),
        qlib_dir=ensure_dir(run_dir / "qlib"),
        qlib_env_dir=ensure_dir(run_dir / "qlib_env"),
        qlib_data_dir=ensure_dir(run_dir / "qlib_data"),
        qlib_model_lab_dir=ensure_dir(run_dir / "qlib_model_lab"),
        qlib_signal_backtest_dir=ensure_dir(run_dir / "qlib_signal_backtest"),
        qlib_walk_forward_dir=ensure_dir(run_dir / "qlib_walk_forward"),
        qlib_overfit_dir=ensure_dir(run_dir / "qlib_overfit"),
        ranking_dir=ensure_dir(run_dir / "ranking"),
        reports_dir=ensure_dir(run_dir / "reports"),
        logs_dir=ensure_dir(run_dir / "logs"),
    )


def make_logger(log_file: Path, level: str = "INFO"):
    logger.remove()
    logger.add(
        sys.stdout,
        level=level,
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )
    logger.add(
        str(log_file),
        level=level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        encoding="utf-8",
        rotation="10 MB",
        retention="30 days",
    )
    return logger


def save_yaml(data: Mapping[str, Any], path: Path | str) -> Path:
    out = Path(path)
    ensure_dir(out.parent)
    with out.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(make_yaml_safe(dict(data)), handle, sort_keys=False, allow_unicode=True)
    return out


def save_json(data: Any, path: Path | str) -> Path:
    out = Path(path)
    ensure_dir(out.parent)
    with out.open("w", encoding="utf-8") as handle:
        json.dump(make_yaml_safe(data), handle, indent=2, ensure_ascii=False)
    return out


def save_text(text: str, path: Path | str) -> Path:
    out = Path(path)
    ensure_dir(out.parent)
    out.write_text(text, encoding="utf-8")
    return out


def save_dataframe(df: pd.DataFrame, path: Path | str, index: bool = False) -> Path:
    out = Path(path)
    ensure_dir(out.parent)
    df.to_csv(out, index=index, encoding="utf-8-sig")
    return out


def save_parquet(df: pd.DataFrame, path: Path | str) -> Path:
    out = Path(path)
    ensure_dir(out.parent)
    df.to_parquet(out, engine="pyarrow", compression="zstd")
    return out


def make_yaml_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): make_yaml_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [make_yaml_safe(item) for item in value]
    if isinstance(value, tuple):
        return [make_yaml_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if pd.isna(value) if not isinstance(value, (str, bytes)) else False:
        return None
    return value


def merge_dicts(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(result.get(key), dict) and isinstance(value, Mapping):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def annualized_return(returns: pd.Series, periods_per_year: int = 252) -> float:
    clean = pd.Series(returns).dropna().astype(float)
    if clean.empty:
        return 0.0
    total = float((1.0 + clean).prod() - 1.0)
    years = len(clean) / float(periods_per_year)
    if years <= 0:
        return 0.0
    if total <= -1.0:
        return -1.0
    return float((1.0 + total) ** (1.0 / years) - 1.0)


def annualized_volatility(returns: pd.Series, periods_per_year: int = 252) -> float:
    clean = pd.Series(returns).dropna().astype(float)
    if clean.empty:
        return 0.0
    return float(clean.std(ddof=0) * np.sqrt(periods_per_year))


def max_drawdown(nav: pd.Series) -> float:
    clean = pd.Series(nav).dropna().astype(float)
    if clean.empty:
        return 0.0
    rolling_peak = clean.cummax()
    drawdown = clean.div(rolling_peak).sub(1.0)
    return float(drawdown.min())


def calmar_ratio(returns: pd.Series, periods_per_year: int = 252) -> float:
    nav = nav_from_returns(returns)
    drawdown = abs(max_drawdown(nav))
    if drawdown == 0:
        return 0.0
    return annualized_return(returns, periods_per_year=periods_per_year) / drawdown


def sharpe_ratio(
    returns: pd.Series,
    periods_per_year: int = 252,
    risk_free_rate: float = 0.0,
) -> float:
    clean = pd.Series(returns).dropna().astype(float)
    if clean.empty:
        return 0.0
    excess = clean - risk_free_rate / periods_per_year
    vol = clean.std(ddof=0)
    if vol == 0:
        return 0.0
    return float(excess.mean() / vol * np.sqrt(periods_per_year))


def sortino_ratio(
    returns: pd.Series,
    periods_per_year: int = 252,
    risk_free_rate: float = 0.0,
) -> float:
    clean = pd.Series(returns).dropna().astype(float)
    if clean.empty:
        return 0.0
    downside = clean.where(clean < 0.0, 0.0)
    downside_std = downside.std(ddof=0)
    if downside_std == 0:
        return 0.0
    excess = clean.mean() - risk_free_rate / periods_per_year
    return float(excess / downside_std * np.sqrt(periods_per_year))


def nav_from_returns(returns: pd.Series) -> pd.Series:
    clean = pd.Series(returns).fillna(0.0).astype(float)
    nav = (1.0 + clean).cumprod()
    if not nav.empty:
        nav.iloc[0] = 1.0
    return nav


def rescale_to_score(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    clean = pd.Series(series, copy=True)
    if clean.empty:
        return clean
    valid = clean.replace([np.inf, -np.inf], np.nan)
    if valid.notna().sum() <= 1:
        return pd.Series(50.0, index=clean.index, dtype=float)
    ranks = valid.rank(pct=True, ascending=higher_is_better)
    return ranks.mul(100.0).fillna(0.0)


def compact_params(params: Mapping[str, Any]) -> str:
    return json.dumps(make_yaml_safe(dict(params)), ensure_ascii=False, sort_keys=True)


def parse_params(raw: str | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if not raw:
        return {}
    return json.loads(raw)


def write_excel(sheets: Mapping[str, pd.DataFrame], path: Path | str) -> Path:
    out = Path(path)
    ensure_dir(out.parent)
    engine_options = ("openpyxl", "xlsxwriter")
    last_error: Exception | None = None
    for engine in engine_options:
        try:
            with pd.ExcelWriter(out, engine=engine) as writer:
                for name, df in sheets.items():
                    safe_name = str(name)[:31]
                    df.to_excel(writer, sheet_name=safe_name, index=False)
            return out
        except Exception as exc:  # pragma: no cover - engine availability depends on env
            last_error = exc
    if last_error is not None:
        raise last_error
    return out


def basic_html_page(title: str, body_html: str) -> str:
    return (
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{html.escape(title)}</title>"
        "<style>"
        "body{font-family:Segoe UI,Arial,sans-serif;background:#f6f8fb;color:#1c2430;margin:0;}"
        ".page{max-width:1240px;margin:0 auto;padding:28px;}"
        ".card{background:#fff;border-radius:14px;padding:24px;margin-bottom:20px;box-shadow:0 8px 30px rgba(28,36,48,.08);}"
        "h1,h2,h3{margin:0 0 12px 0;} p{line-height:1.65;} table{border-collapse:collapse;width:100%;}"
        "th,td{padding:10px 12px;border-bottom:1px solid #e8edf4;text-align:left;font-size:14px;vertical-align:top;}"
        "th{background:#eef3f9;} code{background:#eef3f9;padding:2px 6px;border-radius:6px;}"
        "</style></head><body><div class='page'>"
        f"{body_html}</div></body></html>"
    )


def dataframe_to_html(df: pd.DataFrame, max_rows: int = 20) -> str:
    if df.empty:
        return "<p>无数据。</p>"
    clipped = df.head(max_rows).copy()
    return clipped.to_html(index=False, border=0, classes="dataframe")


def zip_selected_paths(paths: Iterable[Path | str], zip_path: Path | str, root: Path | str | None = None) -> Path:
    out = Path(zip_path)
    ensure_dir(out.parent)
    base_root = Path(root) if root is not None else PROJECT_ROOT
    with ZipFile(out, "w", compression=ZIP_DEFLATED) as zf:
        for path in paths:
            item = Path(path)
            if not item.exists():
                continue
            if item.is_dir():
                for child in item.rglob("*"):
                    if child.is_file():
                        zf.write(child, arcname=str(child.relative_to(base_root)))
            elif item.is_file():
                zf.write(item, arcname=str(item.relative_to(base_root)))
    return out
