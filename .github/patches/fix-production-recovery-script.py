from pathlib import Path

path = Path('.github/patches/apply-production-release-recovery.py')
text = path.read_text(encoding='utf-8')
start_marker = 'replace_once("scanner-api/app/scanner.py", \'\'\'            "scanner_version": VERSION,'
end_marker = '            "scan_deadline_reached": deadline_reached,\'\'\')'
start = text.find(start_marker)
end = text.find(end_marker, start)
if start < 0 or end < 0:
    raise RuntimeError(f'Could not find scanner diagnostics transformer block: start={start}, end={end}')
end += len(end_marker)
replacement = """replace_once(\"scanner-api/app/scanner.py\", '''        \"technical_audit_summary\": {
            \"scanner_version\": VERSION,
            \"pages_crawled\": len(pages),''', '''        \"technical_audit_summary\": {
            \"scanner_version\": VERSION,
            \"scanner_elapsed_ms\": elapsed_ms,
            \"scanner_total_budget_seconds\": budget[\"timeout\"],
            \"scan_deadline_reached\": deadline_reached,
            \"pages_crawled\": len(pages),''')"""
path.write_text(text[:start] + replacement + text[end:], encoding='utf-8')
