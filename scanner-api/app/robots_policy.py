from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from urllib import robotparser

from .security import DEFAULT_MAX_DECODED_RESPONSE_BYTES, safe_get


SCANNER_USER_AGENT = "FixListPythonScanner"
SEARCH_USER_AGENT = "Googlebot"
_OWNER_ROBOTS_OVERRIDE: ContextVar[bool] = ContextVar("fixlist_owner_robots_override", default=False)


def set_owner_robots_override(enabled: bool) -> Token:
    """Set the request-local owner robots override for the current scan task.

    ContextVar keeps concurrent FastAPI requests isolated. The override only
    affects FixList crawler enforcement; Googlebot/indexability evidence still
    reflects the site's actual robots.txt directives.
    """
    return _OWNER_ROBOTS_OVERRIDE.set(bool(enabled))


def reset_owner_robots_override(token: Token) -> None:
    _OWNER_ROBOTS_OVERRIDE.reset(token)


def owner_robots_override_enabled() -> bool:
    return bool(_OWNER_ROBOTS_OVERRIDE.get())


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
        """Return what robots.txt itself says, independent of scan policy."""
        if self.status == "missing":
            return True
        if self.status != "available" or self.parser is None:
            return None
        return bool(self.parser.can_fetch(user_agent, url))

    def allowed(self, user_agent: str, url: str) -> bool | None:
        """Return the effective fetch permission for this FixList request.

        A self-attested owner scan may ignore robots.txt for FixList's own user
        agent. Other user agents, especially Googlebot, always use the raw
        robots.txt directive so SEO/indexability evidence is not falsified.
        """
        if user_agent == SCANNER_USER_AGENT and owner_robots_override_enabled():
            return True
        return self.directive_allowed(user_agent, url)

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
    # Evidence reports the site's actual directive even when an owner has
    # elected not to enforce that directive for this FixList crawl.
    scanner_directive_allowed = policy.directive_allowed(SCANNER_USER_AGENT, url)
    googlebot_allowed = policy.directive_allowed(SEARCH_USER_AGENT, url)
    page.update(policy.evidence())
    page.update({
        "robots_txt_scanner_allowed": scanner_directive_allowed,
        "robots_txt_googlebot_allowed": googlebot_allowed,
        "robots_txt_scanner_blocked": scanner_directive_allowed is False,
        "robots_txt_googlebot_blocked": googlebot_allowed is False,
        "robots_txt_policy_applied": not owner_robots_override_enabled(),
        "owner_attested_robots_override": owner_robots_override_enabled(),
    })
    if googlebot_allowed is False:
        page["indexable"] = False
        page["indexability_state"] = "Blocked by robots.txt"
        page["robots_indexability_status"] = "blocked_by_robots_txt"
    return page
