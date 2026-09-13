from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1] / "app"
POLICY_MODULE = "access_compatibility_policy"


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
