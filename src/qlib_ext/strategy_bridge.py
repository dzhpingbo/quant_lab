"""Bridge reusable strategy specs between vectorbt and Qlib workflows.

This module does not import Qlib at runtime.  It emits plain dictionaries that
match Qlib workflow YAML structure, so tests and strategy discovery work even on
machines where `pyqlib` is not installed yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

import yaml


DEFAULT_EXCHANGE_KWARGS: Dict[str, Any] = {
    "limit_threshold": 0.095,
    "deal_price": "close",
    "open_cost": 0.0005,
    "close_cost": 0.0015,
    "min_cost": 5,
}


@dataclass(frozen=True)
class DualFrameworkStrategySpec:
    """One strategy template that has both vectorbt and Qlib execution forms."""

    name: str
    family: str
    description: str
    vectorbt_method: str
    vectorbt_kwargs: Mapping[str, Any] = field(default_factory=dict)
    qlib_strategy_class: str = "TopkDropoutStrategy"
    qlib_strategy_module: str = "qlib.contrib.strategy"
    qlib_strategy_kwargs: Mapping[str, Any] = field(default_factory=dict)
    required_factor_inputs: tuple[str, ...] = ("score",)
    research_refs: tuple[str, ...] = ()

    def vectorbt_config(self, **overrides: Any) -> Dict[str, Any]:
        config = {"portfolio_method": self.vectorbt_method, **dict(self.vectorbt_kwargs)}
        config.update({key: value for key, value in overrides.items() if value is not None})
        return config

    def qlib_strategy_config(self, signal: str = "<PRED>", **overrides: Any) -> Dict[str, Any]:
        kwargs = {"signal": signal, **dict(self.qlib_strategy_kwargs)}
        kwargs.update({key: value for key, value in overrides.items() if value is not None})
        return {
            "class": self.qlib_strategy_class,
            "module_path": self.qlib_strategy_module,
            "kwargs": kwargs,
        }

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "family": self.family,
            "description": self.description,
            "vectorbt_method": self.vectorbt_method,
            "vectorbt_kwargs": dict(self.vectorbt_kwargs),
            "qlib_strategy_class": self.qlib_strategy_class,
            "qlib_strategy_module": self.qlib_strategy_module,
            "qlib_strategy_kwargs": dict(self.qlib_strategy_kwargs),
            "required_factor_inputs": list(self.required_factor_inputs),
            "research_refs": list(self.research_refs),
        }


DUAL_FRAMEWORK_STRATEGIES: Dict[str, DualFrameworkStrategySpec] = {
    "topk_dropout_50_5": DualFrameworkStrategySpec(
        name="topk_dropout_50_5",
        family="rank_portfolio",
        description="Qlib-style top-50 ranking portfolio with five names dropped per rebalance.",
        vectorbt_method="topk_dropout",
        vectorbt_kwargs={"top_k": 50, "n_drop": 5},
        qlib_strategy_kwargs={"topk": 50, "n_drop": 5},
        research_refs=("qlib_topk_dropout",),
    ),
    "topk_dropout_100_10": DualFrameworkStrategySpec(
        name="topk_dropout_100_10",
        family="rank_portfolio",
        description="Broader Qlib-style top-100 ranking portfolio with controlled turnover.",
        vectorbt_method="topk_dropout",
        vectorbt_kwargs={"top_k": 100, "n_drop": 10},
        qlib_strategy_kwargs={"topk": 100, "n_drop": 10},
        research_refs=("qlib_topk_dropout",),
    ),
    "quantile_20_long_only": DualFrameworkStrategySpec(
        name="quantile_20_long_only",
        family="factor_quantile",
        description="Top 20 percent long-only factor quantile portfolio.",
        vectorbt_method="quantile",
        vectorbt_kwargs={"long_quantile": 0.2, "short_quantile": 0.0, "weighting": "equal"},
        qlib_strategy_kwargs={"topk": 50, "n_drop": 5},
        research_refs=("alphalens_quantile",),
    ),
    "quantile_20_long_short": DualFrameworkStrategySpec(
        name="quantile_20_long_short",
        family="factor_quantile",
        description="Top/bottom 20 percent long-short factor spread for vectorbt; Qlib uses TopkDropout for long-side execution.",
        vectorbt_method="quantile",
        vectorbt_kwargs={"long_quantile": 0.2, "short_quantile": 0.2, "weighting": "equal"},
        qlib_strategy_kwargs={"topk": 50, "n_drop": 5},
        research_refs=("alphalens_quantile", "cross_sectional_momentum"),
    ),
    "ic_weighted_topk_dropout_50_5": DualFrameworkStrategySpec(
        name="ic_weighted_topk_dropout_50_5",
        family="dynamic_factor_blend",
        description="Rolling IC-weighted composite score executed through TopKDropout-style ranking.",
        vectorbt_method="topk_dropout",
        vectorbt_kwargs={"top_k": 50, "n_drop": 5, "use_ic_weights": True},
        qlib_strategy_kwargs={"topk": 50, "n_drop": 5},
        required_factor_inputs=("factor_panels", "forward_returns"),
        research_refs=("rank_ic_weighting", "qlib_topk_dropout"),
    ),
}


@dataclass(frozen=True)
class QlibWorkflowSpec:
    """Parameters for a reusable Qlib model + backtest workflow config."""

    provider_uri: str = "./data/qlib_bin"
    region: str = "cn"
    market: str = "csi300"
    benchmark: str = "SH000300"
    start_time: str = "2010-01-01"
    end_time: str = "2026-12-31"
    fit_start_time: str = "2010-01-01"
    fit_end_time: str = "2018-12-31"
    train_segment: tuple[str, str] = ("2010-01-01", "2018-12-31")
    valid_segment: tuple[str, str] = ("2019-01-01", "2020-12-31")
    test_segment: tuple[str, str] = ("2021-01-01", "2026-12-31")
    backtest_start_time: str = "2021-01-01"
    backtest_end_time: str = "2026-12-31"
    account: int = 100000000
    strategy_name: str = "topk_dropout_50_5"
    handler_class: str = "Alpha360"
    handler_module: str = "qlib.contrib.data.handler"
    model_class: str = "LGBModel"
    model_module: str = "qlib.contrib.model.gbdt"
    model_kwargs: Mapping[str, Any] = field(default_factory=lambda: {
        "loss": "mse",
        "learning_rate": 0.0421,
        "num_leaves": 210,
        "max_depth": 8,
        "num_threads": 20,
    })
    label: tuple[str, ...] = ("Ref($close, -2) / Ref($close, -1) - 1",)
    exchange_kwargs: Mapping[str, Any] = field(default_factory=lambda: dict(DEFAULT_EXCHANGE_KWARGS))


def get_dual_framework_strategy(name: str) -> DualFrameworkStrategySpec:
    try:
        return DUAL_FRAMEWORK_STRATEGIES[name]
    except KeyError as exc:
        known = ", ".join(sorted(DUAL_FRAMEWORK_STRATEGIES))
        raise KeyError(f"Unknown dual-framework strategy '{name}'. Known: {known}") from exc


def list_dual_framework_strategies(family: Optional[str] = None) -> list[DualFrameworkStrategySpec]:
    specs: Iterable[DualFrameworkStrategySpec] = DUAL_FRAMEWORK_STRATEGIES.values()
    if family is not None:
        specs = [spec for spec in specs if spec.family == family]
    return list(specs)


def qlib_topk_dropout_strategy_config(
    topk: int = 50,
    n_drop: int = 5,
    signal: str = "<PRED>",
) -> Dict[str, Any]:
    """Return a Qlib TopkDropoutStrategy config dictionary."""

    if topk <= 0:
        raise ValueError("topk must be positive")
    if n_drop < 0:
        raise ValueError("n_drop must be non-negative")
    return {
        "class": "TopkDropoutStrategy",
        "module_path": "qlib.contrib.strategy",
        "kwargs": {"signal": signal, "topk": int(topk), "n_drop": int(n_drop)},
    }


def qlib_alpha360_field_config(
    start_time: str,
    end_time: str,
    fit_start_time: str,
    fit_end_time: str,
    instruments: str,
    label: Iterable[str],
) -> Dict[str, Any]:
    """Return kwargs for Qlib's built-in Alpha360 handler."""

    return {
        "start_time": start_time,
        "end_time": end_time,
        "fit_start_time": fit_start_time,
        "fit_end_time": fit_end_time,
        "instruments": instruments,
        "infer_processors": [],
        "learn_processors": [
            {"class": "DropnaLabel"},
            {"class": "CSRankNorm", "kwargs": {"fields_group": "label"}},
        ],
        "label": list(label),
    }


def build_qlib_workflow_config(spec: Optional[QlibWorkflowSpec] = None) -> Dict[str, Any]:
    """Build a Qlib workflow config that mirrors a dual-framework strategy spec."""

    spec = spec or QlibWorkflowSpec()
    strategy = get_dual_framework_strategy(spec.strategy_name)
    data_handler_config = qlib_alpha360_field_config(
        start_time=spec.start_time,
        end_time=spec.end_time,
        fit_start_time=spec.fit_start_time,
        fit_end_time=spec.fit_end_time,
        instruments=spec.market,
        label=spec.label,
    )
    port_analysis_config = {
        "strategy": strategy.qlib_strategy_config(),
        "backtest": {
            "start_time": spec.backtest_start_time,
            "end_time": spec.backtest_end_time,
            "account": spec.account,
            "benchmark": spec.benchmark,
            "exchange_kwargs": dict(spec.exchange_kwargs),
        },
    }
    return {
        "qlib_init": {"provider_uri": spec.provider_uri, "region": spec.region},
        "market": spec.market,
        "benchmark": spec.benchmark,
        "strategy_name": spec.strategy_name,
        "data_handler_config": data_handler_config,
        "port_analysis_config": port_analysis_config,
        "task": {
            "model": {
                "class": spec.model_class,
                "module_path": spec.model_module,
                "kwargs": dict(spec.model_kwargs),
            },
            "dataset": {
                "class": "DatasetH",
                "module_path": "qlib.data.dataset",
                "kwargs": {
                    "handler": {
                        "class": spec.handler_class,
                        "module_path": spec.handler_module,
                        "kwargs": data_handler_config,
                    },
                    "segments": {
                        "train": list(spec.train_segment),
                        "valid": list(spec.valid_segment),
                        "test": list(spec.test_segment),
                    },
                },
            },
            "record": [
                {
                    "class": "SignalRecord",
                    "module_path": "qlib.workflow.record_temp",
                    "kwargs": {"model": "<MODEL>", "dataset": "<DATASET>"},
                },
                {
                    "class": "SigAnaRecord",
                    "module_path": "qlib.workflow.record_temp",
                    "kwargs": {"ana_long_short": False, "ann_scaler": 252},
                },
                {
                    "class": "PortAnaRecord",
                    "module_path": "qlib.workflow.record_temp",
                    "kwargs": {"config": port_analysis_config},
                },
            ],
        },
    }


def dump_qlib_workflow_config(config: Mapping[str, Any], path: str | Path) -> Path:
    """Write a generated Qlib workflow config to YAML."""

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(dict(config), sort_keys=False, allow_unicode=True), encoding="utf-8")
    return out
