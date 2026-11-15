// Customer-safe fallback copy for the scan form's durable terminal watcher.
// Never echo server status_detail/error_message, infer charges, or encourage a
// new scan while the persistence path may still be broken (incident #378).
export function terminalScanFailureMessage(status) {
  if (status === "failed") {
    return "This scan ended without a verified saved result. Open My scans to keep its reference, and contact FixList support before starting another scan.";
  }
  if (status === "cancelled") {
    return "This scan was cancelled before a verified result was saved. Open My scans to review it before starting another scan.";
  }
  return "";
}
