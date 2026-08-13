from __future__ import annotations

import base64
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


GITHUB_API = "https://api.github.com"
USER_AGENT = "FixList-Crawler-Research-Agent/1.0"

# Direct adaptation is restricted to clearly permissive licenses. Repositories
# without a recognized permissive license remain useful for architectural ideas,
# but the agent will not recommend copying implementation text from them.
PERMISSIVE_LICENSES = {
    "MIT",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "0BSD",
    "Unlicense",
}

SOURCE_EXTENSIONS = {
    ".py", ".rs", ".go", ".js", ".mjs", ".cjs", ".ts", ".tsx",
    ".java", ".kt", ".cs", ".rb", ".php",
}

PATH_HINTS = (
    "crawl", "crawler", "spider", "frontier", "queue", "fetch", "http",
    "robot", "sitemap", "redirect", "canonical", "hreflang", "render",
    "playwright", "puppeteer", "dedup", "duplicate", "score", "audit",
    "issue", "link", "pagerank", "retry", "backoff", "url", "trap",
)

PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "bounded_frontier": (
        re.compile(r"\b(VecDeque|deque|Queue|PriorityQueue|frontier)\b", re.I),
        re.compile(r"\b(max_pages|max_depth|concurrency|semaphore)\b", re.I),
    ),
    "robots_and_sitemaps": (
        re.compile(r"robots\.txt|robotparser|respect_robots", re.I),
        re.compile(r"sitemap(?:_index)?|sitemap\.xml", re.I),
    ),
    "retry_backoff": (
        re.compile(r"Retry-After|retry_after", re.I),
        re.compile(r"exponential\s*backoff|backoff|retry", re.I),
        re.compile(r"\b429\b|\b503\b|\b502\b|\b504\b", re.I),
    ),
    "crawler_trap_protection": (
        re.compile(r"soft[-_ ]?404|infinite[-_ ]?(?:url|crawl)|crawler[-_ ]?trap", re.I),
        re.compile(r"repeat(?:ing)?[-_ ]?(?:segment|path)|faceted|tracking[_ -]?param", re.I),
        re.compile(r"e-page-|e-filter-|infinity|session(?:id)?|utm_", re.I),
    ),
    "render_vs_raw_diff": (
        re.compile(r"render(?:ed)?[_ -]?(?:html|dom)|headless|playwright|puppeteer|chrome", re.I),
        re.compile(r"raw[_ -]?html|pre[_ -]?render|post[_ -]?render|js[-_ ]?only", re.I),
    ),
    "canonical_redirect_validation": (
        re.compile(r"canonical", re.I),
        re.compile(r"redirect(?:_chain| chain|s)?|location", re.I),
    ),
    "hreflang_validation": (
        re.compile(r"hreflang", re.I),
        re.compile(r"return[-_ ]?tag|reciprocal", re.I),
    ),
    "duplicate_content": (
        re.compile(r"jaccard|shingle|minhash|simhash", re.I),
        re.compile(r"near[-_ ]?duplicate|duplicate[_ -]?(?:body|content)", re.I),
    ),
    "link_graph": (
        re.compile(r"PageRank|pagerank|link[_ -]?(?:graph|score|authority)", re.I),
        re.compile(r"\binlinks?\b|\boutlinks?\b|orphan", re.I),
    ),
    "explainable_scoring": (
        re.compile(r"health[_ -]?score|seo[_ -]?score|severity[_ -]?weight", re.I),
        re.compile(r"why[_ -]?it[_ -]?matters|how[_ -]?to[_ -]?fix|explain[_ -]?issue", re.I),
    ),
    "resume_checkpoint": (
        re.compile(r"checkpoint|resume|jobdir|saved[_ -]?crawl", re.I),
        re.compile(r"durable|persistent[_ -]?(?:queue|frontier|state)", re.I),
    ),
}

# FixList-oriented recommendations. The agent only emits one when the same
# capability is found in public code and is not detected in the local tree.
RECOMMENDATION_LIBRARY: dict[str, dict[str, str]] = {
    "retry_backoff": {
        "priority": "P0",
        "title": "Add deadline-aware retry/backoff for transient fetch failures",
        "why": "A single 429/5xx/transient network failure currently risks becoming misleading access evidence.",
        "implementation": (
            "Wrap scanner fetches in a bounded retry policy for 429/500/502/503/504 and transient transport errors; "
            "honor a small Retry-After value, use jittered exponential backoff, and refuse a retry when the scan deadline lacks budget."
        ),
    },
    "crawler_trap_protection": {
        "priority": "P0",
        "title": "Reject crawler-trap URLs before they enter the frontier",
        "why": "Parameter explosions and repeating-path URLs can consume the Standard 150 discovery budget and reduce representative coverage.",
        "implementation": (
            "Add a deterministic enqueue filter for repeating path segments, known page-builder/faceted/session/tracking parameters, and malformed hrefs; "
            "record bounded evidence for skipped URLs instead of silently crawling them."
        ),
    },
    "render_vs_raw_diff": {
        "priority": "P1",
        "title": "Make raw-vs-rendered SEO differences explicit",
        "why": "FixList already detects rendering risk, but an explicit diff can show which title/canonical/noindex/H1/links exist only after JavaScript.",
        "implementation": (
            "Extend the existing render follow-up to compare raw and rendered head signals and internal links, returning evidence fields rather than a second generic audit."
        ),
    },
    "duplicate_content": {
        "priority": "P1",
        "title": "Add bounded near-duplicate content detection",
        "why": "Exact metadata duplicates miss template-heavy pages whose body content is effectively duplicated.",
        "implementation": (
            "Use bounded shingles or a compact similarity fingerprint on successfully fetched HTML pages; compare only within template families to keep runtime predictable."
        ),
    },
    "link_graph": {
        "priority": "P1",
        "title": "Add internal-link authority and orphan/dead-end evidence",
        "why": "Inlink counts alone do not distinguish important hubs from low-value deep pages.",
        "implementation": (
            "Build the resolved internal-link graph after the crawl and compute a lightweight PageRank/link-authority score plus orphan/dead-end/depth signals for prioritization."
        ),
    },
    "resume_checkpoint": {
        "priority": "P2",
        "title": "Keep durable checkpoint/resume patterns for larger scans",
        "why": "This matters more for the larger async crawler than for Standard 150.",
        "implementation": (
            "Persist frontier/page state at batch boundaries and resume by immutable scan identity; do not enlarge the synchronous Standard request path to achieve scale."
        ),
    },
}


@dataclass(frozen=True)
class RepoSummary:
    full_name: str
    html_url: str
    description: str
    language: str
    stars: int
    forks: int
    default_branch: str
    license_spdx: str
    license_mode: str
    pushed_at: str
    score: float


class GitHubReadOnlyClient:
    """Minimal GitHub REST client that only exposes GET requests."""

    def __init__(self, token: str = "", timeout: float = 20.0):
        self.token = token.strip()
        self.timeout = max(2.0, float(timeout))

    def get_json(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        if not path.startswith("/"):
            raise ValueError("GitHub API path must be absolute")
        url = f"{GITHUB_API}{path}"
        if params:
            url += "?" + urlencode(params, doseq=True)
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"GitHub GET failed ({exc.code}) for {path}: {body}") from exc
        except URLError as exc:
            raise RuntimeError(f"GitHub GET failed for {path}: {exc.reason}") from exc


def _license_mode(spdx: str) -> str:
    value = str(spdx or "").strip()
    if value in PERMISSIVE_LICENSES:
        return "permissive_adaptation_allowed_with_license_compliance"
    if value:
        return "ideas_only_no_code_copy"
    return "unknown_license_ideas_only"


def _repo_score(item: dict[str, Any]) -> float:
    stars = int(item.get("stargazers_count") or 0)
    forks = int(item.get("forks_count") or 0)
    language = str(item.get("language") or "").lower()
    desc = str(item.get("description") or "").lower()
    topics = " ".join(item.get("topics") or []).lower()
    relevance = 0.0
    for term, weight in (
        ("seo", 6.0), ("crawler", 5.0), ("spider", 3.0),
        ("technical", 2.0), ("sitemap", 2.0), ("robots", 2.0),
        ("audit", 2.0), ("scrapy", 1.5), ("render", 1.0),
    ):
        if term in desc or term in topics:
            relevance += weight
    if language in {"python", "rust", "go", "typescript", "javascript"}:
        relevance += 1.5
    # Logarithmic-ish popularity without importing math: cap contribution so a
    # famous generic crawler cannot outrank a smaller but clearly SEO-specific one.
    popularity = min(12.0, stars ** 0.5 / 3.0) + min(4.0, forks ** 0.5 / 4.0)
    return round(relevance + popularity, 3)


def _source_path_score(path: str) -> int:
    lower = path.lower()
    suffix = Path(lower).suffix
    if suffix not in SOURCE_EXTENSIONS:
        return -1
    score = sum(2 for hint in PATH_HINTS if hint in lower)
    if any(part in lower for part in ("/test", "tests/", "fixture", "vendor/", "node_modules/")):
        score -= 2
    if lower.count("/") <= 3:
        score += 1
    return score


def _pattern_hits(text: str) -> dict[str, int]:
    hits: dict[str, int] = {}
    for name, regexes in PATTERNS.items():
        count = sum(1 for regex in regexes if regex.search(text))
        if count:
            hits[name] = count
    return hits


def _merge_hits(target: dict[str, int], incoming: dict[str, int]) -> None:
    for key, value in incoming.items():
        target[key] = target.get(key, 0) + int(value)


def _decode_content(payload: dict[str, Any], max_bytes: int) -> str:
    if payload.get("encoding") != "base64":
        return ""
    raw = base64.b64decode(payload.get("content") or "", validate=False)
    if len(raw) > max_bytes:
        return ""
    return raw.decode("utf-8", errors="replace")


def _local_capabilities(root: str, max_files: int = 180, max_bytes: int = 400_000) -> dict[str, int]:
    base = Path(root)
    if not base.exists():
        return {}
    hits: dict[str, int] = {}
    files = 0
    for path in base.rglob("*"):
        if files >= max_files:
            break
        if not path.is_file() or path.suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        lower = str(path).lower()
        if any(part in lower for part in ("node_modules", ".git/", "dist/", "build/", ".venv/", "venv/")):
            continue
        try:
            if path.stat().st_size > max_bytes:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        _merge_hits(hits, _pattern_hits(text))
        files += 1
    return hits


class FixListCrawlerResearchAgent:
    """Read-only public-repository mining agent for crawler engineering patterns."""

    def __init__(
        self,
        token: str = "",
        max_repos: int = 12,
        max_files_per_repo: int = 24,
        max_file_bytes: int = 350_000,
    ):
        self.token = token
        self.max_repos = max(1, min(int(max_repos), 30))
        self.max_files_per_repo = max(1, min(int(max_files_per_repo), 60))
        self.max_file_bytes = max(10_000, min(int(max_file_bytes), 800_000))
        self.client: Optional[GitHubReadOnlyClient] = None

    def set_up(self):
        token = self.token or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or ""
        self.client = GitHubReadOnlyClient(token=token)

    def _client(self) -> GitHubReadOnlyClient:
        if self.client is None:
            self.set_up()
        assert self.client is not None
        return self.client

    def _search(self, query: str, per_page: int = 10) -> list[dict[str, Any]]:
        q = f"{query.strip()} archived:false fork:false"
        data = self._client().get_json(
            "/search/repositories",
            {"q": q, "sort": "stars", "order": "desc", "per_page": min(max(per_page, 1), 25)},
        )
        return list(data.get("items") or [])

    def _repo_summary(self, item: dict[str, Any]) -> RepoSummary:
        license_info = item.get("license") or {}
        spdx = str(license_info.get("spdx_id") or "")
        return RepoSummary(
            full_name=str(item.get("full_name") or ""),
            html_url=str(item.get("html_url") or ""),
            description=str(item.get("description") or ""),
            language=str(item.get("language") or ""),
            stars=int(item.get("stargazers_count") or 0),
            forks=int(item.get("forks_count") or 0),
            default_branch=str(item.get("default_branch") or "main"),
            license_spdx=spdx,
            license_mode=_license_mode(spdx),
            pushed_at=str(item.get("pushed_at") or ""),
            score=_repo_score(item),
        )

    def _tree(self, repo: RepoSummary) -> list[dict[str, Any]]:
        branch = quote(repo.default_branch, safe="")
        data = self._client().get_json(f"/repos/{repo.full_name}/git/trees/{branch}", {"recursive": "1"})
        return list(data.get("tree") or [])

    def _interesting_paths(self, repo: RepoSummary) -> list[str]:
        ranked: list[tuple[int, str]] = []
        for node in self._tree(repo):
            if node.get("type") != "blob":
                continue
            path = str(node.get("path") or "")
            size = int(node.get("size") or 0)
            if size <= 0 or size > self.max_file_bytes:
                continue
            score = _source_path_score(path)
            if score >= 2:
                ranked.append((score, path))
        ranked.sort(key=lambda row: (-row[0], row[1]))
        return [path for _, path in ranked[: self.max_files_per_repo]]

    def _read_file(self, repo: RepoSummary, path: str) -> str:
        encoded_path = quote(path, safe="/")
        data = self._client().get_json(
            f"/repos/{repo.full_name}/contents/{encoded_path}",
            {"ref": repo.default_branch},
        )
        if not isinstance(data, dict):
            return ""
        return _decode_content(data, self.max_file_bytes)

    def inspect_repo(self, repo: RepoSummary) -> dict[str, Any]:
        aggregate: dict[str, int] = {}
        evidence: dict[str, list[str]] = {}
        scanned_files: list[str] = []
        for path in self._interesting_paths(repo):
            try:
                text = self._read_file(repo, path)
            except RuntimeError:
                continue
            if not text:
                continue
            scanned_files.append(path)
            hits = _pattern_hits(text)
            _merge_hits(aggregate, hits)
            for capability in hits:
                evidence.setdefault(capability, [])
                if len(evidence[capability]) < 4:
                    evidence[capability].append(path)
        return {
            "repo": asdict(repo),
            "capabilities": aggregate,
            "evidence_files": evidence,
            "files_scanned": scanned_files,
        }

    @staticmethod
    def _recommendations(public_capabilities: dict[str, int], local_capabilities: dict[str, int]) -> list[dict[str, Any]]:
        recommendations: list[dict[str, Any]] = []
        for capability, template in RECOMMENDATION_LIBRARY.items():
            if public_capabilities.get(capability, 0) <= 0:
                continue
            if local_capabilities.get(capability, 0) > 0:
                continue
            recommendations.append({
                "capability": capability,
                **template,
                "public_signal_count": public_capabilities.get(capability, 0),
            })
        priority_rank = {"P0": 0, "P1": 1, "P2": 2}
        recommendations.sort(key=lambda item: (priority_rank.get(item.get("priority", "P9"), 9), item["title"]))
        return recommendations

    def query(
        self,
        queries: Optional[list[str]] = None,
        local_root: str = ".",
        seed_repositories: Optional[list[str]] = None,
        max_repos: Optional[int] = None,
    ) -> dict[str, Any]:
        """Mine public crawler repos and compare detected patterns with FixList.

        This method performs read-only GitHub GETs. It never clones, executes,
        imports, installs, commits, pushes, opens PRs, or changes production.
        """
        queries = queries or [
            "technical SEO crawler",
            "SEO spider crawler",
            "SEO crawler Python",
        ]
        limit = self.max_repos if max_repos is None else max(1, min(int(max_repos), self.max_repos))

        by_name: dict[str, RepoSummary] = {}
        errors: list[str] = []

        for full_name in seed_repositories or []:
            try:
                item = self._client().get_json(f"/repos/{full_name}")
                summary = self._repo_summary(item)
                if summary.full_name:
                    by_name[summary.full_name] = summary
            except RuntimeError as exc:
                errors.append(str(exc))

        for query in queries:
            try:
                for item in self._search(query, per_page=min(12, limit)):
                    summary = self._repo_summary(item)
                    if summary.full_name:
                        by_name.setdefault(summary.full_name, summary)
            except RuntimeError as exc:
                errors.append(str(exc))

        repos = sorted(by_name.values(), key=lambda repo: (-repo.score, -repo.stars, repo.full_name))[:limit]
        inspected: list[dict[str, Any]] = []
        public_capabilities: dict[str, int] = {}
        capability_sources: dict[str, list[str]] = {}

        for repo in repos:
            try:
                result = self.inspect_repo(repo)
            except RuntimeError as exc:
                errors.append(f"{repo.full_name}: {exc}")
                continue
            inspected.append(result)
            for capability, count in result["capabilities"].items():
                public_capabilities[capability] = public_capabilities.get(capability, 0) + int(count)
                capability_sources.setdefault(capability, [])
                if repo.full_name not in capability_sources[capability]:
                    capability_sources[capability].append(repo.full_name)

        local_capabilities = _local_capabilities(local_root)
        recommendations = self._recommendations(public_capabilities, local_capabilities)
        for item in recommendations:
            item["source_repositories"] = capability_sources.get(item["capability"], [])[:5]

        return {
            "agent": "fixlist-crawler-research",
            "mode": "READ_ONLY_PUBLIC_REPOSITORY_RESEARCH",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "queries": queries,
            "local_root": str(Path(local_root).resolve()),
            "repositories": inspected,
            "public_capabilities": public_capabilities,
            "local_capabilities": local_capabilities,
            "recommendations": recommendations,
            "license_policy": {
                "permissive_spdx": sorted(PERMISSIVE_LICENSES),
                "rule": "Unknown/copyleft licenses are ideas-only; never copy code without explicit license review.",
            },
            "safety": {
                "network": "GitHub GET requests only",
                "third_party_code_execution": False,
                "clone_or_install": False,
                "repository_mutation": False,
                "production_mutation": False,
            },
            "errors": errors,
        }


crawler_research_agent = FixListCrawlerResearchAgent()
