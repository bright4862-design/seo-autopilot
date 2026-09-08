from __future__ import annotations

from dataclasses import replace

from .contracts import ProviderIdentity
from .vertex_contract import CURRENT_VERTEX_CONTRACT


VERTEX_REASONING_CANDIDATE = replace(
    CURRENT_VERTEX_CONTRACT,
    identity=ProviderIdentity(
        provider="vertex-ai",
        model_id="xai/grok-4.20-reasoning",
    ),
)
