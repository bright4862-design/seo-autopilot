"""Pure customer-copy guard for GEO readiness claims.

This module does not decide evidence or scoring. It only prevents customer-facing
copy from turning a structural readiness diagnostic into a claim about third-
party AI inclusion, ranking, citations, visibility, or traffic.
"""
from __future__ import annotations

import re

_PROVIDER = re.compile(r"\b(?:chatgpt|openai|perplexity|gemini|claude|ai\s+overviews?)\b", re.I)
_OUTCOME = re.compile(r"\b(?:rank(?:s|ed|ing)?|appear(?:s|ed|ing|ance)?|citation(?:s)?|cited|visibility|traffic|inclusion|included)\b", re.I)
_NEGATION = re.compile(
    r"\b(?:does\s+not|do\s+not|did\s+not|is\s+not|are\s+not|not\s+proof|not\s+measure|"
    r"cannot|can't|never|no\s+guarantee|doesn't\s+guarantee|without\s+claiming|not\s+a\s+prediction)\b",
    re.I,
)
_SENTENCE = re.compile(r"[^.!?\n]+(?:[.!?]|$)")


def claim_boundary_violations(text: str) -> tuple[str, ...]:
    """Return bounded sentences that make unsupported provider-outcome claims."""
    if not isinstance(text, str):
        raise ValueError("Expected customer copy string")
    violations = []
    for match in _SENTENCE.finditer(text[:200_000]):
        sentence = " ".join(match.group(0).split())
        if not sentence:
            continue
        if _PROVIDER.search(sentence) and _OUTCOME.search(sentence) and not _NEGATION.search(sentence):
            violations.append(sentence[:500])
    return tuple(violations)


def assert_claim_boundary(text: str) -> None:
    violations = claim_boundary_violations(text)
    if violations:
        raise ValueError("Unsupported GEO visibility claim: " + violations[0])
