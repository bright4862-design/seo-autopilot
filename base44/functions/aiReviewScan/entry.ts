import { createClientFromRequest } from 'npm:@base44/sdk@0.8.31';

Deno.serve(async (req) => {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();

    if (!user) {
      return Response.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const {
      business_name,
      business_type,
      city,
      website_url,
      crawled_pages,
      raw_fixes,
      competitor_results
    } = await req.json();

    if (!website_url) {
      return Response.json({ error: 'website_url is required' }, { status: 400 });
    }

    const utilityPageWords = [
      'cart',
      'checkout',
      'login',
      'signin',
      'signup',
      'register',
      'account',
      'search',
      'privacy',
      'terms',
      'thank-you',
      'thankyou',
      'payment',
      'admin',
      'wp-admin',
      'reset',
      'forgot',
      'cookie',
      'legal',
      'disclaimer'
    ];

    const filteredFixes = dedupeFixes(
      (raw_fixes || []).filter((fix) => {
        const pageUrl = String(fix.page_url || '').toLowerCase();

        const isUtilityPage = utilityPageWords.some((word) =>
          pageUrl.includes(word)
        );

        const isBrokenPage =
          fix.category === '404_error' ||
          fix.category === 'internal_link' ||
          String(fix.issue_title || '').toLowerCase().includes('broken');

        if (isUtilityPage && !isBrokenPage) {
          return false;
        }

        return true;
      })
    );

    const prompt = buildPrompt({
      business_name,
      business_type,
      city,
      website_url,
      crawled_pages,
      filteredFixes,
      competitor_results
    });

    const aiResponse = await base44.integrations.Core.InvokeLLM({
      prompt,
      response_json_schema: {
        type: 'object',
        properties: {
          plain_english_summary: { type: 'string' },
          top_recommended_actions: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                title: { type: 'string' },
                reason: { type: 'string' },
                priority: {
                  type: 'string',
                  enum: ['high', 'medium', 'low']
                }
              },
              required: ['title', 'reason', 'priority']
            }
          },
          cleaned_fixes: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                page_url: { type: 'string' },
                category: { type: 'string' },
                customer_category: { type: 'string' },
                issue_title: { type: 'string' },
                plain_english_explanation: { type: 'string' },
                why_it_matters: { type: 'string' },
                current_value: { type: 'string' },
                recommended_value: { type: 'string' },
                ai_recommendation: { type: 'string' },
                priority: {
                  type: 'string',
                  enum: ['critical', 'high', 'medium', 'low']
                },
                difficulty: {
                  type: 'string',
                  enum: ['easy', 'moderate', 'developer']
                },
                status: {
                  type: 'string',
                  enum: [
                    'auto_fixed',
                    'needs_approval',
                    'needs_developer'
                  ]
                },
                can_auto_fix: { type: 'boolean' },
                requires_approval: { type: 'boolean' },
                requires_developer: { type: 'boolean' }
              },
              required: [
                'page_url',
                'category',
                'customer_category',
                'issue_title',
                'plain_english_explanation',
                'why_it_matters',
                'current_value',
                'recommended_value',
                'ai_recommendation',
                'priority',
                'difficulty',
                'status',
                'can_auto_fix',
                'requires_approval',
                'requires_developer'
              ]
            }
          },
          grouped_page_recommendations: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                page_url: { type: 'string' },
                group_title: { type: 'string' },
                summary: { type: 'string' },
                recommendations: {
                  type: 'array',
                  items: {
                    type: 'object',
                    properties: {
                      label: { type: 'string' },
                      recommendation: { type: 'string' }
                    },
                    required: ['label', 'recommendation']
                  }
                },
                priority: {
                  type: 'string',
                  enum: ['high', 'medium', 'low']
                }
              },
              required: [
                'page_url',
                'group_title',
                'summary',
                'recommendations',
                'priority'
              ]
            }
          },
          ignored_low_value_pages: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                page_url: { type: 'string' },
                reason: { type: 'string' }
              },
              required: ['page_url', 'reason']
            }
          },
          positive_findings: {
            type: 'array',
            items: { type: 'string' }
          }
        },
        required: [
          'plain_english_summary',
          'top_recommended_actions',
          'cleaned_fixes',
          'grouped_page_recommendations',
          'ignored_low_value_pages',
          'positive_findings'
        ]
      }
    });

    const reviewedFixes = aiResponse.cleaned_fixes?.length
      ? preserveStructuredFields(aiResponse.cleaned_fixes, filteredFixes)
      : filteredFixes;

    const cleanedFixes = normalizeCleanedFixes(reviewedFixes);

    return Response.json({
      success: true,
      plain_english_summary:
        aiResponse.plain_english_summary ||
        'We reviewed your scan and prepared a short list of recommended improvements.',
      top_recommended_actions:
        aiResponse.top_recommended_actions || [],
      cleaned_fixes: cleanedFixes,
      grouped_page_recommendations:
        aiResponse.grouped_page_recommendations || [],
      ignored_low_value_pages:
        aiResponse.ignored_low_value_pages || [],
      positive_findings:
        aiResponse.positive_findings || []
    });
  } catch (error) {
    return Response.json({
      success: false,
      error: error.message
    }, { status: 500 });
  }
});

function dedupeFixes(fixes) {
  const seen = new Set();
  const output = [];

  for (const fix of fixes) {
    const key = [
      fix.page_url || '',
      fix.category || '',
      fix.issue_title || ''
    ].join('|').toLowerCase();

    if (seen.has(key)) continue;

    seen.add(key);
    output.push(fix);
  }

  return output;
}

function preserveStructuredFields(cleanedFixes, sourceFixes) {
  return cleanedFixes.map((fix, index) => {
    const source = findMatchingSourceFix(fix, sourceFixes) || sourceFixes[index] || {};
    return {
      ...fix,
      affected_pages: Array.isArray(fix.affected_pages) ? fix.affected_pages : (source.affected_pages || []),
      details: {
        ...(source.details || {}),
        ...(fix.details || {})
      }
    };
  });
}

function findMatchingSourceFix(fix, sourceFixes) {
  return (sourceFixes || []).find((source) =>
    String(source.page_url || '') === String(fix.page_url || '') &&
    String(source.category || '') === String(fix.category || '') &&
    String(source.issue_title || '') === String(fix.issue_title || '')
  ) || (sourceFixes || []).find((source) =>
    String(source.page_url || '') === String(fix.page_url || '') &&
    String(source.category || '') === String(fix.category || '')
  );
}

function normalizeCleanedFixes(fixes) {
  return dedupeFixes(fixes).map((fix) => {
    const status =
      fix.status ||
      (fix.requires_developer
        ? 'needs_developer'
        : fix.requires_approval
          ? 'needs_approval'
          : 'auto_fixed');

    return {
      ...fix,
      status,
      can_auto_fix: Boolean(fix.can_auto_fix),
      requires_approval: Boolean(fix.requires_approval),
      requires_developer: Boolean(fix.requires_developer),
      affected_pages: Array.isArray(fix.affected_pages) ? fix.affected_pages : [],
      details: fix.details && typeof fix.details === 'object' ? fix.details : {},
      confidence_score: fix.confidence_score || 90
      };
  });
}

function buildPrompt({
  business_name,
  business_type,
  city,
  website_url,
  crawled_pages,
  filteredFixes,
  competitor_results
}) {
  return `
You are an expert SEO strategist for small business websites.

Your job is to turn scan findings into a short, useful, plain-English action plan for a non-technical business owner.

Important rules:
- Do not overwhelm the user.
- Do not show duplicate issues.
- Ignore low-value utility pages such as cart, checkout, login, account, privacy, terms, search, and thank-you pages unless they are broken.
- Prioritize homepage, service pages, product pages, location pages, about page, and high-value conversion pages.
- Use simple language.
- Do not use technical jargon unless you explain it.
- Do not say anything was fixed or published.
- Use "prepared," "recommended," "review," and "may help."
- Do not promise rankings.
- Merge related issues for the same page into one grouped recommendation.
- Make the output feel like a smart assistant reviewed the site, not like a raw scan report.
- Keep recommendations practical for a small business owner.
- If a raw fix includes affected_pages or details, keep customer-facing text clean and do not move affected pages into ai_recommendation; the system preserves those structured fields after your review.
- Be balanced: start the summary with what the site already does well, then frame remaining items as cleanup opportunities. Never make a healthy site sound broken. Example tone: "Your website has a solid SEO foundation with dedicated service pages and strong trust signals. The main opportunities are cleanup items: review search descriptions, fix placeholder-like content if visible, and have a developer review preferred-page settings."
- positive_findings: if the site has dedicated service, product, or loan pages, include "Your site has a strong service-page foundation." If pages include reviews, proof numbers, testimonials, phone numbers, or clear calls to action, include "Your site already includes strong trust signals." Add other genuine strengths you notice. Return an empty array only if nothing positive stands out.
- Preferred-page settings: if the raw fixes include duplicate-page / canonical findings, keep them merged as ONE fix titled "Review preferred-page settings across important pages" with affected_pages preserved as a structured array, status "needs_developer", priority "medium". Never create one card per page. In customer-facing text say "preferred-page settings", "main version of the page", or "duplicate-page settings".
- Placeholder text: if the raw fixes flag placeholder-like text (gvar, undefined, null, NaN, [object Object], {{ }}, lorem ipsum, placeholder), keep it as ONE high-priority developer fix titled "Important numbers may not be showing correctly to search engines".
- Search descriptions: for the homepage and service pages, write a recommended description specific to this business and page (use the crawled page titles/headings). Style example for a lender homepage: "Center Street Lending provides real estate investment loans for fix-and-flip, new construction, bridge, and short-term rental projects. Apply online or speak with a lending expert." Style example for a service page: "Explore fix-and-flip loans from Center Street Lending, including flexible rehab financing, competitive terms, in-house servicing, and fast investor-focused funding."

Business name:
${business_name || ''}

Business type:
${business_type || ''}

City or service area:
${city || ''}

Website:
${website_url || ''}

Crawled pages:
${JSON.stringify(crawled_pages || [], null, 2)}

Recommendations after basic filtering:
${JSON.stringify(filteredFixes || [], null, 2)}

Competitor results:
${JSON.stringify(competitor_results || [], null, 2)}

Return JSON only.

Return this exact structure:
{
  "plain_english_summary": "",
  "top_recommended_actions": [
    {
      "title": "",
      "reason": "",
      "priority": "high | medium | low"
    }
  ],
  "cleaned_fixes": [
    {
      "page_url": "",
      "category": "",
      "customer_category": "",
      "issue_title": "",
      "plain_english_explanation": "",
      "why_it_matters": "",
      "current_value": "",
      "recommended_value": "",
      "ai_recommendation": "",
      "priority": "critical | high | medium | low",
      "difficulty": "easy | moderate | developer",
      "status": "auto_fixed | needs_approval | needs_developer",
      "can_auto_fix": true,
      "requires_approval": false,
      "requires_developer": false
    }
  ],
  "grouped_page_recommendations": [
    {
      "page_url": "",
      "group_title": "",
      "summary": "",
      "recommendations": [
        {
          "label": "",
          "recommendation": ""
        }
      ],
      "priority": "high | medium | low"
    }
  ],
  "ignored_low_value_pages": [
    {
      "page_url": "",
      "reason": ""
    }
  ],
  "positive_findings": [""]
}
`;
}