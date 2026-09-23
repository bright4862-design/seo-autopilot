from __future__ import annotations

from app.ai_trace import ai_trace


def test_ai_trace_has_bounded_metadata_only_shape():
    trace = ai_trace(
        operation="grounding_verify",
        result_status="verified",
        schema_version="chat_answer_v1",
        evidence_fingerprint="a" * 64,
        annotation_count=3,
        rejected_count=0,
        latency_ms=12,
    )
    assert trace == {
        "ai_trace_version": "ai_trace_v1",
        "operation": "grounding_verify",
        "result_status": "verified",
        "schema_version": "chat_answer_v1",
        "evidence_fingerprint": "a" * 64,
        "annotation_count": 3,
        "rejected_count": 0,
        "latency_ms": 12,
    }
    forbidden = {"prompt", "text", "url", "evidence", "customer_content", "response"}
    assert forbidden.isdisjoint(trace)


def test_ai_trace_clamps_negative_counters_and_latency():
    trace = ai_trace(
        operation="grounding_verify",
        result_status="rejected",
        annotation_count=-1,
        rejected_count=-2,
        latency_ms=-3,
    )
    assert trace["annotation_count"] == 0
    assert trace["rejected_count"] == 0
    assert trace["latency_ms"] == 0


def test_ai_trace_rejects_freeform_content_bearing_fields():
    import pytest

    with pytest.raises(ValueError):
        ai_trace(operation="customer https://example.com/private", result_status="verified")
    with pytest.raises(ValueError):
        ai_trace(operation="grounding_verify", result_status="verified", schema_version="raw-answer-text")
    with pytest.raises(ValueError):
        ai_trace(operation="grounding_verify", result_status="verified", evidence_fingerprint="not-a-hash")
