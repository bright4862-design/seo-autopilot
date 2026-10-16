"""Optional GEO runtime boundary: failures never change the SEO authority result."""
from urllib.parse import urldefrag
from .geo_evidence import assess_geo_pages, _uncertain, VERSION as ADAPTER_VERSION
from .geo_readiness import VERSION


def empty_geo_readiness(status="not_assessed"):
    if status not in {"not_assessed", "evaluation_error"}:
        raise ValueError("Unsupported empty GEO status")
    return dict(geo_readiness_version=VERSION, evidence_adapter_version=ADAPTER_VERSION,
                assessment_status=status, score=None, coverage=0, score_bounds=None,
                bounds_kind="unknown_outcome_range_not_statistical_confidence", sample_pages=0,
                dimensions={}, reasons=[status], authority_verified=False, observations=[], findings=[],
                assessment_gates=dict(parent_authoritative=False, entry_verified=False, access_limited=False))


def assess_review_geo(body, pages, *, parent_authoritative, access_limited=False):
    try:
        entry = body.get("submitted_url") or body.get("website_url") or body.get("url") or ""
        def identity(url):
            return urldefrag(url)[0] if isinstance(url, str) else ""
        entry_verified = bool(entry) and any(
            identity(p.get("url")) == identity(entry)
            and p.get("page_evidence_class") == "usable_html"
            and not _uncertain(p)
            and isinstance(p.get("geo_evidence"), dict)
            and p["geo_evidence"].get("accepted") is True
            for p in pages
        )
        gates = dict(parent_authoritative=parent_authoritative is True,
                     entry_verified=entry_verified, access_limited=access_limited is True)
        return dict(assess_geo_pages(pages, **gates), assessment_gates=gates)
    except Exception:
        # Deliberately retain no exception text, HTML, URL or fabricated diagnostics.
        return empty_geo_readiness("evaluation_error")
