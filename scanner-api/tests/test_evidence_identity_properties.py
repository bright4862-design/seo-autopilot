"""Properties of the two keys every dedup and cross-scan decision rests on.

`evidence_url_key` decides whether two URLs are the same piece of evidence, and
`template_family_key` decides whether they belong to the same page family.
Between them they decide whether a repair is a duplicate, whether a group covers
a page, and whether a repair seen in two scans is the same repair. Both of the
recent production incidents -- the Ike duplicate cards and the `mixed` family
collapse -- were failures of code sitting directly on top of these.

The architecture review notes the repo has no property-based testing. These are
properties rather than examples: each is checked across the cross product of
paths, queries, cases and URL forms below, so a regression has to hold for every
combination rather than the one a hand-written example happened to pick.

Written without `hypothesis` deliberately -- it is not a declared dependency,
and adding one would touch the release Docker image. The generator is bounded
and deterministic, so a failure names an exact input and reproduces every run.
"""
import itertools

import pytest

from app.repair_coverage import evidence_url_key, template_family_key

PATHS = [
    "/",
    "/a",
    "/a/b",
    "/menu/location/soho",
    "/loans/dscr-rental-loans",
    "/blog/2026/how-to-fix-canonicals",
    "/produits/caté-gorie",
    "/a.b/c-d_e",
    "/deep/" + "/".join(f"seg{i}" for i in range(8)),
]

TRACKING = [
    "utm_source=news",
    "utm_medium=email&utm_campaign=spring",
    "gclid=abc123",
    "fbclid=xyz&mc_cid=1",
    "ref=partner&source=footer",
]

REAL_QUERIES = ["page=2", "id=7&sort=asc", "q=blue+widget"]

FRAGMENTS = ["", "#top", "#section-2"]

ORIGINS = ["", "https://example.com", "https://www.example.com", "http://example.com"]


def build(path, query="", fragment="", origin=""):
    url = f"{origin}{path}"
    if query:
        url += f"?{query}"
    return url + fragment


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("tracking", TRACKING)
def test_tracking_parameters_never_change_evidence_identity(path, tracking):
    """A campaign tag identifies a visitor, never a page.

    If it leaked into the key, one page arriving from five campaigns would count
    as five affected pages and inflate every repair that touched it.
    """
    assert evidence_url_key(build(path, tracking)) == evidence_url_key(path)


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("query", REAL_QUERIES)
def test_query_parameter_order_never_changes_evidence_identity(path, query):
    pairs = query.split("&")
    if len(pairs) < 2:
        pytest.skip("single-parameter query has no ordering to vary")
    forward = evidence_url_key(build(path, "&".join(pairs)))
    reverse = evidence_url_key(build(path, "&".join(reversed(pairs))))
    assert forward == reverse


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("fragment", FRAGMENTS)
@pytest.mark.parametrize("origin", ORIGINS)
def test_fragment_and_origin_never_change_evidence_identity(path, fragment, origin):
    """The same page is the same evidence however it was written down."""
    assert evidence_url_key(build(path, "", fragment, origin)) == evidence_url_key(path)


@pytest.mark.parametrize("path", PATHS)
def test_trailing_slash_and_path_case_never_change_evidence_identity(path):
    assert evidence_url_key(path.rstrip("/") + "/") == evidence_url_key(path)
    assert evidence_url_key(path.upper()) == evidence_url_key(path.lower())


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("query", REAL_QUERIES + [""])
def test_template_family_key_ignores_the_query_entirely(path, query):
    """A query string does not change a page's template, so it must not split a family.

    If it did, one template would fragment into a family per query variant and
    every group card would collapse to `mixed`.
    """
    assert template_family_key(build(path, query)) == template_family_key(path)


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("query", REAL_QUERIES)
def test_a_real_query_parameter_is_still_significant_evidence(path, query):
    """The stripping is targeted: two genuinely different pages stay different.

    Over-normalizing would be the mirror defect -- distinct pages silently
    merging into one and under-reporting the affected count.
    """
    assert evidence_url_key(build(path, query)) != evidence_url_key(path)


@pytest.mark.parametrize("left,right", list(itertools.combinations(PATHS, 2)))
def test_distinct_paths_keep_distinct_identities(left, right):
    assert evidence_url_key(left) != evidence_url_key(right)


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("tracking", TRACKING)
@pytest.mark.parametrize("origin", ORIGINS)
def test_same_evidence_identity_implies_same_template_family(path, tracking, origin):
    """The cross-function invariant dedup relies on.

    `suppress_group_covered_singletons` matches a page against a group's list by
    evidence key, while scope normalization partitions the same URLs by family
    key. If two URLs could share an evidence key but land in different families,
    a group would cover a page it does not belong to.
    """
    variant = build(path, tracking, "#x", origin)
    if evidence_url_key(variant) == evidence_url_key(path):
        assert template_family_key(variant) == template_family_key(path)


@pytest.mark.parametrize("junk", ["", None, "   ", "?", "#", "://", "not a url at all", 0, [], {}])
def test_degenerate_input_never_raises(junk):
    """These keys run over crawler output, which is not always well formed."""
    assert isinstance(evidence_url_key(junk), str)
    assert isinstance(template_family_key(junk), str)


@pytest.mark.parametrize("blank", ["", None, "   ", "\n\t"])
def test_blank_input_produces_no_identity(blank):
    """Callers treat a non-empty key as a real piece of evidence and count it."""
    assert evidence_url_key(blank) == ""
    assert template_family_key(blank) == ""


@pytest.mark.parametrize("pathless", ["?", "#", "?a=1", "#top"])
def test_a_pathless_url_currently_normalizes_to_root(pathless):
    """Characterization, not endorsement -- and the two modules disagree.

    `extract.classify_template` refuses to call an absent path the homepage,
    with a comment naming the incident it caused: "126 cross-family URLs came to
    be compared against one homepage. Absence of a path is unknown; only a real
    root is the root." This module has not learned that lesson: a URL with no
    path keys as `/`, so a malformed affected-page entry can be counted as, and
    covered by, the homepage.

    Pinned as-is deliberately. Changing it moves REPAIR_COVERAGE_VERSION and the
    release fingerprint, which is not a change to make while a deploy is in
    flight. This test exists so the behaviour is visible and so the fix, when it
    comes, is a deliberate edit to a failing assertion rather than a surprise.
    """
    assert template_family_key(pathless) == "/"
