import pandas as pd

from src.factors.safety import SAFETY_FACTORS, composite_safety_score, compute_safety_factor_panel
from src.strategies.safety import (
    BinaryStrategySpec,
    MovingAverageCrossoverSpec,
    RegimeFilteredMASpec,
    average_directional_index,
    defensive_timing_signal,
    moving_average_crossover_signal,
    regime_filtered_ma_signal,
)


def test_safety_factor_panel_and_score_shape():
    dates = pd.date_range("2024-01-01", periods=90, freq="D")
    data = {
        "AAA": pd.DataFrame(
            {
                "open": range(100, 190),
                "high": range(101, 191),
                "low": range(99, 189),
                "close": range(100, 190),
                "volume": [1000 + i for i in range(90)],
            },
            index=dates,
        ),
        "BBB": pd.DataFrame(
            {
                "open": range(200, 110, -1),
                "high": range(201, 111, -1),
                "low": range(199, 109, -1),
                "close": range(200, 110, -1),
                "volume": [2000 + i for i in range(90)],
            },
            index=dates,
        ),
    }

    panels = compute_safety_factor_panel(data)
    score = composite_safety_score(panels)

    assert set(SAFETY_FACTORS).issubset(panels)
    assert list(score.columns) == ["AAA", "BBB"]
    assert score.index.equals(dates)


def test_defensive_timing_signal_uses_safety_filter():
    dates = pd.date_range("2024-01-01", periods=120, freq="D")
    close = pd.Series(range(100, 220), index=dates, dtype=float)
    asset = pd.DataFrame({"open": close, "close": close}, index=dates)
    breadth = pd.DataFrame(
        {
            "breadth_ma20": 0.8,
            "breadth_ma60": 0.8,
            "pool_ret20_median": 0.02,
        },
        index=dates,
    )
    safety_breadth = pd.Series(0.3, index=dates)
    spec = BinaryStrategySpec(
        name="test",
        mom_window=20,
        breadth_buy=0.6,
        breadth_sell=0.5,
        vol_window=20,
        vol_max=1.0,
        safety_buy=0.5,
        safety_sell=0.4,
    )

    signal = defensive_timing_signal(asset, breadth, spec, safety_breadth=safety_breadth)

    assert signal.max() == 0


def test_td9_factors_are_registered_and_bounded():
    dates = pd.date_range("2024-01-01", periods=20, freq="D")
    close = pd.Series(range(100, 80, -1), index=dates, dtype=float)
    data = pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1000,
        },
        index=dates,
    )

    buy = SAFETY_FACTORS["alpha_td9_buy_setup_4_9"].calculate(data)
    sell = SAFETY_FACTORS["alpha_td9_sell_pressure_4_9"].calculate(data)

    assert buy.max() <= 1
    assert buy.iloc[-1] == 1
    assert sell.min() >= -1
    assert sell.iloc[-1] == 0


def test_moving_average_crossover_signal_enters_and_exits():
    dates = pd.date_range("2024-01-01", periods=140, freq="D")
    close = pd.Series(
        list(range(100, 180)) + list(range(180, 120, -1)),
        index=dates,
        dtype=float,
    )
    asset = pd.DataFrame({"open": close, "close": close}, index=dates)
    spec = MovingAverageCrossoverSpec(name="ma_test", fast_window=5, slow_window=20)

    signal = moving_average_crossover_signal(asset, spec)

    assert signal.max() == 1
    assert signal.iloc[-1] == 0


def test_regime_filtered_ma_signal_can_use_adx_filter():
    dates = pd.date_range("2024-01-01", periods=160, freq="D")
    close = pd.Series(
        list(range(100, 220)) + list(range(220, 180, -1)),
        index=dates,
        dtype=float,
    )
    asset = pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
        },
        index=dates,
    )
    spec = RegimeFilteredMASpec(name="regime_test", fast_window=5, slow_window=20, adx_window=14, adx_min=10)

    adx = average_directional_index(asset, 14)
    signal = regime_filtered_ma_signal(asset, spec)

    assert adx.notna().any()
    assert signal.max() == 1
