#!/usr/bin/env python3
"""Read-only verification of staged-scan bucket, queue, IAM and task contract.

No customer task is created. --task verifies one existing task when available.
Without it, per-task OIDC, target and dispatch deadline remain unverified.
"""
from __future__ import annotations

import argparse
import json
import subprocess

from prepare_staged_scan_infra import arguments as infra_arguments


class VerificationError(ValueError):
    pass


def require(condition, detail):
    if not condition:
        raise VerificationError(detail)


def validate_bucket(bucket, policy, worker_sa):
    iam = bucket.get("iamConfiguration") or {}
    uniform = bucket.get("uniform_bucket_level_access")
    if uniform is None:
        uniform = (iam.get("uniformBucketLevelAccess") or {}).get("enabled")
    public = bucket.get("public_access_prevention", iam.get("publicAccessPrevention"))
    require(uniform is True, "Workspace bucket must enforce uniform bucket-level access")
    require(public == "enforced", "Workspace bucket must enforce public access prevention")
    rules = (bucket.get("lifecycle_config") or bucket.get("lifecycle") or {}).get("rule") or []
    require(any(rule.get("action") == {"type": "Delete"}
                and rule.get("condition") == {"age": 30} for rule in rules),
            "Workspace bucket needs an unconditional 30-day deletion rule")
    require(not any(member in ("allUsers", "allAuthenticatedUsers")
                    for binding in policy.get("bindings", []) for member in binding.get("members", [])),
            "Workspace bucket IAM contains public principals")
    validate_binding(policy, "roles/storage.objectUser", worker_sa)


def validate_binding(policy, role, email):
    require(any(binding.get("role") == role and not binding.get("condition")
                and f"serviceAccount:{email}" in binding.get("members", [])
                for binding in policy.get("bindings", [])),
            f"Missing explicit resource-scoped {role} binding for {email}")


def validate_queue(queue, expected_path, concurrency, expected_state="RUNNING"):
    require(queue.get("name") == expected_path, "Stage queue name does not match the configured queue")
    require(expected_state in {"PAUSED", "RUNNING"}, "Expected stage queue state must be PAUSED or RUNNING")
    require(queue.get("state") == expected_state, f"Stage queue must be {expected_state}")
    require((queue.get("rateLimits") or {}).get("maxConcurrentDispatches") == concurrency,
            "Stage queue concurrency differs from the reviewed configuration")
    retry = queue.get("retryConfig") or {}
    require(retry.get("maxAttempts") == 10, "Stage queue must have maxAttempts=10 to outlast a crashed worker lease")
    require(retry.get("minBackoff") == "10s" and retry.get("maxBackoff") == "120s",
            "Stage queue backoff must be 10s to 120s")
    require(retry.get("maxDoublings") == 4 and retry.get("maxRetryDuration") == "1800s",
            "Stage queue needs maxDoublings=4 and maxRetryDuration=1800s")
    require(not queue.get("httpTarget"), "Queue HTTP overrides must not replace pinned per-task OIDC/targets")


def validate_task(task, worker_url, invoker_sa, token_audience=None):
    request = task.get("httpRequest") or {}
    require(request.get("url") in {f"{worker_url}/scan-batch", f"{worker_url}/scan-finalize"},
            "Stage task target must be a pinned worker stage endpoint")
    require(request.get("httpMethod") == "POST", "Stage task must use POST")
    oidc = request.get("oidcToken") or {}
    require(oidc.get("serviceAccountEmail") == invoker_sa, "Stage task OIDC identity differs from invoker")
    require(oidc.get("audience") == (token_audience or worker_url), "Stage task OIDC audience must be the canonical service origin")
    require(task.get("dispatchDeadline") == "480s", "Stage task dispatch deadline must remain 480s")


def describe(command):
    completed = subprocess.run(["gcloud", *command, "--format=json"], check=True,
                               capture_output=True, text=True)
    return json.loads(completed.stdout)


def main(argv=None):
    # Share validated identity/resource arguments with the preparation script.
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--task")
    parser.add_argument("--expected-queue-state", choices=("PAUSED", "RUNNING"), default="RUNNING")
    extra, rest = parser.parse_known_args(argv)
    args = infra_arguments(rest)
    require(not args.apply, "The verifier is read-only; --apply is not accepted")
    project, location = f"--project={args.project}", f"--location={args.region}"
    bucket = f"gs://{args.bucket}"
    validate_bucket(describe(["storage", "buckets", "describe", bucket, project]),
                    describe(["storage", "buckets", "get-iam-policy", bucket, project]), args.worker_sa)
    validate_queue(describe(["tasks", "queues", "describe", args.queue, project, location]),
                   f"projects/{args.project}/locations/{args.region}/queues/{args.queue}", args.concurrency, extra.expected_queue_state)
    validate_binding(describe(["tasks", "queues", "get-iam-policy", args.queue, project, location]),
                     "roles/cloudtasks.enqueuer", args.worker_sa)
    validate_binding(describe(["iam", "service-accounts", "get-iam-policy", args.invoker_sa, project]),
                     "roles/iam.serviceAccountUser", args.worker_sa)
    print(f"PASS: private workspace, lifecycle, {extra.expected_queue_state} queue retry policy and resource-scoped IAM")
    if extra.task:
        validate_task(describe(["tasks", "describe", extra.task, f"--queue={args.queue}", project, location]),
                      args.worker_url, args.invoker_sa, args.token_audience)
        print("PASS: existing stage task target, OIDC identity/audience and 480s dispatch deadline")
    else:
        print("UNVERIFIED: per-task OIDC, target and dispatch deadline (supply --task with an existing task)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (VerificationError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
