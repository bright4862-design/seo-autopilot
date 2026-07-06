import { base44 } from "@/api/base44Client";
import { ACTIVE_STATUSES } from "@/lib/friendlyLabels";

// Resolves the active project the same way everywhere:
// 1. localStorage "active_project_id" if it still exists
// 2. otherwise the user's most recently crawled project
// Persists the choice back to localStorage.
export async function getActiveProject() {
  const user = await base44.auth.me();

  const storedId = window.localStorage.getItem("active_project_id");
  let project = null;

  if (storedId) {
    try {
      project = await base44.entities.BusinessProject.get(storedId);
    } catch {
      // Stored project no longer exists — fall through.
    }
  }

  if (!project) {
    const projects = await base44.entities.BusinessProject.list("-last_crawl_at", 10);
    project =
      projects.find(
        (item) => item.owner_user_id === user.id || item.created_by_id === user.id
      ) ||
      projects[0] ||
      null;
  }

  if (project) {
    window.localStorage.setItem("active_project_id", project.id);
  }

  return { user, project };
}

// The one definition of entity-backed issues the user should see.
export async function getVisibleIssues(projectId, userId) {
  const issues = await base44.entities.SeoIssue.filter({
    project_id: projectId,
    owner_user_id: userId,
  });

  return (issues || []).filter((issue) => ACTIVE_STATUSES.has(issue.status));
}
