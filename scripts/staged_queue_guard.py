#!/usr/bin/env python3
"""Pure readback checks for operate-staged-queue.sh.

Every decision is made from JSON that gcloud returned for the live resources;
nothing here calls gcloud or mutates state. The shell wrapper owns the calls.
"""
from __future__ import annotations

import json
import re
import sys
from urllib.parse import urlsplit

PROJECT = "seo-autopilot-501517"
REGION = "europe-west1"
STAGE_QUEUE = "fixlist-scan-stages"
STAGE_QUEUE_PATH = f"projects/{PROJECT}/locations/{REGION}/queues/{STAGE_QUEUE}"
# The worker opens the bucket its own environment names; activation must bind
# that to the one bucket the infrastructure verifier checks.
WORKSPACE_BUCKET = "fixlist-scan-workspaces-seo-autopilot-501517"
WORKER_SA = f"fixlist-standard150-worker@{PROJECT}.iam.gserviceaccount.com"
INVOKER_SA = f"fixlist-standard150-invoker@{PROJECT}.iam.gserviceaccount.com"
REVISION_RE = re.compile(r"fixlist-standard150-worker-[0-9]{5}-[a-z0-9]{3}\Z")
OWNER_RE = re.compile(r"[A-Za-z0-9_-]{6,64}\Z")
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
MAX_OWNERS = 5


class GuardError(ValueError):
    """The live state does not satisfy the operation's precondition."""


def require(condition: bool, detail: str) -> None:
    if not condition:
        raise GuardError(detail)


def canonical_origin(service: dict) -> str:
    url = str((service.get("status") or {}).get("url") or "")
    parts = urlsplit(url)
    require(parts.scheme == "https" and bool(parts.hostname) and parts.hostname.endswith(".run.app")
            and "---" not in parts.hostname and not parts.username and not parts.password
            and not parts.port and not parts.path and not parts.query and not parts.fragment,
            "Canonical Cloud Run worker origin unavailable")
    return url


def addressable_revisions(service: dict) -> dict[str, dict]:
    """Every revision that can receive a request: serving traffic or tagged."""
    out: dict[str, dict] = {}
    for entry in (service.get("status") or {}).get("traffic") or []:
        name = str(entry.get("revisionName") or "")
        if not name:
            continue
        try:
            percent = int(entry.get("percent") or 0)
        except (TypeError, ValueError) as exc:
            raise GuardError("Ambiguous traffic percentage in service status") from exc
        if percent > 0 or entry.get("tag"):
            slot = out.setdefault(name, {"percent": 0, "tags": {}})
            slot["percent"] += percent
            if entry.get("tag"):
                slot["tags"][str(entry["tag"])] = str(entry.get("url") or "").rstrip("/")
    require(bool(out), "Worker service reports no addressable revision")
    return out


def revision_env(revision: dict) -> dict[str, str]:
    containers = ((revision.get("spec") or {}).get("containers")) or []
    require(len(containers) == 1, "Worker revision must have exactly one container")
    env: dict[str, str] = {}
    for item in containers[0].get("env") or []:
        if "value" in item:
            env[str(item.get("name"))] = str(item.get("value") or "")
    return env


def owners_of(env: dict[str, str]) -> list[str]:
    raw = env.get("SCAN_STAGED_OWNER_IDS") or env.get("SCAN_PIPELINE_OWNER_IDS") or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


def staged_intake_enabled(env: dict[str, str]) -> bool:
    """Mirror scanner-api staged_pipeline_enabled: staged mode plus any owner."""
    return env.get("SCAN_PIPELINE_MODE", "monolith").lower() == "staged" and bool(owners_of(env))


def check_intake_disabled(service: dict, revisions: dict[str, dict], gateway_env: dict[str, str]) -> list[str]:
    """New staged admissions must be off everywhere GCP can read before any drain."""
    addressable = addressable_revisions(service)
    missing = sorted(set(addressable) - set(revisions))
    require(not missing, f"Missing revision readback for {','.join(missing)}")
    enabled = [name for name in sorted(addressable) if staged_intake_enabled(revision_env(revisions[name]))]
    require(not enabled, f"Staged intake still enabled on worker revision(s): {','.join(enabled)}")
    require(not staged_intake_enabled(gateway_env), "Staged intake still enabled on the serving dispatch gateway")
    return sorted(addressable)


def check_activation_candidate(service: dict, revisions: dict[str, dict], staged_revision: str) -> dict[str, str]:
    """The one revision that will receive stage tasks must be exactly configured."""
    require(bool(REVISION_RE.fullmatch(staged_revision)), "STAGED_REVISION must be an exact worker revision name")
    origin = canonical_origin(service)
    addressable = addressable_revisions(service)
    require(staged_revision in addressable and staged_revision in revisions,
            "STAGED_REVISION is not an addressable revision of the worker service")
    slot = addressable[staged_revision]
    require(slot["percent"] == 0, "STAGED_REVISION receives production traffic; refuse to activate through it")
    revision = revisions[staged_revision]
    sa = ((revision.get("spec") or {}).get("serviceAccountName")) or ""
    require(sa == WORKER_SA, "STAGED_REVISION runs as an unexpected service account")
    env = revision_env(revision)
    source = env.get("FIXLIST_WORKER_SOURCE_SHA", "")
    require(bool(SHA_RE.fullmatch(source)), "STAGED_REVISION declares no exact FIXLIST_WORKER_SOURCE_SHA")
    tag = f"staged-{source[:12]}"
    expected_target = f"https://{tag}---{origin.removeprefix('https://')}"
    require(slot["tags"].get(tag) == expected_target,
            f"STAGED_REVISION must carry the source-bound tag {tag} at {expected_target}")
    require(env.get("SCAN_STAGE_TASKS_QUEUE_PATH") == STAGE_QUEUE_PATH
            or (not env.get("SCAN_STAGE_TASKS_QUEUE_PATH") and env.get("SCAN_STAGE_QUEUE") == STAGE_QUEUE
                and env.get("SCAN_TASKS_PROJECT") == PROJECT and env.get("SCAN_TASKS_LOCATION") == REGION),
            "STAGED_REVISION does not enqueue to the fixed stage queue")
    require(env.get("SCAN_STAGE_TARGET_URL", "").rstrip("/") == expected_target,
            "SCAN_STAGE_TARGET_URL must equal the revision's own source-bound tag URL")
    require(env.get("SCAN_STAGE_TOKEN_AUDIENCE", "").rstrip("/") == origin,
            "SCAN_STAGE_TOKEN_AUDIENCE must be the canonical service origin")
    require(env.get("TASKS_INVOKER_SERVICE_ACCOUNT") == INVOKER_SA, "Stage task invoker differs from the fixed invoker")
    require(env.get("SCAN_WORKSPACE_BUCKET") == WORKSPACE_BUCKET,
            f"STAGED_REVISION must use the fixed workspace bucket {WORKSPACE_BUCKET}")
    mode = env.get("SCAN_PIPELINE_MODE", "monolith").lower()
    require(mode in {"monolith", "staged"}, "SCAN_PIPELINE_MODE must be monolith or staged")
    owners = owners_of(env)
    require("*" not in owners, "Wildcard staged cohort refused; list exact owner IDs")
    require(len(owners) <= MAX_OWNERS and all(OWNER_RE.fullmatch(o) for o in owners),
            f"Staged cohort must be at most {MAX_OWNERS} exact owner IDs")
    # Only the verified candidate may admit new staged scans.
    others = [name for name in sorted(addressable) if name != staged_revision
              and name in revisions and staged_intake_enabled(revision_env(revisions[name]))]
    require(not others, f"Other revision(s) still admit staged scans: {','.join(others)}")
    missing = sorted(set(addressable) - set(revisions))
    require(not missing, f"Missing revision readback for {','.join(missing)}")
    return {"target": expected_target, "audience": origin, "source_sha": source,
            "mode": mode, "owner_count": str(len(owners))}


def task_names(listing: list) -> list[str]:
    require(isinstance(listing, list), "Task listing is not a JSON list")
    names = []
    for task in listing:
        name = str((task or {}).get("name") or "")
        require(name.startswith(f"projects/{PROJECT}/locations/{REGION}/queues/") and "/tasks/" in name,
                "Malformed task name in listing")
        names.append(name)
    return names


def _load(path: str):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: list[str]) -> int:
    command, *rest = argv
    if command == "origin":
        print(canonical_origin(_load(rest[0])))
    elif command == "addressable":
        print("\n".join(sorted(addressable_revisions(_load(rest[0])))))
    elif command == "intake-disabled":
        service, gateway, *revision_paths = rest
        revisions = {r.get("metadata", {}).get("name"): r for r in map(_load, revision_paths)}
        gateway_env = revision_env(_load(gateway)) if gateway != "-" else {}
        names = check_intake_disabled(_load(service), revisions, gateway_env)
        print(f"STAGED_INTAKE_DISABLED revisions={','.join(names)}")
    elif command == "activation":
        service, staged_revision, *revision_paths = rest
        revisions = {r.get("metadata", {}).get("name"): r for r in map(_load, revision_paths)}
        found = check_activation_candidate(_load(service), revisions, staged_revision)
        print(" ".join(f"{key}={value}" for key, value in found.items()))
    elif command == "count":
        print(len(task_names(_load(rest[0]))))
    elif command == "first-task":
        names = task_names(_load(rest[0]))
        print(names[0] if names else "")
    else:
        raise GuardError(f"Unknown guard command {command}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (GuardError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"STAGED_QUEUE_GUARD_REFUSED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
