# Dual Framework Strategy Reuse

This project keeps strategy and factor research reusable across two layers:

- `vectorbt`: fast local factor screening, portfolio construction, and walk-forward tests.
- `Qlib`: model workflow, prediction records, and TopKDropout portfolio analysis.

## Strategy Registry

Reusable strategy specs live in `src.qlib_ext.strategy_bridge`.

Use the same spec name in both engines:

```python
from src.qlib_ext import get_dual_framework_strategy

spec = get_dual_framework_strategy("topk_dropout_50_5")
vectorbt_kwargs = spec.vectorbt_config()
qlib_strategy = spec.qlib_strategy_config()
```

Current shared specs:

- `topk_dropout_50_5`
- `topk_dropout_100_10`
- `quantile_20_long_only`
- `quantile_20_long_short`
- `ic_weighted_topk_dropout_50_5`

## VectorBT Path

Use `VBTBacktestEngine.run_enhanced_factor_strategy` for reusable strategy tests:

```python
result = engine.run_enhanced_factor_strategy(
    symbols=symbols,
    factor_names=["qlib360_CLOSE59", "qlib360_VOLUME0", "wq_alpha001"],
    start_date="2021-01-01",
    end_date="2026-12-31",
    rebalance_freq="W",
    portfolio_method="topk_dropout",
    top_k=50,
    n_drop=5,
    use_ic_weights=True,
)
```

Supported portfolio methods:

- `quantile`
- `alphalens`
- `topk_dropout`

Optional overlays:

- rolling IC factor weighting
- time-series momentum / moving-average / volatility filters
- portfolio volatility targeting

## Qlib Path

Export a workflow YAML:

```powershell
$env:PYTHONPATH='.'
python scripts/export_qlib_workflow_config.py --strategy topk_dropout_50_5 --output configs/qlib/generated_topk50.yaml
```

A ready-to-edit template is available at:

```text
configs/qlib/dual_framework_alpha360_lgb_topk50_drop5.yaml
```

The Qlib workflow uses:

- `qlib.contrib.data.handler.Alpha360`
- `qlib.contrib.model.gbdt.LGBModel`
- `qlib.contrib.strategy.TopkDropoutStrategy`
- `SignalRecord`, `SigAnaRecord`, and `PortAnaRecord`

## Factor Bridge

Qlib Alpha360 is available in both layers:

- vectorbt/local: `compute_qlib_alpha360_factor_panels`, factor names like `qlib360_CLOSE59`
- Qlib workflow: `Alpha360` handler

WorldQuant Alpha101 and GTJA Alpha191 adapters are executable in vectorbt/local research. To use them directly in Qlib workflows, export them into a custom Qlib feature table or implement a matching Qlib handler.
