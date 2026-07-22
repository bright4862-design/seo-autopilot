from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FINGERPRINT = "a375c7d739ba9adc"

REPLACEMENTS = {
    ROOT / "scanner-api/tests/test_observability.py": {
        "d69d625dbeaee154": FINGERPRINT,
        "artifact_filter_v3_non_html_resources": "artifact_filter_v4_wordpress_route_noise",
    },
    ROOT / "src/lib/scanRunModel.js": {
        "d69d625dbeaee154": FINGERPRINT,
    },
    ROOT / "tests/frontend/releaseAuthorityGate.test.mjs": {
        "d69d625dbeaee154": FINGERPRINT,
    },
    ROOT / "tests/frontend/scanRunPersistence.test.mjs": {
        "d69d625dbeaee154": FINGERPRINT,
    },
}

for path, replacements in REPLACEMENTS.items():
    text = path.read_text(encoding="utf-8")
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"Expected marker {old!r} missing from {path}")
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")

print(f"Updated release-authority markers to {FINGERPRINT}")
