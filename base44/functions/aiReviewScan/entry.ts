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
          }
        },
        required: [
          'plain_english_summary',
          'top_recommended_actions',
          'cleaned_fixes',
          'grouped_page_recommendations',
          'ignored_low_value_pages'
        ]
      }
    });

    const cleanedFixes = normalizeCleanedFixes(
      aiResponse.cleaned_fixes?.length
        ? aiResponse.cleaned_fixes
        : filteredFixes
    );

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
        aiResponse.ignored_low_value_pages || []
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

Your job is to turn raw crawl findings into a short, useful, plain-English action plan for a non-technical business owner.

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
- Make the output feel like a smart assistant reviewed the site, not like a raw crawler report.
- Keep recommendations practical for a small business owner.

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

Raw fixes after basic filtering:
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
  ]
}
`;
}