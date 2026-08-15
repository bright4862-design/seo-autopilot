import { base44 } from "@/api/base44Client";

const EVENT_CATEGORY = {
  user_registered: "auth",
  user_logged_in: "auth",
  onboarding_started: "onboarding",
  onboarding_completed: "onboarding",
  scan_page_viewed: "scan",
  scan_started: "scan",
  scan_completed: "scan",
  scan_failed: "scan",
  fix_list_viewed: "recommendation",
  recommendation_opened: "recommendation",
  recommendation_approved: "recommendation",
  recommendation_rejected: "recommendation",
  recommendation_marked_reviewed: "recommendation",
  recommendation_copied: "recommendation",
  request_help_clicked: "recommendation",
  competitor_gaps_viewed: "competitor",
  keyword_gap_analysis_started: "competitor",
  keyword_gap_analysis_completed: "competitor",
  improvement_plan_created: "competitor",
  scan_report_viewed: "report",
  report_generated: "report",
  report_exported: "report",
  billing_viewed: "billing",
  checkout_started: "billing",
  payment_returned: "billing",
  access_activated: "billing",
  access_activation_delayed: "billing",
  scan_accepted: "scan",
  result_viewed: "recommendation",
  fix_opened: "recommendation",
  waitlist_joined: "billing",
  cleanup_requested: "help",
  contact_submitted: "help",
  assistant_opened: "assistant",
  assistant_message_sent: "assistant",
};

const QUEUE_KEY = "seo_autopilot_pending_analytics";

function normalizeMetadata(metadata) {
  if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) return {};
  return metadata;
}

export function queueEvent(eventName, metadata = {}) {
  try {
    const pending = JSON.parse(sessionStorage.getItem(QUEUE_KEY) || "[]");
    pending.push({ eventName, metadata: normalizeMetadata(metadata) });
    sessionStorage.setItem(QUEUE_KEY, JSON.stringify(pending.slice(-10)));
  } catch (e) {}
}

export async function flushQueuedEvents() {
  try {
    const pending = JSON.parse(sessionStorage.getItem(QUEUE_KEY) || "[]");
    if (!pending.length) return;
    const remaining = [];
    for (const event of pending) {
      if (!await trackEvent(event.eventName, event.metadata)) remaining.push(event);
    }
    if (remaining.length > 0) {
      sessionStorage.setItem(QUEUE_KEY, JSON.stringify(remaining.slice(-10)));
    } else {
      sessionStorage.removeItem(QUEUE_KEY);
    }
  } catch (e) {}
}

export async function trackEvent(eventName, metadata = {}) {
  try {
    const event_category = EVENT_CATEGORY[eventName];
    if (!event_category) return false;

    const user = await base44.auth.me();
    if (!user?.id) return false;

    let project = null;
    try {
      const projects = await base44.entities.BusinessProject.list("-created_date", 1);
      project = projects[0] || null;
    } catch (e) {}

    await base44.entities.AnalyticsEvent.create({
      owner_user_id: user.id,
      project_id: project?.id || "",
      event_name: eventName,
      event_category,
      page: typeof window !== "undefined" ? window.location.pathname : "",
      metadata: normalizeMetadata(metadata),
      created_at: new Date().toISOString(),
    });
    return true;
  } catch (e) {
    return false;
  }
}
