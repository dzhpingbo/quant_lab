"""
因子库模块

提供六类因子的实现：
- momentum: 动量因子
- reversal: 反转因子
- volatility: 波动率因子
- liquidity: 流动性因子
- quality: 质量因子
- valuation: 估值因子
- safety: 安全因子和公式Alpha候选
"""

from src.factors.base import BaseFactor, FactorRegistry
from src.factors.momentum import MomentumFactor
from src.factors.reversal import ReversalFactor
from src.factors.volatility import VolatilityFactor
from src.factors.liquidity import LiquidityFactor
from src.factors.quality import QualityFactor
from src.factors.valuation import ValuationFactor
from src.factors.safety import SAFETY_FACTORS
from src.factors.external_libraries import (
    EXTERNAL_FACTOR_LIBRARIES,
    ExternalFactorLibrary,
    external_factor_library_summary,
    get_external_factor_library,
    list_external_factor_libraries,
)
from src.factors.external_resource_catalog import (
    REUSABLE_EXTERNAL_RESOURCES,
    ReusableExternalResource,
    get_reusable_external_resource,
    list_reusable_external_resources,
    reusable_external_resource_summary,
)
from src.factors.external_adapters import (
    EXTERNAL_PANEL_FACTOR_SPECS,
    QLIB_ALPHA360_PREFIXED_FACTOR_NAMES,
    WQ_SOURCE_FACTOR_METHODS,
    ExternalPanelFactorSpec,
    align_fama_french_to_index,
    call_joinquant_alpha101_api,
    call_joinquant_alpha191_api,
    compute_alpha101_factor_panels,
    compute_external_price_volume_factor_panels,
    compute_gtja191_factor_panels,
    compute_qlib_alpha360_factor_panels,
    ensure_ohlcv_panels,
    list_external_panel_factors,
    list_joinquant_api_factors,
    load_combined_fama_french_factors,
    load_fama_french_factors,
    probe_worldquant_source_alpha_status,
)

# 注册所有因子
registry = FactorRegistry()

__all__ = [
    "BaseFactor",
    "FactorRegistry",
    "registry",
    "MomentumFactor",
    "ReversalFactor",
    "VolatilityFactor",
    "LiquidityFactor",
    "QualityFactor",
    "ValuationFactor",
    "SAFETY_FACTORS",
    "EXTERNAL_FACTOR_LIBRARIES",
    "ExternalFactorLibrary",
    "external_factor_library_summary",
    "get_external_factor_library",
    "list_external_factor_libraries",
    "REUSABLE_EXTERNAL_RESOURCES",
    "ReusableExternalResource",
    "get_reusable_external_resource",
    "list_reusable_external_resources",
    "reusable_external_resource_summary",
    "EXTERNAL_PANEL_FACTOR_SPECS",
    "QLIB_ALPHA360_PREFIXED_FACTOR_NAMES",
    "WQ_SOURCE_FACTOR_METHODS",
    "ExternalPanelFactorSpec",
    "align_fama_french_to_index",
    "call_joinquant_alpha101_api",
    "call_joinquant_alpha191_api",
    "compute_alpha101_factor_panels",
    "compute_external_price_volume_factor_panels",
    "compute_gtja191_factor_panels",
    "compute_qlib_alpha360_factor_panels",
    "ensure_ohlcv_panels",
    "list_external_panel_factors",
    "list_joinquant_api_factors",
    "load_combined_fama_french_factors",
    "load_fama_french_factors",
    "probe_worldquant_source_alpha_status",
]
