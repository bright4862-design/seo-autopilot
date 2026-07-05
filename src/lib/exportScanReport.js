import { jsPDF } from "jspdf";

// Generates a customer-friendly PDF scan report and triggers download.
export function exportScanReportPdf({ project, crawlJob, issues, devRecs, insights }) {
  const doc = new jsPDF();
  const pageW = doc.internal.pageSize.getWidth();
  const marginX = 16;
  const maxW = pageW - marginX * 2;
  let y = 20;

  const ensureSpace = (needed = 10) => {
    if (y + needed > 280) {
      doc.addPage();
      y = 20;
    }
  };

  const heading = (text) => {
    ensureSpace(14);
    y += 4;
    doc.setFont("helvetica", "bold");
    doc.setFontSize(13);
    doc.setTextColor(30, 41, 59);
    doc.text(text, marginX, y);
    y += 7;
  };

  const line = (text, options = {}) => {
    doc.setFont("helvetica", options.bold ? "bold" : "normal");
    doc.setFontSize(options.size || 10);
    doc.setTextColor(...(options.color || [55, 65, 81]));
    const wrapped = doc.splitTextToSize(text, maxW - (options.indent || 0));
    ensureSpace(wrapped.length * 5 + 2);
    doc.text(wrapped, marginX + (options.indent || 0), y);
    y += wrapped.length * 5 + (options.gap ?? 2);
  };

  const prepared = issues.filter(i => i.status === "auto_fixed");
  const approval = issues.filter(i => i.status === "needs_approval");
  const developer = issues.filter(i => i.status === "needs_developer");
  const scanDate = crawlJob?.completed_at || crawlJob?.created_date || project.last_crawl_at;

  // Title
  doc.setFont("helvetica", "bold");
  doc.setFontSize(18);
  doc.setTextColor(37, 99, 235);
  doc.text("Website Scan Report", marginX, y);
  y += 10;

  line(`Business: ${project.business_name}`, { bold: true, size: 11 });
  line(`Website: ${project.website_url}`, { size: 11 });
  line(`Scan date: ${scanDate ? new Date(scanDate).toLocaleDateString() : "—"}`, { size: 11, gap: 4 });

  heading("At a glance");
  line(`Website health score: ${project.seo_score ?? crawlJob?.seo_score ?? "—"} / 100`);
  line(`Pages scanned: ${crawlJob?.pages_crawled ?? "—"}`);
  line(`Total recommended improvements: ${issues.length}`);
  line(`Prepared fixes: ${prepared.length}`);
  line(`Needs your approval: ${approval.length}`);
  line(`Website improvements: ${developer.length}`);

  heading("Top recommended actions");
  const actions = [];
  if (approval.length > 0) actions.push("Review the items waiting for your approval first.");
  if (prepared.length > 0) actions.push("Review the fixes we prepared for you.");
  if (developer.length > 0) actions.push("Review the website improvements with your developer.");
  if (actions.length === 0) {
    line("No major issues found. Your site is looking good!");
  } else {
    actions.forEach((a, i) => line(`${i + 1}. ${a}`));
  }

  const issueList = (title, items, emptyText) => {
    heading(title);
    if (items.length === 0) {
      line(emptyText);
      return;
    }
    items.forEach(item => {
      line(`• ${item.issue_title}`, { bold: true });
      if (item.page_url) line(`Page: ${item.page_url}`, { indent: 4, color: [107, 114, 128], size: 9 });
      if (item.plain_english_explanation) line(item.plain_english_explanation, { indent: 4, gap: 4 });
    });
  };

  issueList("Top prepared fixes", prepared.slice(0, 10), "No prepared fixes in this scan.");
  issueList("Needs your approval", approval.slice(0, 10), "Nothing is waiting for your approval.");

  heading("Website improvements");
  if (devRecs.length === 0 && developer.length === 0) {
    line("No website improvements needed right now.");
  } else {
    const recs = devRecs.length > 0 ? devRecs : developer;
    recs.slice(0, 10).forEach(r => {
      line(`• ${r.title || r.issue_title}`, { bold: true });
      if (r.description || r.plain_english_explanation) line(r.description || r.plain_english_explanation, { indent: 4 });
      if (r.business_impact || r.why_it_matters) line(`Why it matters: ${r.business_impact || r.why_it_matters}`, { indent: 4, color: [107, 114, 128], size: 9, gap: 4 });
    });
  }

  if (insights.length > 0) {
    heading("Competitor gaps");
    insights.slice(0, 8).forEach(i => {
      line(`• ${i.insight_title}`, { bold: true });
      if (i.explanation) line(i.explanation, { indent: 4 });
      if (i.recommended_action) line(`What to do: ${i.recommended_action}`, { indent: 4, color: [107, 114, 128], size: 9, gap: 4 });
    });
  }

  heading("Recommended next steps");
  const steps = [];
  if (approval.length > 0) steps.push("Approve or reject the fixes waiting for your review.");
  if (prepared.length > 0) steps.push("Apply the prepared fixes on your website.");
  if (developer.length > 0 || devRecs.length > 0) steps.push("Share the website improvements list with your developer.");
  if (insights.length > 0) steps.push("Close the competitor gaps above to catch up with stronger competitors.");
  steps.push("Run a new scan after making changes to track your progress.");
  steps.forEach((s, i) => line(`${i + 1}. ${s}`));

  const safeName = (project.business_name || "website").replace(/[^a-z0-9]+/gi, "-").toLowerCase();
  doc.save(`scan-report-${safeName}.pdf`);
}