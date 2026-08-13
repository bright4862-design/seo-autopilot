# Install conservative crawler-trap hardening before scanner.py binds artifact-filter functions.
from .crawler_trap_guard import install as _install_crawler_trap_guard

_install_crawler_trap_guard()

__all__ = ["main", "scanner", "models", "sitemap", "extract", "artifact_filter", "crawler_trap_guard"]
