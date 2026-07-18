"""Apply the scanner-side corrections from the independent v9 review."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "scanner-api/app/scanner.py"


def replace_once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one scanner anchor, found {count}: {old[:80]!r}")
    return text.replace(old, new, 1)


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    text = replace_once(
        text,
        """    findings: list[dict] = []\n    for members in buckets.values():\n        urls = _unique_nonempty([relative_evidence_url(page) for page in members])\n        if len(urls) < 2:\n            continue\n        title = str(members[0].get(\"title\") or \"\").strip()\n        context = classify_duplicate_title_context(title, urls)\n        details = {\n""",
        """    findings: list[dict] = []\n    for title_key in sorted(buckets):\n        members = buckets[title_key]\n        urls = sorted(_unique_nonempty([relative_evidence_url(page) for page in members]))\n        if len(urls) < 2:\n            continue\n        title = str(members[0].get(\"title\") or \"\").strip()\n        context = classify_duplicate_title_context(title, urls)\n        # Generic fallback titles are owned by build_findings so one affected page\n        # still produces evidence and repeated pages do not create a second bucket card.\n        if context == \"generic_fallback\":\n            continue\n        details = {\n""",
    )
    TARGET.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
