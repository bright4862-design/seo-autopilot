#!/usr/bin/env python3
"""Print the sole executable Vite module entry in a served HTML document.

The release verifier must check the asset actually referenced by the page,
not a filename in an HTML comment, preload hint, or unrelated script.
"""
from html.parser import HTMLParser
from pathlib import Path
import re
import sys

ENTRY = re.compile(r"/assets/index-[A-Za-z0-9_-]+\.js\Z")


class EntryParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.module_scripts = []
        self.ambiguous_attributes = False
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
        if (attr.get("type") or "").strip().lower() == "module":
            self.module_scripts.append(attr.get("src"))

    def handle_endtag(self, tag):
        if tag in ("template", "noscript") and self.inert_depth:
            self.inert_depth -= 1


if len(sys.argv) != 2:
    sys.exit("expected one HTML file path")
parser = EntryParser()
parser.feed(Path(sys.argv[1]).read_text(encoding="utf-8"))
if parser.ambiguous_attributes or len(parser.module_scripts) != 1:
    sys.exit("SITE_ENTRY_AMBIGUOUS_OR_MISSING: expected one external module script")
entry = parser.module_scripts[0]
if not isinstance(entry, str) or not ENTRY.fullmatch(entry):
    sys.exit("SITE_ENTRY_INVALID: expected /assets/index-<hash>.js")
print(entry)
