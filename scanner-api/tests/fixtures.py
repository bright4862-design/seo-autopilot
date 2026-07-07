"""Small synthetic fixtures that mimic each site's failure pattern.

Deliberately minimal and hand-written — no real third-party HTML. Enough to
lock the scanner contract for known regressions. A second layer of sanitized
real-HTML samples can be added once the scanner is stable.
"""


def _sitemap(locs: list[str]) -> str:
    body = "".join(f"<url><loc>{loc}</loc></url>" for loc in locs)
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>'


def _page(title: str, *, h1: str = "Heading", meta: str = "", canonical: str = "", body: str = "Some readable content for this page.", links: list[str] | None = None) -> str:
    head = f"<title>{title}</title>"
    if meta:
        head += f'<meta name="description" content="{meta}">'
    if canonical:
        head += f'<link rel="canonical" href="{canonical}">'
    anchors = "".join(f'<a href="{href}">link</a>' for href in (links or []))
    return f"<html><head>{head}</head><body><h1>{h1}</h1><p>{body}</p>{anchors}</body></html>"


def _html(body): return {"body": body, "status": 200, "content_type": "text/html"}
def _xml(body): return {"body": body, "status": 200, "content_type": "application/xml"}
def _text(body): return {"body": body, "status": 200, "content_type": "text/plain"}
def _status(code): return {"body": "", "status": code, "content_type": "text/html"}


# --- Pretto: same-prefix sitemap + article pages, must NOT invent a trust page ---
PRETTO_ORIGIN = "https://www.pretto.fr"
PRETTO_START = "https://www.pretto.fr/pret-immobilier"
PRETTO_PREFIX = "/pret-immobilier"
PRETTO_ROUTES = {
    f"{PRETTO_ORIGIN}/robots.txt": _text(f"User-agent: *\nSitemap: {PRETTO_ORIGIN}/sitemap.xml\n"),
    f"{PRETTO_ORIGIN}/sitemap.xml": _xml(_sitemap([
        f"{PRETTO_ORIGIN}/pret-immobilier",
        f"{PRETTO_ORIGIN}/pret-immobilier/taux",
        f"{PRETTO_ORIGIN}/pret-immobilier/simulation",
        f"{PRETTO_ORIGIN}/pret-immobilier/guide-achat",
        f"{PRETTO_ORIGIN}/blog/actualites",  # off-prefix: must be excluded
    ])),
    f"{PRETTO_ORIGIN}/pret-immobilier": _html(_page("Prêt immobilier")),
    f"{PRETTO_ORIGIN}/pret-immobilier/taux": _html(_page("Taux de prêt")),
    f"{PRETTO_ORIGIN}/pret-immobilier/simulation": _html(_page("Simulation de prêt")),
    f"{PRETTO_ORIGIN}/pret-immobilier/guide-achat": _html(_page("Guide achat")),
    f"{PRETTO_ORIGIN}/blog/actualites": _html(_page("Actualités")),
}


# --- Meilleurtaux: encoded/base64 artifact links mixed with real section pages ---
MT_ORIGIN = "https://www.meilleurtaux.fr"
MT_START = "https://www.meilleurtaux.fr/assurance"
MT_PREFIX = "/assurance"
_ARTIFACT_1 = f"{MT_ORIGIN}/assurance/aHR0cHM6Ly9ldmlsLmV4YW1wbGUvcGF5bG9hZA/"
_ARTIFACT_2 = f"{MT_ORIGIN}/assurance/L2V0Yy9wYXNzd2Qvc2VjcmV0L2RlZXAvcGF0aA/"
MT_ROUTES = {
    f"{MT_ORIGIN}/sitemap.xml": _xml(_sitemap([
        f"{MT_ORIGIN}/assurance",
        f"{MT_ORIGIN}/assurance/auto",
        f"{MT_ORIGIN}/assurance/habitation",
        _ARTIFACT_1,
        _ARTIFACT_2,
    ])),
    f"{MT_ORIGIN}/assurance": _html(_page("Assurance", meta="Assurance", canonical=f"{MT_ORIGIN}/assurance")),
    f"{MT_ORIGIN}/assurance/auto": _html(_page("Assurance auto")),
    f"{MT_ORIGIN}/assurance/habitation": _html(_page("Assurance habitation")),
}


# --- Funbooker: category pages with duplicate internal links (dedup check) ---
FB_ORIGIN = "https://www.funbooker.com"
FB_START = "https://www.funbooker.com/activites"
FB_PREFIX = "/activites"
FB_ROUTES = {
    f"{FB_ORIGIN}/sitemap.xml": _xml(_sitemap([
        f"{FB_ORIGIN}/activites",
        f"{FB_ORIGIN}/activites/paris",
        f"{FB_ORIGIN}/activites/lyon",
    ])),
    # Links to /activites/paris TWICE plus once in sitemap -> must crawl once.
    f"{FB_ORIGIN}/activites": _html(_page(
        "Activités", meta="Nos activités", canonical=f"{FB_ORIGIN}/activites",
        links=["/activites/paris", "/activites/paris", "/activites/lyon"],
    )),
    f"{FB_ORIGIN}/activites/paris": _html(_page("Activités Paris")),
    f"{FB_ORIGIN}/activites/lyon": _html(_page("Activités Lyon")),
}


# --- Center Street: 429 pages -> scan-coverage cards only, not "broken page" ---
CS_ORIGIN = "https://www.centerstreetlending.com"
CS_START = "https://www.centerstreetlending.com/"
CS_PREFIX = "/"
CS_ROUTES = {
    f"{CS_ORIGIN}/sitemap.xml": _xml(_sitemap([
        f"{CS_ORIGIN}/",
        f"{CS_ORIGIN}/loans",
        f"{CS_ORIGIN}/rates",
    ])),
    f"{CS_ORIGIN}/": _html(_page("Center Street Lending", meta="Home", canonical=f"{CS_ORIGIN}/")),
    f"{CS_ORIGIN}/loans": _status(429),
    f"{CS_ORIGIN}/rates": _status(429),
}
