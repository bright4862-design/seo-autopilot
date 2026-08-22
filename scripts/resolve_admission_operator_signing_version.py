#!/usr/bin/env python3
"""Resolve Secret Manager's ``latest`` alias to a numeric version.

The caller must already be authenticated as the dedicated admission operator.
Only the resolved version number is emitted. The access response (which also
contains the secret payload) stays in process memory and is never logged or
written to disk.
"""

from __future__ import annotations

import json
import re
import subprocess
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

    token = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not token:
        raise SystemExit("Google Cloud access token is unavailable")

    url = (
        "https://secretmanager.googleapis.com/v1/"
        f"projects/{project}/secrets/{secret}/versions/latest:access"
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
    match = re.fullmatch(
        rf"projects/{re.escape(project)}/secrets/{re.escape(secret)}/versions/([1-9][0-9]*)",
        name,
    )
    value.clear()
    if not match:
        raise SystemExit("Secret Manager did not resolve latest to a numeric version")

    print(match.group(1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
