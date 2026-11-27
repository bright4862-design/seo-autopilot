"""Read the Vite entry and stylesheet referenced by the published pilot page."""

from html.parser import HTMLParser
from pathlib import Path
import re
import sys


class AssetParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.modules = []
        self.stylesheets = []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "script" and attrs.get("type") == "module" and "src" in attrs:
            self.modules.append(attrs["src"])
        if tag == "link" and "stylesheet" in (attrs.get("rel") or "").lower().split():
            self.stylesheets.append(attrs.get("href"))


def entry_assets(html):
    parsed = AssetParser()
    parsed.feed(html)
    parsed.close()
    assets = []
    for urls, extension in [(parsed.modules, "js"), (parsed.stylesheets, "css")]:
        pattern = rf"/assets/index-[A-Za-z0-9_-]+\.{extension}"
        if len(urls) != 1 or not re.fullmatch(pattern, urls[0] or ""):
            raise ValueError(f"expected one same-origin Vite {extension} entry")
        assets.append(urls[0])
    return assets


if __name__ == "__main__":
    try:
        print(*entry_assets(Path(sys.argv[1]).read_text(encoding="utf-8")))
    except (ValueError, OSError) as error:
        sys.exit(f"Published pilot asset verification failed: {error}")
