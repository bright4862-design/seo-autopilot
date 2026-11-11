#!/usr/bin/env python3
"""Print a least-privilege staged-scan infrastructure plan; --apply runs it.

This does not deploy a worker, flip a cohort, or enqueue any customer scan.
All resource names and identities must be supplied explicitly.
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--bucket", required=True, help="Bucket name without gs://")
    parser.add_argument("--queue", default="fixlist-scan-stages")
    parser.add_argument("--worker-sa", required=True)
    parser.add_argument("--invoker-sa", required=True)
    parser.add_argument("--worker-url", required=True, help="Pinned HTTPS worker origin")
    parser.add_argument("--token-audience", help="Canonical Cloud Run service origin; required for a tagged target")
    parser.add_argument("--concurrency", type=int, default=40)
    parser.add_argument("--apply", action="store_true", help="Execute the printed gcloud mutations")
    args = parser.parse_args(argv)
    for name in ("project", "region", "queue"):
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", getattr(args, name)):
            parser.error(f"--{name} must be a lowercase resource identifier")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]", args.bucket):
        parser.error("--bucket must be a bucket name without a scheme or path")
    for name in ("worker_sa", "invoker_sa"):
        if not re.fullmatch(r"[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com", getattr(args, name)):
            parser.error(f"--{name.replace('_', '-')} must be a service-account email")
    origin = urlsplit(args.worker_url)
    if (origin.scheme != "https" or not origin.hostname or origin.username or origin.password
            or origin.port not in (None, 443) or origin.path not in ("", "/")
            or origin.query or origin.fragment):
        parser.error("--worker-url must be an HTTPS origin without credentials or a path")
    if not 1 <= args.concurrency <= 40:
        parser.error("--concurrency must be between 1 and 40")
    args.worker_url = args.worker_url.rstrip("/")
    audience = urlsplit(args.token_audience or args.worker_url)
    if (audience.scheme != "https" or not audience.hostname or audience.username or audience.password
            or audience.port not in (None, 443) or audience.path not in ("", "/")
            or audience.query or audience.fragment or "---" in audience.hostname):
        parser.error("--token-audience must be a canonical HTTPS service origin")
    args.token_audience = (args.token_audience or args.worker_url).rstrip("/")
    if args.token_audience != args.worker_url and not (
            origin.hostname.endswith(".run.app") and audience.hostname.endswith(".run.app")
            and origin.hostname.endswith("---" + audience.hostname)
            and origin.port == audience.port):
        parser.error("Tagged worker target must belong to the token audience's Cloud Run service")
    return args


def lifecycle():
    return {"rule": [{"action": {"type": "Delete"}, "condition": {"age": 30}}]}


def plan(args, lifecycle_path):
    project = f"--project={args.project}"
    location = f"--location={args.region}"
    bucket = f"gs://{args.bucket}"
    worker = f"--member=serviceAccount:{args.worker_sa}"
    return [
        ["gcloud", "storage", "buckets", "create", bucket, project, location,
         "--uniform-bucket-level-access", "--public-access-prevention"],
        ["gcloud", "storage", "buckets", "update", bucket, project,
         f"--lifecycle-file={lifecycle_path}"],
        ["gcloud", "storage", "buckets", "add-iam-policy-binding", bucket, project,
         worker, "--role=roles/storage.objectUser"],
        ["gcloud", "tasks", "queues", "create", args.queue, project, location,
         f"--max-concurrent-dispatches={args.concurrency}", "--max-attempts=10",
         "--min-backoff=10s", "--max-backoff=120s", "--max-doublings=4",
         "--max-retry-duration=1800s"],
        ["gcloud", "tasks", "queues", "add-iam-policy-binding", args.queue,
         project, location, worker, "--role=roles/cloudtasks.enqueuer"],
        ["gcloud", "iam", "service-accounts", "add-iam-policy-binding", args.invoker_sa,
         project, worker, "--role=roles/iam.serviceAccountUser"],
    ]


def worker_environment(args):
    return {
        "SCAN_WORKSPACE_BUCKET": args.bucket,
        "SCAN_TASKS_PROJECT": args.project,
        "SCAN_TASKS_LOCATION": args.region,
        "SCAN_STAGE_QUEUE": args.queue,
        "SCAN_STAGE_TASKS_QUEUE_PATH": f"projects/{args.project}/locations/{args.region}/queues/{args.queue}",
        "SCAN_STAGE_TARGET_URL": args.worker_url,
        "SCAN_STAGE_TOKEN_AUDIENCE": args.token_audience,
        "TASKS_INVOKER_SERVICE_ACCOUNT": args.invoker_sa,
    }


def main(argv=None):
    args = arguments(argv)
    with tempfile.TemporaryDirectory(prefix="fixlist-staged-infra-") as temp:
        lifecycle_path = Path(temp) / "lifecycle.json"
        lifecycle_path.write_text(json.dumps(lifecycle()), encoding="utf-8")
        print("Lifecycle JSON:", json.dumps(lifecycle()))
        print("Worker configuration (deploy separately; preserve existing environment):")
        print(json.dumps(worker_environment(args), indent=2))
        for command in plan(args, lifecycle_path):
            print(shlex.join(command), flush=True)
            if args.apply:
                # Stop on failure. Existing resources are never overwritten or
                # silently assumed to have the requested security configuration.
                subprocess.run(command, check=True)
    if not args.apply:
        print("Dry run only. No gcloud command was executed. Use --apply after reviewing this plan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
