import httpx
from app.grok_chat import (
    GROK_CHAT_VERSION,
    GROK_MODEL_ID,
    GrokUpstreamError,
    _response_error,
    build_grounded_prompt,
    extract_output_text,
)


def test_grok_proxy_uses_non_reasoning_model_by_default():
    assert GROK_CHAT_VERSION == "grok_chat_proxy_v3_natural_diy"
    assert GROK_MODEL_ID == "xai/grok-4.20-non-reasoning"


def test_grounded_prompt_contains_evidence_and_authority_rules():
    prompt = build_grounded_prompt(
        "What should I fix first?",
        {
            "website_url": "https://example.com",
            "pages_crawled": 12,
            "release_gate_eligible": False,
        },
    )

    assert "Treat supplied scan evidence as authoritative only" in prompt
    assert '"pages_crawled":12' in prompt
    assert '"release_gate_eligible":false' in prompt
    assert "What should I fix first?" in prompt
    assert "Never use an owner label" in prompt
    assert "help them do it" in prompt
    assert "Never construct, complete, modify, or guess a URL" in prompt
    assert "status_code 200" in prompt


def test_grounded_prompt_preserves_follow_up_context():
    prompt = build_grounded_prompt(
        "Can I do this myself?",
        {"release_gate_eligible": True},
        [
            {"role": "user", "content": "How do I fix the redirected links?"},
            {"role": "assistant", "content": "Update the shared navigation template."},
        ],
    )

    assert "Can I do this myself?" in prompt
    assert "How do I fix the redirected links?" in prompt
    assert "Update the shared navigation template." in prompt


def test_extract_output_text_supports_direct_response_shape():
    assert extract_output_text({"output_text": "Grounded answer."}) == "Grounded answer."


def test_extract_output_text_supports_nested_response_shape():
    payload = {
        "output": [
            {
                "content": [
                    {"type": "output_text", "text": "First paragraph."},
                    {"type": "output_text", "text": "Second paragraph."},
                ]
            }
        ]
    }

    assert extract_output_text(payload) == "First paragraph.\n\nSecond paragraph."


def test_permission_error_identifies_cloud_run_role_fix():
    request = httpx.Request("POST", "https://aiplatform.googleapis.com/test")
    response = httpx.Response(
        403,
        request=request,
        json={
            "error": {
                "status": "PERMISSION_DENIED",
                "message": "Permission aiplatform.endpoints.predict denied.",
            }
        },
    )

    error = _response_error(response)

    assert error.retryable is False
    assert "roles/aiplatform.user" in error.public_detail
    assert "403/PERMISSION_DENIED" in error.public_detail


def test_quota_error_is_retryable_and_actionable():
    request = httpx.Request("POST", "https://aiplatform.googleapis.com/test")
    response = httpx.Response(
        429,
        request=request,
        json={"error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded."}},
    )

    error = _response_error(response)

    assert error.retryable is True
    assert "global Grok QPM and token quotas" in error.public_detail


def test_bad_request_exposes_only_bounded_upstream_detail():
    error = GrokUpstreamError(
        400,
        "INVALID_ARGUMENT",
        "Invalid model field.\n" + ("x" * 300),
        retryable=False,
    )

    assert "400/INVALID_ARGUMENT" in error.public_detail
    assert "\n" not in error.public_detail
    assert len(error.public_detail) < 260
