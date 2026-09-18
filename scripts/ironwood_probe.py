"""Fixed, bounded diagnostic run inside the existing worker image; no scan writes."""
import asyncio
import hashlib
import json
import platform
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup

from app.page_evidence_gate import detect_access_block
from app.security import safe_get_once

ORIGIN = "https://ironwoodcrecapital.com"
OLD_UA = "Mozilla/5.0 (compatible; FixListPythonScanner/1.0)"
NEW_UA = "FixListBot/1.0 (+https://getfixlist.com/crawler)"
HEADERS = ("sg-captcha", "cf-mitigated", "server", "x-robots-tag", "content-type", "retry-after")


def target(value):
    """Record destination without query, fragment or embedded credentials; never fetch it."""
    try:
        parsed = urlsplit(urljoin(ORIGIN + "/", value))
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            return "unsupported_or_redacted"
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))[:512]
    except ValueError:
        return "invalid"


def evidence(response):
    refresh = ""
    if response.content:
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup.find_all("meta"):
            if str(tag.get("http-equiv", "")).lower() == "refresh":
                match = re.search(r"url\s*=\s*(.*)", str(tag.get("content", "")), re.I)
                if match:
                    refresh = target(match.group(1).strip().strip("\"'"))
                    break
    return {"status_code": response.status_code,
            "headers": {name: response.headers[name][:200] for name in HEADERS if name in response.headers},
            "redirect_target": target(response.headers["location"]) if "location" in response.headers else "",
            "meta_refresh_target": refresh, "target_query_and_fragment_redacted": True,
            "decoded_response_bytes": len(response.content),
            "challenge": detect_access_block(response.status_code, response.headers, response.text)}


async def compare(emit):
    matrix = [(path, profile, ua) for path in ("/", "/robots.txt", "/sitemap.xml")
              for profile, ua in (("production", OLD_UA), ("transparent", NEW_UA))]
    matrix.append(("/", "production_repeat", OLD_UA))
    baseline_repeat_allowed, count, stop = False, 0, "matrix_complete"
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        for path, profile, ua in matrix:
            if profile == "production_repeat" and not baseline_repeat_allowed:
                continue
            if count:
                await asyncio.sleep(5)
            client.cookies.clear()  # Each comparison starts without challenge/session cookies.
            client.headers["User-Agent"] = ua
            count += 1
            row = {"event": "response", "request_number": count, "path": path,
                   "profile": profile, "user_agent": ua,
                   "utc": datetime.now(timezone.utc).isoformat()}
            started = time.monotonic()
            try:
                response = await asyncio.wait_for(
                    safe_get_once(client, ORIGIN + path, max_decoded_bytes=2_000_000), timeout=15)
                if response is None:
                    row["error"] = "ssrf_or_dns_refusal"
                else:
                    row.update(evidence(response))
            except (httpx.HTTPError, TimeoutError) as exc:
                row["error"] = type(exc).__name__  # Never dump request/credential-bearing errors.
            row["elapsed_ms"] = round((time.monotonic() - started) * 1000)
            emit(row)
            if count == 1:
                baseline_repeat_allowed = bool(row.get("status_code") == 200 and not row.get("challenge"))
            if row.get("status_code") == 429:
                stop = "rate_limited"
                break
            if row.get("error"):
                stop = "incomplete_network_evidence"
                break
    emit({"event": "complete", "requests": count, "stop_reason": stop,
          "authoritative_scan": False, "source_ip_equivalence_verified": False})


def main():
    scanner = Path("/app/app/scanner.py")
    if OLD_UA not in scanner.read_text():
        raise SystemExit("Refusing: image no longer contains the expected production UA")
    if httpx.__version__ != "0.28.1":
        raise SystemExit("Refusing: unsupported HTTP client version")
    def emit(row):
        print(json.dumps({"diagnostic": "ironwood_v1", **row}), flush=True)
    emit({"event": "runtime", "python": platform.python_version(), "httpx": httpx.__version__,
          "security_module_sha256": hashlib.sha256(Path("/app/app/security.py").read_bytes()).hexdigest(),
          "scanner_module_sha256": hashlib.sha256(scanner.read_bytes()).hexdigest(),
          "sequential": True, "gap_seconds": 5, "request_timeout_seconds": 15,
          "redirects_followed": False, "cookies_replayed": False,
          "worker_process": False, "source_ip_equivalence_verified": False})
    asyncio.run(compare(emit))


if __name__ == "__main__":
    main()
