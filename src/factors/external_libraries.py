"""Catalog of archived external factor libraries.

The entries here point to local archives under ``external_repos``.  They do
not import or execute third-party code; callers can inspect availability and
decide which authorized data/source to load for a concrete research task.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FACTOR_LIBRARY_ROOT = PROJECT_ROOT / "external_repos" / "factor_libraries"


@dataclass(frozen=True)
class ExternalFactorLibrary:
    """Metadata for a downloaded or restricted external factor library."""

    slug: str
    display_name: str
    status: str
    category: str
    local_paths: tuple[str, ...]
    source_urls: tuple[str, ...]
    notes: str
    retry_hint: str = ""

    def resolve_paths(self, project_root: Path | None = None) -> tuple[Path, ...]:
        root = project_root or PROJECT_ROOT
        return tuple(root / path for path in self.local_paths)

    def existing_paths(self, project_root: Path | None = None) -> tuple[Path, ...]:
        return tuple(path for path in self.resolve_paths(project_root) if path.exists())

    @property
    def has_local_archive(self) -> bool:
        return len(self.existing_paths()) > 0

    @property
    def needs_authorization(self) -> bool:
        return self.status in {"requires_auth", "requires_license", "restricted"}

    def as_dict(self, project_root: Path | None = None) -> dict[str, object]:
        paths = self.resolve_paths(project_root)
        return {
            "slug": self.slug,
            "display_name": self.display_name,
            "status": self.status,
            "category": self.category,
            "local_paths": [str(path) for path in paths],
            "existing_paths": [str(path) for path in paths if path.exists()],
            "source_urls": list(self.source_urls),
            "notes": self.notes,
            "retry_hint": self.retry_hint,
        }


EXTERNAL_FACTOR_LIBRARIES: dict[str, ExternalFactorLibrary] = {
    "worldquant_alpha101": ExternalFactorLibrary(
        slug="worldquant_alpha101",
        display_name="WorldQuant Alpha101",
        status="available",
        category="formula_alpha",
        local_paths=(
            "external_repos/factor_libraries/worldquant_alpha101_yli188",
            "external_repos/factor_libraries/worldquant_alpha101_sthsf",
        ),
        source_urls=(
            "https://github.com/yli188/WorldQuant_alpha101_code",
            "https://github.com/STHSF/alpha101",
        ),
        notes="Two public Python implementations were archived. Verify formula orientation and data-field mapping before live use.",
    ),
    "alpha360_qlib": ExternalFactorLibrary(
        slug="alpha360_qlib",
        display_name="Alpha360 / Microsoft Qlib",
        status="available",
        category="multi_factor_handler",
        local_paths=("external_repos/factor_libraries/alpha360_microsoft_qlib",),
        source_urls=("https://github.com/microsoft/qlib",),
        notes="Sparse checkout archived Qlib data handlers/examples/docs. Alpha360 requires Qlib-style data preparation.",
    ),
    "gtja_alpha191": ExternalFactorLibrary(
        slug="gtja_alpha191",
        display_name="Guotai Junan Alpha191",
        status="available",
        category="formula_alpha",
        local_paths=("external_repos/factor_libraries/gtja_alpha191_selenama",),
        source_urls=("https://github.com/SelenaMa9812/Guotai-Junan-191-Alpha",),
        notes="Public implementation archived. A-share limit-up/down and field conventions still need validation in local data.",
    ),
    "tonglian_datayes_424": ExternalFactorLibrary(
        slug="tonglian_datayes_424",
        display_name="Tonglian/DataYes 424",
        status="requires_auth",
        category="fundamental_factor",
        local_paths=("external_repos/factor_libraries/tonglian_datayes_424",),
        source_urls=("https://uqer.io/", "https://www.datayes.com/"),
        notes="Only public homepage snapshots were archived. Complete 424-factor formulas/data were not publicly downloadable.",
        retry_hint="Use an authorized DataYes/UQER account/API, or add a public mirror only if its license is clear.",
    ),
    "fama_french": ExternalFactorLibrary(
        slug="fama_french",
        display_name="Fama-French",
        status="available",
        category="asset_pricing_factor",
        local_paths=("external_repos/factor_libraries/fama_french",),
        source_urls=("https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html",),
        notes="Official 3-factor, 5-factor, and momentum ZIP files were downloaded from Kenneth French's data library.",
    ),
    "barra_msci": ExternalFactorLibrary(
        slug="barra_msci",
        display_name="Barra / MSCI",
        status="requires_license",
        category="risk_model",
        local_paths=(
            "external_repos/factor_libraries/barra_msci",
            "external_repos/factor_libraries/barra_like_alphatrading",
        ),
        source_urls=(
            "https://www.msci.com/documents/10199/2935796a-0a80-4050-934a-12966d1e2518",
            "https://github.com/jerryxyx/AlphaTrading",
        ),
        notes="Public CNE5 fact sheet and an open-source Barra-style example were archived; official Barra engine/data require license.",
        retry_hint="Use licensed MSCI Barra files/API, or keep any substitute clearly labeled as a Barra-like proxy.",
    ),
    "joinquant_builtin": ExternalFactorLibrary(
        slug="joinquant_builtin",
        display_name="JoinQuant built-in",
        status="requires_auth",
        category="platform_factor_sdk",
        local_paths=(
            "external_repos/factor_libraries/joinquant_jqfactor_analyzer",
            "external_repos/factor_libraries/joinquant_jqdatasdk",
        ),
        source_urls=("https://github.com/JoinQuant/jqfactor_analyzer", "https://github.com/JoinQuant/jqdatasdk"),
        notes="SDK/analyzer repos were archived. Complete built-in factor data require JoinQuant credentials.",
        retry_hint="Configure authorized JoinQuant credentials and export factor panels into quant_lab data formats.",
    ),
    "ricequant_builtin": ExternalFactorLibrary(
        slug="ricequant_builtin",
        display_name="RiceQuant built-in",
        status="requires_auth",
        category="platform_factor_sdk",
        local_paths=(
            "external_repos/factor_libraries/ricequant_rqalpha",
            "external_repos/factor_libraries/ricequant_rqalpha_mod_rqdata",
        ),
        source_urls=("https://github.com/ricequant/rqalpha", "https://github.com/ricequant/rqalpha-mod-rqdata"),
        notes="Open-source RQAlpha/RQData modules were archived. Complete built-in factor data require RiceQuant credentials.",
        retry_hint="Configure authorized RiceQuant/rqdatac access; retry rqalpha-mod-rqfactor from RiceQuant's package index if available.",
    ),
    "huatai_thousand_factor": ExternalFactorLibrary(
        slug="huatai_thousand_factor",
        display_name="Huatai thousand-factor / AI hotspot",
        status="not_found_public_full_download",
        category="research_report_factor",
        local_paths=("external_repos/factor_libraries/huatai_multifactor_framework_public_alt",),
        source_urls=("https://github.com/polo2444172276/MultiFactor-Backtesting-Framework", "https://www.htsc.com.cn/"),
        notes="No complete public official Huatai thousand-factor library was found. A public multi-factor framework was archived as an alternative.",
        retry_hint="Search licensed Huatai research attachments or use an explicitly licensed public reproduction.",
    ),
    "crypto_factor_library": ExternalFactorLibrary(
        slug="crypto_factor_library",
        display_name="Crypto factor library",
        status="partial",
        category="crypto_factor",
        local_paths=(
            "external_repos/factor_libraries/crypto_factors",
            "external_repos/factor_libraries/crypto_panda_public_alt",
        ),
        source_urls=("https://wmcclinton.github.io/cryptofactors/ui/index.html", "https://github.com/sjmoran/crypto-panda"),
        notes="Crypto Factors Data Library UI snapshot and a public crypto metrics repository were archived. The UI's CSV/TXT links are currently empty.",
        retry_hint="Find a current mirror for the Crypto Factors Data Library CSV/TXT files, or map crypto-panda metrics into local factor panels.",
    ),
    "earnings_announcement_pead": ExternalFactorLibrary(
        slug="earnings_announcement_pead",
        display_name="Earnings announcement / PEAD",
        status="available",
        category="event_factor",
        local_paths=(
            "external_repos/factor_libraries/pead_earnings_trade_backtest",
            "external_repos/factor_libraries/pead_harikumar_ganesh",
            "external_repos/factor_libraries/python_package_archives",
        ),
        source_urls=(
            "https://github.com/tradermonty/earnings-trade-backtest",
            "https://github.com/Harikumar-Ganesh/Earnings-Analysis-and-Post-Earnings-Announcement-Drift",
            "https://pypi.org/project/earningspy/",
        ),
        notes="Public PEAD/event-study repos and an earningspy package archive were downloaded.",
    ),
}


def get_external_factor_library(slug: str) -> ExternalFactorLibrary:
    """Return one external factor library entry by slug."""

    try:
        return EXTERNAL_FACTOR_LIBRARIES[slug]
    except KeyError as exc:
        known = ", ".join(sorted(EXTERNAL_FACTOR_LIBRARIES))
        raise KeyError(f"Unknown external factor library '{slug}'. Known slugs: {known}") from exc


def list_external_factor_libraries(status: str | None = None) -> list[ExternalFactorLibrary]:
    """List catalog entries, optionally filtered by status."""

    values = list(EXTERNAL_FACTOR_LIBRARIES.values())
    if status is None:
        return values
    return [entry for entry in values if entry.status == status]


def external_factor_library_summary(
    entries: Iterable[ExternalFactorLibrary] | None = None,
    project_root: Path | None = None,
) -> list[dict[str, object]]:
    """Return JSON-serializable catalog rows with resolved local paths."""

    selected = entries if entries is not None else EXTERNAL_FACTOR_LIBRARIES.values()
    return [entry.as_dict(project_root=project_root) for entry in selected]
