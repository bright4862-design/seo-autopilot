#!/usr/bin/env python3
"""Update the one version-prefix assertion for classifier v6."""

from pathlib import Path

path = Path(__file__).resolve().parents[1] / "scanner-api/tests/test_classifier_v3_production_regressions.py"
text = path.read_text(encoding="utf-8")
old = 'startswith("archetype_classifier_v5")'
new = 'startswith("archetype_classifier_v6")'
count = text.count(old)
if count != 1:
    raise RuntimeError(f"{path}: expected one v5 prefix assertion, found {count}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
