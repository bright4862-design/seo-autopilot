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
    const crawlJobId = body.crawlJobId || body.crawl_job_id;
    const projectId = body.projectId || body.project_id;

    if (!crawlJobId && !projectId) {
      return Response.json(
        {
          success: false,
          error: "crawlJobId or projectId is required",
        },
        { status: 400 }
      );
    }

    let crawlJob = null;

    if (crawlJobId) {
      crawlJob = await base44.entities.CrawlJob.get(crawlJobId);
    } else {
      const jobs = await base44.entities.CrawlJob.filter(
        { project_id: projectId },
        "-created_date",
        1
      );

      crawlJob = jobs[0] || null;
    }

    if (!crawlJob) {
      return Response.json(
        { success: false, error: "Crawl job not found" },
        { status: 404 }
      );
    }

    if (
      crawlJob.owner_user_id &&
      crawlJob.owner_user_id !== user.id &&
      crawlJob.created_by_id !== user.id
    ) {
      return Response.json(
        { success: false, error: "Forbidden" },
        { status: 403 }
      );
    }

    const isStale = isStaleJob(crawlJob);

    if (isStale) {
      try {
        crawlJob = await base44.entities.CrawlJob.update(crawlJob.id, {
          status: "failed",
          completed_at: new Date().toISOString(),
          error_message:
            crawlJob.error_message ||
            "The scan took too long and could not complete.",
        });
      } catch {}
    }

    const progress = getProgress(crawlJob.status);

    return Response.json({
      success: true,
      crawlJob,
      crawl_job: crawlJob,
      status: crawlJob.status,
      progress,
      is_complete: crawlJob.status === "complete",
      is_failed: crawlJob.status === "failed",
      is_running: ACTIVE_STATUSES.has(crawlJob.status),
      pages_crawled: crawlJob.pages_crawled || 0,
      pages_found: crawlJob.pages_found || 0,
      issues_found: crawlJob.issues_found || 0,
      seo_score: crawlJob.seo_score || 0,
      error_message: crawlJob.error_message || "",
    });
  } catch (error) {
    return Response.json(
      {
        success: false,
        error: error?.message || "Could not get crawl status",
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

function getProgress(status) {
  const map = {
    queued: 5,
    crawling_html: 25,
    checking_metadata: 40,
    checking_canonicals: 55,
    checking_links: 65,
    finding_competitors: 72,
    benchmarking_competitors: 82,
    generating_recommendations: 90,
    in_progress: 50,
    complete: 100,
    failed: 100,
  };

  return map[status] ?? 0;
}