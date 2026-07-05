import { createClientFromRequest } from 'npm:@base44/sdk@0.8.31';

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) return Response.json({ error: 'Unauthorized' }, { status: 401 });

    const { projectId } = await req.json();
    if (!projectId) return Response.json({ error: 'projectId is required' }, { status: 400 });

    // Gather data
    const [project, issues] = await Promise.all([
      base44.entities.BusinessProject.get(projectId),
      base44.entities.SeoIssue.filter({ project_id: projectId }),
    ]);

    const fixed = issues.filter(i => i.status === 'auto_fixed' || i.status === 'completed').length;
    const approval = issues.filter(i => i.status === 'needs_approval').length;
    const developer = issues.filter(i => i.status === 'needs_developer').length;

    const report = await base44.entities.Report.create({
      project_id: projectId,
      owner_user_id: user.id,
      summary: `SEO scan of ${project.website_url} found ${issues.length} total issues. ${fixed} simple fixes were prepared for review, ${approval} need review, and ${developer} require developer work.`,
      fixed_count: fixed,
      approval_count: approval,
      developer_count: developer,
      seo_score: project.seo_score || 0,
      next_steps: 'Review and approve pending fixes. Export redirect map. Consider implementation packages.',
    });

    return Response.json({ success: true, report });
  } catch (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }
});