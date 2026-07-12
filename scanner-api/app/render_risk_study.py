from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


STUDY_VERSION = "render_risk_study_v1"
VALID_STRATA = {
    "smb_cms",
    "saas_js",
    "ecommerce_marketplace",
}
STRATEGIC_STRATA = {"saas_js", "ecommerce_marketplace"}
VALID_EVIDENCE_STATES = {
    "raw_html_sufficient",
    "isolated_client_rendering_signal",
    "material_client_rendering_risk",
}
VALID_MANUAL_VERDICTS = {
    "not_reviewed",
    "content_sufficient",
    "material_content_missing",
    "inconclusive",
}
MATERIAL_EVIDENCE_STATE = "material_client_rendering_risk"
CALIBRATION_MINIMUM = 5
MEASUREMENT_MINIMUM_TOTAL = 30
MEASUREMENT_MINIMUM_PER_STRATUM = 10
CALIBRATION_MINIMUM_AGREEMENT = 0.80
BUILD_THRESHOLD = 0.25
DEFER_THRESHOLD = 0.10


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise TypeError("study record must be an object")

    site = str(record.get("site") or record.get("site_id") or "").strip()
    if not site:
        raise ValueError("site is required")

    stratum = str(record.get("stratum") or "").strip().lower()
    if stratum not in VALID_STRATA:
        raise ValueError(f"stratum must be one of {sorted(VALID_STRATA)}")

    evidence = record.get("render_evidence") if isinstance(record.get("render_evidence"), dict) else {}
    successful_pages = _nonnegative_int(
        record.get("successful_pages", evidence.get("pages_evaluated", 0)),
        "successful_pages",
    )
    suspected_pages = _nonnegative_int(
        record.get(
            "suspected_pages",
            evidence.get("client_rendering_suspected_pages", 0),
        ),
        "suspected_pages",
    )
    if suspected_pages > successful_pages:
        raise ValueError("suspected_pages cannot exceed successful_pages")

    evidence_state = str(
        record.get("scanner_evidence_state")
        or evidence.get("evidence_state")
        or ""
    ).strip()
    if evidence_state not in VALID_EVIDENCE_STATES:
        raise ValueError(
            f"scanner_evidence_state must be one of {sorted(VALID_EVIDENCE_STATES)}"
        )

    manual_verdict = str(record.get("manual_js_disabled_verdict") or "not_reviewed").strip().lower()
    if manual_verdict not in VALID_MANUAL_VERDICTS:
        raise ValueError(
            f"manual_js_disabled_verdict must be one of {sorted(VALID_MANUAL_VERDICTS)}"
        )

    suspected_ratio = round(suspected_pages / successful_pages, 4) if successful_pages else 0.0
    detector_material = evidence_state == MATERIAL_EVIDENCE_STATE
    manual_material = manual_verdict == "material_content_missing"
    conclusive_manual = manual_verdict in {"content_sufficient", "material_content_missing"}
    agreement = detector_material == manual_material if conclusive_manual else None

    return {
        "site": site,
        "stratum": stratum,
        "successful_pages": successful_pages,
        "suspected_pages": suspected_pages,
        "suspected_ratio": suspected_ratio,
        "scanner_evidence_state": evidence_state,
        "detector_material": detector_material,
        "manual_js_disabled_verdict": manual_verdict,
        "manual_material": manual_material if conclusive_manual else None,
        "manual_review_conclusive": conclusive_manual,
        "agreement": agreement,
        "false_positive": bool(conclusive_manual and detector_material and not manual_material),
        "false_negative": bool(conclusive_manual and not detector_material and manual_material),
        "notes": str(record.get("notes") or "").strip(),
    }


def summarize_records(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    normalized = [normalize_record(record) for record in records]
    by_stratum: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in normalized:
        by_stratum[record["stratum"]].append(record)

    strata = {
        stratum: _summarize_group(by_stratum.get(stratum, []))
        for stratum in sorted(VALID_STRATA)
    }
    overall = _summarize_group(normalized)

    calibration_complete = overall["conclusive_manual_reviews"] >= CALIBRATION_MINIMUM
    calibration_passed = bool(
        calibration_complete
        and overall["agreement_rate"] is not None
        and overall["agreement_rate"] >= CALIBRATION_MINIMUM_AGREEMENT
        and overall["false_negative_count"] == 0
    )
    measurement_complete = bool(
        overall["site_count"] >= MEASUREMENT_MINIMUM_TOTAL
        and all(
            strata[stratum]["site_count"] >= MEASUREMENT_MINIMUM_PER_STRATUM
            for stratum in VALID_STRATA
        )
    )

    decision = _decision(
        overall=overall,
        strata=strata,
        calibration_complete=calibration_complete,
        calibration_passed=calibration_passed,
        measurement_complete=measurement_complete,
    )

    return {
        "version": STUDY_VERSION,
        "site_count": overall["site_count"],
        "calibration": {
            "required_manual_reviews": CALIBRATION_MINIMUM,
            "conclusive_manual_reviews": overall["conclusive_manual_reviews"],
            "minimum_agreement_rate": CALIBRATION_MINIMUM_AGREEMENT,
            "agreement_rate": overall["agreement_rate"],
            "false_positive_count": overall["false_positive_count"],
            "false_negative_count": overall["false_negative_count"],
            "complete": calibration_complete,
            "passed": calibration_passed,
        },
        "measurement": {
            "required_total_sites": MEASUREMENT_MINIMUM_TOTAL,
            "required_sites_per_stratum": MEASUREMENT_MINIMUM_PER_STRATUM,
            "complete": measurement_complete,
        },
        "decision_thresholds": {
            "build": BUILD_THRESHOLD,
            "defer": DEFER_THRESHOLD,
        },
        "overall": overall,
        "strata": strata,
        "decision": decision,
        "records": normalized,
    }


def format_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Renderer-risk study",
        "",
        f"- Version: `{summary.get('version', STUDY_VERSION)}`",
        f"- Sites recorded: {summary.get('site_count', 0)}",
        f"- Calibration passed: {'yes' if summary.get('calibration', {}).get('passed') else 'no'}",
        f"- Measurement complete: {'yes' if summary.get('measurement', {}).get('complete') else 'no'}",
        f"- Decision: **{summary.get('decision', {}).get('action', 'unknown')}**",
        f"- Reason: {summary.get('decision', {}).get('reason', '')}",
        "",
        "| Stratum | Sites | Material-risk incidence | Manual reviews | Agreement |",
        "|---|---:|---:|---:|---:|",
    ]
    for stratum in sorted(VALID_STRATA):
        values = summary.get("strata", {}).get(stratum, {})
        lines.append(
            "| {name} | {sites} | {incidence} | {manual} | {agreement} |".format(
                name=stratum,
                sites=values.get("site_count", 0),
                incidence=_percent(values.get("detector_material_incidence")),
                manual=values.get("conclusive_manual_reviews", 0),
                agreement=_percent(values.get("agreement_rate")),
            )
        )
    lines.append("")
    return "\n".join(lines)


def _summarize_group(records: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(records)
    detector_material_count = sum(1 for record in records if record["detector_material"])
    conclusive = [record for record in records if record["manual_review_conclusive"]]
    manual_material_count = sum(1 for record in conclusive if record["manual_material"])
    agreements = [record for record in conclusive if record["agreement"] is True]
    return {
        "site_count": count,
        "detector_material_count": detector_material_count,
        "detector_material_incidence": round(detector_material_count / count, 4) if count else 0.0,
        "conclusive_manual_reviews": len(conclusive),
        "manual_material_count": manual_material_count,
        "manual_material_incidence": round(manual_material_count / len(conclusive), 4) if conclusive else None,
        "agreement_rate": round(len(agreements) / len(conclusive), 4) if conclusive else None,
        "false_positive_count": sum(1 for record in conclusive if record["false_positive"]),
        "false_negative_count": sum(1 for record in conclusive if record["false_negative"]),
    }


def _decision(
    *,
    overall: dict[str, Any],
    strata: dict[str, dict[str, Any]],
    calibration_complete: bool,
    calibration_passed: bool,
    measurement_complete: bool,
) -> dict[str, str]:
    if not calibration_complete:
        return {
            "action": "validate_detector",
            "reason": "Complete at least five conclusive JavaScript-disabled reviews before trusting incidence data.",
        }
    if not calibration_passed:
        return {
            "action": "recalibrate_detector",
            "reason": "The detector did not meet the pre-committed agreement threshold or produced a false negative.",
        }
    if not measurement_complete:
        return {
            "action": "keep_measuring",
            "reason": "Collect at least ten sites in each stratum and thirty sites overall.",
        }

    strategic_material = [
        stratum
        for stratum in sorted(STRATEGIC_STRATA)
        if strata[stratum]["detector_material_incidence"] >= BUILD_THRESHOLD
    ]
    if strategic_material:
        return {
            "action": "build_for_strategic_segment",
            "reason": (
                "Material rendering risk reached 25% in strategic strata: "
                + ", ".join(strategic_material)
                + "."
            ),
        }

    incidence = overall["detector_material_incidence"]
    if incidence >= BUILD_THRESHOLD:
        return {
            "action": "build_renderer",
            "reason": "Material rendering risk reached the pre-committed 25% build threshold.",
        }
    if incidence < DEFER_THRESHOLD and all(
        values["detector_material_incidence"] < DEFER_THRESHOLD
        for values in strata.values()
    ):
        return {
            "action": "defer_renderer",
            "reason": "Material rendering risk stayed below 10% overall and in every stratum.",
        }
    return {
        "action": "revisit_with_customer_evidence",
        "reason": "Incidence is between the pre-committed defer and build thresholds.",
    }


def _nonnegative_int(value: Any, field: str) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if number < 0:
        raise ValueError(f"{field} must be non-negative")
    return number


def _percent(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"
