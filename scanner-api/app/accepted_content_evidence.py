"""Bounded observations from an independent, sanitized accepted-HTML view.

No fetches, rendered-visibility claims, or changes to the existing GEO adapter.
Image counts describe absent attributes separately from semantic applicability.
Stage-2 main-content and page-weight fields are derived only from the same
accepted HTML and remain explicitly unverified when that evidence is unusable.
"""
from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from .stage2_coverage_evidence import MAIN_TEXT_EVIDENCE_VERSION, PAGE_WEIGHT_VERSION


IMAGE_APPLICABILITY_VERSION = "image_alt_applicability_v1"
VISIBLE_TEMPLATE_VERSION = "visible_template_evidence_v1"
MAX_HTML = 2_000_000
MAX_IMAGE_SAMPLES = 40
MAX_TEMPLATE_SAMPLES = 4
MAX_MAIN_TEXT_CHARS = 120_000
EXCLUDED_TAGS = {"script", "style", "template", "noscript", "code", "pre"}
BLOCK_TAGS = {"title", "h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "dt", "dd", "td", "th", "div", "section", "article", "main", "body", "figcaption", "label", "button", "a"}
HIDDEN_STYLE = re.compile(r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*(?:hidden|collapse)|content-visibility\s*:\s*hidden)\s*(?:!important\s*)?(?:;|$)", re.I)
TEMPLATE_TOKEN = re.compile(
    r"\{\{[^{}\n]{1,180}\}\}|\{%[^%\n]{1,180}%\}|"
    r"#[A-Z][A-Z0-9_-]{1,60}#|#(?:location|city|state|region|market|area)#|"
    r"%%[A-Za-z_][\w .-]{0,100}%%|\$\{[^{}\n]{1,180}\}|"
    r"\{var[-_](?:location|city|state|region|market|area)\}",
)
RUNTIME_VALUE = re.compile(r"\[object Object\]|\bundefined\b|\bNaN\b")
PLACEHOLDER_COPY = re.compile(r"\blorem\s+ipsum\b", re.I)
EXPLANATORY = re.compile(
    r"\b(?:javascript|typescript|programming|source code|template syntax|"
    r"code example|example of|tutorial|undefined behavior|filler text|placeholder text)\b", re.I,
)
RUNTIME_LABEL = re.compile(r"(?:\b(?:price|total|cost|amount|quantity|count|rating|name|product|address|welcome|hello)\b\s*[:=,]?\s*[$€£]?\s*)$", re.I)
SHELL_COPY = re.compile(r"\b(?:coming soon|stay tuned|under construction|check back soon|work in progress)\b", re.I)
SUBJECT_TYPES = re.compile(r"^https?://schema\.org/(?:Product|Person|Organization|LocalBusiness|Article|NewsArticle|BlogPosting|Place|Event)$")


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _placement(node: Any) -> str:
    if node.name == "title" or node.find_parent("title"):
        return "title"
    if node.name == "meta":
        return "meta"
    if node.name == "h1" or node.find_parent("h1"):
        return "h1"
    if node.name in {"main", "article"} or str(node.get("role", "")).lower() == "main" or node.find_parent(["main", "article"]) or node.find_parent(attrs={"role": "main"}):
        return "main"
    if node.find_parent(["header", "nav", "footer", "aside"]):
        return "chrome"
    return "body"


def _node_excluded_by_sanitize(node: Any) -> bool:
    """Return whether this node or an ancestor is removed from accepted evidence."""
    current = node
    while current is not None and getattr(current, "name", None):
        if (current.name in EXCLUDED_TAGS or current.has_attr("hidden")
                or str(current.get("aria-hidden", "")).strip().lower() == "true"
                or HIDDEN_STYLE.search(str(current.get("style", "")))):
            return True
        current = current.parent
    return False


def _sanitize(soup: BeautifulSoup) -> None:
    # Reverse document order prevents a removed parent's children from being
    # accessed after BeautifulSoup clears their attributes during decompose().
    for node in reversed(soup.find_all(True)):
        if (node.name in EXCLUDED_TAGS or node.has_attr("hidden")
                or str(node.get("aria-hidden", "")).strip().lower() == "true"
                or HIDDEN_STYLE.search(str(node.get("style", "")))):
            node.decompose()


def _inline_bytes(soup: BeautifulSoup) -> tuple[int, int]:
    script_bytes = 0
    style_bytes = 0
    for script in soup.find_all("script"):
        if script.get("src"):
            continue
        script_bytes += len(str(script.string or script.get_text(" ") or "").encode("utf-8"))
    for style in soup.find_all("style"):
        style_bytes += len(str(style.string or style.get_text(" ") or "").encode("utf-8"))
    return script_bytes, style_bytes


def _main_text_evidence(soup: BeautifulSoup) -> dict[str, Any]:
    # Work on a clone so chrome removal for B10 cannot change any existing
    # template/image/location evidence extracted from the accepted view.
    clone = BeautifulSoup(str(soup), "lxml")
    root = clone.find("main") or clone.find(attrs={"role": "main"}) or clone.find("article")
    source = "main_landmark"
    if root is None:
        root = clone.body or clone
        source = "body_without_common_chrome"
        for node in reversed(root.find_all(["header", "nav", "footer", "aside"])):
            node.decompose()
    text = _text(root.get_text(" ")) if root else ""
    truncated = len(text) > MAX_MAIN_TEXT_CHARS
    bounded = text[:MAX_MAIN_TEXT_CHARS]
    verified = bool(bounded) and not truncated
    return {
        "main_text_evidence_version": MAIN_TEXT_EVIDENCE_VERSION,
        "main_text_verified": verified,
        "main_text_reason": (
            "accepted_sanitized_main_text"
            if verified
            else ("main_text_too_large" if truncated else "main_text_empty")
        ),
        "main_text_source": source if root else None,
        "main_text": bounded,
        "main_text_char_count": len(text),
        "main_text_truncated": truncated,
    }


def _accessible_name(node: Any, soup: BeautifulSoup) -> bool:
    if _text(node.get("aria-label")) or _text(node.get("title")):
        return True
    for label_id in str(node.get("aria-labelledby", "")).split():
        label = soup.find(id=label_id)
        if label and _text(label.get_text(" ")):
            return True
    return bool(_text(node.get_text(" ")) or any(_text(img.get("alt")) or _accessible_name(img, soup) for img in node.find_all("img")))


def _image_applicability(img: Any, soup: BeautifulSoup) -> tuple[str, str]:
    control = img.find_parent(lambda node: node.name == "button" or (node.name == "a" and node.has_attr("href")) or str(node.get("role", "")).lower() in {"button", "link"})
    if control and not _accessible_name(control, soup):
        return "material", "unnamed_image_control"
    if str(img.get("role", "")).strip().lower() in {"none", "presentation"}:
        return "excluded", "explicit_presentation_role"
    figure = img.find_parent("figure")
    caption = figure.find("figcaption") if figure else None
    if caption and _text(caption.get_text(" ")):
        return "material", "visible_caption"
    properties = str(img.get("itemprop", "")).split()
    subject = img.find_parent(attrs={"itemscope": True, "itemtype": SUBJECT_TYPES})
    if "image" in properties and subject:
        return "material", "explicit_subject_image"
    return "uncertain", "insufficient_semantic_evidence"


def _fragments(soup: BeautifulSoup) -> list[tuple[str, str]]:
    fragments: list[tuple[str, str]] = []
    if soup.title:
        fragments.append(("title", _text(soup.title.get_text(" "))))
    for meta in soup.find_all("meta"):
        name = str(meta.get("name") or meta.get("property") or "").lower()
        if name in {"description", "og:title", "og:description", "twitter:title", "twitter:description"}:
            fragments.append(("meta", _text(meta.get("content"))))
    # Group adjacent inline text under its nearest block without rescanning
    # ancestor text. Each visible occurrence is counted exactly once.
    grouped: dict[int, tuple[Any, list[str]]] = {}
    root = soup.body or soup
    for value in root.find_all(string=True):
        if value.__class__.__name__ in {"Comment", "Doctype", "ProcessingInstruction"}:
            continue
        node = value.parent
        if not node or node.name in {"title", "head"} or node.find_parent("title"):
            continue
        block = node if node.name in BLOCK_TAGS else node.find_parent(list(BLOCK_TAGS)) or root
        key = id(block)
        if key not in grouped:
            grouped[key] = (block, [])
        grouped[key][1].append(str(value))
    fragments.extend((_placement(node), _text(" ".join(parts))) for node, parts in grouped.values())
    return [(placement, text) for placement, text in fragments if text]


def _snippet(text: str, start: int, end: int) -> str:
    left = max(0, start - 70)
    right = min(len(text), max(end + 70, left + 180), left + 258)
    return (("…" if left else "") + text[left:right] + ("…" if right < len(text) else ""))[:260]


def _template_evidence(soup: BeautifulSoup) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "version": VISIBLE_TEMPLATE_VERSION, "accepted": True, "state": "pass", "reason": "accepted_html",
        "issue_types": [], "issue_count": 0, "samples": [], "samples_truncated": False,
    }

    def record(kind: str, placement: str, snippet: str) -> None:
        evidence["issue_count"] += 1
        if kind not in evidence["issue_types"]:
            evidence["issue_types"].append(kind)
        if len(evidence["samples"]) < MAX_TEMPLATE_SAMPLES:
            evidence["samples"].append({"kind": kind, "placement": placement, "snippet": snippet[:260]})

    for placement, text in _fragments(soup):
        if EXPLANATORY.search(text):
            continue
        for kind, pattern in (("unresolved_template", TEMPLATE_TOKEN), ("runtime_value", RUNTIME_VALUE), ("placeholder_copy", PLACEHOLDER_COPY)):
            for match in pattern.finditer(text):
                if kind == "runtime_value" and match[0] != "[object Object]":
                    standalone = text.strip(" .:;!$€£") == match[0]
                    if not standalone and not RUNTIME_LABEL.fullmatch(text[:match.start()]):
                        continue
                record(kind, placement, _snippet(text, match.start(), match.end()))

    main = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.find("article") or soup.body
    if main and not main.find(["img", "video", "audio", "iframe", "svg", "canvas", "form", "input", "textarea", "select"]):
        content = _text(main.get_text(" "))
        if not content:
            record("empty_shell", _placement(main), "No visible text, media or form in the content area.")
        elif re.search(r"\bcoming soon\b", content, re.I) and not re.sub(r"[\W_]+", "", SHELL_COPY.sub("", content)):
            record("coming_soon_shell", _placement(main), content)
    if evidence["issue_count"]:
        evidence["state"] = "fail"
    evidence["samples_truncated"] = evidence["issue_count"] > len(evidence["samples"])
    return evidence


def extract_accepted_content_evidence(html: str, evidence_class: str) -> dict[str, Any]:
    """Return bounded accepted-content records plus transient sanitized inputs."""
    counts = ("image_count", "absent_alt_count", "empty_alt_count", "material_missing_alt_count", "uncertain_missing_alt_count", "excluded_missing_alt_count", "observation_count")
    reason = "html_limit_exceeded" if len(html) > MAX_HTML else evidence_class
    images: dict[str, Any] = {
        "version": IMAGE_APPLICABILITY_VERSION, "accepted": False, "state": "not_verified", "reason": reason,
        **dict.fromkeys(counts), "observations": [], "samples_truncated": False,
    }
    templates = {"version": VISIBLE_TEMPLATE_VERSION, "accepted": False, "state": "not_verified", "reason": reason,
                 "issue_types": [], "issue_count": None, "samples": [], "samples_truncated": False}
    location = {"title": "", "h1": "", "visible_text": ""}
    result = {
        "image_alt_applicability": images,
        "visible_template_evidence": templates,
        "location_context": location,
        "main_text_evidence_version": MAIN_TEXT_EVIDENCE_VERSION,
        "main_text_verified": False,
        "main_text_reason": reason,
        "main_text_source": None,
        "main_text": "",
        "main_text_char_count": None,
        "main_text_truncated": False,
        "page_weight_evidence_version": PAGE_WEIGHT_VERSION,
        "decoded_bytes": None,
        "decoded_bytes_basis": None,
        "inline_script_bytes": None,
        "inline_style_bytes": None,
        "transfer_bytes": None,
        "transfer_bytes_state": "unknown",
    }
    if evidence_class != "usable_html" or len(html) > MAX_HTML:
        return result

    soup = BeautifulSoup(html, "lxml")
    inline_script_bytes, inline_style_bytes = _inline_bytes(soup)
    result.update({
        "decoded_bytes": len((html or "").encode("utf-8")),
        "decoded_bytes_basis": "utf8_of_decoded_html",
        "inline_script_bytes": inline_script_bytes,
        "inline_style_bytes": inline_style_bytes,
    })
    snapshots = []
    for img in soup.find_all("img"):
        alt_state = "absent" if not img.has_attr("alt") else ("empty" if not _text(img.get("alt")) else "present")
        placement = _placement(img)
        if _node_excluded_by_sanitize(img):
            applicability, applicability_reason = "excluded", "hidden_or_example_content"
        else:
            applicability, applicability_reason = _image_applicability(img, soup)
        # Retain only scalar evidence before destructive sanitization. Hidden
        # ancestors are decomposed below, so no later classification may
        # dereference a decomposed BeautifulSoup node.
        snapshots.append((alt_state, placement, applicability, applicability_reason))
    _sanitize(soup)
    images.update(accepted=True, state="pass", reason="accepted_html", **dict.fromkeys(counts, 0))
    images["image_count"] = images["observation_count"] = len(snapshots)
    for ordinal, (alt_state, placement, applicability, applicability_reason) in enumerate(snapshots, start=1):
        if alt_state == "absent":
            images["absent_alt_count"] += 1
            images[f"{applicability}_missing_alt_count"] += 1
        elif alt_state == "empty":
            images["empty_alt_count"] += 1
        if len(images["observations"]) < MAX_IMAGE_SAMPLES:
            images["observations"].append({"ordinal": ordinal, "placement": placement, "alt_state": alt_state, "applicability": applicability, "reason": applicability_reason})
    images["samples_truncated"] = len(snapshots) > MAX_IMAGE_SAMPLES
    if images["material_missing_alt_count"]:
        images["state"] = "fail"
    elif images["uncertain_missing_alt_count"]:
        images["state"] = "not_verified"
    result["visible_template_evidence"] = _template_evidence(soup)
    result.update(_main_text_evidence(soup))
    h1 = soup.find("h1")
    location.update(title=_text(soup.title.get_text(" ")) if soup.title else "", h1=_text(h1.get_text(" ")) if h1 else "", visible_text=_text(soup.get_text(" ")))
    return result
