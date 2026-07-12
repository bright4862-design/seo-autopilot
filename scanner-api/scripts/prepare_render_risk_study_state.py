#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCANNER_API_ROOT = Path(__file__).resolve().parents[1]
if str(SCANNER_API_ROOT) not in sys.path:
    sys.path.insert(0, str(SCANNER_API_ROOT))

from app.render_study_state import prepare_render_study_state  # noqa: E402


def load_jsonl(path: Path, *, required: bool = True) -> list[dict]:
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return []
    records: list[dict] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: each line must contain an object")
        records.append(value)
    return records


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh renderer-study manual verdicts and prune insufficient cached evidence."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("successes", type=Path)
    parser.add_argument("failures", type=Path)
    args = parser.parse_args()

    try:
        manifest = load_jsonl(args.manifest)
        successes = load_jsonl(args.successes, required=False)
        failures = load_jsonl(args.failures, required=False)
        prepared_successes, prepared_failures, summary = prepare_render_study_state(
            manifest,
            successes,
            failures,
        )
        write_jsonl(args.successes, prepared_successes)
        write_jsonl(args.failures, prepared_failures)
    except (OSError, TypeError, ValueError) as exc:
        parser.error(str(exc))

    sys.stdout.write(json.dumps(summary, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
