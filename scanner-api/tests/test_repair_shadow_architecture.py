from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNER_APP = REPO_ROOT / "scanner-api" / "app"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_repair_shadow_is_not_imported_by_scanner_or_review_runtime():
    protected = [
        SCANNER_APP / "scanner.py",
        SCANNER_APP / "main.py",
        SCANNER_APP / "review.py",
    ]

    for path in protected:
        text = _source(path)
        assert "repair_shadow" not in text, f"shadow adapter crossed runtime boundary: {path}"


def test_repair_shadow_is_not_wired_into_authority_or_persistence_handoff():
    protected = [
        REPO_ROOT / "base44" / "functions" / "aiReviewScan" / "entry.ts",
        REPO_ROOT / "base44" / "functions" / "persistScanAuthority" / "index.ts",
    ]

    for path in protected:
        text = _source(path)
        assert "repair_shadow" not in text
        assert "repair_contract_v1_shadow" not in text, f"shadow contract entered authority path: {path}"


def test_production_review_does_not_use_proposed_repair_sorting():
    review_source = _source(SCANNER_APP / "review.py")
    main_source = _source(SCANNER_APP / "main.py")

    for text in (review_source, main_source):
        assert "proposed_customer_order" not in text
        assert "build_shadow_repair_contract" not in text
        assert "build_shadow_review_analysis" not in text
