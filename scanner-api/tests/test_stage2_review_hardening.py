from app.accepted_content_evidence import extract_accepted_content_evidence


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
