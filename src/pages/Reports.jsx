import React, { useEffect, useMemo, useState } from "react";
import {
  BarChart3,
  CheckCircle2,
  ExternalLink,
  KeyRound,
  Link2,
  Loader2,
  Plug,
  Search,
  ShieldCheck,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { base44 } from "@/api/base44Client";

const GOOGLE_CONNECT_FUNCTION = "googleSearchConsoleConnect";
const GSC_INSIGHTS_FUNCTION = "getSearchConsoleInsights";
const BING_BACKLINKS_FUNCTION = "getBingBacklinks";

const GSC_STORAGE_KEY = "seo_autopilot:gsc_connection";

export default function Reports() {
  const [loadingGoogle, setLoadingGoogle] = useState(false);
  const [loadingInsights, setLoadingInsights] = useState(false);
  const [loadingBacklinks, setLoadingBacklinks] = useState(false);

  const [error, setError] = useState("");
  const [googleConnection, setGoogleConnection] = useState(null);
  const [searchConsoleInsights, setSearchConsoleInsights] = useState(null);
  const [backlinkData, setBacklinkData] = useState(null);

  const [selectedSite, setSelectedSite] = useState("");
  const [bingSiteUrl, setBingSiteUrl] = useState("");

  useEffect(() => {
    const stored = loadGoogleConnection();

    if (stored) {
      setGoogleConnection(stored);

      const defaultSite =
        stored.selected_site ||
        stored.sites?.[0]?.siteUrl ||
        stored.sites?.[0]?.url ||
        "";

      setSelectedSite(defaultSite);
      setBingSiteUrl(defaultSite);
    }

    const params = new URLSearchParams(window.location.search);

    if (params.get("gsc") === "connected") {
      window.history.replaceState({}, "", "/reports");
    }
  }, []);

  const sites = useMemo(() => {
    return safeArray(googleConnection?.sites);
  }, [googleConnection]);

  const isGoogleConnected = Boolean(
    googleConnection?.access_token || googleConnection?.refresh_token
  );

  async function connectGoogleSearchConsole() {
    setLoadingGoogle(true);
    setError("");

    try {
      const response = await callBase44Function(GOOGLE_CONNECT_FUNCTION, {});
      const data = normalizeFunctionResponse(response);

      if (data?.auth_url) {
        window.location.href = data.auth_url;
        return;
      }

      setError(
        data?.error ||
          "Google connection did not return an auth URL. Check the backend function."
      );
    } catch (err) {
      setError(
        err?.message ||
          "Google Search Console connection failed. Make sure the backend function exists."
      );
    } finally {
      setLoadingGoogle(false);
    }
  }

  async function loadSearchConsoleInsights() {
    setLoadingInsights(true);
    setError("");

    try {
      const connection = loadGoogleConnection();

      if (!connection?.access_token && !connection?.refresh_token) {
        throw new Error("Connect Google Search Console first.");
      }

      const response = await callBase44Function(GSC_INSIGHTS_FUNCTION, {
        days: 28,
        site_url: selectedSite || connection.selected_site || "",
        access_token: connection.access_token || "",
        refresh_token: connection.refresh_token || "",
      });

      const data = normalizeFunctionResponse(response);

      if (data?.connection_update) {
        const updatedConnection = {
          ...connection,
          ...data.connection_update,
          selected_site:
            data.site_url ||
            selectedSite ||
            connection.selected_site ||
            connection.sites?.[0]?.siteUrl ||
            "",
        };

        saveGoogleConnection(updatedConnection);
        setGoogleConnection(updatedConnection);
      }

      if (data?.site_url && !selectedSite) {
        setSelectedSite(data.site_url);
        setBingSiteUrl(data.site_url);
      }

      setSearchConsoleInsights(data);
    } catch (err) {
      setError(
        err?.message ||
          "Could not load Google Search Console insights yet."
      );
    } finally {
      setLoadingInsights(false);
    }
  }

  async function loadBingBacklinks() {
    setLoadingBacklinks(true);
    setError("");

    try {
      const siteUrl = bingSiteUrl || selectedSite;

      if (!siteUrl) {
        throw new Error(
          "Enter a verified Bing Webmaster Tools site URL first."
        );
      }

      const response = await callBase44Function(BING_BACKLINKS_FUNCTION, {
        site_url: siteUrl,
        count: 100,
      });

      const data = normalizeFunctionResponse(response);
      setBacklinkData(data);
    } catch (err) {
      setError(
        err?.message ||
          "Could not load backlink data. Make sure the Bing Webmaster API key and backend function are configured."
      );
    } finally {
      setLoadingBacklinks(false);
    }
  }

  function handleSiteChange(value) {
    setSelectedSite(value);
    setBingSiteUrl(value);

    if (googleConnection) {
      const updated = {
        ...googleConnection,
        selected_site: value,
      };

      saveGoogleConnection(updated);
      setGoogleConnection(updated);
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-8 px-4 py-8 md:px-8">
      <header>
        <div className="flex items-center gap-2 text-sm font-semibold text-blue-700">
          <Plug className="h-4 w-4" />
          SEO data connections
        </div>

        <h1 className="mt-2 text-4xl font-bold tracking-tight text-slate-950">
          SEO Connections
        </h1>

        <p className="mt-3 max-w-3xl text-lg text-slate-600">
          Connect free SEO data sources so SEO Pilot can use real keyword,
          page-performance, and backlink data in the Fix List.
        </p>
      </header>

      {error ? (
        <div className="rounded-3xl border border-red-200 bg-red-50 p-5 text-sm text-red-800">
          {error}
        </div>
      ) : null}

      <section className="grid gap-6 lg:grid-cols-2">
        <ConnectionCard
          icon={<Search className="h-6 w-6" />}
          title="Google Search Console"
          badge="Best free keyword data"
          description="Connect Google Search Console to pull real Google queries, clicks, impressions, CTR, average position, and page-level opportunities."
          buttonLabel={
            isGoogleConnected
              ? "Reconnect Google Search Console"
              : "Connect Google Search Console"
          }
          loading={loadingGoogle}
          connected={isGoogleConnected}
          onClick={connectGoogleSearchConsole}
        />

        <ConnectionCard
          icon={<Link2 className="h-6 w-6" />}
          title="Bing Webmaster Tools"
          badge="Free backlink tracker"
          description="Use Bing Webmaster Tools as the free backlink source for referring pages, linked pages, anchor text, and link opportunities."
          buttonLabel="Check Backlinks"
          loading={loadingBacklinks}
          connected={Boolean(backlinkData)}
          onClick={loadBingBacklinks}
        />
      </section>

      {isGoogleConnected ? (
        <section className="rounded-3xl border border-emerald-200 bg-emerald-50 p-5">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="mt-0.5 h-5 w-5 text-emerald-700" />

            <div>
              <h2 className="font-semibold text-emerald-950">
                Google Search Console connected
              </h2>

              <p className="mt-1 text-sm text-emerald-800">
                Choose the verified property SEO Pilot should use.
              </p>

              {sites.length > 0 ? (
                <select
                  value={selectedSite}
                  onChange={(event) => handleSiteChange(event.target.value)}
                  className="mt-4 h-10 w-full max-w-xl rounded-md border border-emerald-200 bg-white px-3 text-sm text-slate-900"
                >
                  {sites.map((site, index) => (
                    <option
                      key={`${site.siteUrl || site.url}-${index}`}
                      value={site.siteUrl || site.url}
                    >
                      {site.siteUrl || site.url}
                    </option>
                  ))}
                </select>
              ) : null}
            </div>
          </div>
        </section>
      ) : null}

      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <BarChart3 className="h-5 w-5 text-blue-700" />
              <h2 className="text-xl font-semibold text-slate-950">
                Search Console insights
              </h2>
            </div>

            <p className="mt-2 max-w-3xl text-slate-600">
              After Google Search Console is connected, this section will show
              keywords and pages SEO Pilot should prioritize.
            </p>
          </div>

          <Button
            type="button"
            variant="outline"
            onClick={loadSearchConsoleInsights}
            disabled={loadingInsights}
          >
            {loadingInsights ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Loading...
              </>
            ) : (
              <>
                <BarChart3 className="mr-2 h-4 w-4" />
                Load insights
              </>
            )}
          </Button>
        </div>

        <InsightsPreview data={searchConsoleInsights} />
      </section>

      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center gap-2">
          <Link2 className="h-5 w-5 text-blue-700" />
          <h2 className="text-xl font-semibold text-slate-950">
            Bing backlink tracker
          </h2>
        </div>

        <p className="mt-2 max-w-3xl text-slate-600">
          Enter a site that is verified in Bing Webmaster Tools. This should
          usually match your selected Search Console property.
        </p>

        <div className="mt-4 flex flex-col gap-3 md:flex-row">
          <Input
            value={bingSiteUrl}
            onChange={(event) => setBingSiteUrl(event.target.value)}
            placeholder="https://www.example.com/"
            className="md:max-w-xl"
          />

          <Button
            type="button"
            onClick={loadBingBacklinks}
            disabled={loadingBacklinks}
          >
            {loadingBacklinks ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Loading...
              </>
            ) : (
              <>
                <Link2 className="mr-2 h-4 w-4" />
                Load backlinks
              </>
            )}
          </Button>
        </div>

        {backlinkData ? <BacklinkPreview data={backlinkData} /> : null}
      </section>

      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-emerald-700" />
          <h2 className="text-xl font-semibold text-slate-950">
            What this unlocks
          </h2>
        </div>

        <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <FeatureCard
            title="Keyword opportunities"
            description="Find keywords ranking in positions 4–20 that can be improved."
          />

          <FeatureCard
            title="Low CTR pages"
            description="Find pages with impressions but weak clicks."
          />

          <FeatureCard
            title="Backlink priorities"
            description="Prioritize pages that already have backlinks."
          />

          <FeatureCard
            title="Gemini action plans"
            description="Send real SEO data to Gemini for better Fix List guidance."
          />
        </div>
      </section>
    </div>
  );
}

function ConnectionCard({
  icon,
  title,
  badge,
  description,
  buttonLabel,
  loading,
  connected,
  onClick,
}) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="rounded-2xl bg-blue-50 p-3 text-blue-700">{icon}</div>

        <span
          className={`rounded-full px-3 py-1 text-xs font-semibold ${
            connected
              ? "bg-emerald-50 text-emerald-700"
              : "bg-slate-100 text-slate-600"
          }`}
        >
          {connected ? "Connected" : badge}
        </span>
      </div>

      <h2 className="mt-5 text-2xl font-bold text-slate-950">{title}</h2>

      <p className="mt-3 leading-7 text-slate-600">{description}</p>

      <Button
        type="button"
        onClick={onClick}
        disabled={loading}
        className="mt-6"
      >
        {loading ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Connecting...
          </>
        ) : (
          <>
            <ExternalLink className="mr-2 h-4 w-4" />
            {buttonLabel}
          </>
        )}
      </Button>
    </div>
  );
}

function InsightsPreview({ data }) {
  if (!data) {
    return (
      <div className="mt-5 rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-6 text-center text-slate-600">
        No Search Console data loaded yet.
      </div>
    );
  }

  const keywordOpportunities = safeArray(data.keyword_opportunities);
  const lowCtrPages = safeArray(data.low_ctr_pages);
  const topPages = safeArray(data.top_pages);
  const pageKeywordOpportunities = safeArray(data.page_keyword_opportunities);

  return (
    <div className="mt-6 grid gap-4 lg:grid-cols-2">
      <PreviewList
        title="Keyword opportunities"
        items={keywordOpportunities}
        empty="No keyword opportunities returned yet."
      />

      <PreviewList
        title="Low CTR pages"
        items={lowCtrPages}
        empty="No low-CTR pages returned yet."
      />

      <PreviewList
        title="Top pages"
        items={topPages}
        empty="No top pages returned yet."
      />

      <PreviewList
        title="Page + keyword opportunities"
        items={pageKeywordOpportunities}
        empty="No page keyword opportunities returned yet."
      />
    </div>
  );
}

function PreviewList({ title, items, empty }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <h3 className="font-semibold text-slate-950">{title}</h3>

      {items.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">{empty}</p>
      ) : (
        <div className="mt-3 space-y-3">
          {items.slice(0, 8).map((item, index) => (
            <div key={index} className="rounded-xl bg-white p-3 text-sm">
              <div className="break-words font-medium text-slate-950">
                {item.query ||
                  item.page ||
                  item.url ||
                  item.title ||
                  "SEO opportunity"}
              </div>

              {item.page && item.query ? (
                <div className="mt-1 break-words text-xs text-slate-500">
                  {item.page}
                </div>
              ) : null}

              <div className="mt-1 text-slate-500">
                {formatMetricLine(item)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function BacklinkPreview({ data }) {
  const topLinkedPages = safeArray(data.top_linked_pages);
  const sampleLinks = safeArray(data.sample_links);

  return (
    <div className="mt-6 space-y-5">
      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard label="Backlinks" value={data.backlinks_count || 0} />
        <MetricCard
          label="Referring domains"
          value={data.referring_domains_count || 0}
        />
        <MetricCard label="Linked pages" value={topLinkedPages.length} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <PreviewList
          title="Top linked pages"
          items={topLinkedPages}
          empty="No linked pages returned."
        />

        <PreviewList
          title="Sample backlinks"
          items={sampleLinks}
          empty="No backlink samples returned."
        />
      </div>

      <pre className="max-h-[420px] overflow-auto rounded-2xl bg-slate-950 p-4 text-xs leading-5 text-slate-100">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}

function MetricCard({ label, value }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="text-sm font-medium text-slate-500">{label}</div>
      <div className="mt-2 text-2xl font-bold text-slate-950">{value}</div>
    </div>
  );
}

function FeatureCard({ title, description }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <h3 className="font-semibold text-slate-950">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p>
    </div>
  );
}

function formatMetricLine(item) {
  const parts = [];

  if (item.clicks !== undefined) parts.push(`${item.clicks} clicks`);

  if (item.impressions !== undefined) {
    parts.push(`${item.impressions} impressions`);
  }

  if (item.ctr !== undefined) {
    parts.push(`${formatPercent(item.ctr)} CTR`);
  }

  if (item.position !== undefined) {
    parts.push(`position ${Number(item.position).toFixed(1)}`);
  }

  if (item.backlinks !== undefined) {
    parts.push(`${item.backlinks} backlinks`);
  }

  if (item.referring_page) {
    parts.push(`from ${item.referring_page}`);
  }

  return parts.length ? parts.join(" · ") : "SEO opportunity";
}

function formatPercent(value) {
  const number = Number(value);

  if (!Number.isFinite(number)) return "0%";

  if (number <= 1) return `${(number * 100).toFixed(1)}%`;

  return `${number.toFixed(1)}%`;
}

/* -------------------------------------------------------------------------- */
/* Google connection local storage                                             */
/* -------------------------------------------------------------------------- */

function loadGoogleConnection() {
  try {
    const raw = window.localStorage.getItem(GSC_STORAGE_KEY);

    if (!raw) return null;

    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function saveGoogleConnection(connection) {
  try {
    window.localStorage.setItem(GSC_STORAGE_KEY, JSON.stringify(connection));
  } catch {
    // Ignore localStorage errors.
  }
}

/* -------------------------------------------------------------------------- */
/* Base44 function caller                                                      */
/* -------------------------------------------------------------------------- */

async function callBase44Function(functionName, payload) {
  const errors = [];

  if (base44?.functions?.invoke) {
    try {
      return await base44.functions.invoke(functionName, payload);
    } catch (error) {
      errors.push(`functions.invoke: ${error?.message || error}`);
    }
  }

  if (typeof base44?.functions?.[functionName] === "function") {
    try {
      return await base44.functions[functionName](payload);
    } catch (error) {
      errors.push(`functions.${functionName}: ${error?.message || error}`);
    }
  }

  if (base44?.integrations?.Core?.InvokeFunction) {
    try {
      return await base44.integrations.Core.InvokeFunction({
        name: functionName,
        body: payload,
      });
    } catch (error) {
      errors.push(`InvokeFunction: ${error?.message || error}`);
    }
  }

  throw new Error(
    `${functionName} failed. ${
      errors.length
        ? errors.join(" | ")
        : "No supported Base44 function caller was found."
    }`
  );
}

function normalizeFunctionResponse(response) {
  if (!response) return {};

  if (response.data?.data) return response.data.data;
  if (response.data?.result) return response.data.result;
  if (response.data) return response.data;
  if (response.result?.data) return response.result.data;
  if (response.result) return response.result;
  if (response.body) return response.body;

  return response;
}

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}