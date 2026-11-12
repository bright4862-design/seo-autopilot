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

from staged_candidate_cloudbuild import digest_for, environment as inactive_environment

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


def traffic_percent(entry: dict) -> int:
    """Exact JSON integer 0-100; an omitted field is the protobuf default 0.

    int(x or 0) would read 0.9, False, "0", null and -0.9 as zero traffic,
    which is the one value the 0%-traffic gate must not be fooled about.
    """
    percent = entry.get("percent", 0)
    require(type(percent) is int and 0 <= percent <= 100, "Ambiguous traffic percentage in service status")
    return percent


def traffic_entries(service: dict) -> list[dict]:
    traffic = (service.get("status") or {}).get("traffic")
    require(isinstance(traffic, list) and all(isinstance(e, dict) for e in traffic),
            "Service status has no traffic list")
    # Validate every entry before any is filtered out, so a malformed serving
    # percentage cannot disappear with the untagged 0% entries.
    for entry in traffic:
        traffic_percent(entry)
    return traffic


def serving_revision(service: dict) -> str:
    serving = [e for e in traffic_entries(service) if traffic_percent(e) == 100]
    require(len(serving) == 1 and bool(serving[0].get("revisionName")),
            "Service has no single 100%-serving revision")
    return str(serving[0]["revisionName"])


def addressable_revisions(service: dict) -> dict[str, dict]:
    """Every revision that can receive a request: serving traffic or tagged."""
    out: dict[str, dict] = {}
    for entry in traffic_entries(service):
        name = str(entry.get("revisionName") or "")
        if not name:
            continue
        percent = traffic_percent(entry)
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


COHORT_KEYS = {"SCAN_PIPELINE_MODE", "SCAN_STAGED_OWNER_IDS"}


def check_activation_candidate(service: dict, revisions: dict[str, dict], staged_revision: str,
                               expected_source: str) -> dict[str, str]:
    """The one revision that will receive stage tasks must be exactly configured."""
    require(bool(REVISION_RE.fullmatch(staged_revision)), "STAGED_REVISION must be an exact worker revision name")
    require(bool(SHA_RE.fullmatch(expected_source)), "An exact expected worker source SHA is required")
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
    require(source == expected_source,
            f"STAGED_REVISION was built from {source}, not the confirmed source {expected_source}")
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
    # The reviewed inactive build stamps a digest over its exact staged
    # environment. Recompute it here rather than trusting the stamp, and
    # require every non-cohort value to still equal that reviewed build.
    reviewed = inactive_environment(source, PROJECT, REGION, WORKSPACE_BUCKET, STAGE_QUEUE_PATH, origin)
    require(env.get("FIXLIST_STAGED_CONFIG_SHA256") == digest_for(source, reviewed),
            "STAGED_REVISION configuration digest does not match the reviewed inactive build")
    drift = sorted(key for key in reviewed if key not in COHORT_KEYS and env.get(key) != reviewed[key])
    require(not drift, f"STAGED_REVISION staged configuration drifted from its reviewed build: {','.join(drift)}")
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


BARRIER_LINE = re.compile(
    r"ADMISSION_BARRIER_STATUS mode=(open|closed|acceptance_only) generation=([0-9]+) drain_ready=(true|false) "
    r"active=([0-9]+) bound=([0-9]+) expired_diagnostic=([0-9]+) live_reconciliation=([0-9]+) snapshot=(\S+)\Z")


def check_barrier(output: str, expected_generation: str, require_drained: bool) -> str:
    """Read the coordinator's signed status line (verified by the operator script).

    Closed means no new claim can be admitted anywhere, Base44 included. Zero
    active/bound/live obligations means every admitted scan reached a terminal
    state: the coordinator releases an admission only with a terminal status.
    """
    lines = [line for line in output.splitlines() if line.startswith("ADMISSION_BARRIER_STATUS ")]
    require(len(lines) == 1, "No single signed admission barrier status was returned")
    match = BARRIER_LINE.fullmatch(lines[0].strip())
    require(match is not None, "Admission barrier status line is malformed")
    mode, generation, ready, active, bound, _expired, live, snapshot = match.groups()
    require(generation == expected_generation, "Admission barrier generation changed")
    require(mode == "closed", f"Admission barrier is {mode}; new admissions are still possible")
    if require_drained:
        require(ready == "true" and active == "0" and bound == "0" and live == "0",
                "Admitted scans are not all terminal (active/bound/live obligations remain)")
    return f"generation={generation} snapshot={snapshot} active={active} bound={bound} live={live}"


TAG_HOST_RE = re.compile(r"staged-([0-9a-f]{12})---([a-z0-9.-]+)\Z")
TASK_LIST_LIMIT = 1000


def check_recoverable_tasks(service: dict, revisions: dict[str, dict], listing: list,
                            tasks: list[dict]) -> dict[str, int]:
    """Every pending task must carry a delivery identity the worker would accept.

    Each task is checked against its OWN pinned, still-addressable source tag,
    not today's candidate: a stranded scan may belong to an earlier verified
    tag. The predicate is the existing verifier's validate_task.
    """
    from verify_staged_scan_infra import VerificationError, validate_task

    names = task_names(listing)
    require(len(names) < TASK_LIST_LIMIT, "Task inventory may be truncated; refuse to recover blind")
    described = [str((task or {}).get("name") or "") for task in tasks]
    require(sorted(described) == sorted(names) and len(set(names)) == len(names),
            "Task details do not match the complete task inventory")
    origin = canonical_origin(service)
    host = urlsplit(origin).hostname
    by_tag: dict[str, tuple[str, str]] = {}
    for revision_name, slot in addressable_revisions(service).items():
        for tag, url in slot["tags"].items():
            by_tag[tag] = (revision_name, url)
    counts: dict[str, int] = {}
    for task in tasks:
        name = task["name"]
        url = urlsplit(str(((task.get("httpRequest") or {}).get("url")) or ""))
        match = TAG_HOST_RE.fullmatch(url.hostname or "")
        require(url.scheme == "https" and match is not None and match[2] == host,
                f"Task {name} does not target a source-tagged revision of the worker")
        tag = f"staged-{match[1]}"
        require(tag in by_tag, f"Task {name} targets {tag}, which is no longer an addressable tag")
        revision_name, tag_url = by_tag[tag]
        require(tag_url == f"https://{url.hostname}", f"Task {name} tag {tag} resolves to another URL")
        revision = revisions.get(revision_name)
        require(revision is not None, f"Missing revision readback for {revision_name}")
        require(((revision.get("spec") or {}).get("serviceAccountName")) == WORKER_SA,
                f"Tagged revision {revision_name} runs as an unexpected service account")
        source = revision_env(revision).get("FIXLIST_WORKER_SOURCE_SHA", "")
        require(bool(SHA_RE.fullmatch(source)) and source.startswith(match[1]),
                f"Tagged revision {revision_name} was not built from the source its tag names")
        try:
            validate_task(task, tag_url, INVOKER_SA, origin)
        except VerificationError as exc:
            raise GuardError(f"Task {name}: {exc}") from exc
        counts[tag] = counts.get(tag, 0) + 1
    return counts


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
    elif command == "serving":
        print(serving_revision(_load(rest[0])))
    elif command == "addressable":
        print("\n".join(sorted(addressable_revisions(_load(rest[0])))))
    elif command == "intake-disabled":
        service, gateway, *revision_paths = rest
        revisions = {r.get("metadata", {}).get("name"): r for r in map(_load, revision_paths)}
        gateway_env = revision_env(_load(gateway)) if gateway != "-" else {}
        names = check_intake_disabled(_load(service), revisions, gateway_env)
        print(f"STAGED_INTAKE_DISABLED revisions={','.join(names)}")
    elif command == "activation":
        service, staged_revision, expected_source, *revision_paths = rest
        revisions = {r.get("metadata", {}).get("name"): r for r in map(_load, revision_paths)}
        found = check_activation_candidate(_load(service), revisions, staged_revision, expected_source)
        print(" ".join(f"{key}={value}" for key, value in found.items()))
    elif command == "barrier":
        output_path, expected_generation, mode = rest
        require(mode in {"drained", "closed"}, "Barrier mode must be drained or closed")
        with open(output_path, encoding="utf-8") as handle:
            print(check_barrier(handle.read(), expected_generation, mode == "drained"))
    elif command == "recover-tasks":
        service, listing, task_dir, *revision_paths = rest
        revisions = {r.get("metadata", {}).get("name"): r for r in map(_load, revision_paths)}
        from pathlib import Path
        tasks = [_load(str(path)) for path in sorted(Path(task_dir).glob("*.json"))]
        counts = check_recoverable_tasks(_load(service), revisions, _load(listing), tasks)
        summary = ",".join(f"{tag}:{n}" for tag, n in sorted(counts.items())) or "none"
        print(f"verified={sum(counts.values())} tags={summary}")
    elif command == "first-tag-url":
        # The tag URL of the listing's first task, which status/recover hand to
        # the infrastructure verifier together with that same task.
        service, listing, task_dir = rest
        from pathlib import Path
        names = task_names(_load(listing))
        tasks = {t.get("name"): t for t in (_load(str(p)) for p in Path(task_dir).glob("*.json"))}
        if names:
            url = str(((tasks[names[0]].get("httpRequest") or {}).get("url")) or "")
            print(url.rsplit("/", 1)[0])
        else:
            print(canonical_origin(_load(service)))
    elif command == "names":
        print("\n".join(task_names(_load(rest[0]))))
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
