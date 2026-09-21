from app.stage2_local_shell_evidence import LOCAL_SHELL_VERSION, assess_local_shell


def _observation(*, issue_types, status=None, **extra):
    return {
        "applicable": True,
        "accepted": True,
        "page_evidence_class": "usable_html",
        "contextual_status": status,
        "visible_template_evidence": {
            "accepted": True,
            "issue_types": issue_types,
        },
        **extra,
    }


def test_preopening_coming_soon_shell_is_context_not_a_defect():
    result = assess_local_shell(_observation(issue_types=["coming_soon_shell"], status="Coming Soon"))
    assert result["version"] == LOCAL_SHELL_VERSION
    assert result["state"] == "pass"
    assert result["reason"] == "coming_soon_shell_matches_contextual_status"


def test_open_location_with_coming_soon_shell_is_a_contextual_failure():
    result = assess_local_shell(_observation(issue_types=["coming_soon_shell"], status="open"))
    assert result["state"] == "fail"
    assert result["reason"] == "coming_soon_shell_conflicts_with_open_status"


def test_coming_soon_shell_without_verified_status_stays_unknown():
    result = assess_local_shell(_observation(issue_types=["coming_soon_shell"]))
    assert result["state"] == "not_verified"
    assert result["reason"] == "coming_soon_shell_status_unverified"


def test_empty_local_shell_is_confirmed_only_on_accepted_html():
    result = assess_local_shell(_observation(issue_types=["empty_shell"], status="open"))
    assert result["state"] == "fail"
    assert result["reason"] == "empty_local_content_shell"


def test_failed_or_client_rendered_evidence_never_becomes_empty_shell_failure():
    failed = assess_local_shell(
        _observation(issue_types=["empty_shell"], status="open", rendering_failed=True)
    )
    suspected = assess_local_shell(
        _observation(issue_types=["empty_shell"], status="open", client_rendering_suspected=True)
    )
    assert failed["state"] == "not_verified"
    assert suspected["state"] == "not_verified"
    assert failed["shell_issue_types"] == []
    assert suspected["shell_issue_types"] == []


def test_nonlocal_and_unknown_applicability_do_not_create_local_defects():
    assert assess_local_shell({"applicable": False})["state"] == "not_applicable"
    assert assess_local_shell({})["state"] == "not_verified"
