"""End-to-end US stock selection orchestration."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pandas as pd

from quant_lab.us_stock_selection.buyhold import BuyHoldAnalyzer, attach_buyhold_comparison
from quant_lab.us_stock_selection.data_loader import USDataLoader
from quant_lab.us_stock_selection.factor_screen import FactorRegistryAdapter, FactorScreenEngine
from quant_lab.us_stock_selection.feature_builder import FeatureBuilder
from quant_lab.us_stock_selection.parameter_stability import ParameterStabilityAnalyzer
from quant_lab.us_stock_selection.qlib_data_setup import prepare_qlib_data_status
from quant_lab.us_stock_selection.qlib_env import check_qlib_environment
from quant_lab.us_stock_selection.qlib_model_lab import QlibModelLab
from quant_lab.us_stock_selection.qlib_overfit_checks import run_qlib_overfit_checks
from quant_lab.us_stock_selection.qlib_signal_backtest import (
    build_benchmark_comparison_v4,
    build_close_panel,
    build_weights,
    compute_portfolio_metrics,
    portfolio_returns,
    run_qlib_signal_backtests,
)
from quant_lab.us_stock_selection.qlib_v4_reporting import (
    build_v4_excel,
    build_v4_report,
    package_v4_run,
)
from quant_lab.us_stock_selection.qlib_adapter import QlibAdapter
from quant_lab.us_stock_selection.qlib_runtime_runner import QlibRuntimeRunner
from quant_lab.us_stock_selection.ranking import RankingEngine
from quant_lab.us_stock_selection.reporting import ReportBuilder
from quant_lab.us_stock_selection.search_engine import SearchOutputs, StrategySearchEngine
from quant_lab.us_stock_selection.universe import apply_quality_filter, build_universe_table
from quant_lab.us_stock_selection.utils import (
    PROJECT_ROOT,
    RunArtifacts,
    create_run_artifacts,
    load_env_config,
    load_yaml,
    make_logger,
    merge_many_dicts,
    parse_params,
    save_dataframe,
    save_json,
    save_text,
    save_yaml,
)
from quant_lab.us_stock_selection.validation import ValidationEngine
from quant_lab.us_stock_selection.vectorbt_adapter import VectorbtStrategyAdapter


class USStockSelectionPipeline:
    """Full research pipeline with reusable per-stage entry points."""

    def __init__(self, config_path: str | Path):
        self.config_path = Path(config_path)
        self.env_config = load_env_config()
        self.config = self._load_project_config(self.config_path)
        output_root = PROJECT_ROOT / self.config.get("paths", {}).get("output_root", "outputs/us_stock_selection")
        self.artifacts: RunArtifacts = create_run_artifacts(output_root)
        self.logger = make_logger(self.artifacts.logs_dir / "run.log", level=str(self.config.get("logging", {}).get("level", "INFO")))
        self.loaded_data: dict[str, pd.DataFrame] = {}
        self.market_panels: dict[str, pd.DataFrame] = {}
        self.universe_df = pd.DataFrame()
        self.eligible_universe_df = pd.DataFrame()
        self.excluded_universe_df = pd.DataFrame()
        self.quality_summary_df = pd.DataFrame()
        self.quality_detail_df = pd.DataFrame()
        self.feature_map: dict[str, pd.DataFrame] = {}
        self.label_audit_df = pd.DataFrame()
        self.factor_ic_df = pd.DataFrame()
        self.factor_rank_df = pd.DataFrame()
        self.factor_support_df = pd.DataFrame()
        self.buyhold_df = pd.DataFrame()
        self.all_strategy_results_df = pd.DataFrame()
        self.best_strategy_df = pd.DataFrame()
        self.best_bundles: dict[str, Any] = {}
        self.ml_results_df = pd.DataFrame()
        self.rotation_results_df = pd.DataFrame()
        self.parameter_stability_df = pd.DataFrame()
        self.walk_forward_df = pd.DataFrame()
        self.walk_forward_summary_df = pd.DataFrame()
        self.regime_df = pd.DataFrame()
        self.regime_score_df = pd.DataFrame()
        self.qlib_runtime_status: dict[str, Any] = {}
        self.qlib_env_status: dict[str, Any] = {}
        self.qlib_data_status: dict[str, Any] = {}
        self.qlib_panel_df = pd.DataFrame()
        self.qlib_model_metrics_df = pd.DataFrame()
        self.qlib_signal_results_df = pd.DataFrame()
        self.qlib_predictions_index_df = pd.DataFrame()
        self.qlib_signal_daily_df = pd.DataFrame()
        self.qlib_signal_turnover_df = pd.DataFrame()
        self.qlib_signal_holdings_df = pd.DataFrame()
        self.v4_benchmark_comparison_df = pd.DataFrame()
        self.qlib_walk_forward_detail_df = pd.DataFrame()
        self.qlib_walk_forward_summary_df = pd.DataFrame()
        self.qlib_overfit_summary_df = pd.DataFrame()
        self.qlib_yearly_contribution_df = pd.DataFrame()
        self.qlib_holding_concentration_df = pd.DataFrame()
        self.final_ranking_df = pd.DataFrame()
        self.top_candidates_df = pd.DataFrame()

        self.data_loader = USDataLoader(self.config, self.env_config, self.logger)
        self.feature_builder = FeatureBuilder(self.config, self.logger)
        self.factor_engine = FactorScreenEngine(self.config, self.logger)
        self.buyhold_analyzer = BuyHoldAnalyzer(self.config, self.logger)
        self.strategy_adapter = VectorbtStrategyAdapter(self.config, self.logger)
        self.search_engine = StrategySearchEngine(self.config, self.logger)
        self.parameter_stability_analyzer = ParameterStabilityAnalyzer(self.config, self.logger)
        self.validation_engine = ValidationEngine(self.config, self.logger)
        self.ranking_engine = RankingEngine(self.config, self.logger)
        self.report_builder = ReportBuilder(self.config, self.logger)
        self.qlib_adapter = QlibAdapter(self.config, self.env_config, self.logger)
        self.qlib_runtime_runner = QlibRuntimeRunner(self.config, self.env_config, self.logger)
        self.qlib_model_lab = QlibModelLab(self.config, self.logger)

    def run_all(self) -> dict[str, Any]:
        if str(self.config.get("research_mode", "")).lower() == "qlib_first_v4":
            return self.run_all_v4_qlib_first()
        self.prepare_run()
        self.run_download_stage()
        self.run_universe_stage()
        self.run_feature_stage()
        self.run_factor_screen_stage()
        self.run_strategy_search_stage()
        self.run_qlib_runtime_stage()
        self.run_walk_forward_stage()
        self.run_regime_stage()
        self.run_ranking_stage()
        self.run_reporting_stage()
        return {
            "run_dir": str(self.artifacts.run_dir),
            "report_md": str(self.artifacts.reports_dir / "us_stock_selection_report.md"),
            "ranking_csv": str(self.artifacts.ranking_dir / "final_ticker_ranking.csv"),
            "zip_path": str(self.artifacts.run_dir.parent / f"us_stock_selection_quant_lab_v2_{self.artifacts.timestamp}.zip"),
        }

    def prepare_run(self):
        save_yaml(self.config, self.artifacts.run_dir / "run_config.yaml")
        save_yaml(self.config, self.artifacts.config_snapshot_dir / "validation_config.yaml")
        for path in (PROJECT_ROOT / "configs" / "us_stock_selection").glob("*.yaml"):
            shutil.copy2(path, self.artifacts.config_snapshot_dir / path.name)
        save_json(self.qlib_adapter.runtime_status(), self.artifacts.config_snapshot_dir / "qlib_runtime_status.json")
        self.logger.info(f"Prepared output directory {self.artifacts.run_dir}")

    def run_download_stage(self):
        config_copy = self.config.get("data", {}).copy()
        save_yaml(config_copy, self.artifacts.config_snapshot_dir / "data_stage_config.yaml")
        self.logger.info("Download stage uses local-first loading; optional yfinance fallback remains available.")

    def run_universe_stage(self):
        include_universes = list(self.config.get("universe_selection", {}).get("include_universes", []))
        self.universe_df = build_universe_table(include_universes, PROJECT_ROOT / "configs" / "us_stock_selection")
        self.logger.info(f"Universe contains {len(self.universe_df)} unique tickers before quality screening.")

        results = self.data_loader.load_many(
            tickers=self.universe_df["ticker"].tolist(),
            start_date=self.config.get("study_period", {}).get("start_date"),
            end_date=self.config.get("study_period", {}).get("end_date"),
            allow_download=self.config.get("data", {}).get("allow_download", False),
        )
        self.loaded_data = {ticker: result.data for ticker, result in results.items()}
        self.quality_summary_df, self.quality_detail_df = self.data_loader.build_data_quality_reports(results, self.universe_df)
        self.eligible_universe_df, self.excluded_universe_df = apply_quality_filter(self.universe_df, self.quality_summary_df)

        save_dataframe(self.quality_summary_df, self.artifacts.data_quality_dir / "data_quality_summary.csv")
        save_dataframe(self.quality_detail_df, self.artifacts.data_quality_dir / "data_quality_detail.csv")
        save_dataframe(self.universe_df, self.artifacts.data_quality_dir / "universe_before_quality.csv")
        save_dataframe(self.eligible_universe_df, self.artifacts.data_quality_dir / "universe_after_quality.csv")
        save_dataframe(self.excluded_universe_df, self.artifacts.data_quality_dir / "excluded_tickers.csv")
        self.logger.info(f"{len(self.eligible_universe_df)} tickers passed data quality checks.")

    def run_feature_stage(self):
        if self.eligible_universe_df.empty:
            raise RuntimeError("Universe stage must run before feature stage and yield eligible tickers.")

        eligible_tickers = self.eligible_universe_df["ticker"].tolist()
        loaded = {ticker: self.loaded_data[ticker] for ticker in eligible_tickers}
        self.market_panels = {}
        close_panel = pd.DataFrame({ticker: frame["close"] for ticker, frame in loaded.items() if not frame.empty}).sort_index()
        if "QQQ" in close_panel.columns:
            qqq_close = close_panel["QQQ"]
            self.market_panels["QQQ"] = pd.DataFrame({"QQQ": qqq_close, "benchmark_realized_vol_20": qqq_close.pct_change(fill_method=None).rolling(20).std() * (252 ** 0.5)})
        if "SPY" in close_panel.columns:
            spy_close = close_panel["SPY"]
            self.market_panels["SPY"] = pd.DataFrame({"SPY": spy_close})
        if "TLT" in close_panel.columns:
            self.market_panels["TLT"] = pd.DataFrame({"TLT": close_panel["TLT"]})
        if "IEF" in close_panel.columns:
            self.market_panels["IEF"] = pd.DataFrame({"IEF": close_panel["IEF"]})

        external_names = list(self.config.get("features", {}).get("external_factor_names", []))
        external_feature_map = self.feature_builder.build_external_feature_map(
            loaded_data=loaded,
            factor_names=external_names,
            batch_size=int(self.config.get("features", {}).get("external_factor_batch_size", 25)),
        )

        feature_cache_dir = self.config.get("features", {}).get("cache_dir", "data/features_cache/us_stock_selection")
        self.feature_map = {}
        for idx, ticker in enumerate(eligible_tickers, start=1):
            self.logger.info(f"Building features for {ticker} ({idx}/{len(eligible_tickers)})")
            result = self.feature_builder.build_feature_cache(
                ticker=ticker,
                frame=loaded[ticker],
                market_panels=self._market_reference_panels(),
                cache_dir=feature_cache_dir,
                external_feature_map=external_feature_map.get(ticker),
            )
            self.feature_map[ticker] = result.features

        self.label_audit_df = self.feature_builder.build_label_audit(self.feature_map)
        save_dataframe(self.label_audit_df, self.artifacts.factor_screen_dir / "label_alignment_audit.csv")
        panel_export = self.qlib_adapter.export_panel_dataset(self.feature_map, self.artifacts.strategy_search_dir)
        self.logger.info(f"Feature stage complete. Exported panel dataset to {panel_export}")

    def run_factor_screen_stage(self):
        if not self.feature_map:
            self.run_feature_stage()

        sample_features = next(iter(self.feature_map.values()))
        registry = FactorRegistryAdapter(feature_columns=[col for col in sample_features.columns if col not in {"ticker"}])
        selected_factors = list(self.config.get("factor_screen", {}).get("selected_factors", []))
        if not selected_factors:
            selected_factors = registry.list_available()[:120]
        self.factor_ic_df, self.factor_rank_df, self.factor_support_df = self.factor_engine.run(self.feature_map, selected_factors)

        save_dataframe(self.factor_ic_df, self.artifacts.factor_screen_dir / "factor_ic_summary.csv")
        save_dataframe(self.factor_rank_df, self.artifacts.factor_screen_dir / "factor_rank_by_ticker.csv")
        save_dataframe(self.factor_support_df, self.artifacts.factor_screen_dir / "factor_support_by_ticker.csv")
        save_text("\n".join(selected_factors), self.artifacts.factor_screen_dir / "selected_factor_list.txt")
        self.logger.info("Factor screening stage complete.")

    def run_strategy_search_stage(self):
        if self.eligible_universe_df.empty:
            self.run_universe_stage()
        if not self.feature_map:
            self.run_feature_stage()

        self.buyhold_df = self.buyhold_analyzer.run(
            universe_df=self.eligible_universe_df,
            loaded_data={ticker: self.loaded_data[ticker] for ticker in self.eligible_universe_df["ticker"]},
        )
        save_dataframe(self.buyhold_df, self.artifacts.benchmark_dir / "buyhold_by_ticker.csv")

        search_space = load_yaml(PROJECT_ROOT / "configs" / "us_stock_selection" / "strategy_search_space.yaml")
        market_context_map = {ticker: self._market_context_for_ticker(ticker) for ticker in self.eligible_universe_df["ticker"]}
        all_df, best_df, best_bundles, split_map = self.search_engine.run_vectorbt_search(
            universe_df=self.eligible_universe_df,
            loaded_data={ticker: self.loaded_data[ticker] for ticker in self.eligible_universe_df["ticker"]},
            market_context_map=market_context_map,
            adapter=self.strategy_adapter,
            search_space=search_space.get("templates", {}),
        )
        self.all_strategy_results_df = attach_buyhold_comparison(all_df, self.buyhold_df)
        self.best_strategy_df = attach_buyhold_comparison(best_df, self.buyhold_df)
        self.best_bundles = best_bundles
        self.parameter_stability_df = self.parameter_stability_analyzer.run(self.all_strategy_results_df, self.best_strategy_df)
        if not self.parameter_stability_df.empty:
            replacement_cols = ["ticker", "parameter_stability_score", "parameter_island_risk"]
            self.best_strategy_df = self.best_strategy_df.drop(
                columns=[col for col in replacement_cols if col in self.best_strategy_df.columns and col != "ticker"],
                errors="ignore",
            ).merge(self.parameter_stability_df.loc[:, replacement_cols], how="left", on="ticker")
        self.rotation_results_df = self.search_engine.run_rotation_search(
            loaded_data=self.loaded_data,
            search_config=search_space.get("rotation_strategy", {}),
        )
        ml_max_tickers = int(self.config.get("ml", {}).get("max_tickers", 0) or 0)
        ml_candidates = self.best_strategy_df.head(ml_max_tickers)["ticker"].tolist() if ml_max_tickers > 0 else self.best_strategy_df["ticker"].tolist()
        ml_universe_df = self.eligible_universe_df.loc[self.eligible_universe_df["ticker"].isin(ml_candidates)].copy()
        self.ml_results_df = self.search_engine.run_ml_search(
            universe_df=ml_universe_df,
            feature_map=self.feature_map,
            market_context_map=market_context_map,
            adapter=self.strategy_adapter,
        )
        save_dataframe(self.ml_results_df, self.artifacts.strategy_search_dir / "ml_strategy_results.csv")
        save_dataframe(self.parameter_stability_df, self.artifacts.strategy_search_dir / "parameter_stability_by_ticker.csv")
        save_dataframe(self.rotation_results_df, self.artifacts.strategy_search_dir / "rotation_strategy_results.csv")

        if not self.best_strategy_df.empty:
            workflow_path = self.qlib_adapter.build_workflow_snapshot(
                universe_name="us_stock_selection_panel",
                benchmark=str(self.config.get("benchmark", {}).get("primary", "SPY")),
                out_dir=self.artifacts.config_snapshot_dir,
            )
            self.logger.info(f"Saved Qlib workflow snapshot to {workflow_path}")

        save_dataframe(self.all_strategy_results_df, self.artifacts.strategy_search_dir / "all_strategy_results.csv")
        save_dataframe(self.best_strategy_df, self.artifacts.strategy_search_dir / "best_strategy_by_ticker.csv")
        split_rows = []
        for ticker, split in split_map.items():
            split_rows.append(
                {
                    "ticker": ticker,
                    "split_mode": split.mode,
                    "train_start": split.train_start.date().isoformat(),
                    "train_end": split.train_end.date().isoformat(),
                    "valid_start": split.valid_start.date().isoformat(),
                    "valid_end": split.valid_end.date().isoformat(),
                    "test_start": split.test_start.date().isoformat(),
                    "test_end": split.test_end.date().isoformat(),
                }
            )
        save_dataframe(pd.DataFrame(split_rows), self.artifacts.strategy_search_dir / "time_splits_by_ticker.csv")
        self.logger.info("Strategy search stage complete.")

    def run_qlib_runtime_stage(self):
        if not self.feature_map:
            self.run_feature_stage()
        if self.eligible_universe_df.empty:
            self.run_universe_stage()
        market_context_map = {ticker: self._market_context_for_ticker(ticker) for ticker in self.eligible_universe_df["ticker"]}
        self.qlib_runtime_status, self.qlib_model_metrics_df, self.qlib_signal_results_df = self.qlib_runtime_runner.run(
            feature_map=self.feature_map,
            loaded_data={ticker: self.loaded_data[ticker] for ticker in self.eligible_universe_df["ticker"]},
            market_context_map=market_context_map,
            universe_df=self.eligible_universe_df,
            adapter=self.strategy_adapter,
            out_dir=self.artifacts.qlib_dir,
        )
        self.logger.info(f"Qlib runtime stage complete with status={self.qlib_runtime_status.get('status')}")

    def run_walk_forward_stage(self):
        if self.best_strategy_df.empty:
            self.run_strategy_search_stage()

        search_space = load_yaml(PROJECT_ROOT / "configs" / "us_stock_selection" / "strategy_search_space.yaml")
        market_context_map = {ticker: self._market_context_for_ticker(ticker) for ticker in self.eligible_universe_df["ticker"]}
        rows = []
        max_tickers = int(self.config.get("walk_forward", {}).get("max_tickers", 0) or 0)
        wf_source = self.best_strategy_df.head(max_tickers) if max_tickers > 0 else self.best_strategy_df
        for _, row in wf_source.iterrows():
            ticker = row["ticker"]
            result_df = self.validation_engine.walk_forward_validate(
                ticker=ticker,
                frame=self.loaded_data[ticker],
                market_context=market_context_map.get(ticker, pd.DataFrame()),
                asset_meta=self.eligible_universe_df.set_index("ticker").to_dict(orient="index").get(ticker, {}),
                best_strategy_row=row,
                adapter=self.strategy_adapter,
                search_space=search_space.get("templates", {}),
            )
            if not result_df.empty:
                rows.append(result_df)
        self.walk_forward_df = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
        save_dataframe(self.walk_forward_df, self.artifacts.walk_forward_dir / "walk_forward_results.csv")
        save_dataframe(self.walk_forward_df, self.artifacts.walk_forward_dir / "walk_forward_window_detail.csv")
        self.walk_forward_summary_df = self.validation_engine.walk_forward_summary(self.walk_forward_df)
        save_dataframe(self.walk_forward_summary_df, self.artifacts.walk_forward_dir / "walk_forward_summary_by_ticker.csv")
        self.logger.info("Walk-forward stage complete.")

    def run_regime_stage(self):
        if not self.best_bundles:
            self.run_strategy_search_stage()

        rows = []
        for ticker, bundle in self.best_bundles.items():
            regime_df = self.validation_engine.regime_validate(
                ticker=ticker,
                bundle=bundle,
                market_context=self._market_context_for_ticker(ticker),
            )
            if not regime_df.empty:
                rows.append(regime_df)
        self.regime_df = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
        self.regime_score_df = self.validation_engine.regime_score(self.regime_df)
        save_dataframe(self.regime_df, self.artifacts.regime_validation_dir / "regime_results.csv")
        save_dataframe(self.regime_score_df, self.artifacts.regime_validation_dir / "regime_scores.csv")
        self.logger.info("Regime validation stage complete.")

    def run_ranking_stage(self):
        if self.best_strategy_df.empty:
            self.run_strategy_search_stage()
        if self.factor_support_df.empty:
            self.run_factor_screen_stage()
        if self.walk_forward_df.empty:
            self.run_walk_forward_stage()
        if self.regime_score_df.empty:
            self.run_regime_stage()

        self.final_ranking_df, self.top_candidates_df = self.ranking_engine.build_final_ranking(
            best_strategy_df=self.best_strategy_df,
            factor_support_df=self.factor_support_df if not self.factor_support_df.empty else pd.DataFrame(columns=["ticker", "factor_support_score_raw"]),
            walk_forward_df=self.walk_forward_df,
            regime_score_df=self.regime_score_df if not self.regime_score_df.empty else pd.DataFrame(columns=["ticker", "regime_score_raw"]),
            quality_df=self.quality_summary_df,
            universe_df=self.eligible_universe_df,
            parameter_stability_df=self.parameter_stability_df,
        )
        save_dataframe(self.final_ranking_df, self.artifacts.ranking_dir / "final_ticker_ranking.csv")
        save_dataframe(self.top_candidates_df, self.artifacts.ranking_dir / "top_candidates.csv")
        self.logger.info("Ranking stage complete.")

    def run_reporting_stage(self):
        if self.final_ranking_df.empty:
            self.run_ranking_stage()

        report_md = self.report_builder.build_markdown_report(
            self.artifacts.reports_dir / "us_stock_selection_report.md",
            universe_df=self.eligible_universe_df,
            excluded_df=self.excluded_universe_df,
            top_df=self.top_candidates_df,
            best_strategy_df=self.best_strategy_df,
            factor_rank_df=self.factor_rank_df,
            final_ranking_df=self.final_ranking_df,
            buyhold_df=self.buyhold_df,
            parameter_stability_df=self.parameter_stability_df,
            walk_forward_summary_df=self.walk_forward_summary_df,
            rotation_df=self.rotation_results_df,
            qlib_status=self.qlib_runtime_status,
        )
        report_html = self.report_builder.build_html_report(
            self.artifacts.reports_dir / "us_stock_selection_report.html",
            top_df=self.top_candidates_df,
            best_strategy_df=self.best_strategy_df,
            excluded_df=self.excluded_universe_df,
            final_ranking_df=self.final_ranking_df,
        )
        warnings_df = self.final_ranking_df.loc[
            :, [col for col in ["ticker", "classification", "overfit_penalty", "parameter_island_risk", "data_quality_penalty", "leverage_penalty"] if col in self.final_ranking_df.columns]
        ] if not self.final_ranking_df.empty else pd.DataFrame()
        self.report_builder.build_excel_summary(
            self.artifacts.reports_dir / "us_stock_selection_summary.xlsx",
            {
                "buyhold": self.buyhold_df,
                "data_quality": self.quality_summary_df,
                "final_ranking": self.final_ranking_df,
                "top_candidates": self.top_candidates_df,
                "best_strategy": self.best_strategy_df,
                "parameter_stability": self.parameter_stability_df,
                "rotation": self.rotation_results_df,
                "factor_summary": self.factor_rank_df,
                "walk_forward": self.walk_forward_df,
                "wf_summary": self.walk_forward_summary_df,
                "regime_validation": self.regime_df,
                "qlib_status": pd.DataFrame([self.qlib_runtime_status]) if self.qlib_runtime_status else pd.DataFrame(),
                "qlib_model_metrics": self.qlib_model_metrics_df,
                "qlib_signal_results": self.qlib_signal_results_df,
                "warnings": warnings_df,
            },
        )
        zip_path = self.report_builder.package_run(self.artifacts.run_dir, self.artifacts.timestamp)
        self.logger.info(f"Reporting stage complete. Markdown: {report_md}, HTML: {report_html}, ZIP: {zip_path}")

    def run_all_v4_qlib_first(self) -> dict[str, Any]:
        """Run the v4 Qlib-first cross-sectional research pipeline."""
        self.prepare_run()
        self.run_qlib_env_check_stage()
        self.run_download_stage()
        self.run_universe_stage()
        self.run_feature_stage()
        self.run_qlib_data_stage_v4()
        self.run_qlib_model_lab_stage()
        self.run_qlib_signal_backtest_stage()
        self.run_qlib_walk_forward_stage_v4()
        self.run_qlib_overfit_stage()
        self.run_qlib_v4_ranking_stage()
        zip_path = self.run_qlib_v4_reporting_stage()
        return {
            "run_dir": str(self.artifacts.run_dir),
            "report_md": str(self.artifacts.reports_dir / "us_stock_selection_v4_qlib_first_report.md"),
            "ranking_csv": str(self.artifacts.ranking_dir / "final_ticker_ranking.csv"),
            "zip_path": str(zip_path),
        }

    def run_qlib_env_check_stage(self):
        self.qlib_env_status = check_qlib_environment(
            out_dir=self.artifacts.qlib_env_dir,
            provider_uri=self.config.get("qlib_v4", {}).get("provider_uri"),
            logger=self.logger,
        )
        save_json(self.qlib_env_status, self.artifacts.qlib_dir / "qlib_runtime_status.json")
        self.logger.info(f"v4 qlib env status: {self.qlib_env_status.get('runtime_status')}")

    def run_qlib_data_stage_v4(self):
        if not self.feature_map:
            self.run_feature_stage()
        self.qlib_data_status, self.qlib_panel_df = prepare_qlib_data_status(
            out_dir=self.artifacts.qlib_data_dir,
            qlib_env_status=self.qlib_env_status,
            feature_map=self.feature_map,
            loaded_data={ticker: self.loaded_data[ticker] for ticker in self.eligible_universe_df["ticker"]},
            universe_df=self.eligible_universe_df,
            provider_uri=self.config.get("qlib_v4", {}).get("provider_uri"),
            logger=self.logger,
        )
        self.logger.info(f"v4 qlib data mode: {self.qlib_data_status.get('data_mode')}")

    def run_qlib_model_lab_stage(self):
        if self.qlib_panel_df.empty:
            self.run_qlib_data_stage_v4()
        outputs = self.qlib_model_lab.run(
            panel=self.qlib_panel_df,
            out_dir=self.artifacts.qlib_model_lab_dir,
            qlib_env_status=self.qlib_env_status,
            qlib_data_status=self.qlib_data_status,
        )
        self.qlib_model_metrics_df = outputs.get("signal_quality", pd.DataFrame())
        self.qlib_predictions_index_df = outputs.get("predictions_index", pd.DataFrame())
        self.logger.info(f"v4 qlib model lab completed: {len(self.qlib_model_metrics_df)} successful model rows.")

    def run_qlib_signal_backtest_stage(self):
        if self.qlib_predictions_index_df.empty:
            self.run_qlib_model_lab_stage()
        outputs = run_qlib_signal_backtests(
            predictions_index=self.qlib_predictions_index_df,
            loaded_data={ticker: self.loaded_data[ticker] for ticker in self.eligible_universe_df["ticker"]},
            out_dir=self.artifacts.qlib_signal_backtest_dir,
            config=self.config,
            logger=self.logger,
        )
        self.qlib_signal_results_df = outputs.get("results", pd.DataFrame())
        self.qlib_signal_daily_df = outputs.get("daily", pd.DataFrame())
        self.qlib_signal_turnover_df = outputs.get("turnover", pd.DataFrame())
        self.qlib_signal_holdings_df = outputs.get("holdings", pd.DataFrame())
        self.v4_benchmark_comparison_df = build_benchmark_comparison_v4(
            loaded_data={ticker: self.loaded_data[ticker] for ticker in self.eligible_universe_df["ticker"]},
            qlib_results=self.qlib_signal_results_df,
            qlib_daily=self.qlib_signal_daily_df,
            out_dir=self.artifacts.benchmark_dir,
            config=self.config,
        )
        self.logger.info(f"v4 signal backtest rows: {len(self.qlib_signal_results_df)}")

    def run_qlib_walk_forward_stage_v4(self):
        if self.qlib_signal_results_df.empty:
            self.run_qlib_signal_backtest_stage()
        if self.qlib_signal_results_df.empty or self.qlib_model_metrics_df.empty:
            save_dataframe(pd.DataFrame(), self.artifacts.qlib_walk_forward_dir / "qlib_walk_forward_detail.csv")
            save_dataframe(pd.DataFrame(), self.artifacts.qlib_walk_forward_dir / "qlib_walk_forward_summary.csv")
            return

        close = build_close_panel({ticker: self.loaded_data[ticker] for ticker in self.eligible_universe_df["ticker"]})
        rows = []
        cfg = self.config.get("qlib_v4", {}).get("walk_forward", {})
        start_year = int(cfg.get("start_year", 2020))
        test_months = int(cfg.get("test_months", 12))
        for _, strategy_row in self.qlib_signal_results_df.head(5).iterrows():
            run_id = strategy_row.get("run_id", "")
            model_row_df = self.qlib_model_metrics_df.loc[self.qlib_model_metrics_df["run_id"] == run_id].head(1)
            if model_row_df.empty:
                continue
            wf_pred = self.qlib_model_lab.anchored_walk_forward_predictions(
                panel=self.qlib_panel_df,
                run_row=model_row_df.iloc[0],
                start_year=start_year,
                test_months=test_months,
            )
            if wf_pred.empty:
                continue
            params = parse_params(strategy_row.get("params", "{}"))
            strategy_name = str(strategy_row.get("portfolio_template", "topk_equal_weight"))
            rebalance = str(params.pop("rebalance", "M"))
            for (train_end, test_start, test_end), group in wf_pred.groupby(["train_end", "test_start", "test_end"]):
                score = group.pivot_table(index="date", columns="ticker", values="score", aggfunc="last")
                score.index = pd.to_datetime(score.index)
                local_close = close.loc[(close.index >= pd.Timestamp(test_start)) & (close.index <= pd.Timestamp(test_end)), close.columns.intersection(score.columns)].ffill()
                if local_close.empty:
                    continue
                local_score = score.reindex(local_close.index).loc[:, local_close.columns].ffill(limit=3)
                weights = build_weights(local_close, local_score, strategy_name=strategy_name, rebalance=rebalance, params=params)
                returns, turnover = portfolio_returns(local_close, weights, cost_bps=float(params.get("cost_bps", 5.0)), slippage_bps=float(params.get("slippage_bps", 5.0)))
                metrics = compute_portfolio_metrics(returns, turnover, weights)
                rows.append(
                    {
                        "strategy_id": strategy_row.get("strategy_id"),
                        "run_id": run_id,
                        "train_end": pd.Timestamp(train_end).date().isoformat(),
                        "test_start": pd.Timestamp(test_start).date().isoformat(),
                        "test_end": pd.Timestamp(test_end).date().isoformat(),
                        "selected_feature_set": model_row_df.iloc[0].get("feature_set"),
                        "selected_model": model_row_df.iloc[0].get("model"),
                        "selected_label": model_row_df.iloc[0].get("label"),
                        "selected_portfolio_template": strategy_name,
                        "selected_params": strategy_row.get("params"),
                        "test_cagr": metrics["cagr"],
                        "test_maxdd": metrics["max_drawdown"],
                        "test_calmar": metrics["calmar"],
                        "test_turnover": metrics["annual_turnover"],
                        "test_days": metrics["daily_count"],
                    }
                )
        self.qlib_walk_forward_detail_df = pd.DataFrame(rows)
        if not self.qlib_walk_forward_detail_df.empty:
            summary = (
                self.qlib_walk_forward_detail_df.groupby("strategy_id")
                .agg(
                    wf_window_count=("strategy_id", "size"),
                    wf_mean_cagr=("test_cagr", "mean"),
                    wf_mean_calmar=("test_calmar", "mean"),
                    wf_min_calmar=("test_calmar", "min"),
                    wf_pass_cagr20_rate=("test_cagr", lambda s: float((s >= 0.20).mean())),
                    wf_pass_calmar1_rate=("test_calmar", lambda s: float((s > 1.0).mean())),
                )
                .reset_index()
                .sort_values(["wf_mean_calmar", "wf_mean_cagr"], ascending=[False, False])
            )
        else:
            summary = pd.DataFrame()
        self.qlib_walk_forward_summary_df = summary
        save_dataframe(self.qlib_walk_forward_detail_df, self.artifacts.qlib_walk_forward_dir / "qlib_walk_forward_detail.csv")
        save_dataframe(self.qlib_walk_forward_summary_df, self.artifacts.qlib_walk_forward_dir / "qlib_walk_forward_summary.csv")
        self.logger.info(f"v4 walk-forward windows: {len(self.qlib_walk_forward_detail_df)}")

    def run_qlib_overfit_stage(self):
        if self.qlib_signal_results_df.empty:
            self.run_qlib_signal_backtest_stage()
        outputs = run_qlib_overfit_checks(
            signal_quality=self.qlib_model_metrics_df,
            strategy_results=self.qlib_signal_results_df,
            portfolio_daily=self.qlib_signal_daily_df,
            holdings=self.qlib_signal_holdings_df,
            out_dir=self.artifacts.qlib_overfit_dir,
        )
        self.qlib_overfit_summary_df = outputs.get("summary", pd.DataFrame())
        self.qlib_yearly_contribution_df = outputs.get("yearly", pd.DataFrame())
        self.qlib_holding_concentration_df = outputs.get("concentration", pd.DataFrame())

    def run_qlib_v4_ranking_stage(self):
        if self.qlib_signal_results_df.empty:
            self.run_qlib_signal_backtest_stage()
        top_strategies = self.qlib_signal_results_df.head(20).copy()
        save_dataframe(top_strategies, self.artifacts.ranking_dir / "top_candidates.csv")
        if self.qlib_signal_holdings_df.empty:
            self.final_ranking_df = pd.DataFrame()
        else:
            top_ids = set(self.qlib_signal_results_df.head(10)["strategy_id"].tolist())
            holding = self.qlib_signal_holdings_df.loc[self.qlib_signal_holdings_df["strategy_id"].isin(top_ids)].copy()
            ranking = (
                holding.groupby("ticker")
                .agg(
                    avg_weight_top10=("weight", "mean"),
                    max_weight_top10=("weight", "max"),
                    strategy_count_top10=("strategy_id", "nunique"),
                )
                .reset_index()
            )
            ranking["final_score"] = ranking["avg_weight_top10"] * 80.0 + ranking["strategy_count_top10"] * 2.0
            ranking = ranking.merge(self.eligible_universe_df, how="left", on="ticker").sort_values("final_score", ascending=False)
            self.final_ranking_df = ranking
        save_dataframe(self.final_ranking_df, self.artifacts.ranking_dir / "final_ticker_ranking.csv")
        self.top_candidates_df = top_strategies
        self.logger.info("v4 ticker/strategy ranking stage complete.")

    def run_qlib_v4_reporting_stage(self) -> Path:
        if self.qlib_overfit_summary_df.empty and not self.qlib_signal_results_df.empty:
            self.run_qlib_overfit_stage()
        report_md = build_v4_report(
            report_path=self.artifacts.reports_dir / "us_stock_selection_v4_qlib_first_report.md",
            config=self.config,
            qlib_env_status=self.qlib_env_status,
            qlib_data_status=self.qlib_data_status,
            model_runs=pd.read_csv(self.artifacts.qlib_model_lab_dir / "model_runs.csv") if (self.artifacts.qlib_model_lab_dir / "model_runs.csv").exists() else pd.DataFrame(),
            signal_quality=self.qlib_model_metrics_df,
            strategy_results=self.qlib_signal_results_df,
            benchmark_comparison=self.v4_benchmark_comparison_df,
            walk_forward_summary=self.qlib_walk_forward_summary_df,
            overfit_summary=self.qlib_overfit_summary_df,
            universe_df=self.eligible_universe_df,
        )
        build_v4_excel(
            self.artifacts.reports_dir / "us_stock_selection_v4_qlib_first_summary.xlsx",
            {
                "qlib_env": pd.DataFrame([self.qlib_env_status]),
                "qlib_data": pd.DataFrame([self.qlib_data_status]),
                "model_metrics": self.qlib_model_metrics_df,
                "signal_strategy": self.qlib_signal_results_df,
                "benchmark": self.v4_benchmark_comparison_df,
                "ticker_ranking": self.final_ranking_df,
                "top_candidates": self.top_candidates_df,
                "walk_forward": self.qlib_walk_forward_detail_df,
                "wf_summary": self.qlib_walk_forward_summary_df,
                "overfit": self.qlib_overfit_summary_df,
                "holding_concentration": self.qlib_holding_concentration_df,
                "yearly_contribution": self.qlib_yearly_contribution_df,
            },
        )
        zip_path = package_v4_run(self.artifacts.run_dir, self.artifacts.timestamp)
        self.logger.info(f"v4 reporting complete. Markdown: {report_md}, ZIP: {zip_path}")
        return zip_path

    def _load_project_config(self, config_path: Path) -> dict[str, Any]:
        base = load_yaml(config_path)
        factor_groups = load_yaml(PROJECT_ROOT / "configs" / "us_stock_selection" / "factor_groups.yaml")
        return merge_many_dicts(factor_groups, base)

    def _market_reference_panels(self) -> dict[str, pd.DataFrame]:
        panels = {}
        for ticker in ("QQQ", "SPY", "TLT", "IEF"):
            frame = self.loaded_data.get(ticker)
            if frame is None or frame.empty:
                continue
            panels[ticker] = pd.DataFrame({ticker: frame["close"]})
        return panels

    def _market_context_for_ticker(self, ticker: str) -> pd.DataFrame:
        index = self.loaded_data.get(ticker, pd.DataFrame()).index
        context = pd.DataFrame(index=index)
        for bench in ("QQQ", "SPY", "TLT", "IEF"):
            frame = self.loaded_data.get(bench)
            if frame is None or frame.empty:
                continue
            close = frame["close"].reindex(index).ffill()
            context[f"{bench}_close"] = close
            for ma in (100, 150, 200):
                context[f"{bench}_trend_ma{ma}"] = close.div(close.rolling(ma).mean()).sub(1.0)
            context[f"{bench}_trend"] = context[f"{bench}_trend_ma{200 if bench in {'QQQ', 'SPY'} else 100}"]
            for window in (20, 60):
                context[f"{bench}_realized_vol_{window}"] = close.pct_change(fill_method=None).rolling(window).std() * (252 ** 0.5)
            if bench == "QQQ":
                context["benchmark_realized_vol_20"] = context[f"{bench}_realized_vol_20"]
        return context
