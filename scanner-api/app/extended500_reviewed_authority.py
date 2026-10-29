"""Private Extended 500 *reviewed* evidence authority contract -- NON-OPERATIONAL.

Status: **NON-OPERATIONAL candidate.** Nothing imports this module: no route,
worker, Base44 function, queue, database write, billing or customer surface.
There is no verified Extended 500 terminal issuer yet, so even a fully valid
envelope is only a typed, signed *candidate*:

* ``review.release_gate_eligible`` is always ``False`` and
  ``review.terminal_receipt_state`` is always ``"not_issued"``;
* verification always reports ``operational=False`` and
  ``customer_publishable=False``;
* it must never be used to mark a ScanRun complete, create a FixList/FixItem,
  set ``release_gate_eligible=True`` on any live record, or charge entitlement.

This is the reviewed counterpart of the unreviewed signed collection
``extended500_evidence_handoff_v1_unreviewed``. That handoff is never promoted:
the reviewed contract has its own version, its own purpose-derived HMAC key,
typed per-page review states, findings that reference reviewed retained page
evidence by page id, exact denominators, an explicit review coverage and
confidence statement, and it cites the exact signed handoff that was reviewed.

Canonical serialization is strict (no floats, no unsafe integers, ASCII object
keys, well-formed strings) so the signed bytes are identical in Python and in
``src/lib/extended500ReviewedAuthority.js``. A value that cannot be represented
identically in both runtimes fails closed instead of being coerced.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any
from urllib.parse import urlparse

from .authority_seal import create_authority_seal, stable_serialize
from .extended500_evidence_handoff import (
    EXTENDED500_HANDOFF_VERSION,
    EXTENDED500_MAX_HANDOFF_BYTES,
    EXTENDED500_MAX_PAGES,
    EXTENDED500_MODE,
)
from .page_output_privacy import INTERNAL_PAGE_EVIDENCE_FIELDS

EXTENDED500_REVIEWED_VERSION = "extended500_reviewed_authority_v1"
# HMAC purpose label. The signing key is HMAC-SHA256(root, purpose), so the
# same root (mis)configured for Standard 150 or the unreviewed handoff -- both
# of which sign with the raw secret -- still cannot produce a reviewed proof.
EXTENDED500_REVIEWED_PURPOSE = "fixlist-extended500-reviewed-authority-v1"
EXTENDED500_REVIEWED_OPERATIONAL_STATUS = "non_operational_no_verified_terminal_issuer"
EXTENDED500_REVIEWED_TERMINAL_STATE = "not_issued"
EXTENDED500_REVIEWED_VERDICT_STATE = "reviewed_authority_candidate_non_operational"
EXTENDED500_REVIEWED_OPERATIONAL = False
EXTENDED500_REVIEWED_MAX_FINDINGS = 200
# Development safety bound, not a benchmarked production payload limit.
EXTENDED500_REVIEWED_MAX_BYTES = 2 * 1024 * 1024
EXTENDED500_REVIEWED_MIN_ROOT_BYTES = 32
# Proposed dedicated secret name. Deliberately never read in this module.
EXTENDED500_REVIEWED_SIGNING_ENV = "EXTENDED500_REVIEWED_AUTHORITY_SIGNING_KEY"

# Raw page bodies, extracted main text and producer-internal evidence never
# cross this boundary. Mirrored exactly in the JavaScript verifier.
EXTENDED500_REVIEWED_RESTRICTED_FIELDS = frozenset(INTERNAL_PAGE_EVIDENCE_FIELDS | {
    "raw_html", "html", "page_html", "body_html", "rendered_html", "dom_snapshot",
    "response_body", "response_text", "body_text", "text_content", "visible_text",
    "raw_headers", "set_cookie", "cookies", "authorization",
})
_RESTRICTED_PREFIX = "main_text"

PRIORITIES = ("critical", "high", "medium", "low")
ACTION_PRIORITIES = ("fix_first", "important", "improve", "review")
EVIDENCE_CLASSES = ("confirmed_problem", "improvement", "opportunity")
PAGE_SCOPES = ("page", "family", "mixed", "cross_cutting", "sitewide")
EVIDENCE_STATUSES = (
    "confirmed", "confirmed_by_high_confidence_heuristic", "confirmed_active_baseline",
    "needs_verification",
)
VERIFICATION_STATES = ("verified", "confirmed", "needs_verification", "conflicted")
PAGE_REVIEW_STATES = ("reviewed", "not_reviewed")
REVIEW_COVERAGE_STATES = ("all_assessed_pages_reviewed", "bounded_sample_reviewed")
REVIEW_CONFIDENCE_STATES = (
    "complete", "complete_with_incidental_access_checks", "no_high_confidence_findings",
    "partial_access_needs_verification", "blocked_access_needs_verification",
    "incomplete_evidence", "insufficient_evidence", "insufficient_discovery_quality",
)
PROVISIONAL_CONFIDENCE_STATES = frozenset({
    "partial_access_needs_verification", "blocked_access_needs_verification",
    "incomplete_evidence", "insufficient_evidence", "insufficient_discovery_quality",
})
_ACTION_RANK = {"fix_first": 4, "important": 3, "improve": 2, "review": 1}
_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}
_FIX_CLAIM_TOKENS = frozenset({"fixed", "resolved", "done", "completed"})
_SCAN_STATES_ACCEPTING_REVIEW = ("crawling", "reviewing")

_ENVELOPE_KEYS = (
    "version", "purpose", "operational_status", "identity", "release",
    "evidence_binding", "coverage", "review", "pages", "findings",
    "fix_list_summary", "proof",
)
_SIGNED_KEYS = _ENVELOPE_KEYS[:-1]
_IDENTITY_KEYS = (
    "canonical_mode", "owner_user_id", "scan_id", "project_id",
    "request_id", "idempotency_key", "normalized_domain", "attempt_count",
)
_RELEASE_KEYS = ("scanner_source_sha", "beta_revision_fingerprint", "review_version")
_BINDING_KEYS = ("handoff_version", "handoff_proof")
_COVERAGE_KEYS = (
    "pages_found", "urls_attempted", "usable_html_pages", "pages_assessed",
    "pages_reviewed", "pages_not_reviewed", "review_coverage_basis_points",
    "pages_with_findings",
)
_REVIEW_KEYS = (
    "review_status", "review_coverage_state", "sampling_policy_version",
    "review_confidence_state", "score_is_provisional", "no_high_confidence_findings",
    "health_score", "release_gate_eligible", "terminal_receipt_state",
)
_PAGE_KEYS = ("page_id", "final_url", "review_state")
_FINDING_KEYS = (
    "fix_id", "rule", "category", "issue_title", "plain_english_explanation",
    "simple_next_step", "priority", "evidence_class", "action_priority",
    "action_priority_score", "canonical_action_rank", "page_scope",
    "page_template_family", "affected_page_ids", "page_count", "page_url",
    "evidence_status", "verification_state", "confidence_score",
    "repair_fingerprint", "user_status", "repair_verification_state",
)
_SUMMARY_KEYS = (
    "total_fixes", "critical_count", "high_count", "medium_count", "low_count",
    "fix_first_count", "important_count", "improve_count", "review_count",
    "completed_count", "top_action_fix_ids", "canonical_action_fix_ids",
)
# The unreviewed handoff shape, mirrored from src/lib/extended500EvidenceHandoff.js.
_HANDOFF_KEYS = ("version", "identity", "scan", "review", "proof")
_HANDOFF_SCAN_KEYS = (
    "canonical_mode", "scan_id", "request_id", "idempotency_key",
    "normalized_domain", "pages_found", "pages_crawled", "scan_coverage",
    "scanner_source_sha", "beta_revision_fingerprint", "pages",
)
_HANDOFF_COVERAGE_KEYS = ("urls_attempted", "usable_html_pages", "unique_retained_destinations")
_HANDOFF_REVIEW_KEYS = ("review_status", "pages_reviewed", "release_gate_eligible")

_MAX_SAFE_INT = 2**53 - 1
_MAX_DEPTH = 32
_ASCII_KEY_RE = re.compile(r"[\x20-\x7e]{1,128}")
_ID_TOKEN_RE = re.compile(r"[A-Za-z0-9_.:-]{1,256}")
_VERSION_TOKEN_RE = re.compile(r"[A-Za-z0-9_.:-]{1,160}")
_RULE_RE = re.compile(r"[a-z0-9][a-z0-9_.:-]{0,119}")
_DOMAIN_RE = re.compile(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+")
_ATTEMPT_RE = re.compile(r"[1-9][0-9]{0,15}")
_HANDOFF_ATTEMPT_RE = re.compile(r"[1-9][0-9]*")
_SHA40_RE = re.compile(r"[0-9a-f]{40}")
_FP16_RE = re.compile(r"[0-9a-f]{16}")
_HEX64_RE = re.compile(r"[0-9a-f]{64}")
_URL_RE = re.compile(r"https?://([A-Za-z0-9.-]+)(?::[0-9]{1,5})?(?:[/?#][^\x00-\x20\x7f]*)?")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_EDGE_SPACE_RE = re.compile(r"\A[ \t\r\n]|[ \t\r\n]\Z")
_STATE_LIKE_RE = re.compile(r"[A-Za-z0-9_ -]{1,120}")


class Extended500ReviewedAuthorityError(ValueError):
    """A reviewed envelope or its inputs violate the contract (closed reason code)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _fail(reason: str) -> None:
    raise Extended500ReviewedAuthorityError(reason)


# ------------------------------------------------------------ primitives --

def _plain(value: Any) -> bool:
    return isinstance(value, dict)


def _exact_keys(value: Any, keys: tuple[str, ...]) -> bool:
    return isinstance(value, dict) and len(value) == len(keys) and all(key in value for key in keys)


def _nonneg(value: Any) -> bool:
    return type(value) is int and 0 <= value <= _MAX_SAFE_INT


def _same(left: Any, right: Any) -> bool:
    """Strict structural equality: True is not 1, and lists keep order."""
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_same(left[key], right[key]) for key in left)
    return left == right


def _match(pattern: re.Pattern[str], value: Any) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _text(value: Any, limit: int, *, required: bool) -> bool:
    """Bounded customer copy: no controls, no edge whitespace, no truncation."""
    return (
        isinstance(value, str)
        and (bool(value) or not required)
        and len(value) <= limit
        and _CONTROL_RE.search(value) is None
        and _EDGE_SPACE_RE.search(value) is None
    )


def _claims_fix(value: Any) -> bool:
    if not _match(_STATE_LIKE_RE, value):
        return False
    return any(part in _FIX_CLAIM_TOKENS for part in re.split(r"[_ -]+", value.lower()))


def _url_host(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        return ""
    found = _URL_RE.fullmatch(value)
    if not found:
        return ""
    host = found.group(1).lower()
    if host.startswith("www."):
        host = host[4:]
    return host[:-1] if host.endswith(".") else host


def _frozen_domain(value: Any) -> str:
    """Strict, parser-free domain of the frozen ScanRun (identical in JS)."""
    if not isinstance(value, str):
        return ""
    text = value.strip(" \t\n\r\f\v")
    if "://" in text:
        return _url_host(text)
    if not text.isascii():
        return ""
    text = text.lower()
    if text.startswith("www."):
        text = text[4:]
    return text[:-1] if text.endswith(".") else text


def _handoff_domain(value: Any) -> str:
    """Port of the unreviewed handoff verifier's own domain normalization."""
    if not isinstance(value, str) or not value.strip():
        return ""
    text = value.strip().lower()
    if "://" in text:
        try:
            text = urlparse(text).hostname or ""
        except ValueError:
            return ""
    if text.startswith("www."):
        text = text[4:]
    return text[:-1] if text.endswith(".") else text


def _restricted_present(value: Any) -> bool:
    stack, seen = [value], set()
    while stack:
        item = stack.pop()
        if isinstance(item, (dict, list)):
            if id(item) in seen:
                continue
            seen.add(id(item))
        if isinstance(item, dict):
            for key, child in item.items():
                if isinstance(key, str) and (
                    key in EXTENDED500_REVIEWED_RESTRICTED_FIELDS or key.startswith(_RESTRICTED_PREFIX)
                ):
                    return True
                stack.append(child)
        elif isinstance(item, list):
            stack.extend(item)
    return False


# ----------------------------------------------------- canonical + HMAC --

def _assert_canonical(value: Any, depth: int = 0) -> None:
    if depth > _MAX_DEPTH:
        _fail("canonical_value_invalid")
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        if not -_MAX_SAFE_INT <= value <= _MAX_SAFE_INT:
            _fail("canonical_value_invalid")
        return
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            _fail("canonical_value_invalid")
        return
    if isinstance(value, list):
        for item in value:
            _assert_canonical(item, depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not _match(_ASCII_KEY_RE, key):
                _fail("canonical_value_invalid")
            _assert_canonical(item, depth + 1)
        return
    # Floats, tuples, bytes and every other type have no single
    # cross-runtime byte representation: refuse rather than coerce.
    _fail("canonical_value_invalid")


def canonical_reviewed_bytes(value: Any) -> bytes:
    """Strict canonical JSON bytes, identical to canonicalReviewedJson in JS."""
    _assert_canonical(value)
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False,
    ).encode("utf-8")


def _root_bytes(root: Any) -> bytes:
    if not isinstance(root, str):
        _fail("signing_root_invalid")
    try:
        encoded = root.encode("utf-8")
    except UnicodeEncodeError:
        _fail("signing_root_invalid")
    if len(encoded) < EXTENDED500_REVIEWED_MIN_ROOT_BYTES:
        _fail("signing_root_invalid")
    return encoded


def _seal(signed_bytes: bytes, root: str) -> str:
    derived = hmac.new(_root_bytes(root), EXTENDED500_REVIEWED_PURPOSE.encode("ascii"), hashlib.sha256).digest()
    return hmac.new(derived, signed_bytes, hashlib.sha256).hexdigest()


# -------------------------------------------------- frozen ScanRun checks --

def _check_frozen_scan(scan_run: Any) -> None:
    if not _plain(scan_run) or scan_run.get("scan_mode") != EXTENDED500_MODE:
        _fail("mode_invalid")
    if (
        scan_run.get("status") not in _SCAN_STATES_ACCEPTING_REVIEW
        or scan_run.get("release_gate_eligible") is True
        or scan_run.get("authority_proof") not in (None, "")
    ):
        _fail("scan_state_invalid")


def _check_identity(identity: dict[str, Any], scan_run: dict[str, Any]) -> None:
    if identity["canonical_mode"] != EXTENDED500_MODE:
        _fail("mode_invalid")
    for key in ("owner_user_id", "scan_id", "project_id", "request_id", "idempotency_key"):
        frozen_key = "id" if key == "scan_id" else key
        if not _match(_ID_TOKEN_RE, identity[key]) or identity[key] != scan_run.get(frozen_key):
            _fail("identity_mismatch")
    frozen_domain = _frozen_domain(scan_run.get("normalized_domain") or scan_run.get("website_url"))
    if not _match(_DOMAIN_RE, identity["normalized_domain"]) or identity["normalized_domain"] != frozen_domain:
        _fail("domain_mismatch")
    frozen_attempt = scan_run.get("attempt_count")
    if (
        not _match(_ATTEMPT_RE, identity["attempt_count"])
        or not _nonneg(frozen_attempt)
        or frozen_attempt < 1
        or int(identity["attempt_count"]) != frozen_attempt
    ):
        _fail("attempt_mismatch")


def _handoff_token(value: Any) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 256 and value.strip() == value


def _handoff_valid(handoff: Any, scan_run: dict[str, Any], handoff_key: Any) -> bool:
    """Python port of verifyExtended500EvidenceHandoff (unreviewed collection)."""
    if not _exact_keys(handoff, _HANDOFF_KEYS) or handoff["version"] != EXTENDED500_HANDOFF_VERSION:
        return False
    if scan_run.get("scan_mode") != EXTENDED500_MODE:
        return False
    identity, scan, review = handoff["identity"], handoff["scan"], handoff["review"]
    if not (
        _exact_keys(identity, _IDENTITY_KEYS) and _exact_keys(scan, _HANDOFF_SCAN_KEYS)
        and _exact_keys(scan.get("scan_coverage"), _HANDOFF_COVERAGE_KEYS)
        and _exact_keys(review, _HANDOFF_REVIEW_KEYS)
    ):
        return False
    if identity["canonical_mode"] != EXTENDED500_MODE or scan["canonical_mode"] != EXTENDED500_MODE:
        return False
    if not (
        review["review_status"] == "not_reviewed" and _same(review["pages_reviewed"], 0)
        and review["release_gate_eligible"] is False
    ):
        return False
    for key in ("owner_user_id", "scan_id", "project_id", "request_id", "idempotency_key"):
        frozen_key = "id" if key == "scan_id" else key
        if not _handoff_token(identity[key]) or identity[key] != scan_run.get(frozen_key):
            return False
    domain = identity["normalized_domain"]
    if (
        not _handoff_token(domain)
        or domain != _handoff_domain(scan_run.get("normalized_domain") or scan_run.get("website_url"))
        or scan["normalized_domain"] != domain
    ):
        return False
    frozen_attempt = scan_run.get("attempt_count")
    if (
        not _match(_HANDOFF_ATTEMPT_RE, identity["attempt_count"])
        or not _nonneg(frozen_attempt) or int(identity["attempt_count"]) != frozen_attempt
    ):
        return False
    if any(scan[key] != identity[key] for key in ("scan_id", "request_id", "idempotency_key")):
        return False
    count = scan["pages_crawled"]
    pages = scan["pages"]
    if (
        not _nonneg(count) or not 1 <= count <= EXTENDED500_MAX_PAGES
        or not isinstance(pages, list) or len(pages) != count
        or not _nonneg(scan["pages_found"]) or scan["pages_found"] < count
    ):
        return False
    coverage = scan["scan_coverage"]
    if (
        not _nonneg(coverage["urls_attempted"]) or coverage["urls_attempted"] < count
        or not _nonneg(coverage["usable_html_pages"])
        or coverage["usable_html_pages"] > coverage["urls_attempted"]
        or not _same(coverage["unique_retained_destinations"], count)
    ):
        return False
    destinations = []
    for page in pages:
        if not _plain(page):
            return False
        url = page.get("final_url") or page.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return False
        destinations.append(url)
    if len(set(destinations)) != len(destinations):
        return False
    if not _match(_SHA40_RE, scan["scanner_source_sha"]) or not _match(_FP16_RE, scan["beta_revision_fingerprint"]):
        return False
    signed = {key: handoff[key] for key in ("version", "identity", "scan", "review")}
    serialized = stable_serialize(signed).encode("utf-8")
    if len(serialized) > EXTENDED500_MAX_HANDOFF_BYTES:
        return False
    proof = handoff["proof"]
    if not isinstance(handoff_key, str) or not handoff_key or not isinstance(proof, str):
        return False
    clean = proof.strip().lower()
    if not _match(_HEX64_RE, clean):
        return False
    return hmac.compare_digest(create_authority_seal(signed, handoff_key), clean)


def _handoff_urls(handoff: dict[str, Any]) -> list[str]:
    return [page.get("final_url") or page.get("url") for page in handoff["scan"]["pages"]]


def _page_id(index: int) -> str:
    return f"p{index + 1:03d}"


# ---------------------------------------------------- the shared validator --

def _validate_signed(
    signed: dict[str, Any],
    scan_run: Any,
    expected_release: Any,
    signing_root: Any,
    evidence_handoff: Any,
    handoff_signing_key: Any,
) -> bytes:
    """Every non-HMAC rule; returns the canonical signed bytes. Order is normative."""
    if signed["version"] == EXTENDED500_HANDOFF_VERSION:
        _fail("unreviewed_handoff_not_promotable")
    if signed["version"] != EXTENDED500_REVIEWED_VERSION:
        _fail("version_invalid")
    if signed["purpose"] != EXTENDED500_REVIEWED_PURPOSE:
        _fail("purpose_invalid")
    if signed["operational_status"] != EXTENDED500_REVIEWED_OPERATIONAL_STATUS:
        _fail("non_operational_marker_invalid")
    _check_frozen_scan(scan_run)
    identity, release, binding = signed["identity"], signed["release"], signed["evidence_binding"]
    coverage, review = signed["coverage"], signed["review"]
    pages, findings, summary = signed["pages"], signed["findings"], signed["fix_list_summary"]
    if not (
        _exact_keys(identity, _IDENTITY_KEYS) and _exact_keys(release, _RELEASE_KEYS)
        and _exact_keys(binding, _BINDING_KEYS) and _exact_keys(coverage, _COVERAGE_KEYS)
        and _exact_keys(review, _REVIEW_KEYS) and _exact_keys(summary, _SUMMARY_KEYS)
        and isinstance(pages, list) and isinstance(findings, list)
    ):
        _fail("document_shape_invalid")
    _check_identity(identity, scan_run)

    # Release authority cannot be claimed without a verified terminal issuer.
    if review["release_gate_eligible"] is not False or review["terminal_receipt_state"] != EXTENDED500_REVIEWED_TERMINAL_STATE:
        _fail("premature_release_gate")
    if review["review_status"] != "reviewed":
        _fail("review_not_reviewed")

    if not (
        _exact_keys(expected_release, _RELEASE_KEYS)
        and _match(_SHA40_RE, expected_release["scanner_source_sha"])
        and _match(_FP16_RE, expected_release["beta_revision_fingerprint"])
        and _match(_VERSION_TOKEN_RE, expected_release["review_version"])
    ):
        _fail("release_expectation_missing")
    if any(release[key] != expected_release[key] for key in _RELEASE_KEYS):
        _fail("release_mismatch")

    _root_bytes(signing_root)
    if not isinstance(handoff_signing_key, str) or not handoff_signing_key:
        _fail("signing_root_invalid")
    if signing_root == handoff_signing_key:
        _fail("signing_root_not_distinct")

    if not _handoff_valid(evidence_handoff, scan_run, handoff_signing_key):
        _fail("evidence_handoff_invalid")
    handoff_scan = evidence_handoff["scan"]
    if (
        any(identity[key] != evidence_handoff["identity"][key] for key in _IDENTITY_KEYS)
        or binding["handoff_version"] != EXTENDED500_HANDOFF_VERSION
        or not _match(_HEX64_RE, binding["handoff_proof"])
        or binding["handoff_proof"] != evidence_handoff["proof"]
    ):
        _fail("evidence_binding_mismatch")
    if (
        release["scanner_source_sha"] != handoff_scan["scanner_source_sha"]
        or release["beta_revision_fingerprint"] != handoff_scan["beta_revision_fingerprint"]
    ):
        _fail("release_mismatch")

    count = len(pages)
    if not 1 <= count <= EXTENDED500_MAX_PAGES or count != handoff_scan["pages_crawled"]:
        _fail("page_count_invalid")
    retained = _handoff_urls(evidence_handoff)
    states: dict[str, str] = {}
    for index, page in enumerate(pages):
        if (
            not _exact_keys(page, _PAGE_KEYS) or page["page_id"] != _page_id(index)
            or page["final_url"] != retained[index] or page["review_state"] not in PAGE_REVIEW_STATES
        ):
            _fail("page_index_invalid")
        if _url_host(page["final_url"]) != identity["normalized_domain"]:
            _fail("page_host_mismatch")
        states[page["page_id"]] = page["review_state"]
    urls = {page["page_id"]: page["final_url"] for page in pages}
    reviewed = sum(1 for state in states.values() if state == "reviewed")

    if not all(_nonneg(coverage[key]) for key in _COVERAGE_KEYS):
        _fail("denominator_mismatch")
    if reviewed == 0 or coverage["pages_reviewed"] == 0:
        _fail("review_not_reviewed")
    handoff_coverage = handoff_scan["scan_coverage"]
    if (
        coverage["pages_assessed"] != count
        or coverage["pages_found"] != handoff_scan["pages_found"]
        or coverage["urls_attempted"] != handoff_coverage["urls_attempted"]
        or coverage["usable_html_pages"] != handoff_coverage["usable_html_pages"]
        or coverage["pages_found"] < count or coverage["urls_attempted"] < count
        or coverage["usable_html_pages"] > coverage["urls_attempted"]
        or coverage["pages_reviewed"] != reviewed
        or coverage["pages_not_reviewed"] != count - reviewed
        or coverage["review_coverage_basis_points"] != reviewed * 10000 // count
    ):
        _fail("denominator_mismatch")

    expected_coverage_state = (
        "all_assessed_pages_reviewed" if reviewed == count else "bounded_sample_reviewed"
    )
    if (
        review["review_coverage_state"] != expected_coverage_state
        or not _match(_VERSION_TOKEN_RE, review["sampling_policy_version"])
    ):
        _fail("review_coverage_invalid")

    if len(findings) > EXTENDED500_REVIEWED_MAX_FINDINGS:
        _fail("finding_shape_invalid")
    state = review["review_confidence_state"]
    provisional = review["score_is_provisional"]
    health = review["health_score"]
    no_high = review["no_high_confidence_findings"]
    if (
        state not in REVIEW_CONFIDENCE_STATES
        or not isinstance(provisional, bool) or not isinstance(no_high, bool)
        or not (health is None or (_nonneg(health) and health <= 100))
        or ((state in PROVISIONAL_CONFIDENCE_STATES or reviewed < count) and provisional is not True)
        or no_high != (len(findings) == 0)
        or (state == "no_high_confidence_findings") != (len(findings) == 0)
    ):
        _fail("review_confidence_invalid")

    fix_ids: list[str] = []
    fingerprints: set[str] = set()
    referenced: set[str] = set()
    previous: tuple[int, int, int] | None = None
    for index, finding in enumerate(findings):
        if not _exact_keys(finding, _FINDING_KEYS):
            _fail("finding_shape_invalid")
        if (
            finding["user_status"] == "done"
            or _claims_fix(finding["repair_verification_state"])
            or _claims_fix(finding["evidence_status"])
            or _claims_fix(finding["verification_state"])
        ):
            _fail("false_fix_claim")
        if not (
            _match(_VERSION_TOKEN_RE, finding["fix_id"])
            and _match(_RULE_RE, finding["rule"])
            and _text(finding["category"], 120, required=False)
            and _text(finding["issue_title"], 500, required=True)
            and _text(finding["plain_english_explanation"], 2000, required=False)
            and _text(finding["simple_next_step"], 2000, required=False)
            and finding["priority"] in PRIORITIES
            and finding["evidence_class"] in EVIDENCE_CLASSES
            and finding["action_priority"] in ACTION_PRIORITIES
            and _nonneg(finding["action_priority_score"]) and finding["action_priority_score"] <= 100000
            and finding["page_scope"] in PAGE_SCOPES
            and _text(finding["page_template_family"], 200, required=False)
            and finding["evidence_status"] in EVIDENCE_STATUSES
            and finding["verification_state"] in VERIFICATION_STATES
            and _nonneg(finding["confidence_score"]) and finding["confidence_score"] <= 100
            and _match(_VERSION_TOKEN_RE, finding["repair_fingerprint"])
            and finding["user_status"] == "open"
            and finding["repair_verification_state"] == "not_compared"
        ):
            _fail("finding_field_invalid")
        if finding["fix_id"] in fix_ids or finding["repair_fingerprint"] in fingerprints:
            _fail("duplicate_finding")
        affected = finding["affected_page_ids"]
        if not isinstance(affected, list) or not affected:
            _fail("finding_evidence_missing")
        for page_id in affected:
            if not isinstance(page_id, str) or page_id not in states:
                _fail("finding_evidence_missing")
            if states[page_id] != "reviewed":
                _fail("finding_evidence_not_reviewed")
        if (
            len(set(affected)) != len(affected)
            or not _same(finding["page_count"], len(affected))
            or finding["page_url"] != urls[affected[0]]
            or (finding["page_scope"] == "page" and len(affected) != 1)
            or (finding["page_scope"] == "sitewide" and finding["page_template_family"] != "")
        ):
            _fail("finding_field_invalid")
        key = (
            _ACTION_RANK[finding["action_priority"]],
            finding["action_priority_score"],
            _SEVERITY_RANK[finding["priority"]],
        )
        if not _same(finding["canonical_action_rank"], index + 1) or (previous is not None and key > previous):
            _fail("priority_order_invalid")
        previous = key
        fix_ids.append(finding["fix_id"])
        fingerprints.add(finding["repair_fingerprint"])
        referenced.update(affected)

    if not _same(summary["completed_count"], 0):
        _fail("false_fix_claim")
    if not _same(summary, _summary(findings)):
        _fail("aggregation_mismatch")
    if coverage["pages_with_findings"] != len(referenced):
        _fail("denominator_mismatch")

    serialized = canonical_reviewed_bytes(signed)
    if len(serialized) > EXTENDED500_REVIEWED_MAX_BYTES:
        _fail("byte_budget_exceeded")
    return serialized


def _summary(findings: list[dict[str, Any]]) -> dict[str, Any]:
    ids = [finding["fix_id"] for finding in findings]
    return {
        "total_fixes": len(findings),
        **{f"{level}_count": sum(1 for f in findings if f["priority"] == level) for level in PRIORITIES},
        **{f"{band}_count": sum(1 for f in findings if f["action_priority"] == band) for band in ACTION_PRIORITIES},
        "completed_count": 0,
        "top_action_fix_ids": ids[:3],
        "canonical_action_fix_ids": ids,
    }


def _verdict(signed: dict[str, Any]) -> dict[str, Any]:
    return {
        "valid": True,
        "state": EXTENDED500_REVIEWED_VERDICT_STATE,
        "operational": EXTENDED500_REVIEWED_OPERATIONAL,
        "customer_publishable": False,
        "release_gate_eligible": False,
        "pages_assessed": signed["coverage"]["pages_assessed"],
        "pages_reviewed": signed["coverage"]["pages_reviewed"],
        "total_fixes": signed["fix_list_summary"]["total_fixes"],
    }


# -------------------------------------------------------------- verifier --

def verify_extended500_reviewed_authority(
    envelope: Any,
    *,
    scan_run: Any,
    expected_release: Any,
    signing_root: Any,
    evidence_handoff: Any,
    handoff_signing_key: Any,
) -> dict[str, Any]:
    """Return a closed-reason verdict. A valid verdict is never publishable."""
    try:
        if not _plain(envelope):
            _fail("shape_invalid")
        if _restricted_present(envelope):
            _fail("restricted_field_present")
        if envelope.get("version") == EXTENDED500_HANDOFF_VERSION:
            _fail("unreviewed_handoff_not_promotable")
        if envelope.get("version") != EXTENDED500_REVIEWED_VERSION:
            _fail("version_invalid")
        if not _exact_keys(envelope, _ENVELOPE_KEYS):
            _fail("shape_invalid")
        signed = {key: envelope[key] for key in _SIGNED_KEYS}
        serialized = _validate_signed(
            signed, scan_run, expected_release, signing_root, evidence_handoff, handoff_signing_key,
        )
        proof = envelope["proof"]
        if not _match(_HEX64_RE, proof) or not hmac.compare_digest(_seal(serialized, signing_root), proof):
            _fail("hmac_invalid")
        return _verdict(signed)
    except Extended500ReviewedAuthorityError as error:
        return {"valid": False, "reason": error.reason}
    except (TypeError, KeyError, AttributeError, IndexError, ValueError):
        # Never let a malformed envelope escape as an exception (JS parity).
        return {"valid": False, "reason": "verifier_error"}


# -------------------------------------------------------------- producer --

def _integral(value: Any) -> Any:
    """Accept an integral float from the review producer; the contract is int-only."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _map_finding(raw: Any, index: int, url_to_id: dict[str, str], id_to_url: dict[str, str]) -> dict[str, Any]:
    if not _plain(raw):
        _fail("finding_shape_invalid")
    user_status = raw.get("user_status", "open")
    repair_state = raw.get("repair_verification_state") or "not_compared"
    if (
        user_status == "done" or _claims_fix(repair_state)
        or _claims_fix(raw.get("evidence_status")) or _claims_fix(raw.get("verification_state"))
        or _claims_fix(raw.get("status"))
    ):
        _fail("false_fix_claim")
    if user_status != "open" or repair_state != "not_compared":
        _fail("finding_field_invalid")
    affected_urls = raw.get("affected_pages")
    if not isinstance(affected_urls, list) or not affected_urls:
        _fail("finding_evidence_missing")
    page_ids: list[str] = []
    for url in affected_urls:
        page_id = url_to_id.get(url) if isinstance(url, str) else None
        if page_id is None:
            _fail("finding_evidence_missing")
        if page_id not in page_ids:
            page_ids.append(page_id)
    return {
        "fix_id": raw.get("fix_id"),
        "rule": raw.get("rule"),
        "category": raw.get("category", ""),
        "issue_title": raw.get("issue_title") or raw.get("title"),
        "plain_english_explanation": raw.get("plain_english_explanation", ""),
        "simple_next_step": raw.get("simple_next_step", ""),
        # The canonical Python sort ranks on technical (base) severity.
        "priority": raw.get("base_severity") or raw.get("priority"),
        "evidence_class": raw.get("evidence_class"),
        "action_priority": raw.get("action_priority"),
        "action_priority_score": _integral(raw.get("action_priority_score")),
        "canonical_action_rank": index + 1,
        "page_scope": raw.get("page_scope"),
        "page_template_family": raw.get("page_template_family", ""),
        "affected_page_ids": page_ids,
        "page_count": len(page_ids),
        "page_url": id_to_url[page_ids[0]],
        "evidence_status": raw.get("evidence_status"),
        "verification_state": raw.get("verification_state"),
        "confidence_score": _integral(raw.get("confidence_score")),
        "repair_fingerprint": raw.get("repair_fingerprint"),
        "user_status": "open",
        "repair_verification_state": "not_compared",
    }


def build_extended500_reviewed_authority(
    *,
    scan_run: Any,
    evidence_handoff: Any,
    handoff_signing_key: Any,
    review: Any,
    expected_release: Any,
    signing_root: Any,
) -> dict[str, Any]:
    """Sign one NON-OPERATIONAL reviewed candidate over a verified unreviewed handoff.

    ``review`` is the reviewer's typed output: ``review_status="reviewed"``,
    ``review_version``, ``sampling_policy_version``, ``reviewed_page_urls``
    (exact retained destinations), ``review_confidence_state``, optional
    ``score_is_provisional``/``no_high_confidence_findings``/``health_score``
    and canonical-ordered ``findings`` whose ``affected_pages`` are retained
    destination URLs. Findings are projected through a positive allowlist;
    restricted raw fields anywhere in the input are refused, never stripped.
    The result is re-validated by the verifier's own rules before signing.
    """
    if _restricted_present(review):
        _fail("restricted_field_present")
    if not _plain(review):
        _fail("review_not_reviewed")
    if "release_gate_eligible" in review and review["release_gate_eligible"] is not False:
        _fail("premature_release_gate")
    if review.get("review_status") != "reviewed":
        _fail("review_not_reviewed")
    _check_frozen_scan(scan_run)
    if _plain(evidence_handoff) and _exact_keys(evidence_handoff.get("identity"), _IDENTITY_KEYS):
        # Name a stale or foreign tenant precisely before the generic refusal.
        _check_identity(evidence_handoff["identity"], scan_run)
    if not _handoff_valid(evidence_handoff, scan_run, handoff_signing_key):
        _fail("evidence_handoff_invalid")

    retained = _handoff_urls(evidence_handoff)
    reviewed_urls = review.get("reviewed_page_urls")
    if (
        not isinstance(reviewed_urls, list)
        or not all(isinstance(url, str) for url in reviewed_urls)
        or len(set(reviewed_urls)) != len(reviewed_urls)
        or not set(reviewed_urls) <= set(retained)
    ):
        _fail("page_index_invalid")
    reviewed_set = set(reviewed_urls)
    pages = [
        {"page_id": _page_id(index), "final_url": url,
         "review_state": "reviewed" if url in reviewed_set else "not_reviewed"}
        for index, url in enumerate(retained)
    ]
    url_to_id = {page["final_url"]: page["page_id"] for page in pages}
    id_to_url = {page["page_id"]: page["final_url"] for page in pages}
    raw_findings = review.get("findings")
    if not isinstance(raw_findings, list) or len(raw_findings) > EXTENDED500_REVIEWED_MAX_FINDINGS:
        _fail("finding_shape_invalid")
    findings = [_map_finding(raw, index, url_to_id, id_to_url) for index, raw in enumerate(raw_findings)]

    count, reviewed = len(pages), len(reviewed_set)
    state = review.get("review_confidence_state")
    claim = review.get("score_is_provisional", False)
    no_high_claim = review.get("no_high_confidence_findings", False)
    if not isinstance(claim, bool) or not isinstance(no_high_claim, bool):
        _fail("review_confidence_invalid")
    if no_high_claim and findings:
        _fail("review_confidence_invalid")
    # Provisional can only be strengthened: a bounded sample never scores the site.
    provisional = claim or reviewed < count or state in PROVISIONAL_CONFIDENCE_STATES
    handoff_scan = evidence_handoff["scan"]
    identity = dict(evidence_handoff["identity"])
    referenced = {page_id for finding in findings for page_id in finding["affected_page_ids"]}
    signed = {
        "version": EXTENDED500_REVIEWED_VERSION,
        "purpose": EXTENDED500_REVIEWED_PURPOSE,
        "operational_status": EXTENDED500_REVIEWED_OPERATIONAL_STATUS,
        "identity": identity,
        "release": {
            "scanner_source_sha": handoff_scan["scanner_source_sha"],
            "beta_revision_fingerprint": handoff_scan["beta_revision_fingerprint"],
            "review_version": review.get("review_version"),
        },
        "evidence_binding": {
            "handoff_version": evidence_handoff["version"],
            "handoff_proof": evidence_handoff["proof"],
        },
        "coverage": {
            "pages_found": handoff_scan["pages_found"],
            "urls_attempted": handoff_scan["scan_coverage"]["urls_attempted"],
            "usable_html_pages": handoff_scan["scan_coverage"]["usable_html_pages"],
            "pages_assessed": count,
            "pages_reviewed": reviewed,
            "pages_not_reviewed": count - reviewed,
            "review_coverage_basis_points": reviewed * 10000 // count,
            "pages_with_findings": len(referenced),
        },
        "review": {
            "review_status": "reviewed",
            "review_coverage_state": (
                "all_assessed_pages_reviewed" if reviewed == count else "bounded_sample_reviewed"
            ),
            "sampling_policy_version": review.get("sampling_policy_version"),
            "review_confidence_state": state,
            "score_is_provisional": provisional,
            "no_high_confidence_findings": not findings,
            "health_score": _integral(review.get("health_score")),
            "release_gate_eligible": False,
            "terminal_receipt_state": EXTENDED500_REVIEWED_TERMINAL_STATE,
        },
        "pages": pages,
        "findings": findings,
        "fix_list_summary": _summary(findings),
    }
    if _restricted_present(signed):
        _fail("restricted_field_present")
    serialized = _validate_signed(
        signed, scan_run, expected_release, signing_root, evidence_handoff, handoff_signing_key,
    )
    return {**signed, "proof": _seal(serialized, signing_root)}
