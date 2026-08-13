const payload = {
  request_id: "scanreq_gatewayprobe_20260813_1254_02",
  idempotency_key: "scanreq_gatewayprobe_20260813_1254_02",
  scan_id: "6a7da228918a913c8cbf996b",
  scan_run_id: "6a7da228918a913c8cbf996b",
  website_url: "https://example.com/",
  submitted_url: "https://example.com/",
  normalized_domain: "example.com",
  scan_mode: "standard_150",
  business_name: "Dispatch Probe 2",
  cms_platform: "Custom",
};
try {
  const response = await base44.functions.invoke("startStandardScanJob", payload);
  console.log(JSON.stringify({ ok: true, data: response?.data ?? response }, null, 2));
} catch (error) {
  console.log(JSON.stringify({
    ok: false,
    status: Number(error?.response?.status || error?.status || 0),
    data: error?.response?.data || null,
    message: String(error?.message || "invoke_failed").slice(0, 180),
  }, null, 2));
}
