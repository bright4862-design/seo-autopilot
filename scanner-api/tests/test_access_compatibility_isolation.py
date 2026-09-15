import ast
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1] / "app"
POLICY_MODULE = "access_compatibility_policy"
ALLOWED_POLICY_IMPORT_ROOTS = {"dataclasses", "typing"}


def test_access_compatibility_policy_remains_unwired_during_observer_coordination_hold():
    imported_by = []

    for path in APP_ROOT.glob("*.py"):
        if path.name == f"{POLICY_MODULE}.py":
            continue
        source = path.read_text()
        if POLICY_MODULE in source:
            imported_by.append(path.name)

    assert imported_by == [], (
        "The compatibility policy must remain research-only until the Codex "
        f"observer contract is reviewed; runtime references found in {imported_by}"
    )


def test_access_compatibility_policy_stays_pure_and_cannot_hide_transport_work():
    policy_path = APP_ROOT / f"{POLICY_MODULE}.py"
    tree = ast.parse(policy_path.read_text())
    imported_roots = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])

    assert imported_roots <= ALLOWED_POLICY_IMPORT_ROOTS, (
        "The compatibility policy is classification-only and must not grow "
        "filesystem, environment, HTTP, socket/TLS, subprocess, or other I/O "
        f"dependencies during the observer coordination hold; imports={sorted(imported_roots)}"
    )
