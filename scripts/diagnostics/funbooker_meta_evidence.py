from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

SCANNER_UA = "Mozilla/5.0 (compatible; FixListPythonScanner/1.0)"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)
CHALLENGE_MARKERS = (
    "just a moment", "cf-chl-", "cloudflare", "datadome", "perimeterx",
    "captcha", "access denied", "checking your browser",
)
META_RE = re.compile(r"<meta\b[^>]*>", re.I | re.S)
HEAD_RE = re.compile(r"<head\b[^>]*>.*?</head\s*>", re.I | re.S)
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
NOSCRIPT_RE = re.compile(r"<noscript\b[^>]*>.*?</noscript\s*>", re.I | re.S)
TEMPLATE_RE = re.compile(r"<template\b[^>]*>.*?</template\s*>", re.I | re.S)
DESC_FRAGMENT_RE = re.compile(r"<meta\b[^>]{0,1200}\bname\s*=\s*(['\"]?)description\1", re.I | re.S)


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def slug(url: str) -> str:
    path = urlparse(url).path.strip("/").replace("/", "__") or "root"
    path = re.sub(r"[^a-zA-Z0-9_.-]+", "-", path)[:130]
    return f"{path}-{hashlib.sha1(url.encode()).hexdigest()[:8]}"


def spans(pattern: re.Pattern[str], text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in pattern.finditer(text)]


def in_spans(offset: int, values: list[tuple[int, int]]) -> bool:
    return any(start <= offset < end for start, end in values)


def parse_meta(raw_tag: str) -> dict[str, Any]:
    try:
        tag = BeautifulSoup(raw_tag, "html.parser").find("meta")
        attrs = {str(k).lower(): v for k, v in (tag.attrs if tag else {}).items()}
        name = attrs.get("name", "")
        content = attrs.get("content", "")
        if isinstance(name, list):
            name = " ".join(map(str, name))
        if isinstance(content, list):
            content = " ".join(map(str, content))
        return {
            "parse_ok": bool(tag), "attrs": attrs, "name": str(name or ""),
            "content_present": "content" in attrs, "content_raw": str(content or ""),
            "content_decoded": html.unescape(str(content or "")), "raw_tag": raw_tag,
        }
    except Exception as exc:
        return {
            "parse_ok": False, "parse_error": type(exc).__name__, "attrs": {},
            "name": "", "content_present": False, "content_raw": "", "raw_tag": raw_tag,
        }


def inspect_meta(text: str) -> dict[str, Any]:
    head = HEAD_RE.search(text)
    head_bounds = (head.start(), head.end()) if head else (-1, -1)
    excluded = spans(COMMENT_RE, text) + spans(NOSCRIPT_RE, text) + spans(TEMPLATE_RE, text)
    elements: list[dict[str, Any]] = []
    og = twitter = False
    for match in META_RE.finditer(text):
        item = parse_meta(match.group(0))
        name = item["name"].strip().lower()
        prop = item["attrs"].get("property", "")
        if isinstance(prop, list):
            prop = " ".join(map(str, prop))
        prop = str(prop or "").strip().lower()
        og = og or prop == "og:description"
        twitter = twitter or name == "twitter:description" or prop == "twitter:description"
        if name != "description":
            continue
        item.update({
            "start_offset": match.start(), "end_offset": match.end(),
            "inside_head": bool(head and head_bounds[0] <= match.start() < head_bounds[1]),
            "in_inert_container": in_spans(match.start(), excluded),
        })
        item["active"] = not item["in_inert_container"]
        elements.append(item)

    active = [e for e in elements if e["active"]]
    in_head = [e for e in active if e["inside_head"]]
    resolved = in_head[0] if in_head else (active[0] if active else None)
    malformed_fragment = any(
        not any(e["start_offset"] == m.start() for e in elements)
        for m in DESC_FRAGMENT_RE.finditer(text)
    )

    if resolved and not resolved["inside_head"]:
        state = "head_parse_boundary"
    elif resolved and (not resolved["parse_ok"] or not resolved["content_present"]):
        state = "malformed"
    elif resolved and not resolved.get("content_decoded", "").strip():
        state = "present_empty"
    elif resolved:
        state = "present_valid"
    elif malformed_fragment or any(not e["content_present"] for e in elements):
        state = "malformed"
    else:
        state = "missing"

    value = str((resolved or {}).get("content_decoded") or "")
    return {
        "existence_state": state, "head_found": bool(head),
        "head_start_offset": head_bounds[0], "head_end_offset": head_bounds[1],
        "element_count": len(active), "duplicate": len(active) > 1,
        "all_standard_elements": elements, "resolved_element": resolved,
        "resolved_content": value, "resolved_content_length": len(value.strip()),
        "quality_state": "not_evaluated", "og_description_present": og,
        "twitter_description_present": twitter,
        "malformed_fragment_detected": malformed_fragment,
    }


def access_gate(record: dict[str, Any], text: str) -> None:
    meta = record["meta_description_evidence"]
    lower = text.lower()
    challenge = [marker for marker in CHALLENGE_MARKERS if marker in lower]
    incomplete = []
    if "<head" in lower and "</head" not in lower:
        incomplete.append("head_not_closed")
    if "<html" in lower and "</html" not in lower:
        incomplete.append("html_not_closed")
    meta.update({"challenge_markers": challenge, "incomplete_reasons": incomplete})
    if record["fetch_error"]:
        meta["existence_state"] = "access_inconclusive"
        meta["exclusion_reason"] = record["fetch_error"]
    elif record["status_code"] != 200:
        meta["existence_state"] = "access_inconclusive"
        meta["exclusion_reason"] = f"http_status:{record['status_code']}"
    elif "html" not in record["content_type"].lower():
        meta["existence_state"] = "access_inconclusive"
        meta["exclusion_reason"] = f"non_html:{record['content_type']}"
    elif challenge:
        meta["existence_state"] = "access_inconclusive"
        meta["exclusion_reason"] = "challenge_markers"
    elif incomplete:
        meta["existence_state"] = "raw_html_incomplete"
        meta["exclusion_reason"] = ",".join(incomplete)
    else:
        meta["exclusion_reason"] = ""


def raw_fetch(url: str, mode: str, ua: str) -> tuple[dict[str, Any], str]:
    started = time.monotonic()
    try:
        with httpx.Client(
            follow_redirects=True, timeout=httpx.Timeout(30.0, connect=15.0),
            headers={
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.7", "Cache-Control": "no-cache",
            },
        ) as client:
            response = client.get(url)
        text = response.text
        soup = BeautifulSoup(text, "html.parser")
        record = {
            "mode": mode, "requested_url": url, "final_url": str(response.url),
            "redirect_history": [
                {"url": str(r.url), "status_code": r.status_code, "location": r.headers.get("location", "")}
                for r in response.history
            ],
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", ""),
            "response_size_bytes": len(response.content),
            "safe_headers": {
                k: response.headers.get(k, "")
                for k in ("content-type", "content-length", "content-encoding", "server", "cache-control")
                if response.headers.get(k)
            },
            "user_agent": ua, "title": soup.title.string if soup.title else "",
            "fetch_error": "", "elapsed_ms": round((time.monotonic() - started) * 1000),
            "meta_description_evidence": inspect_meta(text),
        }
    except Exception as exc:
        text = ""
        record = {
            "mode": mode, "requested_url": url, "final_url": "", "redirect_history": [],
            "status_code": 0, "content_type": "", "response_size_bytes": 0,
            "safe_headers": {}, "user_agent": ua, "title": "",
            "fetch_error": f"{type(exc).__name__}:{exc}",
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "meta_description_evidence": inspect_meta(""),
        }
    access_gate(record, text)
    return record, text


def rendered_fetch(browser: Any, url: str) -> tuple[dict[str, Any], str]:
    started = time.monotonic()
    context = browser.new_context(user_agent=BROWSER_UA, locale="fr-FR", viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    response = None
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        try:
            page.wait_for_load_state("networkidle", timeout=10_000)
            wait_state = "networkidle"
        except PlaywrightTimeoutError:
            page.wait_for_timeout(2_000)
            wait_state = "domcontentloaded_plus_2s"
        body = page.content()
        elements = page.evaluate("""() => [...document.querySelectorAll('meta[name]')]
            .filter(e => (e.getAttribute('name') || '').toLowerCase() === 'description')
            .map((e, i) => ({index:i, outerHTML:e.outerHTML, contentPresent:e.hasAttribute('content'), content:e.getAttribute('content') || ''}))""")
        if not elements:
            state_value = "missing"
        elif not elements[0]["contentPresent"]:
            state_value = "malformed"
        elif not elements[0]["content"].strip():
            state_value = "present_empty"
        else:
            state_value = "present_valid"
        status = response.status if response else 0
        content_type = response.headers.get("content-type", "") if response else ""
        challenge = [m for m in CHALLENGE_MARKERS if m in body.lower()]
        if status != 200 or "html" not in content_type.lower() or challenge:
            state_value = "access_inconclusive"
        record = {
            "mode": "rendered", "requested_url": url, "final_url": page.url,
            "status_code": status, "content_type": content_type,
            "response_size_bytes": len(body.encode()), "user_agent": BROWSER_UA,
            "title": page.title(), "wait_state": wait_state, "fetch_error": "",
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "challenge_markers": challenge,
            "meta_description_evidence": {
                "existence_state": state_value, "element_count": len(elements),
                "duplicate": len(elements) > 1, "elements": elements,
                "resolved_content": elements[0]["content"] if elements else "",
                "resolved_content_length": len(elements[0]["content"].strip()) if elements else 0,
            },
        }
        return record, body
    except Exception as exc:
        return {
            "mode": "rendered", "requested_url": url, "final_url": page.url,
            "status_code": response.status if response else 0, "content_type": "",
            "response_size_bytes": 0, "user_agent": BROWSER_UA, "title": "",
            "wait_state": "", "fetch_error": f"{type(exc).__name__}:{exc}",
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "challenge_markers": [],
            "meta_description_evidence": {"existence_state": "access_inconclusive", "element_count": 0, "duplicate": False, "elements": []},
        }, ""
    finally:
        context.close()


def state(record: dict[str, Any]) -> str:
    return str(record["meta_description_evidence"].get("existence_state", "unknown"))


def interpretation(item: dict[str, Any], modes: dict[str, Any]) -> str:
    scanner, browser, rendered = map(state, (modes["scanner"], modes["browser"], modes["rendered"]))
    if scanner in {"access_inconclusive", "raw_html_incomplete"} or browser in {"access_inconclusive", "raw_html_incomplete"}:
        return "access_or_incomplete_response"
    if scanner != browser:
        return "user_agent_specific_response"
    if scanner in {"missing", "present_empty", "malformed", "head_parse_boundary"} and rendered == "present_valid":
        return "rendered_dom_adds_or_repairs_description"
    if item.get("fixlist_state") == "missing" and scanner == "present_valid":
        return "current_raw_evidence_disagrees_with_saved_fixlist"
    if scanner == browser == rendered == "missing":
        return "genuine_current_missing_description"
    if scanner == browser == rendered == "present_valid":
        return "current_description_present"
    if scanner in {"present_empty", "malformed", "head_parse_boundary"}:
        return "non_missing_metadata_state"
    return "mixed_or_unresolved"


def report(manifest: list[dict[str, Any]], records: list[dict[str, Any]]) -> str:
    lines = [
        "# Funbooker meta-description evidence gate", "",
        "No production behavior was changed. Current live HTML was compared under the production scanner UA, a browser UA, and rendered Chromium.", "",
        "| Control | URL | Saved FixList | SiteGuru | Scanner raw | Browser raw | Rendered | Interpretation |",
        "|---|---|---|---|---|---|---|---|",
    ]
    esc = lambda v: str(v or "").replace("|", "\\|").replace("\n", " ")
    for item, record in zip(manifest, records):
        modes = record["modes"]
        values = (
            item.get("control_role"), item["url"], item.get("fixlist_state"), item.get("siteguru_state"),
            state(modes["scanner"]), state(modes["browser"]), state(modes["rendered"]), record["interpretation"],
        )
        lines.append("| " + " | ".join(esc(v) for v in values) + " |")
    lines += ["", "## Limits", "", "The saved FixList scan, SiteGuru audit, and this live diagnostic occurred on different dates. A changed page can therefore appear as a crawl-date/content difference. Raw and rendered evidence is preserved in the artifact for independent review.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if len(manifest) != 7 or len({item["url"] for item in manifest}) != 7:
        raise SystemExit("manifest must contain seven unique URLs")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    dump_json(output / "manifest.json", manifest)
    records: list[dict[str, Any]] = []
    logs: list[str] = []
    with sync_playwright() as p:
        browser_engine = p.chromium.launch(headless=True)
        try:
            for index, item in enumerate(manifest, 1):
                url, file_slug = item["url"], slug(item["url"])
                modes: dict[str, Any] = {}
                for mode, ua in (("scanner", SCANNER_UA), ("browser", BROWSER_UA)):
                    record, body = raw_fetch(url, mode, ua)
                    modes[mode] = record
                    path = output / "raw" / f"{file_slug}-{mode}.html"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(body, encoding="utf-8")
                    head = HEAD_RE.search(body)
                    head_path = output / "raw-head" / f"{file_slug}-{mode}-head.html"
                    head_path.parent.mkdir(parents=True, exist_ok=True)
                    head_path.write_text(head.group(0) if head else "", encoding="utf-8")
                modes["rendered"], rendered = rendered_fetch(browser_engine, url)
                rendered_path = output / "rendered" / f"{file_slug}.html"
                rendered_path.parent.mkdir(parents=True, exist_ok=True)
                rendered_path.write_text(rendered, encoding="utf-8")
                combined = {"manifest": item, "modes": modes, "interpretation": interpretation(item, modes)}
                dump_json(output / "records" / f"{file_slug}.json", combined)
                records.append(combined)
                logs.append(f"[{index}/7] {url} scanner={state(modes['scanner'])} browser={state(modes['browser'])} rendered={state(modes['rendered'])} interpretation={combined['interpretation']}")
        finally:
            browser_engine.close()

    summary = {
        "diagnostic_version": "funbooker_meta_evidence_v1", "url_count": 7,
        "records": [
            {
                "id": record["manifest"]["id"], "url": record["manifest"]["url"],
                "control_role": record["manifest"]["control_role"],
                "fixlist_state": record["manifest"].get("fixlist_state"),
                "siteguru_state": record["manifest"].get("siteguru_state"),
                "scanner_state": state(record["modes"]["scanner"]),
                "browser_state": state(record["modes"]["browser"]),
                "rendered_state": state(record["modes"]["rendered"]),
                "interpretation": record["interpretation"],
            }
            for record in records
        ],
    }
    dump_json(output / "summary.json", summary)
    (output / "report.md").write_text(report(manifest, records), encoding="utf-8")
    (output / "test.log").write_text("\n".join(logs) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
