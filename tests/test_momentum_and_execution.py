import numpy as np
import pandas as pd

from src.backtest.portfolio_factory import PortfolioFactory
from src.factors.momentum import PriceMomentum


def test_price_momentum_skip_uses_prior_window():
    close = pd.Series(
        [100.0, 110.0, 121.0, 133.1, 146.41],
        index=pd.date_range("2024-01-01", periods=5),
        name="close",
    )

    factor = PriceMomentum(window=2, skip=1)
    result = factor.calculate(pd.DataFrame({"close": close}))
    expected = close.shift(1).pct_change(2)

    pd.testing.assert_series_equal(result, expected)


def test_portfolio_rebalance_signal_does_not_get_same_day_return():
    dates = pd.date_range("2024-01-01", periods=3)
    close = pd.DataFrame({"AAA": [100.0, 200.0, 200.0]}, index=dates)
    signal = pd.DataFrame({"AAA": [0.0, 1.0, 1.0]}, index=dates)
    factory = PortfolioFactory(commission_pct=0.0, stamp_tax_pct=0.0)

    nav, returns, holdings = factory.run_portfolio_simple(
        signal,
        close,
        rebalance_freq="D",
        max_positions=1,
    )

    assert returns.loc[dates[1]] == 0.0
    assert not holdings.loc[dates[1], "AAA"]
    assert holdings.loc[dates[2], "AAA"]
    np.testing.assert_allclose(nav.iloc[-1], 1.0)
