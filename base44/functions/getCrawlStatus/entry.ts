import { createClientFromRequest } from 'npm:@base44/sdk@0.8.31';

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) return Response.json({ error: 'Unauthorized' }, { status: 401 });

    const { crawlJobId } = await req.json();
    if (!crawlJobId) return Response.json({ error: 'crawlJobId is required' }, { status: 400 });

    const crawlJob = await base44.entities.CrawlJob.get(crawlJobId);
    return Response.json({ success: true, crawlJob });
  } catch (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }
});