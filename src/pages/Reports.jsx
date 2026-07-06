import React, { useState } from "react";
import {
  BarChart3,
  ExternalLink,
  KeyRound,
  Link2,
  Loader2,
  Plug,
  Search,
  ShieldCheck,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { base44 } from "@/api/base44Client";

const GOOGLE_CONNECT_FUNCTION = "googleSearchConsoleConnect";
const GSC_INSIGHTS_FUNCTION = "getSearchConsoleInsights";
const BING_BACKLINKS_FUNCTION = "getBingBacklinks";

export default function Reports() {
  const [loadingGoogle, setLoadingGoogle] = useState(false);
  const [loadingInsights, setLoadingInsights] = useState(false);
  const [loadingBacklinks, setLoadingBacklinks] = useState(false);

  const [error, setError] = useState("");
  const [googleStatus, setGoogleStatus] = useState(null);
  const [searchConsoleInsights, setSearchConsoleInsights] = useState(null);
  const [backlinkData, setBacklinkData] = useState(null);

  async function connectGoogleSearchConsole() {
    setLoadingGoogle(true);
    setError("");
    setGoogleStatus(null);

    try {
      const response = await callBase44Function(GOOGLE_CONNECT_FUNCTION, {});
      const data = normalizeFunctionResponse(response);

      if (data?.auth_url) {
        window.location.href = data.auth_url;
        return;
      }

      setGoogleStatus(data);
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
      const response = await callBase44Function(GSC_INSIGHTS_FUNCTION, {
        days: 28,
      });

      const data = normalizeFunctionResponse(response);
      setSearchConsoleInsights(data);
    } catch (err) {
      setError(
        err?.message ||
          "Could not load Google Search Console insights yet. Make sure the backend function exists."
      );
    } finally {
      setLoadingInsights(false);
    }
  }

  async function loadBingBacklinks() {
    setLoadingBacklinks(true);
    setError("");

    try {
      const response = await callBase44Function(BING_BACKLINKS_FUNCTION, {});
      const data = normalizeFunctionResponse(response);

      setBacklinkData(data);
    } catch (err) {
      setError(
        err?.message ||
          "Could not load backlink data yet. Make sure the Bing Webmaster API key and backend function are configured."
      );
    } finally {
      setLoadingBacklinks(false);
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
          buttonLabel="Connect Google Search Console"
          loading={loadingGoogle}
          onClick={connectGoogleSearchConsole}
        />

        <ConnectionCard
          icon={<Link2 className="h-6 w-6" />}
          title="Bing Webmaster Tools"
          badge="Free backlink tracker"
          description="Use Bing Webmaster Tools as the free backlink source for referring pages, linked pages, anchor text, and link opportunities."
          buttonLabel="Check Backlinks"
          loading={loadingBacklinks}
          onClick={loadBingBacklinks}
        />
      </section>

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

      {backlinkData ? (
        <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex items-center gap-2">
            <Link2 className="h-5 w-5 text-blue-700" />
            <h2 className="text-xl font-semibold text-slate-950">
              Backlink preview
            </h2>
          </div>

          <BacklinkSummary data={backlinkData} />

          <pre className="mt-5 max-h-[420px] overflow-auto rounded-2xl bg-slate-950 p-4 text-xs leading-5 text-slate-100">
            {JSON.stringify(backlinkData, null, 2)}
          </pre>
        </section>
      ) : null}

      {googleStatus ? (
        <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex items-center gap-2">
            <KeyRound className="h-5 w-5 text-blue-700" />
            <h2 className="text-xl font-semibold text-slate-950">
              Google connection response
            </h2>
          </div>

          <pre className="mt-4 max-h-[420px] overflow-auto rounded-2xl bg-slate-950 p-4 text-xs leading-5 text-slate-100">
            {JSON.stringify(googleStatus, null, 2)}
          </pre>
        </section>
      ) : null}
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
  onClick,
}) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="rounded-2xl bg-blue-50 p-3 text-blue-700">{icon}</div>

        <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
          {badge}
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

  return (
    <div className="mt-6 grid gap-4 lg:grid-cols-3">
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
          {items.slice(0, 5).map((item, index) => (
            <div key={index} className="rounded-xl bg-white p-3 text-sm">
              <div className="font-medium text-slate-950">
                {item.query || item.page || item.url || item.title || "Item"}
              </div>

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

function BacklinkSummary({ data }) {
  const backlinks =
    data.backlinks_count ||
    data.total_backlinks ||
    data.backlinks?.length ||
    data.links?.length ||
    0;

  const referringDomains =
    data.referring_domains_count ||
    data.total_referring_domains ||
    data.referring_domains?.length ||
    data.domains?.length ||
    0;

  const topLinkedPages = safeArray(
    data.top_linked_pages || data.linked_pages || data.pages
  );

  return (
    <div className="mt-5 grid gap-4 md:grid-cols-3">
      <MetricCard label="Backlinks" value={backlinks} />
      <MetricCard label="Referring domains" value={referringDomains} />
      <MetricCard label="Linked pages" value={topLinkedPages.length} />
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

  return parts.length ? parts.join(" · ") : "SEO opportunity";
}

function formatPercent(value) {
  const number = Number(value);

  if (!Number.isFinite(number)) return "0%";

  if (number <= 1) return `${(number * 100).toFixed(1)}%`;

  return `${number.toFixed(1)}%`;
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