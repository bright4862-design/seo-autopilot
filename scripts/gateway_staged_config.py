#!/usr/bin/env python3
"""Plan bounded gateway staging inputs without reading or mutating cloud state."""
import argparse
import hashlib
import json
import re


def owners(value):
    if not value:
        return []
    items = value.split(",")
    if (not 1 <= len(items) <= 5 or len(items) != len(set(items))
            or any(not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", item) for item in items)):
        raise ValueError("staging requires 1-5 distinct exact owner IDs")
    return sorted(items)


def plan(config, owner_ids, canary_owner_ids, pilot_owner_ids=""):
    rollout_scope = "off"
    entitled_500 = config == "paid-500"
    pilot = owners(pilot_owner_ids)
    if bool(pilot) != (config == "paid-pilot-500"):
        raise ValueError("paid-pilot-500 requires its own nonempty pilot cohort; other configurations cannot carry one")
    if config == "off":
        if owner_ids:
            raise ValueError("off staging cannot carry an owner cohort")
        mode, selected = "monolith", []
    elif config == "owner-canary":
        selected = owners(owner_ids)
        if not selected or selected != owners(canary_owner_ids):
            raise ValueError("staged owners must exactly match the verified canary route")
        mode = "staged"
    elif config in {"paid", "paid-500", "paid-pilot-500"}:
        if owner_ids or canary_owner_ids:
            raise ValueError("paid staging requires the canonical worker and an empty owner cohort")
        mode, selected, rollout_scope = "staged", [], "paid"
    else:
        raise ValueError("staging config must be off, owner-canary, paid, paid-500 or paid-pilot-500")
    digest = hashlib.sha256(json.dumps(selected, separators=(",", ":")).encode()).hexdigest()
    pilot_digest = hashlib.sha256(json.dumps(pilot, separators=(",", ":")).encode()).hexdigest()
    return {"pipeline_mode": mode, "staged_rollout_scope": rollout_scope,
            "staged_500_entitled_enabled": entitled_500,
            "owner_ids": ",".join(selected),
            "pilot_owner_ids": ",".join(pilot), "staged_pilot_owner_count": len(pilot),
            "staged_pilot_owner_cohort_sha256": pilot_digest,
            "staged_owner_count": len(selected), "staged_owner_cohort_sha256": digest}


def verify_activation_baseline(previous, source_sha, planned):
    """Allow exact-source zero-owner staging and a separately held paid pilot.

    Publication still requires the closed, drained coordinator and queues.
    A named pilot may be added to paid 150 or removed back to paid 150; changing
    one active named cohort into another first requires that empty baseline.
    """
    empty_hash = hashlib.sha256(b"[]").hexdigest()
    allowed = {("monolith", "off")}
    if planned["staged_rollout_scope"] == "paid":
        allowed.add(("staged", "paid"))
    if (previous.get("source_sha") != source_sha
            or (previous.get("pipeline_mode"), previous.get("staged_rollout_scope", "off")) not in allowed
            or type(previous.get("staged_owner_count")) is not int or previous["staged_owner_count"] != 0
            or previous.get("staged_owner_cohort_sha256") != empty_hash
            or (planned["staged_rollout_scope"] == "paid"
                and (type(previous.get("canary_owner_count")) is not int
                     or previous["canary_owner_count"] != 0 or previous.get("canary_worker_origin")))):
        raise ValueError("Staging requires a freshly verified same-source zero-owner gateway baseline")
    count = previous.get("staged_pilot_owner_count", 0)
    digest = previous.get("staged_pilot_owner_cohort_sha256", empty_hash)
    if (type(count) is not int or not 0 <= count <= 5
            or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)
            or (count == 0 and digest != empty_hash)):
        raise ValueError("Previous gateway pilot cohort is unverified")
    if planned["staged_pilot_owner_count"]:
        if (previous.get("staged_500_entitled_enabled") is not False
                or "staged_pilot_owner_count" not in previous or "staged_pilot_owner_cohort_sha256" not in previous
                or (count and (count != planned["staged_pilot_owner_count"]
                               or digest != planned["staged_pilot_owner_cohort_sha256"]))):
            raise ValueError("Named pilot requires a verified paid-150 baseline or the same exact pilot cohort")
    if count and planned["staged_500_entitled_enabled"]:
        raise ValueError("Remove the named pilot to a verified paid-150 baseline before broad 500 activation")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="off")
    parser.add_argument("--owners", default="")
    parser.add_argument("--canary-owners", default="")
    parser.add_argument("--pilot-owners", default="")
    args = parser.parse_args()
    try:
        result = plan(args.config, args.owners, args.canary_owners, args.pilot_owners)
    except ValueError as error:
        parser.exit(2, f"Refusing gateway staging: {error}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
