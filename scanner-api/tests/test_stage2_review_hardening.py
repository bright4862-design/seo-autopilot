from app.accepted_content_evidence import extract_accepted_content_evidence
from app.redirect_validation import _redirect_meaning_evidence, _redirect_outcome


def test_hidden_image_control_is_excluded_without_post_sanitize_node_access():
    evidence = extract_accepted_content_evidence(
        """
        <html><body><main>
          <div hidden><a href="/cart"><img src="hidden-cart.svg"></a></div>
          <button><img src="visible-next.svg"></button>
        </main></body></html>
        """,
        "usable_html",
    )["image_alt_applicability"]

    assert evidence["image_count"] == 2
    assert evidence["absent_alt_count"] == 2
    assert evidence["excluded_missing_alt_count"] == 1
    assert evidence["material_missing_alt_count"] == 1
    assert evidence["uncertain_missing_alt_count"] == 0
    assert evidence["observations"] == [
        {
            "ordinal": 1,
            "placement": "main",
            "alt_state": "absent",
            "applicability": "excluded",
            "reason": "hidden_or_example_content",
        },
        {
            "ordinal": 2,
            "placement": "main",
            "alt_state": "absent",
            "applicability": "material",
            "reason": "unnamed_image_control",
        },
    ]


def test_diagnostic_only_redirect_loop_without_hops_stays_unverified():
    page = {
        "url": "https://example.com/a",
        "final_url": "https://example.com/a",
        "status_code": 302,
        "content_type": "text/html",
    }
    evidence = {
        "state": "redirect_loop",
        "source_url": "https://example.com/a",
        "destination_url": "https://example.com/a",
        "destination_status_code": 302,
        "hop_count": 0,
        "hops": [],
        "chain": ["https://example.com/a"],
    }

    meaning = _redirect_meaning_evidence(page, evidence)

    assert meaning["state"] == "not_verified"
    assert meaning["reason"] == "redirect_loop_unverified"


def test_redirect_loop_with_concrete_hop_evidence_is_verified_unusable():
    page = {
        "url": "https://example.com/a",
        "final_url": "https://example.com/a",
        "status_code": 302,
        "content_type": "text/html",
    }
    evidence = {
        "state": "redirect_loop",
        "source_url": "https://example.com/a",
        "destination_url": "https://example.com/a",
        "destination_status_code": 302,
        "hop_count": 2,
        "hops": [
            {"url": "https://example.com/a", "status_code": 302, "location": "https://example.com/b"},
            {"url": "https://example.com/b", "status_code": 302, "location": "https://example.com/a"},
        ],
        "chain": ["https://example.com/a", "https://example.com/b", "https://example.com/a"],
    }

    meaning = _redirect_meaning_evidence(page, evidence)

    assert meaning["state"] == "verified_unusable"
    assert meaning["reason"] == "redirect_loop"


def test_challenged_redirect_destination_403_stays_unverified_not_unusable():
    page = {
        "url": "https://example.com/old",
        "final_url": "https://example.com/protected",
        "status_code": 403,
        "content_type": "text/html",
        "access_block_kind": "challenge",
        "fetch_error": "",
    }
    evidence = {
        "state": "single_redirect",
        "source_url": "https://example.com/old",
        "destination_url": "https://example.com/protected",
        "destination_status_code": 403,
        "hop_count": 1,
        "hops": [
            {"url": "https://example.com/old", "status_code": 302, "location": "https://example.com/protected"}
        ],
        "chain": ["https://example.com/old", "https://example.com/protected"],
    }

    meaning = _redirect_meaning_evidence(page, evidence)
    outcome = _redirect_outcome(page, evidence, "Unknown because of access or rendering limitations", meaning)

    assert meaning["state"] == "not_verified"
    assert meaning["reason"] == "destination_access_unverified"
    assert outcome == "redirect_destination_unverified"


def test_genuine_redirect_destination_404_remains_verified_unusable():
    page = {
        "url": "https://example.com/old",
        "final_url": "https://example.com/missing",
        "status_code": 404,
        "content_type": "text/html",
        "access_block_kind": "",
        "fetch_error": "",
    }
    evidence = {
        "state": "single_redirect",
        "source_url": "https://example.com/old",
        "destination_url": "https://example.com/missing",
        "destination_status_code": 404,
        "hop_count": 1,
        "hops": [
            {"url": "https://example.com/old", "status_code": 302, "location": "https://example.com/missing"}
        ],
        "chain": ["https://example.com/old", "https://example.com/missing"],
    }

    meaning = _redirect_meaning_evidence(page, evidence)
    outcome = _redirect_outcome(page, evidence, "HTTP 404", meaning)

    assert meaning["state"] == "verified_unusable"
    assert meaning["reason"] == "destination_http_404"
    assert outcome == "redirect_destination_unusable"
