import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getScanRunWithFixList } from "@/lib/scanRuns";

const POLL_INTERVAL_MS = 3000;
const STALLED_AFTER_MS = 150_000;
const TERMINAL_FAILURE_STATUSES = new Set(["failed", "cancelled"]);

// The browser's own function chain is not the only path to a saved result.
// Once the durable ScanRun reaches "complete" with a fix_list_id, that exact
// result must open even if the scanner response, the review response, or the
// navigation callback was missed (tab backgrounded, request epoch changed,
// preview frame reload). No substitute scan is ever opened: only scanId.
export default function useDurableScanCompletion(scanId, active) {
  const navigate = useNavigate();
  const [state, setState] = useState({ status: "", stalled: false });

  useEffect(() => {
    if (!scanId || !active) {
      setState({ status: "", stalled: false });
      return undefined;
    }
    let cancelled = false;
    const startedAt = Date.now();

    async function check() {
      const bundle = await getScanRunWithFixList(scanId).catch(() => null);
      if (cancelled) return;
      const run = bundle?.run || null;
      const fixListId = bundle?.fixList?.id || run?.fix_list_id || "";
      const status = String(run?.status || "");

      if (["complete", "limited"].includes(status) && fixListId) {
        setState({ status, stalled: false });
        navigate(`/dashboard?scan=complete&scan_id=${encodeURIComponent(scanId)}`);
        return;
      }
      if (TERMINAL_FAILURE_STATUSES.has(status)) {
        setState({ status, stalled: false });
        return;
      }
      // A transient null read never ends the watch; it just waits for the
      // next tick, so an RLS hiccup cannot leave the customer stranded.
      setState({ status, stalled: Date.now() - startedAt >= STALLED_AFTER_MS });
    }

    check();
    const timer = window.setInterval(check, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [scanId, active, navigate]);

  return state;
}