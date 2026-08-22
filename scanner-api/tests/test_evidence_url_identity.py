"""Patch D - one URL identity, agreed between Python and JavaScript.

Python decides a repair's partitions and Base44 re-verifies them. If the two
disagree about whether "/a?b=1&c=2" and "/a?c=2&b=1" are the same URL, then a
payload Python considers valid fails Base44's invariants -- or worse, passes
them while describing a different set of pages.

Two identities, deliberately distinct:

  template family identity  path only. Query and fragment do not change a
                            page's template, and including them would split one
                            family into many.
  evidence identity         path plus canonical query. Two URLs that differ only
                            by tracking parameters are the same evidence; two
                            that differ by a real parameter are not.

The JavaScript half asserts the identical table in
tests/frontend/evidenceUrlIdentityParity.test.mjs.
"""
import json
from pathlib import Path

import pytest

from app.repair_coverage import evidence_url_key, template_family_key

# The shared table. Both languages read this file; neither owns it.
PARITY_CASES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "evidence-url-identity.json"


@pytest.fixture(scope="module")
def cases():
    return json.loads(PARITY_CASES.read_text(encoding="utf-8"))["cases"]


def test_the_shared_table_exists_and_is_not_empty(cases):
    assert len(cases) >= 12


def test_python_matches_the_shared_table(cases):
    for case in cases:
        assert template_family_key(case["url"]) == case["template_family_key"], case["url"]
        assert evidence_url_key(case["url"]) == case["evidence_url_key"], case["url"]


# --------------------------------------------------------- the properties --


def test_a_fragment_never_changes_identity():
    assert evidence_url_key("https://ex.com/a#top") == evidence_url_key("https://ex.com/a")


def test_query_order_never_changes_evidence_identity():
    assert evidence_url_key("/a?b=1&c=2") == evidence_url_key("/a?c=2&b=1")


def test_a_real_parameter_does_change_evidence_identity():
    assert evidence_url_key("/a?page=2") != evidence_url_key("/a")


def test_tracking_parameters_do_not_change_evidence_identity():
    assert evidence_url_key("/a?utm_source=x&utm_medium=y") == evidence_url_key("/a")
    assert evidence_url_key("/a?gclid=123") == evidence_url_key("/a")


def test_duplicate_keys_are_kept_in_a_stable_order():
    """Dropping one silently would merge two genuinely different pages."""
    assert evidence_url_key("/a?x=1&x=2") == evidence_url_key("/a?x=2&x=1")
    assert evidence_url_key("/a?x=1&x=2") != evidence_url_key("/a?x=1")


def test_percent_encoding_is_normalised():
    assert evidence_url_key("/a%2Db") == evidence_url_key("/a-b")


def test_an_uppercase_extension_is_the_same_page():
    assert evidence_url_key("/Doc.PDF") == evidence_url_key("/doc.pdf")


def test_a_trailing_slash_is_the_same_page():
    assert evidence_url_key("/a/") == evidence_url_key("/a")
    assert evidence_url_key("/") == "/"


def test_template_family_identity_ignores_the_query_entirely():
    assert template_family_key("/a?page=2") == template_family_key("/a")
    assert template_family_key("/a?utm_source=x") == template_family_key("/a")
