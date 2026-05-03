# External Resource Reuse Layer

This file records how all archived strategy/factor resources are made reusable
inside quant_lab instead of remaining loose downloads.

## Catalog Entry Points

Factor/resource catalog:

```python
from src.factors import (
    REUSABLE_EXTERNAL_RESOURCES,
    reusable_external_resource_summary,
    list_reusable_external_resources,
)
```

Strategy template catalog:

```python
from src.strategies import (
    EXTERNAL_STRATEGY_TEMPLATES,
    external_strategy_template_summary,
    list_external_strategy_templates,
)
```

Executable panel factors:

```python
from src.factors import (
    list_external_panel_factors,
    compute_external_price_volume_factor_panels,
)
```

## Current Counts

- Reusable local resource records: 18
- External strategy template records: 9
- Directly enumerable external panel factor names: 452
- WorldQuant Alpha101 executable names: 82
- Qlib Alpha360 executable names: 360
- GTJA Alpha191 local executable names: 10
- JoinQuant Alpha101 API names: 101
- JoinQuant Alpha191 API names: 191

## What "Reusable" Means Here

- `adapter_backed`: callable from quant_lab now.
- `template_ready`: can be selected as a strategy/model template; may still need platform data or dependencies to execute in its original engine.
- `requires_auth`: has a standard entry point, but needs authorized vendor credentials.
- `requires_license`: needs commercial license; local files are methodology/reference only.
- `archived_reference`: indexed and documented, intended for porting or reference.

## Snapshots

- `outputs/factor_library_imports/full_reuse_catalog_snapshot_20260416.json`
- `outputs/factor_library_imports/full_reuse_catalog_snapshot_20260416.md`
- `outputs/factor_library_imports/worldquant_source_alpha101_runtime_status_20260416.csv`
- `outputs/factor_library_imports/worldquant_source_alpha101_runtime_status_20260416.md`

## Notes

The catalog makes every downloaded directory discoverable and assigns a reuse
contract. It does not pretend restricted vendor data is available locally.
Restricted sources become reusable once authorized exports/API credentials are
provided and mapped into quant_lab panels.
