from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from .fixtures import representative_cases
from .reasoning_candidate import VERTEX_REASONING_CANDIDATE
from .vertex_contract import CURRENT_VERTEX_CONTRACT

MANIFEST_VERSION = "provider_lab_eval_manifest_v1"


def build_manifest() -> dict[str, Any]:
    cases = representative_cases()
    return {
        "manifest_version": MANIFEST_VERSION,
        "baseline": {
            "provider": CURRENT_VERTEX_CONTRACT.identity.provider,
            "model_id": CURRENT_VERTEX_CONTRACT.identity.model_id,
        },
        "candidate": {
            "provider": VERTEX_REASONING_CANDIDATE.identity.provider,
            "model_id": VERTEX_REASONING_CANDIDATE.identity.model_id,
        },
        "cases": [
            {
                "case_id": case.case_id,
                "authority_hash": case.authority_hash,
                "evidence_hash": case.evidence_hash,
                "question": case.question,
                "history_turns": len(case.history),
            }
            for case in cases
        ],
    }


def manifest_json() -> str:
    return json.dumps(
        build_manifest(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def manifest_sha256() -> str:
    return sha256(manifest_json().encode("utf-8")).hexdigest()
