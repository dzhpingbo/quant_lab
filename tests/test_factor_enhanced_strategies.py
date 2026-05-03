import numpy as np
import pandas as pd

from src.backtest.portfolio_factory import PortfolioFactory
from src.backtest.signal_factory import SignalFactory
from src.strategies.factor_enhanced import (
    FactorBlendSpec,
    QuantilePortfolioSpec,
    TopKDropoutSpec,
    combine_enhanced_factor_panels,
    ic_weighted_composite,
    quantile_weights_from_score,
    topk_dropout_weights,
    volatility_target_weights,
)


def test_quantile_weights_select_exact_top_and_bottom_counts():
    dates = pd.date_range("2024-01-01", periods=2)
    score = pd.DataFrame(
        {
            "AAA": [5.0, 1.0],
            "BBB": [4.0, 2.0],
            "CCC": [3.0, 3.0],
            "DDD": [2.0, 4.0],
            "EEE": [1.0, 5.0],
        },
        index=dates,
    )

    weights = quantile_weights_from_score(
        score,
        QuantilePortfolioSpec(
            long_quantile=0.2,
            short_quantile=0.2,
            market_neutral=True,
        ),
    )

    assert weights.loc[dates[0], "AAA"] == 0.5
    assert weights.loc[dates[0], "EEE"] == -0.5
    assert int((weights.loc[dates[0]] != 0).sum()) == 2
    np.testing.assert_allclose(weights.abs().sum(axis=1), 1.0)


def test_topk_dropout_limits_rebalance_turnover():
    dates = pd.date_range("2024-01-01", periods=3)
    score = pd.DataFrame(
        {
            "AAA": [5.0, 0.0, 0.0],
            "BBB": [4.0, 5.0, 0.0],
            "CCC": [3.0, 4.0, 5.0],
            "DDD": [2.0, 3.0, 4.0],
            "EEE": [1.0, 2.0, 3.0],
        },
        index=dates,
    )

    weights = topk_dropout_weights(
        score,
        TopKDropoutSpec(top_k=3, n_drop=1, rebalance_freq="D"),
    )

    first = set(weights.columns[weights.loc[dates[0]] > 0])
    second = set(weights.columns[weights.loc[dates[1]] > 0])
    third = set(weights.columns[weights.loc[dates[2]] > 0])

    assert first == {"AAA", "BBB", "CCC"}
    assert second == {"BBB", "CCC", "DDD"}
    assert third == {"CCC", "DDD", "EEE"}
    assert len(first - second) == 1
    assert len(second - third) == 1


def test_weighted_portfolio_does_not_get_same_day_return():
    dates = pd.date_range("2024-01-01", periods=3)
    close = pd.DataFrame({"AAA": [100.0, 200.0, 200.0]}, index=dates)
    target_weights = pd.DataFrame({"AAA": [0.0, 1.0, 1.0]}, index=dates)
    factory = PortfolioFactory(commission_pct=0.0, stamp_tax_pct=0.0)

    nav, returns, executed_weights = factory.run_weighted_portfolio_simple(
        target_weights,
        close,
        rebalance_freq="D",
    )

    assert returns.loc[dates[1]] == 0.0
    assert executed_weights.loc[dates[1], "AAA"] == 0.0
    assert executed_weights.loc[dates[2], "AAA"] == 1.0
    np.testing.assert_allclose(nav.iloc[-1], 1.0)


def test_ic_weighted_composite_uses_lagged_ic_weights():
    dates = pd.date_range("2024-01-01", periods=5)
    assets = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    good = pd.DataFrame([range(5) for _ in dates], index=dates, columns=assets, dtype=float)
    bad = -good
    forward_returns = good.copy()

    score, ic_weights = ic_weighted_composite(
        {"good": good, "bad": bad},
        forward_returns=forward_returns,
        blend_spec=FactorBlendSpec(normalize="rank"),
        lookback=1,
        min_periods=1,
        ic_lag=1,
    )

    assert ic_weights.loc[dates[0], "good"] == 0.5
    assert ic_weights.loc[dates[0], "bad"] == 0.5
    assert ic_weights.loc[dates[1], "good"] > 0
    assert ic_weights.loc[dates[1], "bad"] < 0
    assert score.loc[dates[1], "EEE"] > score.loc[dates[1], "AAA"]


def test_signal_factory_additional_timing_templates():
    dates = pd.date_range("2024-01-01", periods=40)
    close = pd.DataFrame({"AAA": np.arange(100.0, 140.0)}, index=dates)
    factory = SignalFactory()

    dual_mom = factory.dual_momentum_signal(close, lookback=5, top_k=1)
    donchian = factory.donchian_trend_signal(close, entry_window=5, exit_window=3)
    macd = factory.macd_trend_signal(close, fast_window=3, slow_window=6, signal_window=3)

    assert dual_mom.iloc[-1, 0] == 1.0
    assert donchian.iloc[-1, 0] == 1.0
    assert macd.iloc[-1, 0] == 1.0


def test_volatility_target_weights_scales_down_high_vol_portfolio():
    dates = pd.date_range("2024-01-01", periods=40)
    close = pd.DataFrame(
        {"AAA": [100.0 + ((-1) ** i) * i for i in range(40)]},
        index=dates,
    ).abs()
    weights = pd.DataFrame({"AAA": 1.0}, index=dates)

    scaled, leverage = volatility_target_weights(
        weights,
        close,
        target_annual_vol=0.05,
        vol_window=5,
        max_leverage=1.0,
    )

    assert leverage.iloc[-1] < 1.0
    assert scaled.iloc[-1, 0] < 1.0


def test_combine_enhanced_factor_panels_respects_direction():
    dates = pd.date_range("2024-01-01", periods=2)
    panel = pd.DataFrame(
        {"AAA": [1.0, 1.0], "BBB": [2.0, 2.0], "CCC": [3.0, 3.0]},
        index=dates,
    )

    high_good = combine_enhanced_factor_panels({"factor": panel})
    low_good = combine_enhanced_factor_panels(
        {"factor": panel},
        FactorBlendSpec(directions={"factor": "low"}),
    )

    assert high_good.loc[dates[0], "CCC"] > high_good.loc[dates[0], "AAA"]
    assert low_good.loc[dates[0], "CCC"] < low_good.loc[dates[0], "AAA"]
