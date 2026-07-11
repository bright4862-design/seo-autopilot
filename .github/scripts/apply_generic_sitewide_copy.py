from pathlib import Path

root = Path(__file__).resolve().parents[2]
review = root / "scanner-api/app/review.py"
test = root / "scanner-api/tests/test_review_presentation_contract.py"

old_step = "Verify at least one representative conversion, loan, location, article, legal, contact, standard, and homepage page."
new_step = "Verify at least one representative page from every affected family listed in the card."

text = review.read_text(encoding="utf-8")
if old_step not in text:
    raise SystemExit("Sitewide verification step anchor not found")
review.write_text(text.replace(old_step, new_step, 1), encoding="utf-8")

text = test.read_text(encoding="utf-8")
anchor = '    assert "global document-head" in card["plain_english_explanation"].lower()\n'
addition = (
    anchor
    + '    steps = " ".join(card["what_to_do_steps"]).lower()\n'
    + '    assert "every affected family listed in the card" in steps\n'
    + '    assert "conversion, loan, location" not in steps\n'
)
if anchor not in text:
    raise SystemExit("Sitewide presentation test anchor not found")
test.write_text(text.replace(anchor, addition, 1), encoding="utf-8")
