import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();

    if (!user) {
      return Response.json(
        { success: false, error: "Unauthorized" },
        { status: 401 }
      );
    }

    const body = await req.json();
    const projectId = body.projectId || body.project_id;

    if (!projectId) {
      return Response.json(
        { success: false, error: "projectId is required" },
        { status: 400 }
      );
    }

    const project = await base44.entities.BusinessProject.get(projectId);

    if (!project) {
      return Response.json(
        { success: false, error: "Project not found" },
        { status: 404 }
      );
    }

    if (
      project.owner_user_id &&
      project.owner_user_id !== user.id &&
      project.created_by_id !== user.id
    ) {
      return Response.json(
        { success: false, error: "Forbidden" },
        { status: 403 }
      );
    }

    const [issues, jobs, pages, competitorInsights] = await Promise.all([
      base44.entities.SeoIssue.filter({ project_id: projectId }).catch(() => []),
      base44.entities.CrawlJob.filter({ project_id: projectId }, "-created_date", 5).catch(() => []),
      base44.entities.CrawledPage.filter({ project_id: projectId }).catch(() => []),
      base44.entities.CompetitorInsight.filter({ project_id: projectId }).catch(() => []),
    ]);

    const activeIssues = issues.filter((issue) =>
      ["auto_fixed", "needs_approval", "needs_developer", "open", "in_progress"].includes(
        issue.status
      )
    );

    const prepared = activeIssues.filter(
      (issue) => issue.status === "auto_fixed" || issue.can_auto_fix
    ).length;

    const needsReview = activeIssues.filter(
      (issue) => issue.status === "needs_approval" || issue.requires_approval
    ).length;

    const mayNeedHelp = activeIssues.filter(
      (issue) => issue.status === "needs_developer" || issue.requires_developer
    ).length;

    const highPriority = activeIssues.filter(
      (issue) => issue.priority === "critical" || issue.priority === "high"
    ).length;

    const latestJob = jobs[0] || null;

    const seoScore = normalizeScore(
      latestJob?.seo_score || project.seo_score || 0
    );

    const topIssues = activeIssues
      .sort((a, b) => {
        const priorityRank = {
          critical: 0,
          high: 1,
          medium: 2,
          low: 3,
        };

        return (
          (priorityRank[a.priority] ?? 9) -
          (priorityRank[b.priority] ?? 9)
        );
      })
      .slice(0, 5);

    const summary = buildSummary({
      project,
      seoScore,
      pages,
      activeIssues,
      prepared,
      needsReview,
      mayNeedHelp,
      highPriority,
      competitorInsights,
    });

    const nextSteps = buildNextSteps({
      topIssues,
      prepared,
      needsReview,
      mayNeedHelp,
      competitorInsights,
    });

    const report = await base44.entities.Report.create({
      project_id: projectId,
      owner_user_id: user.id,
      summary,
      fixed_count: prepared,
      approval_count: needsReview,
      developer_count: mayNeedHelp,
      seo_score: seoScore,
      next_steps: nextSteps.join("\n"),
    });

    return Response.json({
      success: true,
      report,
      summary,
      counts: {
        total_recommendations: activeIssues.length,
        prepared,
        needs_review: needsReview,
        may_need_help: mayNeedHelp,
        high_priority: highPriority,
        pages_reviewed: pages.length,
        competitor_insights: competitorInsights.length,
      },
      next_steps: nextSteps,
    });
  } catch (error) {
    return Response.json(
      {
        success: false,
        error: error?.message || "Report generation failed",
      },
      { status: 500 }
    );
  }
});

function buildSummary({
  project,
  seoScore,
  pages,
  activeIssues,
  prepared,
  needsReview,
  mayNeedHelp,
  highPriority,
  competitorInsights,
}) {
  const site = project.website_url || "this website";
  const pageCount = pages.length;

  const intro =
    seoScore >= 85
      ? `${site} has a strong SEO foundation.`
      : seoScore >= 70
        ? `${site} has a good SEO foundation with a few cleanup opportunities.`
        : `${site} has several SEO opportunities worth reviewing.`;

  const pageText =
    pageCount > 0
      ? `We reviewed ${pageCount} page${pageCount === 1 ? "" : "s"}.`
      : "We reviewed the available scan data.";

  const issueText =
    activeIssues.length > 0
      ? `SEO Autopilot prepared ${activeIssues.length} recommendation${
          activeIssues.length === 1 ? "" : "s"
        }: ${prepared} prepared, ${needsReview} needing review, and ${mayNeedHelp} that may need help.`
      : "No major recommendations were found from the pages we could access.";

  const priorityText =
    highPriority > 0
      ? `${highPriority} recommendation${
          highPriority === 1 ? " is" : "s are"
        } high priority.`
      : "No high-priority recommendations stood out.";

  const competitorText =
    competitorInsights.length > 0
      ? `We also found ${competitorInsights.length} competitor opportunity${
          competitorInsights.length === 1 ? "" : "ies"
        }.`
      : "No competitor opportunities were saved for this report yet.";

  return [intro, pageText, issueText, priorityText, competitorText].join(" ");
}

function buildNextSteps({
  topIssues,
  prepared,
  needsReview,
  mayNeedHelp,
  competitorInsights,
}) {
  const steps = [];

  if (topIssues.length > 0) {
    steps.push(`Start with: ${topIssues[0].issue_title}`);
  }

  if (prepared > 0) {
    steps.push("Review the prepared search titles and descriptions first.");
  }

  if (needsReview > 0) {
    steps.push("Review recommendations that need a decision before making changes.");
  }

  if (mayNeedHelp > 0) {
    steps.push("Send the “May need help” items to a website editor or cleanup provider.");
  }

  if (competitorInsights.length > 0) {
    steps.push("Review competitor opportunities for missing service details, FAQs, proof points, and calls to action.");
  }

  if (steps.length === 0) {
    steps.push("Run another scan after making website updates.");
  }

  return steps;
}

function normalizeScore(value) {
  const number = Number(value);

  if (!Number.isFinite(number) || number <= 0) return 0;

  return Math.max(0, Math.min(100, Math.round(number)));
}