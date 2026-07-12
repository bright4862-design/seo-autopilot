from __future__ import annotations

from dataclasses import dataclass
from urllib import robotparser

from .security import safe_get


SCANNER_USER_AGENT = "FixListPythonScanner"
SEARCH_USER_AGENT = "Googlebot"


@dataclass
class RobotsPolicy:
    url: str
    status: str
    status_code: int
    parser: robotparser.RobotFileParser | None = None

    @property
    def rules_known(self) -> bool:
        return self.status in {"available", "missing"}

    def allowed(self, user_agent: str, url: str) -> bool | None:
        if self.status == "missing":
            return True
        if self.status != "available" or self.parser is None:
            return None
        return bool(self.parser.can_fetch(user_agent, url))

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
        response = await safe_get(client, robots_url)
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
    scanner_allowed = policy.allowed(SCANNER_USER_AGENT, url)
    googlebot_allowed = policy.allowed(SEARCH_USER_AGENT, url)
    page.update(policy.evidence())
    page.update({
        "robots_txt_scanner_allowed": scanner_allowed,
        "robots_txt_googlebot_allowed": googlebot_allowed,
        "robots_txt_scanner_blocked": scanner_allowed is False,
        "robots_txt_googlebot_blocked": googlebot_allowed is False,
    })
    if googlebot_allowed is False:
        page["indexable"] = False
        page["indexability_state"] = "Blocked by robots.txt"
        page["robots_indexability_status"] = "blocked_by_robots_txt"
    return page
