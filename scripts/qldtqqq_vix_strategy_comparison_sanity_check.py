from __future__ import annotations

import ast
from pathlib import Path


SCRIPT = Path(__file__).with_name("qldtqqq_vix_strategy_comparison.py")


def main() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(text)
    functions = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    required_strings = [
        "--dry-run",
        "--no-write",
        "--overwrite",
        "DRY_RUN_NO_FILES_WRITTEN",
        "independent_qldtqqq_vix_research",
        "formal_mve2_related",
        "replace_v82_baseline",
        "create_v10",
        "source_run_selection",
        "latest_by_mtime",
        "explicit_input_run",
        "reproducibility_warning",
    ]
    missing_strings = [item for item in required_strings if item not in text]
    missing_functions = [name for name in ["main", "make_zip", "print_dry_run_plan"] if name not in functions]
    if missing_strings or missing_functions:
        raise SystemExit(
            "SANITY_CHECK_FAILED "
            f"missing_strings={missing_strings} missing_functions={missing_functions}"
        )
    print("SANITY_CHECK_OK")


if __name__ == "__main__":
    main()
