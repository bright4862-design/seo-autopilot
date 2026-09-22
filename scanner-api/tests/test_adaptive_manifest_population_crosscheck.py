from copy import deepcopy
import hashlib
import json

from app.adaptive_manifest_population_crosscheck import (
    ADAPTIVE_MANIFEST_POPULATION_CROSSCHECK_INTEGRITY_VERSION,
    ADAPTIVE_MANIFEST_POPULATION_CROSSCHECK_VERSION,
    build_manifest_population_crosscheck,
    validate_manifest_population_crosscheck,
)


def manifest_fp(urls):
    return hashlib.sha256(
        json.dumps(list(urls), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def marginal_fp(urls):
    digest = hashlib.sha256()
    digest.update(b"adaptive_marginal_population_v1\0")
    for url in urls:
        digest.update(url.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def benchmark_fp(role, urls):
    return hashlib.sha256(
        json.dumps(
            {
                "version": "adaptive_benchmark_population_v1",
                "role": role,
                "urls": tuple(urls),
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def urls(count):
    return [f"https://example.test/section-{i % 11}/page-{i}" for i in range(count)]


def selected_population(unique_urls, target, *, variant="a"):
    bound = min(target, len(unique_urls))
    base = list(unique_urls[: min(150, bound)])
    if bound <= len(base):
        return tuple(base)
    remainder = list(unique_urls[len(base) : bound])
    if variant == "b":
        remainder.reverse()
    return tuple(base + remainder)


def tranche_targets(count):
    if count <= 0:
        return ()
    if count < 150:
        return (count,)
    result = [150]
    if count < 500:
        result.append(count)
    else:
        result.append(500)
        if count < 1000:
            result.append(count)
        else:
            result.append(1000)
    return tuple(dict.fromkeys(result))


def role(target, count):
    if target <= 150:
        return "standard_reference"
    if target == 500:
        return "smart_500_candidate"
    if target == 1000:
        return "blind_1000_reference"
    if target == count and count < 1000:
        return "inventory_bound"
    return "adaptive_intermediate"


def sources(count=1100, *, duplicate_count=0, variant="a"):
    unique = urls(count)
    raw = list(unique) + ([unique[-1]] * duplicate_count if unique else [])
    targets = tranche_targets(count)
    tranches = []
    for target in targets:
        selected = selected_population(unique, target, variant=variant)
        tranches.append(
            {
                "target": target,
                "role": role(target, count),
                "selected_count": len(selected),
                "selected_urls": selected,
                "selected_population_fingerprint": manifest_fp(selected),
            }
        )

    def population_for(checkpoint):
        for row in tranches:
            if row["target"] == checkpoint:
                return row
        assert count < checkpoint
        return tranches[-1]

    standard = population_for(150)
    smart = population_for(500)
    p1000 = population_for(1000)
    input_fp = manifest_fp(raw)
    manifest = {
        "version": "adaptive_tranche_selection_manifest_v1",
        "discovered_input_count": len(raw),
        "unique_discovered_count": count,
        "input_population_fingerprint": input_fp,
        "selection_targets": targets,
        "standard_reference_population_fingerprint": manifest_fp(
            standard["selected_urls"]
        ),
        "tranches": tuple(tranches),
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
    integrity = {
        "version": "adaptive_tranche_selection_manifest_integrity_v1",
        "valid": True,
        "input_population_fingerprint": input_fp,
        "selection_targets": targets,
        "standard_reference_population_fingerprint": manifest[
            "standard_reference_population_fingerprint"
        ],
    }

    marginal_rows = []
    for checkpoint, row in ((150, standard), (500, smart), (1000, p1000)):
        selected = row["selected_urls"]
        marginal_rows.append(
            {
                "checkpoint": checkpoint,
                "manifest_target": row["target"],
                "manifest_role": row["role"],
                "pages_assessed": len(selected),
                "population_fingerprint": marginal_fp(selected),
                "inventory_limited": len(selected) < checkpoint,
            }
        )
    marginal = {
        "version": "adaptive_manifest_marginal_binding_v1",
        "valid": True,
        "candidate_count": count,
        "input_population_fingerprint": input_fp,
        "selection_targets": targets,
        "bindings": tuple(marginal_rows),
        "binding_fingerprint": "b" * 64,
        "standard_150_preserved": True,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }

    smart_selected = smart["selected_urls"]
    blind_selected = tuple(unique[: min(1000, count)])
    benchmark = {
        "version": "adaptive_manifest_benchmark_binding_v1",
        "valid": True,
        "candidate_urls_supplied": len(raw),
        "candidate_urls_unique": count,
        "duplicate_candidate_identities_removed": duplicate_count,
        "manifest_input_population_fingerprint": input_fp,
        "manifest_smart_target": smart["target"],
        "standard_manifest_target": standard["target"],
        "smart_pages": len(smart_selected),
        "blind_pages": len(blind_selected),
        "smart_population_sha256": benchmark_fp("smart_500", smart_selected),
        "blind_population_sha256": benchmark_fp("blind_1000", blind_selected),
        "binding_fingerprint": "c" * 64,
        "standard_150_preserved": True,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
    return raw, manifest, integrity, marginal, benchmark


def test_full_1100_population_crosschecks_exact_smart_and_blind_populations():
    raw, manifest, integrity, marginal, benchmark = sources(1100)
    artifact = build_manifest_population_crosscheck(
        manifest, marginal, benchmark, raw, manifest_integrity=integrity
    )
    assert artifact["version"] == ADAPTIVE_MANIFEST_POPULATION_CROSSCHECK_VERSION
    assert artifact["valid"] is True
    assert artifact["standard_150_pages"] == 150
    assert artifact["smart_500_pages"] == 500
    assert artifact["blind_1000_pages"] == 1000
    assert artifact["standard_150_preserved"] is True


def test_inventory_limited_620_crosschecks_terminal_1000_checkpoint():
    raw, manifest, integrity, marginal, benchmark = sources(620)
    artifact = build_manifest_population_crosscheck(
        manifest, marginal, benchmark, raw, manifest_integrity=integrity
    )
    assert artifact["valid"] is True
    assert artifact["smart_500_pages"] == 500
    assert artifact["blind_1000_pages"] == 620
    assert artifact["manifest_population_fingerprints"][-1][0] == 1000


def test_sub_500_population_uses_exact_terminal_smart_population():
    raw, manifest, integrity, marginal, benchmark = sources(320)
    artifact = build_manifest_population_crosscheck(
        manifest, marginal, benchmark, raw, manifest_integrity=integrity
    )
    assert artifact["valid"] is True
    assert artifact["smart_500_pages"] == 320
    assert artifact["blind_1000_pages"] == 320


def test_sub_150_population_preserves_terminal_standard_population():
    raw, manifest, integrity, marginal, benchmark = sources(83)
    artifact = build_manifest_population_crosscheck(
        manifest, marginal, benchmark, raw, manifest_integrity=integrity
    )
    assert artifact["valid"] is True
    assert artifact["standard_150_pages"] == 83
    assert artifact["smart_500_pages"] == 83


def test_duplicate_transport_geometry_is_preserved_exactly():
    raw, manifest, integrity, marginal, benchmark = sources(620, duplicate_count=7)
    artifact = build_manifest_population_crosscheck(
        manifest, marginal, benchmark, raw, manifest_integrity=integrity
    )
    assert artifact["valid"] is True
    assert artifact["candidate_urls_supplied"] == 627
    assert artifact["candidate_urls_unique"] == 620
    assert artifact["duplicate_candidate_identities_removed"] == 7


def test_same_discovery_but_different_smart_manifest_rejects_benchmark_transplant():
    raw, manifest_a, integrity_a, marginal_a, _ = sources(1100, variant="a")
    _, _, _, _, benchmark_b = sources(1100, variant="b")
    artifact = build_manifest_population_crosscheck(
        manifest_a, marginal_a, benchmark_b, raw, manifest_integrity=integrity_a
    )
    assert artifact["valid"] is False
    assert artifact["reason"] == "benchmark_smart_500_population_mismatch"


def test_same_discovery_but_different_smart_manifest_rejects_marginal_transplant():
    raw, manifest_a, integrity_a, _, benchmark_a = sources(1100, variant="a")
    _, _, _, marginal_b, _ = sources(1100, variant="b")
    artifact = build_manifest_population_crosscheck(
        manifest_a, marginal_b, benchmark_a, raw, manifest_integrity=integrity_a
    )
    assert artifact["valid"] is False
    assert artifact["reason"] == "marginal_binding_checkpoint_500_population_mismatch"


def test_blind_reference_hash_must_match_exact_fifo_unique_population():
    raw, manifest, integrity, marginal, benchmark = sources(620)
    benchmark["blind_population_sha256"] = "d" * 64
    artifact = build_manifest_population_crosscheck(
        manifest, marginal, benchmark, raw, manifest_integrity=integrity
    )
    assert artifact["valid"] is False
    assert artifact["reason"] == "benchmark_blind_1000_population_mismatch"


def test_discovery_order_drift_is_rejected():
    raw, manifest, integrity, marginal, benchmark = sources(620)
    raw[0], raw[1] = raw[1], raw[0]
    artifact = build_manifest_population_crosscheck(
        manifest, marginal, benchmark, raw, manifest_integrity=integrity
    )
    assert artifact["valid"] is False
    assert artifact["reason"] == "manifest_input_population_mismatch"


def test_manifest_replay_identity_mismatch_fails_closed():
    raw, manifest, integrity, marginal, benchmark = sources(620)
    integrity["input_population_fingerprint"] = "0" * 64
    artifact = build_manifest_population_crosscheck(
        manifest, marginal, benchmark, raw, manifest_integrity=integrity
    )
    assert artifact["valid"] is False
    assert artifact["reason"] == "manifest_integrity_input_population_fingerprint_mismatch"


def test_manifest_selected_population_fingerprint_must_reconcile():
    raw, manifest, integrity, marginal, benchmark = sources(620)
    tranches = list(manifest["tranches"])
    tranches[1] = dict(tranches[1])
    tranches[1]["selected_population_fingerprint"] = "0" * 64
    manifest["tranches"] = tuple(tranches)
    artifact = build_manifest_population_crosscheck(
        manifest, marginal, benchmark, raw, manifest_integrity=integrity
    )
    assert artifact["valid"] is False
    assert artifact["reason"] == "manifest_checkpoint_500_fingerprint_mismatch"


def test_forbidden_authority_claim_on_any_source_fails_closed():
    raw, manifest, integrity, marginal, benchmark = sources(620)
    marginal["production_budget_authorized"] = True
    artifact = build_manifest_population_crosscheck(
        manifest, marginal, benchmark, raw, manifest_integrity=integrity
    )
    assert artifact["valid"] is False
    assert artifact["reason"] == "marginal_binding_forbidden_authority_claim"

    raw, manifest, integrity, marginal, benchmark = sources(620)
    benchmark["site_fully_understood"] = True
    artifact = build_manifest_population_crosscheck(
        manifest, marginal, benchmark, raw, manifest_integrity=integrity
    )
    assert artifact["valid"] is False
    assert artifact["reason"] == "benchmark_binding_forbidden_authority_claim"


def test_binding_fingerprints_must_be_canonical_sha256():
    raw, manifest, integrity, marginal, benchmark = sources(620)
    marginal["binding_fingerprint"] = "B" * 64
    artifact = build_manifest_population_crosscheck(
        manifest, marginal, benchmark, raw, manifest_integrity=integrity
    )
    assert artifact["valid"] is False
    assert artifact["reason"] == "marginal_binding_fingerprint_invalid"


def test_duplicate_or_missing_marginal_checkpoint_is_rejected():
    raw, manifest, integrity, marginal, benchmark = sources(620)
    rows = list(marginal["bindings"])
    rows[-1] = deepcopy(rows[1])
    marginal["bindings"] = tuple(rows)
    artifact = build_manifest_population_crosscheck(
        manifest, marginal, benchmark, raw, manifest_integrity=integrity
    )
    assert artifact["valid"] is False
    assert artifact["reason"] == "marginal_binding_checkpoint_identity_invalid"


def test_json_transport_validates_and_tampering_is_rejected():
    raw, manifest, integrity, marginal, benchmark = sources(1100)
    artifact = build_manifest_population_crosscheck(
        manifest, marginal, benchmark, raw, manifest_integrity=integrity
    )
    transported = json.loads(json.dumps(artifact))
    accepted = validate_manifest_population_crosscheck(
        transported,
        manifest,
        marginal,
        benchmark,
        raw,
        manifest_integrity=integrity,
    )
    assert accepted["version"] == ADAPTIVE_MANIFEST_POPULATION_CROSSCHECK_INTEGRITY_VERSION
    assert accepted["valid"] is True

    transported["smart_500_pages"] = 499
    rejected = validate_manifest_population_crosscheck(
        transported,
        manifest,
        marginal,
        benchmark,
        raw,
        manifest_integrity=integrity,
    )
    assert rejected["valid"] is False
    assert rejected["reason"] == "artifact_mismatch"


def test_crosscheck_is_deterministic_shadow_only_and_does_not_mutate_inputs():
    raw, manifest, integrity, marginal, benchmark = sources(1100)
    before = (
        deepcopy(raw),
        deepcopy(manifest),
        deepcopy(integrity),
        deepcopy(marginal),
        deepcopy(benchmark),
    )
    first = build_manifest_population_crosscheck(
        manifest, marginal, benchmark, raw, manifest_integrity=integrity
    )
    second = build_manifest_population_crosscheck(
        manifest, marginal, benchmark, raw, manifest_integrity=integrity
    )
    assert first == second
    assert (raw, manifest, integrity, marginal, benchmark) == before
    assert first["population_scope_complete"] is False
    assert first["production_budget_authorized"] is False
    assert first["site_fully_understood"] is False
