from app import DEMO_SCAN, build_grounded_prompt, demo_answer, extract_output_text


def test_extract_output_text_from_responses_api():
    payload = {
        "output": [
            {
                "content": [
                    {"type": "output_text", "text": "Grounded answer."}
                ]
            }
        ]
    }
    assert extract_output_text(payload) == "Grounded answer."


def test_prompt_contains_authority_rules_and_evidence():
    prompt = build_grounded_prompt("What should I fix first?", DEMO_SCAN)
    assert "Never invent URLs" in prompt
    assert '"release_gate_eligible":true' in prompt
    assert "What should I fix first?" in prompt


def test_demo_answer_is_grounded():
    answer = demo_answer("What should I fix first?", DEMO_SCAN)
    assert "redirected internal links" in answer.lower()
    assert "18 pages" in answer
