"""Catalog of reusable strategy templates archived from external resources."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from src.factors.external_libraries import PROJECT_ROOT


@dataclass(frozen=True)
class ExternalStrategyTemplate:
    """External strategy or model workflow that can be reused as a template."""

    slug: str
    source_resource: str
    family: str
    status: str
    local_path: str
    entry_command: str
    reuse_contract: str
    required_data: tuple[str, ...]
    notes: str = ""

    def resolve_path(self, project_root: Path | None = None) -> Path:
        root = project_root or PROJECT_ROOT
        return root / self.local_path

    def as_dict(self, project_root: Path | None = None) -> dict[str, object]:
        path = self.resolve_path(project_root)
        return {
            "slug": self.slug,
            "source_resource": self.source_resource,
            "family": self.family,
            "status": self.status,
            "local_path": str(path),
            "exists": path.exists(),
            "entry_command": self.entry_command,
            "reuse_contract": self.reuse_contract,
            "required_data": list(self.required_data),
            "notes": self.notes,
        }


EXTERNAL_STRATEGY_TEMPLATES: dict[str, ExternalStrategyTemplate] = {
    "qlib_lightgbm_alpha360": ExternalStrategyTemplate(
        slug="qlib_lightgbm_alpha360",
        source_resource="alpha360_microsoft_qlib",
        family="ml_factor_model",
        status="template_ready",
        local_path="external_repos/factor_libraries/alpha360_microsoft_qlib/examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha360.yaml",
        entry_command="qlib workflow from YAML after qlib data init",
        reuse_contract="Use as a LightGBM Alpha360 model template; local `qlib360_*` features can also be used in quant_lab directly.",
        required_data=("qlib_data_bundle", "instrument_universe"),
    ),
    "qlib_gru_alpha360": ExternalStrategyTemplate(
        slug="qlib_gru_alpha360",
        source_resource="alpha360_microsoft_qlib",
        family="deep_factor_model",
        status="template_ready",
        local_path="external_repos/factor_libraries/alpha360_microsoft_qlib/examples/benchmarks/GRU/workflow_config_gru_Alpha360.yaml",
        entry_command="qlib workflow from YAML after qlib data init",
        reuse_contract="Use as a GRU Alpha360 model template if deep-learning dependencies are available.",
        required_data=("qlib_data_bundle", "instrument_universe"),
    ),
    "qlib_lstm_alpha360": ExternalStrategyTemplate(
        slug="qlib_lstm_alpha360",
        source_resource="alpha360_microsoft_qlib",
        family="deep_factor_model",
        status="template_ready",
        local_path="external_repos/factor_libraries/alpha360_microsoft_qlib/examples/benchmarks/LSTM/workflow_config_lstm_Alpha360.yaml",
        entry_command="qlib workflow from YAML after qlib data init",
        reuse_contract="Use as an LSTM Alpha360 model template if deep-learning dependencies are available.",
        required_data=("qlib_data_bundle", "instrument_universe"),
    ),
    "rqalpha_buy_and_hold": ExternalStrategyTemplate(
        slug="rqalpha_buy_and_hold",
        source_resource="ricequant_rqalpha",
        family="baseline_strategy",
        status="template_ready",
        local_path="external_repos/factor_libraries/ricequant_rqalpha/tests/integration_tests/test_backtest_results/test_s_buy_and_hold.py",
        entry_command="rqalpha test strategy template",
        reuse_contract="Use as a buy-and-hold template or benchmark behavior reference.",
        required_data=("rqalpha_data_bundle",),
    ),
    "rqalpha_dual_thrust": ExternalStrategyTemplate(
        slug="rqalpha_dual_thrust",
        source_resource="ricequant_rqalpha",
        family="breakout_strategy",
        status="template_ready",
        local_path="external_repos/factor_libraries/ricequant_rqalpha/tests/integration_tests/test_backtest_results/test_s_dual_thrust.py",
        entry_command="rqalpha test strategy template",
        reuse_contract="Use as a Dual Thrust breakout strategy reference and port rules into quant_lab if useful.",
        required_data=("rqalpha_data_bundle", "ohlcv"),
    ),
    "rqalpha_turtle": ExternalStrategyTemplate(
        slug="rqalpha_turtle",
        source_resource="ricequant_rqalpha",
        family="trend_following_strategy",
        status="template_ready",
        local_path="external_repos/factor_libraries/ricequant_rqalpha/tests/integration_tests/test_backtest_results/test_s_turtle.py",
        entry_command="rqalpha test strategy template",
        reuse_contract="Use as a Turtle trend-following strategy reference and port rules into quant_lab if useful.",
        required_data=("rqalpha_data_bundle", "ohlcv"),
    ),
    "rqalpha_macd": ExternalStrategyTemplate(
        slug="rqalpha_macd",
        source_resource="ricequant_rqalpha",
        family="technical_timing_strategy",
        status="template_ready",
        local_path="external_repos/factor_libraries/ricequant_rqalpha/tests/integration_tests/test_backtest_results/test_f_macd.py",
        entry_command="rqalpha test strategy template",
        reuse_contract="Use as a MACD strategy reference for local timing strategy generation.",
        required_data=("rqalpha_data_bundle", "ohlcv"),
    ),
    "pead_dynamic_gap": ExternalStrategyTemplate(
        slug="pead_dynamic_gap",
        source_resource="pead_earnings_trade_backtest",
        family="event_gap_strategy",
        status="template_ready_needs_event_data",
        local_path="external_repos/factor_libraries/pead_earnings_trade_backtest/scripts/run_dynamic_realistic.py",
        entry_command="python scripts/run_dynamic_realistic.py after configuring project data",
        reuse_contract="Use as PEAD gap/event strategy template once local earnings announcement data exist.",
        required_data=("earnings_announcement_events", "open_close_prices"),
    ),
    "pead_multi_condition": ExternalStrategyTemplate(
        slug="pead_multi_condition",
        source_resource="pead_earnings_trade_backtest",
        family="event_condition_strategy",
        status="template_ready_needs_event_data",
        local_path="external_repos/factor_libraries/pead_earnings_trade_backtest/scripts/analysis/multi_condition_backtest.py",
        entry_command="python scripts/analysis/multi_condition_backtest.py after configuring project data",
        reuse_contract="Use as multi-condition PEAD event-study template.",
        required_data=("earnings_announcement_events", "fundamental_surprise_fields", "prices"),
    ),
}


def get_external_strategy_template(slug: str) -> ExternalStrategyTemplate:
    try:
        return EXTERNAL_STRATEGY_TEMPLATES[slug]
    except KeyError as exc:
        known = ", ".join(sorted(EXTERNAL_STRATEGY_TEMPLATES))
        raise KeyError(f"Unknown external strategy template '{slug}'. Known templates: {known}") from exc


def list_external_strategy_templates(
    family: str | None = None,
    status: str | None = None,
) -> list[ExternalStrategyTemplate]:
    templates: Iterable[ExternalStrategyTemplate] = EXTERNAL_STRATEGY_TEMPLATES.values()
    if family is not None:
        templates = [template for template in templates if template.family == family]
    if status is not None:
        templates = [template for template in templates if template.status == status]
    return list(templates)


def external_strategy_template_summary(
    templates: Iterable[ExternalStrategyTemplate] | None = None,
    project_root: Path | None = None,
) -> list[dict[str, object]]:
    selected = templates if templates is not None else EXTERNAL_STRATEGY_TEMPLATES.values()
    return [template.as_dict(project_root=project_root) for template in selected]
