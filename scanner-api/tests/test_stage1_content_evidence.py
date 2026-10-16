import pytest

from app.extract import extract_page
from app.review_calibration import apply_review_evidence_calibration, image_alt_evidence


def page(body, *, head="", path="/catalog", **kwargs):
    url = f"https://example.com{path}"
    return extract_page(
        f"<html><head><title>Catalog</title>{head}</head><body>{body}</body></html>",
        url, url, kwargs.pop("status_code", 200), "text/html", {}, **kwargs,
    )


def test_main_placement_large_size_and_subject_filename_do_not_prove_image_materiality():
    extracted = page('<main><h1>Catalog</h1><img src="product-hero.jpg" width="1200" height="900"></main>')
    observed = extracted.get("image_alt_applicability", {})
    assert observed.get("material_missing_alt_count") == 0
    assert observed["uncertain_missing_alt_count"] == 1
    assert observed["observations"][0]["applicability"] == "uncertain"
    assert observed["observations"][0]["placement"] == "main"
    assert image_alt_evidence(extracted)["material"] is False
    assert image_alt_evidence(extracted)["missing_alt"] == 1


def test_caption_subject_semantics_and_unnamed_image_controls_prove_applicability():
    extracted = page('''<main>
      <figure><img src="a.jpg"><figcaption>Handmade cedar table.</figcaption></figure>
      <div itemscope itemtype="https://schema.org/Product"><span itemprop="name">Cedar table</span><img itemprop="image" src="b.jpg"></div>
      <button><img src="next.svg"></button>
      <a href="/cart"><img src="cart.svg"></a>
      <img src="empty.svg" alt=""><img src="space.svg" alt="   ">
    </main>''')
    observed = extracted.get("image_alt_applicability", {})
    assert observed.get("material_missing_alt_count") == 4
    assert observed["empty_alt_count"] == 2
    assert observed["absent_alt_count"] == extracted["image_missing_alt_count"] == 4
    assert image_alt_evidence(extracted)["material_missing_alt"] == 4
    assert image_alt_evidence(extracted)["material"] is True
    assert {item["reason"] for item in observed["observations"] if item["applicability"] == "material"} == {
        "visible_caption", "explicit_subject_image", "unnamed_image_control",
    }


def test_named_controls_and_unlabelled_figures_are_uncertain_not_decorative():
    extracted = page('''<main>
      <a href="/cart" aria-label="Cart"><img src="cart.svg"></a>
      <button aria-labelledby="next-label"><img src="next.svg"></button><span id="next-label">Next</span>
      <button><img src="next.svg">Next</button>
      <figure><img src="unknown.jpg"></figure>
    </main>''')
    observed = extracted.get("image_alt_applicability", {})
    assert observed.get("material_missing_alt_count") == 0
    assert observed["uncertain_missing_alt_count"] == 4
    assert observed["excluded_missing_alt_count"] == 0


def test_hidden_presentation_and_code_images_are_explicitly_excluded():
    extracted = page('''<main><img role="presentation" src="line.svg">
      <div hidden><img src="hidden.jpg"></div>
      <section style="display: none"><div style="visibility:hidden"><img src="nested.jpg"></div></section>
      <div aria-hidden="TRUE"><img src="aria.jpg"></div><pre><img src="example.jpg"></pre>
      <p>Our catalog offers handmade furniture for your home.</p></main>''')
    observed = extracted.get("image_alt_applicability", {})
    assert observed.get("excluded_missing_alt_count") == 5
    assert observed["uncertain_missing_alt_count"] == observed["material_missing_alt_count"] == 0
    assert extracted["image_missing_alt_count"] == 5


def test_image_counts_do_not_truncate_with_per_image_samples():
    extracted = page('<main>' + '<img src="unknown.jpg">' * 75 + '</main>')
    observed = extracted.get("image_alt_applicability", {})
    assert observed.get("uncertain_missing_alt_count") == 75
    assert observed["observation_count"] == 75
    assert len(observed["observations"]) <= 40
    assert observed["samples_truncated"] is True
    assert observed["observations"][0]["ordinal"] == 1


@pytest.mark.parametrize("text,kind", [
    ("Welcome {{customer.name}}", "unresolved_template"),
    ("{% if product %}", "unresolved_template"),
    ("Hello #CUSTOMER_NAME#", "unresolved_template"),
    ("Hello %%CUSTOMER_NAME%%", "unresolved_template"),
    ("Hello ${customer.name}", "unresolved_template"),
    ("Product: [object Object]", "runtime_value"),
    ("Price: undefined", "runtime_value"),
    ("Price: $NaN", "runtime_value"),
    ("Lorem ipsum dolor sit amet", "placeholder_copy"),
])
def test_generic_visible_tokens_outside_location_routes_are_retained(text, kind):
    extracted = page(f"<main><h1>Catalog</h1><p>{text}</p></main>")
    evidence = extracted.get("visible_template_evidence", {})
    assert evidence.get("state") == "fail"
    assert evidence["accepted"] is True
    assert kind in evidence["issue_types"]
    assert any(sample["placement"] == "main" and text in sample["snippet"] for sample in evidence["samples"])


def test_template_placements_and_total_count_survive_sample_bounds():
    # Use the title seam itself, independently of the test fixture's normal title.
    extracted = extract_page(
        '<title>{{title}}</title><meta name="description" content="Shop #PRODUCT#">'
        '<main><h1>Hello {{heading}}</h1>' + '<p>Hello {{item}}</p>' * 9 + '</main>',
        'https://example.com/catalog', 'https://example.com/catalog', 200, 'text/html', {},
    )
    evidence = extracted.get("visible_template_evidence", {})
    assert evidence.get("issue_count") == 12
    assert [sample["placement"] for sample in evidence["samples"]] == ["title", "meta", "h1", "main"]
    assert len(evidence["samples"]) == 4
    assert all(len(sample["snippet"]) <= 260 for sample in evidence["samples"])
    assert evidence["samples_truncated"] is True


def test_template_snippet_contains_late_token_and_is_bounded():
    extracted = page('<main><p>' + 'Useful furniture. ' * 100 + '{{unfinished}}' + ' More details.' * 100 + '</p></main>')
    evidence = extracted.get("visible_template_evidence", {})
    assert evidence.get("issue_count") == 1
    assert '{{unfinished}}' in evidence["samples"][0]["snippet"]
    assert len(evidence["samples"][0]["snippet"]) <= 260


@pytest.mark.parametrize("wrapper", [
    '<script>{}</script>', '<style>{}</style>', '<template>{}</template>', '<noscript>{}</noscript>',
    '<code>{}</code>', '<pre>{}</pre>', '<div hidden>{}</div>', '<div aria-hidden="true">{}</div>',
    '<div aria-hidden="TRUE">{}</div>', '<div style="display: none !important">{}</div>',
    '<div style="visibility:hidden"><div style="display:none">{}</div></div>',
])
def test_nonvisible_and_code_tokens_do_not_create_generic_or_location_issues(wrapper):
    extracted = page(
        '<main><h1>Alaska lenders</h1><p>We support local borrowers with lending options.</p>'
        + wrapper.format('#location# As Georgia hard money lenders, contact us. {{broken}}') + '</main>',
        path='/locations/alaska',
    )
    assert extracted.get("visible_template_evidence", {}).get("state") == "pass"
    assert extracted["template_content_issue_types"] == []
    assert extracted["template_content_issue_count"] == 0


@pytest.mark.parametrize("text", [
    'Undefined behavior is a term used in programming language specifications.',
    'The NaN value is explained in this JavaScript guide.',
    'This tutorial explains why JavaScript displays [object Object].',
    'Use {{customer.name}} as an example of template syntax.',
    'Lorem ipsum is filler text used by designers; replace it before publication.',
])
def test_legitimate_explanatory_prose_is_not_a_template_failure(text):
    extracted = page(f'<main><h1>Learning resources</h1><p>{text}</p></main>')
    assert extracted.get("visible_template_evidence", {}).get("state") == "pass"


@pytest.mark.parametrize("body,kind", [
    ('<main></main>', 'empty_shell'),
    ('<main><h1>Coming Soon</h1><p>Stay tuned.</p></main>', 'coming_soon_shell'),
])
def test_empty_and_unfinished_shells_have_explicit_evidence(body, kind):
    evidence = page(body).get("visible_template_evidence", {})
    assert evidence.get("state") == "fail"
    assert kind in evidence["issue_types"]


@pytest.mark.parametrize("body", [
    '<main><h1>Coming Soon</h1><p>Our Cedar store opens October 12 at 44 Pine Street. Join us for opening day.</p></main>',
    '<main><h1>Coming Soon</h1><form><label>Email<input type="email"></label><button>Notify me</button></form></main>',
    '<main><h1>Coming Soon</h1><video controls src="preview.mp4"></video></main>',
    '<main><img src="portfolio.jpg" alt="My portfolio"></main>',
])
def test_substantive_announcements_forms_and_media_are_not_empty_shells(body):
    assert page(body).get("visible_template_evidence", {}).get("state") == "pass"


@pytest.mark.parametrize("kwargs", [
    {"body_truncated": True}, {"status_code": 403}, {"status_code": 202},
    {"response_headers": {"cf-mitigated": "challenge"}},
])
def test_unaccepted_html_has_unknown_content_applicability(kwargs):
    extracted = page('<main><h1>{{broken}}</h1><figure><img src="a"><figcaption>Product</figcaption></figure></main>', **kwargs)
    for field in ("image_alt_applicability", "visible_template_evidence"):
        evidence = extracted.get(field, {})
        assert evidence.get("accepted") is False
        assert evidence["state"] == "not_verified"
    assert extracted["image_alt_applicability"]["material_missing_alt_count"] is None
    assert extracted["visible_template_evidence"]["issue_count"] is None
    assert image_alt_evidence(extracted)["material"] is False


def test_new_alt_calibration_keeps_uncertainty_as_non_scoring_review_evidence():
    extracted = page('<main><img src="unknown.jpg"></main>')
    result = apply_review_evidence_calibration({"health_score": 100, "recommendations": [{
        "rule": "image_alt_text", "category": "image_alt_text", "priority": "high", "affected_pages": ["/catalog"],
    }]}, {"pages": [extracted]})
    fixes = result["recommendations"]
    assert len(fixes) == 1
    assert fixes[0].get("non_scoring") is True
    assert fixes[0]["score_impact"] == 0
    assert fixes[0]["evidence_status"] == "needs_verification"
    assert "decorative" not in fixes[0]["current_value"].lower()


def test_legacy_alt_calibration_retains_count_based_fallback():
    assert image_alt_evidence({"image_count": 1, "image_missing_alt_count": 1}) == {
        "image_count": 1, "missing_alt": 1, "missing_alt_ratio": 1.0, "material": True,
    }
    assert image_alt_evidence({"image_count": 100, "image_missing_alt_count": 1})["material"] is False


def test_calibration_uses_exact_published_identity_with_trusted_context():
    material = page('<main><figure><img src="a"><figcaption>Cedar table</figcaption></figure></main>', path='/x')
    uncertain = page('<main><img src="b"></main>', path='/x/')
    fixes = [{"rule": "image_alt_text", "category": "image_alt_text", "priority": "high", "affected_pages": ['/x', '/x/']}]
    result = apply_review_evidence_calibration(
        {"health_score": 100, "recommendations": fixes}, {"pages": [material, uncertain]},
        scan_origin='https://example.com', identity_version='evidence_url_identity_v2_published_route',
    )
    assert result['recommendations'][0]['affected_pages'] == ['https://example.com/x']
    assert result['recommendations'][0]['missing_alt_total'] == 1


def test_image_accessible_name_can_supply_its_parent_control_name():
    extracted = page('''<main><button><img src="next.svg" aria-label="Next"></button>
      <a href="/cart"><img src="cart.svg" aria-labelledby="cart-label"></a>
      <span id="cart-label">Cart</span></main>''')
    evidence = extracted["image_alt_applicability"]
    assert evidence["material_missing_alt_count"] == 0
    assert evidence["uncertain_missing_alt_count"] == 2


def test_natural_language_undefined_is_not_promoted_by_a_product_label():
    extracted = page('<main><h1>Policies</h1><p>The product undefined in this contract remains outside its scope.</p></main>')
    assert extracted['visible_template_evidence']['state'] == 'pass'


def test_calibration_new_evidence_counts_material_images_without_uncertain_or_excluded_images():
    extracted = page('''<main><figure><img src="table.jpg"><figcaption>Cedar table</figcaption></figure>
      <img src="unknown.jpg"><img src="line.svg" role="presentation"></main>''')
    fixes = [{"rule": "image_alt_text", "category": "image_alt_text", "priority": "high", "affected_pages": ['/catalog']}]
    result = apply_review_evidence_calibration({"health_score": 100, "recommendations": fixes}, {"pages": [extracted]})
    assert result['recommendations'][0]['missing_alt_total'] == 1
    assert result['recommendations'][0].get('uncertain_missing_alt_total') == 1
    assert result['recommendations'][0]['missing_alt_ratio'] == 0.333


def test_calibration_deduplicates_absolute_and_relative_references_to_one_observation():
    extracted = page('<main><figure><img src="table.jpg"><figcaption>Cedar table</figcaption></figure></main>')
    fixes = [{"rule": "image_alt_text", "category": "image_alt_text", "priority": "high", "affected_pages": ['/catalog', 'https://example.com/catalog']}]
    result = apply_review_evidence_calibration(
        {"health_score": 100, "recommendations": fixes}, {"pages": [extracted]},
        scan_origin='https://example.com', identity_version='evidence_url_identity_v2_published_route',
    )
    assert result['recommendations'][0]['page_count'] == 1
    assert result['recommendations'][0]['missing_alt_total'] == 1


def test_inline_hidden_images_do_not_gain_materiality_from_a_visible_caption():
    extracted = page('<main><figure><img src="table.jpg" style="DISPLAY: none"><figcaption>Cedar table</figcaption></figure></main>')
    assert extracted['image_alt_applicability']['material_missing_alt_count'] == 0
    assert extracted['image_alt_applicability']['excluded_missing_alt_count'] == 1


def test_extracting_content_evidence_preserves_schema_and_link_observations():
    extracted = page('''<main><h1>Catalog</h1><p>Useful furniture for your home.</p>
      <a href="/products">Products</a></main>''', head='''<script type="application/ld+json">{"@type":"Product"}</script>''', include_links=True)
    assert extracted['schema_types'] == ['Product']
    assert extracted['_links'] == [{
        'href': 'https://example.com/products',
        'text': 'Products',
        'navigation_presence': False,
    }]
    assert extracted['geo_evidence']['accepted'] is True
