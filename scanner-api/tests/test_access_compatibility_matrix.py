import json
from pathlib import Path

from app.access_compatibility_policy import assess_access


REPO_ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = REPO_ROOT / "tests" / "fixtures" / "access-compatibility-research-matrix-20260913.json"


def _matrix() -> dict:
    return json.loads(MATRIX_PATH.read_text())


def test_real_site_matrix_stays_fail_closed_until_exact_observer_evidence_exists():
    matrix = _matrix()
    sites = matrix["real_sites"]

    assert sites
    assert {row["site"] for row in sites} >= {
        "ironwoodcrecapital.com",
        "rbiprivatelending.com",
        "klook.com",
        "feverup.com",
        "ratp.fr",
        "viator.com",
        "winamax.fr",
        "funbooker.com",
    }

    for row in sites:
        if row["observer_status"] != "complete":
            assert row["normalized_inputs"] is None, row["site"]
            assert row["expected_policy"] is None, row["site"]
            assert row["root_cause_confidence"] in {
                "unproven",
                "not_applicable_control",
            }, row["site"]


def test_synthetic_matrix_matches_access_policy_contract():
    matrix = _matrix()

    for case in matrix["synthetic_policy_cases"]:
        result = assess_access(**case["normalized_inputs"])
        expected = case["expected_policy"]
        assert result.failure_kind == expected["failure_kind"], case["name"]
        assert result.identity_sensitivity == expected["identity_sensitivity"], case["name"]
        assert result.owner_action == expected["owner_action"], case["name"]
        assert result.access_strategy == expected["access_strategy"], case["name"]


def test_matrix_does_not_encode_browser_impersonation_as_a_strategy():
    matrix_text = MATRIX_PATH.read_text().lower()

    forbidden = {
        "pretend_to_be_chrome",
        "browser_impersonation",
        "captcha_bypass",
        "proxy_rotation",
        "stealth_evasion",
    }
    for token in forbidden:
        assert token not in matrix_text
