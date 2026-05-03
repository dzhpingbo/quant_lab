"""Reusable catalog for every archived external factor/strategy resource."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from src.factors.external_libraries import PROJECT_ROOT


@dataclass(frozen=True)
class ReusableExternalResource:
    """One local external resource with an explicit reuse contract."""

    slug: str
    library_slug: str
    resource_type: str
    status: str
    local_path: str
    entry_points: tuple[str, ...]
    capabilities: tuple[str, ...]
    reuse_contract: str
    limitations: str = ""

    def resolve_path(self, project_root: Path | None = None) -> Path:
        root = project_root or PROJECT_ROOT
        return root / self.local_path

    def as_dict(self, project_root: Path | None = None) -> dict[str, object]:
        path = self.resolve_path(project_root)
        return {
            "slug": self.slug,
            "library_slug": self.library_slug,
            "resource_type": self.resource_type,
            "status": self.status,
            "local_path": str(path),
            "exists": path.exists(),
            "entry_points": list(self.entry_points),
            "capabilities": list(self.capabilities),
            "reuse_contract": self.reuse_contract,
            "limitations": self.limitations,
        }


REUSABLE_EXTERNAL_RESOURCES: dict[str, ReusableExternalResource] = {
    "worldquant_alpha101_yli188": ReusableExternalResource(
        slug="worldquant_alpha101_yli188",
        library_slug="worldquant_alpha101",
        resource_type="factor_source",
        status="adapter_backed",
        local_path="external_repos/factor_libraries/worldquant_alpha101_yli188",
        entry_points=("101Alpha_code_1.py", "101Alpha_code_2.py", "101 Formulaic Alphas.pdf"),
        capabilities=("source_backed_alpha101", "price_volume_factor", "formula_reference"),
        reuse_contract="Use `wq_alpha###` names through `compute_external_price_volume_factor_panels` or the VectorBT engine.",
        limitations="Some industry-neutralized/cap-dependent formulas are absent from this public implementation.",
    ),
    "worldquant_alpha101_sthsf": ReusableExternalResource(
        slug="worldquant_alpha101_sthsf",
        library_slug="worldquant_alpha101",
        resource_type="factor_source",
        status="archived_reference",
        local_path="external_repos/factor_libraries/worldquant_alpha101_sthsf",
        entry_points=("src/alpha101.py", "src/alpha101_tmp.py", "src/factor_util.py"),
        capabilities=("alpha101_reference", "formula_source"),
        reuse_contract="Use as a second formula reference; test before direct production import.",
        limitations="Original code uses old pandas idioms and database assumptions.",
    ),
    "alpha360_microsoft_qlib": ReusableExternalResource(
        slug="alpha360_microsoft_qlib",
        library_slug="alpha360_qlib",
        resource_type="factor_and_model_framework",
        status="adapter_backed",
        local_path="external_repos/factor_libraries/alpha360_microsoft_qlib",
        entry_points=("qlib/contrib/data/loader.py", "qlib/contrib/data/handler.py", "examples/benchmarks"),
        capabilities=("qlib_alpha360_360_features", "model_workflow_yaml", "dataset_handler_reference"),
        reuse_contract="Use `qlib360_*` names locally for Alpha360 features; use workflow YAMLs as model-strategy templates.",
        limitations="Full Qlib workflows still require Qlib data initialization and model dependencies.",
    ),
    "gtja_alpha191_selenama": ReusableExternalResource(
        slug="gtja_alpha191_selenama",
        library_slug="gtja_alpha191",
        resource_type="report_and_reference",
        status="adapter_backed_partial",
        local_path="external_repos/factor_libraries/gtja_alpha191_selenama",
        entry_points=("README.md", "files/国泰君安－基于短周期价量特征的多因子选股体系.pdf"),
        capabilities=("gtja_formula_reference", "price_volume_factor"),
        reuse_contract="Use `gtja_alpha###` names through the local adapter; expand formulas from the report as needed.",
        limitations="This repo mainly contains the report/reference, not a full executable 191 implementation.",
    ),
    "tonglian_datayes_424": ReusableExternalResource(
        slug="tonglian_datayes_424",
        library_slug="tonglian_datayes_424",
        resource_type="restricted_data_reference",
        status="requires_auth",
        local_path="external_repos/factor_libraries/tonglian_datayes_424",
        entry_points=("uqer_home.html", "datayes_home.html"),
        capabilities=("vendor_reference",),
        reuse_contract="Use as authorization checklist; add exported DataYes/UQER factor panels under quant_lab data before backtesting.",
        limitations="No complete public 424-factor formulas/data were available.",
    ),
    "fama_french": ReusableExternalResource(
        slug="fama_french",
        library_slug="fama_french",
        resource_type="factor_data",
        status="adapter_backed",
        local_path="external_repos/factor_libraries/fama_french",
        entry_points=("F-F_Research_Data_Factors_daily_CSV.zip", "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip", "F-F_Momentum_Factor_daily_CSV.zip"),
        capabilities=("asset_pricing_time_series", "regime_context", "return_attribution"),
        reuse_contract="Use `load_fama_french_factors`, `load_combined_fama_french_factors`, or `align_fama_french_to_index`.",
        limitations="Time-series factors, not cross-sectional stock-selection factors.",
    ),
    "barra_msci_docs": ReusableExternalResource(
        slug="barra_msci_docs",
        library_slug="barra_msci",
        resource_type="risk_model_reference",
        status="requires_license",
        local_path="external_repos/factor_libraries/barra_msci",
        entry_points=("msci_barra_cne5_factsheet.pdf",),
        capabilities=("risk_model_methodology_reference",),
        reuse_contract="Use as methodology reference; wire licensed MSCI Barra exports into quant_lab when available.",
        limitations="Official Barra engine/data require commercial license.",
    ),
    "barra_like_alphatrading": ReusableExternalResource(
        slug="barra_like_alphatrading",
        library_slug="barra_msci",
        resource_type="risk_model_source",
        status="archived_reference",
        local_path="external_repos/factor_libraries/barra_like_alphatrading",
        entry_points=("README.md",),
        capabilities=("barra_like_proxy", "risk_model_example"),
        reuse_contract="Use as a Barra-like implementation reference, explicitly labeled as a proxy.",
        limitations="Not official MSCI Barra.",
    ),
    "joinquant_jqfactor_analyzer": ReusableExternalResource(
        slug="joinquant_jqfactor_analyzer",
        library_slug="joinquant_builtin",
        resource_type="factor_analysis_toolkit",
        status="archived_reference",
        local_path="external_repos/factor_libraries/joinquant_jqfactor_analyzer",
        entry_points=("jqfactor_analyzer", "jqfactor_analyzer/sample_data/VOL5.csv", "docs/API文档.md"),
        capabilities=("factor_ic_analysis", "quantile_analysis", "sample_factor_data"),
        reuse_contract="Use sample data and APIs as analysis templates; feed quant_lab factor panels into equivalent local analysis.",
        limitations="Platform data access still requires JoinQuant credentials.",
    ),
    "joinquant_jqdatasdk": ReusableExternalResource(
        slug="joinquant_jqdatasdk",
        library_slug="joinquant_builtin",
        resource_type="platform_sdk",
        status="requires_auth",
        local_path="external_repos/factor_libraries/joinquant_jqdatasdk",
        entry_points=("jqdatasdk/alpha101.py", "jqdatasdk/alpha191.py", "jqdatasdk/technical_analysis.py"),
        capabilities=("joinquant_alpha101_api", "joinquant_alpha191_api", "technical_analysis_api"),
        reuse_contract="Use JoinQuant API wrappers once authorized credentials are configured.",
        limitations="API calls require account authentication and network access.",
    ),
    "ricequant_rqalpha": ReusableExternalResource(
        slug="ricequant_rqalpha",
        library_slug="ricequant_builtin",
        resource_type="backtest_engine",
        status="archived_reference",
        local_path="external_repos/factor_libraries/ricequant_rqalpha",
        entry_points=("rqalpha", "examples", "tests/integration_tests/test_backtest_results"),
        capabilities=("rqalpha_engine", "strategy_examples", "backtest_reference"),
        reuse_contract="Use strategy examples as templates; run RQAlpha workflows only after dependencies/data bundle are configured.",
        limitations="Complete RiceQuant data requires account/API or local bundle.",
    ),
    "ricequant_rqalpha_mod_rqdata": ReusableExternalResource(
        slug="ricequant_rqalpha_mod_rqdata",
        library_slug="ricequant_builtin",
        resource_type="platform_data_module",
        status="requires_auth",
        local_path="external_repos/factor_libraries/ricequant_rqalpha_mod_rqdata",
        entry_points=("rqalpha_mod_rqdata",),
        capabilities=("rqdata_bridge",),
        reuse_contract="Use as data bridge when authorized RQData access is configured.",
        limitations="Requires RiceQuant/rqdatac credentials.",
    ),
    "huatai_multifactor_framework_public_alt": ReusableExternalResource(
        slug="huatai_multifactor_framework_public_alt",
        library_slug="huatai_thousand_factor",
        resource_type="multi_factor_framework",
        status="archived_reference",
        local_path="external_repos/factor_libraries/huatai_multifactor_framework_public_alt",
        entry_points=("README.md",),
        capabilities=("multi_factor_backtest_reference",),
        reuse_contract="Use as a public multi-factor framework reference; keep distinct from official Huatai thousand-factor model.",
        limitations="Not the official Huatai model.",
    ),
    "crypto_factors": ReusableExternalResource(
        slug="crypto_factors",
        library_slug="crypto_factor_library",
        resource_type="crypto_factor_reference",
        status="partial",
        local_path="external_repos/factor_libraries/crypto_factors",
        entry_points=("cryptofactors_index.html",),
        capabilities=("crypto_factor_catalog_reference",),
        reuse_contract="Use as reference for crypto factor taxonomy; add real CSV endpoints if found.",
        limitations="Archived UI has empty CSV/TXT links.",
    ),
    "crypto_panda_public_alt": ReusableExternalResource(
        slug="crypto_panda_public_alt",
        library_slug="crypto_factor_library",
        resource_type="crypto_metrics_source",
        status="archived_reference",
        local_path="external_repos/factor_libraries/crypto_panda_public_alt",
        entry_points=("README.md",),
        capabilities=("crypto_metrics_reference",),
        reuse_contract="Use as a crypto metrics adapter reference if crypto assets enter the research universe.",
        limitations="Not directly applicable to A-share ETF constituents.",
    ),
    "pead_earnings_trade_backtest": ReusableExternalResource(
        slug="pead_earnings_trade_backtest",
        library_slug="earnings_announcement_pead",
        resource_type="event_strategy_source",
        status="archived_reference",
        local_path="external_repos/factor_libraries/pead_earnings_trade_backtest",
        entry_points=("scripts",),
        capabilities=("earnings_gap_strategy", "dynamic_position_backtest", "event_study_reference"),
        reuse_contract="Use as a PEAD/event-strategy template once local earnings announcement data are available.",
        limitations="US earnings-oriented project; needs local A-share event mapping.",
    ),
    "pead_harikumar_ganesh": ReusableExternalResource(
        slug="pead_harikumar_ganesh",
        library_slug="earnings_announcement_pead",
        resource_type="event_study_source",
        status="archived_reference",
        local_path="external_repos/factor_libraries/pead_harikumar_ganesh",
        entry_points=("README.md",),
        capabilities=("pead_analysis_reference",),
        reuse_contract="Use as PEAD methodology reference for local event-factor implementation.",
        limitations="Requires earnings announcement data.",
    ),
    "python_package_archives": ReusableExternalResource(
        slug="python_package_archives",
        library_slug="earnings_announcement_pead",
        resource_type="package_archive",
        status="archived_reference",
        local_path="external_repos/factor_libraries/python_package_archives",
        entry_points=("earningspy",),
        capabilities=("earnings_api_package_archive",),
        reuse_contract="Install or inspect package archive only when needed; do not import blindly in production.",
        limitations="Package API/data coverage must be verified before use.",
    ),
}


def get_reusable_external_resource(slug: str) -> ReusableExternalResource:
    try:
        return REUSABLE_EXTERNAL_RESOURCES[slug]
    except KeyError as exc:
        known = ", ".join(sorted(REUSABLE_EXTERNAL_RESOURCES))
        raise KeyError(f"Unknown external resource '{slug}'. Known resources: {known}") from exc


def list_reusable_external_resources(
    library_slug: str | None = None,
    status: str | None = None,
    capability: str | None = None,
) -> list[ReusableExternalResource]:
    resources: Iterable[ReusableExternalResource] = REUSABLE_EXTERNAL_RESOURCES.values()
    if library_slug is not None:
        resources = [resource for resource in resources if resource.library_slug == library_slug]
    if status is not None:
        resources = [resource for resource in resources if resource.status == status]
    if capability is not None:
        resources = [resource for resource in resources if capability in resource.capabilities]
    return list(resources)


def reusable_external_resource_summary(
    resources: Iterable[ReusableExternalResource] | None = None,
    project_root: Path | None = None,
) -> list[dict[str, object]]:
    selected = resources if resources is not None else REUSABLE_EXTERNAL_RESOURCES.values()
    return [resource.as_dict(project_root=project_root) for resource in selected]
