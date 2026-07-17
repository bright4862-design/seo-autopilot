from pathlib import Path

TARGET = Path("scripts/ops/run_deployed_production_validation.py")
text = TARGET.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    text = text.replace(old, new, 1)


replace_once(
    '''        retryable = (
            error_taxonomy in {"timeout", "network", "infrastructure_invalid_json"}
            or status_code in RETRYABLE_HTTP
        )
''',
    '''        retryable = (
            error_taxonomy in {"timeout", "network"}
            or status_code in RETRYABLE_HTTP
        )
''',
    "strict retry policy",
)

replace_once(
    '''def find_primary_archetype(scan: Any, review: Any) -> str:
''',
    '''def collect_access_evidence_states(value: Any) -> dict[str, Any]:
    exact_states: dict[str, str] = {}
    for path, item in walk(value):
        if not isinstance(item, dict):
            continue
        for key, candidate in item.items():
            lower = str(key).strip().lower()
            is_access_state = (
                lower == "access_evidence_state"
                or lower == "evidence_sufficiency"
                or ("access" in lower and ("state" in lower or "sufficiency" in lower))
            )
            if not is_access_state:
                continue
            if isinstance(candidate, str) and candidate.strip():
                exact_states[f"{path}.{key}"] = candidate.strip()
            elif isinstance(candidate, list):
                values = [str(entry).strip() for entry in candidate if str(entry).strip()]
                if values:
                    exact_states[f"{path}.{key}"] = "|".join(values)

    normalized = [state.lower() for state in exact_states.values()]
    incidental = any(
        "incidental_access_limited" in state or "incidental access limited" in state
        for state in normalized
    )
    material_or_partial_or_blocked = any(
        any(token in state for token in (
            "partial_access_limited", "material_access_limited", "blocked",
            "access_denied", "severe_access_limited", "insufficient_access",
        ))
        for state in normalized
    )
    access_limited = any(
        "access_limited" in state
        or "access limited" in state
        or "access_denied" in state
        or "blocked" in state
        for state in normalized
    )
    return {
        "exact_states": exact_states,
        "incidental_access_limited": incidental,
        "material_partial_or_blocked": material_or_partial_or_blocked,
        "access_limited": access_limited,
    }


def find_primary_archetype(scan: Any, review: Any) -> str:
''',
    "access evidence extractor",
)

replace_once(
    '''        looks_like_fix = bool(
            keys.intersection({"stable_id", "rule", "page_url", "affected_pages", "priority", "severity"})
            and keys.intersection({"title", "recommendation", "current_value", "page_url", "affected_pages"})
        )
''',
    '''        looks_like_fix = bool(
            keys.intersection({"stable_id", "rule"})
            and keys.intersection({
                "title", "recommendation", "current_value", "page_url",
                "affected_pages", "priority", "severity",
            })
        )
''',
    "fix item boundary",
)

replace_once(
    '''    access_flags = {
        **extract_bool_flags(scan, ("access_limited", "access-limited", "accesslimited")),
        **extract_bool_flags(review, ("access_limited", "access-limited", "accesslimited")),
    }
    incomplete_flags = {
''',
    '''    access_flags = {
        **extract_bool_flags(scan, ("access_limited", "access-limited", "accesslimited")),
        **extract_bool_flags(review, ("access_limited", "access-limited", "accesslimited")),
    }
    scan_access_evidence = collect_access_evidence_states(scan)
    review_access_evidence = collect_access_evidence_states(review)
    access_evidence = {
        "scan": scan_access_evidence,
        "review": review_access_evidence,
        "incidental_access_limited": (
            scan_access_evidence["incidental_access_limited"]
            or review_access_evidence["incidental_access_limited"]
        ),
        "material_partial_or_blocked": (
            scan_access_evidence["material_partial_or_blocked"]
            or review_access_evidence["material_partial_or_blocked"]
        ),
        "access_limited": (
            scan_access_evidence["access_limited"]
            or review_access_evidence["access_limited"]
        ),
    }
    incomplete_flags = {
''',
    "access evidence integration",
)

replace_once(
    '''        "access_limited": any(access_flags.values()) or "limited" in status_lower,
        "access_limited_flags": access_flags,
        "incomplete": any(incomplete_flags.values()) or "incomplete" in status_lower,
''',
    '''        "access_limited": (
            any(access_flags.values())
            or access_evidence["access_limited"]
            or "limited" in status_lower
        ),
        "access_limited_flags": access_flags,
        "access_evidence": access_evidence,
        "incidental_access_limited": access_evidence["incidental_access_limited"],
        "material_partial_or_blocked_access": access_evidence["material_partial_or_blocked"],
        "incomplete": any(incomplete_flags.values()) or "incomplete" in status_lower,
''',
    "access evidence output",
)

replace_once(
    '''        if not record.get("hard_cap_compliant", True):
            flags.append("page_cap")
''',
    '''        if record.get("incidental_access_limited"):
            flags.append("incidental_access_limited")
        if record.get("material_partial_or_blocked_access"):
            flags.append("material_partial_or_blocked_access")
        if not record.get("hard_cap_compliant", True):
            flags.append("page_cap")
''',
    "access summary flags",
)

replace_once(
    '''                "beta_revision_fingerprint": (
                    health.get("beta_revision_fingerprint") if isinstance(health, dict) else None
                ) or (revision.get("fingerprint") if isinstance(revision, dict) else None),
                "commit_candidates": commit_candidates,
''',
    '''                "beta_revision_fingerprint": (
                    health.get("beta_revision_fingerprint") if isinstance(health, dict) else None
                ),
                "optional_revision_fingerprint": (
                    revision.get("fingerprint") if isinstance(revision, dict) else None
                ),
                "commit_candidates": commit_candidates,
''',
    "health authoritative fingerprint",
)

replace_once(
    '''        authority_gate["passed"] = bool(
            health_transport.get("final_outcome") == "success"
            and revision_transport.get("final_outcome") == "success"
            and isinstance(health, dict)
            and health.get("archetype_classifier_version") == EXPECTED_CLASSIFIER
            and (
                health.get("beta_revision_fingerprint") == EXPECTED_FINGERPRINT
                or (isinstance(revision, dict) and revision.get("fingerprint") == EXPECTED_FINGERPRINT)
            )
            and commit_matches
            and not health_leak
        )
''',
    '''        authority_gate["revision_optional"] = True
        authority_gate["passed"] = bool(
            health_transport.get("final_outcome") == "success"
            and isinstance(health, dict)
            and health.get("archetype_classifier_version") == EXPECTED_CLASSIFIER
            and health.get("beta_revision_fingerprint") == EXPECTED_FINGERPRINT
            and commit_matches
            and not health_leak
        )
''',
    "optional revision authority gate",
)

replace_once(
    '''            "access_limited": sum(bool(item.get("access_limited")) for item in site_summaries),
            "page_cap_exceeded": sum(not bool(item.get("hard_cap_compliant")) for item in site_summaries),
''',
    '''            "access_limited": sum(bool(item.get("access_limited")) for item in site_summaries),
            "incidental_access_limited": sum(
                bool(item.get("incidental_access_limited")) for item in site_summaries
            ),
            "material_partial_or_blocked_access": sum(
                bool(item.get("material_partial_or_blocked_access")) for item in site_summaries
            ),
            "page_cap_exceeded": sum(not bool(item.get("hard_cap_compliant")) for item in site_summaries),
''',
    "access totals",
)

TARGET.write_text(text, encoding="utf-8")
