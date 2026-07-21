from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLD_FINGERPRINT = "6fe5526e10adf27d"
NEW_CANONICAL_VERSION = "canonical_href_resolution_v2_absolute_single_label_same_path"
EXPECTED_NEW_FINGERPRINT = "d69d625dbeaee154"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one locator, found {count}")
    write(path, content.replace(old, new, 1))


old_block = '''CANONICAL_HREF_RESOLUTION_VERSION = "canonical_href_resolution_v1_hostless_same_path"


def _canonical_path_key(value: str) -> str:
    path = str(value or "/").split("?", 1)[0].split("#", 1)[0]
    return path.rstrip("/") or "/"


def resolve_canonical_href(base_url: str, href: str) -> str:
    """Resolve canonical hrefs without turning a same-path slug into a fake host.

    Some HTML generators emit a root-relative canonical as ``//slug/``. URL
    joining normally interprets that as a scheme-relative host. We only repair
    the value when the authority is a single label and rebuilding it as a path
    exactly matches the final page path. Genuine scheme-relative domains keep
    normal URL semantics and remain eligible for cross-domain validation.
    """
    raw = str(href or "").strip()
    if not raw:
        return ""
    if raw.startswith("//"):
        candidate = urlparse(raw)
        base = urlparse(str(base_url or ""))
        hostname = (candidate.hostname or "").lower().strip(".")
        reconstructed_path = f"/{hostname}{candidate.path or ''}"
        is_plain_single_label = bool(hostname) and "." not in hostname and candidate.netloc.lower() == hostname
        if (
            is_plain_single_label
            and candidate.query == base.query
            and _canonical_path_key(reconstructed_path) == _canonical_path_key(base.path or "/")
        ):
            return base._replace(
                path=reconstructed_path,
                query=candidate.query,
                fragment=candidate.fragment,
            ).geturl()
    return urljoin(base_url, raw)
'''

new_block = '''CANONICAL_HREF_RESOLUTION_VERSION = "canonical_href_resolution_v2_absolute_single_label_same_path"


def _canonical_path_key(value: str) -> str:
    path = str(value or "/").split("?", 1)[0].split("#", 1)[0]
    return path.rstrip("/") or "/"


def _repair_single_label_same_path(base_url: str, raw: str) -> str:
    """Return the final page URL for a malformed single-label same-page href."""
    candidate = urlparse(raw)
    base = urlparse(str(base_url or ""))
    hostname = (candidate.hostname or "").lower().strip(".")
    if not hostname or "." in hostname:
        return ""
    if candidate.username or candidate.password or candidate.port is not None:
        return ""
    if candidate.netloc.lower().strip(".") != hostname:
        return ""
    if candidate.scheme and candidate.scheme.lower() not in {"http", "https"}:
        return ""
    if candidate.scheme and candidate.path not in {"", "/"}:
        return ""
    reconstructed_path = f"/{hostname}{candidate.path or ''}"
    if candidate.query != base.query:
        return ""
    if _canonical_path_key(reconstructed_path) != _canonical_path_key(base.path or "/"):
        return ""
    return base._replace(
        path=base.path or "/",
        query=base.query,
        fragment=candidate.fragment,
    ).geturl()


def resolve_canonical_href(base_url: str, href: str) -> str:
    """Resolve canonicals while repairing only exact same-page malformed hosts.

    Two malformed forms have appeared in production: ``//slug/`` and
    ``http://slug``. Both normally parse as a host. They are repaired only when
    the host is a plain single label and rebuilding it as a path exactly matches
    the final page path. Dotted or different-path external domains retain normal
    URL semantics and remain eligible for cross-domain validation.
    """
    raw = str(href or "").strip()
    if not raw:
        return ""
    candidate = urlparse(raw)
    is_scheme_relative = raw.startswith("//")
    is_absolute_http = candidate.scheme.lower() in {"http", "https"} and bool(candidate.netloc)
    if is_scheme_relative or is_absolute_http:
        repaired = _repair_single_label_same_path(base_url, raw)
        if repaired:
            return repaired
    return urljoin(base_url, raw)
'''

replace_once("scanner-api/app/extract.py", old_block, new_block)

# Update the existing v1 regression marker and add the exact live v2 case plus controls.
test_path = "scanner-api/tests/test_canonical_origin_alias_equivalence.py"
tests = read(test_path).replace(
    'canonical_href_resolution_v1_hostless_same_path',
    NEW_CANONICAL_VERSION,
)
marker = "def test_absolute_single_label_same_path_canonical_uses_final_origin():"
if marker in tests:
    raise RuntimeError("v2 canonical regression already present")
tests += '''


def test_absolute_single_label_same_path_canonical_uses_final_origin():
    page = extract_page(
        '<html><head><title>Chocolate Milk</title><link rel="canonical" href="http://chocolate-milk"></head><body><h1>Chocolate Milk</h1></body></html>',
        "https://hartzlerdairy.com/chocolate-milk",
        "https://www.hartzlerdairy.com/chocolate-milk/",
        200,
        "text/html",
        DISCOVERY,
    )

    assert page["canonical"] == "https://www.hartzlerdairy.com/chocolate-milk/"
    assert page["canonical_status"] == "self_or_equivalent"
    assert page["canonical_href_resolution_version"] == "canonical_href_resolution_v2_absolute_single_label_same_path"
    assert not any(item["rule"] == "canonical_cross_domain" for item in build_findings([page]))


@pytest.mark.asyncio
async def test_absolute_dotted_external_domain_remains_cross_domain():
    page = extract_page(
        '<html><head><title>Page</title><link rel="canonical" href="http://canonical.example/chocolate-milk/"></head><body><h1>Page</h1></body></html>',
        "https://www.hartzlerdairy.com/chocolate-milk/",
        "https://www.hartzlerdairy.com/chocolate-milk/",
        200,
        "text/html",
        DISCOVERY,
    )

    assert page["canonical"] == "http://canonical.example/chocolate-milk/"
    await validate_canonical_targets(
        FakeClient(),
        [page],
        RobotsPolicy("https://www.hartzlerdairy.com/robots.txt", "missing", 404),
    )
    assert page["canonical_target_state"] == "cross_domain_needs_verification"
    assert any(item["rule"] == "canonical_cross_domain" for item in build_findings([page]))


@pytest.mark.asyncio
async def test_absolute_single_label_different_path_remains_cross_domain():
    page = extract_page(
        '<html><head><title>Page</title><link rel="canonical" href="http://other-page"></head><body><h1>Page</h1></body></html>',
        "https://www.hartzlerdairy.com/chocolate-milk/",
        "https://www.hartzlerdairy.com/chocolate-milk/",
        200,
        "text/html",
        DISCOVERY,
    )

    assert page["canonical"] == "http://other-page"
    await validate_canonical_targets(
        FakeClient(),
        [page],
        RobotsPolicy("https://www.hartzlerdairy.com/robots.txt", "missing", 404),
    )
    assert page["canonical_target_state"] == "cross_domain_needs_verification"
    assert any(item["rule"] == "canonical_cross_domain" for item in build_findings([page]))
'''
write(test_path, tests)

# Advance the frozen revision from the live component set.
revision_path = ROOT / "data/beta-crawler-revision.json"
revision = json.loads(revision_path.read_text(encoding="utf-8"))
revision["component_versions"]["canonical_href_resolution_version"] = NEW_CANONICAL_VERSION
payload = json.dumps(revision["component_versions"], sort_keys=True, separators=(",", ":"))
new_fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
if new_fingerprint != EXPECTED_NEW_FINGERPRINT:
    raise RuntimeError(f"unexpected fingerprint {new_fingerprint}")
revision.update({
    "acceptance_report": "docs/releases/hartzler-absolute-single-label-canonical-v2.md",
    "fingerprint": new_fingerprint,
    "git_commit": "",
    "note": "Hartzler release-blocker candidate: repair an absolute http(s) single-label canonical only when it reconstructs the exact final page path; preserve genuine external domains.",
    "recorded_at": "2026-07-21T00:00:00Z",
    "status": "candidate",
})
revision_path.write_text(json.dumps(revision, indent=2) + "\n", encoding="utf-8")

# Frontend and test authority markers must match the advanced backend fingerprint.
for path in [
    "src/lib/scanRunModel.js",
    "tests/frontend/releaseAuthorityGate.test.mjs",
    "tests/frontend/scanRunPersistence.test.mjs",
    "scanner-api/tests/test_observability.py",
]:
    content = read(path)
    if OLD_FINGERPRINT not in content:
        raise RuntimeError(f"{path}: old fingerprint not found")
    write(path, content.replace(OLD_FINGERPRINT, new_fingerprint))

report = '''# Hartzler absolute single-label canonical resolution v2

## Exact live evidence

- Requested URL: `https://hartzlerdairy.com/chocolate-milk`
- Redirect: `301` to `https://www.hartzlerdairy.com/chocolate-milk/`
- Final URL: `https://www.hartzlerdairy.com/chocolate-milk/`
- Raw canonical tag: `<link rel="canonical" href="http://chocolate-milk" />`
- Raw href: `http://chocolate-milk`

## Scope

- Repairs an absolute `http(s)://<single-label>` canonical only when the single label reconstructs the exact final page path.
- Retains the earlier scheme-relative same-path repair.
- Dotted external domains and single-label values that reconstruct a different path remain cross-domain verification findings.

## Candidate

- Canonical href resolution: `canonical_href_resolution_v2_absolute_single_label_same_path`
- Fingerprint: `d69d625dbeaee154`

## Production acceptance

1. Hartzler `/chocolate-milk` has no `canonical_cross_domain` finding.
2. Hartzler remains complete and authoritative.
3. Funbooker remains an authoritative control.
4. Lamanna remains provisional for default-route discovery quality.
'''
write("docs/releases/hartzler-absolute-single-label-canonical-v2.md", report)

print(new_fingerprint)
