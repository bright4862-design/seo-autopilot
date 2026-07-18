"""Align v9 release-marker contracts without changing scanner behavior."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLD = "430813f2b15afa8f"
NEW = "52348dd1f3b77700"


def replace(path: str, old: str, new: str, expected: int = 1) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"{path}: expected {expected} occurrence(s), found {count}")
    target.write_text(text.replace(old, new), encoding="utf-8")


def main() -> None:
    replace("src/lib/scanRunModel.js", OLD, NEW)
    replace("tests/frontend/releaseAuthorityGate.test.mjs", OLD, NEW)
    replace("tests/frontend/scanRunPersistence.test.mjs", OLD, NEW)
    replace("scanner-api/tests/test_observability.py", OLD, NEW, expected=3)
    replace(
        "scanner-api/app/review.py",
        'return f"Add missing meta descriptions to {label} pages" if is_group else "Add a missing meta description to the affected page"',
        'return f"Add missing meta descriptions to {label} pages" if is_group else "Add a meta description to the affected page"',
    )


if __name__ == "__main__":
    main()
