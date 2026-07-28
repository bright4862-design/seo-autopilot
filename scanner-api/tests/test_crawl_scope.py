from app.scanner import resolve_crawl_scope


def test_leaf_seed_defaults_to_full_origin_scope():
    prefix, source, seed_path = resolve_crawl_scope(
        None,
        "/credit-immobilier/index.html",
    )

    assert prefix == "/"
    assert source == "origin_root"
    assert seed_path == "/credit-immobilier/index.html"


def test_explicit_subtree_scope_remains_authoritative():
    prefix, source, seed_path = resolve_crawl_scope(
        "/credit-immobilier/",
        "/credit-immobilier/index.html",
    )

    assert prefix == "/credit-immobilier"
    assert source == "explicit_path_prefix"
    assert seed_path == "/credit-immobilier/index.html"


def test_country_language_seed_keeps_one_market_scope():
    prefix, source, seed_path = resolve_crawl_scope(
        None,
        "/fr/fr/cat/canapes-10661",
    )

    assert prefix == "/fr/fr"
    assert source == "requested_market_path"
    assert seed_path == "/fr/fr/cat/canapes-10661"
