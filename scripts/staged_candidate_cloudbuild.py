#!/usr/bin/env python3
"""Bound inactive staged candidates to exact source, configuration and tags."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit


OWNER_RE = re.compile(r"[A-Za-z0-9_-]{6,64}")
COHORT_KEYS = ("SCAN_PIPELINE_MODE", "SCAN_STAGED_OWNER_IDS")
ENV_KEYS = {"SCAN_WORKSPACE_BUCKET", "SCAN_TASKS_PROJECT", "SCAN_TASKS_LOCATION", "SCAN_STAGE_QUEUE", "SCAN_STAGE_TASKS_QUEUE_PATH", "SCAN_STAGE_TARGET_URL", "SCAN_STAGE_TOKEN_AUDIENCE", "SCAN_PIPELINE_MODE", "SCAN_STAGED_OWNER_IDS"}


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def source_tag(sha):
    require(bool(re.fullmatch(r"[0-9a-f]{40}", sha)), "An exact full source SHA is required")
    return "staged-" + sha[:12]


def digest_for(sha, env):
    return hashlib.sha256(json.dumps({"source_sha": sha, "environment": env}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def environment(sha, project, region, bucket, queue, origin):
    require(bool(re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]", bucket)), "Explicit workspace bucket required")
    match = re.fullmatch(r"projects/([a-z][a-z0-9-]{0,62})/locations/([a-z][a-z0-9-]{0,62})/queues/([a-z][a-z0-9-]{0,62})", queue)
    require(match is not None and match[1] == project and match[2] == region, "Stage queue must match the selected project and region")
    parsed = urlsplit(origin)
    require(parsed.scheme == "https" and parsed.hostname and parsed.netloc == parsed.hostname and parsed.hostname.endswith(".run.app") and "---" not in parsed.hostname and not parsed.path and not parsed.query and not parsed.fragment, "A canonical Cloud Run service token audience is required")
    target = "https://" + source_tag(sha) + "---" + parsed.hostname
    require(all(0 < len(label) <= 63 for label in urlsplit(target).hostname.split(".")), "Source-bound staged tag exceeds a DNS label limit")
    return {"SCAN_WORKSPACE_BUCKET": bucket, "SCAN_TASKS_PROJECT": project, "SCAN_TASKS_LOCATION": region, "SCAN_STAGE_QUEUE": match[3], "SCAN_STAGE_TASKS_QUEUE_PATH": queue, "SCAN_STAGE_TARGET_URL": target, "SCAN_STAGE_TOKEN_AUDIENCE": origin, "SCAN_PIPELINE_MODE": "monolith", "SCAN_STAGED_OWNER_IDS": ""}


def owner_cohort(value):
    """The explicit owner-canary cohort: exactly one exact owner ID.

    One owner keeps the value free of the commas that separate Cloud Run
    environment entries. Base44, the gateway and this worker must list the
    same owner; the digest uses the gateway's sorted-cohort definition.
    """
    owners = [item for item in str(value or "").split(",")]
    require(len(owners) == 1 and bool(OWNER_RE.fullmatch(owners[0])), "owner-canary requires exactly one exact owner ID; wildcards and lists are refused")
    return owners[0]


def cohort_sha256(owner):
    return hashlib.sha256(json.dumps([owner], separators=(",", ":")).encode()).hexdigest()


def cohorted(env, owner):
    """The reviewed inactive environment with only the two cohort keys set.

    The configuration digest is computed over the reviewed inactive environment,
    so a cohort cannot hide a change to any other staged setting.
    """
    return {**env, "SCAN_PIPELINE_MODE": "staged", "SCAN_STAGED_OWNER_IDS": owner}


def prepare(args):
    worker = json.loads(Path(args.worker_json).read_text())
    tag = source_tag(args.source_sha)
    require(not any(item.get("tag") == tag for item in worker.get("status", {}).get("traffic", [])), "Immutable staged source tag already exists and must never be rebound")
    reviewed = environment(args.source_sha, args.project, args.region, args.bucket, args.queue_path, str(worker.get("status", {}).get("url") or "").rstrip("/"))
    digest = digest_for(args.source_sha, reviewed)
    env = dict(reviewed)
    result = {"tag": tag, "digest": digest, "mode": args.mode}
    if args.mode == "owner-canary":
        owner = owner_cohort(args.owners)
        env = cohorted(reviewed, owner)
        result["cohort_sha256"] = cohort_sha256(owner)
    else:
        require(args.mode == "inactive" and not args.owners, "Inactive candidates carry no owner cohort")
    env["FIXLIST_STAGED_CONFIG_SHA256"] = digest
    result["environment"] = env
    print(json.dumps(result))


def validate(args):
    mode, suffix, tag, digest, sha = (os.environ[key] for key in ("STAGED_SCAN_MODE", "STAGED_ENV_SUFFIX", "STAGED_TAG", "STAGED_CONFIG_SHA256", "STAGED_SOURCE_SHA"))
    source_tag(sha)
    require(Path(args.source_stamp).read_text().strip() == sha, "Cloud Build source stamp does not match the configured full SHA")
    if mode == "off":
        require(not suffix and not tag and not digest, "Disabled staged configuration must be empty")
        return
    require(mode in {"inactive", "owner-canary"}, "Unsupported staged candidate mode")
    entries = suffix.split(",")[1:] if suffix.startswith(",") else []
    require(all("=" in item for item in entries), "Invalid staged environment suffix")
    pairs = [item.split("=", 1) for item in entries]
    env = dict(pairs)
    require(len(pairs) == len(env) and set(env) == ENV_KEYS | {"FIXLIST_STAGED_CONFIG_SHA256"}, "Unexpected staged environment field")
    reviewed = environment(sha, os.environ["STAGED_PROJECT"], os.environ["STAGED_REGION"], env["SCAN_WORKSPACE_BUCKET"], env["SCAN_STAGE_TASKS_QUEUE_PATH"], env["SCAN_STAGE_TOKEN_AUDIENCE"])
    supplied = env.pop("FIXLIST_STAGED_CONFIG_SHA256")
    if mode == "inactive":
        require(env == reviewed, "Inactive environment must retain monolith mode, no owner cohort and the exact source-bound target")
    else:
        owner = owner_cohort(env.get("SCAN_STAGED_OWNER_IDS"))
        require(env == cohorted(reviewed, owner), "Owner-canary environment may differ from the reviewed inactive build only in staged mode and one exact owner")
    require(tag == source_tag(sha) and supplied == digest == digest_for(sha, reviewed), "Source tag or staged configuration digest mismatch")


def cloud(*arguments):
    done = subprocess.run(["gcloud", *arguments, "--format=json"], text=True, capture_output=True, check=True, timeout=180)
    return json.loads(done.stdout)


def traffic_state(service):
    rows = service.get("status", {}).get("traffic", [])
    weights = sorted((row.get("revisionName"), int(row.get("percent") or 0)) for row in rows if int(row.get("percent") or 0))
    tags = {row["tag"]: row.get("revisionName") for row in rows if row.get("tag")}
    return weights, tags


def tag_candidate(args):
    if args.mode == "off":
        return
    require(args.mode in {"inactive", "owner-canary"} and args.tag == source_tag(args.source_sha), "Only inactive or owner-canary source-bound candidates may be tagged")
    owner = owner_cohort(args.owners) if args.mode == "owner-canary" else ""
    expected_mode = "staged" if owner else "monolith"
    require(bool(re.fullmatch(r"[0-9a-f]{64}", args.digest)), "Staged configuration digest is required")
    scope = (f"--project={args.project}", f"--region={args.region}")
    rows = cloud("run", "revisions", "list", f"--service={args.worker_service}", *scope)
    matches = []
    for revision in rows:
        env = {item.get("name"): item.get("value", "") for item in (revision.get("spec", {}).get("containers") or [{}])[0].get("env", [])}
        if (env.get("FIXLIST_WORKER_SOURCE_SHA") == args.source_sha and env.get("FIXLIST_STAGED_CONFIG_SHA256") == args.digest
                and env.get("SCAN_PIPELINE_MODE") == expected_mode and env.get("SCAN_STAGED_OWNER_IDS", "") == owner
                and not env.get("SCAN_PIPELINE_OWNER_IDS")
                and (not args.image_ref or (revision.get("status") or {}).get("imageDigest") == args.image_ref)):
            matches.append((revision.get("metadata", {}).get("creationTimestamp", ""), revision.get("metadata", {}).get("name", "")))
    require(bool(matches), "No exact source/configuration staged revision exists")
    candidate = sorted(matches)[-1][1]
    if args.revision:
        # The caller already bound this revision to the build's image digest:
        # it must be the only match, or no tag is touched.
        require([name for _, name in matches] == [args.revision], "Staged candidate is not the exact revision bound to the built image digest")
    before = cloud("run", "services", "describe", args.worker_service, *scope)
    weights, tags = traffic_state(before)
    require(args.tag not in tags, "Refusing to rebind an existing immutable staged source tag")
    require(not any(revision == candidate and weight > 0 for revision, weight in weights), "Candidate unexpectedly receives traffic")
    cloud("run", "services", "update-traffic", args.worker_service, *scope, f"--update-tags={args.tag}={candidate}")
    after = cloud("run", "services", "describe", args.worker_service, *scope)
    new_weights, new_tags = traffic_state(after)
    require(new_weights == weights and all(new_tags.get(tag) == revision for tag, revision in tags.items()), "Tagging changed the serving traffic split or an existing tag")
    require(new_tags.get(args.tag) == candidate, "Staged source tag does not resolve to the exact candidate")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    item = commands.add_parser("prepare")
    for name in ("worker-json", "source-sha", "project", "region", "bucket", "queue-path"):
        item.add_argument("--" + name, required=True)
    item.add_argument("--mode", choices=("inactive", "owner-canary"), default="inactive")
    item.add_argument("--owners", default="")
    item = commands.add_parser("validate")
    item.add_argument("--source-stamp", required=True)
    item = commands.add_parser("tag")
    for name in ("mode", "source-sha", "tag", "digest", "worker-service", "region", "project"):
        item.add_argument("--" + name, required=True)
    item.add_argument("--owners", default="")
    item.add_argument("--revision", default="")
    item.add_argument("--image-ref", default="")
    args = parser.parse_args(argv)
    {"prepare": prepare, "validate": validate, "tag": tag_candidate}[args.command](args)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"STAGED_CANDIDATE_BLOCKED: {exc}") from exc
