from pathlib import Path

for name in [
    "patch_backend_correctness.py",
    "patch_scan_storage.py",
    "patch_fixlist_zero_state.py",
]:
    path = Path(".github/scripts") / name
    text = path.read_text(encoding="utf-8")
    old = "re.subn(pattern, replacement, text, count=1, flags=flags)"
    new = "re.subn(pattern, lambda _match: replacement, text, count=1, flags=flags)"
    if old in text:
        text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
