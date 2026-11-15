#!/usr/bin/env python3
"""Validate the exact signed-POST observation from a pinned Cloud Run worker."""

import argparse
import json
import re
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IDENTITIES_FILE = ROOT / "scanner-api/app/generated_v9_worker_runtime.py"
MAX_OBSERVATION_BYTES = 16_384


def matches_observation(observed, *, source_sha, revision):
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        return False
    if not re.fullmatch(r"fixlist-standard150-worker-[a-z0-9-]{1,40}", revision):
        return False

    generated = runpy.run_path(str(IDENTITIES_FILE))
    fingerprint = generated["V9_WORKER_RELEASE_FINGERPRINT"]
    expected = {
        "source_sha": source_sha,
        "worker_revision": revision,
        "transport": "worker_signed_post",
        "base44_app_id": "6a498732ec779dfaaeab0e53",
        "base44_origin": "https://base44.app",
        "release_fingerprint": fingerprint,
        "functions": [
            {
                "protocol": "fixlist_worker_runtime_v1",
                "action": "identity",
                "function_name": name,
                "http_status": 200,
                "release_fingerprint": fingerprint,
                **identity,
            }
            for name, identity in generated["V9_WORKER_FUNCTION_IDENTITIES"].items()
        ],
    }
    return observed == expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    raw = sys.stdin.buffer.read(MAX_OBSERVATION_BYTES + 1)
    try:
        observed = json.loads(raw) if len(raw) <= MAX_OBSERVATION_BYTES else None
    except (UnicodeError, ValueError):
        observed = None
    if not matches_observation(observed, source_sha=args.source_sha, revision=args.revision):
        print("Staged worker Base44 signed runtime does not match the release.", file=sys.stderr)
        return 1
    print(f"STAGED_WORKER_BASE44_RUNTIME_VERIFIED revision={args.revision} signed_functions=3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
