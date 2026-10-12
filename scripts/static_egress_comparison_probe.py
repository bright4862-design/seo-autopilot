"""One isolated Standard 150 comparison; no application credentials or writes.

The process-local guard only refuses requests or slows them down. Allowed hops
still use the image's original DNS-pinned, TLS-verified transport. Neither the
production scanner files nor customer-facing routes are changed.
"""
import asyncio
from contextlib import contextmanager
import ipaddress
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from urllib import robotparser

import httpx

from app import canonical_validation, coverage_probes, redirect_validation, robots_policy, scanner, security
from app.page_evidence_gate import detect_access_block, page_evidence_class

TARGETS = {
    "winamax": "https://www.winamax.fr/",
    "ratp": "https://www.ratp.fr/",
    "viator": "https://www.viator.com/",
    "klook": "https://www.klook.com/",
    "fever": "https://feverup.com/",
    "ironwood": "https://ironwoodcrecapital.com/",
    "funbooker": "https://www.funbooker.com/",
}
USER_AGENT = "Mozilla/5.0 (compatible; FixListPythonScanner/1.0)"
IMAGE_REPOSITORY = "europe-west1-docker.pkg.dev/seo-autopilot-501517/cloud-run-source-deploy/fixlist-standard150-worker"
DIAGNOSTIC = "static_egress_comparison_v1"
MAX_HTTP_HOPS = 200
_sleep = asyncio.sleep
_monotonic = time.monotonic


def public_ipv4(value):
    address = ipaddress.IPv4Address(value)
    if not security._is_public_ip(value) or str(address) != value:
        raise ValueError("Canonical public IPv4 required")
    return value


def configuration(environment):
    names = ("TARGET", "PROFILE", "EXPECTED_IP", "SOURCE_SHA", "REVISION", "IMAGE")
    values = {name.lower(): environment.get("FIXLIST_COMPARISON_" + name, "") for name in names}
    if (values["target"] not in TARGETS or values["profile"] not in {"default", "static"}
            or not re.fullmatch(r"[0-9a-f]{40}", values["source_sha"])
            or not re.fullmatch(r"fixlist-standard150-worker-[a-z0-9]+(?:-[a-z0-9]+)*", values["revision"])
            or not re.fullmatch(re.escape(IMAGE_REPOSITORY) + r"@sha256:[0-9a-f]{64}", values["image"])):
        raise ValueError("Invalid comparison configuration")
    public_ipv4(values["expected_ip"])
    forbidden = {"http_proxy", "https_proxy", "all_proxy", "no_proxy", "ssl_cert_file", "ssl_cert_dir",
                 "requests_ca_bundle", "curl_ca_bundle", "scan_evidence_signing_key", "scanner_api_key",
                 "base44_app_id", "base44_api_url"}
    if any(name.lower() in forbidden for name in environment):
        raise ValueError("Production credentials, proxies and custom certificates are forbidden")
    return values


class RobotsRefusal(Exception):
    """A fixed, non-sensitive stop signal; never a transport bypass."""


class RobotsGuard:
    """One origin, known robots, serial paced hops and a finite total budget."""

    def __init__(self, origin):
        self.origin = origin
        self.policy = None
        self.hops = self.refusals = 0
        self.unknown_seen = self.disallowed_seen = False
        self.scope_refused = self.pressure_seen = self.budget_exhausted = False
        self.last_started = None
        self.lock = asyncio.Lock()
        self.original_fetch = security.safe_get_once
        self.original_loader = robots_policy.load_robots_policy

    def refuse(self):
        self.refusals += 1
        return None

    def observe_pressure(self, response):
        if response is not None and (response.status_code == 429 or "retry-after" in response.headers):
            self.pressure_seen = True

    async def load_policy(self, client, origin):
        if origin != self.origin:
            self.scope_refused = True
            self.refuse()
            raise RobotsRefusal()
        self.policy = await self.original_loader(client, origin)
        if not self.policy.rules_known:
            self.unknown_seen = True
            raise RobotsRefusal()
        if self.policy.allowed(robots_policy.SCANNER_USER_AGENT, origin + "/") is not True:
            self.disallowed_seen = True
            raise RobotsRefusal()
        return self.policy

    def interval(self):
        seconds = 0.5
        if self.policy is not None and self.policy.parser is not None:
            parser = self.policy.parser
            delay = parser.crawl_delay(robots_policy.SCANNER_USER_AGENT)
            rate = parser.request_rate(robots_policy.SCANNER_USER_AGENT)
            if delay is not None:
                seconds = max(seconds, float(delay))
            if rate is not None and rate.requests > 0:
                seconds = max(seconds, float(rate.seconds) / rate.requests)
        return seconds

    def observe_robots(self, response):
        # Sitemap discovery reads robots independently of scanner.load_robots_policy.
        # Refresh the guard on every robots response, so a later failure or changed
        # Disallow cannot reuse a previous allow. Parsing mirrors the image's loader.
        url = self.origin + "/robots.txt"
        status = int(response.status_code) if response is not None else 0
        if response is None:
            policy = robots_policy.RobotsPolicy(url, "unavailable", 0)
        elif detect_access_block(status, response.headers, response.text):
            policy = robots_policy.RobotsPolicy(url, "access_limited", status)
        elif status in {404, 410}:
            policy = robots_policy.RobotsPolicy(url, "missing", status)
        elif not 200 <= status < 300:
            policy = robots_policy.RobotsPolicy(url, "access_limited", status)
        else:
            parser = robotparser.RobotFileParser()
            parser.set_url(url)
            parser.parse(response.text.splitlines())
            policy = robots_policy.RobotsPolicy(url, "available", status, parser)
        self.policy = policy
        if not policy.rules_known:
            self.unknown_seen = True
        elif policy.directive_allowed(robots_policy.SCANNER_USER_AGENT, self.origin + "/") is not True:
            self.disallowed_seen = True

    async def fetch(self, client, url, *, max_decoded_bytes=None):
        try:
            parsed = urlsplit(str(url))
            origin = f"{parsed.scheme}://{parsed.netloc}"
            if origin != self.origin or parsed.username or parsed.password or parsed.fragment:
                self.scope_refused = True
                return self.refuse()
            is_robots = parsed.path == "/robots.txt" and not parsed.query
        except ValueError:
            self.scope_refused = True
            return self.refuse()
        async with self.lock:
            if self.pressure_seen:
                return self.refuse()
            if self.hops >= MAX_HTTP_HOPS:
                self.budget_exhausted = True
                return self.refuse()
            if not is_robots:
                if self.policy is None or not self.policy.rules_known:
                    self.unknown_seen = True
                    return self.refuse()
                if self.policy.allowed(robots_policy.SCANNER_USER_AGENT, str(url)) is not True:
                    self.disallowed_seen = True
                    return self.refuse()
            if self.last_started is not None:
                # A required robots wait is never shortened to fit a deadline.
                await _sleep(max(0.0, self.interval() - (_monotonic() - self.last_started)))
            self.last_started = _monotonic()
            self.hops += 1
            try:
                response = await self.original_fetch(client, url, max_decoded_bytes=max_decoded_bytes)
            except BaseException:
                if is_robots:
                    self.observe_robots(None)
                raise
            if is_robots:
                self.observe_robots(response)
            self.observe_pressure(response)
            return response

    @contextmanager
    def activate(self):
        aliases = (security, redirect_validation, canonical_validation, coverage_probes)
        previous = [(module, module.safe_get_once) for module in aliases]
        old_loader = scanner.load_robots_policy
        old_allowed = robots_policy.RobotsPolicy.allowed
        old_client = httpx.AsyncClient
        guard = self

        def strict_allowed(policy, user_agent, url):
            current = guard.policy if guard.policy is not None else policy
            allowed = old_allowed(current, user_agent, url)
            if allowed is None:
                guard.unknown_seen = True
            return allowed is True

        async def pressure_headers(response):
            # HTTPX calls response hooks before body decoding. Stop after pressure
            # even if the unchanged bounded decoder subsequently rejects the body.
            guard.observe_pressure(response)

        class StrictClient(old_client):
            def __init__(self, *args, **kwargs):
                kwargs["trust_env"] = False
                kwargs["follow_redirects"] = False
                hooks = {name: list(handlers) for name, handlers in (kwargs.get("event_hooks") or {}).items()}
                hooks.setdefault("response", []).append(pressure_headers)
                kwargs["event_hooks"] = hooks
                super().__init__(*args, **kwargs)

        try:
            for module in aliases:
                module.safe_get_once = self.fetch
            scanner.load_robots_policy = self.load_policy
            robots_policy.RobotsPolicy.allowed = strict_allowed
            httpx.AsyncClient = StrictClient
            with robots_policy.owner_robots_override(False):
                yield
        finally:
            for module, previous_fetch in previous:
                module.safe_get_once = previous_fetch
            scanner.load_robots_policy = old_loader
            robots_policy.RobotsPolicy.allowed = old_allowed
            httpx.AsyncClient = old_client


def summarize(result, row):
    pages = result.get("pages") or result.get("crawled_pages") or []
    pages = pages[:150] if isinstance(pages, list) else []
    row["pages_crawled"] = len(pages)
    row["scan_deadline_reached"] = result.get("scan_deadline_reached") is True
    row["scan_completed"] = result.get("success") is True
    for page in pages:
        if not isinstance(page, dict):
            continue
        status = page.get("status_code")
        status = status if isinstance(status, int) and not isinstance(status, bool) else 0
        error = page.get("fetch_error") or page.get("error") or ""
        row["http_403_pages"] += status == 403
        row["http_429_pages"] += status == 429
        if page.get("robots_txt_fetch_allowed") is False or error in {
            "blocked_by_robots_txt", "redirect_destination_blocked_by_robots",
        }:
            row["robots_blocked_pages"] += 1
        elif status in {401, 403, 429} or page.get("access_block_kind") in {"block", "challenge", "rate_limit"}:
            row["access_limited_pages"] += 1
        elif status == 0 or status >= 500 or error:
            row["transport_failure_pages"] += 1
        elif status == 200 and page_evidence_class(page) == "usable_html":
            row["usable_html_pages"] += 1


async def run_probe(environment):
    config = configuration(environment)  # All identity checks precede networking.
    if USER_AGENT not in Path(scanner.__file__).read_text(encoding="utf-8"):
        raise ValueError("Unsupported scanner identity")
    started = _monotonic()
    origin = TARGETS[config["target"]].rstrip("/")
    guard = RobotsGuard(origin)
    row = {"diagnostic": DIAGNOSTIC, "event": "complete", **config,
           "observed_ip": "", "static_ip_verified": False, "classification": "inconclusive",
           "robots_status": "not_checked", "robots_status_code": 0,
           "pages_crawled": 0, "usable_html_pages": 0, "access_limited_pages": 0,
           "robots_blocked_pages": 0, "transport_failure_pages": 0,
           "http_403_pages": 0, "http_429_pages": 0, "elapsed_ms": 0,
           "scan_deadline_reached": False, "authoritative_scan": False, "worker_process": False,
           "scan_completed": False, "robots_unknown_seen": False, "robots_disallowed_seen": False,
           "pressure_seen": False, "http_hops": 0, "guard_refusals": 0, "failure_code": ""}

    async def execute():
        try:
            async with httpx.AsyncClient(timeout=20, trust_env=False, follow_redirects=False,
                                         headers={"User-Agent": USER_AGENT}) as client:
                guard.hops += 1
                response = await guard.original_fetch(client, "https://api.ipify.org", max_decoded_bytes=64)
            if response is None or response.status_code != 200:
                raise ValueError()
            row["observed_ip"] = public_ipv4(response.text.strip())
        except Exception:
            row.update(classification="transport_failure", failure_code="ip_probe_failed")
            return
        if config["profile"] == "static":
            if row["observed_ip"] != config["expected_ip"]:
                row["failure_code"] = "source_ip_mismatch"
                return
            row["static_ip_verified"] = True
        with guard.activate():
            try:
                async with httpx.AsyncClient(timeout=10, headers={"User-Agent": USER_AGENT}) as client:
                    await guard.load_policy(client, origin)
                result = await asyncio.wait_for(scanner.run_scan(
                    website_url=TARGETS[config["target"]], scan_mode="advanced",
                    timeout_seconds=210, job_mode=True,
                ), timeout=135)
                summarize(result, row)
            except RobotsRefusal:
                pass
            except asyncio.TimeoutError:
                row["failure_code"] = "scanner_timeout"
            except Exception:
                row["failure_code"] = "scanner_failed"
        if guard.budget_exhausted:
            row["failure_code"] = "request_budget_exhausted"
        if guard.unknown_seen:
            row["classification"] = "robots_unknown"
        elif row["usable_html_pages"]:
            row["classification"] = "usable_html"
        elif row["access_limited_pages"] or guard.pressure_seen:
            row["classification"] = "access_limited"
        elif guard.disallowed_seen or row["robots_blocked_pages"]:
            row["classification"] = "robots_blocked"
        elif not guard.scope_refused and row["transport_failure_pages"]:
            row["classification"] = "transport_failure"

    try:
        await asyncio.wait_for(execute(), timeout=190)
    except asyncio.TimeoutError:
        row["failure_code"] = "probe_timeout"
    if guard.policy is not None:
        row["robots_status"] = guard.policy.status
        row["robots_status_code"] = min(599, max(0, int(guard.policy.status_code)))
    row.update(robots_unknown_seen=guard.unknown_seen, robots_disallowed_seen=guard.disallowed_seen,
               pressure_seen=guard.pressure_seen, http_hops=min(MAX_HTTP_HOPS, guard.hops),
               guard_refusals=min(MAX_HTTP_HOPS, guard.refusals),
               elapsed_ms=min(210000, max(0, round((_monotonic() - started) * 1000))))
    return row


def main(environment=None):
    try:
        row = asyncio.run(run_probe(os.environ if environment is None else environment))
    except ValueError:
        print(json.dumps({"diagnostic": DIAGNOSTIC, "event": "error", "failure_code": "invalid_configuration"}), flush=True)
        return 2
    except Exception:
        print(json.dumps({"diagnostic": DIAGNOSTIC, "event": "error", "failure_code": "probe_failed"}), flush=True)
        return 1
    print(json.dumps(row, separators=(",", ":")), flush=True)
    return int(bool(row["failure_code"]))


if __name__ == "__main__":
    raise SystemExit(main())
