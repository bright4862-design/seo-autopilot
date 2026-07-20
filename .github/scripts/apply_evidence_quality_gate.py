from __future__ import annotations

import hashlib
import json
from pathlib import Path

VERSION = "evidence_quality_gate_v1_default_route_dominance"


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement, found {count}: {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


Path("scanner-api/app/evidence_quality.py").write_text('''from __future__ import annotations

from copy import deepcopy
from typing import Any
from urllib.parse import urlparse

from .review import unwrap_scan_payload

EVIDENCE_QUALITY_GATE_VERSION = "evidence_quality_gate_v1_default_route_dominance"

LIMITED_SCAN_STATUSES = {
    "complete_with_access_limitations",
    "incomplete_evidence",
    "inconclusive_insufficient_evidence",
    "blocked_or_incomplete",
}
DEFAULT_ROUTE_EXACT = {
    "/hello-world",
    "/sample-page",
    "/category/uncategorized",
    "/tag/uncategorized",
    "/uncategorized",
    "/wp-login",
    "/wp-admin",
    "/feed",
}
DEFAULT_ROUTE_PREFIXES = (
    "/author/",
    "/wp-admin/",
    "/wp-json/",
)
NON_HTML_SUFFIXES = (
    ".pdf", ".xml", ".json", ".csv", ".txt", ".zip",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _path(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
        path = parsed.path or "/"
    except Exception:
        path = raw
    if not path.startswith("/"):
        path = f"/{path}"
    if path != "/":
        path = path.rstrip("/")
    return path.lower()


def _content_type(page: dict[str, Any]) -> str:
    headers = page.get("headers") if isinstance(page.get("headers"), dict) else {}
    return str(
        page.get("content_type")
        or page.get("mime_type")
        or headers.get("content-type")
        or headers.get("Content-Type")
        or ""
    ).split(";", 1)[0].strip().lower()


def _pages_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    body = unwrap_scan_payload(payload)
    for key in ("crawled_pages", "pages", "scanned_pages", "crawl_pages"):
        value = body.get(key)
        if isinstance(value, list):
            return [page for page in value if isinstance(page, dict)]
    technical = body.get("technical_audit_summary")
    if isinstance(technical, dict) and isinstance(technical.get("pages"), list):
        return [page for page in technical["pages"] if isinstance(page, dict)]
    return []


def _is_usable_html(page: dict[str, Any]) -> bool:
    status = _int(page.get("status_code") or page.get("status"))
    if status != 200 or str(page.get("fetch_error") or "").strip():
        return False
    path = _path(page.get("final_url") or page.get("url") or page.get("path"))
    if path.endswith(NON_HTML_SUFFIXES):
        return False
    content_type = _content_type(page)
    if content_type and content_type not in {"text/html", "application/xhtml+xml"}:
        return False
    return bool(
        str(page.get("title") or "").strip()
        or str(page.get("h1") or "").strip()
        or _int(page.get("word_count")) >= 20
        or path == "/"
    )


def _is_default_route(page: dict[str, Any]) -> bool:
    path = _path(page.get("final_url") or page.get("url") or page.get("path"))
    family = str(page.get("page_template_family") or "").strip().lower()
    intent = str(page.get("estimated_page_intent") or "").strip().lower()
    return bool(
        path in DEFAULT_ROUTE_EXACT
        or any(path.startswith(prefix) for prefix in DEFAULT_ROUTE_PREFIXES)
        or family == "route_boundary"
        or intent == "internal_or_auth"
    )


def _meaningful_root(page: dict[str, Any]) -> bool:
    path = _path(page.get("final_url") or page.get("url") or page.get("path"))
    return bool(
        path == "/"
        and _is_usable_html(page)
        and (
            _int(page.get("word_count")) >= 50
            or (str(page.get("title") or "").strip() and str(page.get("h1") or "").strip())
        )
    )


def evaluate_evidence_quality(payload: dict[str, Any]) -> dict[str, Any]:
    pages = _pages_from_payload(payload)
    usable = [page for page in pages if _is_usable_html(page)]
    default_routes = [page for page in usable if _is_default_route(page)]
    representative = [page for page in usable if not _is_default_route(page)]
    usable_count = len(usable)
    default_count = len(default_routes)
    representative_count = len(representative)
    default_ratio = default_count / usable_count if usable_count else 0.0
    reasons: list[str] = []
    blocking = False

    if usable_count == 0:
        state = "no_usable_html"
        discovery_state = "no_usable_html"
        score = 0
        blocking = True
        reasons.append("no_usable_html_pages")
    elif usable_count == 1 and representative_count == 1 and _meaningful_root(representative[0]):
        state = "small_site_supported"
        discovery_state = "small_site_supported"
        score = 85
        reasons.append("meaningful_single_page_site")
    elif (
        2 <= usable_count <= 6
        and default_count >= 2
        and default_ratio >= 0.5
        and representative_count <= 2
    ):
        state = "insufficient_discovery"
        discovery_state = "default_route_dominated"
        score = 35
        blocking = True
        reasons.extend(["default_route_dominance", "representative_html_pages_below_minimum"])
    else:
        state = "representative"
        discovery_state = "representative"
        score = min(100, 80 + min(20, representative_count))
        reasons.append("representative_html_evidence")

    return {
        "evidence_quality_state": state,
        "evidence_quality_score": score,
        "evidence_quality_reasons": reasons,
        "discovery_quality_state": discovery_state,
        "representative_html_page_count": representative_count,
        "usable_html_page_count": usable_count,
        "default_route_page_count": default_count,
        "default_route_ratio": round(default_ratio, 3),
        "default_route_paths": [
            _path(page.get("final_url") or page.get("url") or page.get("path"))
            for page in default_routes[:12]
        ],
        "evidence_quality_blocking": blocking,
        "evidence_quality_gate_version": EVIDENCE_QUALITY_GATE_VERSION,
    }


def _copy_quality_fields(target: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    return {
        **target,
        **quality,
    }


def apply_evidence_quality_gate(result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return result

    calibrated = deepcopy(result)
    quality = evaluate_evidence_quality(payload)
    calibrated.update(quality)

    existing_status = str(calibrated.get("scan_status") or "complete")
    existing_provisional = calibrated.get("score_is_provisional") is True
    existing_limited = existing_provisional or existing_status in LIMITED_SCAN_STATUSES
    should_block = quality["evidence_quality_blocking"] and not existing_limited

    if should_block:
        usable = quality["usable_html_page_count"]
        representative = quality["representative_html_page_count"]
        defaults = quality["default_route_page_count"]
        limitation = (
            f"FixList reviewed {usable} usable HTML pages, but only {representative} were representative business pages "
            f"and {defaults} were default, archive, or internal routes. Discovery was too narrow to support a full authoritative audit."
        )
        next_step = "Verify sitemap and internal navigation coverage"
        score = min(55, _int(calibrated.get("health_score") or calibrated.get("seo_score")))
        calibrated.update({
            "scan_status": "inconclusive_insufficient_evidence",
            "review_confidence_state": "insufficient_discovery_quality",
            "score_is_provisional": True,
            "release_gate_eligible": False,
            "limitation": limitation,
            "next_best_step": next_step,
            "health_score": score,
            "seo_score": score,
            "health_grade": "Insufficient evidence",
        })
        summary = str(calibrated.get("customer_summary") or calibrated.get("plain_english_summary") or "").strip()
        if limitation not in summary:
            summary = f"{summary} {limitation}".strip()
        calibrated["customer_summary"] = summary
        calibrated["plain_english_summary"] = summary
    else:
        score = _int(calibrated.get("health_score") or calibrated.get("seo_score"))
        limitation = str(calibrated.get("limitation") or "")
        next_step = str(calibrated.get("next_best_step") or "")

    report = calibrated.get("website_health_report") if isinstance(calibrated.get("website_health_report"), dict) else {}
    report = _copy_quality_fields(report, quality)
    if should_block:
        report.update({
            "scan_status": calibrated["scan_status"],
            "review_confidence_state": calibrated["review_confidence_state"],
            "score_is_provisional": True,
            "health_score": score,
            "score": score,
            "health_grade": "Insufficient evidence",
            "limitations": [limitation],
            "next_best_step": next_step,
        })
    calibrated["website_health_report"] = report

    for key in ("scan_summary", "site_summary", "technical_audit_summary"):
        nested = calibrated.get(key) if isinstance(calibrated.get(key), dict) else {}
        nested = _copy_quality_fields(nested, quality)
        if should_block:
            nested.update({
                "scan_status": calibrated["scan_status"],
                "review_confidence_state": calibrated["review_confidence_state"],
                "score_is_provisional": True,
                "health_score": score,
                "score": score,
                "limitation": limitation,
                "next_best_step": next_step,
            })
        calibrated[key] = nested

    return calibrated
''', encoding="utf-8")

main_path = "scanner-api/app/main.py"
replace_once(
    main_path,
    '''from .indexability_postprocess import apply_indexability_quality_to_result
from .indexability_quality import INDEXABILITY_QUALITY_VERSION''',
    '''from .evidence_quality import EVIDENCE_QUALITY_GATE_VERSION, apply_evidence_quality_gate
from .indexability_postprocess import apply_indexability_quality_to_result
from .indexability_quality import INDEXABILITY_QUALITY_VERSION''',
)
replace_once(
    main_path,
    '''        "render_evidence_quality_version": RENDER_EVIDENCE_QUALITY_VERSION,
        "beta_revision_fingerprint": live_revision()["fingerprint"],''',
    '''        "render_evidence_quality_version": RENDER_EVIDENCE_QUALITY_VERSION,
        "evidence_quality_gate_version": EVIDENCE_QUALITY_GATE_VERSION,
        "beta_revision_fingerprint": live_revision()["fingerprint"],''',
)
replace_once(
    main_path,
    '''        result = apply_trust_discovery_gate(result, payload)
        result = apply_review_evidence_calibration(result, payload)
        result["beta_revision_fingerprint"] = live_revision()["fingerprint"]''',
    '''        result = apply_trust_discovery_gate(result, payload)
        result = apply_review_evidence_calibration(result, payload)
        result = apply_evidence_quality_gate(result, payload)
        result["beta_revision_fingerprint"] = live_revision()["fingerprint"]''',
)

beta_path = "scanner-api/app/beta_revision.py"
replace_once(
    beta_path,
    '''    from .crawler_acceptance import CRAWLER_ACCEPTANCE_VERSION
    from .indexability_quality import INDEXABILITY_QUALITY_VERSION''',
    '''    from .crawler_acceptance import CRAWLER_ACCEPTANCE_VERSION
    from .evidence_quality import EVIDENCE_QUALITY_GATE_VERSION
    from .indexability_quality import INDEXABILITY_QUALITY_VERSION''',
)
replace_once(
    beta_path,
    '''        "crawler_acceptance_version": CRAWLER_ACCEPTANCE_VERSION,
    }''',
    '''        "crawler_acceptance_version": CRAWLER_ACCEPTANCE_VERSION,
        "evidence_quality_gate_version": EVIDENCE_QUALITY_GATE_VERSION,
    }''',
)

schema_path = Path("base44/entities/ScanRun.jsonc")
schema = json.loads(schema_path.read_text(encoding="utf-8"))
properties = schema["properties"]
properties["evidence_quality_state"] = {"type": "string"}
properties["evidence_quality_score"] = {"type": "number", "default": 0}
properties["evidence_quality_reasons"] = {"type": "array", "items": {"type": "string"}, "default": []}
properties["discovery_quality_state"] = {"type": "string"}
properties["representative_html_page_count"] = {"type": "number", "default": 0}
properties["usable_html_page_count"] = {"type": "number", "default": 0}
properties["default_route_page_count"] = {"type": "number", "default": 0}
properties["evidence_quality_blocking"] = {"type": "boolean", "default": False}
properties["evidence_quality_gate_version"] = {"type": "string"}
schema_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")

model_path = "src/lib/scanRunModel.js"
replace_once(
    model_path,
    '''    && calibrationVersion === CURRENT_CALIBRATION_VERSION
    && authorityMarkers.beta_revision_fingerprint === CURRENT_BETA_REVISION_FINGERPRINT;''',
    '''    && calibrationVersion === CURRENT_CALIBRATION_VERSION
    && record.evidence_quality_blocking !== true
    && authorityMarkers.beta_revision_fingerprint === CURRENT_BETA_REVISION_FINGERPRINT;''',
)
replace_once(
    model_path,
    '''    access_evidence_state: toStr(record.access_evidence_state),
    no_high_confidence_findings: record.no_high_confidence_findings === true,''',
    '''    access_evidence_state: toStr(record.access_evidence_state),
    evidence_quality_state: toStr(record.evidence_quality_state),
    evidence_quality_score: Number(record.evidence_quality_score || 0),
    evidence_quality_reasons: toArr(record.evidence_quality_reasons).map(toStr).filter(Boolean).slice(0, 12),
    discovery_quality_state: toStr(record.discovery_quality_state),
    representative_html_page_count: Number(record.representative_html_page_count || 0),
    usable_html_page_count: Number(record.usable_html_page_count || 0),
    default_route_page_count: Number(record.default_route_page_count || 0),
    evidence_quality_blocking: record.evidence_quality_blocking === true,
    evidence_quality_gate_version: toStr(record.evidence_quality_gate_version),
    no_high_confidence_findings: record.no_high_confidence_findings === true,''',
)

Path("scanner-api/tests/test_evidence_quality_gate.py").write_text('''from app.evidence_quality import apply_evidence_quality_gate, evaluate_evidence_quality


def page(path: str, *, words: int = 180, family: str = "standard", intent: str = "standard") -> dict:
    return {
        "url": f"https://example.com{path}",
        "final_url": f"https://example.com{path}",
        "path": path,
        "status_code": 200,
        "content_type": "text/html",
        "fetch_error": "",
        "title": "Useful page title",
        "h1": "Useful heading",
        "word_count": words,
        "page_template_family": family,
        "estimated_page_intent": intent,
    }


def payload(pages: list[dict]) -> dict:
    return {
        "website_url": "https://example.com/",
        "pages_found": len(pages),
        "pages_crawled": len(pages),
        "crawled_pages": pages,
    }


def complete_result() -> dict:
    return {
        "scan_status": "complete",
        "review_confidence_state": "complete",
        "score_is_provisional": False,
        "release_gate_eligible": True,
        "health_score": 72,
        "seo_score": 72,
        "health_grade": "Needs work",
        "customer_summary": "FixList reviewed the discovered pages.",
        "website_health_report": {},
        "scan_summary": {},
        "site_summary": {},
        "technical_audit_summary": {},
    }


def test_lamanna_style_default_route_crawl_becomes_provisional():
    pages = [
        page("/", words=328, family="homepage", intent="money_or_conversion"),
        page("/merch", family="standard"),
        page("/hello-world", family="standard"),
        page("/author/admin", family="route_boundary", intent="internal_or_auth"),
        page("/category/uncategorized", family="collection_page"),
    ]

    quality = evaluate_evidence_quality(payload(pages))
    assert quality["usable_html_page_count"] == 5
    assert quality["representative_html_page_count"] == 2
    assert quality["default_route_page_count"] == 3
    assert quality["discovery_quality_state"] == "default_route_dominated"
    assert quality["evidence_quality_blocking"] is True

    result = apply_evidence_quality_gate(complete_result(), payload(pages))
    assert result["scan_status"] == "inconclusive_insufficient_evidence"
    assert result["score_is_provisional"] is True
    assert result["release_gate_eligible"] is False
    assert result["health_score"] <= 55
    assert result["review_confidence_state"] == "insufficient_discovery_quality"
    assert result["next_best_step"] == "Verify sitemap and internal navigation coverage"
    assert result["website_health_report"]["evidence_quality_state"] == "insufficient_discovery"


def test_meaningful_one_page_site_remains_supported():
    pages = [page("/", words=420, family="homepage", intent="money_or_conversion")]
    result = apply_evidence_quality_gate(complete_result(), payload(pages))
    assert result["evidence_quality_state"] == "small_site_supported"
    assert result["discovery_quality_state"] == "small_site_supported"
    assert result["evidence_quality_blocking"] is False
    assert result["scan_status"] == "complete"
    assert result["score_is_provisional"] is False


def test_small_brochure_site_without_default_route_dominance_remains_complete():
    pages = [
        page("/", family="homepage"),
        page("/about", family="standard", intent="trust_or_legal"),
        page("/services", family="service_page", intent="money_or_conversion"),
        page("/contact", family="contact", intent="money_or_conversion"),
    ]
    result = apply_evidence_quality_gate(complete_result(), payload(pages))
    assert result["evidence_quality_state"] == "representative"
    assert result["representative_html_page_count"] == 4
    assert result["evidence_quality_blocking"] is False
    assert result["scan_status"] == "complete"


def test_hartzler_like_eighteen_page_site_remains_complete():
    pages = [page("/", family="homepage")] + [page(f"/product-{index}") for index in range(17)]
    result = apply_evidence_quality_gate(complete_result(), payload(pages))
    assert result["usable_html_page_count"] == 18
    assert result["representative_html_page_count"] == 18
    assert result["evidence_quality_blocking"] is False
    assert result["scan_status"] == "complete"


def test_funbooker_like_large_site_remains_complete():
    pages = [page("/", family="homepage")] + [
        page(f"/fr/annonce/activity-{index}/voir", family="activity_detail", intent="money_or_conversion")
        for index in range(149)
    ]
    result = apply_evidence_quality_gate(complete_result(), payload(pages))
    assert result["usable_html_page_count"] == 150
    assert result["representative_html_page_count"] == 150
    assert result["evidence_quality_blocking"] is False
    assert result["scan_status"] == "complete"


def test_access_limited_result_keeps_existing_status_and_limitation():
    pages = [
        page("/"),
        page("/hello-world"),
        page("/author/admin", family="route_boundary", intent="internal_or_auth"),
    ]
    result = complete_result()
    result.update({
        "scan_status": "complete_with_access_limitations",
        "review_confidence_state": "partial_access_needs_verification",
        "score_is_provisional": True,
        "release_gate_eligible": False,
        "limitation": "HTTP 429 results require access-log confirmation.",
    })
    calibrated = apply_evidence_quality_gate(result, payload(pages))
    assert calibrated["scan_status"] == "complete_with_access_limitations"
    assert calibrated["review_confidence_state"] == "partial_access_needs_verification"
    assert calibrated["score_is_provisional"] is True
    assert calibrated["limitation"] == "HTTP 429 results require access-log confirmation."
''', encoding="utf-8")

Path("docs/releases/evidence-quality-gate-v1.md").write_text('''# Evidence quality gate v1

## Scope

The release gate now distinguishes mechanical crawl completion from representative business evidence.

- Clear default-route dominance on a very small crawl becomes provisional.
- Zero usable HTML evidence becomes provisional.
- Meaningful one-page sites remain supported.
- Small brochure sites without default-route dominance remain complete.
- Existing access-limited and incomplete results keep their original status and limitation.

## Production acceptance

1. Lamanna Bakery becomes non-authoritative with `discovery_quality_state: default_route_dominated`.
2. Hartzler Dairy remains complete and authoritative.
3. Funbooker remains complete and authoritative at the 150-page cap.
''', encoding="utf-8")

# Extend durable mapping tests and schema checks.
test_path = Path("tests/frontend/scanRunPersistence.test.mjs")
with test_path.open("a", encoding="utf-8") as handle:
    handle.write('''\n\ntest("evidence quality fields persist and block release authority defensively", () => {\n  const fields = buildScanRunFields({\n    ...authoritativeRecord,\n    evidence_quality_state: "insufficient_discovery",\n    evidence_quality_score: 35,\n    evidence_quality_reasons: ["default_route_dominance"],\n    discovery_quality_state: "default_route_dominated",\n    representative_html_page_count: 2,\n    usable_html_page_count: 5,\n    default_route_page_count: 3,\n    evidence_quality_blocking: true,\n    evidence_quality_gate_version: "evidence_quality_gate_v1_default_route_dominance",\n  });\n\n  assert.equal(fields.release_gate_eligible, false);\n  assert.equal(fields.evidence_quality_state, "insufficient_discovery");\n  assert.equal(fields.evidence_quality_score, 35);\n  assert.deepEqual(fields.evidence_quality_reasons, ["default_route_dominance"]);\n  assert.equal(fields.discovery_quality_state, "default_route_dominated");\n  assert.equal(fields.representative_html_page_count, 2);\n  assert.equal(fields.usable_html_page_count, 5);\n  assert.equal(fields.default_route_page_count, 3);\n  assert.equal(fields.evidence_quality_blocking, true);\n});\n''')

schema_test = Path("tests/frontend/evidenceQualityGate.test.mjs")
schema_test.write_text('''import assert from "node:assert/strict";\nimport { readFileSync } from "node:fs";\nimport test from "node:test";\n\nconst scanRunEntity = JSON.parse(readFileSync(new URL("../../base44/entities/ScanRun.jsonc", import.meta.url), "utf8"));\n\ntest("ScanRun stores evidence-quality authority fields", () => {\n  for (const field of [\n    "evidence_quality_state",\n    "evidence_quality_score",\n    "evidence_quality_reasons",\n    "discovery_quality_state",\n    "representative_html_page_count",\n    "usable_html_page_count",\n    "default_route_page_count",\n    "evidence_quality_blocking",\n    "evidence_quality_gate_version",\n  ]) {\n    assert.ok(scanRunEntity.properties[field], `ScanRun missing ${field}`);\n  }\n});\n''', encoding="utf-8")

revision_path = Path("data/beta-crawler-revision.json")
revision = json.loads(revision_path.read_text(encoding="utf-8"))
old_fingerprint = str(revision["fingerprint"])
components = dict(revision["component_versions"])
components["evidence_quality_gate_version"] = VERSION
payload = json.dumps(components, sort_keys=True, separators=(",", ":"))
new_fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
revision.update({
    "acceptance_report": "docs/releases/evidence-quality-gate-v1.md",
    "component_versions": dict(sorted(components.items())),
    "fingerprint": new_fingerprint,
    "git_commit": "",
    "note": "Evidence quality candidate: default-route-dominated narrow crawls are provisional while meaningful one-page and representative small sites remain supported.",
    "recorded_at": "2026-07-20T00:00:00Z",
    "status": "candidate",
})
revision_path.write_text(json.dumps(revision, indent=2, sort_keys=True) + "\n", encoding="utf-8")

for file_name in [
    "src/lib/scanRunModel.js",
    "tests/frontend/releaseAuthorityGate.test.mjs",
    "tests/frontend/scanRunPersistence.test.mjs",
    "scanner-api/tests/test_observability.py",
]:
    target = Path(file_name)
    text = target.read_text(encoding="utf-8")
    if old_fingerprint not in text:
        raise SystemExit(f"{file_name}: old fingerprint {old_fingerprint} not found")
    target.write_text(text.replace(old_fingerprint, new_fingerprint), encoding="utf-8")

print(f"old fingerprint: {old_fingerprint}")
print(f"new fingerprint: {new_fingerprint}")
