"""Qlib workflow adapter with graceful degradation when Qlib is unavailable."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pandas as pd

from src.qlib_ext import QlibWorkflowSpec, build_qlib_workflow_config, dump_qlib_workflow_config

from quant_lab.us_stock_selection.utils import PROJECT_ROOT, ensure_dir, save_parquet


class QlibAdapter:
    """Export panel datasets and build Qlib workflow snapshots."""

    def __init__(self, config: dict[str, Any], env_config: dict[str, Any], logger):
        self.config = config
        self.env_config = env_config
        self.logger = logger
        self.qlib_available = importlib.util.find_spec("qlib") is not None

    def export_panel_dataset(
        self,
        feature_map: dict[str, pd.DataFrame],
        out_dir: Path | str,
    ) -> Path:
        rows = []
        for ticker, frame in feature_map.items():
            if frame.empty:
                continue
            subset = frame.copy()
            subset["ticker"] = ticker
            subset = subset.reset_index().rename(columns={"index": "date"})
            rows.append(subset)
        panel = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
        out_path = ensure_dir(out_dir) / "qlib_panel_dataset.parquet"
        save_parquet(panel, out_path)
        return out_path

    def build_workflow_snapshot(
        self,
        universe_name: str,
        benchmark: str,
        out_dir: Path | str,
    ) -> Path:
        qlib_cfg = self.config.get("qlib", {})
        env_paths = self.env_config.get("paths", {})
        provider_uri = qlib_cfg.get("provider_uri") or env_paths.get("qlib_bin", "./data/qlib_bin")
        spec = QlibWorkflowSpec(
            provider_uri=str(provider_uri),
            region=str(qlib_cfg.get("region", "us")),
            market=str(universe_name),
            benchmark=str(benchmark),
            start_time=str(self.config.get("study_period", {}).get("start_date", "2010-01-01")),
            end_time=str(self.config.get("study_period", {}).get("end_date", "2026-12-31")),
            fit_start_time=str(self.config.get("validation", {}).get("preferred_train_start", "2010-01-01")),
            fit_end_time=str(self.config.get("validation", {}).get("preferred_train_end", "2017-12-31")),
            train_segment=(
                str(self.config.get("validation", {}).get("preferred_train_start", "2010-01-01")),
                str(self.config.get("validation", {}).get("preferred_train_end", "2017-12-31")),
            ),
            valid_segment=(
                str(self.config.get("validation", {}).get("preferred_valid_start", "2018-01-01")),
                str(self.config.get("validation", {}).get("preferred_valid_end", "2021-12-31")),
            ),
            test_segment=(
                str(self.config.get("validation", {}).get("preferred_test_start", "2022-01-01")),
                str(self.config.get("validation", {}).get("preferred_test_end", "2026-12-31")),
            ),
            backtest_start_time=str(self.config.get("validation", {}).get("preferred_test_start", "2022-01-01")),
            backtest_end_time=str(self.config.get("validation", {}).get("preferred_test_end", "2026-12-31")),
            strategy_name=str(qlib_cfg.get("strategy_name", "topk_dropout_50_5")),
            model_class=str(qlib_cfg.get("model_class", "LGBModel")),
            model_module=str(qlib_cfg.get("model_module", "qlib.contrib.model.gbdt")),
        )
        workflow = build_qlib_workflow_config(spec)
        out_path = ensure_dir(out_dir) / f"qlib_workflow_{universe_name}.yaml"
        dump_qlib_workflow_config(workflow, out_path)
        return out_path

    def runtime_status(self) -> dict[str, Any]:
        return {
            "qlib_available": self.qlib_available,
            "provider_uri": str(self.env_config.get("paths", {}).get("qlib_bin", "./data/qlib_bin")),
            "note": (
                "Qlib runtime available."
                if self.qlib_available
                else "Qlib runtime is not installed; workflow config export only."
            ),
        }

