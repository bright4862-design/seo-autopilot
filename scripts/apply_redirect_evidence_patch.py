from pathlib import Path

path = Path("scanner-api/app/scanner.py")
text = path.read_text()


def replace_once(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one match, found {count}: {old[:120]!r}")
    text = text.replace(old, new, 1)


replace_once(
    "from .canonical_validation import validate_canonical_targets\n"
    "from .extract import classify_template, extract_links, extract_page\n",
    "from .canonical_validation import validate_canonical_targets\n"
    "from .redirect_validation import apply_redirect_evidence, fetch_with_redirect_evidence, summarize_redirect_evidence\n"
    "from .extract import classify_template, extract_links, extract_page\n",
)

replace_once(
    "                        page = await fetch_and_extract(client, target, snapshot)\n",
    "                        page = await fetch_and_extract(client, target, snapshot, robots_policy=robots_policy)\n",
)

replace_once(
    "        canonical_target_evidence = await validate_canonical_targets(\n"
    "            client,\n"
    "            pages,\n"
    "            robots_policy,\n"
    "            deadline=deadline,\n"
    "        )\n",
    "        canonical_target_evidence = await validate_canonical_targets(\n"
    "            client,\n"
    "            pages,\n"
    "            robots_policy,\n"
    "            deadline=deadline,\n"
    "        )\n"
    "        redirect_evidence = summarize_redirect_evidence(pages)\n",
)

replace_once(
    '        "canonical_target_evidence": canonical_target_evidence,\n'
    '        "scan_mode": scan_mode,\n',
    '        "canonical_target_evidence": canonical_target_evidence,\n'
    '        "redirect_evidence": redirect_evidence,\n'
    '        "scan_mode": scan_mode,\n',
)

replace_once(
    '            "canonical_target_evidence": canonical_target_evidence,\n'
    '            "render_evidence_version": RENDER_EVIDENCE_VERSION,\n',
    '            "canonical_target_evidence": canonical_target_evidence,\n'
    '            "redirect_evidence": redirect_evidence,\n'
    '            "render_evidence_version": RENDER_EVIDENCE_VERSION,\n',
)

replace_once(
    '            "failed_pages": sum(1 for page in pages if page.get("status_code", 0) >= 400 or page.get("fetch_error")),\n',
    '            "failed_pages": sum(1 for page in pages if is_verified_failed(page)),\n',
)

replace_once(
    '        if 200 <= int(page.get("status_code") or 0) < 400 and not page.get("fetch_error")\n',
    '        if 200 <= int(page.get("status_code") or 0) < 400\n'
    '        and not page.get("fetch_error")\n'
    '        and not page_is_redirect_source(page)\n',
)

start = text.index("async def fetch_and_extract(")
end = text.index("\n\ndef build_findings", start)
new_fetch = '''async def fetch_and_extract(
    client: httpx.AsyncClient,
    url: str,
    discovery: dict,
    robots_policy=None,
) -> dict:
    if not is_public_http_url(url):
        return extract_page("", url, url, 0, "", discovery, fetch_error="blocked_non_public_host")
    try:
        redirect_evidence = None
        if robots_policy is None:
            response = await safe_get(client, url)
            if response is None:
                return extract_page("", url, url, 0, "", discovery, fetch_error="blocked_non_public_redirect")
        else:
            response, redirect_evidence = await fetch_with_redirect_evidence(
                client,
                url,
                robots_policy,
            )
            if response is None:
                page = extract_page(
                    "",
                    url,
                    str(redirect_evidence.get("destination_url") or url),
                    0,
                    "",
                    discovery,
                    fetch_error=str(redirect_evidence.get("fetch_error") or "redirect_validation_failed"),
                )
                apply_redirect_evidence(page, redirect_evidence)
                return page

        content_type = response.headers.get("content-type", "")
        html = response.text if "html" in content_type or "xml" in content_type or not content_type else ""
        page = extract_page(
            html,
            url,
            str(response.url),
            response.status_code,
            content_type,
            discovery,
            response_headers={"x-robots-tag": response.headers.get_list("x-robots-tag")},
        )
        if redirect_evidence is not None:
            apply_redirect_evidence(page, redirect_evidence)
        page["_html"] = html
        return page
    except Exception as exc:
        return extract_page("", url, url, 0, "", discovery, fetch_error=str(exc)[:220])
'''
text = text[:start] + new_fetch + text[end:]

replace_once(
    '        if page.get("url_confidence") == "crawler_artifact":\n'
    '            continue\n'
    '        if sitemap_indexability_conflict(page):\n',
    '        if page.get("url_confidence") == "crawler_artifact":\n'
    '            continue\n'
    '        redirect_finding = redirect_finding_for_page(page)\n'
    '        if redirect_finding is not None:\n'
    '            findings.append(redirect_finding)\n'
    '        if page_is_redirect_source(page):\n'
    '            continue\n'
    '        if sitemap_indexability_conflict(page):\n',
)

marker = "\ndef canonical_target_finding(page: dict) -> dict | None:\n"
insert = r'''


def page_is_redirect_source(page: dict) -> bool:
    state = str(page.get("redirect_state") or "")
    return int(page.get("redirect_hop_count") or 0) > 0 or state in {
        "redirect_loop",
        "redirect_missing_location",
        "redirect_invalid_location",
        "redirect_chain_limit_exceeded",
        "redirect_destination_blocked_by_robots",
        "redirect_destination_failed",
        "blocked_non_public_redirect",
    }


def redirect_finding_for_page(page: dict) -> dict | None:
    if not page_is_redirect_source(page):
        return None

    state = str(page.get("redirect_state") or "")
    sources = set(page.get("discovered_from") or [])
    source_path = str(page.get("redirect_source_path") or urlparse(str(page.get("url") or "")).path or "/")
    destination = str(page.get("redirect_destination_url") or page.get("final_url") or "")
    destination_status = int(page.get("redirect_destination_status_code") or 0)
    destination_indexability = str(page.get("redirect_destination_indexability_state") or "")
    chain = [str(item) for item in (page.get("redirect_chain") or []) if str(item)]
    hop_count = int(page.get("redirect_hop_count") or 0)

    if state == "redirect_loop":
        details = (
            "redirect_loop", "high", "Remove a redirect loop",
            "This URL redirects back to a URL already visited in the same redirect path, so crawlers and visitors cannot reach a final page.",
            "Choose one final destination and update each redirect so the path ends there without returning to an earlier URL.",
        )
    elif state in {"redirect_missing_location", "redirect_invalid_location"}:
        details = (
            "redirect_invalid_response", "high", "Fix a redirect with no valid destination",
            "This URL returned a redirect response without a usable destination URL.",
            "Add a valid absolute or relative Location header that points directly to the intended final page.",
        )
    elif state == "redirect_chain_limit_exceeded":
        details = (
            "redirect_chain_limit", "high", "Fix an unresolved redirect chain",
            "The redirect path exceeded the scanner's bounded hop limit before reaching a final page.",
            "Replace the chain with one direct redirect to the final live destination.",
        )
    elif state in {"redirect_destination_failed", "blocked_non_public_redirect"} or destination_status >= 400 or destination_indexability == "Failed":
        details = (
            "redirect_destination_failed", "high", "Fix a redirect that ends on an unavailable page",
            "The redirect destination failed to load, returned an error, or could not be safely reached.",
            "Point the source URL directly to a live 200-status destination or restore the intended destination page.",
        )
    elif state == "redirect_destination_blocked_by_robots" or destination_indexability == "Blocked by robots.txt":
        details = (
            "redirect_destination_blocked", "medium", "Review a redirect to a robots-blocked destination",
            "The redirect ends on a URL that Googlebot or the scanner is blocked from crawling.",
            "Confirm the destination is intentional and allow search crawlers to access it when the page should appear in search.",
        )
    elif destination_indexability == "Noindexed":
        details = (
            "redirect_destination_noindex", "high", "Fix a redirect to a noindexed destination",
            "The redirect ends on a page that explicitly tells search engines not to index it.",
            "Use an indexable final destination or remove the noindex directive when the destination should rank.",
        )
    elif state == "redirect_chain" or hop_count >= 2:
        details = (
            "redirect_chain", "medium", "Shorten a redirect chain",
            "This URL passes through multiple redirects before reaching the final page.",
            "Update the first redirect and any links or sitemap entries to point directly to the final destination.",
        )
    elif "sitemap" in sources:
        details = (
            "sitemap_redirect", "medium", "Replace a redirecting URL in the sitemap",
            "The sitemap lists a URL that redirects instead of the final indexable destination.",
            "Replace the sitemap entry with the final 200-status canonical URL.",
        )
    elif "internal_link" in sources:
        details = (
            "internal_link_redirect", "low", "Update an internal link that passes through a redirect",
            "An internal link points to an old URL and makes crawlers and visitors take an unnecessary redirect.",
            "Update the internal link to point directly to the final destination.",
        )
    else:
        return None

    rule, priority, title, explanation, recommendation = details
    current_parts = []
    if chain:
        current_parts.append(" → ".join(chain[:8]))
    elif destination:
        current_parts.append(destination)
    if destination_status:
        current_parts.append(f"destination HTTP {destination_status}")
    if destination_indexability:
        current_parts.append(f"destination: {destination_indexability}")

    finding = create_finding(
        rule=rule,
        category="indexability",
        priority=priority,
        title=title,
        page_url=source_path,
        current_value=" — ".join(current_parts),
        explanation=explanation,
        recommendation=recommendation,
        difficulty="developer",
        source_pages=page.get("source_pages", []),
        link_text_samples=page.get("link_text_samples", []),
    )
    finding.update({
        "redirect_state": state,
        "redirect_hop_count": hop_count,
        "redirect_chain": chain,
        "redirect_destination_url": destination,
        "redirect_destination_status_code": destination_status,
        "redirect_destination_indexability_state": destination_indexability,
        "redirect_evidence_version": page.get("redirect_evidence_version"),
        "evidence_status": "confirmed",
        "verification_state": "verified",
        "confidence_score": 94,
    })
    return finding
'''
if marker not in text:
    raise SystemExit("canonical finding marker missing")
text = text.replace(marker, insert + marker, 1)

replace_once(
    'TEMPLATE_RULES = {"client_rendering", "canonical_missing", "canonical_target_redirect", "canonical_target_failed", "canonical_target_noindex", "canonical_target_blocked", "canonical_chain", "canonical_loop", "canonical_cross_domain", "schema", "missing_h1", "multiple_h1", "image_alt_text", "missing_meta_description", "sitemap_indexability_conflict"}\n',
    'TEMPLATE_RULES = {"client_rendering", "canonical_missing", "canonical_target_redirect", "canonical_target_failed", "canonical_target_noindex", "canonical_target_blocked", "canonical_chain", "canonical_loop", "canonical_cross_domain", "redirect_loop", "redirect_invalid_response", "redirect_chain_limit", "redirect_destination_failed", "redirect_destination_blocked", "redirect_destination_noindex", "redirect_chain", "sitemap_redirect", "internal_link_redirect", "schema", "missing_h1", "multiple_h1", "image_alt_text", "missing_meta_description", "sitemap_indexability_conflict"}\n',
)

replace_once(
    '    if rule == "canonical_cross_domain":\n        return "Verify cross-domain canonical URLs"\n    if rule == "sitemap_indexability_conflict":\n',
    '    if rule == "canonical_cross_domain":\n        return "Verify cross-domain canonical URLs"\n    if rule == "redirect_loop":\n        return "Remove redirect loops"\n    if rule in {"redirect_invalid_response", "redirect_chain_limit"}:\n        return "Fix unresolved redirect paths"\n    if rule == "redirect_destination_failed":\n        return "Fix redirects that end on unavailable pages"\n    if rule == "redirect_destination_blocked":\n        return "Review redirects to robots-blocked pages"\n    if rule == "redirect_destination_noindex":\n        return "Fix redirects to noindexed pages"\n    if rule == "redirect_chain":\n        return "Shorten repeated redirect chains"\n    if rule == "sitemap_redirect":\n        return "Replace redirecting URLs in the sitemap"\n    if rule == "internal_link_redirect":\n        return "Update internal links that pass through redirects"\n    if rule == "sitemap_indexability_conflict":\n',
)

replace_once(
    'def is_verified_failed(page: dict) -> bool:\n    if str(page.get("fetch_error") or "").startswith("blocked_"):\n        return False\n',
    'def is_verified_failed(page: dict) -> bool:\n    if page_is_redirect_source(page):\n        return False\n    if str(page.get("fetch_error") or "").startswith("blocked_"):\n        return False\n',
)

replace_once(
    '    keys = ["url", "final_url", "path", "status_code", "fetch_error", "url_confidence", "url_suspicion_reasons", "discovered_from", "source_pages", "link_text_samples", "page_template_family", "estimated_page_intent", "title", "h1"]\n',
    '    keys = ["url", "final_url", "path", "status_code", "fetch_error", "url_confidence", "url_suspicion_reasons", "discovered_from", "source_pages", "link_text_samples", "page_template_family", "estimated_page_intent", "title", "h1", "redirect_state", "redirect_hop_count", "redirect_chain", "redirect_destination_url", "redirect_destination_status_code", "redirect_destination_indexability_state"]\n',
)

path.write_text(text)
