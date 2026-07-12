from pathlib import Path


SCANNER = Path("scanner-api/app/scanner.py")


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return source.replace(old, new, 1)


text = SCANNER.read_text()

text = replace_once(
    text,
    "from .canonical_validation import validate_canonical_targets\nfrom .redirect_validation import apply_redirect_evidence, fetch_with_redirect_evidence, summarize_redirect_evidence\n",
    "from .canonical_validation import validate_canonical_targets\nfrom .indexability_quality import (\n    annotate_indexability_quality,\n    build_indexability_quality_findings,\n    summarize_indexability_quality,\n)\nfrom .redirect_validation import apply_redirect_evidence, fetch_with_redirect_evidence, summarize_redirect_evidence\n",
    "indexability import",
)

text = replace_once(
    text,
    "        redirect_evidence = summarize_redirect_evidence(pages)\n",
    "        for page in pages:\n            annotate_indexability_quality(page)\n        indexability_quality_evidence = summarize_indexability_quality(pages)\n        redirect_evidence = summarize_redirect_evidence(pages)\n",
    "quality annotation",
)

text = replace_once(
    text,
    '        "canonical_target_evidence": canonical_target_evidence,\n        "redirect_evidence": redirect_evidence,\n        "scan_mode": scan_mode,\n',
    '        "canonical_target_evidence": canonical_target_evidence,\n        "redirect_evidence": redirect_evidence,\n        "indexability_quality_evidence": indexability_quality_evidence,\n        "scan_mode": scan_mode,\n',
    "top-level evidence",
)

text = replace_once(
    text,
    '            "canonical_target_evidence": canonical_target_evidence,\n            "redirect_evidence": redirect_evidence,\n            "render_evidence_version": RENDER_EVIDENCE_VERSION,\n',
    '            "canonical_target_evidence": canonical_target_evidence,\n            "redirect_evidence": redirect_evidence,\n            "indexability_quality_evidence": indexability_quality_evidence,\n            "render_evidence_version": RENDER_EVIDENCE_VERSION,\n',
    "technical evidence",
)

text = replace_once(
    text,
    "        if page_is_redirect_source(page):\n            continue\n        if sitemap_indexability_conflict(page):\n",
    "        if page_is_redirect_source(page):\n            continue\n        quality_findings = build_indexability_quality_findings(page, create_finding)\n        findings.extend(quality_findings)\n        if page.get(\"soft_404_suspected\"):\n            continue\n        if sitemap_indexability_conflict(page):\n",
    "finding integration",
)

text = replace_once(
    text,
    '"internal_link_redirect", "schema"',
    '"internal_link_redirect", "soft_404", "robots_directive_conflict", "noindex_canonical_conflict", "sitemap_canonicalized_url", "schema"',
    "template rules",
)

text = replace_once(
    text,
    '    if rule == "internal_link_redirect":\n        return "Update internal links that pass through redirects"\n    if rule == "sitemap_indexability_conflict":\n',
    '    if rule == "internal_link_redirect":\n        return "Update internal links that pass through redirects"\n    if rule == "soft_404":\n        return "Return real 404 or 410 responses for missing pages"\n    if rule == "robots_directive_conflict":\n        return "Resolve conflicting index and noindex directives"\n    if rule == "noindex_canonical_conflict":\n        return "Choose between noindex and canonical consolidation"\n    if rule == "sitemap_canonicalized_url":\n        return "Replace canonicalized URLs in the sitemap"\n    if rule == "sitemap_indexability_conflict":\n',
    "group titles",
)

SCANNER.write_text(text)
print("Applied indexability quality integration")
