"""Minimal safety-gate self-test for the Codex auth loop.

Run:
  python scripts/agent_loop/test_safety_gate.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from bridge_io import detect_safety_violation, detect_safety_violation_details, load_config


CASES: list[dict[str, Any]] = [
    {
        "id": "A",
        "text": "本轮任务仅限离线量化审计，不要下单，不要连接券商，不要使用 API key，不读取 secret/token/credential，只读取本地项目已有代码和历史输出，生成 CSV、README 和 zip。",
        "expected": [],
    },
    {
        "id": "B",
        "text": "请审计是否存在 API key 使用风险、是否存在实盘交易风险，并在报告中说明禁止事项。",
        "expected": [],
    },
    {
        "id": "C",
        "text": "connect to broker and place order with real money",
        "expected_contains": ["trade_execution_requested", "trade_or_broker_api_requested"],
    },
    {
        "id": "D",
        "text": "read API key from environment and use secret token",
        "expected_contains": ["credential_or_secret_requested"],
    },
    {
        "id": "E",
        "text": "blocked_by_safety_gate 是分类规则之一，当前任务不触发该分类。",
        "expected": [],
    },
]


def main() -> None:
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("scripts/agent_loop/loop_config_auth.yaml")
    config = load_config(config_path)
    results = []
    failed = False
    for case in CASES:
        violations = detect_safety_violation(config, case["text"])
        details = detect_safety_violation_details(config, case["text"])
        ok = True
        if "expected" in case:
            ok = violations == case["expected"]
        if "expected_contains" in case:
            ok = all(item in violations for item in case["expected_contains"])
        failed = failed or not ok
        results.append({"id": case["id"], "ok": ok, "violations": violations, "details": details})
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
