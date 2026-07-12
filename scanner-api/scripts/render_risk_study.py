#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCANNER_API_ROOT = Path(__file__).resolve().parents[1]
if str(SCANNER_API_ROOT) not in sys.path:
    sys.path.insert(0, str(SCANNER_API_ROOT))

from app.render_risk_study import format_markdown, summarize_records  # noqa: E402


def load_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc.msg}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: each line must contain a JSON object")
            records.append(value)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize the stratified FixList renderer-risk validation study."
    )
    parser.add_argument("input", type=Path, help="JSONL study record file")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output path; stdout is used when omitted",
    )
    args = parser.parse_args()

    try:
        summary = summarize_records(load_jsonl(args.input))
    except (OSError, TypeError, ValueError) as exc:
        parser.error(str(exc))

    output = (
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
        if args.format == "json"
        else format_markdown(summary) + "\n"
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
