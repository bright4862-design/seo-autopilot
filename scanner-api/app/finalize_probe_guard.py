"""Stop new optional I/O after finalization observes target-site throttling."""

import httpx

from .transport_evidence import SKIP_RESPONSE_BODY_EXTENSION


FINALIZE_RATE_LIMITED = "finalize_rate_limited"
FINALIZE_OPTIONAL_PROBES_UNAVAILABLE = "finalize_optional_probes_unavailable"


class FinalizeProbeSuppressed(RuntimeError):
    pass


class FinalizeProbeGuard:
    def __init__(self):
        self.reason = ""

    def observe_status(self, status_code: int) -> None:
        if status_code == 429 and not self.reason:
            self.reason = FINALIZE_RATE_LIMITED

    async def before_request(self, _request: httpx.Request) -> None:
        if self.reason:
            raise FinalizeProbeSuppressed(self.reason)

    async def after_response(self, response: httpx.Response) -> None:
        # HTTPX calls response hooks before consuming the body. Admit no new
        # optional traffic even if the throttled response body is slow.
        if response.status_code == 429:
            self.observe_status(429)
            response.extensions[SKIP_RESPONSE_BODY_EXTENSION] = True
