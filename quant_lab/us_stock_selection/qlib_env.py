"""Qlib runtime and data environment diagnostics for the v4 research path."""

from __future__ import annotations

import importlib
import importlib.metadata as importlib_metadata
import importlib.util
import platform
import sys
from pathlib import Path
from typing import Any

from quant_lab.us_stock_selection.utils import (
    PROJECT_ROOT,
    ensure_dir,
    save_json,
    save_text,
)


INSTALL_COMMANDS = [
    "conda run -n aimodel pip install pyqlib numpy==1.26.4",
    "conda run -n aimodel pip install lightgbm xgboost catboost",
    "conda run -n aimodel python -m qlib.cli.data qlib_data --target_dir ~/.qlib/qlib_data/us_data --region us",
]


def default_provider_uri() -> Path:
    """Return the default Qlib US data path."""
    return Path.home() / ".qlib" / "qlib_data" / "us_data"


def check_qlib_environment(
    out_dir: Path | str,
    provider_uri: str | Path | None = None,
    logger: Any | None = None,
) -> dict[str, Any]:
    """Check pyqlib, model libraries, GPU, provider data, and basic Qlib reads."""
    out_path = ensure_dir(out_dir)
    provider_path = Path(provider_uri).expanduser() if provider_uri else default_provider_uri()
    qlib_spec = importlib.util.find_spec("qlib")
    status: dict[str, Any] = {
        "python_executable": sys.executable,
        "python_version": sys.version.replace("\n", " "),
        "platform": platform.platform(),
        "provider_uri": str(provider_path),
        "qlib_installed": bool(qlib_spec),
        "qlib_version": None,
        "qlib_import_ok": False,
        "qlib_data_import_ok": False,
        "qlib_workflow_import_ok": False,
        "alpha158_available": False,
        "alpha360_available": False,
        "provider_exists": provider_path.exists(),
        "provider_readable": False,
        "provider_error": "",
        "instruments_sample_count": 0,
        "lightgbm_available": False,
        "xgboost_available": False,
        "catboost_available": False,
        "sklearn_available": False,
        "torch_available": False,
        "gpu_available": False,
        "runtime_status": "not_installed" if not qlib_spec else "runtime_import_failed",
        "recommended_commands": INSTALL_COMMANDS,
    }

    if qlib_spec:
        try:
            status["qlib_version"] = importlib_metadata.version("pyqlib")
        except Exception:
            status["qlib_version"] = "unknown"
        try:
            import qlib  # noqa: F401

            status["qlib_import_ok"] = True
            status["runtime_status"] = "installed"
        except Exception as exc:
            status["provider_error"] = f"qlib import failed: {exc}"
            if logger:
                logger.warning(status["provider_error"])

        for module_name, key in (
            ("qlib.data", "qlib_data_import_ok"),
            ("qlib.workflow", "qlib_workflow_import_ok"),
        ):
            try:
                importlib.import_module(module_name)
                status[key] = True
            except Exception as exc:
                if logger:
                    logger.warning(f"{module_name} import failed: {exc}")

        try:
            handler_mod = importlib.import_module("qlib.contrib.data.handler")
            status["alpha158_available"] = hasattr(handler_mod, "Alpha158")
            status["alpha360_available"] = hasattr(handler_mod, "Alpha360")
        except Exception as exc:
            if logger:
                logger.warning(f"Alpha handler import failed: {exc}")

    for module_name, key in (
        ("lightgbm", "lightgbm_available"),
        ("xgboost", "xgboost_available"),
        ("catboost", "catboost_available"),
        ("sklearn", "sklearn_available"),
        ("torch", "torch_available"),
    ):
        status[key] = bool(importlib.util.find_spec(module_name))

    if status["torch_available"]:
        try:
            import torch

            status["gpu_available"] = bool(torch.cuda.is_available())
            status["gpu_name"] = torch.cuda.get_device_name(0) if status["gpu_available"] else ""
        except Exception as exc:
            status["gpu_error"] = str(exc)

    if status["qlib_import_ok"] and provider_path.exists():
        try:
            import qlib
            from qlib.config import REG_US
            from qlib.data import D

            qlib.init(provider_uri=str(provider_path), region=REG_US, expression_cache=None, dataset_cache=None)
            instruments = D.instruments("all")
            if isinstance(instruments, list):
                status["instruments_sample_count"] = len(instruments[:1000])
            else:
                status["instruments_sample_count"] = 1
            status["provider_readable"] = True
            status["runtime_status"] = "ready_with_provider"
        except Exception as exc:
            status["provider_error"] = str(exc)
            if logger:
                logger.warning(f"Qlib provider check failed: {exc}")
    elif status["qlib_import_ok"]:
        status["runtime_status"] = "installed_provider_missing"

    save_json(status, out_path / "qlib_env_status.json")
    save_text(build_env_report(status), out_path / "qlib_env_report.md")
    if not status["qlib_installed"] or not status["provider_exists"]:
        save_text(build_setup_instructions(status), PROJECT_ROOT / "outputs" / "us_stock_selection" / "qlib_setup_instructions.md")
    return status


def build_env_report(status: dict[str, Any]) -> str:
    """Build a compact markdown environment report."""
    lines = [
        "# Qlib Environment Check",
        "",
        f"- Python: `{status.get('python_executable')}`",
        f"- Qlib installed: `{status.get('qlib_installed')}`",
        f"- pyqlib version: `{status.get('qlib_version')}`",
        f"- Runtime status: `{status.get('runtime_status')}`",
        f"- Provider URI: `{status.get('provider_uri')}`",
        f"- Provider exists: `{status.get('provider_exists')}`",
        f"- Provider readable: `{status.get('provider_readable')}`",
        f"- Alpha158 available: `{status.get('alpha158_available')}`",
        f"- Alpha360 available: `{status.get('alpha360_available')}`",
        f"- LightGBM/XGBoost/CatBoost: `{status.get('lightgbm_available')}` / `{status.get('xgboost_available')}` / `{status.get('catboost_available')}`",
        f"- GPU available: `{status.get('gpu_available')}`",
        "",
    ]
    if status.get("provider_error"):
        lines.extend(["## Provider Error", "", f"```text\n{status.get('provider_error')}\n```", ""])
    if not status.get("qlib_installed") or not status.get("provider_exists"):
        lines.extend(["## Next Commands", "", *[f"```powershell\n{cmd}\n```" for cmd in status.get("recommended_commands", [])]])
    return "\n".join(lines)


def build_setup_instructions(status: dict[str, Any]) -> str:
    """Write standalone setup instructions when runtime/data are missing."""
    return "\n".join(
        [
            "# Qlib Setup Instructions",
            "",
            "当前环境检查显示 Qlib runtime 或 US provider 数据尚未完全就绪。",
            "",
            "## Windows / aimodel 推荐命令",
            "",
            "```powershell",
            "conda run -n aimodel pip install pyqlib numpy==1.26.4",
            "conda run -n aimodel pip install lightgbm xgboost catboost",
            "conda run -n aimodel python -m qlib.cli.data qlib_data --target_dir ~/.qlib/qlib_data/us_data --region us",
            "conda run -n aimodel python scripts/us_stock_selection/11_qlib_env_check.py",
            "conda run -n aimodel python scripts/us_stock_selection/13_run_qlib_model_lab.py --config configs/us_stock_selection/validation_config.yaml",
            "```",
            "",
            "## 当前诊断摘要",
            "",
            f"- Python: `{status.get('python_executable')}`",
            f"- qlib_installed: `{status.get('qlib_installed')}`",
            f"- provider_exists: `{status.get('provider_exists')}`",
            f"- provider_uri: `{status.get('provider_uri')}`",
            f"- provider_error: `{status.get('provider_error', '')}`",
            "",
            "如果 `python` 默认仍指向 base 环境，请使用 `conda run -n aimodel python ...` 或先激活 `aimodel`。",
        ]
    )
