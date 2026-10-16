"""Malformed technical evidence cannot become a stable cross-scan identity."""
from copy import deepcopy

import pytest

from app.repair_identity import build_repair_identity, compare_repair_runs


def repair():
    return {
        "rule": "missing_title",
        "repair_surface": "cms_title_field",
        "remediation_family": "set_title",
        "affected_pages": ["/product"],
    }


@pytest.mark.parametrize("field", ["rule", "repair_surface", "remediation_family"])
@pytest.mark.parametrize("value", [{"private": "source"}, ["cms_field"], True, 42])
def test_non_string_identity_source_cannot_verify_a_disappeared_repair(field, value):
    previous = repair()
    previous[field] = value
    before = deepcopy(previous)
    identity = build_repair_identity(previous)
    assert identity["stable"] is False
    result = compare_repair_runs(previous, [], [{
        "url": "/product", "status_code": 200, "content_type": "text/html", "indexable": True,
    }])
    assert result["state"] == "could_not_verify"
    assert previous == before


@pytest.mark.parametrize("field,alias", [
    ("rule_id", "rule"),
    ("repair_surface", "implementation_surface"),
    ("remediation_family", "recommended_action_family"),
])
@pytest.mark.parametrize("value", [{}, [], False, 0, "   "])
def test_malformed_preferred_identity_is_not_rescued_by_a_valid_alias(field, alias, value):
    previous = repair()
    previous[field] = value
    previous[alias] = "otherwise_valid_alias"
    assert build_repair_identity(previous)["stable"] is False


def test_valid_string_identity_and_supported_aliases_keep_the_same_fingerprint():
    expected = build_repair_identity(repair())
    aliased = {
        "rule_id": "  MISSING_TITLE ",
        "implementation_surface": " CMS_TITLE_FIELD ",
        "recommended_action_family": " SET_TITLE ",
    }
    actual = build_repair_identity(aliased)
    assert expected["stable"] is actual["stable"] is True
    assert expected["fingerprint"] == actual["fingerprint"] == "449f1d37ab0f1cf0004e319d"
