"""Apply the direct corrections from the independent v9 review."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNER = ROOT / "scanner-api/app/scanner.py"
TESTS = ROOT / "scanner-api/tests/test_metadata_title_evidence_v9.py"


def replace_once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one anchor, found {count}: {old[:80]!r}")
    return text.replace(old, new, 1)


def main() -> None:
    scanner = SCANNER.read_text(encoding="utf-8")
    scanner = replace_once(
        scanner,
        """    findings: list[dict] = []\n    for members in buckets.values():\n        urls = _unique_nonempty([relative_evidence_url(page) for page in members])\n        if len(urls) < 2:\n            continue\n        title = str(members[0].get(\"title\") or \"\").strip()\n        context = classify_duplicate_title_context(title, urls)\n        details = {\n""",
        """    findings: list[dict] = []\n    for title_key in sorted(buckets):\n        members = buckets[title_key]\n        urls = sorted(_unique_nonempty([relative_evidence_url(page) for page in members]))\n        if len(urls) < 2:\n            continue\n        title = str(members[0].get(\"title\") or \"\").strip()\n        context = classify_duplicate_title_context(title, urls)\n        # Generic fallback titles are owned by build_findings so one affected page\n        # still produces evidence and repeated pages do not create a second bucket card.\n        if context == \"generic_fallback\":\n            continue\n        details = {\n""",
    )
    SCANNER.write_text(scanner, encoding="utf-8")

    tests = TESTS.read_text(encoding="utf-8")
    tests = replace_once(
        tests,
        """    grouped = group_findings(build_findings(pages) + duplicate_title_findings(pages))\n    fallback = [item for item in grouped if item[\"rule\"] == \"generic_fallback_title\"]\n    assert len(fallback) == 1\n    assert fallback[0][\"non_scoring\"] is True\n    assert fallback[0][\"score_impact\"] == 0\n    assert len(fallback[0][\"affected_pages\"]) == 3\n""",
        """    grouped = group_findings(build_findings(pages) + duplicate_title_findings(pages))\n    fallback = [item for item in grouped if item[\"rule\"] == \"generic_fallback_title\"]\n    affected = [url for item in fallback for url in item[\"affected_pages\"]]\n    assert sorted(affected) == [\"/accessibility\", \"/promotion\", \"/terms\"]\n    assert len(affected) == len(set(affected))\n    assert all(item[\"non_scoring\"] is True for item in fallback)\n    assert all(item[\"score_impact\"] == 0 for item in fallback)\n""",
    )
    TESTS.write_text(tests, encoding="utf-8")


if __name__ == "__main__":
    main()
