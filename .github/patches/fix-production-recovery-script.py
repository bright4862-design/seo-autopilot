from pathlib import Path

path = Path('.github/patches/apply-production-release-recovery.py')
text = path.read_text(encoding='utf-8')

scanner_start_marker = 'replace_once("scanner-api/app/scanner.py", \'\'\'            "scanner_version": VERSION,'
scanner_end_marker = '            "scan_deadline_reached": deadline_reached,\'\'\')'
start = text.find(scanner_start_marker)
end = text.find(scanner_end_marker, start)
if start < 0 or end < 0:
    raise RuntimeError(f'Could not find scanner transformer block: start={start}, end={end}')
end += len(scanner_end_marker)
scanner_replacement = """replace_once(\"scanner-api/app/scanner.py\", '''        \"technical_audit_summary\": {
            \"scanner_version\": VERSION,
            \"pages_crawled\": len(pages),''', '''        \"technical_audit_summary\": {
            \"scanner_version\": VERSION,
            \"scanner_elapsed_ms\": elapsed_ms,
            \"scanner_total_budget_seconds\": budget[\"timeout\"],
            \"scan_deadline_reached\": deadline_reached,
            \"pages_crawled\": len(pages),''')"""
text = text[:start] + scanner_replacement + text[end:]

review_start_marker = 'replace_once("scanner-api/app/review.py", \'\'\'    ecommerce_paths = sum('
review_end_marker = '        adjusted_scores.append((key, score))\'\'\')'
start = text.find(review_start_marker)
end = text.find(review_end_marker, start)
if start < 0 or end < 0:
    raise RuntimeError(f'Could not find review transformer block: start={start}, end={end}')
end += len(review_end_marker)
review_replacement = """replace_once(\"scanner-api/app/review.py\", '''    ecommerce_paths = sum(count_includes(path_text, pattern) for pattern in (\"/products/\", \"/product/\", \"/collections/\", \"/collection/\", \"/cart\", \"/checkout\"))
    saas_paths = sum(count_includes(path_text, pattern) for pattern in (\"/pricing\", \"/features\", \"/use-cases\", \"/solutions\", \"/login\", \"/signup\", \"/docs\", \"/api\"))
    adjusted_scores = []
    for key, score in scores:
        if key == \"ecommerce_specialty_retail\" and ecommerce_paths < 2:
            score = min(score, 1.0)
        if key == \"saas_app_membership\":
            if saas_paths < 2:
                score = min(score, 1.0)
            else:
                score += 12
        adjusted_scores.append((key, score))''', '''    ecommerce_paths = sum(count_includes(path_text, pattern) for pattern in (\"/products/\", \"/product/\", \"/collections/\", \"/collection/\", \"/cart\", \"/checkout\", \"/itm/\", \"/sch/\", \"/b/\", \"/buy/\", \"/shop/\", \"/seller/\", \"/listing/\"))
    marketplace_signals = sum(count_includes(text, signal) for signal in (\"ebay\", \"buy it now\", \"auction\", \"seller\", \"item number\", \"shop by category\"))
    saas_paths = sum(count_includes(path_text, pattern) for pattern in (\"/pricing\", \"/features\", \"/use-cases\", \"/solutions\", \"/login\", \"/signup\", \"/docs\", \"/api\"))
    adjusted_scores = []
    for key, score in scores:
        if key == \"ecommerce_specialty_retail\":
            if ecommerce_paths < 2 and marketplace_signals < 2:
                score = min(score, 1.0)
            else:
                score += min(60, ecommerce_paths * 4 + marketplace_signals * 8)
        if key == \"saas_app_membership\":
            if saas_paths < 2:
                score = min(score, 1.0)
            else:
                score += 12
        adjusted_scores.append((key, score))''')"""
text = text[:start] + review_replacement + text[end:]

budget_injected = '''    budget = SCAN_BUDGETS.get(str(scan_mode or "advanced").lower(), SCAN_BUDGETS["advanced"])
    scan_started_at = time.monotonic()
    deadline = scan_started_at + budget["timeout"]'''
budget_compatible = '''    budget = SCAN_BUDGETS.get(str(scan_mode or "advanced").lower(), SCAN_BUDGETS["advanced"])
    fetch_timeout = float(budget.get("fetch_timeout", min(10, max(3, budget["timeout"] / 5))))
    max_sitemap_fetches = int(budget.get("max_sitemap_fetches", 10))
    scan_started_at = time.monotonic()
    deadline = scan_started_at + budget["timeout"]'''
if text.count(budget_injected) != 1:
    raise RuntimeError(f'Expected one injected budget block, found {text.count(budget_injected)}')
text = text.replace(budget_injected, budget_compatible, 1)

for old, new in (
    ('        timeout=budget["fetch_timeout"],', '        timeout=fetch_timeout,'),
    ('            max_fetches=budget["max_sitemap_fetches"],', '            max_fetches=max_sitemap_fetches,'),
):
    if text.count(old) != 1:
        raise RuntimeError(f'Expected one compatibility marker {old!r}, found {text.count(old)}')
    text = text.replace(old, new, 1)

path.write_text(text, encoding='utf-8')
