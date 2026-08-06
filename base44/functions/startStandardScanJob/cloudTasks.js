// Cloud Tasks enqueue for the durable Standard 150 worker.
//
// Base44 reaps post-response work: ScanRun 6a748d5f9e8a27963ae678dc logged
// worker_scan_start via waitUntil() and then produced nothing for 247s. The
// crawl therefore runs on Cloud Run (300s request budget) and Cloud Tasks is
// the durable handoff.
//
// Task identity is derived from the existing scan_id, so a duplicate submit
// for the same ScanRun is rejected by Cloud Tasks itself (ALREADY_EXISTS)
// rather than starting a second worker against one durable row.

const TASKS_API = "https://cloudtasks.googleapis.com/v2";

export function taskNameForScan(queuePath, scanId) {
  // Deterministic: same scan_id always yields the same task name.
  const safeId = String(scanId || "").replace(/[^A-Za-z0-9_-]/g, "");
  return `${queuePath}/tasks/standard150-${safeId}`;
}

// Metadata-server token for the Cloud Run / Base44 runtime identity.
async function accessToken() {
  const direct = String(Deno.env.get("GCP_ACCESS_TOKEN") || "");
  if (direct) return direct;
  const key = String(Deno.env.get("GCP_SERVICE_ACCOUNT_KEY") || "");
  if (!key) return "";
  const { createSignedJwtAssertion } = await import("./gcpAuth.js");
  return await createSignedJwtAssertion(key);
}

export async function enqueueScanJob({ queuePath, workerUrl, invokerServiceAccount, scanId, payload }) {
  const token = await accessToken();
  if (!token) return { ok: false, failureCode: "tasks_credentials_not_configured" };

  const body = {
    task: {
      name: taskNameForScan(queuePath, scanId),
      httpRequest: {
        url: workerUrl,
        httpMethod: "POST",
        headers: { "content-type": "application/json" },
        body: btoa(JSON.stringify(payload)),
        // Cloud Run is deployed --no-allow-unauthenticated; Cloud Tasks mints
        // an OIDC token for this service account and the worker checks it.
        oidcToken: { serviceAccountEmail: invokerServiceAccount, audience: workerUrl },
      },
    },
  };

  let response;
  try {
    response = await fetch(`${TASKS_API}/${queuePath}/tasks`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
    });
  } catch {
    return { ok: false, failureCode: "tasks_unreachable" };
  }

  if (response.status === 409) {
    // The task already exists for this exact scan_id: the job is already
    // queued or running. Treat as accepted, never as a second submission.
    return { ok: true, deduplicated: true, taskName: taskNameForScan(queuePath, scanId) };
  }
  if (!response.ok) {
    return { ok: false, failureCode: `tasks_http_${response.status}` };
  }
  let created = {};
  try { created = await response.json(); } catch { /* name is best-effort */ }
  return { ok: true, deduplicated: false, taskName: String(created?.name || taskNameForScan(queuePath, scanId)) };
}
