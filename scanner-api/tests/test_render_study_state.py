from app.render_study_state import prepare_render_study_state


def _manifest(site, stratum="smb_cms", verdict="not_reviewed", notes=""):
    return {
        "site": site,
        "url": f"https://{site}.example.com",
        "stratum": stratum,
        "manual_js_disabled_verdict": verdict,
        "notes": notes,
    }


def _success(site, *, evaluated=10, crawled=10, state="raw_html_sufficient"):
    return {
        "site": site,
        "url": f"https://{site}.example.com",
        "stratum": "smb_cms",
        "manual_js_disabled_verdict": "not_reviewed",
        "notes": "",
        "pages_crawled": crawled,
        "pages_found": crawled,
        "render_evidence": {
            "pages_evaluated": evaluated,
            "client_rendering_suspected_pages": 2 if state == "material_client_rendering_risk" else 0,
            "evidence_state": state,
        },
    }


def test_preparation_syncs_manual_reviews_and_prunes_insufficient_cached_successes():
    manifest = [
        _manifest("valid", verdict="content_sufficient", notes="reviewed"),
        _manifest("zero"),
        _manifest("shallow"),
        _manifest("failed", stratum="saas_js"),
    ]
    successes = [
        _success("valid"),
        _success("zero", evaluated=0, crawled=2),
        _success("shallow", evaluated=1, crawled=22),
    ]
    failures = [
        {
            "site": "failed",
            "url": "https://old.example.com",
            "stratum": "smb_cms",
            "scan_status": "failed",
            "error": "HTTP 503",
        }
    ]

    prepared_successes, prepared_failures, summary = prepare_render_study_state(
        manifest,
        successes,
        failures,
    )

    assert [record["site"] for record in prepared_successes] == ["valid"]
    assert prepared_successes[0]["manual_js_disabled_verdict"] == "content_sufficient"
    assert prepared_successes[0]["notes"] == "reviewed"
    assert prepared_successes[0]["render_evidence_quality"]["sufficient"] is True
    assert [record["site"] for record in prepared_failures] == ["failed"]
    assert prepared_failures[0]["stratum"] == "saas_js"
    assert summary["removed_insufficient_sites"] == ["zero", "shallow"]
    assert summary["pending_sites"] == 2


def test_material_signal_is_retained_despite_shallow_coverage():
    manifest = [_manifest("material", stratum="saas_js")]
    successes = [
        {
            **_success(
                "material",
                evaluated=2,
                crawled=50,
                state="material_client_rendering_risk",
            ),
            "stratum": "saas_js",
        }
    ]

    prepared_successes, prepared_failures, summary = prepare_render_study_state(
        manifest,
        successes,
        [],
    )

    assert [record["site"] for record in prepared_successes] == ["material"]
    assert prepared_failures == []
    assert prepared_successes[0]["render_evidence_quality"]["sufficient"] is False
    assert summary["removed_insufficient_count"] == 0


def test_preparation_is_idempotent():
    manifest = [_manifest("valid", verdict="content_sufficient", notes="reviewed")]
    first_successes, first_failures, _ = prepare_render_study_state(
        manifest,
        [_success("valid")],
        [],
    )
    second_successes, second_failures, second_summary = prepare_render_study_state(
        manifest,
        first_successes,
        first_failures,
    )

    assert second_successes == first_successes
    assert second_failures == first_failures
    assert second_summary["manual_field_updates"] == 0
