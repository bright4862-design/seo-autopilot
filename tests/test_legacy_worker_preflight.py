import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
OPERATOR = ROOT / "scripts" / "fixlist-cloud-operator.sh"
CANONICAL_ORIGIN = "https://fixlist-standard150-worker-abc-uc.a.run.app"
CANDIDATE_ORIGIN = "https://candidate---fixlist-standard150-worker-abc-uc.a.run.app"
SERVING_REVISION = "fixlist-standard150-worker-00054-trs"
CANDIDATE_REVISION = "fixlist-standard150-worker-00055-jdd"
V8_RELEASE = {
    "fingerprint": "b36ca24b8e0f728e",
    "component_versions": {"review_version": "fixture-v8", "scanner_version": "fixture-v8"},
}


@pytest.mark.parametrize("compatible,fail_describe", [(True, 0), (False, 0), (True, 1), (True, 2)])
def test_legacy_preflight_probes_the_canonical_worker(tmp_path, compatible, fail_describe):
    baseline_data = tmp_path / "baseline" / "data"
    baseline_data.mkdir(parents=True)
    (baseline_data / "beta-crawler-revision.json").write_text(json.dumps(V8_RELEASE))

    service = {
        "status": {"url": CANONICAL_ORIGIN, "traffic": [
            {"revisionName": SERVING_REVISION, "percent": 100},
            {"revisionName": CANDIDATE_REVISION, "percent": 0, "tag": "candidate", "url": CANDIDATE_ORIGIN},
        ]},
    }
    live = {**V8_RELEASE, "source_sha": "b" * 40, "worker_revision": SERVING_REVISION}
    if not compatible:
        next_release = json.loads((ROOT / "data" / "beta-crawler-revision.json").read_text())
        live.update(fingerprint=next_release["fingerprint"], component_versions=next_release["component_versions"])
    (tmp_path / "service.json").write_text(json.dumps(service))
    (tmp_path / "worker.json").write_text(json.dumps(live))

    commands = {
        "gcloud": 'case "$1 $2 $3" in\n'
        '  "config set project") exit 0 ;;\n'
        '  "run services describe")\n'
        '    printf "describe\\n" >> "$FIXTURE/describes"\n'
        '    cat "$FIXTURE/service.json"\n'
        '    if [ "$(wc -l < "$FIXTURE/describes")" -eq "$FAIL_DESCRIBE" ]; then exit 2; fi ;;\n'
        '  *) exit 2 ;;\nesac\n',
        "curl": 'while [ "$1" != --output ]; do shift; done\n'
        'cp "$FIXTURE/worker.json" "$2"\n'
        'printf "%s\\n" "${@: -1}" >> "$FIXTURE/requests"\n'
        'printf 200\n',
    }
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, script in commands.items():
        executable = bin_dir / name
        executable.write_text(f"#!/usr/bin/env bash\nset -eu\n{script}")
        executable.chmod(0o755)

    definitions, dispatch, _ = OPERATOR.read_text().rpartition('\ncase "$OPERATION" in\n')
    assert dispatch
    harness = definitions + '\nREPO_ROOT="$PWD"\nverify_legacy_fallback_worker "$FIXTURE" || exit 1\n'
    result = subprocess.run(
        ["bash", "-c", harness, str(OPERATOR)], cwd=ROOT, capture_output=True, text=True, timeout=15,
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "FIXTURE": str(tmp_path),
             "OPERATION": "verify-worker-runtime-revision", "GCP_PROJECT": "test-project", "GCP_REGION": "test-region",
             "CLOUD_RUN_SERVICE": "fixlist-standard150-worker", "CLOUD_TASKS_QUEUE": "fixlist-standard150",
             "TASKS_INVOKER_SERVICE_ACCOUNT": "fixture@example.invalid", "TARGET_REVISION": CANDIDATE_REVISION,
             "FIXLIST_WORKER_ID_TOKEN": "fixture-only", "FIXLIST_WORKER_TOKEN_AUDIENCE": CANONICAL_ORIGIN,
             "FIXLIST_WORKER_PROBE_URL": CANDIDATE_ORIGIN, "FAIL_DESCRIBE": str(fail_describe)},
    )
    requests = tmp_path / "requests"
    if fail_describe == 1:
        assert not requests.exists()
    else:
        assert requests.read_text().splitlines() == [f"{CANONICAL_ORIGIN}/revision"]
        assert f"recorded fingerprint: {V8_RELEASE['fingerprint']}" in result.stdout
    assert len((tmp_path / "describes").read_text().splitlines()) == (1 if fail_describe == 1 or not compatible else 2)
    passed = compatible and not fail_describe
    assert result.returncode == (0 if passed else 1), result.stdout + result.stderr
    assert ("PASS: the running worker computes the release identity" in result.stdout) == passed
