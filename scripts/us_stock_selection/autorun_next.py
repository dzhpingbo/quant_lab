"""Codex engineering entrypoint for the next us_stock_selection research loop.

This script does not call any AI service. It reads project documents to choose
the current engineering stage, then runs the corresponding local scripts.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.us_stock_selection._bootstrap import PROJECT_ROOT


def main() -> None:
    agents = _read(PROJECT_ROOT / "AGENTS.md")
    roadmap = _read(PROJECT_ROOT / "docs" / "US_STOCK_SELECTION_AUTORUN.md")
    next_steps = _read(PROJECT_ROOT / "NEXT_STEPS.md")
    next_lower = next_steps.lower()
    if "long-window" in next_lower or "long window" in next_lower or "更长" in next_steps or "合并半年度" in next_steps:
        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "us_stock_selection" / "30_run_v7_long_window_validation.py"),
            "--config",
            "configs/us_stock_selection/validation_config.yaml",
        ]
        _run_stage_and_publish(cmd)
        return
    if "invalid_due_to_backtest_bug" in next_lower or "dropout 瑙勫垯" in next_steps:
        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "us_stock_selection" / "29_run_v7_dropout_fix_and_audit.py"),
            "--config",
            "configs/us_stock_selection/validation_config.yaml",
        ]
        _run_stage_and_publish(cmd)
        return
    if "v7" in next_lower or "v7" in roadmap.lower():
        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "us_stock_selection" / "27_run_v7_fast_wf.py"),
            "--config",
            "configs/us_stock_selection/validation_config.yaml",
        ]
        _run_stage_and_publish(cmd)
        return
    raise SystemExit("No supported autorun stage found. Review NEXT_STEPS.md and docs/US_STOCK_SELECTION_AUTORUN.md.")


def _run_stage_and_publish(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), text=True, check=False)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)
    bridge_cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "us_stock_selection" / "99_publish_for_chatgpt.py"),
        "--git-push",
    ]
    bridge = subprocess.run(bridge_cmd, cwd=str(PROJECT_ROOT), text=True, check=False)
    if bridge.returncode != 0:
        print("ChatGPT bridge publish failed; run outputs remain available locally.", file=sys.stderr)


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    main()
