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


def plan(config, owner_ids, canary_owner_ids):
    if config == "off":
        if owner_ids:
            raise ValueError("off staging cannot carry an owner cohort")
        mode, selected = "monolith", []
    elif config == "owner-canary":
        selected = owners(owner_ids)
        if not selected or selected != owners(canary_owner_ids):
            raise ValueError("staged owners must exactly match the verified canary route")
        mode = "staged"
    else:
        raise ValueError("staging config must be off or owner-canary")
    digest = hashlib.sha256(json.dumps(selected, separators=(",", ":")).encode()).hexdigest()
    return {"pipeline_mode": mode, "owner_ids": ",".join(selected),
            "staged_owner_count": len(selected), "staged_owner_cohort_sha256": digest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="off")
    parser.add_argument("--owners", default="")
    parser.add_argument("--canary-owners", default="")
    args = parser.parse_args()
    try:
        result = plan(args.config, args.owners, args.canary_owners)
    except ValueError as error:
        parser.exit(2, f"Refusing gateway staging: {error}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
