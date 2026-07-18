from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FINGERPRINT = "4a560c34a3d68c6b"
OLD_FINGERPRINT = "52348dd1f3b77700"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, value: str) -> None:
    (ROOT / path).write_text(value, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


path = "scanner-api/app/scanner.py"
text = read(path)
text = replace_once(
    text,
    'priority="medium" if is_seed or status_code in {0, 429} else "high" if status_code >= 500 else "medium",',
    'priority="medium" if is_seed or status_code == 0 else "high" if status_code == 429 or status_code >= 500 else "medium",',
    "preserve 429 severity",
)
write(path, text)

path = "scanner-api/app/review.py"
text = read(path)
text = replace_once(
    text,
    '"health_grade": "Score unavailable" if health_score is None else "Blocked / incomplete" if blocked else "Scan incomplete" if incomplete else "Insufficient evidence" if insufficient else "Strong" if health_score >= 90 else "Good" if health_score >= 80 else "Needs work" if health_score >= 65 else "Major issues",',
    '"health_grade": "Blocked / incomplete" if blocked else "Scan incomplete" if incomplete else "Insufficient evidence" if insufficient else "Score unavailable" if health_score is None else "Strong" if health_score >= 90 else "Good" if health_score >= 80 else "Needs work" if health_score >= 65 else "Major issues",',
    "preserve evidence status labels",
)
write(path, text)

for test_path in (ROOT / "scanner-api/tests").glob("test_*.py"):
    source = test_path.read_text(encoding="utf-8")
    if OLD_FINGERPRINT in source:
        test_path.write_text(source.replace(OLD_FINGERPRINT, FINGERPRINT), encoding="utf-8")

path = "scanner-api/tests/test_review_scoring_gates.py"
text = read(path)
text = replace_once(
    text,
    '    assert result["health_score"] <= 55\n',
    '    assert result["health_score"] is None\n    assert result["health_score_status"] == "insufficient_evidence"\n',
    "incomplete score contract",
)
text = replace_once(
    text,
    '    assert result["health_score"] <= 45\n    assert result["site_fingerprint"]["blocked_or_429_pages"] == 1\n',
    '    assert result["health_score"] is None\n    assert result["health_score_status"] == "insufficient_evidence"\n    assert result["site_fingerprint"]["blocked_or_429_pages"] == 1\n',
    "blocked page score contract",
)
text = replace_once(
    text,
    '    assert result["site_fingerprint"]["blocked_or_429_pages"] == 1\n    assert result["health_score"] <= 45\n',
    '    assert result["site_fingerprint"]["blocked_or_429_pages"] == 1\n    assert result["health_score"] is None\n    assert result["health_score_status"] == "insufficient_evidence"\n',
    "metadata-only blocked score contract",
)
write(path, text)

path = "scanner-api/tests/test_review_presentation_contract.py"
text = read(path)
text = replace_once(
    text,
    '    assert result["health_score"] <= 45\n    assert result["review_input_quality"]["access_evidence_state"] == "blocked"\n',
    '    assert result["health_score"] is None\n    assert result["health_score_status"] == "insufficient_evidence"\n    assert result["review_input_quality"]["access_evidence_state"] == "blocked"\n',
    "fully blocked score contract",
)
write(path, text)

print("Aligned evidence-gate compatibility contracts")
