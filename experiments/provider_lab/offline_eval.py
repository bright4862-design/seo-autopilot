from __future__ import annotations

from time import perf_counter
from typing import Callable, Protocol

from .contracts import EvaluationCase, EvaluationRecord, ProviderIdentity


class OfflineProvider(Protocol):
    """Minimal provider seam for offline evaluation."""

    identity: ProviderIdentity

    async def generate(self, prompt: str) -> str:
        ...


PromptBuilder = Callable[[EvaluationCase], str]


def _bounded_error(exc: Exception) -> str:
    detail = " ".join(str(exc).split())[:400]
    return f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__


async def evaluate_case(
    case: EvaluationCase,
    provider: OfflineProvider,
    prompt_builder: PromptBuilder,
) -> EvaluationRecord:
    """Run one lab case and return traceable provider-neutral evidence.

    This function performs no network access itself. Any future network-capable
    provider must be injected explicitly by a lab-only caller.
    """

    prompt = prompt_builder(case)
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt_builder must return a non-empty string.")

    started = perf_counter()
    try:
        output = await provider.generate(prompt)
        if not isinstance(output, str) or not output.strip():
            raise ValueError("provider returned no readable text output.")
        error = None
        output_text = output.strip()
    except Exception as exc:  # lab records failures instead of mutating runtime state
        error = _bounded_error(exc)
        output_text = None

    latency_ms = max(0, round((perf_counter() - started) * 1000))
    identity = provider.identity

    return EvaluationRecord(
        case_id=case.case_id,
        provider=identity.provider,
        model_id=identity.model_id,
        authority_hash=case.authority_hash,
        evidence_hash=case.evidence_hash,
        latency_ms=latency_ms,
        output_text=output_text,
        error=error,
    )
