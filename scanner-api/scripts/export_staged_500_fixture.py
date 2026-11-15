#!/usr/bin/env python3
"""Export the synthetic staged scanner test site as static HTML, sitemap, and robots files."""

import argparse
from html import escape
from pathlib import Path
import re
import shutil


REPO_ROOT = Path(__file__).resolve().parents[2]
HOST_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
HTTPS_ORIGIN = re.compile(rf"https://(?:{HOST_LABEL}\.)+{HOST_LABEL}/?")
SECTIONS = {
    "solutions": "Find a synthetic service guide and a worked example for this fixture topic.",
    "products": "Compare the example product features, reference number, and care notes.",
    "stores": "Read the synthetic branch directory entry and its access information.",
    "insights": "Explore a fixture article with observations about a sample workflow.",
}
PAGES_PER_SECTION = 160


def html_page(url: str, title: str, description: str, links: list[tuple[str, str]]) -> str:
    navigation = "".join(f'<li><a href="{escape(href)}">{escape(label)}</a></li>' for href, label in links)
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
        f'<title>{escape(title)}</title>\n'
        f'<meta name="description" content="{escape(description)}">\n'
        f'<link rel="canonical" href="{escape(url)}">\n'
        f'</head><body><main><h1>{escape(title)}</h1><p>{escape(description)}</p></main>\n'
        f'<nav aria-label="Fixture pages"><ul>{navigation}</ul></nav>\n</body></html>\n'
    )


def fixture_files(origin: str) -> dict[str, str]:
    if not HTTPS_ORIGIN.fullmatch(origin):
        raise ValueError("origin must be an HTTPS origin with a lowercase hostname and no path, port, query, or fragment")
    origin = origin.removesuffix("/")
    links = [(f"/{section}/0.html", section.title()) for section in SECTIONS]
    files = {"index.html": html_page(f"{origin}/", "Staged scanner test site", "A synthetic four-section crawl fixture.", links)}
    urls = []
    for section, description in SECTIONS.items():
        for index in range(PAGES_PER_SECTION):
            path = f"{section}/{index}.html"
            url = f"{origin}/{path}"
            urls.append(url)
            title = f"{section.title()} fixture {index + 1}"
            next_page = (index + 1) % PAGES_PER_SECTION
            files[path] = html_page(url, title, f"{description} This is entry {index + 1} in the {section} section.",
                                   [("/", "Fixture home"), (f"/{section}/{next_page}.html", "Next entry")])
    sitemap = "".join(f"  <url><loc>{url}</loc></url>\n" for url in urls)
    files["sitemap.xml"] = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{sitemap}</urlset>\n')
    files["robots.txt"] = f"User-agent: *\nAllow: /\nSitemap: {origin}/sitemap.xml\n"
    return files


def export_fixture(origin: str, output: Path) -> int:
    if (not output.is_absolute() or output.is_relative_to(REPO_ROOT)
            or not output.parent.is_dir() or output.parent.resolve(strict=True) != output.parent):
        raise ValueError("output must be a new absolute directory outside the checkout, under an existing canonical parent")
    files = fixture_files(origin)
    output.mkdir(mode=0o755)
    try:
        for relative, contents in files.items():
            target = output / relative
            target.parent.mkdir(exist_ok=True)
            with target.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(contents)
    except OSError:
        shutil.rmtree(output)
        raise
    return len(files)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True, help="Final HTTPS site origin, with no path")
    parser.add_argument("--output", required=True, type=Path, help="New absolute output directory outside the checkout")
    args = parser.parse_args()
    try:
        count = export_fixture(args.origin, args.output)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Exported {count} static files to {args.output}")


if __name__ == "__main__":
    main()
