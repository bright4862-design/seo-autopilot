import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const BING_WEBMASTER_API_KEY = Deno.env.get("BING_WEBMASTER_API_KEY") || "";
const BING_API_BASE = "https://ssl.bing.com/webmaster/api.svc/json";

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();

    if (!user) {
      return Response.json(
        {
          success: false,
          error: "Unauthorized",
        },
        { status: 401 }
      );
    }

    if (!BING_WEBMASTER_API_KEY) {
      return Response.json(
        {
          success: false,
          error: "BING_WEBMASTER_API_KEY is not configured in Base44 secrets.",
        },
        { status: 500 }
      );
    }

    const body = await req.json().catch(() => ({}));

    const requestedSiteUrl = normalizeSiteUrl(body.site_url || "");
    const count = clampNumber(Number(body.count || 100), 10, 250);

    const userSites = await getUserSites();

    const siteUrl =
      requestedSiteUrl ||
      userSites.find((site) => site.IsVerified)?.Url ||
      userSites[0]?.Url ||
      "";

    if (!siteUrl) {
      return Response.json(
        {
          success: false,
          error:
            "No Bing Webmaster Tools site found. Add and verify the site in Bing Webmaster Tools first.",
          user_sites: userSites,
        },
        { status: 400 }
      );
    }

    const linkCounts = await getLinkCounts(siteUrl, count);

    const topLinkedPages = normalizeLinkCounts(linkCounts).slice(0, 25);

    const sampleLinks = await getSampleLinksForTopPages({
      siteUrl,
      pages: topLinkedPages.slice(0, 5),
      count: 25,
    });

    const referringDomains = unique(
      sampleLinks
        .map((link) => {
          try {
            return new URL(link.referring_page).hostname.replace(/^www\./i, "");
          } catch {
            return "";
          }
        })
        .filter(Boolean)
    );

    const backlinksCount =
      topLinkedPages.reduce(
        (sum, page) => sum + Number(page.backlinks || 0),
        0
      ) || sampleLinks.length;

    return Response.json({
      success: true,
      provider: "bing_webmaster_tools",
      site_url: siteUrl,
      user_sites: userSites,
      backlinks_count: backlinksCount,
      referring_domains_count: referringDomains.length,
      top_linked_pages: topLinkedPages,
      sample_links: sampleLinks,
      raw: {
        link_counts: linkCounts,
      },
      note:
        "Bing backlink data only works for sites verified in Bing Webmaster Tools.",
    });
  } catch (error) {
    return Response.json(
      {
        success: false,
        error: error?.message || "getBingBacklinks failed",
      },
      { status: 500 }
    );
  }
});

async function getUserSites() {
  const json = await bingGet("GetUserSites", {});

  const data = unwrapBingD(json);

  return Array.isArray(data) ? data : [];
}

async function getLinkCounts(siteUrl: string, count: number) {
  const json = await bingGet("GetLinkCounts", {
    siteUrl,
    count: String(count),
  });

  return unwrapBingD(json);
}

async function getUrlLinks(siteUrl: string, url: string, count: number) {
  const json = await bingGet("GetUrlLinks", {
    siteUrl,
    url,
    count: String(count),
  });

  return unwrapBingD(json);
}

async function getSampleLinksForTopPages({
  siteUrl,
  pages,
  count,
}: {
  siteUrl: string;
  pages: any[];
  count: number;
}) {
  const output: any[] = [];

  for (const page of pages) {
    const targetUrl = page.page || page.url;

    if (!targetUrl) continue;

    try {
      const links = await getUrlLinks(siteUrl, targetUrl, count);
      const normalizedLinks = normalizeUrlLinks(links, targetUrl);

      output.push(...normalizedLinks);

      if (output.length >= 100) break;
    } catch {
      // Keep partial backlink data even if one URL fails.
    }
  }

  return output.slice(0, 100);
}

async function bingGet(method: string, params: Record<string, string>) {
  const url = new URL(`${BING_API_BASE}/${method}`);

  url.searchParams.set("apikey", BING_WEBMASTER_API_KEY);

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, value);
    }
  });

  const response = await fetch(url.toString(), {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
  });

  const text = await response.text();
  const json = safeJsonParse(text);

  if (!response.ok) {
    throw new Error(
      `Bing Webmaster API ${method} failed with status ${response.status}: ${text.slice(
        0,
        300
      )}`
    );
  }

  return json;
}

function unwrapBingD(json: any) {
  if (!json) return null;

  if (json.d !== undefined) return json.d;

  return json;
}

function normalizeLinkCounts(value: any) {
  const list = Array.isArray(value)
    ? value
    : Array.isArray(value?.Details)
      ? value.Details
      : Array.isArray(value?.LinkCounts)
        ? value.LinkCounts
        : Array.isArray(value?.Items)
          ? value.Items
          : [];

  return list
    .map((item: any) => {
      const page =
        item.Url ||
        item.url ||
        item.Page ||
        item.page ||
        item.TargetUrl ||
        item.targetUrl ||
        "";

      const backlinks =
        item.Count ||
        item.count ||
        item.LinkCount ||
        item.linkCount ||
        item.AnchorCount ||
        item.anchorCount ||
        0;

      return {
        page,
        url: page,
        backlinks: Number(backlinks || 0),
      };
    })
    .filter((item) => item.page)
    .sort((a, b) => Number(b.backlinks || 0) - Number(a.backlinks || 0));
}

function normalizeUrlLinks(value: any, targetUrl: string) {
  const list = Array.isArray(value)
    ? value
    : Array.isArray(value?.Details)
      ? value.Details
      : Array.isArray(value?.Links)
        ? value.Links
        : Array.isArray(value?.Items)
          ? value.Items
          : [];

  return list
    .map((item: any) => {
      const referringPage =
        item.Url ||
        item.url ||
        item.SourceUrl ||
        item.sourceUrl ||
        item.ReferringUrl ||
        item.referringUrl ||
        item.ReferringPage ||
        item.referringPage ||
        "";

      const anchorText =
        item.AnchorText ||
        item.anchorText ||
        item.Anchor ||
        item.anchor ||
        item.Text ||
        item.text ||
        "";

      const linkedPage =
        item.TargetUrl ||
        item.targetUrl ||
        item.LinkedUrl ||
        item.linkedUrl ||
        targetUrl;

      return {
        referring_page: referringPage,
        linked_page: linkedPage,
        page: linkedPage,
        anchor_text: anchorText,
        query: anchorText,
      };
    })
    .filter((item) => item.referring_page || item.anchor_text);
}

function normalizeSiteUrl(value: string) {
  const raw = String(value || "").trim();

  if (!raw) return "";

  try {
    const withProtocol = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
    const url = new URL(withProtocol);

    if (!url.pathname || url.pathname === "") {
      url.pathname = "/";
    }

    return url.toString();
  } catch {
    return raw;
  }
}

function safeJsonParse(value: string) {
  try {
    if (!value) return null;

    return JSON.parse(value);
  } catch {
    return null;
  }
}

function unique(values: string[]) {
  return Array.from(new Set(values.filter(Boolean)));
}

function clampNumber(value: number, min: number, max: number) {
  if (!Number.isFinite(value)) return min;

  return Math.max(min, Math.min(max, value));
}