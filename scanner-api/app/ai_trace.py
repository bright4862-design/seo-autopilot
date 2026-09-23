"""Bounded offline grounding trace metadata; no production instrumentation."""
AI_TRACE_VERSION = "ai_trace_v1"
_AI_TRACE_OPERATIONS = frozenset({"grounding_verify", "fixbench_evaluate"})
_AI_TRACE_STATUSES = frozenset({"verified", "redacted", "rejected", "unavailable", "passed", "failed"})
_AI_TRACE_SCHEMAS = frozenset({"", "ai_annotation_v1", "chat_answer_v1", "ai_annotation_v2", "chat_answer_v2"})


def ai_trace(
    *,
    operation: str,
    result_status: str,
    schema_version: str = "",
    evidence_fingerprint: str = "",
    annotation_count: int = 0,
    rejected_count: int = 0,
    latency_ms: int = 0,
) -> dict[str, object]:
    """Return the bounded metadata-only H1-6 AI trace shape.

    Inputs are deliberately allow-listed so callers cannot smuggle raw customer
    text, URLs, prompts, answers, or evidence snippets into observability fields.
    """
    if operation not in _AI_TRACE_OPERATIONS:
        raise ValueError("unsupported ai trace operation")
    if result_status not in _AI_TRACE_STATUSES:
        raise ValueError("unsupported ai trace status")
    if schema_version not in _AI_TRACE_SCHEMAS:
        raise ValueError("unsupported ai trace schema")
    fingerprint = str(evidence_fingerprint or "").lower()
    if fingerprint and (len(fingerprint) != 64 or any(ch not in "0123456789abcdef" for ch in fingerprint)):
        raise ValueError("invalid evidence fingerprint")
    return {
        "ai_trace_version": AI_TRACE_VERSION,
        "operation": operation,
        "result_status": result_status,
        "schema_version": schema_version,
        "evidence_fingerprint": fingerprint,
        "annotation_count": max(0, min(int(annotation_count), 10000)),
        "rejected_count": max(0, min(int(rejected_count), 10000)),
        "latency_ms": max(0, min(int(latency_ms), 86_400_000)),
    }
