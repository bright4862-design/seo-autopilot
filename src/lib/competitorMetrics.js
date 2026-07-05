const SERVICE_WORDS = /service|product|treatment|location|pricing|appointment|repair|installation|consultation/i;

// Compute the customer's comparison metrics from CrawledPage records
export function computeCustomerMetrics(pages, businessType, city) {
  const okPages = pages.filter(p => p.status_code === 200);
  const titleScore = (title) => {
    if (!title) return 0;
    let s = 40;
    if (title.length >= 20 && title.length <= 70) s += 20;
    if (SERVICE_WORDS.test(title) || (businessType && title.toLowerCase().includes(String(businessType).toLowerCase()))) s += 20;
    if (city && title.toLowerCase().includes(String(city).toLowerCase())) s += 20;
    return s;
  };
  const servicePages = okPages.filter(p =>
    SERVICE_WORDS.test(p.url || '') || SERVICE_WORDS.test(p.title || '') || SERVICE_WORDS.test(p.h1 || '')
  ).length;
  const avgTitle = okPages.length ? Math.round(okPages.reduce((s, p) => s + titleScore(p.title), 0) / okPages.length) : 0;
  const metaPct = okPages.length ? Math.round((okPages.filter(p => p.meta_description).length / okPages.length) * 100) : 0;
  const avgWords = okPages.length ? okPages.reduce((s, p) => s + (p.word_count || 0), 0) / okPages.length : 0;
  const depth = avgWords <= 150 ? 30 : avgWords <= 300 ? 60 : 90;
  const broken = pages.filter(p => p.status_code === 404 || p.status_code === 0).length;
  return {
    service_pages_count: servicePages,
    title_quality_score: avgTitle,
    meta_coverage_pct: metaPct,
    content_depth_score: depth,
    broken_links_count: broken,
  };
}