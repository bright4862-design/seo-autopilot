from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from urllib import robotparser

from .security import DEFAULT_MAX_DECODED_RESPONSE_BYTES, safe_get


SCANNER_USER_AGENT = "FixListPythonScanner"
SEARCH_USER_AGENT = "Googlebot"
_OWNER_ROBOTS_OVERRIDE: ContextVar[bool] = ContextVar(
    "fixlist_owner_robots_override",
    default=False,
)


@contextmanager
def owner_robots_override(enabled: bool):
    """Apply the owner-attested robots override to this request context only.

    The ContextVar prevents one concurrent scan from changing another scan's
    policy. It changes only FixList's fetch permission for an explicit Disallow;
    the parsed robots directives remain available for Google/indexability
    evidence and an unavailable robots file remains unknown rather than allowed.
    """
    token = _OWNER_ROBOTS_OVERRIDE.set(bool(enabled))
    try:
        yield
    finally:
        _OWNER_ROBOTS_OVERRIDE.reset(token)


def owner_robots_override_active() -> bool:
    return _OWNER_ROBOTS_OVERRIDE.get() is True


@dataclass
class RobotsPolicy:
    url: str
    status: str
    status_code: int
    parser: robotparser.RobotFileParser | None = None

    @property
    def rules_known(self) -> bool:
        return self.status in {"available", "missing"}

    def directive_allowed(self, user_agent: str, url: str) -> bool | None:
        """Return the robots.txt directive without applying FixList policy."""
        if self.status == "missing":
            return True
        if self.status != "available" or self.parser is None:
            return None
        return bool(self.parser.can_fetch(user_agent, url))

    def allowed(self, user_agent: str, url: str) -> bool | None:
        """Return effective fetch permission for the requested user-agent.

        Only the FixList scanner user-agent may turn an explicit Disallow into
        an allow, and only while the request-local owner override is active.
        Googlebot and every other agent always receive the actual directive.
        """
        directive = self.directive_allowed(user_agent, url)
        if (
            user_agent == SCANNER_USER_AGENT
            and directive is False
            and owner_robots_override_active()
        ):
            return True
        return directive

    def evidence(self) -> dict:
        return {
            "robots_txt_url": self.url,
            "robots_txt_status": self.status,
            "robots_txt_status_code": self.status_code,
            "robots_txt_rules_known": self.rules_known,
        }


async def load_robots_policy(client, origin: str) -> RobotsPolicy:
    robots_url = f"{str(origin or '').rstrip('/')}/robots.txt"
    try:
        response = await safe_get(
            client,
            robots_url,
            max_decoded_bytes=DEFAULT_MAX_DECODED_RESPONSE_BYTES,
        )
    except Exception:
        return RobotsPolicy(robots_url, "unavailable", 0)
    if response is None:
        return RobotsPolicy(robots_url, "unavailable", 0)

    status_code = int(getattr(response, "status_code", 0) or 0)
    if status_code in {404, 410}:
        return RobotsPolicy(robots_url, "missing", status_code)
    if not (200 <= status_code < 300):
        return RobotsPolicy(robots_url, "access_limited", status_code)

    parser = robotparser.RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(str(getattr(response, "text", "") or "").splitlines())
    return RobotsPolicy(robots_url, "available", status_code, parser)


def annotate_robots_evidence(page: dict, policy: RobotsPolicy, url: str) -> dict:
    scanner_directive_allowed = policy.directive_allowed(SCANNER_USER_AGENT, url)
    scanner_fetch_allowed = policy.allowed(SCANNER_USER_AGENT, url)
    googlebot_allowed = policy.directive_allowed(SEARCH_USER_AGENT, url)
    page.update(policy.evidence())
    page.update({
        "robots_txt_scanner_allowed": scanner_directive_allowed,
        "robots_txt_googlebot_allowed": googlebot_allowed,
        "robots_txt_scanner_blocked": scanner_directive_allowed is False,
        "robots_txt_googlebot_blocked": googlebot_allowed is False,
        "robots_txt_owner_override_applied": owner_robots_override_active(),
        "robots_txt_fetch_allowed": scanner_fetch_allowed,
    })
    if googlebot_allowed is False:
        page["indexable"] = False
        page["indexability_state"] = "Blocked by robots.txt"
        page["robots_indexability_status"] = "blocked_by_robots_txt"
    return page
