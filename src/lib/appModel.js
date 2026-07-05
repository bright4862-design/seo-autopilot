export const BUCKETS = [
  {
    key: "auto_fixed",
    title: "Prepared",
    subtitle: "Recommendations prepared for review.",
    empty: "Nothing is prepared right now.",
  },
  {
    key: "needs_approval",
    title: "Needs review",
    subtitle: "Items that need your decision.",
    empty: "Nothing needs review right now.",
  },
  {
    key: "needs_developer",
    title: "May need help",
    subtitle: "Larger improvements for a website editor or done-for-you help.",
    empty: "No larger improvements found right now.",
  },
];

export const ACTIVE_STATUSES = new Set([
  "auto_fixed",
  "needs_approval",
  "needs_developer",
  "open",
  "in_progress",
]);

export const DONE_STATUSES = new Set([
  "approved",
  "completed",
]);

export function getIssueBucket(issue) {
  if (issue.status === "auto_fixed") return "auto_fixed";
  if (issue.status === "needs_approval") return "needs_approval";
  if (issue.status === "needs_developer") return "needs_developer";

  if (issue.requires_developer) return "needs_developer";
  if (issue.requires_approval) return "needs_approval";
  if (issue.can_auto_fix) return "auto_fixed";

  return "needs_approval";
}

export function countBuckets(issues = []) {
  return issues.reduce(
    (acc, issue) => {
      const bucket = getIssueBucket(issue);
      acc[bucket] += 1;
      return acc;
    },
    {
      auto_fixed: 0,
      needs_approval: 0,
      needs_developer: 0,
    }
  );
}

export function getFirstStep(counts) {
  if (counts.needs_approval > 0) {
    return "Start with the items that need your review.";
  }

  if (counts.needs_developer > 0) {
    return "Start with the improvements that may need help.";
  }

  if (counts.auto_fixed > 0) {
    return "Start by reviewing your prepared recommendations.";
  }

  return "Your scan looks clean based on the website content we reviewed.";
}

export async function resolveActiveProject(base44) {
  const user = await base44.auth.me();
  const activeProjectId = window.localStorage.getItem("active_project_id");
  let activeProject = null;

  if (activeProjectId) {
    try {
      activeProject = await base44.entities.BusinessProject.get(activeProjectId);
    } catch {}
  }

  if (!activeProject) {
    const projects = await base44.entities.BusinessProject.list("-last_crawl_at", 10);

    activeProject =
      projects.find(
        (item) => item.owner_user_id === user.id || item.created_by_id === user.id
      ) ||
      projects[0] ||
      null;
  }

  if (activeProject) {
    window.localStorage.setItem("active_project_id", activeProject.id);
  }

  return { user, project: activeProject };
}

export function getScoreBand(score) {
  if (typeof score !== "number") return null;
  if (score >= 85) return "Strong foundation";
  if (score >= 70) return "Good, with cleanup opportunities";
  if (score >= 50) return "Needs focused improvement";
  return "Needs attention";
}

export function getScoreTrend(crawls = []) {
  const completed = crawls
    .filter((crawl) => crawl.status === "complete" && typeof crawl.seo_score === "number")
    .sort((a, b) => new Date(b.completed_at || b.started_at || 0) - new Date(a.completed_at || a.started_at || 0));

  if (completed.length < 2) return null;

  return Math.round(completed[0].seo_score - completed[1].seo_score);
}