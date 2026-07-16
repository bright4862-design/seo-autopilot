from __future__ import annotations

import runpy
from pathlib import Path

script = Path(__file__).with_name("apply_focused_acceptance_followup_v8.py")
text = script.read_text(encoding="utf-8")

count_anchor = '    2,\n    "SaaS structural product routes",\n'
if text.count(count_anchor) != 1:
    raise RuntimeError(f"expected one structural count anchor, found {text.count(count_anchor)}")
text = text.replace(
    count_anchor,
    '    1,\n    "SaaS structural product routes",\n',
    1,
)

insert_after = '    "SaaS structural product routes",\n)\n'
core_block = r'''review = replace_once(
    review,
    '    "/register", "/demo", "/api", "/developers", "/platform", "/apps",\n'
    '    "/download",\n',
    '    "/register", "/demo", "/api", "/developers", "/platform", "/apps",\n'
    '    "/download", "/payments", "/billing", "/connect", "/radar",\n'
    '    "/terminal", "/issuing", "/treasury", "/tax", "/identity",\n'
    '    "/atlas", "/financial-connections",\n',
    "SaaS core product routes",
)
'''
if text.count(insert_after) != 1:
    raise RuntimeError(f"expected one structural insertion anchor, found {text.count(insert_after)}")
text = text.replace(insert_after, insert_after + core_block, 1)
script.write_text(text, encoding="utf-8")
runpy.run_path(str(script), run_name="__main__")

root = Path(__file__).resolve().parents[2]
review_path = root / "scanner-api/app/review.py"
review = review_path.read_text(encoding="utf-8")
old_source_ranking = '        ranked_source_pages = dedupe_strings(ranked_affected[:5] + representative_pages)\n'
new_source_ranking = (
    '        ranked_source_pages = sorted(\n'
    '            representative_pages,\n'
    '            key=lambda url: representative_page_score(\n'
    '                url, {**base, "rule": rule}, page_lookup, body, playbook\n'
    '            ),\n'
    '            reverse=True,\n'
    '        )\n'
)
if review.count(old_source_ranking) != 1:
    raise RuntimeError(f"expected one sitewide source-ranking anchor, found {review.count(old_source_ranking)}")
review_path.write_text(review.replace(old_source_ranking, new_source_ranking, 1), encoding="utf-8")

for test_path in (root / "scanner-api/tests").rglob("*.py"):
    test_text = test_path.read_text(encoding="utf-8")
    updated = test_text.replace(
        'startswith("archetype_classifier_v7")',
        'startswith("archetype_classifier_v8")',
    )
    if updated != test_text:
        test_path.write_text(updated, encoding="utf-8")
