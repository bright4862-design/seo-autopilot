from pathlib import Path

path = Path(".github/scripts/patch_scan_storage.py")
text = path.read_text(encoding="utf-8")
old = '''text = sub1(text, r'function getTemplateGroupTitle\\(fix = \\{\\}, family = "template"\\) \\{.*?\\}', group_title, "group title", re.S)'''
new = '''text = sub1(text, r'function getTemplateGroupTitle\\(fix = \\{\\}, family = "template"\\) \\{.*?(?=\\nfunction getTemplateGroupExplanation)', group_title + "\\n", "group title", re.S)'''
if old not in text:
    raise SystemExit("group-title replacement line not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
