#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

EXPECTED_CLASSIFIER = "archetype_classifier_v8_platform_product_routes"
EXPECTED_FINGERPRINT = "430813f2b15afa8f"
EXPECTED_COMMIT = "6904c6376f8bcffeafb3fe87e72ce03a3d6c6be9"
RETRYABLE_HTTP = {408, 425, 429, 500, 502, 503, 504}
NON_HTML_EXTENSIONS = {
    ".avif", ".bmp", ".css", ".csv", ".doc", ".docx", ".eot", ".gif", ".ico",
    ".jpeg", ".jpg", ".js", ".json", ".map", ".md", ".markdown", ".mp3", ".mp4",
    ".pdf", ".png", ".ppt", ".pptx", ".svg", ".tif", ".tiff", ".ttf", ".txt",
    ".wav", ".webm", ".webp", ".woff", ".woff2", ".xls", ".xlsx", ".xml", ".zip",
}
SENSITIVE_KEY_PARTS = (
    "secret", "api_key", "apikey", "token", "authorization", "credential",
    "x_scanner_key", "x-scanner-key", "scanner_api_url",
)
AUTHORITY_KEYS = {
    "archetype_classifier_version",
    "beta_revision_fingerprint",
    "scanner_version",
    "version",
    "scanner_build_revision",
    "review_version",
    "representative_page_version",
    "page_level_asset_evidence_version",
    "orphan_asset_evidence_version",
}
COMMIT_KEYS = {
    "deployed_commit", "source_commit", "git_commit", "git_sha",
    "commit_sha", "revision_commit", "build_commit",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    def write(self, message: str) -> None:
        line = f"{now_utc()} {message}"
        print(line, flush=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def contains_raw_secret(text: str, scanner_key: str, scanner_url: str) -> bool:
    candidates = [scanner_key, scanner_url, scanner_url.rstrip("/")]
    return any(value and value in text for value in candidates)


def sanitize(value: Any, scanner_key: str, scanner_url: str) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if any(part.replace("-", "_") in normalized for part in SENSITIVE_KEY_PARTS):
                cleaned[str(key)] = "[REDACTED]"
            else:
                cleaned[str(key)] = sanitize(item, scanner_key, scanner_url)
        return cleaned
    if isinstance(value, list):
        return [sanitize(item, scanner_key, scanner_url) for item in value]
    if isinstance(value, tuple):
        return [sanitize(item, scanner_key, scanner_url) for item in value]
    if isinstance(value, str):
        text = value
        for secret in (scanner_key, scanner_url, scanner_url.rstrip("/")):
            if secret:
                text = text.replace(secret, "[REDACTED]")
        return text
    return value


def safe_error(exc: BaseException, scanner_key: str, scanner_url: str) -> str:
    return str(sanitize(str(exc), scanner_key, scanner_url))[:800]


def parse_json_bytes(data: bytes) -> tuple[Any | None, str | None]:
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception as exc:
        return None, f"decode_error:{exc.__class__.__name__}"
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, f"non_json_response:{exc.msg}"


def request_json(
    *,
    method: str,
    endpoint: str,
    scanner_key: str,
    scanner_url: str,
    payload: Any | None,
    timeout_seconds: float,
    max_attempts: int,
    phase: str,
) -> tuple[Any | None, dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    last_result: Any | None = None
    headers = {"accept": "application/json"}
    body: bytes | None = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers["content-type"] = "application/json"
    if scanner_key:
        headers["x-scanner-key"] = scanner_key

    for attempt_number in range(1, max(1, max_attempts) + 1):
        started = time.monotonic()
        started_at = now_utc()
        status_code: int | None = None
        error_taxonomy = ""
        error_message = ""
        outcome = "unknown"
        try:
            req = Request(endpoint, data=body, headers=headers, method=method)
            with urlopen(req, timeout=timeout_seconds) as response:
                status_code = int(response.status)
                raw = response.read()
            result, parse_error = parse_json_bytes(raw)
            last_result = result
            if parse_error:
                outcome = "invalid_response"
                error_taxonomy = "infrastructure_invalid_json"
                error_message = parse_error
            elif 200 <= status_code < 300:
                outcome = "success"
            else:
                outcome = "http_failure"
                error_taxonomy = "http_retryable" if status_code in RETRYABLE_HTTP else "http_nonretryable"
                error_message = f"HTTP {status_code}"
        except HTTPError as exc:
            status_code = int(exc.code)
            try:
                raw = exc.read()
            except Exception:
                raw = b""
            result, _ = parse_json_bytes(raw)
            last_result = result
            outcome = "http_failure"
            error_taxonomy = "http_retryable" if status_code in RETRYABLE_HTTP else "http_nonretryable"
            error_message = f"HTTP {status_code}"
        except (TimeoutError, socket.timeout) as exc:
            outcome = "transport_failure"
            error_taxonomy = "timeout"
            error_message = safe_error(exc, scanner_key, scanner_url)
        except URLError as exc:
            outcome = "transport_failure"
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, (TimeoutError, socket.timeout)):
                error_taxonomy = "timeout"
            else:
                error_taxonomy = "network"
            error_message = safe_error(reason, scanner_key, scanner_url)
        except OSError as exc:
            outcome = "transport_failure"
            error_taxonomy = "network"
            error_message = safe_error(exc, scanner_key, scanner_url)
        except Exception as exc:
            outcome = "integration_failure"
            error_taxonomy = "unexpected_client_error"
            error_message = safe_error(exc, scanner_key, scanner_url)

        duration = round(time.monotonic() - started, 3)
        attempt = {
            "attempt": attempt_number,
            "phase": phase,
            "started_at": started_at,
            "finished_at": now_utc(),
            "duration_seconds": duration,
            "http_status": status_code,
            "outcome": outcome,
            "error_taxonomy": error_taxonomy or None,
            "error": error_message or None,
        }
        attempts.append(attempt)

        if outcome == "success":
            return last_result, {"attempts": attempts, "final_outcome": "success"}

        retryable = (
            error_taxonomy in {"timeout", "network"}
            or status_code in RETRYABLE_HTTP
        )
        if not retryable or attempt_number >= max_attempts:
            break
        time.sleep(min(15, 3 * attempt_number))

    return last_result, {
        "attempts": attempts,
        "final_outcome": attempts[-1]["outcome"] if attempts else "not_started",
    }


def walk(value: Any, path: str = "$"):
    yield path, value
    if isinstance(value, dict):
        for key, item in value.items():
            yield from walk(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk(item, f"{path}[{index}]")


def first_nonempty_by_keys(value: Any, keys: set[str]) -> Any | None:
    for _, item in walk(value):
        if not isinstance(item, dict):
            continue
        for key, candidate in item.items():
            if str(key).lower() in keys and candidate not in (None, "", [], {}):
                return candidate
    return None


def collect_authority(value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for _, item in walk(value):
        if not isinstance(item, dict):
            continue
        for key, candidate in item.items():
            lower = str(key).lower()
            if lower in AUTHORITY_KEYS and lower not in result and candidate not in (None, ""):
                result[lower] = candidate
    return result


def collect_commit_candidates(*values: Any) -> list[str]:
    candidates: list[str] = []
    for value in values:
        for _, item in walk(value):
            if not isinstance(item, dict):
                continue
            for key, candidate in item.items():
                if str(key).lower() in COMMIT_KEYS and candidate:
                    text = str(candidate).strip()
                    if text and text not in candidates:
                        candidates.append(text)
    return candidates


def boolish(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "limited", "provisional", "incomplete"}
    if isinstance(value, (int, float)):
        return value != 0
    return False


def extract_bool_flags(value: Any, tokens: tuple[str, ...]) -> dict[str, bool]:
    flags: dict[str, bool] = {}
    for path, item in walk(value):
        if not isinstance(item, dict):
            continue
        for key, candidate in item.items():
            lower = str(key).lower()
            if any(token in lower for token in tokens):
                flags[f"{path}.{key}"] = boolish(candidate)
    return flags


def collect_access_evidence_states(value: Any) -> dict[str, Any]:
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
    preferred_keys = {
        "primary_archetype", "site_archetype", "archetype",
        "business_archetype", "website_archetype",
    }
    for source in (review, scan):
        candidate = first_nonempty_by_keys(source, preferred_keys)
        if isinstance(candidate, str):
            return candidate.strip()
        if isinstance(candidate, dict):
            for key in ("primary", "name", "value", "archetype"):
                if candidate.get(key):
                    return str(candidate[key]).strip()
    return ""


def find_int(value: Any, keys: set[str]) -> int:
    candidate = first_nonempty_by_keys(value, keys)
    try:
        return int(candidate or 0)
    except (TypeError, ValueError):
        return 0


def candidate_fixitems(review: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path, value in walk(review):
        if not isinstance(value, dict):
            continue
        keys = {str(key).lower() for key in value}
        looks_like_fix = bool(
            keys.intersection({"stable_id", "rule"})
            and keys.intersection({
                "title", "recommendation", "current_value", "page_url",
                "affected_pages", "priority", "severity",
            })
        )
        if not looks_like_fix:
            continue
        signature = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        if signature in seen:
            continue
        seen.add(signature)
        item = dict(value)
        item["_source_path"] = path
        items.append(item)
    return items


def urls_from_fixitem(item: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    page_url = item.get("page_url")
    if isinstance(page_url, str) and page_url.strip():
        urls.append(page_url.strip())
    affected = item.get("affected_pages")
    if isinstance(affected, list):
        for value in affected:
            if isinstance(value, str) and value.strip():
                urls.append(value.strip())
            elif isinstance(value, dict):
                for key in ("url", "page_url", "website_url"):
                    if isinstance(value.get(key), str) and value[key].strip():
                        urls.append(value[key].strip())
                        break
    return list(dict.fromkeys(urls))


def non_html_urls(fixitems: list[dict[str, Any]]) -> list[dict[str, str]]:
    bad: list[dict[str, str]] = []
    for item in fixitems:
        identity = str(item.get("stable_id") or item.get("rule") or item.get("title") or item.get("_source_path"))
        for url in urls_from_fixitem(item):
            try:
                suffix = Path(urlparse(url).path.lower()).suffix
            except Exception:
                suffix = ""
            if suffix in NON_HTML_EXTENSIONS:
                bad.append({"fixitem": identity, "url": url, "extension": suffix})
    return bad


def stable_sets(fixitems: list[dict[str, Any]]) -> dict[str, list[str]]:
    stable_ids: set[str] = set()
    severities: set[str] = set()
    groupings: set[str] = set()
    for item in fixitems:
        for key in ("stable_id", "rule"):
            if item.get(key):
                stable_ids.add(str(item[key]))
        for key in ("severity", "priority"):
            if item.get(key):
                severities.add(str(item[key]))
        for key in ("group", "grouping", "group_key", "category", "scope", "title"):
            if item.get(key):
                groupings.add(str(item[key]))
    return {
        "stable_ids": sorted(stable_ids),
        "severities": sorted(severities),
        "groupings": sorted(groupings),
    }


def detect_center_contact_canonical(site: str, fixitems: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if site != "center-street-lending":
        return []
    flagged: list[dict[str, Any]] = []
    for item in fixitems:
        identity = " ".join(
            str(item.get(key) or "")
            for key in ("rule", "stable_id", "title", "scope", "grouping")
        ).lower()
        page_url = str(item.get("page_url") or "")
        path = urlparse(page_url).path.lower() if page_url else ""
        if "canonical" in identity and (path == "/contact" or path.startswith("/contact/")):
            flagged.append({
                "stable_id": item.get("stable_id"),
                "rule": item.get("rule"),
                "title": item.get("title"),
                "page_url": page_url,
            })
    return flagged


def detect_funbooker_429_title(site: str, fixitems: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if site != "funbooker":
        return []
    flagged: list[dict[str, Any]] = []
    for item in fixitems:
        blob = json.dumps(item, ensure_ascii=False, sort_keys=True).lower()
        has_429_evidence = "429" in blob or "rate limit" in blob or "too many requests" in blob
        if not has_429_evidence:
            continue
        title = str(item.get("title") or item.get("recommendation") or "")
        title_lower = title.lower()
        preserves_meaning = "429" in title_lower or "rate" in title_lower or "too many" in title_lower
        if not preserves_meaning:
            flagged.append({
                "stable_id": item.get("stable_id"),
                "rule": item.get("rule"),
                "title": title,
            })
    return flagged


def detect_pretto_zero_fix_state(
    site: str,
    fixitems: list[dict[str, Any]],
    scan: Any,
    review: Any,
) -> dict[str, Any] | None:
    if site != "pretto" or fixitems:
        return None
    blob = (
        json.dumps(scan, ensure_ascii=False, sort_keys=True)
        + "\n"
        + json.dumps(review, ensure_ascii=False, sort_keys=True)
    ).lower()
    bounded_state = any(token in blob for token in (
        "no_high_confidence", "no-high-confidence", "no high-confidence",
        "bounded_no_high_confidence", "no_high_confidence_findings",
    ))
    return {"zero_fix": True, "bounded_no_high_confidence_state_present": bounded_state}


def find_scan_status(scan: Any, review: Any) -> str:
    for source in (review, scan):
        candidate = first_nonempty_by_keys(source, {"scan_status", "status"})
        if isinstance(candidate, str):
            return candidate
    return ""


def summarize_site(
    manifest_record: dict[str, Any],
    scan: Any,
    review: Any,
    scan_transport: dict[str, Any],
    review_transport: dict[str, Any],
    raw_secret_leakage: bool,
) -> dict[str, Any]:
    site = manifest_record["site"]
    expected = manifest_record["expected_archetype"]
    actual = find_primary_archetype(scan, review)
    pages_found = max(
        find_int(scan, {"pages_found", "total_pages_found"}),
        find_int(review, {"pages_found", "total_pages_found"}),
    )
    pages_crawled = max(
        find_int(scan, {"pages_crawled", "pages_scanned"}),
        find_int(review, {"pages_crawled", "pages_scanned"}),
    )
    fixitems = candidate_fixitems(review)
    fallback_flags = {
        **extract_bool_flags(scan, ("fallback",)),
        **extract_bool_flags(review, ("fallback",)),
    }
    provisional_flags = {
        **extract_bool_flags(scan, ("provisional",)),
        **extract_bool_flags(review, ("provisional",)),
    }
    access_flags = {
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
        **extract_bool_flags(scan, ("incomplete",)),
        **extract_bool_flags(review, ("incomplete",)),
    }
    scan_status = find_scan_status(scan, review)
    status_lower = scan_status.lower()
    scan_authority = collect_authority(scan)
    review_authority = collect_authority(review)
    authority_mismatches: list[dict[str, Any]] = []
    authority_missing: list[dict[str, str]] = []
    required_authority = {
        "scan": (
            ("archetype_classifier_version",),
            ("beta_revision_fingerprint",),
            ("scanner_version", "version"),
        ),
        "review": (
            ("archetype_classifier_version",),
            ("beta_revision_fingerprint",),
            ("review_version",),
        ),
    }
    for label, values in (("scan", scan_authority), ("review", review_authority)):
        for alternatives in required_authority[label]:
            if not any(values.get(key) for key in alternatives):
                authority_missing.append({"source": label, "field": "|".join(alternatives)})
        classifier = values.get("archetype_classifier_version")
        fingerprint = values.get("beta_revision_fingerprint")
        if classifier and classifier != EXPECTED_CLASSIFIER:
            authority_mismatches.append({
                "source": label,
                "field": "archetype_classifier_version",
                "actual": classifier,
                "expected": EXPECTED_CLASSIFIER,
            })
        if fingerprint and fingerprint != EXPECTED_FINGERPRINT:
            authority_mismatches.append({
                "source": label,
                "field": "beta_revision_fingerprint",
                "actual": fingerprint,
                "expected": EXPECTED_FINGERPRINT,
            })

    non_html = non_html_urls(fixitems)
    center_flags = detect_center_contact_canonical(site, fixitems)
    funbooker_flags = detect_funbooker_429_title(site, fixitems)
    pretto_state = detect_pretto_zero_fix_state(site, fixitems, scan, review)
    classification_mismatch = bool(actual and actual != expected)

    return {
        "site": site,
        "url": manifest_record["url"],
        "expected_archetype": expected,
        "primary_archetype": actual or None,
        "classification_mismatch": classification_mismatch,
        "classification_unresolved": not bool(actual),
        "pages_found": pages_found,
        "pages_crawled": pages_crawled,
        "hard_cap_compliant": pages_crawled <= 150,
        "scan_status": scan_status or None,
        "provisional": any(provisional_flags.values()) or "provisional" in status_lower,
        "provisional_flags": provisional_flags,
        "access_limited": (
            any(access_flags.values())
            or access_evidence["access_limited"]
            or "limited" in status_lower
        ),
        "access_limited_flags": access_flags,
        "access_evidence": access_evidence,
        "incidental_access_limited": access_evidence["incidental_access_limited"],
        "material_partial_or_blocked_access": access_evidence["material_partial_or_blocked"],
        "incomplete": any(incomplete_flags.values()) or "incomplete" in status_lower,
        "incomplete_flags": incomplete_flags,
        "fallback_used": any(fallback_flags.values()),
        "fallback_flags": fallback_flags,
        "scan_authority": scan_authority,
        "review_authority": review_authority,
        "authority_mismatches": authority_mismatches,
        "authority_missing": authority_missing,
        "stale_or_missing_authority": bool(authority_mismatches or authority_missing),
        "fixitem_count": len(fixitems),
        "fixitem_sets": stable_sets(fixitems),
        "fixitem_evidence": [
            {
                "source_path": item.get("_source_path"),
                "stable_id": item.get("stable_id"),
                "rule": item.get("rule"),
                "severity": item.get("severity"),
                "priority": item.get("priority"),
                "grouping": item.get("grouping") or item.get("group") or item.get("group_key"),
                "scope": item.get("scope"),
                "title": item.get("title"),
                "page_url": item.get("page_url"),
                "affected_pages": item.get("affected_pages"),
            }
            for item in fixitems
        ],
        "non_html_fixitem_evidence": non_html,
        "center_street_contact_canonical_flags": center_flags,
        "funbooker_429_title_flags": funbooker_flags,
        "pretto_zero_fix_state": pretto_state,
        "raw_output_secret_leakage": raw_secret_leakage,
        "scan_transport": scan_transport,
        "review_transport": review_transport,
    }


def markdown_summary(summary: dict[str, Any]) -> str:
    lines = [
        "# Deployed 20-site production validation",
        "",
        f"- Validation ID: `{summary['validation_id']}`",
        f"- Started: `{summary['started_at']}`",
        f"- Finished: `{summary['finished_at']}`",
        f"- Authority gate passed: `{summary['authority_gate']['passed']}`",
        f"- Sites requested: `{summary['sites_requested']}`",
        f"- Site records: `{summary['site_records']}`",
        f"- Failures: `{summary['failure_count']}`",
        f"- Secret leakage flags: `{summary['raw_output_secret_leakage_count']}`",
        "",
        "## Flag totals",
        "",
    ]
    for key, value in summary["flag_totals"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend([
        "",
        "## Per-site integration summary",
        "",
        "| Site | Scan/review | Pages | Archetype | Flags |",
        "|---|---:|---:|---|---|",
    ])
    for record in summary.get("sites", []):
        transport = f"{record['scan_transport']['final_outcome']}/{record['review_transport']['final_outcome']}"
        archetype = record.get("primary_archetype") or "unresolved"
        flags = []
        for key in (
            "classification_mismatch", "classification_unresolved", "fallback_used",
            "stale_or_missing_authority", "provisional", "access_limited", "incomplete",
        ):
            if record.get(key):
                flags.append(key)
        if record.get("incidental_access_limited"):
            flags.append("incidental_access_limited")
        if record.get("material_partial_or_blocked_access"):
            flags.append("material_partial_or_blocked_access")
        if not record.get("hard_cap_compliant", True):
            flags.append("page_cap")
        if record.get("non_html_fixitem_evidence"):
            flags.append("non_html_evidence")
        if record.get("center_street_contact_canonical_flags"):
            flags.append("center_contact_canonical")
        if record.get("funbooker_429_title_flags"):
            flags.append("funbooker_429_title")
        pretto = record.get("pretto_zero_fix_state")
        if pretto and not pretto.get("bounded_no_high_confidence_state_present"):
            flags.append("pretto_zero_fix_state")
        if record.get("raw_output_secret_leakage"):
            flags.append("secret_leakage")
        lines.append(
            f"| {record['site']} | {transport} | {record['pages_crawled']}/{record['pages_found']} "
            f"| {archetype} | {', '.join(flags) or 'none'} |"
        )
    lines.extend([
        "",
        "This report records integration evidence only. Codex owns independent pass/fail validation.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: run_deployed_production_validation.py MANIFEST OUTPUT_DIR", file=sys.stderr)
        return 2

    manifest_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)
    records_dir = output_dir / "records"
    records_dir.mkdir(parents=True, exist_ok=True)
    log = AuditLog(output_dir / "test.log")

    scanner_url = os.getenv("SCANNER_API_URL", "").strip().rstrip("/")
    scanner_key = os.getenv("SCANNER_API_KEY", "").strip()
    started_at = now_utc()

    integration_state = {
        "started_at": started_at,
        "completed": False,
        "authority_gate_passed": False,
        "fatal_error": None,
    }
    dump_json(output_dir / "integration-state.json", integration_state)

    try:
        if not scanner_url or not scanner_key:
            raise RuntimeError("required scanner integration secrets are not configured")
        parsed = urlparse(scanner_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise RuntimeError("scanner integration URL must be an absolute HTTPS URL")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        sites = manifest.get("sites")
        if not isinstance(sites, list) or len(sites) != 20:
            raise RuntimeError("manifest must contain exactly 20 sites")
        expected_orders = list(range(1, 21))
        actual_orders = [int(item.get("order") or 0) for item in sites]
        if actual_orders != expected_orders:
            raise RuntimeError("manifest site order must be exactly 1 through 20")
        if len({item.get("site") for item in sites}) != 20:
            raise RuntimeError("manifest site IDs must be unique")
        dump_json(output_dir / "manifest.json", manifest)
        log.write("Manifest validated: 20 sequential advanced production scans")

        health, health_transport = request_json(
            method="GET",
            endpoint=f"{scanner_url}/health",
            scanner_key="",
            scanner_url=scanner_url,
            payload=None,
            timeout_seconds=45,
            max_attempts=2,
            phase="health",
        )
        revision, revision_transport = request_json(
            method="GET",
            endpoint=f"{scanner_url}/revision",
            scanner_key="",
            scanner_url=scanner_url,
            payload=None,
            timeout_seconds=45,
            max_attempts=2,
            phase="revision",
        )

        raw_health_text = json.dumps(health, ensure_ascii=False, sort_keys=True, default=str)
        raw_revision_text = json.dumps(revision, ensure_ascii=False, sort_keys=True, default=str)
        health_leak = contains_raw_secret(raw_health_text + raw_revision_text, scanner_key, scanner_url)
        sanitized_health = sanitize(health, scanner_key, scanner_url)
        sanitized_revision = sanitize(revision, scanner_key, scanner_url)
        commit_candidates = collect_commit_candidates(health, revision)
        commit_available = bool(commit_candidates)
        commit_matches = not commit_available or EXPECTED_COMMIT in commit_candidates

        authority_gate = {
            "checked_at": now_utc(),
            "health_transport": health_transport,
            "revision_transport": revision_transport,
            "health": sanitized_health,
            "revision": sanitized_revision,
            "expected": {
                "archetype_classifier_version": EXPECTED_CLASSIFIER,
                "beta_revision_fingerprint": EXPECTED_FINGERPRINT,
                "deployed_commit": EXPECTED_COMMIT,
            },
            "actual": {
                "archetype_classifier_version": health.get("archetype_classifier_version") if isinstance(health, dict) else None,
                "beta_revision_fingerprint": (
                    health.get("beta_revision_fingerprint") if isinstance(health, dict) else None
                ),
                "optional_revision_fingerprint": (
                    revision.get("fingerprint") if isinstance(revision, dict) else None
                ),
                "commit_candidates": commit_candidates,
                "commit_marker_available": commit_available,
            },
            "raw_output_secret_leakage": health_leak,
        }
        authority_gate["revision_optional"] = True
        authority_gate["passed"] = bool(
            health_transport.get("final_outcome") == "success"
            and isinstance(health, dict)
            and health.get("archetype_classifier_version") == EXPECTED_CLASSIFIER
            and health.get("beta_revision_fingerprint") == EXPECTED_FINGERPRINT
            and commit_matches
            and not health_leak
        )
        dump_json(output_dir / "authority-gate.json", authority_gate)

        if not authority_gate["passed"]:
            log.write("Authority gate failed; no production scans were started")
            integration_state.update({
                "completed": True,
                "authority_gate_passed": False,
                "fatal_error": "authority_gate_failed",
                "finished_at": now_utc(),
            })
            dump_json(output_dir / "integration-state.json", integration_state)
            summary = {
                "validation_id": manifest.get("validation_id"),
                "started_at": started_at,
                "finished_at": now_utc(),
                "authority_gate": authority_gate,
                "sites_requested": 20,
                "site_records": 0,
                "failure_count": 0,
                "raw_output_secret_leakage_count": int(health_leak),
                "flag_totals": {},
                "sites": [],
                "integration_execution_success": False,
            }
            dump_json(output_dir / "summary.json", summary)
            (output_dir / "summary.md").write_text(markdown_summary(summary), encoding="utf-8")
            return 1

        log.write("Authority gate passed; starting sequential production validation")
        integration_state["authority_gate_passed"] = True
        dump_json(output_dir / "integration-state.json", integration_state)

        site_summaries: list[dict[str, Any]] = []
        failure_records: list[dict[str, Any]] = []
        raw_leakage_count = int(health_leak)

        for manifest_record in sites:
            site = str(manifest_record["site"])
            log.write(f"{site}: scan started")
            site_started = now_utc()
            scan_payload = {
                "website_url": manifest_record["url"],
                "scan_mode": "advanced",
            }
            scan_raw, scan_transport = request_json(
                method="POST",
                endpoint=f"{scanner_url}/scan",
                scanner_key=scanner_key,
                scanner_url=scanner_url,
                payload=scan_payload,
                timeout_seconds=330,
                max_attempts=2,
                phase="scan",
            )
            scan_text = json.dumps(scan_raw, ensure_ascii=False, sort_keys=True, default=str)
            scan_leak = contains_raw_secret(scan_text, scanner_key, scanner_url)
            scan = sanitize(scan_raw, scanner_key, scanner_url)
            if scan_leak:
                raw_leakage_count += 1

            if scan_transport.get("final_outcome") != "success" or not isinstance(scan_raw, dict):
                failure = {
                    "site": site,
                    "url": manifest_record["url"],
                    "phase": "scan",
                    "started_at": site_started,
                    "finished_at": now_utc(),
                    "transport": scan_transport,
                    "sanitized_response": scan,
                    "error_taxonomy": (
                        scan_transport.get("attempts", [{}])[-1].get("error_taxonomy")
                        if scan_transport.get("attempts") else "scan_failed"
                    ),
                    "raw_output_secret_leakage": scan_leak,
                }
                failure_records.append(failure)
                append_jsonl(output_dir / "failures.jsonl", failure)
                dump_json(records_dir / f"{site}.json", {
                    "manifest": manifest_record,
                    "failure": failure,
                })
                log.write(f"{site}: scan did not complete; review skipped")
                continue

            log.write(f"{site}: review started")
            review_payload = dict(scan_raw)
            review_payload.setdefault("website_url", manifest_record["url"])
            review_raw, review_transport = request_json(
                method="POST",
                endpoint=f"{scanner_url}/review",
                scanner_key=scanner_key,
                scanner_url=scanner_url,
                payload=review_payload,
                timeout_seconds=180,
                max_attempts=2,
                phase="review",
            )
            review_text = json.dumps(review_raw, ensure_ascii=False, sort_keys=True, default=str)
            review_leak = contains_raw_secret(review_text, scanner_key, scanner_url)
            review = sanitize(review_raw, scanner_key, scanner_url)
            if review_leak:
                raw_leakage_count += 1

            if review_transport.get("final_outcome") != "success" or not isinstance(review_raw, dict):
                failure = {
                    "site": site,
                    "url": manifest_record["url"],
                    "phase": "review",
                    "started_at": site_started,
                    "finished_at": now_utc(),
                    "scan_transport": scan_transport,
                    "review_transport": review_transport,
                    "sanitized_scan": scan,
                    "sanitized_review_response": review,
                    "error_taxonomy": (
                        review_transport.get("attempts", [{}])[-1].get("error_taxonomy")
                        if review_transport.get("attempts") else "review_failed"
                    ),
                    "raw_output_secret_leakage": scan_leak or review_leak,
                }
                failure_records.append(failure)
                append_jsonl(output_dir / "failures.jsonl", failure)
                dump_json(records_dir / f"{site}.json", {
                    "manifest": manifest_record,
                    "scan": scan,
                    "failure": failure,
                })
                log.write(f"{site}: review did not complete")
                continue

            site_summary = summarize_site(
                manifest_record,
                scan,
                review,
                scan_transport,
                review_transport,
                scan_leak or review_leak,
            )
            site_summary["started_at"] = site_started
            site_summary["finished_at"] = now_utc()
            site_summaries.append(site_summary)
            dump_json(records_dir / f"{site}.json", {
                "manifest": manifest_record,
                "timestamps": {
                    "started_at": site_started,
                    "finished_at": site_summary["finished_at"],
                },
                "scan_transport": scan_transport,
                "review_transport": review_transport,
                "scan": scan,
                "review": review,
                "validation_summary": site_summary,
            })
            log.write(
                f"{site}: complete pages={site_summary['pages_crawled']} "
                f"archetype={site_summary.get('primary_archetype') or 'unresolved'}"
            )

        if not (output_dir / "failures.jsonl").exists():
            (output_dir / "failures.jsonl").write_text("", encoding="utf-8")

        flag_totals = {
            "classification_mismatch": sum(bool(item.get("classification_mismatch")) for item in site_summaries),
            "classification_unresolved": sum(bool(item.get("classification_unresolved")) for item in site_summaries),
            "fallback_used": sum(bool(item.get("fallback_used")) for item in site_summaries),
            "stale_or_missing_authority": sum(bool(item.get("stale_or_missing_authority")) for item in site_summaries),
            "incomplete": sum(bool(item.get("incomplete")) for item in site_summaries),
            "provisional": sum(bool(item.get("provisional")) for item in site_summaries),
            "access_limited": sum(bool(item.get("access_limited")) for item in site_summaries),
            "incidental_access_limited": sum(
                bool(item.get("incidental_access_limited")) for item in site_summaries
            ),
            "material_partial_or_blocked_access": sum(
                bool(item.get("material_partial_or_blocked_access")) for item in site_summaries
            ),
            "page_cap_exceeded": sum(not bool(item.get("hard_cap_compliant")) for item in site_summaries),
            "non_html_fixitem_evidence": sum(bool(item.get("non_html_fixitem_evidence")) for item in site_summaries),
            "center_street_contact_canonical": sum(bool(item.get("center_street_contact_canonical_flags")) for item in site_summaries),
            "funbooker_429_title_loss": sum(bool(item.get("funbooker_429_title_flags")) for item in site_summaries),
            "pretto_zero_fix_state_missing": sum(
                bool(item.get("pretto_zero_fix_state"))
                and not bool(item["pretto_zero_fix_state"].get("bounded_no_high_confidence_state_present"))
                for item in site_summaries
            ),
            "raw_output_secret_leakage": raw_leakage_count,
        }

        finished_at = now_utc()
        summary = {
            "validation_id": manifest.get("validation_id"),
            "started_at": started_at,
            "finished_at": finished_at,
            "authority_gate": authority_gate,
            "sites_requested": 20,
            "site_records": len(site_summaries),
            "failure_count": len(failure_records),
            "raw_output_secret_leakage_count": raw_leakage_count,
            "flag_totals": flag_totals,
            "sites": site_summaries,
            "integration_execution_success": True,
            "codex_validation_required": True,
        }
        dump_json(output_dir / "summary.json", summary)
        (output_dir / "summary.md").write_text(markdown_summary(summary), encoding="utf-8")
        integration_state.update({
            "completed": True,
            "authority_gate_passed": True,
            "fatal_error": None,
            "finished_at": finished_at,
            "site_records": len(site_summaries),
            "failure_count": len(failure_records),
        })
        dump_json(output_dir / "integration-state.json", integration_state)
        log.write("Production validation collection finished; Codex validation remains required")
        return 0
    except Exception as exc:
        safe = safe_error(exc, scanner_key, scanner_url)
        log.write(f"Fatal integration error: {safe}")
        integration_state.update({
            "completed": True,
            "fatal_error": safe,
            "finished_at": now_utc(),
        })
        dump_json(output_dir / "integration-state.json", integration_state)
        failure = {
            "site": None,
            "phase": "integration",
            "error_taxonomy": "integration_fatal",
            "error": safe,
            "finished_at": now_utc(),
        }
        append_jsonl(output_dir / "failures.jsonl", failure)
        summary = {
            "validation_id": None,
            "started_at": started_at,
            "finished_at": now_utc(),
            "authority_gate": {"passed": False},
            "sites_requested": 20,
            "site_records": 0,
            "failure_count": 1,
            "raw_output_secret_leakage_count": 0,
            "flag_totals": {},
            "sites": [],
            "integration_execution_success": False,
            "fatal_error": safe,
        }
        dump_json(output_dir / "summary.json", summary)
        (output_dir / "summary.md").write_text(markdown_summary(summary), encoding="utf-8")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
