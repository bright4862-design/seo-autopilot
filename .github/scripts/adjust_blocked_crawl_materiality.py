from pathlib import Path

path = Path(__file__).with_name("apply_blocked_crawl_contract.py")
text = path.read_text(encoding="utf-8")

old_count = '''    reviewed_count = max(
        int_or_zero(site_fingerprint.get("pages_received")),
        int_or_zero(site_fingerprint.get("pages_crawled")),
    )

    summary ='''
new_count = '''    reviewed_count = max(
        int_or_zero(site_fingerprint.get("pages_received")),
        int_or_zero(site_fingerprint.get("pages_crawled")),
    )
    blocked_ratio = blocked_count / max(1, reviewed_count)
    material_access_limited = rate_limited and not blocked and blocked_ratio >= 0.10

    summary ='''
if old_count not in text:
    raise SystemExit("Reviewed-count anchor not found")
text = text.replace(old_count, new_count, 1)

old_state = '''    access_evidence_state = "blocked" if blocked else "partial_access_limited" if rate_limited else "complete"
    review_confidence_state = (
        "blocked_access_needs_verification"
        if blocked
        else "incomplete_evidence"
        if incomplete
        else "partial_access_needs_verification"
        if rate_limited
        else "complete"
    )
    scan_status = (
        "blocked_or_incomplete"
        if blocked
        else "incomplete_evidence"
        if incomplete
        else "complete_with_access_limitations"
        if rate_limited
        else "complete"
    )
    score_is_provisional = bool(blocked or incomplete or rate_limited)
'''
new_state = '''    access_evidence_state = (
        "blocked"
        if blocked
        else "partial_access_limited"
        if material_access_limited
        else "incidental_access_limited"
        if rate_limited
        else "complete"
    )
    review_confidence_state = (
        "blocked_access_needs_verification"
        if blocked
        else "incomplete_evidence"
        if incomplete
        else "partial_access_needs_verification"
        if material_access_limited
        else "complete_with_incidental_access_checks"
        if rate_limited
        else "complete"
    )
    scan_status = (
        "blocked_or_incomplete"
        if blocked
        else "incomplete_evidence"
        if incomplete
        else "complete_with_access_limitations"
        if material_access_limited
        else "complete"
    )
    score_is_provisional = bool(blocked or incomplete or rate_limited)
'''
if old_state not in text:
    raise SystemExit("Access-state anchor not found")
text = text.replace(old_state, new_state, 1)

path.write_text(text, encoding="utf-8")
