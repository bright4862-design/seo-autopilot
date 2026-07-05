// Mock data helpers for demo state
export const MOCK_PROJECT = {
  business_name: "Sunshine Plumbing & Heating",
  website_url: "https://sunshineplumbing.com",
  business_type: "Plumbing & HVAC",
  city: "Denver",
  service_area: "Denver Metro Area",
  main_services: "Emergency plumbing, water heater installation, HVAC repair, drain cleaning",
  cms_platform: "WordPress",
  status: "active",
  seo_score: 62,
  subscription_plan: "diy",
  last_crawl_at: "2026-06-28T10:00:00Z",
  next_crawl_at: "2026-07-28T10:00:00Z",
};

export const MOCK_CRAWL_JOB = {
  status: "complete",
  crawl_type: "full",
  pages_found: 47,
  pages_crawled: 47,
  js_pages_rendered: 12,
  started_at: "2026-06-28T10:00:00Z",
  completed_at: "2026-06-28T10:35:00Z",
};

export const MOCK_ISSUES = [
  { page_url: "/services", category: "meta_title", priority: "high", status: "auto_fixed", issue_title: "Missing page title on Services page", plain_english_explanation: "Your Services page didn't have a unique title tag. We generated one based on your business name and services.", why_it_matters: "Page titles are the first thing people see in Google search results. Without one, Google makes up its own — and it's usually not great.", current_value: "(empty)", recommended_value: "Plumbing & HVAC Services | Sunshine Plumbing Denver", ai_recommendation: "We prepared a title using your business name, location, and main services.", confidence_score: 92, can_auto_fix: true, requires_approval: false, requires_developer: false },
  { page_url: "/about", category: "meta_description", priority: "medium", status: "needs_approval", issue_title: "Missing search description on About page", plain_english_explanation: "Your About page doesn't have a search description. This is the short summary that shows under your page title in Google.", why_it_matters: "A good search description convinces people to click your result instead of a competitor's.", current_value: "(empty)", recommended_value: "Sunshine Plumbing & Heating has served the Denver metro area for 15+ years. Licensed, insured, and ready to help with plumbing & HVAC.", ai_recommendation: "We wrote a description highlighting your experience and service area.", confidence_score: 85, can_auto_fix: false, requires_approval: true, requires_developer: false },
  { page_url: "/old-summer-promo", category: "404_error", priority: "critical", status: "open", issue_title: "Broken page returning 404 error", plain_english_explanation: "This page no longer exists but people (and Google) are still trying to visit it. It shows an error page.", why_it_matters: "404 errors frustrate visitors and waste your SEO value. If other sites link here, that link juice is lost.", current_value: "404 Not Found", recommended_value: "Redirect to /services or /specials", ai_recommendation: "Set up a redirect from this old promo page to your current specials or services page.", confidence_score: 90, can_auto_fix: false, requires_approval: true, requires_developer: false },
  { page_url: "/water-heater-repair", category: "canonical", priority: "medium", status: "needs_approval", issue_title: "Preferred page setting points to a different URL version", plain_english_explanation: "This page's preferred page setting points to a URL with a trailing slash, but the actual URL doesn't have one. This confuses Google about which version is the 'real' page.", why_it_matters: "When Google sees two versions of the same page, it may split your ranking power between them.", current_value: "https://sunshineplumbing.com/water-heater-repair/", recommended_value: "https://sunshineplumbing.com/water-heater-repair", ai_recommendation: "Update the preferred page setting to match the actual URL without trailing slash.", confidence_score: 95, can_auto_fix: false, requires_approval: true, requires_developer: false },
  { page_url: "/drain-cleaning", category: "thin_content", priority: "high", status: "needs_developer", issue_title: "Very thin content on service page", plain_english_explanation: "This page only has 87 words. That's not enough for Google to understand what it's about or rank it well.", why_it_matters: "Pages with very little content rarely rank in Google. Your competitors' similar pages have 500-1,200 words.", current_value: "87 words", recommended_value: "500+ words with service details, FAQ, and service area info", ai_recommendation: "A developer or content writer should expand this page with service details, pricing info, FAQs, and local service area information.", confidence_score: 88, can_auto_fix: false, requires_approval: false, requires_developer: true },
  { page_url: "/contact", category: "schema", priority: "medium", status: "needs_developer", issue_title: "Missing LocalBusiness trust signals", plain_english_explanation: "Your contact page doesn't have structured data telling Google your business name, address, phone, and hours.", why_it_matters: "Trust signals helps Google show rich results like your phone number, hours, and star ratings directly in search.", current_value: "No schema found", recommended_value: "Add LocalBusiness schema with NAP, hours, and service area", ai_recommendation: "A developer should add LocalBusiness JSON-LD schema to your contact page.", confidence_score: 95, can_auto_fix: false, requires_approval: false, requires_developer: true },
  { page_url: "/blog/tips", category: "internal_link", priority: "low", status: "auto_fixed", issue_title: "Broken internal link to removed blog post", plain_english_explanation: "This page links to a blog post that no longer exists.", why_it_matters: "Broken links make your site look unmaintained and waste scan time.", current_value: "Link to /blog/summer-tips-2024 (404)", recommended_value: "Remove or update the link", ai_recommendation: "We flagged this link for removal.", confidence_score: 80, can_auto_fix: true, requires_approval: false, requires_developer: false },
  { page_url: "/services/hvac", category: "js_rendering", priority: "high", status: "needs_developer", issue_title: "Page content only appears after JavaScript runs", plain_english_explanation: "The main content on this page is loaded by JavaScript. Google might not see it when scanning.", why_it_matters: "If Google can't read your content without running JavaScript, it may not index or rank the page properly.", current_value: "Content missing in raw HTML", recommended_value: "Server-side render or pre-render key content", ai_recommendation: "A developer should ensure key content is in the initial HTML response.", confidence_score: 82, can_auto_fix: false, requires_approval: false, requires_developer: true },
  { page_url: "/sitemap.xml", category: "sitemap", priority: "medium", status: "needs_approval", issue_title: "Sitemap contains URLs that return 404", plain_english_explanation: "Your sitemap lists 3 pages that no longer exist. This tells Google to crawl pages that aren't there.", why_it_matters: "A clean sitemap helps Google find your real pages faster and wastes less of your scan time.", current_value: "3 URLs returning 404 in sitemap", recommended_value: "Remove 404 URLs from sitemap.xml", ai_recommendation: "Remove the broken URLs from your sitemap. If using WordPress, regenerate with Yoast or RankMath.", confidence_score: 95, can_auto_fix: false, requires_approval: true, requires_developer: false },
  { page_url: "/", category: "performance", priority: "medium", status: "needs_developer", issue_title: "Homepage loads slowly on mobile", plain_english_explanation: "Your homepage takes over 5 seconds to load on a mobile connection. Most visitors leave after 3 seconds.", why_it_matters: "Google uses page speed as a ranking factor, and slow pages lose customers.", current_value: "5.2s mobile load time", recommended_value: "Under 3 seconds", ai_recommendation: "A developer should optimize images, reduce JavaScript, and consider lazy loading.", confidence_score: 78, can_auto_fix: false, requires_approval: false, requires_developer: true },
];

export const MOCK_REDIRECTS = [
  { broken_url: "/old-summer-promo", status_code: 404, recommended_destination: "/specials", reason: "Old promotional page — redirect to current specials", confidence_score: 90, approval_status: "pending" },
  { broken_url: "/blog/summer-tips-2024", status_code: 404, recommended_destination: "/blog", reason: "Removed blog post — redirect to blog index", confidence_score: 85, approval_status: "pending" },
  { broken_url: "/services/ac-repair", status_code: 404, recommended_destination: "/services/hvac", reason: "Page removed — related HVAC service page exists", confidence_score: 88, approval_status: "approved" },
  { broken_url: "/team", status_code: 301, recommended_destination: "/about", reason: "Team page merged into About — confirm redirect", confidence_score: 75, approval_status: "pending" },
];

export const MOCK_METADATA = [
  { page_url: "/", current_title: "Home - Sunshine Plumbing", recommended_title_1: "Sunshine Plumbing & Heating | Denver's Trusted Plumber", recommended_title_2: "Denver Plumbing & HVAC Services | Sunshine Plumbing", recommended_title_3: "24/7 Plumbing & Heating in Denver | Sunshine Plumbing", current_meta_description: "", recommended_description_1: "Denver's trusted plumbing & HVAC company. Emergency repairs, water heaters, drain cleaning & more. Licensed, insured, serving the Denver metro area.", recommended_description_2: "Need a plumber in Denver? Sunshine Plumbing offers 24/7 emergency service, water heater installation, and HVAC repair. Call for a free estimate.", recommended_description_3: "Family-owned plumbing & heating company serving Denver since 2010. Fast, reliable service for homes and businesses. Free estimates available.", suggested_h1: "Denver's Trusted Plumbing & HVAC Experts", suggested_slug: "/", suggested_faq_ideas: "What areas do you serve? How quickly can you respond to emergencies? Do you offer free estimates? What plumbing services do you provide?", approval_status: "pending" },
  { page_url: "/services", current_title: "", recommended_title_1: "Plumbing & HVAC Services | Sunshine Plumbing Denver", recommended_title_2: "Our Services - Plumbing, Heating & Cooling | Denver CO", recommended_title_3: "Professional Plumbing & HVAC Services in Denver Metro", current_meta_description: "", recommended_description_1: "Full-service plumbing and HVAC: emergency repairs, water heater installation, drain cleaning, furnace repair, and AC service in the Denver metro area.", recommended_description_2: "From leaky faucets to full HVAC systems — Sunshine Plumbing handles it all. See our complete list of plumbing and heating services.", recommended_description_3: "Professional plumbing & HVAC services for Denver homes and businesses. Licensed technicians, upfront pricing, same-day service available.", suggested_h1: "Plumbing & HVAC Services for Denver Homes & Businesses", suggested_slug: "/services", suggested_faq_ideas: "What plumbing services do you offer? Do you repair water heaters? Can you fix my AC? Do you offer financing?", approval_status: "pending" },
];

export const MOCK_COMPETITORS = [
  { name: "Rocky Mountain Plumbing", website_url: "https://rockymtnplumbing.com", notes: "Strong local presence, good reviews", service_pages_count: 12, title_quality_score: 85, meta_coverage_pct: 90, content_depth_score: 78, faq_usage: true, schema_usage: true, broken_links_count: 1 },
  { name: "Mile High Plumbing Co", website_url: "https://milehighplumbingco.com", notes: "Aggressive SEO, lots of content", service_pages_count: 18, title_quality_score: 90, meta_coverage_pct: 95, content_depth_score: 88, faq_usage: true, schema_usage: true, broken_links_count: 0 },
  { name: "Denver Drain Pros", website_url: "https://denverdrainpros.com", notes: "Newer competitor, basic site", service_pages_count: 6, title_quality_score: 60, meta_coverage_pct: 50, content_depth_score: 45, faq_usage: false, schema_usage: false, broken_links_count: 5 },
];

export const MOCK_DEV_RECOMMENDATIONS = [
  { title: "Add dedicated service pages", description: "Create individual pages for each service (drain cleaning, water heater repair, HVAC maintenance, etc.) with unique content, FAQs, and local info.", category: "content_pages", priority: "high", business_impact: "Your top competitor has 12 service pages vs your 3. Individual pages rank better for specific searches like 'water heater repair Denver'.", estimated_complexity: "moderate", recommended_package: "500_cleanup", status: "open" },
  { title: "Add LocalBusiness trust signals", description: "Add structured data to your site so Google can show your business info (hours, phone, address) directly in search results.", category: "technical_seo", priority: "high", business_impact: "Trust signals can increase click-through rates by 20-30% by showing rich results in Google.", estimated_complexity: "simple", recommended_package: "diy", status: "open" },
  { title: "Fix JavaScript-rendered navigation", description: "Your main navigation menu loads via JavaScript. This means Google might not see all your pages when scanning.", category: "technical_seo", priority: "high", business_impact: "If Google can't find your pages through navigation, they may not get indexed at all.", estimated_complexity: "complex", recommended_package: "custom_rebuild", status: "open" },
  { title: "Improve mobile page speed", description: "Your homepage takes 5.2 seconds to load on mobile. Optimize images, reduce JavaScript, and enable caching.", category: "speed_mobile", priority: "medium", business_impact: "Google uses page speed as a ranking factor. Faster sites also convert more visitors into customers.", estimated_complexity: "moderate", recommended_package: "500_cleanup", status: "open" },
  { title: "Create city/service landing pages", description: "Build pages targeting specific cities in your service area (e.g., 'Plumber in Aurora CO', 'HVAC Repair Lakewood').", category: "content_pages", priority: "medium", business_impact: "Location-specific pages can capture local searches you're currently missing.", estimated_complexity: "moderate", recommended_package: "500_cleanup", status: "open" },
  { title: "Clean up duplicate URL versions", description: "Your site is accessible with and without 'www' and with and without trailing slashes. This creates duplicate content.", category: "technical_seo", priority: "medium", business_impact: "Duplicate URLs split your ranking power. Consolidating them can boost your existing rankings.", estimated_complexity: "simple", recommended_package: "diy", status: "open" },
  { title: "Add FAQ sections to service pages", description: "Add frequently asked questions with answers to each service page. Use FAQ schema for rich results.", category: "content_pages", priority: "low", business_impact: "FAQ rich results can appear directly in Google, increasing visibility and clicks.", estimated_complexity: "simple", recommended_package: "diy", status: "open" },
  { title: "Create SEO-safe redirect map before rebuild", description: "If you're planning a site redesign, create a complete redirect map first to preserve SEO value.", category: "rebuild_migration", priority: "low", business_impact: "Rebuilding without redirects can destroy years of SEO progress.", estimated_complexity: "moderate", recommended_package: "custom_rebuild", status: "open" },
];

export const MOCK_CRAWLED_PAGES = [
  { url: "/", status_code: 200, title: "Home - Sunshine Plumbing", meta_description: "", h1: "Welcome", canonical_url: "https://sunshineplumbing.com/", word_count: 320, indexable: true, in_sitemap: true, rendered_title: "Home - Sunshine Plumbing", rendered_meta_description: "", rendered_canonical: "https://sunshineplumbing.com/", js_difference_detected: false },
  { url: "/services", status_code: 200, title: "", meta_description: "", h1: "Our Services", canonical_url: "", word_count: 250, indexable: true, in_sitemap: true, rendered_title: "Our Services - Sunshine Plumbing", rendered_meta_description: "", rendered_canonical: "", js_difference_detected: true },
  { url: "/services/hvac", status_code: 200, title: "HVAC Services", meta_description: "HVAC services in Denver", h1: "", canonical_url: "https://sunshineplumbing.com/services/hvac", word_count: 45, indexable: true, in_sitemap: true, rendered_title: "HVAC Services", rendered_meta_description: "Full HVAC services in the Denver metro area", rendered_canonical: "https://sunshineplumbing.com/services/hvac", js_difference_detected: true },
  { url: "/about", status_code: 200, title: "About Us", meta_description: "", h1: "About Sunshine Plumbing", canonical_url: "https://sunshineplumbing.com/about", word_count: 480, indexable: true, in_sitemap: true, rendered_title: "About Us", rendered_meta_description: "", rendered_canonical: "https://sunshineplumbing.com/about", js_difference_detected: false },
  { url: "/contact", status_code: 200, title: "Contact Us", meta_description: "Contact Sunshine Plumbing", h1: "Get In Touch", canonical_url: "https://sunshineplumbing.com/contact", word_count: 150, indexable: true, in_sitemap: true, rendered_title: "Contact Us", rendered_meta_description: "Contact Sunshine Plumbing", rendered_canonical: "https://sunshineplumbing.com/contact", js_difference_detected: false },
  { url: "/water-heater-repair", status_code: 200, title: "Water Heater Repair Denver", meta_description: "Water heater repair and installation in Denver.", h1: "Water Heater Repair & Installation", canonical_url: "https://sunshineplumbing.com/water-heater-repair/", word_count: 650, indexable: true, in_sitemap: true, rendered_title: "Water Heater Repair Denver", rendered_meta_description: "Water heater repair and installation in Denver.", rendered_canonical: "https://sunshineplumbing.com/water-heater-repair/", js_difference_detected: false },
  { url: "/drain-cleaning", status_code: 200, title: "Drain Cleaning", meta_description: "", h1: "Drain Cleaning", canonical_url: "https://sunshineplumbing.com/drain-cleaning", word_count: 87, indexable: true, in_sitemap: true, rendered_title: "Drain Cleaning", rendered_meta_description: "", rendered_canonical: "https://sunshineplumbing.com/drain-cleaning", js_difference_detected: false },
  { url: "/old-summer-promo", status_code: 404, title: "", meta_description: "", h1: "", canonical_url: "", word_count: 0, indexable: false, in_sitemap: true, rendered_title: "", rendered_meta_description: "", rendered_canonical: "", js_difference_detected: false },
  { url: "/blog/summer-tips-2024", status_code: 404, title: "", meta_description: "", h1: "", canonical_url: "", word_count: 0, indexable: false, in_sitemap: true, rendered_title: "", rendered_meta_description: "", rendered_canonical: "", js_difference_detected: false },
];

export const PRIORITY_COLORS = {
  critical: "bg-red-100 text-red-700 border-red-200",
  high: "bg-orange-100 text-orange-700 border-orange-200",
  medium: "bg-yellow-100 text-yellow-700 border-yellow-200",
  low: "bg-blue-100 text-blue-700 border-blue-200",
};

export const STATUS_COLORS = {
  open: "bg-gray-100 text-gray-700",
  auto_fixed: "bg-green-100 text-green-700",
  needs_approval: "bg-amber-100 text-amber-700",
  approved: "bg-blue-100 text-blue-700",
  rejected: "bg-red-100 text-red-700",
  needs_developer: "bg-purple-100 text-purple-700",
  in_progress: "bg-cyan-100 text-cyan-700",
  completed: "bg-emerald-100 text-emerald-700",
};

export const STATUS_LABELS = {
  open: "Recommended",
  auto_fixed: "Prepared",
  needs_approval: "Needs review",
  approved: "Approved",
  rejected: "Not now",
  needs_developer: "May need help",
  in_progress: "In progress",
  completed: "Reviewed",
};

export const CATEGORY_LABELS = {
  meta_title: "Search title",
  meta_description: "Search description",
  "404_error": "Broken page",
  redirect: "Page redirect",
  canonical: "Preferred page setting",
  sitemap: "Website setup",
  robots_txt: "Website setup",
  js_rendering: "Content visibility",
  internal_link: "Website link",
  thin_content: "Page content",
  duplicate_content: "Page content",
  schema: "Trust signals",
  performance: "Performance",
  web_dev: "Website improvement",
};