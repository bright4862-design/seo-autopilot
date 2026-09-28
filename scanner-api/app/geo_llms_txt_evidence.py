"""Pure llms.txt structural evidence for GEO readiness.

The llms.txt convention is treated as optional structural metadata. This adapter
performs no network request and does not claim that a provider fetches, ranks,
cites, includes, displays, or sends traffic because a file is present.
"""
from __future__ import annotations

from hashlib import sha256
import re
from urllib.parse import urlparse

VERSION = "geo_llms_txt_evidence_v1"
MAX_BODY_BYTES = 256_000
MAX_LINES = 10_000
MAX_LINKS = 500

_H1 = re.compile(r"^#\s+(\S(?:.*\S)?)\s*$")
_H2 = re.compile(r"^##\s+(\S(?:.*\S)?)\s*$")
_LIST_LINK = re.compile(r"^\s*[-*+]\s+\[[^\]\r\n]{1,300}\]\(([^)\s]{1,8192})\)(?:\s*:\s*.*)?\s*$")


def _canonical_llms_url(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 8192:
        raise ValueError("Expected bounded llms.txt URL")
    try:
        parsed = urlparse(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query:
            raise ValueError("Expected public HTTP(S) llms.txt URL without credentials or query")
        if not parsed.path.lower().endswith("/llms.txt") and parsed.path.lower() != "/llms.txt":
            raise ValueError("Observation URL must identify llms.txt")
        host = parsed.hostname.lower()
        port = parsed.port
        if port and not ((parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443)):
            host = f"{host}:{port}"
        return parsed._replace(scheme=parsed.scheme.lower(), netloc=host, fragment="").geturl()
    except ValueError as exc:
        if str(exc).startswith("Observation URL") or str(exc).startswith("Expected"):
            raise
        raise ValueError("Malformed llms.txt URL") from exc


def _scope_path(url: str) -> str:
    path = urlparse(url).path
    prefix = path[:-len("llms.txt")]
    return prefix or "/"


def _evidence_ref(url: str, status_code: int, body_digest: str) -> str:
    material = f"{url}\n{status_code}\n{body_digest}".encode()
    return f"{VERSION}:{sha256(material).hexdigest()[:24]}"


def _safe_link(value: str) -> bool:
    try:
        parsed = urlparse(value)
        if parsed.scheme:
            return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and not parsed.username and not parsed.password
        return value.startswith(("/", "./", "../")) or bool(value.strip())
    except ValueError:
        return False


def extract_llms_txt_evidence(observation: dict) -> dict:
    """Normalize one already-retained llms.txt response into bounded evidence.

    Expected observation fields are intentionally transport-neutral: `url`,
    `status_code`, optional `content_type`, optional `body`, plus explicit
    uncertainty flags. The adapter never fetches the URL itself.
    """
    if not isinstance(observation, dict):
        raise ValueError("Expected llms.txt observation object")
    if len(observation) > 20 or any(not isinstance(key, str) or len(key) > 100 for key in observation):
        raise ValueError("Unbounded llms.txt observation")
    url = _canonical_llms_url(observation.get("url"))

    status_code = observation.get("status_code")
    if type(status_code) is not int or not 0 <= status_code <= 599:
        raise ValueError("Malformed llms.txt status code")
    content_type = observation.get("content_type")
    if content_type is not None and (not isinstance(content_type, str) or len(content_type) > 500):
        raise ValueError("Malformed llms.txt content type")
    body = observation.get("body")
    if body is not None and not isinstance(body, str):
        raise ValueError("Malformed llms.txt body")
    for key in ("body_truncated", "access_limited", "fetch_error"):
        value = observation.get(key)
        if value is not None and type(value) is not bool:
            raise ValueError(f"Malformed llms.txt {key}")

    uncertain = bool(observation.get("body_truncated") or observation.get("access_limited") or observation.get("fetch_error"))
    base = {
        "version": VERSION,
        "url": url,
        "scope_path": _scope_path(url),
        "presence": "not_verified",
        "format_status": "not_verified",
        "title": "",
        "has_summary": False,
        "section_count": 0,
        "linked_resource_count": 0,
        "content_digest": "",
        "evidence_ref": "",
        "validation_scope": "required_h1_and_bounded_structure_only",
        "claim_boundary": "optional_structural_metadata_not_provider_fetch_indexing_inclusion_citations_ranking_visibility_or_traffic",
    }

    if uncertain or status_code in {401, 403, 407, 429} or status_code >= 500:
        return base

    if status_code in {404, 410}:
        base.update(presence="absent", format_status="not_applicable")
        return base

    if status_code != 200:
        return base

    if body is None:
        return base
    encoded = body.encode("utf-8")
    if len(encoded) > MAX_BODY_BYTES or "\x00" in body:
        return base
    lines = body.lstrip("\ufeff").splitlines()
    if len(lines) > MAX_LINES:
        return base
    first_index = next((i for i, line in enumerate(lines) if line.strip()), None)
    if first_index is None:
        digest = sha256(encoded).hexdigest()
        base.update(presence="present", format_status="invalid", content_digest=digest,
                    evidence_ref=_evidence_ref(url, status_code, digest))
        return base

    h1 = _H1.match(lines[first_index])
    title = h1.group(1).strip() if h1 else ""
    later_h1 = any(_H1.match(line) for line in lines[first_index + 1:])
    valid = bool(title) and not later_h1

    has_summary = False
    section_count = 0
    link_count = 0
    for line in lines[first_index + 1:]:
        if line.lstrip().startswith(">") and line.lstrip()[1:].strip():
            has_summary = True
        if _H2.match(line):
            section_count += 1
        link_match = _LIST_LINK.match(line)
        if link_match and link_count < MAX_LINKS and _safe_link(link_match.group(1)):
            link_count += 1

    digest = sha256(encoded).hexdigest()
    base.update(
        presence="present",
        format_status="valid" if valid else "invalid",
        title=title if valid else "",
        has_summary=has_summary,
        section_count=section_count,
        linked_resource_count=link_count,
        content_digest=digest,
        evidence_ref=_evidence_ref(url, status_code, digest),
    )
    return base
