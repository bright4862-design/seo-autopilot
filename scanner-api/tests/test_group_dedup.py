"""Polish patch 1: grouped template cards suppress per-page duplicates of the same defect class,
without collapsing distinct defects or lone single-page fixes."""

from app.review import run_review


def _run(pages, raw):
    return run_review({
        "website_url": "https://csl.com",
        "pages": pages,
        "raw_fixes": raw,
        "scan_coverage": {
            "pages_found": 20,
            "pages_crawled": len(pages),
            "sampled_pages_sent_to_ai": len(pages),
        },
    })


def _loan_pages(slugs):
    return [
        {
            "final_url": f"https://csl.com/loans/{s}",
            "status_code": 200,
            "h1_count": 1,
            "meta_description": "x",
            "canonical": "",
            "page_template_family": "loan_program",
        }
        for s in slugs
    ]


def test_grouped_canonical_suppresses_per_page_duplicates():
    slugs = ["dscr", "bridge", "fix-and-flip"]
    raw = [
        {
            "rule": "missing_canonical",
            "category": "canonical",
            "title": "Add a canonical URL",
            "page_url": f"https://csl.com/loans/{s}",
            "affected_pages": [f"https://csl.com/loans/{s}"],
        }
        for s in slugs
    ]
    r = _run(_loan_pages(slugs), raw)
    canon = [f for f in r["cleaned_fixes"] if "canonical" in (f.get("category", "") + " " + f.get("rule", "")).lower()]
    assert len(canon) == 1
    assert len(canon[0]["affected_pages"]) == 3
    assert "loan program" in canon[0]["title"].lower()


def test_distinct_defect_on_covered_page_survives():
    slugs = ["dscr", "bridge", "fix-and-flip"]
    raw = [
        {
            "rule": "missing_canonical",
            "category": "canonical",
            "title": "Add a canonical URL",
            "page_url": f"https://csl.com/loans/{s}",
            "affected_pages": [f"https://csl.com/loans/{s}"],
        }
        for s in slugs
    ]
    raw.append({
        "rule": "broken_page",
        "category": "broken_page",
        "title": "Fix broken page",
        "page_url": "https://csl.com/loans/dscr",
        "affected_pages": ["https://csl.com/loans/dscr"],
        "status_code": 404,
    })
    r = _run(_loan_pages(slugs), raw)
    assert sum(1 for f in r["cleaned_fixes"] if f.get("rule") == "broken_page") == 1


def test_lone_single_page_fix_is_not_suppressed():
    pages = [
        {
            "final_url": "https://csl.com/apply-now",
            "status_code": 200,
            "h1_count": 1,
            "meta_description": "x",
            "canonical": "https://csl.com/apply-now",
            "page_template_family": "conversion",
        }
    ]
    raw = [
        {
            "rule": "missing_canonical",
            "category": "canonical",
            "title": "Add a canonical URL",
            "page_url": "https://csl.com/apply-now",
            "affected_pages": ["https://csl.com/apply-now"],
        }
    ]
    r = _run(pages, raw)
    canon = [f for f in r["cleaned_fixes"] if "canonical" in (f.get("category", "") + " " + f.get("rule", "")).lower()]
    assert len(canon) == 1
    assert canon[0]["affected_pages"] == ["/apply-now"]


def test_raw_scanner_multipage_grouping_does_not_suppress_singletons():
    """A raw scanner grouping must not suppress a more specific single-page fix of the same class."""
    pages = _loan_pages(["dscr"])
    pages[0]["canonical"] = "https://csl.com/loans/dscr"
    raw = [
        {
            "rule": "missing_canonical",
            "category": "canonical",
            "title": "Canonical issues",
            "affected_pages": ["https://csl.com/loans/dscr", "https://csl.com/loans/bridge"],
        },
        {
            "rule": "missing_canonical",
            "category": "canonical",
            "title": "Add a canonical URL",
            "page_url": "https://csl.com/loans/dscr",
            "affected_pages": ["https://csl.com/loans/dscr"],
        },
    ]
    r = _run(pages, raw)
    canon = [f for f in r["cleaned_fixes"] if "canonical" in (f.get("category", "") + " " + f.get("rule", "")).lower()]
    assert any(len(f["affected_pages"]) == 1 for f in canon)


def test_our_grouped_evidence_card_suppresses_per_page_404_duplicates():
    """Our grouped broken-page evidence card should suppress per-page 404 scanner duplicates."""
    pages = [
        {
            "final_url": f"https://csl.com/dead{i}",
            "status_code": 404,
            "source_pages": ["https://csl.com/"],
        }
        for i in range(3)
    ]
    raw = [
        {
            "rule": "broken_page",
            "category": "broken_page",
            "title": "Fix broken page",
            "page_url": f"https://csl.com/dead{i}",
            "affected_pages": [f"https://csl.com/dead{i}"],
            "status_code": 404,
        }
        for i in range(3)
    ]
    r = _run(pages, raw)
    broken = [
        f
        for f in r["cleaned_fixes"]
        if "broken" in (f.get("category", "") + " " + f.get("rule", "")).lower()
        or f.get("rule") == "broken_page"
    ]
    assert any(len(f["affected_pages"]) >= 3 for f in broken)
    assert all(len(f["affected_pages"]) != 1 for f in broken)
