"""Reusable strategy template definitions and parameter grids."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any, Iterable


@dataclass(frozen=True)
class StrategyTemplate:
    name: str
    description: str
    complexity: int
    uses_market_filter: bool = True
    uses_vol_filter: bool = False
    uses_atr_stop: bool = False


DEFAULT_TEMPLATES: dict[str, StrategyTemplate] = {
    "ma_trend": StrategyTemplate(
        name="ma_trend",
        description="Fast/slow moving-average trend with benchmark trend filter.",
        complexity=1,
        uses_market_filter=True,
    ),
    "breakout_atr": StrategyTemplate(
        name="breakout_atr",
        description="Donchian-style breakout with ATR stop.",
        complexity=2,
        uses_market_filter=True,
        uses_atr_stop=True,
    ),
    "momentum_hold": StrategyTemplate(
        name="momentum_hold",
        description="Absolute momentum threshold strategy with cash filter.",
        complexity=1,
        uses_market_filter=True,
    ),
    "rsi_trend": StrategyTemplate(
        name="rsi_trend",
        description="RSI and moving-average hybrid trend/reversal strategy.",
        complexity=2,
        uses_market_filter=True,
    ),
    "combo_guardrail": StrategyTemplate(
        name="combo_guardrail",
        description="Trend + market filter + volatility guardrail + ATR stop.",
        complexity=3,
        uses_market_filter=True,
        uses_vol_filter=True,
        uses_atr_stop=True,
    ),
    "aggressive_breakout": StrategyTemplate(
        name="aggressive_breakout",
        description="Higher-beta trend breakout with volume, volatility, market, and ATR guardrails.",
        complexity=3,
        uses_market_filter=True,
        uses_vol_filter=True,
        uses_atr_stop=True,
    ),
    "trend_takeprofit": StrategyTemplate(
        name="trend_takeprofit",
        description="Dual moving-average trend strategy with simplified take-profit stop ratchet.",
        complexity=3,
        uses_market_filter=True,
        uses_atr_stop=True,
    ),
    "momentum_pullback_reentry": StrategyTemplate(
        name="momentum_pullback_reentry",
        description="Strong momentum pullback re-entry strategy with RSI and ATR exits.",
        complexity=3,
        uses_market_filter=True,
        uses_atr_stop=True,
    ),
    "leveraged_etf_guardrail": StrategyTemplate(
        name="leveraged_etf_guardrail",
        description="Leveraged ETF trend/risk-control template using the unlevered underlying index.",
        complexity=3,
        uses_market_filter=True,
        uses_vol_filter=True,
        uses_atr_stop=True,
    ),
    "ml_signal": StrategyTemplate(
        name="ml_signal",
        description="Predicted edge threshold converted to long/cash signals.",
        complexity=2,
        uses_market_filter=True,
        uses_atr_stop=True,
    ),
}


def expand_template_grid(template_name: str, search_space: dict[str, Any]) -> list[dict[str, Any]]:
    if template_name not in search_space:
        return []
    params = search_space[template_name].get("params", {})
    if not params:
        return [{}]

    names = list(params.keys())
    values: list[Iterable[Any]] = []
    for name in names:
        raw = params[name]
        if isinstance(raw, dict) and {"start", "stop", "step"} <= set(raw):
            values.append(range(int(raw["start"]), int(raw["stop"]) + int(raw["step"]), int(raw["step"])))
        else:
            values.append(list(raw))
    return [dict(zip(names, combo)) for combo in product(*values)]
