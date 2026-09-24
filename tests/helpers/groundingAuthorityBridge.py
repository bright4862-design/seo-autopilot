#!/usr/bin/env python3
"""Test bridge for V8 authority -> authenticated Grounding EvidenceSet."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SCANNER_API = ROOT / "scanner-api"
if str(SCANNER_API) not in sys.path:
    sys.path.insert(0, str(SCANNER_API))

from app.authority_seal import stable_serialize  # noqa: E402
from app.grounding_authority import (  # noqa: E402
    GROUNDING_V8_AUTHORITY_ADAPTER_VERSION,
    build_evidence_set_from_v8_authority,
)
from app.grounding_verifier import EvidenceUnavailable  # noqa: E402


def main() -> None:
    request = json.load(sys.stdin)
    snapshot = request.get("snapshot")
    proof = request.get("proof")
    signing_key = request.get("signing_key")
    try:
        evidence = build_evidence_set_from_v8_authority(
            snapshot,
            proof=proof,
            signing_key=signing_key,
        )
        authority_sha256 = hashlib.sha256(
            stable_serialize(snapshot).encode("utf-8")
        ).hexdigest()
        print(json.dumps({
            "ok": True,
            "adapter_version": GROUNDING_V8_AUTHORITY_ADAPTER_VERSION,
            "authority_sha256": authority_sha256,
            "evidence": {
                "version": evidence.version,
                "fingerprint": evidence.fingerprint,
                "scan_origin": evidence.scan_origin,
                "url_members": sorted(evidence.url_members),
                "live_urls": sorted(evidence.live_urls),
                "numeric_values": dict(evidence.numeric_values),
                "state_values": dict(evidence.state_values),
                "fix_refs": sorted(evidence.fix_refs),
                "root_cause_refs": sorted(evidence.root_cause_refs),
            },
        }, sort_keys=True))
    except EvidenceUnavailable as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))


if __name__ == "__main__":
    main()
