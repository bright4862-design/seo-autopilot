"""A bank and an insurer must not be told to fix their loan program pages.

One finance archetype covered businesses that share none of each other's work.
The 35-site production audit caught the cost directly in the customer summary:
N26, a digital bank, and Alan, a health insurer, were both told to "Start with
the highest-impact items on loan program pages, application pages, quote/contact
forms" because the lending playbook was the only one the archetype had.

The sub-playbook refines advice inside the archetype. A correctly classified
lender keeps the lending default, so Pretto is the control that proves this
narrowed the advice instead of relabelling everything.
"""

from app.review import run_review


def page(path, title, description="", host="https://example.com"):
    return {
        "url": f"{host}{path}",
        "final_url": f"{host}{path}",
        "status_code": 200,
        "title": title,
        "h1": title,
        "meta_description": description or title,
        "word_count": 250,
        "indexable": True,
        "page_template_family": "homepage" if path == "/" else "standard",
    }


def review(pages, host="https://example.com"):
    return run_review({
        "website_url": host,
        "pages_found": len(pages),
        "pages_crawled": len(pages),
        "pages": pages,
    })


DIGITAL_BANK = [
    page("/", "The mobile bank you'll love", "Open a bank account with a debit card"),
    page("/bank-account", "Bank account"),
    page("/cards", "Debit cards"),
    page("/accounts/premium", "Premium account"),
    page("/legal-documents", "Legal documents"),
    page("/team", "Our team"),
]

HEALTH_INSURER = [
    page("/", "Health insurance for your team", "Assurance sante for companies"),
    page("/coverage/v23720", "Coverage"),
    page("/coverage/v253437", "Coverage"),
    page("/fr-fr/assurance-sante/fonction-publique", "Assurance sante"),
    page("/en/healthybusiness", "Healthy business"),
]

MORTGAGE_BROKER = [
    page("/", "Courtier en pret immobilier", "Simulation de pret immobilier gratuite"),
    page("/pret-immobilier", "Pret immobilier"),
    page("/simulation-pret-immobilier", "Simulation"),
    page("/taux-immobilier", "Taux"),
    page("/devis", "Devis"),
]


def test_a_digital_bank_is_not_sold_a_lending_playbook():
    result = review(DIGITAL_BANK)
    fingerprint = result["site_fingerprint"]
    assert fingerprint["primary_archetype"] == "finance_insurance_lead_gen"
    assert fingerprint["finance_sub_playbook"] == "digital_bank"
    assert fingerprint["archetype_label"] == "digital bank / consumer fintech"
    summary = result["plain_english_summary"]
    assert "loan program pages" not in summary, summary
    assert "account and card product pages" in summary, summary


def test_an_insurer_is_not_sold_a_lending_playbook():
    result = review(HEALTH_INSURER)
    fingerprint = result["site_fingerprint"]
    assert fingerprint["finance_sub_playbook"] == "insurance"
    assert fingerprint["archetype_label"] == "insurance"
    summary = result["plain_english_summary"]
    assert "loan program pages" not in summary, summary
    assert "coverage and plan pages" in summary, summary


def test_a_mortgage_broker_keeps_the_lending_default():
    result = review(MORTGAGE_BROKER)
    fingerprint = result["site_fingerprint"]
    assert fingerprint["finance_sub_playbook"] == ""
    assert fingerprint["archetype_label"] == "finance / insurance / lead generation"
    assert "loan program pages" in result["plain_english_summary"]


def test_the_decision_survives_the_pipeline_rebuilding_the_playbook():
    # The review pipeline rebuilds the playbook from the archetype key alone.
    # Without the fingerprint carrying the decision, the summary reverts to the
    # lending wording while the fingerprint still claims the sub-playbook.
    result = review(DIGITAL_BANK)
    assert result["site_fingerprint"]["archetype_label"] == "digital bank / consumer fintech"
    assert "digital bank / consumer fintech playbook" in result["plain_english_summary"]


def test_one_incidental_route_does_not_rewrite_the_playbook():
    # A lender that happens to mention a card is still a lender. Overriding on a
    # single route would relabel businesses on incidental evidence.
    pages = MORTGAGE_BROKER + [page("/cards", "Our partner card")]
    fingerprint = review(pages)["site_fingerprint"]
    assert fingerprint["finance_sub_playbook"] == ""
    assert fingerprint["archetype_label"] == "finance / insurance / lead generation"
