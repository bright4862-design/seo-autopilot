from __future__ import annotations

import html
import ipaddress
import json
import os
from collections import Counter
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import gradio as gr
import requests
from google.auth import default as google_auth_default
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    project_id: str = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    location: str = os.getenv("VERTEX_LOCATION", "global").strip() or "global"
    model_id: str = os.getenv("GROK_MODEL_ID", "xai/grok-4.20-non-reasoning").strip()
    service_account_json: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    scanner_api_url: str = os.getenv(
        "SCANNER_API_URL",
        "https://seo-autopilot-4545-919035207432.europe-west1.run.app",
    ).strip()
    scanner_api_key: str = os.getenv("SCANNER_API_KEY", "").strip()
    grok_timeout_seconds: int = _env_int("GROK_TIMEOUT_SECONDS", 90)
    scanner_timeout_seconds: int = _env_int("SCANNER_TIMEOUT_SECONDS", 240)

    @property
    def live_grok_enabled(self) -> bool:
        return bool(
            self.live_scan_enabled
            or (self.project_id and self.service_account_json)
        )

    @property
    def live_scan_enabled(self) -> bool:
        return bool(self.scanner_api_url and self.scanner_api_key)


SETTINGS = Settings()

DEMO_SCAN: dict[str, Any] = {
    "source": "demo",
    "website": "https://www.funbooker.com/",
    "status": "complete",
    "score": 68,
    "pages_found": 1200,
    "pages_crawled": 150,
    "pages_retained": 150,
    "grouped_fixes": 9,
    "release_gate_eligible": True,
    "score_is_provisional": False,
    "scanner_backend": "Python scanner",
    "review_backend": "Python review",
    "fallbacks_used": False,
    "priorities": [
        {
            "title": "Update redirected internal links",
            "priority": "High",
            "owner": "Web developer",
            "affected_pages": 18,
            "why": "Direct internal links reduce unnecessary hops and make crawling more efficient.",
        },
        {
            "title": "Add useful meta descriptions",
            "priority": "High",
            "owner": "Content team",
            "affected_pages": 42,
            "why": "Clear descriptions can improve search-result messaging and click-through rate.",
        },
        {
            "title": "Add structured data to conversion templates",
            "priority": "Medium",
            "owner": "Web developer",
            "affected_pages": 2,
            "why": "Structured data gives search engines clearer information about page purpose.",
        },
    ],
    "limitations": [
        "This is a bundled 150-page acceptance-scan example.",
        "AI explanations may prioritize evidence but must not alter crawl facts.",
    ],
}


def _first_present(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return default


def _number(*values: Any, default: int | float | None = None) -> int | float | None:
    for value in values:
        if value is None or value == "":
            continue
        try:
            number = float(value)
            return int(number) if number.is_integer() else number
        except (TypeError, ValueError):
            continue
    return default


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _humanize(value: Any) -> str:
    text = str(value or "").strip().replace("_", " ").replace("-", " ")
    return " ".join(part for part in text.split() if part).capitalize()


def _affected_count(item: dict[str, Any]) -> int:
    for key in (
        "affected_pages",
        "affected_page_count",
        "affected_urls",
        "urls",
        "page_urls",
        "evidence_urls",
        "count",
        "occurrences",
    ):
        value = item.get(key)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            return len(value)
        number = _number(value)
        if number is not None:
            return max(0, int(number))
    return 0


def _infer_owner(item: dict[str, Any], title: str) -> str:
    explicit = _first_present(
        item.get("owner"),
        item.get("fix_owner"),
        item.get("assigned_to"),
        item.get("responsible_party"),
    )
    if explicit:
        return _humanize(explicit)

    haystack = " ".join(
        str(part or "").lower()
        for part in (title, item.get("category"), item.get("type"), item.get("issue_type"))
    )
    developer_terms = (
        "canonical",
        "redirect",
        "schema",
        "structured data",
        "index",
        "crawl",
        "server",
        "javascript",
        "render",
        "status code",
        "robots",
        "sitemap",
    )
    if any(term in haystack for term in developer_terms):
        return "Web developer"
    return "Content / SEO"


def _priority_label(value: Any) -> str:
    text = str(value or "Medium").strip().lower()
    if text in {"critical", "urgent", "highest", "p0"}:
        return "Critical"
    if text in {"high", "important", "p1"}:
        return "High"
    if text in {"low", "minor", "p3"}:
        return "Low"
    return "Medium"


def _normalize_priority(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        title = item.strip()
        if not title:
            return None
        return {
            "title": title,
            "priority": "Medium",
            "owner": _infer_owner({}, title),
            "affected_pages": 0,
            "why": "Confirmed crawl evidence should be reviewed and corrected where appropriate.",
        }
    if not isinstance(item, dict):
        return None

    title = str(
        _first_present(
            item.get("title"),
            item.get("fix_title"),
            item.get("action"),
            item.get("recommendation"),
            item.get("issue"),
            item.get("name"),
            item.get("type"),
            item.get("issue_type"),
            default="",
        )
    ).strip()
    if not title:
        return None

    why = str(
        _first_present(
            item.get("why"),
            item.get("why_it_matters"),
            item.get("description"),
            item.get("impact"),
            item.get("reason"),
            item.get("summary"),
            item.get("details"),
            default="Confirmed crawl evidence supports reviewing this issue.",
        )
    ).strip()

    return {
        "title": _humanize(title) if title == title.lower() else title,
        "priority": _priority_label(
            _first_present(item.get("priority"), item.get("severity"), item.get("impact_level"))
        ),
        "owner": _infer_owner(item, title),
        "affected_pages": _affected_count(item),
        "why": why,
    }


def _candidate_recommendation_lists(review: dict[str, Any]) -> list[list[Any]]:
    health = review.get("website_health_report")
    if not isinstance(health, dict):
        health = {}
    fix_list = review.get("fix_list")
    if not isinstance(fix_list, dict):
        fix_list = {}

    candidates = [
        review.get("recommendations"),
        review.get("grouped_recommendations"),
        review.get("prioritized_recommendations"),
        review.get("priority_actions"),
        review.get("fixes"),
        review.get("fix_items"),
        review.get("issues"),
        health.get("recommendations"),
        health.get("top_priorities"),
        health.get("priority_actions"),
        fix_list.get("items"),
        fix_list.get("fixes"),
    ]
    return [candidate for candidate in candidates if isinstance(candidate, list) and candidate]


def _derive_page_priorities(scan: dict[str, Any]) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for key in ("crawled_pages", "pages", "scanned_pages", "crawl_pages"):
        value = scan.get(key)
        if isinstance(value, list):
            pages = [page for page in value if isinstance(page, dict)]
            if pages:
                break

    counts: Counter[str] = Counter()
    descriptions: dict[str, str] = {}
    for page in pages:
        page_issues: list[Any] = []
        for key in ("issues", "findings", "seo_issues", "errors", "warnings"):
            page_issues.extend(_safe_list(page.get(key)))
        for issue in page_issues:
            if isinstance(issue, str):
                code = issue.strip()
                description = ""
            elif isinstance(issue, dict):
                code = str(
                    _first_present(
                        issue.get("type"),
                        issue.get("issue_type"),
                        issue.get("code"),
                        issue.get("title"),
                        issue.get("name"),
                        default="",
                    )
                ).strip()
                description = str(
                    _first_present(
                        issue.get("description"),
                        issue.get("message"),
                        issue.get("why"),
                        default="",
                    )
                ).strip()
            else:
                continue

            if code:
                counts[code] += 1
                if description:
                    descriptions.setdefault(code, description)

    priorities: list[dict[str, Any]] = []
    for code, count in counts.most_common(5):
        title = _humanize(code)
        priorities.append(
            {
                "title": title,
                "priority": "High" if count >= 10 else "Medium",
                "owner": _infer_owner({"type": code}, title),
                "affected_pages": count,
                "why": descriptions.get(code)
                or "This pattern was confirmed across the crawled page evidence.",
            }
        )
    return priorities


def extract_priorities(scan: dict[str, Any], review: dict[str, Any]) -> list[dict[str, Any]]:
    for candidate_list in _candidate_recommendation_lists(review):
        normalized = [_normalize_priority(item) for item in candidate_list]
        priorities = [item for item in normalized if item]
        if priorities:
            return priorities[:5]
    return _derive_page_priorities(scan)[:5]


def _extract_limitations(scan: dict[str, Any], review: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for source in (
        review.get("limitations"),
        review.get("warnings"),
        scan.get("crawl_warnings"),
        scan.get("limitations"),
    ):
        if isinstance(source, str) and source.strip():
            items.append(source.strip())
        elif isinstance(source, list):
            items.extend(str(item).strip() for item in source if str(item).strip())
    return items[:8]


def normalize_scan_result(
    website_url: str,
    scan: dict[str, Any],
    review: dict[str, Any],
) -> dict[str, Any]:
    health = review.get("website_health_report")
    if not isinstance(health, dict):
        health = {}

    pages: list[Any] = []
    for key in ("crawled_pages", "pages", "scanned_pages", "crawl_pages"):
        value = scan.get(key)
        if isinstance(value, list):
            pages = value
            if value:
                break

    priorities = extract_priorities(scan, review)
    score = _number(
        review.get("health_score"),
        review.get("score"),
        health.get("health_score"),
        health.get("score"),
        health.get("overall_score"),
    )
    status = str(
        _first_present(
            review.get("scan_status"),
            review.get("status"),
            scan.get("scan_status"),
            scan.get("status"),
            default="complete",
        )
    )
    fallback_used = any(
        bool(value)
        for value in (
            scan.get("python_scanner_fallback_used"),
            scan.get("scanner_fallback_used"),
            review.get("python_review_fallback_used"),
            review.get("review_fallback_used"),
        )
    )
    grouped_fixes = int(
        _number(
            review.get("grouped_fix_count"),
            review.get("recommendation_count"),
            review.get("fix_count"),
            health.get("grouped_fix_count"),
            len(priorities),
            default=0,
        )
        or 0
    )

    return {
        "source": "live",
        "website": str(
            _first_present(
                review.get("website_url"),
                scan.get("website_url"),
                scan.get("final_url"),
                website_url,
            )
        ),
        "status": status,
        "score": score,
        "pages_found": int(_number(scan.get("pages_found"), default=0) or 0),
        "pages_crawled": int(_number(scan.get("pages_crawled"), len(pages), default=0) or 0),
        "pages_retained": len(pages) or int(_number(scan.get("pages_crawled"), default=0) or 0),
        "grouped_fixes": grouped_fixes,
        "release_gate_eligible": bool(review.get("release_gate_eligible", False)),
        "score_is_provisional": bool(review.get("score_is_provisional", False)),
        "scanner_backend": str(
            _first_present(
                scan.get("scanner_backend"),
                scan.get("scan_backend"),
                scan.get("scanner_version"),
                default="Python scanner",
            )
        ),
        "review_backend": str(
            _first_present(
                review.get("ai_review_backend"),
                review.get("review_backend"),
                review.get("review_version"),
                default="Python review",
            )
        ),
        "fallbacks_used": fallback_used,
        "priorities": priorities,
        "limitations": _extract_limitations(scan, review),
        "beta_revision_fingerprint": _first_present(
            review.get("beta_revision_fingerprint"),
            scan.get("beta_revision_fingerprint"),
        ),
        "health_score_status": review.get("health_score_status"),
    }


def validate_public_website_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("Enter a website URL.")
    if "://" not in raw:
        raw = f"https://{raw}"

    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Enter a valid http or https website URL.")

    hostname = parsed.hostname.lower().strip(".")
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".localhost"):
        raise ValueError("Localhost addresses cannot be scanned.")

    try:
        ip = ipaddress.ip_address(hostname)
        if not ip.is_global:
            raise ValueError("Private, loopback, and link-local addresses cannot be scanned.")
    except ValueError as exc:
        if "cannot be scanned" in str(exc):
            raise
        # Domain names are allowed; the scanner performs full network validation.

    return raw


def _scanner_base_url() -> str:
    base = SETTINGS.scanner_api_url.rstrip("/")
    for suffix in ("/scan", "/review", "/health", "/revision"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base


def _scanner_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-Scanner-Key": SETTINGS.scanner_api_key,
    }


def _post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(
        f"{_scanner_base_url()}/{path.lstrip('/')}",
        headers=_scanner_headers(),
        json=payload,
        timeout=SETTINGS.scanner_timeout_seconds,
    )
    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Scanner returned an unreadable response ({response.status_code})."
        ) from exc

    if not response.ok:
        detail = body.get("detail") if isinstance(body, dict) else None
        raise RuntimeError(
            f"Scanner request failed ({response.status_code}): {detail or 'Unknown error'}"
        )
    if not isinstance(body, dict):
        raise RuntimeError("Scanner returned an unexpected response shape.")
    if body.get("error") and not body.get("pages_crawled"):
        raise RuntimeError(str(body.get("message") or body.get("error"))[:240])
    return body


def run_scan_pipeline(website_url: str, scan_mode: str = "advanced") -> dict[str, Any]:
    if not SETTINGS.live_scan_enabled:
        raise RuntimeError(
            "Scanning is not connected yet. Add SCANNER_API_KEY as a private Hugging Face Space secret."
        )

    clean_url = validate_public_website_url(website_url)
    scan_result = _post_json(
        "/scan",
        {
            "website_url": clean_url,
            "scan_mode": scan_mode,
            "business_name": "",
            "cms_platform": "",
        },
    )
    review_payload = dict(scan_result)
    review_payload.setdefault("website_url", clean_url)
    review_result = _post_json("/review", review_payload)
    return normalize_scan_result(clean_url, scan_result, review_result)


def _gate_label(scan: dict[str, Any]) -> str:
    if scan.get("release_gate_eligible"):
        return "Authoritative"
    if scan.get("score_is_provisional"):
        return "Provisional"
    return "Limited"


def scan_markdown(scan: dict[str, Any]) -> str:
    gate = _gate_label(scan)
    fallback = "None" if not scan.get("fallbacks_used") else "Used"
    score = scan.get("score")
    score_html = "—" if score is None else html.escape(str(score))
    website = html.escape(str(scan.get("website") or "No scan selected"))
    source = "Live scan" if scan.get("source") == "live" else "Demo scan"

    return f"""
<div class="summary">
  <div class="panel-heading">
    <span class="eyebrow">{source.upper()}</span>
    <span class="status">{html.escape(gate)}</span>
  </div>
  <h2>{website}</h2>
  <div class="score-row">
    <div><span class="score">{score_html}</span><span class="muted">/100</span></div>
  </div>
  <div class="metric-grid">
    <div><strong>{int(scan.get('pages_crawled') or 0)}</strong><span>crawled</span></div>
    <div><strong>{int(scan.get('pages_retained') or 0)}</strong><span>retained</span></div>
    <div><strong>{int(scan.get('grouped_fixes') or 0)}</strong><span>grouped fixes</span></div>
    <div><strong>{fallback}</strong><span>fallbacks</span></div>
  </div>
</div>
"""


def priority_markdown(scan: dict[str, Any]) -> str:
    priorities = _safe_list(scan.get("priorities"))[:3]
    if not priorities:
        return """
<div class="priority-section">
  <div class="eyebrow">TOP PRIORITIES</div>
  <p class="empty-copy">No grouped priorities were returned for this scan.</p>
</div>
"""

    items: list[str] = []
    for index, fix in enumerate(priorities, start=1):
        title = html.escape(str(fix.get("title") or "Review finding"))
        priority = html.escape(str(fix.get("priority") or "Medium"))
        owner = html.escape(str(fix.get("owner") or "SEO team"))
        affected = int(_number(fix.get("affected_pages"), default=0) or 0)
        items.append(
            f"""
<div class="priority">
  <div class="priority-index">{index}</div>
  <div class="priority-copy">
    <strong>{title}</strong>
    <p>{priority} · {owner} · {affected} pages</p>
  </div>
</div>
"""
        )
    return (
        '<div class="priority-section"><div class="eyebrow">TOP PRIORITIES</div>'
        + "".join(items)
        + "</div>"
    )


def build_grounded_prompt(message: str, scan: dict[str, Any]) -> str:
    evidence = json.dumps(scan, ensure_ascii=False, separators=(",", ":"))
    return f"""You are FixList AI, an evidence-grounded SEO consultant.

Rules:
1. Treat the supplied scan evidence as authoritative only when release_gate_eligible is true.
2. Never invent URLs, counts, findings, or scan outcomes.
3. Never claim a limited or provisional scan is authoritative.
4. Explain technical SEO in plain language.
5. Distinguish confirmed crawl evidence from recommendations.
6. Keep answers concise and organized.
7. When useful, state who should perform the fix.
8. Do not expose hidden reasoning or chain-of-thought.

SCAN_EVIDENCE:
{evidence}

USER_QUESTION:
{message}
"""


def load_google_credentials() -> Any:
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    if SETTINGS.service_account_json:
        info = json.loads(SETTINGS.service_account_json)
        return service_account.Credentials.from_service_account_info(info, scopes=scopes)
    credentials, _ = google_auth_default(scopes=scopes)
    return credentials


def extract_output_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    chunks: list[str] = []
    for output_item in payload.get("output", []) or []:
        if not isinstance(output_item, dict):
            continue
        for content_item in output_item.get("content", []) or []:
            if not isinstance(content_item, dict):
                continue
            text = content_item.get("text")
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
    if chunks:
        return "\n\n".join(chunks)
    raise RuntimeError("Grok returned no readable text output.")


def call_grok(message: str, scan: dict[str, Any]) -> str:
    if SETTINGS.live_scan_enabled:
        response = requests.post(
            f"{_scanner_base_url()}/chat",
            headers=_scanner_headers(),
            json={"message": message, "scan": scan},
            timeout=SETTINGS.grok_timeout_seconds,
        )
        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"Grok proxy returned an unreadable response ({response.status_code})."
            ) from exc
        if not response.ok:
            detail = body.get("detail") if isinstance(body, dict) else None
            raise RuntimeError(
                f"Grok proxy failed ({response.status_code}): {detail or 'Unknown error'}"
            )
        answer = body.get("answer") if isinstance(body, dict) else None
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("Grok proxy returned no readable answer.")
        return answer.strip()

    credentials = load_google_credentials()
    credentials.refresh(GoogleAuthRequest())
    endpoint = (
        "https://aiplatform.googleapis.com/v1/projects/"
        f"{SETTINGS.project_id}/locations/{SETTINGS.location}/endpoints/openapi/responses"
    )
    response = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {credentials.token}",
            "Content-Type": "application/json",
        },
        json={
            "model": SETTINGS.model_id,
            "input": build_grounded_prompt(message, scan),
            "max_output_tokens": 900,
            "stream": False,
        },
        timeout=SETTINGS.grok_timeout_seconds,
    )
    response.raise_for_status()
    return extract_output_text(response.json())


def guided_answer(message: str, scan: dict[str, Any]) -> str:
    normalized = message.lower()
    priorities = _safe_list(scan.get("priorities"))
    prefix = "The demo" if scan.get("source") == "demo" else "The current scan"

    if "first" in normalized or "priority" in normalized:
        if not priorities:
            return "This scan did not return a grouped priority list. Review the crawl limitations before acting."
        fix = priorities[0]
        affected = int(_number(fix.get("affected_pages"), default=0) or 0)
        return (
            f"Start with **{fix.get('title', 'the first confirmed issue')}**.\n\n"
            f"It affects **{affected} pages** and should go to your "
            f"**{str(fix.get('owner') or 'SEO team').lower()}**. "
            f"{fix.get('why') or 'It is the highest-priority confirmed pattern in this scan.'}"
        )

    if "score" in normalized:
        score = scan.get("score")
        if score is None:
            return (
                f"{prefix} did not produce an available health score. "
                "That usually means the review was limited or lacked enough reliable evidence."
            )
        return (
            f"{prefix} score is **{score}/100** and the result is **{_gate_label(scan).lower()}**. "
            f"The review grouped **{int(scan.get('grouped_fixes') or 0)} fixes** from "
            f"**{int(scan.get('pages_retained') or 0)} retained pages**."
        )

    if "myself" in normalized or "developer" in normalized or "who" in normalized:
        if not priorities:
            return "There are no grouped priorities available to assign yet."
        assignments = [
            f"- **{fix.get('title')}** → {fix.get('owner', 'SEO team')}"
            for fix in priorities[:3]
        ]
        return "Here is the cleanest ownership split:\n\n" + "\n".join(assignments)

    if "affected" in normalized or "pages" in normalized:
        if not priorities:
            return (
                f"{prefix} retained **{int(scan.get('pages_retained') or 0)} pages**, "
                "with no grouped priority counts returned."
            )
        return "\n".join(
            f"- **{fix.get('title')}**: {int(_number(fix.get('affected_pages'), default=0) or 0)} pages"
            for fix in priorities[:5]
        )

    return (
        f"{prefix} retained **{int(scan.get('pages_retained') or 0)} pages** and produced "
        f"**{int(scan.get('grouped_fixes') or 0)} grouped fixes**. The result is "
        f"**{_gate_label(scan).lower()}**. Ask what to fix first, why the score changed, "
        "or who should own the work."
    )


def answer_question(message: str, scan: dict[str, Any]) -> str:
    clean_message = (message or "").strip()
    if not clean_message:
        return "Ask a question about the current scan."

    if SETTINGS.live_grok_enabled:
        try:
            return call_grok(clean_message, scan)
        except Exception as exc:
            return (
                "Live Grok could not complete this request, so I answered from the structured "
                f"scan data instead.\n\n`{type(exc).__name__}: {str(exc)[:160]}`\n\n"
                + guided_answer(clean_message, scan)
            )
    return guided_answer(clean_message, scan)


def submit_chat(
    message: str,
    history: list[dict[str, Any]] | None,
    scan: dict[str, Any] | None,
) -> tuple[str, list[dict[str, Any]]]:
    clean_message = (message or "").strip()
    current_scan = scan if isinstance(scan, dict) else DEMO_SCAN
    messages = list(history or [])
    if not clean_message:
        return "", messages
    messages.append({"role": "user", "content": clean_message})
    messages.append({"role": "assistant", "content": answer_question(clean_message, current_scan)})
    return "", messages


def scan_opening_message(scan: dict[str, Any]) -> str:
    score = "not available" if scan.get("score") is None else f"{scan.get('score')}/100"
    priorities = _safe_list(scan.get("priorities"))
    lead = priorities[0].get("title") if priorities else None
    message = (
        f"**Scan complete.** I reviewed **{int(scan.get('pages_retained') or 0)} pages**. "
        f"The health score is **{score}** and the result is **{_gate_label(scan).lower()}**."
    )
    if lead:
        message += f"\n\nThe first grouped priority is **{lead}**."
    return message


def run_scan_from_ui(
    website_url: str,
    scan_mode: str,
    current_scan: dict[str, Any] | None,
    history: list[dict[str, Any]] | None,
    progress: gr.Progress = gr.Progress(),
) -> tuple[dict[str, Any], str, str, str, list[dict[str, Any]]]:
    previous_scan = current_scan if isinstance(current_scan, dict) else DEMO_SCAN
    previous_history = list(history or [])

    if not SETTINGS.live_scan_enabled:
        status = (
            "⚠️ **Scanner not connected.** Add `SCANNER_API_KEY` as a private Space secret, "
            "then restart the Space."
        )
        return (
            previous_scan,
            scan_markdown(previous_scan),
            priority_markdown(previous_scan),
            status,
            previous_history,
        )

    try:
        clean_url = validate_public_website_url(website_url)
        progress(0.05, desc="Preparing scan")
        progress(0.15, desc="Crawling website")
        scan = run_scan_pipeline(clean_url, scan_mode)
        progress(0.95, desc="Preparing results")
        opening_history = [{"role": "assistant", "content": scan_opening_message(scan)}]
        status = (
            f"✅ **Scan complete** · {int(scan.get('pages_crawled') or 0)} pages crawled · "
            f"{_gate_label(scan)}"
        )
        progress(1.0, desc="Complete")
        return scan, scan_markdown(scan), priority_markdown(scan), status, opening_history
    except Exception as exc:
        status = f"❌ **Scan failed:** {html.escape(str(exc)[:260])}"
        return (
            previous_scan,
            scan_markdown(previous_scan),
            priority_markdown(previous_scan),
            status,
            previous_history,
        )


CSS = """
:root {
  --surface: #ffffff;
  --background: #f5f6f4;
  --ink: #18211c;
  --muted: #6c746e;
  --line: #e4e8e4;
  --accent: #24734b;
  --accent-soft: #edf6f0;
  --shadow: 0 10px 30px rgba(20, 35, 25, 0.05);
}
body, .gradio-container { background: var(--background) !important; }
.gradio-container {
  max-width: 1480px !important;
  margin: 0 auto !important;
  color: var(--ink) !important;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
  padding: 16px !important;
}
.main-shell { min-height: calc(100vh - 110px); gap: 14px !important; }
.panel {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 18px;
  box-shadow: var(--shadow);
  padding: 18px;
}
.sidebar-panel { min-height: 760px; }
.chat-panel { padding: 22px; }
.evidence-panel { padding: 20px; }
.brand {
  font-weight: 760;
  font-size: 20px;
  letter-spacing: -0.035em;
  margin-bottom: 24px;
}
.brand-mark {
  display: inline-grid;
  place-items: center;
  width: 28px;
  height: 28px;
  margin-right: 9px;
  border-radius: 9px;
  background: var(--accent);
  color: white;
  font-size: 13px;
}
.nav-item {
  padding: 10px 11px;
  border-radius: 10px;
  color: var(--muted);
  margin: 2px 0;
  font-size: 14px;
}
.nav-item.active { background: var(--accent-soft); color: var(--accent); font-weight: 650; }
.connection-card { margin-top: 28px; padding-top: 16px; border-top: 1px solid var(--line); }
.connection-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 0;
  color: var(--muted);
  font-size: 12px;
}
.connection-value { color: var(--ink); font-weight: 650; }
.hero-copy h1 { font-size: 24px !important; letter-spacing: -0.04em; margin-bottom: 4px !important; }
.hero-copy p { color: var(--muted); margin-top: 0 !important; }
.scan-launcher {
  background: #fafbf9;
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 13px;
  margin: 10px 0 12px;
}
.scan-status { min-height: 28px; color: var(--muted); font-size: 13px; }
.chatbot {
  border: 1px solid var(--line) !important;
  border-radius: 14px !important;
  background: #fbfcfb !important;
}
.chat-compose { margin-top: 8px; gap: 8px !important; }
.chat-input textarea { min-height: 54px !important; }
.secondary-action button {
  background: white !important;
  border-color: var(--line) !important;
  color: var(--muted) !important;
}
.panel-heading { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.eyebrow { color: var(--muted); font-size: 10px; font-weight: 760; letter-spacing: .13em; }
.summary h2 {
  margin: 12px 0 0;
  font-size: 16px;
  letter-spacing: -0.025em;
  word-break: break-word;
}
.score-row { margin: 18px 0 16px; }
.score { font-size: 42px; font-weight: 760; letter-spacing: -0.065em; }
.muted { color: var(--muted); }
.status {
  border: 1px solid #bdd8c7;
  color: var(--accent);
  background: #f0f8f3;
  padding: 5px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 650;
}
.metric-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px; }
.metric-grid div {
  border-top: 1px solid var(--line);
  padding: 10px 0;
  display: flex;
  flex-direction: column;
}
.metric-grid strong { font-size: 17px; }
.metric-grid span, .empty-copy { color: var(--muted); font-size: 12px; }
.priority-section { margin-top: 24px; }
.priority { display: flex; gap: 10px; border-top: 1px solid var(--line); padding: 13px 0; }
.priority-index {
  flex: 0 0 23px;
  width: 23px;
  height: 23px;
  border: 1px solid var(--line);
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: var(--muted);
  font-size: 11px;
}
.priority-copy { min-width: 0; }
.priority-copy strong { font-size: 13px; line-height: 1.35; }
.priority-copy p { margin: 4px 0 0; color: var(--muted); font-size: 11px; }
footer { display: none !important; }
@media (max-width: 1000px) {
  .main-shell { display: block !important; }
  .sidebar-panel { min-height: auto; }
}
"""

scanner_state_label = "Connected" if SETTINGS.live_scan_enabled else "Setup needed"
ai_state_label = "Grok" if SETTINGS.live_grok_enabled else "Guided"

with gr.Blocks(
    title="FixList AI",
    css=CSS,
    theme=gr.themes.Base(
        primary_hue="green",
        neutral_hue="gray",
        radius_size="lg",
        spacing_size="md",
    ),
) as demo:
    current_scan = gr.State(DEMO_SCAN)

    with gr.Row(elem_classes="main-shell"):
        with gr.Column(scale=2, min_width=185, elem_classes=["panel", "sidebar-panel"]):
            gr.HTML('<div class="brand"><span class="brand-mark">F</span>FixList AI</div>')
            gr.HTML(
                """
                <div class="nav-item active">Current scan</div>
                <div class="nav-item">Projects</div>
                <div class="nav-item">Scan history</div>
                <div class="nav-item">Settings</div>
                """
            )
            gr.HTML(
                f"""
                <div class="connection-card">
                  <div class="eyebrow">CONNECTIONS</div>
                  <div class="connection-row"><span>Scanner</span><span class="connection-value">{scanner_state_label}</span></div>
                  <div class="connection-row"><span>Assistant</span><span class="connection-value">{ai_state_label}</span></div>
                </div>
                """
            )

        with gr.Column(scale=7, min_width=480, elem_classes=["panel", "chat-panel"]):
            gr.Markdown(
                """
                # Ask about your crawl
                Get a clear explanation of what happened, what matters, and what to fix next.
                """,
                elem_classes="hero-copy",
            )

            with gr.Group(elem_classes="scan-launcher"):
                with gr.Row():
                    website_input = gr.Textbox(
                        label="Website",
                        placeholder="https://example.com",
                        scale=6,
                        container=False,
                    )
                    scan_mode = gr.Dropdown(
                        choices=["advanced", "deep", "quick", "basic"],
                        value="advanced",
                        label="Scan size",
                        scale=2,
                    )
                    run_scan_button = gr.Button(
                        "Run scan",
                        variant="primary",
                        scale=2,
                        interactive=SETTINGS.live_scan_enabled,
                    )
                scan_status = gr.Markdown(
                    (
                        "Ready for a new 150-page scan."
                        if SETTINGS.live_scan_enabled
                        else "Add the `SCANNER_API_KEY` Space secret to enable new scans."
                    ),
                    elem_classes="scan-status",
                )

            chatbot = gr.Chatbot(
                type="messages",
                height=490,
                placeholder=(
                    "Run a scan or ask about the current result.\n\n"
                    "Try: What should I fix first?"
                ),
                elem_classes="chatbot",
            )

            with gr.Row(elem_classes="chat-compose"):
                chat_input = gr.Textbox(
                    placeholder="Ask anything about this scan…",
                    show_label=False,
                    lines=2,
                    max_lines=5,
                    scale=8,
                    elem_classes="chat-input",
                )
                send_button = gr.Button("Send", variant="primary", scale=1)
                clear_button = gr.Button(
                    "Clear",
                    variant="secondary",
                    scale=1,
                    elem_classes="secondary-action",
                )

            gr.Examples(
                examples=[
                    "What should I fix first?",
                    "Why did I get this score?",
                    "What can I fix myself?",
                    "How many pages are affected?",
                ],
                inputs=chat_input,
                label="Suggested questions",
            )

        with gr.Column(scale=3, min_width=270, elem_classes=["panel", "evidence-panel"]):
            summary_panel = gr.HTML(scan_markdown(DEMO_SCAN))
            priority_panel = gr.HTML(priority_markdown(DEMO_SCAN))

    run_scan_button.click(
        fn=run_scan_from_ui,
        inputs=[website_input, scan_mode, current_scan, chatbot],
        outputs=[current_scan, summary_panel, priority_panel, scan_status, chatbot],
        api_name="run_scan",
        concurrency_limit=1,
    )
    send_button.click(
        fn=submit_chat,
        inputs=[chat_input, chatbot, current_scan],
        outputs=[chat_input, chatbot],
        api_name="chat",
    )
    chat_input.submit(
        fn=submit_chat,
        inputs=[chat_input, chatbot, current_scan],
        outputs=[chat_input, chatbot],
    )
    clear_button.click(fn=lambda: ("", []), outputs=[chat_input, chatbot])


if __name__ == "__main__":
    demo.queue(default_concurrency_limit=4).launch(
        server_name=os.getenv("GRADIO_SERVER_NAME", "0.0.0.0"),
        server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
        show_error=True,
    )
