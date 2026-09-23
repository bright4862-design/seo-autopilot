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

_SUPPORTED_FIXTURES = frozenset({
    "fixbench_grounding_adversarial_v1",
    "fixbench_grounding_v8_preservation_v1",
    "fixbench_grounding_url_scope_v1",
    "fixbench_grounding_nested_scope_v1",
    "fixbench_grounding_identity_scope_v1",
})


def _verified_annotations(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    annotations = payload.get("annotations")
    if isinstance(annotations, list):
        return [item for item in annotations if isinstance(item, dict)]
    return [payload]


def _preservation_projection(payload: dict[str, Any] | None) -> dict[str, Any]:
    annotations = _verified_annotations(payload)
    return {
        "annotation_ids": [str(item.get("annotation_id") or "") for item in annotations],
        "evidence": [
            ref
            for annotation in annotations
            for ref in (annotation.get("evidence") or [])
            if isinstance(ref, dict)
        ],
        "numeric_claims": [
            claim
            for annotation in annotations
            for claim in (annotation.get("numeric_claims") or [])
            if isinstance(claim, dict)
        ],
        "fix_refs": [
            ref
            for annotation in annotations
            for ref in (annotation.get("fix_refs") or [])
            if isinstance(ref, str)
        ],
        "root_cause_refs": [
            ref
            for annotation in annotations
            for ref in (annotation.get("root_cause_refs") or [])
            if isinstance(ref, str)
        ],
        "state_claims": [
            claim
            for annotation in annotations
            for claim in (annotation.get("state_claims") or [])
            if isinstance(claim, dict)
        ],
    }


def _preservation_matches(case: dict[str, Any], payload: dict[str, Any] | None) -> bool:
    expected_evidence = case.get("expect_preserved_evidence")
    projection = _preservation_projection(payload)
    if isinstance(expected_evidence, list):
        observed = [ref.get("url") for ref in projection["evidence"]]
        if observed != expected_evidence:
            return False

    expected = case.get("expect_preserved")
    if expected is None:
        return True
    if not isinstance(expected, dict):
        raise ValueError("invalid FixBench expect_preserved contract")
    unknown = set(expected) - set(projection)
    if unknown:
        raise ValueError("unsupported FixBench preservation field: " + ",".join(sorted(unknown)))
    return all(projection[key] == value for key, value in expected.items())


def _reasons_match(case: dict[str, Any], reasons: list[str]) -> bool:
    expected = case.get("expected_reasons")
    if expected is None:
        return True
    if not isinstance(expected, list) or any(not isinstance(reason, str) for reason in expected):
        raise ValueError("invalid FixBench expected_reasons contract")
    return sorted(set(reasons)) == sorted(set(expected))


def run_fixture(path: str | Path) -> dict[str, Any]:
    fixture_path = Path(path)
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture_version = data.get("fixture_version")
    if fixture_version not in _SUPPORTED_FIXTURES:
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
        case_l2 = case.get("sealed_l2_override", sealed_l2)
        if case_l2 is not None and not isinstance(case_l2, dict):
            raise ValueError("invalid FixBench sealed_l2_override")
        result = verify_grounded_payload(case.get("payload"), sealed_l2=case_l2)
        expected = case.get("expected_status")
        ok = result.status == expected and _reasons_match(case, result.reasons)
        if ok:
            ok = _preservation_matches(case, result.verified_payload)
        passed += int(ok)
        rows.append({
            "name": str(case.get("name") or ""),
            "expected": expected,
            "actual": result.status,
            "reasons": list(result.reasons),
            "passed": ok,
        })
    return {
        "fixbench_version": "fixbench_grounding_v1",
        "fixture_version": fixture_version,
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
