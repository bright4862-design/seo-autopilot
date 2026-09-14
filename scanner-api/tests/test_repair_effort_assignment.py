"""Customer-facing ownership and effort calibration for FixList repair cards."""

from app.review import normalize_fix


def _urls(count: int) -> list[str]:
    return [f"/page-{index}" for index in range(count)]


def _normalize(rule: str, category: str, count: int, **extra):
    pages = _urls(count)
    return normalize_fix({
        "rule": rule,
        "category": category,
        "title": rule.replace("_", " ").title(),
        "page_url": pages[0] if pages else "/",
        "affected_pages": pages,
        **extra,
    }, 0)


def test_small_canonical_change_is_not_forced_to_developer_or_two_hours():
    fix = _normalize(
        "canonical_missing",
        "canonical",
        2,
        difficulty="developer",
        requires_developer=True,
        status="needs_developer",
        who_can_do_this="your_web_person",
    )

    assert fix["requires_developer"] is False
    assert fix["who_can_do_this"] == "you_or_your_web_person"
    assert fix["difficulty"] == "moderate"
    assert fix["status"] == "needs_approval"
    assert fix["estimated_time"] == "about 5–15 minutes"


def test_manual_content_batch_scales_with_number_of_affected_urls():
    fix = _normalize(
        "missing_meta_description",
        "meta_description",
        8,
        difficulty="developer",
        requires_developer=True,
        status="needs_developer",
        who_can_do_this="your_web_person",
    )

    assert fix["requires_developer"] is False
    assert fix["who_can_do_this"] == "you"
    assert fix["difficulty"] == "easy"
    assert fix["estimated_time"] == "about 30–60 minutes"


def test_shared_template_fix_does_not_scale_linearly_with_100_urls():
    fix = _normalize(
        "missing_meta_description",
        "meta_description",
        100,
        shared_repair_confirmed=True,
        page_scope="template",
        difficulty="moderate",
    )

    assert fix["requires_developer"] is False
    assert fix["estimated_time"] == "about 15–30 minutes"


def test_small_redirect_change_is_presented_as_owner_or_web_person_work():
    fix = _normalize(
        "redirect_chain",
        "redirect",
        3,
        difficulty="developer",
        requires_developer=True,
        status="needs_developer",
        who_can_do_this="your_web_person",
    )

    assert fix["requires_developer"] is False
    assert fix["who_can_do_this"] == "you_or_your_web_person"
    assert fix["difficulty"] == "moderate"
    assert fix["estimated_time"] == "about 15–30 minutes"


def test_shared_image_alt_pattern_is_owner_or_web_person_not_developer_only():
    fix = _normalize(
        "image_alt_text",
        "image_alt_text",
        3,
        source="page_pattern:image_alt_text:activity_detail",
        page_template_family="activity_detail",
        page_scope="family",
        difficulty="developer",
        requires_developer=True,
        status="needs_developer",
        who_can_do_this="your_web_person",
    )

    assert fix["requires_developer"] is False
    assert fix["who_can_do_this"] == "you_or_your_web_person"
    assert fix["difficulty"] == "moderate"
    assert fix["estimated_time"] == "about 15–30 minutes"


def test_rendering_problem_stays_developer_owned_even_for_one_url():
    fix = _normalize(
        "js_rendering",
        "web_dev",
        1,
        difficulty="developer",
        requires_developer=True,
        status="needs_developer",
        who_can_do_this="your_web_person",
    )

    assert fix["requires_developer"] is True
    assert fix["who_can_do_this"] == "your_web_person"
    assert fix["difficulty"] == "developer"
    assert fix["estimated_time"] == "about 30–60 minutes"


def test_server_error_stays_developer_owned_even_for_one_url():
    fix = _normalize(
        "server_error",
        "web_dev",
        1,
        difficulty="developer",
        requires_developer=True,
        status="needs_developer",
        who_can_do_this="your_web_person",
    )

    assert fix["requires_developer"] is True
    assert fix["estimated_time"] == "about 30–60 minutes"
