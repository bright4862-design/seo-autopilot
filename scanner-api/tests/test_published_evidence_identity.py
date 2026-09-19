"""Observed routes must survive evidence counting, unlike legacy family keys."""
import json
from pathlib import Path

import pytest

from app import repair_coverage

TABLE = json.loads((Path(__file__).resolve().parents[2] / "tests" / "fixtures" /
                    "published-evidence-url-identity.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", TABLE["cases"], ids=lambda case: case["name"])
def test_observed_identity_matches_shared_literal_contract(case):
    key = getattr(repair_coverage, "published_evidence_url_key", None)
    assert callable(key), "published evidence identity interface is missing"
    assert key(case["url"], scan_origin=case.get("scan_origin", "")) == case["expected"]


def test_historical_case_and_slash_folding_is_unchanged():
    assert [repair_coverage.evidence_url_key(url) for url in ["/x", "/x/", "/X"]] == ["/x"] * 3
