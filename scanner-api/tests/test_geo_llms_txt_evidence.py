from copy import deepcopy

import pytest

from app.geo_llms_txt_evidence import VERSION, extract_llms_txt_evidence


def obs(**overrides):
    value = {
        "url": "https://example.com/llms.txt",
        "status_code": 200,
        "content_type": "text/plain; charset=utf-8",
        "body": "# Example\n\n> Example site summary.\n\n## Docs\n\n- [Guide](https://example.com/guide.md): Main guide\n",
    }
    value.update(overrides)
    return value


def test_minimal_valid_file_is_structural_only():
    result = extract_llms_txt_evidence(obs(body="# Example\n"))
    assert result["version"] == VERSION
    assert result["presence"] == "present"
    assert result["format_status"] == "valid"
    assert result["title"] == "Example"
    assert result["linked_resource_count"] == 0
    assert result["validation_scope"] == "required_h1_and_bounded_structure_only"
    assert "not_provider" in result["claim_boundary"]


def test_bom_summary_sections_and_links_are_bounded_metadata():
    result = extract_llms_txt_evidence(obs(body="\ufeff# Example\n\n> Summary\n\n## Docs\n- [A](/a.md): A\n- [B](https://example.org/b.md)\n## Optional\n- [C](../c.md)\n"))
    assert result["format_status"] == "valid"
    assert result["has_summary"] is True
    assert result["section_count"] == 2
    assert result["linked_resource_count"] == 3


def test_present_file_without_required_h1_is_explicit_invalid_structure():
    result = extract_llms_txt_evidence(obs(body="> Summary only\n\n## Docs\n- [A](/a.md)\n"))
    assert result["presence"] == "present"
    assert result["format_status"] == "invalid"
    assert result["title"] == ""
    assert result["evidence_ref"]


def test_second_h1_is_invalid_instead_of_guessed_through():
    result = extract_llms_txt_evidence(obs(body="# First\n\n# Second\n"))
    assert result["presence"] == "present"
    assert result["format_status"] == "invalid"


@pytest.mark.parametrize("status", [404, 410])
def test_missing_file_is_neutral_not_applicable_not_failure(status):
    result = extract_llms_txt_evidence(obs(status_code=status, body=None))
    assert result["presence"] == "absent"
    assert result["format_status"] == "not_applicable"
    assert result["evidence_ref"] == ""


@pytest.mark.parametrize("status", [401, 403, 407, 429, 500, 503])
def test_access_or_server_uncertainty_stays_not_verified(status):
    result = extract_llms_txt_evidence(obs(status_code=status, body=None))
    assert result["presence"] == "not_verified"
    assert result["format_status"] == "not_verified"


@pytest.mark.parametrize("flag", ["body_truncated", "access_limited", "fetch_error"])
def test_uncertainty_flags_override_apparent_200(flag):
    result = extract_llms_txt_evidence(obs(**{flag: True}))
    assert result["presence"] == "not_verified"
    assert result["format_status"] == "not_verified"


def test_empty_200_is_present_but_invalid():
    result = extract_llms_txt_evidence(obs(body="\n\n"))
    assert result["presence"] == "present"
    assert result["format_status"] == "invalid"


def test_oversized_or_nul_body_is_not_verified_not_negative_quality():
    too_large = extract_llms_txt_evidence(obs(body="# X\n" + "a" * 256_001))
    nul = extract_llms_txt_evidence(obs(body="# X\x00\n"))
    assert too_large["format_status"] == "not_verified"
    assert nul["format_status"] == "not_verified"


def test_subpath_llms_txt_has_explicit_scope():
    result = extract_llms_txt_evidence(obs(url="https://example.com/docs/llms.txt"))
    assert result["scope_path"] == "/docs/"


@pytest.mark.parametrize("url", [
    "https://example.com/robots.txt",
    "ftp://example.com/llms.txt",
    "https://user:pass@example.com/llms.txt",
    "https://example.com/llms.txt?variant=1",
    "not a url",
])
def test_non_llms_or_non_public_http_identity_fails_closed(url):
    with pytest.raises(ValueError):
        extract_llms_txt_evidence(obs(url=url))


def test_malformed_transport_types_fail_closed():
    with pytest.raises(ValueError, match="status code"):
        extract_llms_txt_evidence(obs(status_code=True))
    with pytest.raises(ValueError, match="body"):
        extract_llms_txt_evidence(obs(body=b"# Example"))
    with pytest.raises(ValueError, match="body_truncated"):
        extract_llms_txt_evidence(obs(body_truncated="yes"))


def test_adapter_is_deterministic_and_input_immutable():
    value = obs()
    original = deepcopy(value)
    first = extract_llms_txt_evidence(value)
    second = extract_llms_txt_evidence(value)
    assert first == second
    assert value == original
    assert len(first["content_digest"]) == 64
