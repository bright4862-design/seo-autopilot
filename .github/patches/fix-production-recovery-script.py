from pathlib import Path

path = Path('.github/patches/apply-production-release-recovery.py')
text = path.read_text(encoding='utf-8')
old = '''replace_once("scanner-api/app/scanner.py", '''            "scanner_version": VERSION,
            "scanner_profile": "python_screaming_frog_lite_v1",''', '''            "scanner_version": VERSION,
            "scanner_profile": "python_screaming_frog_lite_v1",
            "scanner_elapsed_ms": elapsed_ms,
            "scanner_total_budget_seconds": budget["timeout"],
            "scan_deadline_reached": deadline_reached,''')'''
new = '''replace_once("scanner-api/app/scanner.py", '''        "technical_audit_summary": {
            "scanner_version": VERSION,
            "pages_crawled": len(pages),''', '''        "technical_audit_summary": {
            "scanner_version": VERSION,
            "scanner_elapsed_ms": elapsed_ms,
            "scanner_total_budget_seconds": budget["timeout"],
            "scan_deadline_reached": deadline_reached,
            "pages_crawled": len(pages),''')'''
if text.count(old) != 1:
    raise RuntimeError(f'Expected one scanner marker in transformer, found {text.count(old)}')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
