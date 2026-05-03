# Data Migration Map

The legacy data under `D:\dzhwork\quant` has been mirrored into this QuantLab
workspace without deleting or moving the original D drive files.

## Mapping

| Legacy source | QuantLab mirror |
| --- | --- |
| `D:\dzhwork\quant` | `E:\dzhwork\quant\quant_lab\data\external\legacy_quant` |
| `D:\dzhwork\quant\AStock` | `E:\dzhwork\quant\quant_lab\data\external\legacy_quant\AStock` |
| `D:\dzhwork\quant\AStock\20100101_20260407` | `E:\dzhwork\quant\quant_lab\data\external\legacy_quant\AStock\20100101_20260407` |
| `D:\dzhwork\quant\AStock\yf_data` | `E:\dzhwork\quant\quant_lab\data\external\legacy_quant\AStock\yf_data` |
| `D:\dzhwork\quant\AStock\ETF` | `E:\dzhwork\quant\quant_lab\data\external\legacy_quant\AStock\ETF` |
| `D:\dzhwork\quant\NSDQStock` | `E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock` |
| `D:\dzhwork\quant\backtest_results` | `E:\dzhwork\quant\quant_lab\data\external\legacy_quant\backtest_results` |

## Verification

The mirror was checked after copy:

| Path | Files | Size |
| --- | ---: | ---: |
| `D:\dzhwork\quant` | 18,545 | 9.977 GB |
| `E:\dzhwork\quant\quant_lab\data\external\legacy_quant` | 18,545 | 9.977 GB |

Use `configs/env/local.yaml` path keys such as `legacy_astock_daily` and
`legacy_quant_root` for new code instead of hardcoding `D:\dzhwork\quant`.
