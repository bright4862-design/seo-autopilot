from pathlib import Path
import re


def sub1(text, pattern, replacement, label, flags=0):
    updated, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    return updated


path = Path("src/pages/FixList.jsx")
text = path.read_text(encoding="utf-8")

state = '''  const topActions = getTopActions(scanRecord, recommendations);
  const counts = countBuckets(recommendations);
  const summary = getBestSummary(scanRecord, healthScore, pagesScanned, recommendations.length);
'''
state_new = '''  const topActions = getTopActions(scanRecord, recommendations);
  const counts = countBuckets(recommendations);
  const noHighConfidenceFindings = isNoHighConfidenceFindings(scanRecord, recommendations);
  const healthGrade = getHealthGrade(scanRecord, healthScore, noHighConfidenceFindings);
  const nextBestStep = getNextBestStep(scanRecord, noHighConfidenceFindings);
  const summary = getBestSummary(scanRecord, healthScore, pagesScanned, recommendations.length);
'''
if state not in text:
    raise SystemExit("FixList state anchor not found")
text = text.replace(state, state_new, 1)
text = text.replace(
    '            <NextStepCard counts={counts} onReview={() => scrollToRecommendations()} />',
    '            <NextStepCard counts={counts} onReview={() => scrollToRecommendations()} noHighConfidenceFindings={noHighConfidenceFindings} nextBestStep={nextBestStep} />',
    1,
)
text = text.replace(
    '<WebsiteHealthCard healthScore={healthScore} pagesScanned={pagesScanned} createdAt={scanRecord?.created_at} />',
    '<WebsiteHealthCard healthScore={healthScore} healthGrade={healthGrade} pagesScanned={pagesScanned} createdAt={scanRecord?.created_at} />',
    1,
)
text = text.replace(
    '<EmptyFilteredState />',
    '<EmptyFilteredState noHighConfidenceFindings={noHighConfidenceFindings} nextBestStep={nextBestStep} />',
    1,
)

next_card = '''function NextStepCard({ counts, onReview, noHighConfidenceFindings = false, nextBestStep = "" }) {
  const activeBucket = BUCKET_ORDER.find((key) => Number(counts[key] || 0) > 0);
  const bucket = activeBucket ? BUCKETS[activeBucket] : null;
  return (
    <section className="rounded-3xl border border-slate-200/80 bg-white p-6 shadow-sm sm:p-7">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-medium text-indigo-600">Your next step</p>
          <h2 className="mt-2 text-xl font-semibold text-slate-950">
            {noHighConfidenceFindings ? "No high-confidence issues were found in this scanned sample." : bucket ? `Start with ${bucket.title}` : "Your scan has recommendations ready."}
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {noHighConfidenceFindings ? (nextBestStep || "Consider a deeper crawl or manually reviewing key money pages.") : (bucket?.subtitle || "Review the highest-impact items first.")}
          </p>
        </div>
        {!noHighConfidenceFindings ? (
          <Button type="button" onClick={onReview} className="shrink-0 rounded-full bg-indigo-600 px-6 text-sm font-medium text-white shadow-none hover:bg-indigo-700">
            {bucket?.cta || "Review recommendations"}
            <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        ) : null}
      </div>
    </section>
  );
}'''
text = sub1(text, r'function NextStepCard\(\{ counts, onReview \}\) \{.*?\n\}', next_card, "NextStepCard", re.S)

health_card = '''function WebsiteHealthCard({ healthScore, healthGrade = "", pagesScanned, createdAt }) {
  const band = getScoreBand(healthScore);
  const displayedGrade = healthGrade || band.label;
  const gradeClassName = healthGrade && healthGrade !== band.label ? "bg-slate-100 text-slate-700" : band.className;
  return (
    <section className="rounded-3xl border border-slate-200/80 bg-white p-6 shadow-sm">
      <h2 className="text-base font-semibold text-slate-950">Website health</h2>
      <div className="mt-4 space-y-4">
        <div>
          <div className="text-5xl font-bold tracking-tight text-slate-950">{healthScore || "—"}</div>
          <span className={`mt-3 inline-flex rounded-full px-3 py-1 text-xs font-medium ${gradeClassName}`}>{displayedGrade}</span>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
          <MiniStat label="Pages checked" value={pagesScanned || 0} icon={FileText} />
          <MiniStat label="Last scan" value={createdAt ? formatDate(createdAt) : "Recent"} icon={CheckCircle2} />
        </div>
      </div>
    </section>
  );
}'''
text = sub1(text, r'function WebsiteHealthCard\(\{ healthScore, pagesScanned, createdAt \}\) \{.*?\n\}', health_card, "WebsiteHealthCard", re.S)

empty_state = '''function EmptyFilteredState({ noHighConfidenceFindings = false, nextBestStep = "" }) {
  return (
    <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
      <p className="text-sm font-medium text-slate-950">
        {noHighConfidenceFindings ? "No high-confidence recommendations were found in this sample." : "No recommendations match this filter."}
      </p>
      <p className="mt-1 text-sm text-slate-500">
        {noHighConfidenceFindings ? (nextBestStep || "Consider a deeper crawl or manually reviewing key money pages.") : "Choose another priority filter to see more items."}
      </p>
    </div>
  );
}'''
text = sub1(text, r'function EmptyFilteredState\(\) \{.*?\n\}', empty_state, "EmptyFilteredState", re.S)

helpers = '''function isNoHighConfidenceFindings(record, recommendations = []) {
  const scanStatus = String(record?.scan_status || "");
  if (["incomplete_evidence", "blocked_or_incomplete"].includes(scanStatus)) return false;
  return record?.no_high_confidence_findings === true
    || record?.review_confidence_state === "no_high_confidence_findings"
    || scanStatus === "complete_no_high_confidence_findings"
    || recommendations.length === 0;
}

function getHealthGrade(record, healthScore, noHighConfidenceFindings) {
  return cleanString(record?.website_health_report?.health_grade || record?.health_grade)
    || (noHighConfidenceFindings ? "No issues found in sample" : getScoreBand(healthScore).label);
}

function getNextBestStep(record, noHighConfidenceFindings) {
  return cleanString(record?.website_health_report?.next_best_step || record?.next_best_step)
    || (noHighConfidenceFindings ? "No high-confidence issues were found in the scanned sample — consider a deeper crawl or manual review of money pages." : "");
}

'''
if "function isNoHighConfidenceFindings" not in text:
    anchor = "function getBestSummary(record, healthScore, pagesScanned, issueCount) {\n"
    if anchor not in text:
        raise SystemExit("helper anchor not found")
    text = text.replace(anchor, helpers + anchor, 1)
path.write_text(text, encoding="utf-8")
