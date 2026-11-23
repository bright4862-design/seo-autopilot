#!/usr/bin/env python3
"""Summarize only safe fields from *already retrieved* Cloud Run logs.

P0 #378, /revision HTTP 500 investigation. This script never fetches logs,
contacts a service, scans a customer, writes a file, or outputs raw payloads.
Pipe a narrow, read-only Cloud Logging JSON query to stdin; never attach raw
logs to tickets. Every printed field is an allowlisted derivative.

Example read-only operator query (requires existing Cloud Logging viewer access):

  gcloud logging read '\
resource.type="cloud_run_revision" AND \
resource.labels.service_name="fixlist-standard150-worker" AND \
resource.labels.revision_name="fixlist-standard150-worker-00097-lvl" AND \
timestamp>="2026-11-23T12:06:50Z" AND timestamp<="2026-11-23T12:09:35Z" AND \
(logName:"run.googleapis.com%2Frequests" OR \
 logName:"run.googleapis.com%2Fvarlog%2Fsystem" OR severity>=ERROR)' \
    --project="$PROJECT" --limit=500 --format=json | \
    python scripts/summarize_revision_500_logs.py \
      --service fixlist-standard150-worker \
      --revision fixlist-standard150-worker-00097-lvl \
      --since 2026-11-23T12:06:50Z --until 2026-11-23T12:09:35Z \
      --query-limit 500

Use "set -o pipefail" so a denied logging read does not look like zero rows.
A query that reaches --limit is not complete evidence: this tool emits only
redacted metadata and exits 3 until a narrower time window is queried.
A trace-correlated error is NOT proof the application caused the HTTP 500;
platform and request metadata must be reviewed privately before attributing.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import sys
from urllib.parse import urlsplit

MAX_ENTRIES = 1000
ERROR_LEVELS = {"ERROR", "CRITICAL", "ALERT", "EMERGENCY"}
SYSTEM_LOG_SUFFIX = "/logs/run.googleapis.com%2Fvarlog%2Fsystem"


def as_utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamps must be ISO-8601 UTC strings")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(dt):
        raise ValueError("timestamps must have explicit UTC timezone")
    return dt.astimezone(timezone.utc)


def summarize(entries: list[dict], *, service: str, revision: str, since: str, until: str,
              query_limit: int = 500) -> dict:
    if type(entries) is not list or len(entries) > MAX_ENTRIES:
        raise ValueError("expected an array with at most 1000 log entries")
    if type(query_limit) is not int or not 1 <= query_limit <= MAX_ENTRIES:
        raise ValueError("query limit must be an integer in 1..1000")
    query_at_limit = len(entries) >= query_limit
    start, end = as_utc(since), as_utc(until)
    if end <= start or (end - start).total_seconds() > 1800:
        raise ValueError("require positive interval of at most 30 minutes")
    if not service or not revision or not revision.startswith(service + "-"):
        raise ValueError("require exact service and service-prefixed revision")

    eligible = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        resource = entry.get("resource") or {}
        labels = resource.get("labels") or {}
        if (resource.get("type") != "cloud_run_revision"
                or labels.get("service_name") != service
                or labels.get("revision_name") != revision):
            continue
        try:
            when = as_utc(entry.get("timestamp", ""))
        except (ValueError, TypeError):
            continue
        if not start <= when <= end:
            continue
        eligible.append((when, entry))

    # Cloud Run system logs can be INFO without a request trace (e.g.,
    # instance starts). Keep counts only, never text or causal attribution.
    system_logs = [entry for _, entry in eligible
                   if (entry.get("logName") or "").endswith(SYSTEM_LOG_SUFFIX)]
    untraced_nonrequest_errors = sum(
        entry.get("severity") in ERROR_LEVELS
        and "run.googleapis.com%2Frequests" not in (entry.get("logName") or "")
        and not entry.get("trace") for _, entry in eligible
    )

    # Only exact trace matches are counted; never print trace IDs. A correlated
    # error may originate anywhere in a request's execution path.
    error_traces = set()
    for _, entry in eligible:
        if (entry.get("severity") in ERROR_LEVELS
                and "run.googleapis.com%2Frequests" not in (entry.get("logName") or "")
                and isinstance(entry.get("trace"), str)
                and entry["trace"]):
            error_traces.add(entry["trace"])

    requests = []
    seen = set()
    for when, entry in eligible:
        if "run.googleapis.com%2Frequests" not in (entry.get("logName") or ""):
            continue
        http = entry.get("httpRequest") or {}
        try:
            parsed = urlsplit(http.get("requestUrl") or "")
            status = int(http.get("status"))
        except (ValueError, TypeError):
            continue
        if parsed.scheme != "https" or parsed.path != "/revision":
            continue
        if status not in (200, 500):
            continue
        # Cloud Logging considers insertId duplicates only at the same exact
        # timestamp within a project. This operator query is project-scoped.
        # Reusing an insertId at another timestamp must not erase a request.
        # Keep the original timestamp precision, not the redacted seconds.
        insert_id = entry.get("insertId")
        if isinstance(insert_id, str) and insert_id:
            key = (entry.get("timestamp"), insert_id)
            if key in seen:
                continue
            seen.add(key)
        trace = entry.get("trace")
        requests.append({
            "time_utc": when.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "http_status": status,
            "correlated_error_log": bool(trace and trace in error_traces),
        })
    requests.sort(key=lambda row: (row["time_utc"], row["http_status"]))
    failures = sum(row["http_status"] == 500 for row in requests)
    return {
        "status": ("INDETERMINATE_QUERY_AT_LIMIT" if query_at_limit
                   else "METADATA_ONLY_DIAGNOSTIC_NOT_CAUSE_PROOF"),
        "query_at_limit": query_at_limit,
        "query_entry_count": len(entries),
        "query_limit": query_limit,
        "revision": revision,
        "request_500_count": failures,
        "request_200_count": len(requests) - failures,
        "system_log_count": len(system_logs),
        "system_error_log_count": sum(
            entry.get("severity") in ERROR_LEVELS for entry in system_logs),
        "untraced_nonrequest_error_count": untraced_nonrequest_errors,
        "error_correlated_500_count": sum(
            row["http_status"] == 500 and row["correlated_error_log"] for row in requests),
        "requests": requests,
        "interpretation": (
            "Correlated error logs are clues, not attribution; missing matches "
            "do not establish a platform cause. System or untraced error logs "
            "are uncorrelated context, not proof of failed startup. "
            "Missing requests do not establish health. A result at or above "
            "the query limit can omit earlier request and startup logs; "
            "even a result below that limit does not prove logging completeness."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--since", required=True)
    parser.add_argument("--until", required=True)
    parser.add_argument("--query-limit", type=int, default=500,
                        help="Match the gcloud logging read --limit value (default 500)")
    args = parser.parse_args()
    try:
        raw = sys.stdin.read(4_000_001)
        if len(raw) > 4_000_000:
            raise ValueError("input exceeds 4 MB")
        result = summarize(json.loads(raw), service=args.service, revision=args.revision,
                           since=args.since, until=args.until, query_limit=args.query_limit)
    except (json.JSONDecodeError, ValueError, TypeError):
        # Never print supplied data or exception messages: they may contain
        # raw log payloads or customer secrets.
        print("LOG_DIAGNOSTIC_INPUT_REJECTED", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 3 if result["query_at_limit"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
