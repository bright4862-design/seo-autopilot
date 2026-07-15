#!/usr/bin/env python3
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "scanner-api/tests/test_classifier_v3_production_regressions.py"
text = path.read_text(encoding="utf-8")
old = 'classification["classifier_version"].startswith("archetype_classifier_v6")'
new = 'classification["classifier_version"].startswith("archetype_classifier_v7")'
if text.count(old) != 1:
    raise SystemExit(f"expected one legacy classifier-prefix assertion, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
