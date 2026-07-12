from app.scanner import RENDER_EVIDENCE_VERSION, build_render_evidence


def _page(path, *, suspected=False, status=200, error=""):
    return {
        "path": path,
        "status_code": status,
        "fetch_error": error,
        "client_rendering_suspected": suspected,
    }


def test_render_evidence_reports_material_app_shell_risk():
    pages = [
        _page("/app-a", suspected=True),
        _page("/app-b", suspected=True),
        _page("/content"),
        _page("/not-found", suspected=True, status=404),
    ]

    evidence = build_render_evidence(pages)

    assert evidence == {
        "version": RENDER_EVIDENCE_VERSION,
        "pages_evaluated": 3,
        "client_rendering_suspected_pages": 2,
        "suspected_ratio": 0.6667,
        "evidence_state": "material_client_rendering_risk",
        "rendering_mode": "browser_follow_up_recommended",
        "representative_pages": ["/app-a", "/app-b"],
    }


def test_render_evidence_keeps_isolated_signal_bounded():
    pages = [_page("/app", suspected=True)] + [
        _page(f"/content-{index}") for index in range(9)
    ]

    evidence = build_render_evidence(pages)

    assert evidence["pages_evaluated"] == 10
    assert evidence["client_rendering_suspected_pages"] == 1
    assert evidence["suspected_ratio"] == 0.1
    assert evidence["evidence_state"] == "isolated_client_rendering_signal"
    assert evidence["rendering_mode"] == "raw_html_first"


def test_render_evidence_ignores_failed_pages():
    pages = [
        _page("/rate-limited", suspected=True, status=429),
        _page("/blocked", suspected=True, status=0, error="timeout"),
        _page("/content"),
    ]

    evidence = build_render_evidence(pages)

    assert evidence["pages_evaluated"] == 1
    assert evidence["client_rendering_suspected_pages"] == 0
    assert evidence["evidence_state"] == "raw_html_sufficient"
    assert evidence["representative_pages"] == []
