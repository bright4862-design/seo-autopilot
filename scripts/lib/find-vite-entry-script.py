#!/usr/bin/env python3
"""Select the sole Vite module entry and refuse unrelated executable scripts.

This is a browser-entry check, not a signature of Base44's inline analytics.
"""
from html.parser import HTMLParser
from pathlib import Path
import re
import sys

ENTRY = re.compile(r"/assets/index-[A-Za-z0-9_-]+\.js\Z")
INERT_INLINE_TYPES = frozenset(("application/ld+json", "application/json"))


class EntryParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.module_scripts = []
        self.ambiguous_attributes = False
        self.unattested_script = False
        self.inline_modules = 0
        self.inert_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("template", "noscript"):
            self.inert_depth += 1
        if self.inert_depth or tag != "script":
            return
        keys = [key for key, _ in attrs]
        if len(set(keys)) != len(keys):
            self.ambiguous_attributes = True
            return
        attr = dict(attrs)
        kind = (attr.get("type") or "").strip().lower()
        if kind == "module":
            if "src" in attr:
                self.module_scripts.append(attr["src"])
            else:
                # Base44 injects one inline page-view analytics module in real
                # Vite output. It is separate, not source-SHA attested here.
                self.inline_modules += 1
        elif "src" in attr or kind not in INERT_INLINE_TYPES:
            # Refuse external classic scripts (even before/after the Vite
            # entry), inline classic JS and import maps. Import maps are not
            # executable alone but can change module resolution.
            self.unattested_script = True

    def handle_endtag(self, tag):
        if tag in ("template", "noscript") and self.inert_depth:
            self.inert_depth -= 1


if len(sys.argv) != 2:
    sys.exit("expected one HTML file path")
parser = EntryParser()
parser.feed(Path(sys.argv[1]).read_text(encoding="utf-8"))
if parser.ambiguous_attributes or len(parser.module_scripts) != 1:
    sys.exit("SITE_ENTRY_AMBIGUOUS_OR_MISSING: expected one external module script")
if parser.unattested_script or parser.inline_modules > 1:
    sys.exit("SITE_UNATTESTED_SCRIPT: unrelated executable script or unsupported inline module")
entry = parser.module_scripts[0]
if not isinstance(entry, str) or not ENTRY.fullmatch(entry):
    sys.exit("SITE_ENTRY_INVALID: expected /assets/index-<hash>.js")
print(entry)
