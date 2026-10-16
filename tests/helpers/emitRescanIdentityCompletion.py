#!/usr/bin/env python3
"""Synthetic identity transport vectors using the real canonical producer/HMAC.

No network or stored customer data. The provisional vector deliberately omits
technical identity BEFORE canonicalization and signing, as historical producers
may do. The comparison mode uses the production comparator without stubs.
"""
import json
import sys

import emitStage3SignedCompletion as fixture
from app.repair_identity import compare_repair_runs

mode = sys.argv[1]
if mode == "compare":
    data = json.load(sys.stdin)
    print(json.dumps(compare_repair_runs(data["previous"], data["current"], data["pages"])))
elif mode in {"stable", "provisional"}:
    if mode == "provisional":
        original = fixture.fix

        def provisional_fix(*args, **kwargs):
            item = original(*args, **kwargs)
            item.pop("repair_surface")
            item.pop("remediation_family")
            return item

        fixture.fix = provisional_fix
    fixture.main()
else:
    raise SystemExit("expected stable, provisional or compare")
