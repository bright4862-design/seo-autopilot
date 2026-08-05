import { base44 } from "@/api/base44Client";
import { ACTIVE_STATUSES } from "@/lib/friendlyLabels";
import { normalizeScanTarget, normalizedScanDomain } from "@/lib/scanRunIdentity";
import {
  clearCustomerAuthBoundary,
  readCustomerActiveProject,
  writeCustomerActiveProject,
} from "@/lib/customerBrowserCache";

const MAX_PROJECT_MATCH_CANDIDATES = 100;

function normalizeProjectCms(value) {
  const normalized = String(value || "").trim().toLowerCase();
  const supported = {
    wordpress: "WordPress",
    shopify: "Shopify",
    wix: "Wix",
    webflow: "Webflow",
    squarespace: "Squarespace",
    custom: "Custom",
    "custom / not sure": "Custom",
    unknown: "Unknown",
  };
  return supported[normalized] || "Unknown";
}

function isOwnedProject(project, userId) {
  return project?.owner_user_id === userId;
}

async function loadOwnedProject(projectId, userId) {
  if (!projectId) return null;
  try {
    const project = await base44.entities.BusinessProject.get(projectId);
    if (isOwnedProject(project, userId)) return project;
    if (!project?.owner_user_id && project?.created_by_id === userId) {
      const updated = await base44.entities.BusinessProject.update(project.id, { owner_user_id: userId });
      return { ...project, ...(updated || {}), owner_user_id: userId };
    }
  } catch (error) {
    if (clearCustomerAuthBoundary(error)) throw error;
    // Missing or inaccessible candidates are not eligible scan identities.
  }
  return null;
}

// Resolves the active project from an owner-scoped pointer, then from the
// signed-in owner's server records. Global or cross-owner browser pointers are
// never eligible project authority.
export async function getActiveProject() {
  const user = await base44.auth.me();
  if (!user?.id) return { user, project: null };

  const storedId = readCustomerActiveProject(user.id);
  let project = await loadOwnedProject(storedId, user.id);

  if (!project) {
    const projects = await base44.entities.BusinessProject.filter(
      { owner_user_id: user.id },
      "-last_crawl_at",
      10,
    );
    project = (projects || []).find((item) => isOwnedProject(item, user.id)) || null;
  }

  if (project?.id) writeCustomerActiveProject(user.id, project.id);
  return { user, project };
}

// Resolves the BusinessProject identity for a scan target before any ScanRun is
// created. Projects are domain-scoped and explicitly owner-bound so a user's
// first Standard scan cannot persist an empty or unrelated project_id.
export async function ensureScanProject({
  projectId,
  websiteUrl,
  businessName,
  cmsPlatform,
  importantKeywords = [],
} = {}) {
  const user = await base44.auth.me();
  if (!user?.id) throw new Error("Sign in before creating a website project.");

  const normalizedUrl = normalizeScanTarget(websiteUrl);
  const domain = normalizedScanDomain(normalizedUrl);
  if (!domain) throw new Error("A valid website URL is required before creating a website project.");

  const preferredIds = [projectId, readCustomerActiveProject(user.id)]
    .map((value) => String(value || "").trim())
    .filter(Boolean);
  let matchingProject = null;
  for (const preferredId of new Set(preferredIds)) {
    const candidate = await loadOwnedProject(preferredId, user.id);
    if (candidate && normalizedScanDomain(candidate.website_url) === domain) {
      matchingProject = candidate;
      break;
    }
  }

  if (!matchingProject) {
    const projects = await base44.entities.BusinessProject.filter(
      { owner_user_id: user.id },
      "-last_crawl_at",
      MAX_PROJECT_MATCH_CANDIDATES,
    );
    matchingProject = (projects || []).find(
      (candidate) => normalizedScanDomain(candidate.website_url) === domain,
    ) || null;
  }

  if (!matchingProject) {
    const projectFields = {
      business_name: String(businessName || domain).trim() || domain,
      website_url: normalizedUrl,
      important_keywords: Array.isArray(importantKeywords) ? importantKeywords : [],
      cms_platform: normalizeProjectCms(cmsPlatform),
      status: "active",
      seo_score: 0,
      subscription_plan: "free",
      owner_user_id: user.id,
    };
    const created = await base44.entities.BusinessProject.create(projectFields);
    matchingProject = { ...projectFields, ...(created || {}) };
  }

  const stableProjectId = String(matchingProject?.id || "").trim();
  if (!stableProjectId) throw new Error("Website project creation did not return a project id.");
  if (!isOwnedProject(matchingProject, user.id)) {
    throw new Error("The website project is not owned by the signed-in user.");
  }
  writeCustomerActiveProject(user.id, stableProjectId);
  return { user, project: matchingProject, normalized_domain: domain };
}

// The one definition of entity-backed issues the user should see.
export async function getVisibleIssues(projectId, userId) {
  const issues = await base44.entities.SeoIssue.filter({
    project_id: projectId,
    owner_user_id: userId,
  });

  return (issues || []).filter((issue) => ACTIVE_STATUSES.has(issue.status));
}
