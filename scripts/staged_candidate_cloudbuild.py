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


def prepare(args):
    worker = json.loads(Path(args.worker_json).read_text())
    tag = source_tag(args.source_sha)
    require(not any(item.get("tag") == tag for item in worker.get("status", {}).get("traffic", [])), "Immutable staged source tag already exists and must never be rebound")
    env = environment(args.source_sha, args.project, args.region, args.bucket, args.queue_path, str(worker.get("status", {}).get("url") or "").rstrip("/"))
    digest = digest_for(args.source_sha, env)
    env["FIXLIST_STAGED_CONFIG_SHA256"] = digest
    print(json.dumps({"tag": tag, "digest": digest, "environment": env}))


def validate(args):
    mode, suffix, tag, digest, sha = (os.environ[key] for key in ("STAGED_SCAN_MODE", "STAGED_ENV_SUFFIX", "STAGED_TAG", "STAGED_CONFIG_SHA256", "STAGED_SOURCE_SHA"))
    source_tag(sha)
    require(Path(args.source_stamp).read_text().strip() == sha, "Cloud Build source stamp does not match the configured full SHA")
    if mode == "off":
        require(not suffix and not tag and not digest, "Disabled staged configuration must be empty")
        return
    require(mode == "inactive", "Owner activation requires verified deployed V9 runtime acceptance")
    entries = suffix.split(",")[1:] if suffix.startswith(",") else []
    require(all("=" in item for item in entries), "Invalid staged environment suffix")
    pairs = [item.split("=", 1) for item in entries]
    env = dict(pairs)
    require(len(pairs) == len(env) and set(env) == ENV_KEYS | {"FIXLIST_STAGED_CONFIG_SHA256"}, "Unexpected staged environment field")
    expected = environment(sha, os.environ["STAGED_PROJECT"], os.environ["STAGED_REGION"], env["SCAN_WORKSPACE_BUCKET"], env["SCAN_STAGE_TASKS_QUEUE_PATH"], env["SCAN_STAGE_TOKEN_AUDIENCE"])
    supplied = env.pop("FIXLIST_STAGED_CONFIG_SHA256")
    require(env == expected, "Inactive environment must retain monolith mode, no owner cohort and the exact source-bound target")
    require(tag == source_tag(sha) and supplied == digest == digest_for(sha, expected), "Source tag or staged configuration digest mismatch")


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
    require(args.mode == "inactive" and args.tag == source_tag(args.source_sha), "Only inactive source-bound candidates may be tagged")
    require(bool(re.fullmatch(r"[0-9a-f]{64}", args.digest)), "Staged configuration digest is required")
    scope = (f"--project={args.project}", f"--region={args.region}")
    rows = cloud("run", "revisions", "list", f"--service={args.worker_service}", *scope)
    matches = []
    for revision in rows:
        env = {item.get("name"): item.get("value", "") for item in (revision.get("spec", {}).get("containers") or [{}])[0].get("env", [])}
        if env.get("FIXLIST_WORKER_SOURCE_SHA") == args.source_sha and env.get("FIXLIST_STAGED_CONFIG_SHA256") == args.digest and env.get("SCAN_PIPELINE_MODE") == "monolith" and not env.get("SCAN_STAGED_OWNER_IDS"):
            matches.append((revision.get("metadata", {}).get("creationTimestamp", ""), revision.get("metadata", {}).get("name", "")))
    require(bool(matches), "No exact source/configuration staged revision exists")
    candidate = sorted(matches)[-1][1]
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
    item = commands.add_parser("validate")
    item.add_argument("--source-stamp", required=True)
    item = commands.add_parser("tag")
    for name in ("mode", "source-sha", "tag", "digest", "worker-service", "region", "project"):
        item.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    {"prepare": prepare, "validate": validate, "tag": tag_candidate}[args.command](args)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"STAGED_CANDIDATE_BLOCKED: {exc}") from exc
