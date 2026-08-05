from types import SimpleNamespace

import app_redesign
from app_redesign import (
    CSS,
    SCAN_MODE_CHOICES,
    STANDARD_SCAN_MODE,
    context_markup,
    run_workspace_scan_transitions,
    score_markup,
    site_markup,
)


def _live_scan(website: str, *, pages: int = 150) -> dict:
    return {
        "source": "live",
        "website": website,
        "score": 68,
        "pages_crawled": pages,
        "pages_retained": pages,
        "release_gate_eligible": True,
        "score_is_provisional": False,
    }


def _ignore_progress(*args, **kwargs) -> None:
    del args, kwargs


def test_empty_workspace_contains_no_demo_result():
    assert "Ready for a new scan" in site_markup({})
    assert "Your score will appear here" in score_markup({})
    assert "Run a scan to load context" in context_markup({})


def test_live_workspace_matches_one_page_result_contract():
    scan = {
        "source": "live",
        "website": "https://www.funbooker.com",
        "score": 68,
        "pages_crawled": 150,
        "release_gate_eligible": True,
        "score_is_provisional": False,
    }

    assert "www.funbooker.com" in site_markup(scan)
    assert "150 pages checked" in site_markup(scan)
    assert "Authoritative result" in site_markup(scan)
    assert "A solid foundation." in score_markup(scan)
    assert "--v:68" in score_markup(scan)
    assert "Scan context loaded" in context_markup(scan)


def test_single_page_workspace_uses_singular_label():
    assert "1 page checked" in site_markup(
        _live_scan("https://one.example", pages=1)
    )
    assert "1 pages" not in site_markup(
        _live_scan("https://one.example", pages=1)
    )


def test_scan_transition_clears_every_surface_before_authoritative_success(
    monkeypatch,
):
    captured: dict = {}
    scan = _live_scan("https://new.example")

    def fake_pipeline_ui(
        website_url,
        scan_mode,
        current_scan,
        history,
        progress,
    ):
        captured.update(
            website_url=website_url,
            scan_mode=scan_mode,
            current_scan=current_scan,
            history=history,
            progress=progress,
        )
        return (
            scan,
            "unused summary",
            "unused priority",
            "✅ **Scan complete** · 150 pages crawled · Authoritative",
            [{"role": "assistant", "content": "new scan context"}],
        )

    monkeypatch.setattr(app_redesign, "run_scan_pipeline_ui", fake_pipeline_ui)
    monkeypatch.setattr(
        app_redesign,
        "SETTINGS",
        SimpleNamespace(live_scan_enabled=True),
    )

    transitions = list(
        run_workspace_scan_transitions(
            "https://new.example",
            STANDARD_SCAN_MODE,
            _live_scan("https://old.example"),
            [{"role": "assistant", "content": "old Grok context"}],
            _ignore_progress,
        )
    )

    assert len(transitions) == 2
    reset, terminal = transitions
    assert reset[0] == {}
    assert "Ready for a new scan" in reset[1]
    assert "Your score will appear here" in reset[2]
    assert "Run a scan to load context" in reset[3]
    assert reset[5] == []
    assert reset[6] == {}
    assert reset[7] == ""
    assert reset[8]["interactive"] is False
    assert reset[8]["value"] == "Scanning…"
    assert "old.example" not in "".join(map(str, reset))
    assert "old Grok context" not in "".join(map(str, reset))

    assert captured["website_url"] == "https://new.example"
    assert captured["scan_mode"] == "advanced"
    assert captured["current_scan"] == {}
    assert captured["history"] == []
    assert terminal[0] == scan
    assert "new.example" in terminal[1]
    assert "Authoritative result" in terminal[1]
    assert "Scan context loaded" in terminal[3]
    assert terminal[5][0]["content"] == "new scan context"
    assert terminal[6] == scan
    assert terminal[7] == ""
    assert terminal[8]["interactive"] is True
    assert terminal[8]["value"] == "Run scan"


def test_scan_transition_failure_is_empty_and_reenables_submission(monkeypatch):
    def fail_workspace_scan(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("new.example failed")

    monkeypatch.setattr(app_redesign, "run_workspace_scan", fail_workspace_scan)
    monkeypatch.setattr(
        app_redesign,
        "SETTINGS",
        SimpleNamespace(live_scan_enabled=True),
    )

    reset, terminal = list(
        run_workspace_scan_transitions(
            "https://new.example",
            STANDARD_SCAN_MODE,
            _live_scan("https://old.example"),
            [{"role": "assistant", "content": "old answer"}],
            _ignore_progress,
        )
    )

    assert reset[8]["interactive"] is False
    assert terminal[0] == {}
    assert "Ready for a new scan" in terminal[1]
    assert "Your score will appear here" in terminal[2]
    assert "Run a scan to load context" in terminal[3]
    assert "new.example failed" in terminal[4]
    assert terminal[5] == []
    assert terminal[6] == {}
    assert terminal[7] == ""
    assert terminal[8]["interactive"] is True
    assert terminal[8]["value"] == "Run scan"
    assert "old.example" not in "".join(map(str, terminal))
    assert "old answer" not in "".join(map(str, terminal))


def test_scan_event_is_single_active_generator_and_controls_button():
    dependencies = [
        dependency
        for dependency in app_redesign.demo.config["dependencies"]
        if dependency.get("api_name") == "run_scan"
    ]

    assert len(dependencies) == 1
    dependency = dependencies[0]
    assert dependency["trigger_mode"] == "once"
    assert dependency["types"]["generator"] is True
    assert dependency["show_progress"] == "minimal"
    assert dependency["outputs"][-2:] == [
        app_redesign.chat_input._id,
        app_redesign.run_scan_button._id,
    ]


def test_standard_plan_is_only_selectable_mode_and_premium_is_unavailable():
    assert SCAN_MODE_CHOICES == [("Standard · 150", "advanced")]
    assert app_redesign.scan_mode.choices == SCAN_MODE_CHOICES
    assert app_redesign.scan_mode.value == "advanced"
    assert "Premium · 5,000 — coming soon" in str(app_redesign.demo.config)


def test_chat_css_targets_role_bubble_and_resets_nested_message_width():
    assert ".chatbot .message.user,\n.chatbot .message.bot" in CSS
    assert ".chatbot .message .message {" in CSS
    nested_rule = CSS.split(".chatbot .message .message {", 1)[1].split("}", 1)[0]
    assert "width: 100% !important" in nested_rule
    assert "max-width: none !important" in nested_rule
