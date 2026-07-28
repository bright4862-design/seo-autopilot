from app.grok_chat import (
    GROK_CHAT_VERSION,
    GROK_MODEL_ID,
    build_grounded_prompt,
    extract_output_text,
)


def test_grok_proxy_uses_non_reasoning_model_by_default():
    assert GROK_CHAT_VERSION == "grok_chat_proxy_v1"
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
