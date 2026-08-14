"""Regression coverage for Python -> JSON -> JavaScript authority-seal parity."""

from app.scan_job import stable_serialize


def test_integral_floats_serialize_identically_to_javascript_json():
    document = {
        "scan": {
            "health_score": 85.0,
            "ratio": 0.0,
            "ms": 1500.0,
            "large": 1e16,
            "negative_zero": -0.0,
            "non_integral": 72.5,
        }
    }

    assert stable_serialize(document) == (
        '{"scan":{"health_score":85,"large":10000000000000000,'
        '"ms":1500,"negative_zero":0,"non_integral":72.5,"ratio":0}}'
    )


def test_non_finite_floats_still_canonicalize_to_null():
    assert stable_serialize({"nan": float("nan"), "inf": float("inf"), "ninf": float("-inf")}) == (
        '{"inf":null,"nan":null,"ninf":null}'
    )
