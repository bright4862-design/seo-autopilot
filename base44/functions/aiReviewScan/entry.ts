import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();

    if (!user) {
      return Response.json(
        {
          success: false,
          error: "Unauthorized",
        },
        { status: 401 }
      );
    }

    const body = await req.json().catch(() => ({}));

    return Response.json({
      success: true,
      message: "runAiReview is deployed and reachable",
      received_keys: Object.keys(body || {}),
      crawled_pages_count: Array.isArray(body.crawled_pages)
        ? body.crawled_pages.length
        : 0,
      raw_fixes_count: Array.isArray(body.raw_fixes)
        ? body.raw_fixes.length
        : 0,
      cleaned_fixes: Array.isArray(body.raw_fixes) ? body.raw_fixes : [],
      raw_fixes: Array.isArray(body.raw_fixes) ? body.raw_fixes : [],
      fixes: Array.isArray(body.raw_fixes) ? body.raw_fixes : [],
      findings: Array.isArray(body.raw_fixes) ? body.raw_fixes : [],
      recommendations: Array.isArray(body.raw_fixes) ? body.raw_fixes : [],
      recommended_actions: [],
      top_recommended_actions: [],
      competitor_insights: [],
      crawled_pages: Array.isArray(body.crawled_pages)
        ? body.crawled_pages
        : [],
      pages: Array.isArray(body.crawled_pages) ? body.crawled_pages : [],
    });
  } catch (error) {
    return Response.json(
      {
        success: false,
        error: error?.message || "runAiReview test failed",
        stack: error?.stack || "",
      },
      { status: 500 }
    );
  }
});