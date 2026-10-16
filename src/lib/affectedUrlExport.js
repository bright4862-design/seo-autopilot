import { evidenceIdentityOptions, resolveEvidenceUrl } from "./evidenceUrl.js";

function absolutePageUrl(page, item) {
  const options = evidenceIdentityOptions(item);
  if (options.identityVersion) return resolveEvidenceUrl(page, item.websiteUrl, options);
  // Preserve the serializer used by historical saved reports.
  const raw = String(page || "").trim();
  if (!raw || /^https?:\/\//i.test(raw)) return raw;
  try {
    return new URL(raw, item.websiteUrl || "https://fixlist.invalid").toString();
  } catch {
    return raw;
  }
}

function affectedUrls(item) {
  return (item.affectedPages || []).map(page => absolutePageUrl(page, item)).filter(Boolean);
}

export function serializeAffectedUrlsText(item) {
  return affectedUrls(item).join("\n");
}

export function serializeAffectedUrlsCsv(item) {
  const rows = affectedUrls(item).map(url => [url, item.title, item.rule, item.priority, item.templateFamily]);
  return [["affected_url", "finding", "rule", "priority", "template_family"], ...rows]
    .map(row => row.map(value => `"${String(value ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
}
