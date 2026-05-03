"""Adapters that turn archived external factor libraries into local panels.

This module intentionally implements a conservative executable subset instead
of importing third-party research code directly.  The goal is to give quant_lab
stable ``date x asset`` factor panels that can be passed to strategy search and
backtests while keeping data-field mapping, factor lagging, and provenance
explicit.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Callable, Mapping, Sequence
from zipfile import ZipFile

import numpy as np
import pandas as pd

from src.factors.external_libraries import FACTOR_LIBRARY_ROOT


PanelMap = Mapping[str, pd.DataFrame]
FactorFunction = Callable[[dict[str, pd.DataFrame]], pd.DataFrame]


@dataclass(frozen=True)
class ExternalPanelFactorSpec:
    """Executable external price-volume factor metadata."""

    name: str
    library: str
    description: str
    required_fields: tuple[str, ...]
    direction: str = "high"


WQ_YLI188_SOURCE_PATH = FACTOR_LIBRARY_ROOT / "worldquant_alpha101_yli188" / "101Alpha_code_1.py"
JOINQUANT_SDK_ROOT = FACTOR_LIBRARY_ROOT / "joinquant_jqdatasdk"

WQ_SOURCE_ALPHA_METHODS: tuple[str, ...] = (
    "alpha001",
    "alpha002",
    "alpha003",
    "alpha004",
    "alpha005",
    "alpha006",
    "alpha007",
    "alpha008",
    "alpha009",
    "alpha010",
    "alpha011",
    "alpha012",
    "alpha013",
    "alpha014",
    "alpha015",
    "alpha016",
    "alpha017",
    "alpha018",
    "alpha019",
    "alpha020",
    "alpha021",
    "alpha022",
    "alpha023",
    "alpha024",
    "alpha025",
    "alpha026",
    "alpha027",
    "alpha028",
    "alpha029",
    "alpha030",
    "alpha031",
    "alpha032",
    "alpha033",
    "alpha034",
    "alpha035",
    "alpha036",
    "alpha037",
    "alpha038",
    "alpha039",
    "alpha040",
    "alpha041",
    "alpha042",
    "alpha043",
    "alpha044",
    "alpha045",
    "alpha046",
    "alpha047",
    "alpha049",
    "alpha050",
    "alpha051",
    "alpha052",
    "alpha053",
    "alpha054",
    "alpha055",
    "alpha057",
    "alpha060",
    "alpha061",
    "alpha062",
    "alpha064",
    "alpha065",
    "alpha066",
    "alpha068",
    "alpha071",
    "alpha072",
    "alpha073",
    "alpha074",
    "alpha075",
    "alpha077",
    "alpha078",
    "alpha081",
    "alpha083",
    "alpha084",
    "alpha085",
    "alpha086",
    "alpha088",
    "alpha092",
    "alpha094",
    "alpha095",
    "alpha096",
    "alpha098",
    "alpha099",
    "alpha101",
)

WQ_SOURCE_FACTOR_METHODS: dict[str, str] = {
    f"wq_alpha{method[-3:]}": method for method in WQ_SOURCE_ALPHA_METHODS
}

QLIB_ALPHA360_FACTOR_NAMES: tuple[str, ...] = tuple(
    f"{field}{window}"
    for field in ("CLOSE", "OPEN", "HIGH", "LOW", "VWAP", "VOLUME")
    for window in range(59, -1, -1)
)

QLIB_ALPHA360_PREFIXED_FACTOR_NAMES: tuple[str, ...] = tuple(
    f"qlib360_{name}" for name in QLIB_ALPHA360_FACTOR_NAMES
)


def _clean_panel(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out.index = pd.to_datetime(out.index)
    out = out.sort_index()
    out.columns = [str(col) for col in out.columns]
    return out.apply(pd.to_numeric, errors="coerce")


def _panel_from_single_asset_frames(
    data_by_code: Mapping[str, pd.DataFrame],
    field: str,
    index: pd.Index | None = None,
) -> pd.DataFrame:
    series: dict[str, pd.Series] = {}
    for code, data in data_by_code.items():
        cols = {str(col).strip().lower(): col for col in data.columns}
        source_col = cols.get(field)
        if source_col is None:
            continue
        s = pd.to_numeric(data[source_col], errors="coerce")
        s.index = pd.to_datetime(data.index)
        series[str(code)] = s.sort_index()
    if not series:
        return pd.DataFrame(index=index)
    panel = pd.DataFrame(series).sort_index()
    if index is not None:
        panel = panel.reindex(index)
    return panel


def ensure_ohlcv_panels(data: Mapping[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Normalize OHLCV input into a field -> date x asset panel mapping.

    Accepted inputs:

    - ``{"open": DataFrame, "high": DataFrame, ...}``
    - ``{"000001.SZ": single_asset_ohlcv_df, ...}``
    """

    field_names = {"open", "high", "low", "close", "volume", "amount", "vwap"}
    lower_keys = {str(key).lower(): key for key in data}

    if "close" in lower_keys and isinstance(data[lower_keys["close"]], pd.DataFrame):
        panels = {
            field: _clean_panel(data[lower_keys[field]])
            for field in field_names
            if field in lower_keys
        }
    else:
        close = _panel_from_single_asset_frames(data, "close")
        panels = {"close": close}
        for field in ("open", "high", "low", "volume", "amount", "vwap"):
            panels[field] = _panel_from_single_asset_frames(data, field, index=close.index)

    close = panels.get("close", pd.DataFrame())
    if close.empty:
        raise ValueError("OHLCV panels require a non-empty close panel.")

    for field in ("open", "high", "low"):
        if field not in panels or panels[field].empty:
            panels[field] = close.copy()
        else:
            panels[field] = panels[field].reindex(index=close.index, columns=close.columns)

    if "volume" not in panels or panels["volume"].empty:
        panels["volume"] = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    else:
        panels["volume"] = panels["volume"].reindex(index=close.index, columns=close.columns)

    if "amount" in panels and not panels["amount"].empty:
        panels["amount"] = panels["amount"].reindex(index=close.index, columns=close.columns)
    else:
        panels["amount"] = panels["close"] * panels["volume"]

    if "vwap" in panels and not panels["vwap"].empty:
        panels["vwap"] = panels["vwap"].reindex(index=close.index, columns=close.columns)
    else:
        amount = panels["amount"]
        volume = panels["volume"].replace(0, np.nan)
        typical = (panels["open"] + panels["high"] + panels["low"] + panels["close"]) / 4.0
        panels["vwap"] = amount.div(volume).where(amount.notna() & volume.notna(), typical)

    panels["returns"] = panels["close"].pct_change(fill_method=None)
    return panels


def _load_wq_yli188_module():
    if not WQ_YLI188_SOURCE_PATH.exists():
        raise FileNotFoundError(WQ_YLI188_SOURCE_PATH)
    if not hasattr(pd.DataFrame, "as_matrix"):
        pd.DataFrame.as_matrix = pd.DataFrame.to_numpy  # type: ignore[attr-defined]
    spec = importlib.util.spec_from_file_location("quant_lab_wq_yli188_alpha101", WQ_YLI188_SOURCE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {WQ_YLI188_SOURCE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _joinquant_alpha_file(kind: str) -> Path:
    if kind not in {"alpha101", "alpha191"}:
        raise ValueError("kind must be 'alpha101' or 'alpha191'")
    return JOINQUANT_SDK_ROOT / "jqdatasdk" / f"{kind}.py"


def list_joinquant_api_factors(kind: str) -> tuple[str, ...]:
    """List archived JoinQuant API alpha function names without calling the API."""

    path = _joinquant_alpha_file(kind)
    if not path.exists():
        return tuple()
    text = path.read_text(encoding="utf-8", errors="ignore")
    names = sorted(set(re.findall(r"^def (alpha_\d{3})\(", text, flags=re.MULTILINE)))
    return tuple(names)


def _import_archived_joinquant_module(kind: str):
    if str(JOINQUANT_SDK_ROOT) not in sys.path:
        sys.path.insert(0, str(JOINQUANT_SDK_ROOT))
    return __import__(f"jqdatasdk.{kind}", fromlist=["*"])


def call_joinquant_alpha101_api(factor_name: str, enddate, index: str = "all"):
    """Call an archived JoinQuant Alpha101 API wrapper.

    This requires valid JoinQuant authentication.  The function exists so the
    archived SDK is a reusable entry point instead of a passive download.
    """

    module = _import_archived_joinquant_module("alpha101")
    if not hasattr(module, factor_name):
        raise KeyError(f"JoinQuant alpha101 factor not found: {factor_name}")
    return getattr(module, factor_name)(enddate=enddate, index=index)


def call_joinquant_alpha191_api(factor_name: str, code, end_date=None, fq: str = "pre"):
    """Call an archived JoinQuant Alpha191 API wrapper.

    This requires valid JoinQuant authentication.
    """

    module = _import_archived_joinquant_module("alpha191")
    if not hasattr(module, factor_name):
        raise KeyError(f"JoinQuant alpha191 factor not found: {factor_name}")
    return getattr(module, factor_name)(code=code, end_date=end_date, fq=fq)


def _source_panels_for_yli188(panels: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    close = panels["close"]
    volume = panels["volume"]
    return {
        "S_DQ_OPEN": panels["open"],
        "S_DQ_HIGH": panels["high"],
        "S_DQ_LOW": panels["low"],
        "S_DQ_CLOSE": close,
        "S_DQ_VOLUME": volume / 100.0,
        "S_DQ_AMOUNT": panels["amount"] / 1000.0,
        "S_DQ_PCTCHANGE": panels["returns"],
    }


def _source_single_asset_for_yli188(
    panels: dict[str, pd.DataFrame],
    column: str,
) -> dict[str, pd.Series]:
    source = _source_panels_for_yli188(panels)
    return {key: frame[column] for key, frame in source.items()}


def _normalize_source_alpha_result(
    value: pd.DataFrame | pd.Series,
    index: pd.Index,
    columns: pd.Index,
    preferred_column: str | None = None,
) -> pd.DataFrame:
    if isinstance(value, pd.Series):
        name = preferred_column or value.name or "value"
        return pd.DataFrame({str(name): value}).reindex(index=index)
    if isinstance(value, pd.DataFrame):
        out = value.copy()
        out.index = pd.to_datetime(out.index)
        if len(out.columns) == 1 and preferred_column is not None:
            out.columns = [preferred_column]
        return out.reindex(index=index, columns=columns)
    raise TypeError(f"Unsupported alpha result type: {type(value)!r}")


def _compute_wq_source_alpha(
    panels: dict[str, pd.DataFrame],
    factor_name: str,
) -> pd.DataFrame:
    method_name = WQ_SOURCE_FACTOR_METHODS[factor_name]
    module = _load_wq_yli188_module()
    source_data = _source_panels_for_yli188(panels)
    alpha_obj = module.Alphas(source_data)
    method = getattr(alpha_obj, method_name)
    try:
        return _sanitize(
            _normalize_source_alpha_result(
                method(),
                index=panels["close"].index,
                columns=panels["close"].columns,
            )
        )
    except Exception as panel_error:
        per_asset: list[pd.Series] = []
        errors: dict[str, str] = {}
        for column in panels["close"].columns:
            try:
                single_obj = module.Alphas(_source_single_asset_for_yli188(panels, str(column)))
                single_value = getattr(single_obj, method_name)()
                normalized = _normalize_source_alpha_result(
                    single_value,
                    index=panels["close"].index,
                    columns=pd.Index([str(column)]),
                    preferred_column=str(column),
                )
                per_asset.append(normalized[str(column)])
            except Exception as exc:  # pragma: no cover - reported to caller.
                errors[str(column)] = f"{type(exc).__name__}: {exc}"
        if per_asset:
            return _sanitize(pd.concat(per_asset, axis=1).reindex(columns=panels["close"].columns))
        sample_errors = "; ".join(f"{k}: {v}" for k, v in list(errors.items())[:3])
        raise RuntimeError(
            f"Source-backed {factor_name} failed. Panel error: {type(panel_error).__name__}: {panel_error}. "
            f"Per-asset errors: {sample_errors}"
        ) from panel_error


def _sanitize(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.replace([np.inf, -np.inf], np.nan)


def _safe_div(numerator: pd.DataFrame, denominator: pd.DataFrame | pd.Series | float) -> pd.DataFrame:
    return _sanitize(numerator.div(denominator).replace([np.inf, -np.inf], np.nan))


def _cs_rank(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.rank(axis=1, pct=True)


def _ts_sum(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    return frame.rolling(window, min_periods=window).sum()


def _ts_mean(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    return frame.rolling(window, min_periods=window).mean()


def _ts_std(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    return frame.rolling(window, min_periods=window).std()


def _ts_min(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    return frame.rolling(window, min_periods=window).min()


def _ts_max(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    return frame.rolling(window, min_periods=window).max()


def _rolling_corr(left: pd.DataFrame, right: pd.DataFrame, window: int) -> pd.DataFrame:
    return _sanitize(left.rolling(window, min_periods=window).corr(right))


def _rolling_cov(left: pd.DataFrame, right: pd.DataFrame, window: int) -> pd.DataFrame:
    return _sanitize(left.rolling(window, min_periods=window).cov(right))


def _last_rank_pct(values: np.ndarray) -> float:
    valid = ~np.isnan(values)
    if not valid[-1] or valid.sum() == 0:
        return np.nan
    ranks = pd.Series(values[valid]).rank(pct=True)
    return float(ranks.iloc[-1])


def _ts_rank(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    return frame.rolling(window, min_periods=window).apply(_last_rank_pct, raw=True)


def _nan_argmax(values: np.ndarray) -> float:
    if np.isnan(values).all():
        return np.nan
    return float(np.nanargmax(values) + 1)


def _ts_argmax(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    return frame.rolling(window, min_periods=window).apply(_nan_argmax, raw=True)


def _decay_linear(frame: pd.DataFrame, period: int) -> pd.DataFrame:
    weights = np.arange(1, period + 1, dtype=float)
    weights = weights / weights.sum()
    values = frame.astype(float).ffill().bfill().fillna(0.0)
    return values.rolling(period, min_periods=period).apply(lambda x: float(np.dot(x, weights)), raw=True)


def _panel_max(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        np.maximum(left.to_numpy(dtype=float), right.to_numpy(dtype=float)),
        index=left.index,
        columns=left.columns,
    )


def _panel_min(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        np.minimum(left.to_numpy(dtype=float), right.to_numpy(dtype=float)),
        index=left.index,
        columns=left.columns,
    )


def _choose(mask: pd.DataFrame, left: pd.DataFrame | float, right: pd.DataFrame | float) -> pd.DataFrame:
    left_frame = left if isinstance(left, pd.DataFrame) else pd.DataFrame(left, index=mask.index, columns=mask.columns)
    right_frame = right if isinstance(right, pd.DataFrame) else pd.DataFrame(right, index=mask.index, columns=mask.columns)
    return left_frame.where(mask, right_frame)


def _signed_power(frame: pd.DataFrame, exponent: float) -> pd.DataFrame:
    return np.sign(frame) * frame.abs().pow(exponent)


def _alpha101_001(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    x = p["close"].where(p["returns"] >= 0, _ts_std(p["returns"], 20))
    return _cs_rank(_ts_argmax(_signed_power(x, 2.0), 5)) - 0.5


def _alpha101_002(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    volume_log_delta = np.log(p["volume"].where(p["volume"] > 0)).diff(2)
    intraday = _safe_div(p["close"] - p["open"], p["open"])
    return -_rolling_corr(_cs_rank(volume_log_delta), _cs_rank(intraday), 6)


def _alpha101_003(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return -_rolling_corr(_cs_rank(p["open"]), _cs_rank(p["volume"]), 10)


def _alpha101_004(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return -_ts_rank(_cs_rank(p["low"]), 9)


def _alpha101_005(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    left = _cs_rank(p["open"] - _ts_mean(p["vwap"], 10))
    right = -_cs_rank((p["close"] - p["vwap"]).abs())
    return left * right


def _alpha101_006(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return -_rolling_corr(p["open"], p["volume"], 10)


def _alpha101_007(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    adv20 = _ts_mean(p["volume"], 20)
    delta7 = p["close"].diff(7)
    active = -_ts_rank(delta7.abs(), 60) * np.sign(delta7)
    return active.where(adv20 < p["volume"], -1.0)


def _alpha101_008(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    raw = _ts_sum(p["open"], 5) * _ts_sum(p["returns"], 5)
    return -_cs_rank(raw - raw.shift(10))


def _alpha101_009(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    delta1 = p["close"].diff(1)
    same_direction = (_ts_min(delta1, 5) > 0) | (_ts_max(delta1, 5) < 0)
    return delta1.where(same_direction, -delta1)


def _alpha101_010(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return _cs_rank(_alpha101_009(p))


def _alpha101_012(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return np.sign(p["volume"].diff(1)) * (-p["close"].diff(1))


def _alpha101_013(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return -_cs_rank(_rolling_cov(_cs_rank(p["close"]), _cs_rank(p["volume"]), 5))


def _alpha101_014(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return -_cs_rank(p["returns"].diff(3)) * _rolling_corr(p["open"], p["volume"], 10)


def _alpha101_015(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    corr = _rolling_corr(_cs_rank(p["high"]), _cs_rank(p["volume"]), 3)
    return -_ts_sum(_cs_rank(corr), 3)


def _alpha101_016(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return -_cs_rank(_rolling_cov(_cs_rank(p["high"]), _cs_rank(p["volume"]), 5))


def _alpha101_017(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    adv20 = _ts_mean(p["volume"], 20)
    return -(
        _cs_rank(_ts_rank(p["close"], 10))
        * _cs_rank(p["close"].diff(1).diff(1))
        * _cs_rank(_ts_rank(_safe_div(p["volume"], adv20), 5))
    )


def _alpha101_020(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return -(
        _cs_rank(p["open"] - p["high"].shift(1))
        * _cs_rank(p["open"] - p["close"].shift(1))
        * _cs_rank(p["open"] - p["low"].shift(1))
    )


def _alpha101_025(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    adv20 = _ts_mean(p["volume"], 20)
    raw = (-p["returns"]) * adv20 * p["vwap"] * (p["high"] - p["close"])
    return _cs_rank(raw)


def _alpha101_023(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return (-p["high"].diff(2)).where(_ts_mean(p["high"], 20) < p["high"], 0.0)


def _alpha101_071(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    adv180 = _ts_mean(p["volume"], 180)
    p1 = _ts_rank(_decay_linear(_rolling_corr(_ts_rank(p["close"], 3), _ts_rank(adv180, 12), 18), 4), 16)
    p2 = _ts_rank(_decay_linear(_cs_rank(((p["low"] + p["open"]) - (p["vwap"] + p["vwap"])).pow(2)), 16), 4)
    return _panel_max(p1, p2)


def _alpha101_073(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    p1 = _cs_rank(_decay_linear(p["vwap"].diff(5), 3))
    base = p["open"] * 0.147155 + p["low"] * (1 - 0.147155)
    p2 = _ts_rank(_decay_linear(_safe_div(base.diff(2), base) * -1.0, 3), 17)
    return -_panel_max(p1, p2)


def _alpha101_077(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    adv40 = _ts_mean(p["volume"], 40)
    p1 = _cs_rank(_decay_linear((((p["high"] + p["low"]) / 2.0) + p["high"]) - (p["vwap"] + p["high"]), 20))
    p2 = _cs_rank(_decay_linear(_rolling_corr((p["high"] + p["low"]) / 2.0, adv40, 3), 6))
    return _panel_min(p1, p2)


def _alpha101_088(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    adv60 = _ts_mean(p["volume"], 60)
    p1 = _cs_rank(
        _decay_linear(
            (_cs_rank(p["open"]) + _cs_rank(p["low"])) - (_cs_rank(p["high"]) + _cs_rank(p["close"])),
            8,
        )
    )
    p2 = _ts_rank(_decay_linear(_rolling_corr(_ts_rank(p["close"], 8), _ts_rank(adv60, 21), 8), 7), 3)
    return _panel_min(p1, p2)


def _alpha101_092(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    adv30 = _ts_mean(p["volume"], 30)
    p1 = _ts_rank(_decay_linear(((((p["high"] + p["low"]) / 2.0) + p["close"]) < (p["low"] + p["open"])).astype(float), 15), 19)
    p2 = _ts_rank(_decay_linear(_rolling_corr(_cs_rank(p["low"]), _cs_rank(adv30), 8), 7), 7)
    return _panel_min(p1, p2)


def _alpha101_096(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    adv60 = _ts_mean(p["volume"], 60)
    p1 = _ts_rank(_decay_linear(_rolling_corr(_cs_rank(p["vwap"]), _cs_rank(p["volume"]), 4), 4), 8)
    p2_raw = _ts_argmax(_rolling_corr(_ts_rank(p["close"], 7), _ts_rank(adv60, 4), 4), 13)
    p2 = _ts_rank(_decay_linear(p2_raw, 14), 13)
    return -_panel_max(p1, p2)


def _alpha101_101(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return _safe_div(p["close"] - p["open"], (p["high"] - p["low"]).replace(0, np.nan) + 0.001)


def _qlib360_feature(p: dict[str, pd.DataFrame], name: str) -> pd.DataFrame:
    raw = name.removeprefix("qlib360_")
    field = "".join(ch for ch in raw if ch.isalpha()).lower()
    lag_text = "".join(ch for ch in raw if ch.isdigit())
    if field not in {"close", "open", "high", "low", "vwap", "volume"} or lag_text == "":
        raise KeyError(f"Unsupported Qlib Alpha360 feature name: {name}")
    lag = int(lag_text)
    if field == "volume":
        return _safe_div(p["volume"].shift(lag), p["volume"] + 1e-12)
    return _safe_div(p[field].shift(lag), p["close"])


def _gtja_001(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    volume_log_delta = np.log(p["volume"].where(p["volume"] > 0)).diff(1)
    intraday = _safe_div(p["close"] - p["open"], p["open"])
    return -_rolling_corr(_cs_rank(volume_log_delta), _cs_rank(intraday), 6)


def _gtja_002(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    close_location = _safe_div((p["close"] - p["low"]) - (p["high"] - p["close"]), p["high"] - p["low"])
    return -close_location.diff(1)


def _gtja_003(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    prev_close = p["close"].shift(1)
    low_or_prev = pd.DataFrame(
        np.minimum(p["low"].to_numpy(dtype=float), prev_close.to_numpy(dtype=float)),
        index=p["close"].index,
        columns=p["close"].columns,
    )
    high_or_prev = pd.DataFrame(
        np.maximum(p["high"].to_numpy(dtype=float), prev_close.to_numpy(dtype=float)),
        index=p["close"].index,
        columns=p["close"].columns,
    )
    up_part = p["close"] - low_or_prev
    down_part = p["close"] - high_or_prev
    raw = _choose(p["close"] > prev_close, up_part, _choose(p["close"] < prev_close, down_part, 0.0))
    return _ts_sum(raw, 6)


def _gtja_004(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    mean8 = _ts_mean(p["close"], 8)
    std8 = _ts_std(p["close"], 8)
    mean2 = _ts_mean(p["close"], 2)
    volume_ratio = _safe_div(p["volume"], _ts_mean(p["volume"], 20))
    base = pd.DataFrame(-1.0, index=p["close"].index, columns=p["close"].columns)
    base = base.where(~(volume_ratio >= 1), 1.0)
    base = base.where(~(mean2 < mean8 - std8), 1.0)
    base = base.where(~(mean8 + std8 < mean2), -1.0)
    return base


def _gtja_005(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    corr = _rolling_corr(_ts_rank(p["volume"], 5), _ts_rank(p["high"], 5), 5)
    return -_ts_max(corr, 3)


def _gtja_006(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    weighted_price = p["open"] * 0.85 + p["high"] * 0.15
    return -_cs_rank(np.sign(weighted_price.diff(4)))


def _gtja_007(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    spread = p["vwap"] - p["close"]
    return _cs_rank(_ts_max(spread, 3)) + _cs_rank(_ts_min(spread, 3)) * _cs_rank(p["volume"].diff(3))


def _gtja_008(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    weighted_price = (p["high"] + p["low"]) * 0.1 + p["vwap"] * 0.8
    return -_cs_rank(weighted_price.diff(4))


def _gtja_009(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    mid = (p["high"] + p["low"]) / 2.0
    raw = _safe_div((mid - mid.shift(1)) * (p["high"] - p["low"]), p["volume"].replace(0, np.nan))
    return raw.ewm(alpha=2 / 8, adjust=False, min_periods=7).mean()


def _gtja_010(p: dict[str, pd.DataFrame]) -> pd.DataFrame:
    x = p["close"].where(p["returns"] >= 0, _ts_std(p["returns"], 20))
    return _cs_rank(_ts_max(_signed_power(x, 2.0), 5))


ALPHA101_FACTOR_FUNCTIONS: dict[str, FactorFunction] = {
    "wq_alpha001": _alpha101_001,
    "wq_alpha002": _alpha101_002,
    "wq_alpha003": _alpha101_003,
    "wq_alpha004": _alpha101_004,
    "wq_alpha005": _alpha101_005,
    "wq_alpha006": _alpha101_006,
    "wq_alpha007": _alpha101_007,
    "wq_alpha008": _alpha101_008,
    "wq_alpha009": _alpha101_009,
    "wq_alpha010": _alpha101_010,
    "wq_alpha012": _alpha101_012,
    "wq_alpha013": _alpha101_013,
    "wq_alpha014": _alpha101_014,
    "wq_alpha015": _alpha101_015,
    "wq_alpha016": _alpha101_016,
    "wq_alpha017": _alpha101_017,
    "wq_alpha020": _alpha101_020,
    "wq_alpha023": _alpha101_023,
    "wq_alpha025": _alpha101_025,
    "wq_alpha071": _alpha101_071,
    "wq_alpha073": _alpha101_073,
    "wq_alpha077": _alpha101_077,
    "wq_alpha088": _alpha101_088,
    "wq_alpha092": _alpha101_092,
    "wq_alpha096": _alpha101_096,
    "wq_alpha101": _alpha101_101,
}


GTJA191_FACTOR_FUNCTIONS: dict[str, FactorFunction] = {
    "gtja_alpha001": _gtja_001,
    "gtja_alpha002": _gtja_002,
    "gtja_alpha003": _gtja_003,
    "gtja_alpha004": _gtja_004,
    "gtja_alpha005": _gtja_005,
    "gtja_alpha006": _gtja_006,
    "gtja_alpha007": _gtja_007,
    "gtja_alpha008": _gtja_008,
    "gtja_alpha009": _gtja_009,
    "gtja_alpha010": _gtja_010,
}


EXTERNAL_PANEL_FACTOR_SPECS: dict[str, ExternalPanelFactorSpec] = {
    **{
        name: ExternalPanelFactorSpec(
            name=name,
            library="worldquant_alpha101",
            description=f"Source-backed WorldQuant Alpha101 formula {name[-3:]} from archived yli188 implementation.",
            required_fields=("open", "high", "low", "close", "volume", "amount"),
        )
        for name in WQ_SOURCE_FACTOR_METHODS
    },
    **{
        name: ExternalPanelFactorSpec(
            name=name,
            library="worldquant_alpha101",
            description=f"Executable quant_lab adapter for WorldQuant Alpha101 formula {name[-3:]}.",
            required_fields=("open", "high", "low", "close", "volume"),
        )
        for name in ALPHA101_FACTOR_FUNCTIONS
    },
    **{
        name: ExternalPanelFactorSpec(
            name=name,
            library="alpha360_qlib",
            description=f"Local Qlib Alpha360 feature {name.removeprefix('qlib360_')}.",
            required_fields=("open", "high", "low", "close", "volume"),
            direction="unknown",
        )
        for name in QLIB_ALPHA360_PREFIXED_FACTOR_NAMES
    },
    **{
        name: ExternalPanelFactorSpec(
            name=name,
            library="gtja_alpha191",
            description=f"Executable quant_lab adapter for GTJA Alpha191 formula subset {name[-3:]}.",
            required_fields=("open", "high", "low", "close", "volume"),
        )
        for name in GTJA191_FACTOR_FUNCTIONS
    },
}


def list_external_panel_factors(library: str | None = None) -> list[str]:
    """List executable external price-volume factor names."""

    names = sorted(EXTERNAL_PANEL_FACTOR_SPECS)
    if library is None:
        return names
    return [name for name in names if EXTERNAL_PANEL_FACTOR_SPECS[name].library == library]


def compute_alpha101_factor_panels(
    data: Mapping[str, pd.DataFrame],
    factor_names: Sequence[str] | None = None,
) -> dict[str, pd.DataFrame]:
    """Compute executable WorldQuant Alpha101 subset panels."""

    panels = ensure_ohlcv_panels(data)
    selected = list(factor_names) if factor_names is not None else sorted(WQ_SOURCE_FACTOR_METHODS)
    results: dict[str, pd.DataFrame] = {}
    for name in selected:
        if name in ALPHA101_FACTOR_FUNCTIONS:
            results[name] = _sanitize(ALPHA101_FACTOR_FUNCTIONS[name](panels))
        elif name in WQ_SOURCE_FACTOR_METHODS:
            results[name] = _compute_wq_source_alpha(panels, name)
    return results


def compute_gtja191_factor_panels(
    data: Mapping[str, pd.DataFrame],
    factor_names: Sequence[str] | None = None,
) -> dict[str, pd.DataFrame]:
    """Compute executable GTJA Alpha191 subset panels."""

    panels = ensure_ohlcv_panels(data)
    selected = list(factor_names) if factor_names is not None else sorted(GTJA191_FACTOR_FUNCTIONS)
    return {
        name: _sanitize(GTJA191_FACTOR_FUNCTIONS[name](panels))
        for name in selected
        if name in GTJA191_FACTOR_FUNCTIONS
    }


def compute_external_price_volume_factor_panels(
    data: Mapping[str, pd.DataFrame],
    factor_names: Sequence[str],
) -> dict[str, pd.DataFrame]:
    """Compute any supported external price-volume factor panels by name."""

    panels = ensure_ohlcv_panels(data)
    results: dict[str, pd.DataFrame] = {}
    functions = {**ALPHA101_FACTOR_FUNCTIONS, **GTJA191_FACTOR_FUNCTIONS}
    known_names = set(functions) | set(WQ_SOURCE_FACTOR_METHODS) | set(QLIB_ALPHA360_PREFIXED_FACTOR_NAMES)
    unknown = [name for name in factor_names if name not in known_names]
    if unknown:
        known = ", ".join(sorted(known_names))
        raise KeyError(f"Unsupported external factor(s): {unknown}. Known factors: {known}")
    for name in factor_names:
        if name in functions:
            results[name] = _sanitize(functions[name](panels))
        elif name in WQ_SOURCE_FACTOR_METHODS:
            results[name] = _compute_wq_source_alpha(panels, name)
        elif name in QLIB_ALPHA360_PREFIXED_FACTOR_NAMES:
            results[name] = _sanitize(_qlib360_feature(panels, name))
    return results


def compute_qlib_alpha360_factor_panels(
    data: Mapping[str, pd.DataFrame],
    factor_names: Sequence[str] | None = None,
) -> dict[str, pd.DataFrame]:
    """Compute Qlib Alpha360 local feature panels.

    Names use the ``qlib360_`` prefix to avoid collisions with other factor
    libraries, for example ``qlib360_CLOSE59`` or ``qlib360_VOLUME0``.
    """

    panels = ensure_ohlcv_panels(data)
    selected = list(factor_names) if factor_names is not None else list(QLIB_ALPHA360_PREFIXED_FACTOR_NAMES)
    unknown = [name for name in selected if name not in QLIB_ALPHA360_PREFIXED_FACTOR_NAMES]
    if unknown:
        raise KeyError(f"Unsupported Qlib Alpha360 feature(s): {unknown}")
    return {name: _sanitize(_qlib360_feature(panels, name)) for name in selected}


def probe_worldquant_source_alpha_status(
    data: Mapping[str, pd.DataFrame],
    factor_names: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Return a runtime status table for archived source-backed Alpha101 factors."""

    selected = list(factor_names) if factor_names is not None else sorted(WQ_SOURCE_FACTOR_METHODS)
    rows: list[dict[str, object]] = []
    for name in selected:
        try:
            panel = compute_external_price_volume_factor_panels(data, [name])[name]
            rows.append(
                {
                    "factor": name,
                    "status": "ok",
                    "rows": int(panel.shape[0]),
                    "columns": int(panel.shape[1]),
                    "non_na": int(panel.notna().sum().sum()),
                    "error": "",
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "factor": name,
                    "status": "failed",
                    "rows": 0,
                    "columns": 0,
                    "non_na": 0,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return pd.DataFrame(rows)


FAMA_FRENCH_FILES = {
    ("3_factor", "monthly"): "F-F_Research_Data_Factors_CSV.zip",
    ("3_factor", "daily"): "F-F_Research_Data_Factors_daily_CSV.zip",
    ("5_factor", "monthly"): "F-F_Research_Data_5_Factors_2x3_CSV.zip",
    ("5_factor", "daily"): "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip",
    ("momentum", "monthly"): "F-F_Momentum_Factor_CSV.zip",
    ("momentum", "daily"): "F-F_Momentum_Factor_daily_CSV.zip",
}


def _parse_fama_french_date(raw: str, frequency: str) -> pd.Timestamp:
    value = str(raw).strip()
    if frequency == "monthly":
        return pd.to_datetime(value + "01", format="%Y%m%d") + pd.offsets.MonthEnd(0)
    return pd.to_datetime(value, format="%Y%m%d")


def load_fama_french_factors(
    model: str = "5_factor",
    frequency: str = "daily",
    root: Path | None = None,
    percent_to_decimal: bool = True,
) -> pd.DataFrame:
    """Load an archived Kenneth French factor file.

    Parameters
    ----------
    model:
        One of ``"3_factor"``, ``"5_factor"``, or ``"momentum"``.
    frequency:
        ``"daily"`` or ``"monthly"``.
    percent_to_decimal:
        French library values are percentages.  Keep the default ``True`` to
        return decimal returns suitable for regressions/backtests.
    """

    key = (model, frequency)
    if key not in FAMA_FRENCH_FILES:
        raise KeyError(f"Unsupported Fama-French file key: {key}")

    base = root or FACTOR_LIBRARY_ROOT / "fama_french"
    zip_path = base / FAMA_FRENCH_FILES[key]
    if not zip_path.exists():
        raise FileNotFoundError(zip_path)

    with ZipFile(zip_path) as zf:
        inner_name = zf.namelist()[0]
        text = zf.read(inner_name).decode("latin1")

    lines = text.splitlines()
    header_idx = next(i for i, line in enumerate(lines) if line.startswith(","))
    data_lines = [lines[header_idx]]
    for line in lines[header_idx + 1 :]:
        first = line.split(",", 1)[0].strip()
        if not first.isdigit():
            break
        data_lines.append(line)

    df = pd.read_csv(StringIO("\n".join(data_lines)))
    date_col = df.columns[0]
    df = df.rename(columns={date_col: "date"})
    df["date"] = df["date"].map(lambda value: _parse_fama_french_date(value, frequency))
    df = df.set_index("date").sort_index()
    df.columns = [
        str(col).strip().lower().replace("-", "_").replace(" ", "_")
        for col in df.columns
    ]
    df = df.apply(pd.to_numeric, errors="coerce").replace([-99.99, -999.0], np.nan)
    if percent_to_decimal:
        df = df / 100.0
    return df


def load_combined_fama_french_factors(
    frequency: str = "daily",
    include_momentum: bool = True,
    root: Path | None = None,
) -> pd.DataFrame:
    """Load 5-factor data and optionally append momentum."""

    factors = load_fama_french_factors("5_factor", frequency, root=root)
    if include_momentum:
        momentum = load_fama_french_factors("momentum", frequency, root=root)
        factors = factors.join(momentum, how="left")
    return factors


def align_fama_french_to_index(
    index: pd.Index,
    frequency: str = "daily",
    include_momentum: bool = True,
    root: Path | None = None,
) -> pd.DataFrame:
    """Align Fama-French time-series factors to a local trading-date index."""

    target_index = pd.to_datetime(index)
    factors = load_combined_fama_french_factors(frequency=frequency, include_momentum=include_momentum, root=root)
    return factors.reindex(target_index).ffill()
