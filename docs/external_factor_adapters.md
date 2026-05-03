# External Factor Adapters

This document records the local adapter layer that turns archived external
factor resources into quant_lab-ready factor panels.

## What Is Ready

The adapter module is:

- `src/factors/external_adapters.py`

It currently exposes:

- 82 executable WorldQuant Alpha101 price-volume factors from the archived public source: `wq_alpha001`, `wq_alpha002`, ..., `wq_alpha101` where the public implementation exists.
- 360 executable Qlib Alpha360 features: `qlib360_CLOSE59`, ..., `qlib360_VOLUME0`.
- 10 executable GTJA Alpha191 price-volume factors: `gtja_alpha001`, ..., `gtja_alpha010`.
- 101 JoinQuant Alpha101 API entry names and 191 JoinQuant Alpha191 API entry names. These require authorized JoinQuant credentials when called.
- Fama-French official ZIP readers for daily/monthly 3-factor, 5-factor, and momentum files.

The VectorBT engine can now receive external price-volume factor names through
the existing `factor_names` argument.

```python
from src.backtest.vbt_engine import VBTBacktestEngine

engine = VBTBacktestEngine(data_dir="data")
result = engine.run_factor_strategy(
    symbols=["000001.SZ", "000002.SZ"],
    factor_names=["wq_alpha018", "qlib360_CLOSE59", "gtja_alpha004"],
    start_date="2023-01-01",
    end_date="2025-12-31",
)
```

## Direct Factor Panel Usage

```python
from src.factors import (
    compute_external_price_volume_factor_panels,
    list_external_panel_factors,
)

print(list_external_panel_factors("worldquant_alpha101"))
print(list_external_panel_factors("alpha360_qlib"))

panels = compute_external_price_volume_factor_panels(
    {
        "open": open_panel,
        "high": high_panel,
        "low": low_panel,
        "close": close_panel,
        "volume": volume_panel,
    },
    ["wq_alpha018", "qlib360_CLOSE59", "gtja_alpha004"],
)
```

The returned value is:

```python
dict[str, pandas.DataFrame]  # factor_name -> date x asset panel
```

## Fama-French Usage

Fama-French factors are time-series asset-pricing factors, not stock-selection
cross-sectional characteristics. Use them for regime context, return
attribution, or timing overlays rather than as same-value cross-sectional ranks.

```python
from src.factors import load_combined_fama_french_factors, align_fama_french_to_index

ff_daily = load_combined_fama_french_factors("daily")
ff_for_local_dates = align_fama_french_to_index(close_panel.index, frequency="daily")
```

## JoinQuant API Usage

The archived JoinQuant SDK exposes full Alpha101/Alpha191 API entry names. These
functions require authorized JoinQuant credentials.

```python
from src.factors import (
    list_joinquant_api_factors,
    call_joinquant_alpha101_api,
    call_joinquant_alpha191_api,
)

alpha101_names = list_joinquant_api_factors("alpha101")
alpha191_names = list_joinquant_api_factors("alpha191")

# Requires authenticated JoinQuant SDK state.
# values = call_joinquant_alpha101_api("alpha_001", enddate="2025-12-31", index="all")
# values = call_joinquant_alpha191_api("alpha_001", code=["000001.XSHE"], end_date="2025-12-31")
```

## Important Limits

- WorldQuant Alpha101 is executable for the 82 formulas present in the downloaded public implementation. Some original 101 formulas are industry-neutralized or cap-dependent and are not present in that source.
- Qlib Alpha360 is fully represented as 360 local price/volume lag features.
- GTJA Alpha191 has full JoinQuant API entry discovery, but only the local no-account executable subset is currently implemented from public formulas.
- Formula orientation must still be validated on local A-share/ETF-pool data.
- All generated signals should be lagged before trading to avoid future leakage.
- Downloaded third-party repos remain archives under `external_repos`; quant_lab
  does not import or execute them directly by default.
- Restricted sources listed in `external_repos/factor_libraries/FAILED_DOWNLOADS.md`
  still need authorized data/API access before they can become real factors.
