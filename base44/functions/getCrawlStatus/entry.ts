import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

const ACTIVE_STATUSES = new Set([
  "queued",
  "crawling_html",
  "checking_metadata",
  "checking_canonicals",
  "checking_links",
  "finding_competitors",
  "benchmarking_competitors",
  "generating_recommendations",
  "in_progress",
]);

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
    const scanMode = body.scan_mode === "deep" ? "deep" : "quick";

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

    const existingJobs = await base44.entities.CrawlJob.filter(
      { project_id: projectId },
      "-created_date",
      5
    );

    const existingActiveJob = existingJobs.find(
      (job) => ACTIVE_STATUSES.has(job.status) && !isStaleJob(job)
    );

    if (existingActiveJob) {
      return Response.json({
        success: true,
        crawl_job_id: existingActiveJob.id,
        crawlJob: existingActiveJob,
        crawl_job: existingActiveJob,
        reused_existing_job: true,
        message: "A scan is already in progress.",
      });
    }

    const now = new Date().toISOString();

    const crawlJob = await base44.entities.CrawlJob.create({
      project_id: projectId,
      status: "queued",
      crawl_type: scanMode === "deep" ? "deep" : "full",
      started_at: now,
      completed_at: "",
      error_message: "",
      pages_found: 0,
      pages_crawled: 0,
      issues_found: 0,
      seo_score: 0,
      owner_user_id: user.id,
    });

    try {
      await base44.entities.BusinessProject.update(projectId, {
        status: "scanning",
        scan_mode: scanMode,
      });
    } catch {}

    return Response.json({
      success: true,
      crawl_job_id: crawlJob.id,
      crawlJob,
      crawl_job: crawlJob,
      reused_existing_job: false,
      scan_mode: scanMode,
      message:
        "Crawl job created. The frontend should now call runAdvancedScan and then aiReviewScan.",
    });
  } catch (error) {
    return Response.json(
      {
        success: false,
        error: error?.message || "Could not start crawl",
      },
      { status: 500 }
    );
  }
});

function isStaleJob(job) {
  if (!ACTIVE_STATUSES.has(job.status)) return false;

  const dateValue = job.started_at || job.created_date || job.created_at;

  if (!dateValue) return false;

  const ageMs = Date.now() - new Date(dateValue).getTime();

  return ageMs > 10 * 60 * 1000;
}