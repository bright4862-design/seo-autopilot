from app.extract import classify_template, estimate_intent
from app.market_scope import market_pair_prefix, path_within_scope, strip_market_locale_prefix


def test_scope_prefix_is_segment_bounded():
    assert path_within_scope("/fr", "/fr")
    assert path_within_scope("/fr/page", "/fr")
    assert not path_within_scope("/france/page", "/fr")


def test_market_pair_and_locale_stripping():
    assert market_pair_prefix("https://www.ikea.com/fr/fr/cat/chairs") == "/fr/fr"
    assert strip_market_locale_prefix("/fr/fr/cat/chairs") == "/cat/chairs"
    assert strip_market_locale_prefix("/fr/page/cgu") == "/page/cgu"


def test_ikea_localized_routes_are_classified_by_template():
    assert classify_template("/fr/fr/") == "homepage"
    assert classify_template("/fr/fr/cat/canapes-10661") == "collection_page"
    assert classify_template("/us/en/p/billy-bookcase-00263850") == "product_page"
    assert classify_template("/fr/fr/customer-service/contact-us/") == "contact"
    assert estimate_intent("/fr/fr/cat/canapes-10661", "", "", 200) == "money_or_conversion"
