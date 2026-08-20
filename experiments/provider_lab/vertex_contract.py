from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import ProviderIdentity


@dataclass(frozen=True)
class VertexTransportContract:
    """Data-only snapshot of the current production Vertex Grok transport.

    This is a parity target for lab work, not a production adapter. It intentionally
    contains no Google credentials, HTTP client, endpoint invocation, or runtime import.
    """

    identity: ProviderIdentity
    location: str
    max_output_tokens: int
    stream: bool
    store: bool
    retryable_status_codes: frozenset[int]

    def payload_for_prompt(self, prompt: str) -> dict[str, Any]:
        clean_prompt = str(prompt or "").strip()
        if not clean_prompt:
            raise ValueError("prompt must be non-empty.")
        return {
            "model": self.identity.model_id,
            "input": clean_prompt,
            "max_output_tokens": self.max_output_tokens,
            "stream": self.stream,
            "store": self.store,
        }


CURRENT_VERTEX_CONTRACT = VertexTransportContract(
    identity=ProviderIdentity(
        provider="vertex-ai",
        model_id="xai/grok-4.20-non-reasoning",
    ),
    location="global",
    max_output_tokens=1_600,
    stream=False,
    store=False,
    retryable_status_codes=frozenset({429, 500, 502, 503, 504}),
)
