"""Mandatory seed-to-admission bridge for Extended 500 private reservations.

Pure verifier used INSIDE the coordinator's Firestore transaction.
A signed paid entitlement cannot reserve: an exact Base44-created ScanRun
must already be reconciled to a seeded receipt in Firestore, and that
receipt must still own its seed-owner slot.

No customer route, network calls, payments, queue operations or deployment.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import core
import scanrun_seed


def require_seeded_scanrun(
    seed: Any, seed_slot: Any, claim: dict[str, Any], grant: dict[str, Any],
) -> str:
    """Return bound scan ID; refuse any missing, stale or conflicting seed.

    Called under the SAME Firestore read-before-write transaction that
    reserves an admission owner slot. The initial Base44 create is not
    atomic with Firestore: only exact reconciled seed authorizes admission.
    """
    claim = {key: claim[key] for key in (
        "owner_user_id", "scan_id", "project_id", "request_id",
        "idempotency_key", "access_id", "attempt_count",
    )}
    for name in ("owner_user_id", "scan_id", "project_id", "request_id",
                 "idempotency_key", "access_id"):
        core.required_identifier(claim[name], name)
    core.safe_attempt(claim["attempt_count"])
    if claim["idempotency_key"] != claim["request_id"]:
        raise core.AdmissionRefused("seed_request_idempotency_mismatch")
    rid = scanrun_seed.seed_receipt_id(claim["owner_user_id"], claim["request_id"])
    idem_ref = scanrun_seed.idempotency_ref(claim["owner_user_id"], claim["idempotency_key"])
    if not isinstance(seed, dict) or seed.get("schema") != scanrun_seed.RECEIPT_SCHEMA:
        raise core.AdmissionRefused("seed_receipt_unavailable")
    if seed.get("state") != scanrun_seed.SEEDED:
        raise core.AdmissionRefused("seed_not_reconciled")
    if (seed.get("receipt_id") != rid or seed.get("scan_id") != claim["scan_id"]
            or seed.get("owner_user_id") != claim["owner_user_id"]
            or seed.get("project_id") != claim["project_id"]
            or seed.get("request_id") != claim["request_id"]
            or seed.get("attempt_count") != claim["attempt_count"]
            or seed.get("access_id") != claim["access_id"]
            or seed.get("idempotency_ref") != idem_ref
            or seed.get("scan_mode") != core.MODE
            or seed.get("scan_source") != scanrun_seed.SCAN_SOURCE):
        raise core.AdmissionRefused("seed_admission_identity_mismatch")
    if (not isinstance(seed_slot, dict)
            or seed_slot.get("schema") != scanrun_seed.SLOT_SCHEMA
            or seed_slot.get("state") != scanrun_seed.SLOT_ACTIVE
            or seed_slot.get("owner_user_id") != claim["owner_user_id"]
            or seed_slot.get("request_id") != claim["request_id"]
            or seed_slot.get("receipt_id") != rid):
        raise core.AdmissionRefused("seed_owner_slot_not_bound")
    if not isinstance(grant, dict):
        raise core.AdmissionRefused("seed_grant_missing")
    target = grant.get("website_url")
    try:
        parsed = urlsplit(target)
        host = (parsed.hostname or "").lower().rstrip(".")
    except (ValueError, TypeError):
        raise core.AdmissionRefused("seed_target_invalid") from None
    if (not isinstance(target, str) or parsed.scheme not in ("https", "http")
            or not host or "." not in host or parsed.netloc != host
            or parsed.port is not None or parsed.query or parsed.fragment
            or parsed.path not in ("", "/")
            or parsed.username or parsed.password
            or target != f"{parsed.scheme}://{host}/"
            or grant.get("path_prefix") is not None
            or grant.get("respect_robots_txt") is not True
            or grant.get("owner_attested_robots_override") is not False):
        raise core.AdmissionRefused("seed_target_invalid")
    normalized = host.removeprefix("www.")
    if (seed.get("website_url") != target
            or seed.get("normalized_domain") != normalized
            or seed.get("request_fingerprint")
                != f"{core.MODE}|{target}|root|respect_robots_txt"):
        raise core.AdmissionRefused("seed_target_mismatch")
    return claim["scan_id"]
