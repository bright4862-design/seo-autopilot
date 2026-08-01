from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "scanner-api" / "deploy" / "premium-5000"
RUNBOOK = ROOT / "docs" / "runbooks" / "premium-5000-operations.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_review_manifest_is_disabled_isolated_and_single_concurrency() -> None:
    manifest = read(DEPLOY / "review-only-manifests.yaml")

    required = (
        'review.fixlist.ai/apply: "false"',
        'review.fixlist.ai/customer-ready: "false"',
        'standard150Unchanged: true',
        'separateService: true',
        'separateQueue: true',
        'containerConcurrency: 1',
        'maxInstances: 1',
        'PREMIUM_5000_ENABLED: "false"',
        'PREMIUM_5000_KILL_SWITCH: "true"',
        'PREMIUM_5000_GLOBAL_ACTIVE_LIMIT: "1"',
        'PREMIUM_5000_TENANT_ACTIVE_LIMIT: "1"',
        'maxConcurrentDispatches: 1',
        'state: PAUSED',
        'serviceName: seo-autopilot-premium-5000-worker',
    )
    for value in required:
        assert value in manifest

    proposed_bindings = manifest.split("proposedBindings:", 1)[1]
    proposed_bindings = proposed_bindings.split("reviewNotes:", 1)[0]
    prohibited = (
        "roles/owner",
        "roles/editor",
        "principal: allUsers",
        "principal: allAuthenticatedUsers",
    )
    for value in prohibited:
        assert value not in proposed_bindings


def test_runtime_dependencies_are_premium_only_and_exactly_pinned() -> None:
    requirements = read(DEPLOY / "runtime-requirements.txt")
    assert "Do not merge these pins into scanner-api/requirements.txt" in requirements
    assert "google-cloud-firestore==2.28.0" in requirements
    assert "google-cloud-tasks==2.23.0" in requirements
    assert "google-auth[requests]==2.56.2" in requirements


def test_observability_contract_redacts_secrets_and_sensitive_payloads() -> None:
    contract = read(DEPLOY / "observability-contract.yaml")
    for value in (
        "authorization",
        "cookie",
        "idempotency_key",
        "oidc_token",
        "raw_page_body",
        "url_query",
        "premium_stale_leases_total",
        "premium_cancellation_latency_seconds",
    ):
        assert value in contract


def test_runbook_preserves_release_gates_and_standard_isolation() -> None:
    runbook = read(RUNBOOK)
    for value in (
        "NOT READY TO ENABLE",
        "PREMIUM_5000_ENABLED=false",
        "PREMIUM_5000_KILL_SWITCH=true",
        "Standard 150 routes, cap, image, service and persistence contract remain unchanged",
        "no Meilleurtaux or other third-party crawl",
        "No benchmark is authorized by this runbook",
        "Infrastructure applied: no",
    ):
        assert value in runbook
