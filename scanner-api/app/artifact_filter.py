import re
from urllib.parse import parse_qsl, unquote, urlparse

MAX_ARTIFACT_EVIDENCE = 50
ARTIFACT_FILTER_VERSION = "artifact_filter_v4_wordpress_route_noise"
WORDPRESS_ROUTE_NOISE_VERSION = "wordpress_route_noise_v1_default_utility_routes"

_ENCODED_URL_MARKERS = ("%2f", "%3a", "http%3a", "https%3a")
_BASE64_PREFIXES = ("aHR0", "L2", "eyJ", "PHN2", "PD94", "data:")
_URL_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9+/_=-]+={0,2}$")
_HUMAN_SLUG_CHUNK = re.compile(r"^[a-z0-9]{1,24}$")

# Exact WordPress technical endpoints that cannot provide public page-level SEO
# evidence. Keep this list deliberately narrow: public categories, tags, authors,
# posts, products, and other CMS routes remain crawlable.
_WORDPRESS_TECHNICAL_EXACT_PATHS = {
    "/wp-login.php",
    "/wp-comments-post.php",
    "/wp-cron.php",
    "/wp-signup.php",
    "/wp-activate.php",
    "/xmlrpc.php",
}
_WORDPRESS_DEFAULT_CONTENT_PATHS = {
    "/hello-world",
    "/sample-page",
    "/category/uncategorized",
}
_WORDPRESS_NOISE_QUERY_KEYS = {
    "feed",
    "replytocom",
    "rest_route",
}

# XML and XML.GZ are deliberately excluded: they can be sitemap indexes or URL sets.
# These suffixes represent resources that must never become page-level SEO evidence.
_NON_HTML_RESOURCE_SUFFIXES = (
    ".avif",
    ".bmp",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".tif",
    ".tiff",
    ".webp",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".csv",
    ".md",
    ".txt",
    ".css",
    ".js",
    ".mjs",
    ".map",
    ".eot",
    ".otf",
    ".ttf",
    ".woff",
    ".woff2",
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".tar.gz",
    ".tgz",
    ".bz2",
    ".mp3",
    ".m4a",
    ".ogg",
    ".wav",
    ".avi",
    ".mov",
    ".mp4",
    ".webm",
)


def _path_from_url(url: str) -> str:
    try:
        return urlparse(url).path or url
    except Exception:
        return url


def _normalized_route_parts(url: str) -> tuple[str, set[str]]:
    try:
        parsed = urlparse(str(url or "").strip())
    except Exception:
        return "", set()
    path = unquote(parsed.path or "/").lower()
    path = re.sub(r"/+", "/", path)
    if len(path) > 1:
        path = path.rstrip("/")
    query_keys = {
        str(key or "").strip().lower()
        for key, _ in parse_qsl(parsed.query or "", keep_blank_values=True)
        if str(key or "").strip()
    }
    return path or "/", query_keys


def is_wordpress_route_noise_url(url: str) -> bool:
    """Return True only for high-confidence WordPress utility/default routes.

    These URLs can be linked by themes, starter content, feeds, login redirects,
    Jetpack, or REST endpoints, but they should not consume page slots or create
    canonical, redirect, metadata, or content findings. Legitimate public archive
    and content routes are intentionally outside this filter.
    """
    path, query_keys = _normalized_route_parts(url)
    if not path:
        return False
    if path in _WORDPRESS_TECHNICAL_EXACT_PATHS:
        return True
    if path in _WORDPRESS_DEFAULT_CONTENT_PATHS:
        return True
    if path == "/wp-admin" or path.startswith("/wp-admin/"):
        return True
    if path == "/wp-json" or path.startswith("/wp-json/"):
        return True
    if path == "/feed" or path.endswith("/feed"):
        return True
    if path == "/trackback" or path.endswith("/trackback"):
        return True
    return bool(query_keys & _WORDPRESS_NOISE_QUERY_KEYS)


def is_non_html_resource_url(url: str) -> bool:
    """Return True for resource paths that cannot provide HTML page evidence.

    This is an early queue/sitemap guard. Response content type remains the final
    authority for extensionless routes, but obvious assets should never consume a
    page slot or influence scoring, sampling, classification, or page-family totals.
    """
    path = unquote(_path_from_url(str(url or ""))).lower().rstrip("/")
    if not path:
        return False
    return path.endswith(_NON_HTML_RESOURCE_SUFFIXES)


def _looks_like_human_slug(segment: str) -> bool:
    """Return True for normal SEO slugs such as long blog/article/product paths.

    The old artifact filter treated any 32+ char URL-safe segment as encoded data.
    That accidentally suppressed real sitemap URLs like
    /blog/benefits-of-using-bridge-loans-for-real-estate-transactions.
    Human slugs usually contain several hyphen/underscore-separated word chunks;
    encoded blobs usually do not.
    """
    decoded = unquote(str(segment or "")).strip().lower().strip("/")
    if not decoded:
        return False
    if "-" not in decoded and "_" not in decoded:
        return False
    chunks = [chunk for chunk in re.split(r"[-_]+", decoded) if chunk]
    wordish = [chunk for chunk in chunks if _HUMAN_SLUG_CHUNK.fullmatch(chunk) and re.search(r"[a-z]", chunk)]
    return len(wordish) >= 3


def _looks_like_encoded_segment(segment: str) -> bool:
    raw = str(segment or "").strip().strip("/")
    if not raw:
        return False
    decoded = unquote(raw)
    lowered = raw.lower()

    # Explicit encoded URLs should still be suppressed.
    if "%2f" in lowered and ("%3a" in lowered or "http" in decoded.lower()):
        return True

    # Common base64 / JWT / encoded-HTML prefixes. These are much safer than
    # classifying every long hyphenated string as encoded data.
    if raw.startswith(_BASE64_PREFIXES):
        return True

    # Do not treat normal multi-word SEO slugs as artifacts, even when long.
    if _looks_like_human_slug(raw):
        return False

    # Long URL-safe blobs with no human word separators are likely encoded.
    compact = raw.rstrip("=")
    if len(compact) >= 48 and _URL_SAFE_TOKEN.fullmatch(raw):
        has_mixed_case = any(ch.islower() for ch in raw) and any(ch.isupper() for ch in raw)
        has_digit = any(ch.isdigit() for ch in raw)
        has_token_chars = any(ch in raw for ch in "+/_=")
        if has_token_chars or (has_mixed_case and has_digit) or len(compact) >= 80:
            return True

    return False


def is_artifact_url(url: str) -> bool:
    text = str(url or "").strip()
    if not text:
        return False

    if is_non_html_resource_url(text):
        return True
    if is_wordpress_route_noise_url(text):
        return True

    path = _path_from_url(text)
    decoded_path = unquote(path)
    lowered_path = path.lower()

    if "%2f" in lowered_path and ("%3a" in lowered_path or "http" in decoded_path.lower()):
        return True

    return any(_looks_like_encoded_segment(segment) for segment in path.split("/") if segment)


def record_artifact(target: list[dict], url: str, discovered_from: str, source_page: str = "", link_text: str = "") -> None:
    if len(target) >= MAX_ARTIFACT_EVIDENCE:
        return
    if is_non_html_resource_url(url):
        reason = "non_html_resource_path"
    elif is_wordpress_route_noise_url(url):
        reason = "wordpress_route_noise"
    else:
        reason = "encoded_or_base64_like_path"
    target.append({
        "url": str(url or "")[:500],
        "path": urlparse(str(url or "")).path[:500],
        "url_confidence": "crawler_artifact",
        "url_suspicion_reasons": [reason],
        "discovered_from": [discovered_from or "unknown"],
        "source_pages": [source_page] if source_page else [],
        "link_text_samples": [link_text[:160]] if link_text else [],
        "suppressed_from_crawl": True,
    })
