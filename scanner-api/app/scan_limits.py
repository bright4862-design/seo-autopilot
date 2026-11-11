"""Server-owned assessed-page budgets, separate from bounded evidence samples.

Only trusted worker orchestration enters ``scan_page_limit``. Public request
fields must never select this context. The default preserves historical guards.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from types import MappingProxyType


PAGE_CAPS = MappingProxyType({
    "basic": 25, "quick": 40, "deep": 85, "advanced": 150,
    "standard_150": 150, "standard_500": 500,
})
PAGE_CAP_CONTRACT_VERSION = "server_scan_page_caps_v1_150_500"
SERVER_MAX_PAGE_CAP = 500
DEFAULT_PAGE_CAP = PAGE_CAPS["standard_150"]
_page_cap = ContextVar("scan_page_cap", default=DEFAULT_PAGE_CAP)


def page_cap_for_mode(mode: str) -> int:
    try:
        return PAGE_CAPS[mode]
    except (KeyError, TypeError) as exc:
        raise ValueError("Unsupported server scan mode") from exc


def current_page_cap() -> int:
    return _page_cap.get()


@contextmanager
def scan_page_limit(cap: int):
    if type(cap) is not int or cap not in PAGE_CAPS.values():
        raise ValueError("Invalid server-owned page cap")
    token = _page_cap.set(cap)
    try:
        yield
    finally:
        _page_cap.reset(token)
