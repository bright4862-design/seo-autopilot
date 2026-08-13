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
const EMPTY_STATE = {
  status: "",
  stalled: false,
  domain: "",
  statusDetail: "",
  pagesFound: 0,
  pagesCrawled: 0,
};

// The run is already fetched on every tick to decide completion. Surfacing the
// discovery counters and domain from that same read costs no extra request and
// lets the scan feel alive instead of showing an unchanging spinner.
function progressFrom(run) {
  return {
    domain: String(run?.normalized_domain || ""),
    statusDetail: String(run?.status_detail || ""),
    pagesFound: Number(run?.pages_found) || 0,
    pagesCrawled: Number(run?.pages_crawled) || 0,
  };
}

export default function useDurableScanCompletion(scanId, active) {
  const navigate = useNavigate();
  const [state, setState] = useState(EMPTY_STATE);

  useEffect(() => {
    if (!scanId || !active) {
      setState(EMPTY_STATE);
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
        setState({ status, stalled: false, ...progressFrom(run) });
        navigate(`/dashboard?scan=complete&scan_id=${encodeURIComponent(scanId)}`);
        return;
      }
      if (TERMINAL_FAILURE_STATUSES.has(status)) {
        setState({ status, stalled: false, ...progressFrom(run) });
        return;
      }
      // A transient null read never ends the watch; it just waits for the
      // next tick, so an RLS hiccup cannot leave the customer stranded.
      // A transient null read must not blank counters that were already shown,
      // so progress only ever moves forward within one watch.
      setState((previous) => {
        const next = progressFrom(run);
        return {
          status,
          stalled: Date.now() - startedAt >= STALLED_AFTER_MS,
          domain: next.domain || previous.domain,
          statusDetail: next.statusDetail || previous.statusDetail,
          pagesFound: Math.max(previous.pagesFound, next.pagesFound),
          pagesCrawled: Math.max(previous.pagesCrawled, next.pagesCrawled),
        };
      });
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