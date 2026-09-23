"""Offline FixBench gate for grounding attribution/evidence preservation."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNER_API = REPO_ROOT / "scanner-api"
if str(SCANNER_API) not in sys.path:
    sys.path.insert(0, str(SCANNER_API))

from app.grounding_verifier import verify_grounded_payload


def run_fixture(path: str | Path) -> dict[str, Any]:
    fixture_path = Path(path)
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    if data.get("fixture_version") != "fixbench_grounding_adversarial_v1":
        raise ValueError("unsupported FixBench fixture version")
    sealed_l2 = data.get("sealed_l2")
    cases = data.get("cases")
    if not isinstance(sealed_l2, dict) or not isinstance(cases, list) or not cases:
        raise ValueError("invalid FixBench fixture")

    rows = []
    passed = 0
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("invalid FixBench case")
        result = verify_grounded_payload(case.get("payload"), sealed_l2=sealed_l2)
        expected = case.get("expected_status")
        ok = result.status == expected
        preserved = case.get("expect_preserved_evidence")
        if ok and isinstance(preserved, list):
            payload_out = result.verified_payload or {}
            annotations = payload_out.get("annotations") if isinstance(payload_out, dict) else None
            if not isinstance(annotations, list):
                annotations = [payload_out] if isinstance(payload_out, dict) else []
            observed = [
                ref.get("url")
                for annotation in annotations if isinstance(annotation, dict)
                for ref in (annotation.get("evidence") or []) if isinstance(ref, dict)
            ]
            ok = observed == preserved
        passed += int(ok)
        rows.append({"name": str(case.get("name") or ""), "expected": expected, "actual": result.status, "passed": ok})
    return {
        "fixbench_version": "fixbench_grounding_v1",
        "fixture_version": data["fixture_version"],
        "gate_state": "passed" if passed == len(rows) else "failed",
        "passed": passed,
        "total": len(rows),
        "cases": rows,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        raise SystemExit("usage: run_grounding.py <fixture.json>")
    report = run_fixture(argv[1])
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if report["gate_state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
