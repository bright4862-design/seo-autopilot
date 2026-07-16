from __future__ import annotations

import runpy
from pathlib import Path

script = Path(__file__).with_name("apply_focused_acceptance_followup_v8.py")
text = script.read_text(encoding="utf-8")
old = '''review = replace_all_checked(
    review,
    '    "/platform", "/apps", "/download",\n',
    '    "/platform", "/apps", "/download", "/payments", "/billing",\n'
    '    "/connect", "/radar", "/terminal", "/issuing", "/treasury",\n'
    '    "/tax", "/identity", "/atlas", "/financial-connections",\n',
    2,
    "SaaS structural product routes",
)
'''
new = '''review = replace_once(
    review,
    '    "/platform", "/apps", "/download",\n',
    '    "/platform", "/apps", "/download", "/payments", "/billing",\n'
    '    "/connect", "/radar", "/terminal", "/issuing", "/treasury",\n'
    '    "/tax", "/identity", "/atlas", "/financial-connections",\n',
    "SaaS structural product routes",
)
review = replace_once(
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
if text.count(old) != 1:
    raise RuntimeError(f"patch-anchor wrapper expected one target, found {text.count(old)}")
script.write_text(text.replace(old, new, 1), encoding="utf-8")
runpy.run_path(str(script), run_name="__main__")
