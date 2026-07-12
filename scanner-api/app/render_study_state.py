from __future__ import annotations

from typing import Any

from .render_evidence_quality import assess_render_evidence_coverage


MANUAL_FIELDS = ("manual_js_disabled_verdict", "notes")


def _site(record: dict[str, Any]) -> str:
    return str(record.get("site") or record.get("site_id") or "").strip()


def _ordered_by_manifest(manifest: list[dict], records: dict[str, dict]) -> list[dict]:
    return [records[site] for site in (_site(item) for item in manifest) if site in records]


def prepare_render_study_state(
    manifest: list[dict[str, Any]],
    successes: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Refresh manual review metadata and remove invalid cached negative evidence.

    Cached records with zero or materially shallow evaluable HTML coverage are
    removed from both state files. The collector will therefore treat them as
    pending and rescan them on the next run rather than preserving a false
    `raw_html_sufficient` conclusion.
    """
    manifest_by_site = {_site(item): dict(item) for item in manifest if _site(item)}
    success_by_site = {_site(item): dict(item) for item in successes if _site(item) in manifest_by_site}
    failure_by_site = {_site(item): dict(item) for item in failures if _site(item) in manifest_by_site}

    removed_sites: list[str] = []
    manual_updates = 0

    for site, record in list(success_by_site.items()):
        manifest_record = manifest_by_site[site]
        for field in MANUAL_FIELDS:
            manifest_value = str(manifest_record.get(field) or ("not_reviewed" if field == "manual_js_disabled_verdict" else "")).strip()
            if str(record.get(field) or "").strip() != manifest_value:
                record[field] = manifest_value
                manual_updates += 1

        evidence = record.get("render_evidence") if isinstance(record.get("render_evidence"), dict) else {}
        coverage = assess_render_evidence_coverage(
            evidence,
            pages_crawled=record.get("pages_crawled", 0),
            pages_found=record.get("pages_found", 0),
        )
        record["render_evidence_quality"] = coverage
        if not coverage["sufficient"] and str(evidence.get("evidence_state") or "") != "material_client_rendering_risk":
            removed_sites.append(site)
            success_by_site.pop(site, None)
            failure_by_site.pop(site, None)
            continue

        success_by_site[site] = record
        failure_by_site.pop(site, None)

    for site, record in list(failure_by_site.items()):
        manifest_record = manifest_by_site[site]
        record["url"] = str(manifest_record.get("url") or record.get("url") or "")
        record["stratum"] = str(manifest_record.get("stratum") or record.get("stratum") or "")
        failure_by_site[site] = record

    prepared_successes = _ordered_by_manifest(manifest, success_by_site)
    prepared_failures = _ordered_by_manifest(manifest, failure_by_site)
    summary = {
        "manifest_sites": len(manifest_by_site),
        "successful_sites": len(prepared_successes),
        "failed_sites": len(prepared_failures),
        "removed_insufficient_sites": removed_sites,
        "removed_insufficient_count": len(removed_sites),
        "manual_field_updates": manual_updates,
        "pending_sites": len(manifest_by_site) - len(prepared_successes) - len(prepared_failures),
    }
    return prepared_successes, prepared_failures, summary
