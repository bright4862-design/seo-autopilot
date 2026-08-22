#!/usr/bin/env python3
"""Resolve Secret Manager's ``latest`` alias to enabled numeric metadata.

The caller must already be authenticated as the dedicated admission operator.
Only the resolved version number is emitted. The metadata endpoint never sends
secret payload bytes to this process.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: resolve_admission_operator_signing_version.py PROJECT SECRET")

    project, secret = sys.argv[1:]
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]", project):
        raise SystemExit("invalid Google Cloud project id")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,255}", secret):
        raise SystemExit("invalid Secret Manager secret name")

    token = os.environ.get("FIXLIST_ADMISSION_ACCESS_TOKEN", "").strip()
    if not token:
        raise SystemExit("dedicated admission access token is unavailable")

    url = (
        "https://secretmanager.googleapis.com/v1/"
        f"projects/{project}/secrets/{secret}/versions/latest"
    )
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            value = json.load(response)
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise SystemExit(f"unable to resolve admission signing-secret version: {exc}") from None
    finally:
        token = ""

    name = str(value.get("name") or "")
    state = str(value.get("state") or "")
    match = re.fullmatch(
        rf"projects/[^/]+(?:/locations/[^/]+)?/secrets/{re.escape(secret)}/versions/([1-9][0-9]*)",
        name,
    )
    value.clear()
    if not match:
        raise SystemExit("Secret Manager did not resolve latest to a numeric version")
    if state != "ENABLED":
        raise SystemExit("Secret Manager latest version is not enabled")

    print(match.group(1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
