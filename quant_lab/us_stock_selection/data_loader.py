"""Local-first US market data loading and quality checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.utils import PROJECT_ROOT, ensure_dir


CANONICAL_COLUMNS = [
    "date",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "dividends",
    "splits",
]


@dataclass(frozen=True)
class TickerLoadResult:
    ticker: str
    path: Path | None
    data: pd.DataFrame
    source: str
    downloaded: bool = False


class USDataLoader:
    """Load OHLCV data for US symbols, preferring existing local files."""

    def __init__(self, config: dict[str, Any], env_config: dict[str, Any], logger):
        self.config = config
        self.env_config = env_config
        self.logger = logger
        self.raw_data_dir = PROJECT_ROOT / "data" / "raw" / "us" / "us_stock_selection"
        self.raw_data_dir.mkdir(parents=True, exist_ok=True)

        env_paths = env_config.get("paths", {})
        legacy_nsdq_root = PROJECT_ROOT / Path(env_paths.get("legacy_nsdq", "./data/external/legacy_quant/NSDQStock"))
        legacy_candidates = [path for path in legacy_nsdq_root.iterdir() if path.is_dir()] if legacy_nsdq_root.exists() else []
        self.search_dirs = [
            self.raw_data_dir,
            PROJECT_ROOT / "data" / "raw" / "us",
            *sorted(legacy_candidates, reverse=True),
        ]

    def available_local_tickers(self) -> set[str]:
        tickers: set[str] = set()
        for directory in self.search_dirs:
            if not directory.exists():
                continue
            for path in directory.glob("*.csv"):
                tickers.add(path.stem.upper())
        return tickers

    def load_many(
        self,
        tickers: list[str],
        start_date: str | None = None,
        end_date: str | None = None,
        allow_download: bool | None = None,
    ) -> dict[str, TickerLoadResult]:
        results: dict[str, TickerLoadResult] = {}
        for ticker in tickers:
            results[ticker] = self.load_ticker(
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                allow_download=allow_download,
            )
        return results

    def load_ticker(
        self,
        ticker: str,
        start_date: str | None = None,
        end_date: str | None = None,
        allow_download: bool | None = None,
    ) -> TickerLoadResult:
        symbol = str(ticker).upper()
        allow_download = (
            self.config.get("data", {}).get("allow_download", False)
            if allow_download is None
            else allow_download
        )

        local_file = self._find_local_file(symbol)
        if local_file is not None:
            frame = self._read_csv(local_file)
            return TickerLoadResult(
                ticker=symbol,
                path=local_file,
                data=self._clip_dates(frame, start_date, end_date),
                source="local",
            )

        if allow_download:
            downloaded = self._download_yfinance(symbol, start_date=start_date, end_date=end_date)
            if downloaded is not None:
                frame = self._read_csv(downloaded)
                return TickerLoadResult(
                    ticker=symbol,
                    path=downloaded,
                    data=self._clip_dates(frame, start_date, end_date),
                    source="yfinance",
                    downloaded=True,
                )

        self.logger.warning(f"Ticker {symbol} not found in local data roots and download disabled.")
        return TickerLoadResult(ticker=symbol, path=None, data=pd.DataFrame(columns=CANONICAL_COLUMNS), source="missing")

    def to_panel(self, loaded: dict[str, TickerLoadResult], field: str) -> pd.DataFrame:
        panels = {}
        for ticker, result in loaded.items():
            if result.data.empty or field not in result.data.columns:
                continue
            panels[ticker] = result.data[field]
        if not panels:
            return pd.DataFrame()
        panel = pd.DataFrame(panels).sort_index()
        panel.index.name = "date"
        return panel

    def build_data_quality_reports(
        self,
        loaded: dict[str, TickerLoadResult],
        universe_metadata: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        quality_cfg = self.config.get("data_quality", {})
        min_obs = int(quality_cfg.get("min_observations", 750))
        max_missing_rate = float(quality_cfg.get("max_missing_rate", 0.05))
        abnormal_return_threshold = float(quality_cfg.get("abnormal_return_threshold", 0.8))
        min_avg_dollar_volume = float(quality_cfg.get("min_average_dollar_volume", 5_000_000))
        max_zero_volume_ratio = float(quality_cfg.get("max_zero_volume_ratio", 0.1))

        rows: list[dict[str, Any]] = []
        detail_rows: list[dict[str, Any]] = []

        metadata_map = universe_metadata.set_index("ticker").to_dict(orient="index") if not universe_metadata.empty else {}

        for ticker, result in loaded.items():
            frame = result.data.copy()
            meta = metadata_map.get(ticker, {})
            if frame.empty:
                rows.append(
                    {
                        "ticker": ticker,
                        "source": result.source,
                        "path": str(result.path) if result.path else "",
                        "start_date": None,
                        "end_date": None,
                        "observations": 0,
                        "missing_rate": 1.0,
                        "abnormal_price_count": 0,
                        "abnormal_return_count": 0,
                        "split_like_count": 0,
                        "possible_adjustment_issue": True,
                        "average_dollar_volume": 0.0,
                        "zero_volume_ratio": 1.0,
                        "has_adj_close": False,
                        "meets_min_length": False,
                        "passes_missing_check": False,
                        "passes_liquidity_check": False,
                        "passes_anomaly_check": False,
                        "passes_quality": False,
                        "is_leveraged": bool(meta.get("is_leveraged", False)),
                        "asset_type": meta.get("asset_type", ""),
                    }
                )
                detail_rows.append(
                    {
                        "ticker": ticker,
                        "check_name": "data_exists",
                        "check_value": False,
                        "threshold": "must_exist",
                        "passed": False,
                        "message": "No local data was found.",
                    }
                )
                continue

            returns = frame["close"].pct_change(fill_method=None)
            missing_rate = float(frame[["open", "high", "low", "close", "volume"]].isna().mean().mean())
            abnormal_price_count = int(
                (
                    frame[["open", "high", "low", "close"]] <= 0
                ).sum().sum()
            )
            abnormal_return_count = int(returns.abs().gt(abnormal_return_threshold).sum())
            split_like_count = int(returns.abs().gt(0.4).sum())
            average_dollar_volume = float((frame["close"] * frame["volume"]).rolling(20).mean().dropna().mean() or 0.0)
            zero_volume_ratio = float(frame["volume"].fillna(0).eq(0).mean())
            has_adj_close = bool(frame["adj_close"].notna().any())
            possible_adjustment_issue = bool(split_like_count > 0 and frame["splits"].fillna(0).eq(0).all())
            meets_min_length = int(len(frame)) >= min_obs
            passes_missing_check = missing_rate <= max_missing_rate
            passes_liquidity_check = average_dollar_volume >= min_avg_dollar_volume and zero_volume_ratio <= max_zero_volume_ratio
            passes_anomaly_check = abnormal_price_count == 0 and abnormal_return_count <= max(3, int(len(frame) * 0.01))
            passes_quality = all([meets_min_length, passes_missing_check, passes_liquidity_check, passes_anomaly_check])

            rows.append(
                {
                    "ticker": ticker,
                    "source": result.source,
                    "path": str(result.path) if result.path else "",
                    "start_date": frame.index.min().date().isoformat(),
                    "end_date": frame.index.max().date().isoformat(),
                    "observations": int(len(frame)),
                    "missing_rate": missing_rate,
                    "abnormal_price_count": abnormal_price_count,
                    "abnormal_return_count": abnormal_return_count,
                    "split_like_count": split_like_count,
                    "possible_adjustment_issue": possible_adjustment_issue,
                    "average_dollar_volume": average_dollar_volume,
                    "zero_volume_ratio": zero_volume_ratio,
                    "has_adj_close": has_adj_close,
                    "meets_min_length": meets_min_length,
                    "passes_missing_check": passes_missing_check,
                    "passes_liquidity_check": passes_liquidity_check,
                    "passes_anomaly_check": passes_anomaly_check,
                    "passes_quality": passes_quality,
                    "is_leveraged": bool(meta.get("is_leveraged", False)),
                    "asset_type": meta.get("asset_type", ""),
                }
            )

            detail_rows.extend(
                [
                    {
                        "ticker": ticker,
                        "check_name": "min_observations",
                        "check_value": int(len(frame)),
                        "threshold": min_obs,
                        "passed": meets_min_length,
                        "message": "Minimum history length requirement.",
                    },
                    {
                        "ticker": ticker,
                        "check_name": "missing_rate",
                        "check_value": missing_rate,
                        "threshold": max_missing_rate,
                        "passed": passes_missing_check,
                        "message": "Average missing ratio across OHLCV columns.",
                    },
                    {
                        "ticker": ticker,
                        "check_name": "average_dollar_volume",
                        "check_value": average_dollar_volume,
                        "threshold": min_avg_dollar_volume,
                        "passed": passes_liquidity_check,
                        "message": "20-day average dollar volume screen.",
                    },
                    {
                        "ticker": ticker,
                        "check_name": "abnormal_return_count",
                        "check_value": abnormal_return_count,
                        "threshold": f"<= {max(3, int(len(frame) * 0.01))}",
                        "passed": passes_anomaly_check,
                        "message": "Suspiciously large daily move count.",
                    },
                    {
                        "ticker": ticker,
                        "check_name": "possible_adjustment_issue",
                        "check_value": possible_adjustment_issue,
                        "threshold": False,
                        "passed": not possible_adjustment_issue,
                        "message": "Potential split/adjustment issue heuristic.",
                    },
                ]
            )

        summary_df = pd.DataFrame(rows).sort_values(["passes_quality", "ticker"], ascending=[False, True]).reset_index(drop=True)
        detail_df = pd.DataFrame(detail_rows).sort_values(["ticker", "check_name"]).reset_index(drop=True)
        return summary_df, detail_df

    def _find_local_file(self, ticker: str) -> Path | None:
        for directory in self.search_dirs:
            if not directory.exists():
                continue
            direct = directory / f"{ticker}.csv"
            if direct.exists():
                return direct
            matches = list(directory.rglob(f"{ticker}.csv"))
            if matches:
                return sorted(matches)[0]
        return None

    def _read_csv(self, path: Path) -> pd.DataFrame:
        frame = pd.read_csv(path)
        frame.columns = [str(col).strip().lower().replace(" ", "_") for col in frame.columns]
        rename_map = {"adj_close": "adj_close", "adjclose": "adj_close", "adj_close_": "adj_close"}
        frame = frame.rename(columns=rename_map)
        if "date" not in frame.columns:
            raise ValueError(f"Data file {path} does not contain a date column.")

        for column in CANONICAL_COLUMNS:
            if column not in frame.columns:
                if column == "adj_close":
                    frame[column] = frame["close"] if "close" in frame.columns else np.nan
                elif column in {"dividends", "splits"}:
                    frame[column] = 0.0
                else:
                    frame[column] = np.nan

        frame["date"] = pd.to_datetime(frame["date"], utc=True).dt.tz_localize(None)
        frame = frame[CANONICAL_COLUMNS].sort_values("date").drop_duplicates(subset=["date"]).set_index("date")
        frame.index.name = "date"
        return frame.astype(
            {
                "open": float,
                "high": float,
                "low": float,
                "close": float,
                "adj_close": float,
                "volume": float,
                "dividends": float,
                "splits": float,
            }
        )

    def _clip_dates(self, frame: pd.DataFrame, start_date: str | None, end_date: str | None) -> pd.DataFrame:
        clipped = frame
        if start_date:
            clipped = clipped.loc[clipped.index >= pd.Timestamp(start_date)]
        if end_date:
            clipped = clipped.loc[clipped.index <= pd.Timestamp(end_date)]
        return clipped.copy()

    def _download_yfinance(self, ticker: str, start_date: str | None, end_date: str | None) -> Path | None:
        try:
            import yfinance as yf
        except Exception as exc:  # pragma: no cover - dependency varies by env
            self.logger.warning(f"yfinance unavailable for {ticker}: {exc}")
            return None

        download_start = start_date or self.config.get("data", {}).get("download_start", "2000-01-01")
        history = yf.download(
            tickers=ticker,
            start=download_start,
            end=end_date,
            auto_adjust=False,
            progress=False,
            actions=True,
        )
        if history is None or history.empty:
            self.logger.warning(f"yfinance returned no rows for {ticker}.")
            return None

        if isinstance(history.columns, pd.MultiIndex):
            history.columns = [str(col[-1] if isinstance(col, tuple) else col).lower().replace(" ", "_") for col in history.columns]
        else:
            history.columns = [str(col).lower().replace(" ", "_") for col in history.columns]

        history = history.rename(
            columns={
                "adj_close": "adj_close",
                "stock_splits": "splits",
                "capital_gains": "dividends",
            }
        )
        if "adj_close" not in history.columns and "close" in history.columns:
            history["adj_close"] = history["close"]
        if "dividends" not in history.columns:
            history["dividends"] = 0.0
        if "splits" not in history.columns:
            history["splits"] = 0.0
        history.index.name = "date"

        out_path = ensure_dir(self.raw_data_dir) / f"{ticker}.csv"
        history.reset_index().to_csv(out_path, index=False, encoding="utf-8")
        self.logger.info(f"Downloaded {ticker} to {out_path}")
        return out_path
