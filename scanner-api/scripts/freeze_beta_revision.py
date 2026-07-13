#!/usr/bin/env python3
"""Record — or verify — the frozen beta crawler revision.

Phase 1 "tag or record the frozen beta revision". The record lives at
``data/beta-crawler-revision.json`` and captures the git commit plus the exact
scanner/review version constants the frozen beta promises.

Record / update the freeze after acceptance passes::

    python scripts/freeze_beta_revision.py \\
        --git-commit "$(git rev-parse HEAD)" \\
        --acceptance-report docs/beta-acceptance.md \\
        --note "frozen after Shopify/Signal/Basecamp acceptance"

Verify the running code still matches the recorded freeze (drift gate; exits
non-zero on mismatch, suitable for CI or a deploy check)::

    python scripts/freeze_beta_revision.py --check
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCANNER_API_ROOT = Path(__file__).resolve().parents[1]
if str(SCANNER_API_ROOT) not in sys.path:
    sys.path.insert(0, str(SCANNER_API_ROOT))

from app.beta_revision import (  # noqa: E402
    DEFAULT_REVISION_PATH,
    build_revision_record,
    diff_versions,
    live_revision,
    load_recorded_revision,
)


def _write_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def cmd_record(args: argparse.Namespace) -> int:
    recorded_at = args.recorded_at or datetime.now(timezone.utc).isoformat()
    record = build_revision_record(
        git_commit=args.git_commit,
        recorded_at=recorded_at,
        acceptance_report=args.acceptance_report,
        note=args.note,
    )
    _write_record(args.path, record)
    sys.stdout.write(
        f"Recorded beta revision fingerprint {record['fingerprint']} "
        f"(commit {record['git_commit'] or 'unset'}) to {args.path}\n"
    )
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    try:
        recorded = load_recorded_revision(args.path)
    except FileNotFoundError:
        sys.stderr.write(f"No recorded revision at {args.path}; run without --check to create one.\n")
        return 2

    live = live_revision()
    drift = diff_versions(recorded, live)
    if not drift:
        sys.stdout.write(
            f"OK: live code matches frozen beta revision {recorded.get('fingerprint')} "
            f"(commit {recorded.get('git_commit') or 'unset'}).\n"
        )
        return 0

    sys.stderr.write("DRIFT: live code no longer matches the frozen beta revision.\n")
    sys.stderr.write(f"  recorded fingerprint: {recorded.get('fingerprint')}\n")
    sys.stderr.write(f"  live fingerprint:     {live['fingerprint']}\n")
    for component, values in drift.items():
        sys.stderr.write(f"  - {component}: recorded={values['recorded']!r} live={values['live']!r}\n")
    sys.stderr.write("Re-run acceptance and re-record the freeze, or revert the version change.\n")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=DEFAULT_REVISION_PATH)
    parser.add_argument("--check", action="store_true", help="Verify live code matches the recorded freeze.")
    parser.add_argument("--git-commit", default="", help="Commit SHA of the frozen revision.")
    parser.add_argument("--acceptance-report", default="", help="Path to the acceptance report backing this freeze.")
    parser.add_argument("--recorded-at", default="", help="Override the recorded timestamp (defaults to now, UTC).")
    parser.add_argument("--note", default="", help="Free-text note about this freeze.")
    args = parser.parse_args()

    return cmd_check(args) if args.check else cmd_record(args)


if __name__ == "__main__":
    raise SystemExit(main())
