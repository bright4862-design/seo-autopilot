import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ExternalLink,
  FileText,
  HeartPulse,
  LayoutDashboard,
  ListChecks,
  MonitorCog,
  Search,
  Sparkles,
  Wrench,
} from "lucide-react";

import { Button } from "@/components/ui/button";

const LAST_SCAN_KEYS = [
  "seo_autopilot:last_scan",
  "SEO_AUTOPILOT_LAST_SCAN",
];

const SCAN_HISTORY_KEYS = [
  "seo_autopilot:scan_history",
  "SEO_AUTOPILOT_SCAN_HISTORY",
];

const CMS_OPTIONS = [
  { id: "wordpress", label: "WordPress" },
  { id: "squarespace", label: "Squarespace" },
  { id: "wix", label: "Wix" },
  { id: "shopify", label: "Shopify" },
  { id: "webflow", label: "Webflow" },
  { id: "framer", label: "Framer" },
  { id: "godaddy", label: "GoDaddy" },
  { id: "custom", label: "Custom CMS" },
];

const FILTERS = [
  { id: "all", label: "All" },
  { id: "priority", label: "Priority" },
  { id: "prepared", label: "Can prepare" },
  { id: "review", label: "Needs review" },
  { id: "help", label: "May need help" },
];

export default function FixList() {
  const navigate = useNavigate();

  const [scanRecord, setScanRecord] = useState(null);
  const [activeFilter, setActiveFilter] = useState("all");
  const [selectedCms, setSelectedCms] = useState("wordpress");

  useEffect(() => {
    function reload() {
      setScanRecord(loadBestScanRecord());
    }

    reload();

    window.addEventListener("focus", reload);
    window.addEventListener("storage", reload);
    window.addEventListener("seo-autopilot-scan-saved", reload);

    return () => {
      window.removeEventListener("focus", reload);
      window.removeEventListener("storage", reload);
      window.removeEventListener("seo-autopilot-scan-saved", reload);
    };
  }, []);

  const scan = scanRecord?.result || null;

  const fixes = useMemo(() => getFixes(scan), [scan]);
  const pages = useMemo(() => getPages(scan), [scan]);

  const hasScan = Boolean(scan && (pages.length > 0 || fixes.length > 0));

  const healthReport =
    scan?.website_health_report ||
    scan?.scan_summary?.website_health_report ||
    scan?.scan_summary ||
    null;

  const score = hasScan
    ? numberOrNull(scan?.health_score) ??
      numberOrNull(scan?.scan_summary?.score) ??
      numberOrNull(healthReport?.health_score) ??
      calculateFallbackScore(fixes)
    : null;

  const highPriorityCount = fixes.filter((fix) =>
    ["critical", "high"].includes(String(fix.priority || ""))
  ).length;

  const helpCount = fixes.filter((fix) => needsWebHelp(fix)).length;

  const filteredFixes = useMemo(() => {
    if (activeFilter === "priority") {
      return fixes.filter((fix) =>
        ["critical", "high"].includes(String(fix.priority || ""))
      );
    }

    if (activeFilter === "prepared") {
      return fixes.filter((fix) => !needsWebHelp(fix));
    }

    if (activeFilter === "review") {
      return fixes.filter(
        (fix) =>
          fix.status === "needs_approval" ||
          fix.requires_approval === true ||
          !needsWebHelp(fix)
      );
    }

    if (activeFilter === "help") {
      return fixes.filter((fix) => needsWebHelp(fix));
    }

    return fixes;
  }, [fixes, activeFilter]);

  const cmsLabel =
    CMS_OPTIONS.find((item) => item.id === selectedCms)?.label || "your CMS";

  const actionPlan = useMemo(() => {
    return buildActionPlan({
      scan,
      fixes,
      healthReport,
      selectedCms,
      cmsLabel,
    });
  }, [scan, fixes, healthReport, selectedCms, cmsLabel]);

  return (
    <div className="mx-auto max-w-7xl space-y-8 px-4 py-8 md:px-8">
      <header>
        <div className="flex items-center gap-2 text-sm font-semibold text-blue-700">
          <LayoutDashboard className="h-4 w-4" />
          Website recommendations
        </div>

        <h1 className="mt-2 text-4xl font-bold tracking-tight text-slate-950">
          Fix List
        </h1>

        <p className="mt-3 max-w-3xl text-lg text-slate-600">
          A prioritized list of what to review, prepare, or ask for help with.
        </p>
      </header>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Score"
          value={score === null ? "—" : score}
          sublabel={score === null ? "Run a scan" : scoreToLabel(score)}
          icon={<Sparkles className="h-5 w-5" />}
        />

        <MetricCard
          label="Recommendations"
          value={hasScan ? fixes.length : 0}
          sublabel={`${hasScan ? highPriorityCount : 0} high priority`}
          icon={<AlertCircle className="h-5 w-5" />}
        />

        <MetricCard
          label="Pages scanned"
          value={hasScan ? pages.length : 0}
          sublabel={
            hasScan
              ? formatDate(scanRecord?.created_at || scan?.created_at)
              : "No scan yet"
          }
          icon={<Search className="h-5 w-5" />}
        />

        <MetricCard
          label="May need help"
          value={hasScan ? helpCount : 0}
          sublabel="Website setup or cleanup"
          icon={<Wrench className="h-5 w-5" />}
        />
      </section>

      {!hasScan ? (
        <NoScanState onScan={() => navigate("/onboarding")} />
      ) : (
        <>
          <AiActionPlan
            plan={actionPlan}
            provider={scan?.ai_provider}
            cmsLabel={cmsLabel}
            healthReport={healthReport}
            score={score}
          />

          <CmsSelector selectedCms={selectedCms} onSelectCms={setSelectedCms} />

          <div className="flex flex-wrap gap-3">
            {FILTERS.map((filter) => (
              <button
                key={filter.id}
                type="button"
                onClick={() => setActiveFilter(filter.id)}
                className={`rounded-full border px-5 py-2 text-sm font-medium transition ${
                  activeFilter === filter.id
                    ? "border-slate-950 bg-slate-950 text-white"
                    : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                }`}
              >
                {filter.label}
              </button>
            ))}
          </div>

          <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="mb-5 flex items-center gap-2">
              <ListChecks className="h-5 w-5 text-blue-700" />
              <h2 className="text-xl font-semibold text-slate-950">
                Recommendations
              </h2>
            </div>

            {filteredFixes.length === 0 ? (
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-8 text-center">
                <h3 className="text-lg font-semibold text-slate-950">
                  No recommendations in this filter.
                </h3>
                <p className="mt-2 text-slate-600">
                  Try switching back to All.
                </p>
              </div>
            ) : (
              <div className="space-y-5">
                {filteredFixes.map((fix, index) => (
                  <FixCard
                    key={fix.id || fix.fix_id || index}
                    fix={fix}
                    cms={selectedCms}
                    cmsLabel={cmsLabel}
                    scan={scan}
                    index={index}
                  />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function NoScanState({ onScan }) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-10 text-center shadow-sm">
      <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-50 text-blue-700">
        <Search className="h-7 w-7" />
      </div>

      <h2 className="mt-5 text-2xl font-bold text-slate-950">
        No recommendations yet.
      </h2>

      <p className="mx-auto mt-3 max-w-xl text-slate-600">
        Run a website scan first. Once the scan finishes, your Fix List,
        AI-guided action plan, and CMS instructions will appear here.
      </p>

      <Button onClick={onScan} className="mt-6">
        <Search className="mr-2 h-4 w-4" />
        Scan Website
      </Button>
    </section>
  );
}

function MetricCard({ label, value, sublabel, icon }) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-sm font-semibold uppercase tracking-wide text-slate-400">
            {label}
          </div>
          <div className="mt-3 text-3xl font-bold text-slate-950">{value}</div>
          <div className="mt-2 text-slate-600">{sublabel}</div>
        </div>

        <div className="rounded-2xl bg-slate-100 p-3 text-slate-600">
          {icon}
        </div>
      </div>
    </div>
  );
}

function AiActionPlan({ plan, provider, cmsLabel, healthReport, score }) {
  const providerLabel =
    provider === "gemini"
      ? "Guided by Gemini"
      : provider
        ? `Guided by ${provider}`
        : "AI-guided plan";

  return (
    <section className="rounded-3xl border border-blue-200 bg-gradient-to-br from-blue-50 to-white p-6 shadow-sm">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-blue-700">
            <Sparkles className="h-4 w-4" />
            {providerLabel}
          </div>

          <h2 className="mt-2 text-2xl font-bold text-slate-950">
            Best plan of action
          </h2>

          <p className="mt-3 max-w-4xl text-slate-700">
            {healthReport?.overall_explanation ||
              healthReport?.plain_english_summary ||
              `Your website score is ${score}/100. Start with the highest priority items, then work through the easier content improvements.`}
          </p>
        </div>

        <div className="rounded-2xl bg-white px-5 py-4 text-center shadow-sm">
          <div className="text-sm text-slate-500">Selected CMS</div>
          <div className="mt-1 font-semibold text-slate-950">{cmsLabel}</div>
        </div>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        {plan.map((step, index) => (
          <div
            key={index}
            className="rounded-2xl border border-slate-200 bg-white p-5"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-600 text-sm font-bold text-white">
              {index + 1}
            </div>

            <h3 className="mt-4 font-semibold text-slate-950">
              {step.title}
            </h3>

            <p className="mt-2 text-sm leading-6 text-slate-600">
              {step.reason}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

function CmsSelector({ selectedCms, onSelectCms }) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex items-center gap-2">
        <MonitorCog className="h-5 w-5 text-slate-700" />
        <h2 className="text-xl font-semibold text-slate-950">
          Choose your website builder
        </h2>
      </div>

      <p className="mt-2 text-slate-600">
        Click the CMS your site uses to see fix instructions written for that
        platform.
      </p>

      <div className="mt-5 flex flex-wrap gap-3">
        {CMS_OPTIONS.map((cms) => (
          <button
            key={cms.id}
            type="button"
            onClick={() => onSelectCms(cms.id)}
            className={`rounded-full border px-5 py-2 text-sm font-medium transition ${
              selectedCms === cms.id
                ? "border-blue-600 bg-blue-600 text-white"
                : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
            }`}
          >
            {cms.label}
          </button>
        ))}
      </div>
    </section>
  );
}

function FixCard({ fix, cms, cmsLabel, scan, index }) {
  const [openInstructions, setOpenInstructions] = useState(index < 2);

  const priority = String(fix.priority || "medium");
  const category = fix.customer_category || friendlyCategory(fix.category);
  const steps = safeArray(fix.what_to_do || fix.what_to_do_steps || fix.fix_steps);
  const affectedPages = buildFriendlyAffectedPages(fix);
  const cmsSteps = getCmsInstructions(fix, cms, cmsLabel);
  const helpNeeded = needsWebHelp(fix);

  return (
    <article className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap gap-2">
            <Badge>{priority}</Badge>
            <Badge>{category}</Badge>
            {helpNeeded ? (
              <Badge>may need help</Badge>
            ) : (
              <Badge>can prepare</Badge>
            )}
          </div>

          <h3 className="mt-4 text-xl font-bold text-slate-950">
            {fix.issue_title || fix.title || "Website recommendation"}
          </h3>

          <p className="mt-2 max-w-4xl text-slate-600">
            {fix.plain_english_explanation ||
              fix.plain_english_summary ||
              "This was found during the website scan."}
          </p>
        </div>

        {helpNeeded ? (
          <div className="rounded-2xl bg-amber-50 px-4 py-3 text-sm text-amber-900">
            Best for your web person
          </div>
        ) : (
          <div className="rounded-2xl bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
            You can prepare this
          </div>
        )}
      </div>

      {fix.why_it_matters ? (
        <div className="mt-5 rounded-2xl bg-slate-50 p-4">
          <div className="text-sm font-semibold text-slate-950">
            Why this matters
          </div>
          <p className="mt-1 text-sm leading-6 text-slate-600">
            {fix.why_it_matters}
          </p>
        </div>
      ) : null}

      {steps.length > 0 ? (
        <div className="mt-5">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
            <CheckCircle2 className="h-4 w-4 text-emerald-700" />
            General next steps
          </div>

          <ol className="mt-3 space-y-2 text-sm leading-6 text-slate-600">
            {steps.slice(0, 5).map((step, stepIndex) => (
              <li key={stepIndex}>
                <span className="font-semibold text-slate-900">
                  {stepIndex + 1}.
                </span>{" "}
                {step}
              </li>
            ))}
          </ol>
        </div>
      ) : null}

      <div className="mt-5 rounded-2xl border border-blue-200 bg-blue-50">
        <button
          type="button"
          onClick={() => setOpenInstructions((value) => !value)}
          className="flex w-full items-center justify-between p-4 text-left"
        >
          <div>
            <div className="font-semibold text-blue-950">
              How to fix this in {cmsLabel}
            </div>
            <div className="mt-1 text-sm text-blue-800">
              Platform-specific instructions
            </div>
          </div>

          <ChevronDown
            className={`h-5 w-5 text-blue-700 transition ${
              openInstructions ? "rotate-180" : ""
            }`}
          />
        </button>

        {openInstructions ? (
          <div className="border-t border-blue-100 p-4">
            <ol className="space-y-2 text-sm leading-6 text-blue-950">
              {cmsSteps.map((step, stepIndex) => (
                <li key={stepIndex}>
                  <span className="font-semibold">{stepIndex + 1}.</span>{" "}
                  {step}
                </li>
              ))}
            </ol>
          </div>
        ) : null}
      </div>

      {affectedPages.length > 0 ? (
        <div className="mt-5">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-950">
            <FileText className="h-4 w-4 text-slate-600" />
            Example affected pages
          </div>

          <div className="grid gap-2">
            {affectedPages.slice(0, 6).map((page, pageIndex) => (
              <AffectedPage
                key={`${page.path}-${pageIndex}`}
                page={page}
                scan={scan}
              />
            ))}
          </div>

          {affectedPages.length > 6 ? (
            <p className="mt-2 text-xs text-slate-500">
              Plus {affectedPages.length - 6} more affected page
              {affectedPages.length - 6 === 1 ? "" : "s"}.
            </p>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

function AffectedPage({ page, scan }) {
  const href = buildPageHref(page.path, scan);

  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="font-medium text-slate-950">{page.label}</div>
          <div className="mt-1 flex items-center gap-1 text-xs text-slate-500">
            <ExternalLink className="h-3 w-3" />
            <code>{page.path}</code>
          </div>
        </div>

        {href ? (
          <a
            href={href}
            target="_blank"
            rel="noreferrer"
            className="text-sm font-medium text-blue-700 hover:underline"
          >
            Open page
          </a>
        ) : null}
      </div>
    </div>
  );
}

function Badge({ children }) {
  return (
    <span className="rounded-full bg-slate-100 px-3 py-1 text-sm font-medium text-slate-700">
      {children}
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* Action plan                                                                 */
/* -------------------------------------------------------------------------- */

function buildActionPlan({ scan, fixes, healthReport, selectedCms, cmsLabel }) {
  const topActions = safeArray(
    scan?.top_recommended_actions || scan?.recommended_actions
  );

  if (topActions.length > 0) {
    return topActions.slice(0, 3).map((action, index) => ({
      title: action.title || `Action ${index + 1}`,
      reason:
        action.reason ||
        action.why_it_matters ||
        "This is one of the highest value improvements from the scan.",
    }));
  }

  if (healthReport?.next_best_step) {
    return [
      {
        title: "Start with the next best step",
        reason: healthReport.next_best_step,
      },
      {
        title: `Use ${cmsLabel} instructions`,
        reason: `Follow the platform-specific steps under each recommendation for ${cmsLabel}.`,
      },
      {
        title: "Rescan after changes",
        reason:
          "Run another scan after updates are published so the dashboard can confirm what improved.",
      },
    ];
  }

  const priorityFixes = fixes
    .filter((fix) => ["critical", "high", "medium"].includes(fix.priority))
    .slice(0, 3);

  if (priorityFixes.length > 0) {
    return priorityFixes.map((fix) => ({
      title: fix.issue_title || fix.title || "Review this recommendation",
      reason:
        fix.why_it_matters ||
        fix.plain_english_explanation ||
        "This should be reviewed first because it may affect visitors or search visibility.",
    }));
  }

  return [
    {
      title: "Review the recommendations",
      reason:
        "Start with the items marked high priority, then work through the easier content improvements.",
    },
    {
      title: `Use ${cmsLabel} instructions`,
      reason:
        "Pick your website builder above and follow the instructions under each fix.",
    },
    {
      title: "Scan again",
      reason:
        "After publishing changes, run another scan to update the Fix List.",
    },
  ];
}

/* -------------------------------------------------------------------------- */
/* CMS instructions                                                            */
/* -------------------------------------------------------------------------- */

function getCmsInstructions(fix, cms, cmsLabel) {
  const category = String(fix.category || "").toLowerCase();
  const customerCategory = String(fix.customer_category || "").toLowerCase();

  if (isBrokenPageFix(category, customerCategory)) {
    return cmsBrokenPageSteps(cms, cmsLabel);
  }

  if (isTitleFix(category)) {
    return cmsTitleSteps(cms, cmsLabel);
  }

  if (isDescriptionFix(category)) {
    return cmsDescriptionSteps(cms, cmsLabel);
  }

  if (isContentFix(category, customerCategory)) {
    return cmsContentSteps(cms, cmsLabel);
  }

  if (isTechnicalFix(category, customerCategory)) {
    return cmsTechnicalSteps(cms, cmsLabel);
  }

  if (isPerformanceFix(category)) {
    return cmsPerformanceSteps(cms, cmsLabel);
  }

  return [
    `Open the affected page in ${cmsLabel}.`,
    "Review the recommendation and compare it with what is currently on the page.",
    "Make the update, save or publish the page, then run another scan.",
  ];
}

function cmsBrokenPageSteps(cms, cmsLabel) {
  const commonFinal =
    "After fixing or redirecting the page, publish the change and run another scan.";

  const map = {
    wordpress: [
      "In WordPress, go to Pages or Posts and search for the affected URL slug.",
      "If the page should exist, restore it or update its permalink.",
      "If the page is old, create a 301 redirect using a redirect plugin or your SEO plugin.",
      commonFinal,
    ],
    squarespace: [
      "In Squarespace, open Pages and look for the affected page or collection item.",
      "If it should exist, restore or recreate the page.",
      "If it is old, go to Settings > Developer Tools > URL Mappings and add a redirect.",
      commonFinal,
    ],
    wix: [
      "In Wix, open Site Pages and Menu and search for the affected page.",
      "If the page should exist, restore it or update its page URL.",
      "If it is old, go to SEO tools > URL Redirect Manager and create a redirect.",
      commonFinal,
    ],
    shopify: [
      "In Shopify, check Online Store > Pages, Products, Collections, or Blog posts.",
      "If the URL should exist, restore the item or update its handle.",
      "If it is old, go to Online Store > Navigation > View URL redirects and add a redirect.",
      commonFinal,
    ],
    webflow: [
      "In Webflow, check Pages and CMS Collections for the affected slug.",
      "If it should exist, restore or recreate the page.",
      "If it is old, add a 301 redirect in Site settings > Publishing > 301 redirects.",
      commonFinal,
    ],
    framer: [
      "In Framer, open Pages and search for the affected route.",
      "If it should exist, recreate the page or correct the page path.",
      "If it is old, add a redirect in site settings if your Framer plan supports redirects.",
      commonFinal,
    ],
    godaddy: [
      "In GoDaddy Website Builder, open Website > Pages and check whether the page exists.",
      "If it should exist, recreate it or update the page URL.",
      "If the page is old, use GoDaddy redirects or ask your web person to add a redirect.",
      commonFinal,
    ],
  };

  return map[cms] || [
    `Open your CMS and search for the affected page path.`,
    "If the page should exist, restore or recreate it.",
    "If the page is old, create a 301 redirect to the closest live page.",
    commonFinal,
  ];
}

function cmsTitleSteps(cms, cmsLabel) {
  const map = {
    wordpress: [
      "Open the affected page in WordPress.",
      "Use your SEO plugin, such as Yoast, Rank Math, or All in One SEO, to edit the SEO title.",
      "Keep the title clear, specific, and around 50–60 characters.",
      "Update the page and rescan.",
    ],
    squarespace: [
      "Open Pages in Squarespace and click the gear icon beside the affected page.",
      "Go to SEO or Marketing settings.",
      "Update the SEO title with a clear page-specific title.",
      "Save and rescan.",
    ],
    wix: [
      "Open the Wix editor and go to Site Pages.",
      "Click the affected page, then open SEO Basics.",
      "Update the title tag with a clear page-specific title.",
      "Publish and rescan.",
    ],
    shopify: [
      "Open the affected product, collection, page, or blog post in Shopify.",
      "Scroll to Search engine listing and click Edit.",
      "Update the page title.",
      "Save and rescan.",
    ],
    webflow: [
      "Open Webflow Pages or the CMS Collection item.",
      "Open page settings.",
      "Update the Title Tag in SEO Settings.",
      "Publish and rescan.",
    ],
    framer: [
      "Open the affected page in Framer.",
      "Open page settings.",
      "Update the page title / metadata title.",
      "Publish and rescan.",
    ],
  };

  return map[cms] || [
    `Open the affected page in ${cmsLabel}.`,
    "Find the SEO title or metadata title field.",
    "Write a clear title that explains the page topic.",
    "Publish and rescan.",
  ];
}

function cmsDescriptionSteps(cms, cmsLabel) {
  const map = {
    wordpress: [
      "Open the affected page in WordPress.",
      "Use your SEO plugin to edit the meta description.",
      "Write 1–2 helpful sentences explaining what the visitor will find.",
      "Update the page and rescan.",
    ],
    squarespace: [
      "Open the page settings in Squarespace.",
      "Go to the SEO section.",
      "Write a helpful SEO description.",
      "Save and rescan.",
    ],
    wix: [
      "Open the page in Wix Site Pages.",
      "Go to SEO Basics.",
      "Update the meta description.",
      "Publish and rescan.",
    ],
    shopify: [
      "Open the affected product, collection, page, or blog post.",
      "Scroll to Search engine listing and click Edit.",
      "Update the meta description.",
      "Save and rescan.",
    ],
    webflow: [
      "Open the page or CMS item in Webflow.",
      "Open SEO Settings.",
      "Update the Meta Description field.",
      "Publish and rescan.",
    ],
    framer: [
      "Open the affected page in Framer.",
      "Open page settings.",
      "Update the description metadata.",
      "Publish and rescan.",
    ],
  };

  return map[cms] || [
    `Open the affected page in ${cmsLabel}.`,
    "Find the SEO description or meta description field.",
    "Write a short description that explains the page clearly.",
    "Publish and rescan.",
  ];
}

function cmsContentSteps(cms, cmsLabel) {
  return [
    `Open the affected page in ${cmsLabel}.`,
    "Add helpful content that answers real visitor questions.",
    "Include proof points such as reviews, location details, experience, pricing context, process details, or FAQs.",
    "Make sure the page has one clear main heading and one clear next step.",
    "Publish the update and run another scan.",
  ];
}

function cmsTechnicalSteps(cms, cmsLabel) {
  const map = {
    wordpress: [
      "Open the affected page in WordPress and check your SEO plugin settings.",
      "Review indexability, canonical URL, social preview, schema, and page template settings.",
      "If you are unsure, send this recommendation to your web person.",
      "After changes are made, clear cache if needed and rescan.",
    ],
    squarespace: [
      "Open the affected page settings in Squarespace.",
      "Review SEO settings, social image/settings, URL slug, and page visibility.",
      "For advanced schema or canonical issues, send this to your web person.",
      "Save changes and rescan.",
    ],
    wix: [
      "Open the affected page in Wix and go to SEO settings.",
      "Review SEO Basics, Advanced SEO, structured data, and page visibility.",
      "For advanced issues, use Wix SEO tools or ask your web person.",
      "Publish and rescan.",
    ],
    shopify: [
      "Open the affected product, collection, page, or theme template.",
      "Review the search listing, theme SEO fields, structured data, and app-generated SEO settings.",
      "For template or schema issues, ask your Shopify developer.",
      "Save, publish if needed, and rescan.",
    ],
    webflow: [
      "Open the affected page or CMS template in Webflow.",
      "Review SEO settings, Open Graph settings, canonical settings, and custom code.",
      "For template or JavaScript issues, ask your Webflow developer.",
      "Publish and rescan.",
    ],
    framer: [
      "Open the affected page settings in Framer.",
      "Review metadata, social preview, page path, and visibility.",
      "For advanced script or structured data issues, ask your web person.",
      "Publish and rescan.",
    ],
  };

  return map[cms] || [
    `Open the affected page or template in ${cmsLabel}.`,
    "Review SEO visibility, canonical settings, metadata, social preview, and structured data.",
    "Ask your web person to handle anything involving templates, code, or scripts.",
    "Publish and rescan.",
  ];
}

function cmsPerformanceSteps(cms, cmsLabel) {
  return [
    `Open the affected page or template in ${cmsLabel}.`,
    "Compress oversized images and remove unnecessary sections, apps, scripts, or embeds.",
    "Check whether important text is visible without relying too heavily on scripts.",
    "Ask your web person to review theme, template, and JavaScript performance.",
    "Publish the changes and rescan.",
  ];
}

/* -------------------------------------------------------------------------- */
/* Classification helpers                                                      */
/* -------------------------------------------------------------------------- */

function isBrokenPageFix(category, customerCategory) {
  return (
    category.includes("broken") ||
    category.includes("404") ||
    customerCategory.includes("broken")
  );
}

function isTitleFix(category) {
  return category.includes("title");
}

function isDescriptionFix(category) {
  return category.includes("description");
}

function isContentFix(category, customerCategory) {
  return (
    category.includes("thin_content") ||
    category.includes("page_heading") ||
    category.includes("faq") ||
    customerCategory.includes("content") ||
    customerCategory.includes("trust")
  );
}

function isTechnicalFix(category, customerCategory) {
  return (
    category.includes("canonical") ||
    category.includes("schema") ||
    category.includes("index") ||
    category.includes("robots") ||
    category.includes("social") ||
    category.includes("mobile") ||
    category.includes("internal_link") ||
    customerCategory.includes("technical")
  );
}

function isPerformanceFix(category) {
  return (
    category.includes("performance") ||
    category.includes("js_rendering") ||
    category.includes("web_dev")
  );
}

function needsWebHelp(fix) {
  return (
    fix.requires_developer === true ||
    fix.status === "needs_developer" ||
    fix.difficulty === "developer" ||
    fix.who_can_do_this === "your_web_person"
  );
}

/* -------------------------------------------------------------------------- */
/* Storage                                                                     */
/* -------------------------------------------------------------------------- */

function loadBestScanRecord() {
  const records = [];

  for (const key of LAST_SCAN_KEYS) {
    const parsed = safeJsonParse(window.localStorage.getItem(key));
    collectRecords(parsed, records);
  }

  for (const key of SCAN_HISTORY_KEYS) {
    const parsed = safeJsonParse(window.localStorage.getItem(key));
    collectRecords(parsed, records);
  }

  try {
    for (let i = 0; i < window.localStorage.length; i++) {
      const key = window.localStorage.key(i);

      if (!key) continue;

      const lowerKey = key.toLowerCase();

      if (
        !lowerKey.includes("scan") &&
        !lowerKey.includes("seo_autopilot") &&
        !lowerKey.includes("seo-autopilot")
      ) {
        continue;
      }

      const parsed = safeJsonParse(window.localStorage.getItem(key));
      collectRecords(parsed, records);
    }
  } catch {
    // Ignore broad localStorage search errors.
  }

  const normalized = records
    .map(normalizeStoredRecord)
    .filter(Boolean)
    .filter((record) => record.result);

  const useful = normalized.filter(recordHasUsefulData);

  const candidates = useful.length > 0 ? useful : normalized;

  if (candidates.length === 0) return null;

  return candidates.sort(compareRecordsByQualityAndDate)[0];
}

function collectRecords(value, records) {
  if (!value) return;

  if (Array.isArray(value)) {
    value.forEach((item) => collectRecords(item, records));
    return;
  }

  if (typeof value === "object") {
    records.push(value);
  }
}

function normalizeStoredRecord(value) {
  if (!value || typeof value !== "object") return null;

  const result = value.result && typeof value.result === "object" ? value.result : value;

  const websiteUrl =
    value.website_url ||
    result.normalized_url ||
    result.website_url ||
    result.url ||
    "";

  const createdAt =
    value.created_at ||
    result.created_at ||
    value.completed_at ||
    result.completed_at ||
    value.date ||
    result.date ||
    "";

  return {
    id: value.id || result.id || `scan_${stableString(websiteUrl + createdAt)}`,
    created_at: createdAt,
    website_url: websiteUrl,
    result,
  };
}

function recordHasUsefulData(record) {
  const result = record?.result || {};
  const pages = getPages(result);
  const fixes = getFixes(result);

  return pages.length > 0 || fixes.length > 0;
}

function compareRecordsByQualityAndDate(a, b) {
  const aUseful = recordHasUsefulData(a) ? 1 : 0;
  const bUseful = recordHasUsefulData(b) ? 1 : 0;

  if (aUseful !== bUseful) return bUseful - aUseful;

  const aPages = getPages(a.result).length;
  const bPages = getPages(b.result).length;

  if (aPages !== bPages) return bPages - aPages;

  const aFixes = getFixes(a.result).length;
  const bFixes = getFixes(b.result).length;

  if (aFixes !== bFixes) return bFixes - aFixes;

  const aTime = Date.parse(a.created_at || "") || 0;
  const bTime = Date.parse(b.created_at || "") || 0;

  return bTime - aTime;
}

/* -------------------------------------------------------------------------- */
/* Data helpers                                                                */
/* -------------------------------------------------------------------------- */

function getFixes(scan) {
  return pickFirstNonEmptyArray([
    scan?.cleaned_fixes,
    scan?.fixes,
    scan?.findings,
    scan?.recommendations,
    scan?.raw_fixes,
    scan?.grouped_findings,
    scan?.raw_findings,
    scan?.issues,
  ]);
}

function getPages(scan) {
  return pickFirstNonEmptyArray([
    scan?.crawled_pages,
    scan?.pages,
    scan?.scanned_pages,
    scan?.crawl_pages,
  ]);
}

function buildFriendlyAffectedPages(fix) {
  const examples = safeArray(fix?.details?.examples);
  const affectedPages = safeArray(fix?.affected_pages);

  if (examples.length > 0) {
    return examples
      .map((example) => {
        const rawUrl = example.url || example.page_url || example.path || "";
        const path = cleanPath(rawUrl);

        if (!path) return null;

        return {
          path,
          label:
            cleanString(example.readable_label) ||
            cleanString(example.title) ||
            friendlyPageLabel(path) ||
            "Affected page",
          statusCode: example.status_code || example.status || "",
        };
      })
      .filter(Boolean);
  }

  return affectedPages
    .map((page) => {
      const path = cleanPath(page);

      if (!path) return null;

      return {
        path,
        label: friendlyPageLabel(path),
        statusCode: "",
      };
    })
    .filter(Boolean);
}

function friendlyPageLabel(pathOrUrl) {
  const path = cleanPath(pathOrUrl);
  const language = getLanguageNameFromPath(path);

  const cleaned = path
    .replace(/^\/(en|fr|es|de|it|pt|nl)(\/|$)/i, "/")
    .replace(/^\/+/, "")
    .replace(/\/+$/, "");

  if (!cleaned) {
    return language ? `${language} homepage` : "Homepage";
  }

  const parts = cleaned.split("/").filter(Boolean);

  if (parts[0] === "category" && parts[1]) {
    const category = humanizeSlug(parts.slice(1).join(" / "));

    return language
      ? `${language} category page: ${category}`
      : `Category page: ${category}`;
  }

  if (parts[0] === "wine" && parts[1]) {
    return `Wine page: ${humanizeSlug(parts.slice(1).join(" / "))}`;
  }

  if (parts[0] === "listing" && parts[1]) {
    return `Listing page: ${humanizeSlug(parts.slice(1).join(" / "))}`;
  }

  if (parts[0] === "annonce" && parts[1]) {
    return `Activity page: ${humanizeSlug(parts[1])}`;
  }

  const label = humanizeSlug(parts.join(" / "));

  return language ? `${language} page: ${label}` : label;
}

function getLanguageNameFromPath(pathOrUrl) {
  const path = cleanPath(pathOrUrl);
  const match = path.match(/^\/(en|fr|es|de|it|pt|nl)(\/|$)/i);

  if (!match) return "";

  const map = {
    en: "English",
    fr: "French",
    es: "Spanish",
    de: "German",
    it: "Italian",
    pt: "Portuguese",
    nl: "Dutch",
  };

  return map[match[1].toLowerCase()] || "";
}

function buildPageHref(path, scan) {
  try {
    const base =
      scan?.normalized_url ||
      scan?.website_url ||
      scan?.scan_summary?.website_url ||
      "";

    if (!base) return "";

    const origin = new URL(base).origin;

    return new URL(path, origin).toString();
  } catch {
    return "";
  }
}

/* -------------------------------------------------------------------------- */
/* Generic helpers                                                             */
/* -------------------------------------------------------------------------- */

function pickFirstNonEmptyArray(values) {
  for (const value of values || []) {
    if (Array.isArray(value) && value.length > 0) return value;
  }

  return [];
}

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

function safeJsonParse(value) {
  try {
    if (!value) return null;
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function numberOrNull(value) {
  if (value === null || value === undefined || value === "") return null;

  const number = Number(value);

  return Number.isFinite(number) ? number : null;
}

function cleanString(value) {
  return typeof value === "string" && value.trim() ? value.trim() : "";
}

function cleanPath(input) {
  try {
    const parsed = new URL(String(input || ""), "https://example.com");
    const path = parsed.pathname || "/";

    return path !== "/" && path.endsWith("/") ? path.slice(0, -1) : path;
  } catch {
    const value = String(input || "/").split("?")[0].split("#")[0];

    if (!value || value === "/") return "/";

    return value.endsWith("/") && value !== "/" ? value.slice(0, -1) : value;
  }
}

function humanizeSlug(value) {
  return String(value || "")
    .replace(/-/g, " ")
    .replace(/_/g, " ")
    .replace(/\s*\/\s*/g, " / ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function friendlyCategory(category) {
  const map = {
    meta_title: "Search appearance",
    meta_description: "Search appearance",
    canonical: "Technical SEO",
    schema: "Technical SEO",
    thin_content: "Page content",
    duplicate_content: "Search appearance",
    "404_error": "Broken pages",
    broken_page: "Broken pages",
    redirect: "Page redirects",
    internal_link: "Technical SEO",
    performance: "Website performance",
    web_dev: "Website setup",
    robots_txt: "Search visibility",
    js_rendering: "Website setup",
    indexability: "Technical SEO",
    mobile_setup: "Technical SEO",
    social_metadata: "Technical SEO",
    performance_hint: "Technical SEO",
    competitor_gap: "Competitor opportunities",
  };

  return map[category] || "Website improvement";
}

function scoreToLabel(score) {
  if (score === null || score === undefined) return "Run a scan";
  if (score >= 85) return "Strong";
  if (score >= 70) return "Good start";
  if (score >= 45) return "Needs attention";
  return "Needs urgent attention";
}

function calculateFallbackScore(fixes) {
  let score = 100;

  for (const fix of fixes || []) {
    if (fix.priority === "critical") score -= 16;
    else if (fix.priority === "high") score -= 10;
    else if (fix.priority === "medium") score -= 5;
    else if (fix.priority === "low") score -= 2;
  }

  return Math.max(0, Math.min(100, score));
}

function formatDate(value) {
  if (!value) return "No scan yet";

  try {
    return new Intl.DateTimeFormat("en", {
      month: "short",
      day: "numeric",
      year: "numeric",
    }).format(new Date(value));
  } catch {
    return String(value);
  }
}

function stableString(value) {
  let hash = 0;
  const text = String(value || "");

  for (let i = 0; i < text.length; i++) {
    hash = (hash << 5) - hash + text.charCodeAt(i);
    hash |= 0;
  }

  return Math.abs(hash);
}