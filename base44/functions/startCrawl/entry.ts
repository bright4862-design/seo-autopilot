import { createClientFromRequest } from 'npm:@base44/sdk@0.8.31';

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) return Response.json({ error: 'Unauthorized' }, { status: 401 });

    const { projectId } = await req.json();
    if (!projectId) return Response.json({ error: 'projectId is required' }, { status: 400 });

    // Create a new crawl job
    const crawlJob = await base44.entities.CrawlJob.create({
      project_id: projectId,
      status: 'queued',
      crawl_type: 'full',
      started_at: new Date().toISOString(),
      owner_user_id: user.id,
    });

    // In production, this would call an external crawler API
    // For now, return the created job
    return Response.json({
      success: true,
      crawl_job_id: crawlJob.id,
      message: 'Crawl job created and queued. In production, this triggers the external crawler API.',
    });
  } catch (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }
});