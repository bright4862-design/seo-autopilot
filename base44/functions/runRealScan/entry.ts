import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const GOOGLE_CLIENT_ID = Deno.env.get("GOOGLE_CLIENT_ID") || "";
const GOOGLE_CLIENT_SECRET = Deno.env.get("GOOGLE_CLIENT_SECRET") || "";

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

    const body = await req.json().catch(() => ({}));

    const days = clampNumber(Number(body.days || 28), 7, 90);
    const refreshToken = String(body.refresh_token || "").trim();
    let accessToken = String(body.access_token || "").trim();
    let connectionUpdate: Record<string, unknown> | null = null;

    if (!accessToken && !refreshToken) {
      return Response.json(
        {
          success: false,
          error:
            "Missing Google access token. Connect Google Search Console first.",
        },
        { status: 400 }
      );
    }

    if (refreshToken) {
      const refreshed = await refreshGoogleAccessToken(refreshToken);

      if (refreshed.access_token) {
        accessToken = refreshed.access_token;

        connectionUpdate = {
          access_token: refreshed.access_token,
          expires_in: refreshed.expires_in || 3600,
          expires_at:
            Date.now() + Number(refreshed.expires_in || 3600) * 1000,
          token_type: refreshed.token_type || "Bearer",
          refreshed_at: new Date().toISOString(),
        };
      }
    }

    const sites = await listSearchConsoleSites(accessToken);

    const requestedSiteUrl = String(body.site_url || "").trim();

    const siteUrl =
      requestedSiteUrl ||
      sites?.[0]?.siteUrl ||
      sites?.[0]?.url ||
      "";

    if (!siteUrl) {
      return Response.json(
        {
          success: false,
          error:
            "No Search Console property found. Make sure the connected Google account has access to a verified site.",
          sites,
          connection_update: connectionUpdate,
        },
        { status: 400 }
      );
    }

    await assertPublicHttpUrlIfPresent(siteUrl);

    const { startDate, endDate } = getSearchConsoleDateRange(days);

    const queryRows = await querySearchAnalytics({
      accessToken,
      siteUrl,
      startDate,
      endDate,
      dimensions: ["query"],
      rowLimit: 1000,
    });

    const pageRows = await querySearchAnalytics({
      accessToken,
      siteUrl,
      startDate,
      endDate,
      dimensions: ["page"],
      rowLimit: 1000,
    });

    const pageQueryRows = await querySearchAnalytics({
      accessToken,
      siteUrl,
      startDate,
      endDate,
      dimensions: ["page", "query"],
      rowLimit: 2000,
    });

    const keywordOpportunities = buildKeywordOpportunities(queryRows);
    const lowCtrPages = buildLowCtrPages(pageRows);
    const topPages = buildTopPages(pageRows);
    const pageKeywordOpportunities =
      buildPageKeywordOpportunities(pageQueryRows);

    return Response.json({
      success: true,
      provider: "google_search_console",
      site_url: siteUrl,
      date_range: {
        start_date: startDate,
        end_date: endDate,
        days,
      },
      sites,
      totals: buildTotals(pageRows),
      keyword_opportunities: keywordOpportunities,
      low_ctr_pages: lowCtrPages,
      top_pages: topPages,
      page_keyword_opportunities: pageKeywordOpportunities,
      raw_counts: {
        query_rows: queryRows.length,
        page_rows: pageRows.length,
        page_query_rows: pageQueryRows.length,
      },
      connection_update: connectionUpdate,
    });
  } catch (error) {
    return Response.json(
      {
        success: false,
        error: error?.message || "getSearchConsoleInsights failed",
      },
      { status: 500 }
    );
  }
});

async function refreshGoogleAccessToken(refreshToken: string) {
  if (!GOOGLE_CLIENT_ID || !GOOGLE_CLIENT_SECRET) {
    throw new Error(
      "GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET is missing in Base44 secrets."
    );
  }

  const body = new URLSearchParams();

  body.set("client_id", GOOGLE_CLIENT_ID);
  body.set("client_secret", GOOGLE_CLIENT_SECRET);
  body.set("refresh_token", refreshToken);
  body.set("grant_type", "refresh_token");

  const response = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body,
  });

  const json = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      `Could not refresh Google token: ${
        json.error_description || json.error || response.status
      }`
    );
  }

  return json;
}

async function listSearchConsoleSites(accessToken: string) {
  const response = await fetch("https://www.googleapis.com/webmasters/v3/sites", {
    method: "GET",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Accept: "application/json",
    },
  });

  const json = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      `Could not list Search Console sites: ${
        json.error?.message || response.status
      }`
    );
  }

  return Array.isArray(json.siteEntry) ? json.siteEntry : [];
}

async function querySearchAnalytics({
  accessToken,
  siteUrl,
  startDate,
  endDate,
  dimensions,
  rowLimit,
}: {
  accessToken: string;
  siteUrl: string;
  startDate: string;
  endDate: string;
  dimensions: string[];
  rowLimit: number;
}) {
  const encodedSiteUrl = encodeURIComponent(siteUrl);

  const response = await fetch(
    `https://www.googleapis.com/webmasters/v3/sites/${encodedSiteUrl}/searchAnalytics/query`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        startDate,
        endDate,
        dimensions,
        rowLimit,
        startRow: 0,
      }),
    }
  );

  const json = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      `Search Console query failed: ${json.error?.message || response.status}`
    );
  }

  return Array.isArray(json.rows)
    ? json.rows.map((row: any) => normalizeSearchRow(row, dimensions))
    : [];
}

function normalizeSearchRow(row: any, dimensions: string[]) {
  const keys = Array.isArray(row.keys) ? row.keys : [];

  const output: Record<string, unknown> = {
    keys,
    clicks: Number(row.clicks || 0),
    impressions: Number(row.impressions || 0),
    ctr: Number(row.ctr || 0),
    position: Number(row.position || 0),
  };

  dimensions.forEach((dimension, index) => {
    output[dimension] = keys[index] || "";
  });

  return output;
}

function buildKeywordOpportunities(rows: any[]) {
  return rows
    .filter((row) => {
      return (
        row.query &&
        Number(row.impressions || 0) >= 50 &&
        Number(row.position || 0) >= 4 &&
        Number(row.position || 0) <= 20
      );
    })
    .sort((a, b) => {
      const impressionDiff =
        Number(b.impressions || 0) - Number(a.impressions || 0);

      if (impressionDiff !== 0) return impressionDiff;

      return Number(a.position || 0) - Number(b.position || 0);
    })
    .slice(0, 25)
    .map((row) => ({
      query: row.query,
      clicks: row.clicks,
      impressions: row.impressions,
      ctr: row.ctr,
      position: row.position,
      opportunity_type: "ranking_position_4_to_20",
      recommendation:
        "Improve the matching page with stronger content, internal links, and a clearer title/meta description.",
    }));
}

function buildLowCtrPages(rows: any[]) {
  return rows
    .filter((row) => {
      return (
        row.page &&
        Number(row.impressions || 0) >= 100 &&
        Number(row.ctr || 0) < 0.02
      );
    })
    .sort((a, b) => Number(b.impressions || 0) - Number(a.impressions || 0))
    .slice(0, 25)
    .map((row) => ({
      page: row.page,
      clicks: row.clicks,
      impressions: row.impressions,
      ctr: row.ctr,
      position: row.position,
      opportunity_type: "low_ctr",
      recommendation:
        "Rewrite the title and meta description to better match the search intent.",
    }));
}

function buildTopPages(rows: any[]) {
  return rows
    .sort((a, b) => Number(b.clicks || 0) - Number(a.clicks || 0))
    .slice(0, 25)
    .map((row) => ({
      page: row.page,
      clicks: row.clicks,
      impressions: row.impressions,
      ctr: row.ctr,
      position: row.position,
    }));
}

function buildPageKeywordOpportunities(rows: any[]) {
  return rows
    .filter((row) => {
      return (
        row.page &&
        row.query &&
        Number(row.impressions || 0) >= 25 &&
        Number(row.position || 0) >= 4 &&
        Number(row.position || 0) <= 20
      );
    })
    .sort((a, b) => Number(b.impressions || 0) - Number(a.impressions || 0))
    .slice(0, 50)
    .map((row) => ({
      page: row.page,
      query: row.query,
      clicks: row.clicks,
      impressions: row.impressions,
      ctr: row.ctr,
      position: row.position,
      opportunity_type: "page_keyword_improvement",
      recommendation:
        "Add more helpful content around this query and strengthen internal links to this page.",
    }));
}

function buildTotals(pageRows: any[]) {
  return pageRows.reduce(
    (totals, row) => {
      totals.clicks += Number(row.clicks || 0);
      totals.impressions += Number(row.impressions || 0);

      return totals;
    },
    {
      clicks: 0,
      impressions: 0,
    }
  );
}

function getSearchConsoleDateRange(days: number) {
  const end = new Date();

  end.setUTCDate(end.getUTCDate() - 3);

  const start = new Date(end);

  start.setUTCDate(start.getUTCDate() - days);

  return {
    startDate: formatDate(start),
    endDate: formatDate(end),
  };
}

function formatDate(date: Date) {
  return date.toISOString().slice(0, 10);
}

async function assertPublicHttpUrlIfPresent(value: string) { const text = String(value || "").trim(); if (!/^https?:\/\//i.test(text)) return; const url = new URL(text); const ips = await resolvePublicIps(url.hostname); if (!ips.length || ips.some((ip) => !isPublicIp(ip))) throw new Error("Private or local network addresses cannot be scanned."); }
async function resolvePublicIps(hostname: string) { const host = String(hostname || "").replace(/^\[|\]$/g, "").toLowerCase(); if (!host || host === "localhost" || host.endsWith(".localhost") || host.endsWith(".local") || host.endsWith(".internal")) throw new Error("Private or local network addresses cannot be scanned."); if (isIpv4Address(host) || host.includes(":")) return [host]; const response = await fetch(`https://cloudflare-dns.com/dns-query?name=${encodeURIComponent(host)}&type=A`, { headers: { Accept: "application/dns-json" } }); const data = await response.json().catch(() => ({})); return (data.Answer || []).map((answer: any) => String(answer?.data || "")).filter(isIpv4Address); }
function isIpv4Address(value: string) { const parts = String(value || "").split("."); return parts.length === 4 && parts.every((part) => /^\d+$/.test(part) && Number(part) >= 0 && Number(part) <= 255); }
function isPublicIp(ip: string) { const value = String(ip || "").toLowerCase(); if (isIpv4Address(value)) return isPublicIpv4(value); return Boolean(value.includes(":")) && !value.startsWith("::1") && !value.startsWith("fc") && !value.startsWith("fd") && !value.startsWith("fe80"); }
function isPublicIpv4(ip: string) { const [a, b] = ip.split(".").map(Number); return !(a === 0 || a === 10 || a === 127 || a >= 224 || (a === 100 && b >= 64 && b <= 127) || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31) || (a === 192 && (b === 0 || b === 168)) || (a === 198 && (b === 18 || b === 19)) || ip === "255.255.255.255"); }

function clampNumber(value: number, min: number, max: number) {
  if (!Number.isFinite(value)) return min;

  return Math.max(min, Math.min(max, value));
}