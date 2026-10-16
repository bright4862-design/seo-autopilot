#!/usr/bin/env python3
"""Offline bridge: real Python completion -> V8 JS rows -> authority adapter."""
import json
import sys

import emitStage3SignedCompletion as fixture

data = json.load(sys.stdin)
action = data.pop("action")
if action == "emit":
    fixture.SCAN_ID = data["scan_id"]
    original = fixture.fix

    def source_fix(fix_id, *args, **kwargs):
        item = original(f"{fix_id}-{fixture.SCAN_ID}", *args, **kwargs)
        if data.get("mode") == "provisional":
            item.pop("repair_surface")
            item.pop("remediation_family")
        return item

    fixture.fix = source_fix
    fixture.main()
else:
    from app.scan_comparison_authority import (
        build_authenticated_scan_comparison_v1,
        build_scan_comparison_lineage_v1,
    )

    try:
        if action == "issue":
            result = build_scan_comparison_lineage_v1(**data)
        elif action == "compare":
            result = build_authenticated_scan_comparison_v1(**data)
        else:
            raise ValueError("unsupported fixture action")
        print(json.dumps({"ok": True, "result": result}))
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
