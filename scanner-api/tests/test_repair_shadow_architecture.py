from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNER_APP = REPO_ROOT / "scanner-api" / "app"

SHADOW_MODULE_MARKERS = (
    "repair_identity",
    "repair_integration",
    "repair_persistence_shadow",
    "repair_priority",
    "repair_priority_calibration",
    "repair_shadow",
    "repair_shadow_calibration",
)
SHADOW_CONTRACT_MARKERS = (
    "repair_contract_v1_shadow",
    "repair_contract_v2_shadow_calibrated",
)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_shadow_markers_absent(path: Path) -> None:
    text = _source(path)
    for marker in (*SHADOW_MODULE_MARKERS, *SHADOW_CONTRACT_MARKERS):
        assert marker not in text, f"shadow repair marker {marker!r} crossed runtime boundary: {path}"


def test_repair_calibration_does_not_cross_scanner_or_normal_review_runtime():
    protected = [
        SCANNER_APP / "scanner.py",
        SCANNER_APP / "main.py",
        SCANNER_APP / "review.py",
    ]

    for path in protected:
        _assert_shadow_markers_absent(path)


def test_durable_worker_uses_one_explicit_post_review_contract_boundary():
    worker = _source(SCANNER_APP / "scan_job.py")
    wrapper = _source(SCANNER_APP / "repair_contract_v2.py")
    assert "from .repair_contract_v2 import apply_canonical_repair_contract" in worker
    assert "return apply_canonical_repair_contract(review, result)" in worker
    assert "build_calibrated_shadow_review_analysis" in wrapper
    assert "validate_v2_persistence_candidate" in wrapper
    for marker in ("repair_persistence_shadow", "repair_shadow_calibration", "repair_priority_calibration"):
        assert marker not in worker


def test_repair_shadow_is_not_wired_into_authority_or_persistence_handoff():
    protected = [
        REPO_ROOT / "base44" / "functions" / "aiReviewScan" / "entry.ts",
        REPO_ROOT / "base44" / "functions" / "persistScanAuthority" / "index.ts",
    ]

    for path in protected:
        _assert_shadow_markers_absent(path)


def test_production_review_does_not_use_proposed_repair_sorting():
    protected = [
        SCANNER_APP / "review.py",
        SCANNER_APP / "main.py",
        SCANNER_APP / "scan_job.py",
    ]
    prohibited_calls = (
        "proposed_customer_order",
        "build_shadow_repair_contract",
        "build_shadow_review_analysis",
        "build_calibrated_shadow_review_analysis",
        "validate_v2_persistence_candidate",
    )

    for path in protected:
        text = _source(path)
        for call in prohibited_calls:
            assert call not in text, f"shadow repair call {call!r} crossed runtime boundary: {path}"
