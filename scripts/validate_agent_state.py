#!/usr/bin/env python3
"""Validate FixList autonomous-agent state using only the Python standard library."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "agent"

ALLOWED_GATE_STATUSES = {"unknown", "pending", "passed", "failed", "blocked", "not_applicable"}
ALLOWED_PRIORITIES = {"P0", "P1", "P2", "P3"}
ALLOWED_QUEUE_STATUSES = {"todo", "in_progress", "blocked", "done", "cancelled"}


def load(name: str):
    path = AGENT / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise AssertionError(f"missing required agent file: {path.relative_to(ROOT)}")
    except json.JSONDecodeError as exc:
        raise AssertionError(f"invalid JSON in {path.relative_to(ROOT)}: {exc}") from exc


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_state(state: dict) -> None:
    require(state.get("schema_version") == 1, "STATE.json schema_version must be 1")
    require(state.get("project") == "FixList", "STATE.json project must be FixList")
    require(state.get("requires_refresh_on_start") is True, "live refresh must be required on start")
    release = state.get("release") or {}
    require(release.get("status") in {"go", "no_go", "unknown"}, "invalid release status")
    require(isinstance(release.get("production_deploy_authorized"), bool), "deploy authorization must be boolean")
    require(isinstance(release.get("merge_authorized"), bool), "merge authorization must be boolean")


def validate_gates(gates_doc: dict, state: dict) -> None:
    require(gates_doc.get("schema_version") == 1, "RELEASE_GATES.json schema_version must be 1")
    gates = gates_doc.get("gates")
    require(isinstance(gates, list) and gates, "release gates must be a non-empty list")
    ids = [gate.get("id") for gate in gates]
    require(len(ids) == len(set(ids)), "release gate ids must be unique")
    for gate in gates:
        require(gate.get("status") in ALLOWED_GATE_STATUSES, f"invalid gate status for {gate.get('id')}")
        require(isinstance(gate.get("required"), bool), f"required must be boolean for {gate.get('id')}")
        require(bool(gate.get("evidence")), f"evidence description required for {gate.get('id')}")

    required = [gate for gate in gates if gate["required"]]
    all_passed = all(gate["status"] == "passed" for gate in required)
    release_status = (state.get("release") or {}).get("status")
    require(release_status != "go" or all_passed, "release cannot be GO while a required gate is not passed")


def validate_queue(queue_doc: dict) -> None:
    require(queue_doc.get("schema_version") == 1, "WORK_QUEUE.json schema_version must be 1")
    items = queue_doc.get("items")
    require(isinstance(items, list), "work queue items must be a list")
    ids = [item.get("id") for item in items]
    require(len(ids) == len(set(ids)), "work queue ids must be unique")
    id_set = set(ids)
    for item in items:
        require(item.get("priority") in ALLOWED_PRIORITIES, f"invalid priority for {item.get('id')}")
        require(item.get("status") in ALLOWED_QUEUE_STATUSES, f"invalid queue status for {item.get('id')}")
        require(isinstance(item.get("requires_owner_approval"), bool), f"approval flag must be boolean for {item.get('id')}")
        for blocker in item.get("blocked_by", []):
            require(blocker in id_set, f"{item.get('id')} references unknown blocker {blocker}")
        if item.get("status") == "done":
            require(not item.get("blocked_by"), f"done item {item.get('id')} cannot remain blocked")


def validate_evals(evals_doc: dict) -> None:
    require(evals_doc.get("schema_version") == 1, "EVALS.json schema_version must be 1")
    scenarios = evals_doc.get("scenarios")
    require(isinstance(scenarios, list) and len(scenarios) >= 5, "at least five autonomy evals are required")
    ids = [item.get("id") for item in scenarios]
    require(len(ids) == len(set(ids)), "eval ids must be unique")
    for item in scenarios:
        require(bool(item.get("scenario")), f"eval scenario missing for {item.get('id')}")
        require(bool(item.get("expected")), f"eval expected result missing for {item.get('id')}")


def main() -> int:
    try:
        state = load("STATE.json")
        gates = load("RELEASE_GATES.json")
        queue = load("WORK_QUEUE.json")
        evals = load("EVALS.json")
        validate_state(state)
        validate_gates(gates, state)
        validate_queue(queue)
        validate_evals(evals)
    except AssertionError as exc:
        print(f"agent-state validation failed: {exc}", file=sys.stderr)
        return 1

    print("agent-state validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
