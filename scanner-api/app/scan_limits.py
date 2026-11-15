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


def standard_scan_contract(scan: dict) -> tuple[str, int, str] | None:
    """Read a V9 contract or the implicit Standard 150 cap on an old row."""
    mode = scan.get("scan_mode")
    cap = scan.get("page_cap")
    pipeline = scan.get("pipeline_mode")
    if cap is None:
        if mode not in (None, "", "advanced", "standard_150"):
            return None
        mode, cap = "standard_150", DEFAULT_PAGE_CAP
        if pipeline is None:
            pipeline = "monolith"
    if (
        type(cap) is int
        and mode in ("standard_150", "standard_500")
        and cap == page_cap_for_mode(mode)
        and pipeline in ("monolith", "staged")
        and (cap != SERVER_MAX_PAGE_CAP or pipeline == "staged")
    ):
        return mode, cap, pipeline
    return None


def task_matches_scan_contract(scan: dict, task: dict) -> bool:
    """A task can repeat a frozen contract but cannot choose it."""
    cap = task.get("page_cap")
    pipeline = task.get("pipeline_mode")
    scope = task.get("staged_rollout_scope")
    if scope is not None and (scope != "paid" or scan.get("staged_rollout_scope") != scope or pipeline != "staged"):
        return False
    if cap is None and pipeline is None:
        return task.get("scan_mode") != "standard_500"  # Older tasks carry no frozen contract.
    return type(cap) is int and standard_scan_contract(scan) == (task.get("scan_mode"), cap, pipeline)


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
