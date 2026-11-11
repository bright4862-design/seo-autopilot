"""Recorded legacy evidence retains its review representation across the cap refactor."""
import hashlib
import json
from pathlib import Path

import pytest

from app.review import run_review


ROOT = Path(__file__).resolve().parents[2]
BASELINE = json.loads((ROOT / "docs/scans/review-baseline-689a7fb.json").read_text())


@pytest.mark.parametrize("fixture", BASELINE["fixtures"], ids=lambda row: row["fixture"])
def test_legacy_recorded_review_bytes_match_immutable_prechange_revision(fixture):
    raw = (ROOT / "tests/fixtures" / fixture["fixture"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == fixture["input_sha256"]
    reviewed = run_review(json.loads(raw))
    encoded = json.dumps(reviewed, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    assert hashlib.sha256(encoded).hexdigest() == fixture["review_sha256"]
